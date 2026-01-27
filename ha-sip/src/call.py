from __future__ import annotations

import os
import re
import time
from enum import Enum
from typing import Optional, Callable, Union, Any, List

import pjsua2 as pj
import yaml
from typing_extensions import TypedDict, Literal

import account
import audio
import audio_cache
import ha
import player
import utils
from call_state_change import CallStateChange
from command_client import Command
from command_handler import CommandHandler
from constants import DEFAULT_RING_TIMEOUT, DEFAULT_DTMF_ON, DEFAULT_DTMF_OFF
from log import log
from event_sender import EventSender
from post_action import PostAction, PostActionNoop, PostActionHangup, PostActionRepeatMessage, PostActionReturn, PostActionJump

CallCallback = Callable[[CallStateChange, str, 'Call'], None]
DtmfMethod = Union[Literal['in_band'], Literal['rfc2833'], Literal['sip_info']]


class WebhookToCall(TypedDict):
    call_established: Optional[str]
    entered_menu: Optional[str]
    dtmf_digit: Optional[str]
    call_disconnected: Optional[str]
    timeout: Optional[str]
    ring_timeout: Optional[str]
    playback_done: Optional[str]


class MenuFromStdin(TypedDict):
    id: Optional[str]
    message: Optional[str]
    handle_as_template: Optional[bool]
    audio_file: Optional[str]
    language: Optional[str]
    action: Optional[Command]
    choices_are_pin: Optional[bool]
    post_action: Optional[str]
    timeout: Optional[int]
    choices: Optional[dict[Any, MenuFromStdin]]
    cache_audio: Optional[bool]
    wait_for_audio_to_finish: Optional[bool]


class Menu(TypedDict):
    id: Optional[str]
    message: Optional[str]
    handle_as_template: bool
    audio_file: Optional[str]
    language: str
    action: Optional[Command]
    choices_are_pin: bool
    post_action: PostAction
    timeout: float
    choices: Optional[dict[str, Menu]]
    default_choice: Optional[Menu]
    timeout_choice: Optional[Menu]
    parent_menu: Optional[Menu]
    cache_audio: bool
    wait_for_audio_to_finish: bool


class CallInfo(TypedDict):
    local_uri: str
    remote_uri: str
    parsed_caller: Optional[str]
    call_id: str


class CallHandling(Enum):
    LISTEN = 'LISTEN'
    ACCEPT = 'ACCEPT'

    @staticmethod
    def get_or_else(name: Optional[str], default: CallHandling) -> CallHandling:
        try:
            return CallHandling[(name or '').upper()]
        except (KeyError, AttributeError):
            return default


class Call(pj.Call):
    def __init__(
        self,
        end_point: pj.Endpoint,
        sip_account: account.Account,
        call_id: str,
        uri_to_call: Optional[str],
        menu: Optional[MenuFromStdin],
        command_handler: CommandHandler,
        event_sender: EventSender,
        ha_config: ha.HaConfig,
        ring_timeout: float,
        webhooks: Optional[WebhookToCall]
    ):
        pj.Call.__init__(self, sip_account, call_id)
        self.player: Optional[player.Player] = None
        self.audio_media: Optional[pj.AudioMedia] = None
        self.recorder: Optional[pj.AudioMediaRecorder] = None
        self.recording_file: Optional[str] = None
        self.requested_recording_filename: Optional[str] = None
        self.connected = False
        self.current_input = ''
        self.end_point = end_point
        self.account = sip_account
        self.uri_to_call = uri_to_call
        self.ha_config = ha_config
        self.ring_timeout = ring_timeout
        self.settle_time = sip_account.config.settle_time
        self.webhooks: WebhookToCall = webhooks or WebhookToCall(
            call_established=None,
            entered_menu=None,
            dtmf_digit=None,
            call_disconnected=None,
            timeout=None,
            ring_timeout=None,
            playback_done=None,
        )
        self.command_handler = command_handler
        self.event_sender = event_sender
        self.scheduled_post_action: Optional[PostAction] = None
        self.playback_is_done = True
        self.wait_for_audio_to_finish = False
        self.last_seen = time.time()
        self.call_settled_at: Optional[float] = None
        self.answer_at: Optional[float] = None
        self.tone_gen: Optional[pj.ToneGenerator] = None
        self.call_info: Optional[CallInfo] = None
        self.pressed_digit_list: List[str] = []
        self.callback_id, other_ids = self.get_callback_ids()
        self.current_playback: Optional[ha.CurrentPlayback] = None
        self.menu = self.normalize_menu(menu) if menu else self.get_standard_menu()
        self.menu_map = self.create_menu_map(self.menu)
        Call.pretty_print_menu(self.menu)
        log(self.account.config.index, 'Registering call with id %s' % self.callback_id)
        self.command_handler.register_call(self.callback_id, self, other_ids)

    def handle_events(self) -> None:
        if not self.connected and time.time() - self.last_seen > self.ring_timeout:
            self.trigger_webhook({
                'event': 'ring_timeout',
                'caller': self.call_info['remote_uri'] if self.call_info else 'unknown',
                'parsed_caller': self.call_info['parsed_caller'] if self.call_info else None,
                'sip_account': self.account.config.index,
                'call_id': self.call_info['call_id'] if self.call_info else None,
                'internal_id': self.callback_id,
            })
            log(self.account.config.index, 'Ring timeout of %s triggered' % self.ring_timeout)
            self.hangup_call()
            return
        if not self.connected and self.answer_at and self.answer_at < time.time():
            log(self.account.config.index, 'Call will be answered now.')
            self.answer_at = None
            call_prm = pj.CallOpParam()
            call_prm.statusCode = 200
            self.answer(call_prm)
            return
        if not self.connected and self.call_settled_at and self.call_settled_at < time.time():
            self.call_settled_at = None
            self.handle_connected_state()
            return
        if not self.connected:
            return
        if time.time() - self.last_seen > self.menu['timeout']:
            log(self.account.config.index, 'Timeout of %s triggered' % self.menu['timeout'])
            self.handle_menu(self.menu['timeout_choice'])
            self.trigger_webhook({
                'event': 'timeout',
                'caller': self.call_info['remote_uri'] if self.call_info else 'unknown',
                'parsed_caller': self.call_info['parsed_caller'] if self.call_info else None,
                'sip_account': self.account.config.index,
                'menu_id': self.menu['id'],
                'call_id': self.call_info['call_id'] if self.call_info else None,
                'internal_id': self.callback_id,
            })
            return
        if self.playback_is_done and self.scheduled_post_action:
            post_action = self.scheduled_post_action
            self.scheduled_post_action = None
            self.handle_post_action(post_action)
            return
        if len(self.pressed_digit_list) > 0:
            next_digit = self.pressed_digit_list.pop(0)
            self.handle_dtmf_digit(next_digit)
            return

    def handle_post_action(self, post_action: PostAction):
        log(self.account.config.index, 'Scheduled post action: %s' % post_action["action"])
        if post_action["action"] == 'noop':
            pass
        elif post_action["action"] == 'return':
            m = self.menu
            for _ in range(0, post_action['level']):
                if m:
                    m = m['parent_menu']
            if m:
                self.handle_menu(m)
            else:
                log(self.account.config.index, 'Could not return %s level in current menu' % post_action["level"])
        elif post_action["action"] == 'jump':
            new_menu = self.menu_map.get(post_action['menu_id'])
            if new_menu:
                self.handle_menu(new_menu)
            else:
                log(self.account.config.index, 'Could not find menu_id: "%s". Valid IDs are %s' % (post_action["menu_id"], self.menu_map.keys()))
        elif post_action["action"] == 'hangup':
            self.hangup_call()
        elif post_action["action"] == 'repeat_message':
            self.handle_menu(self.menu, send_webhook_event=False, handle_action=False, reset_input=False)

    def trigger_webhook(self, event: ha.WebhookEvent):
        event_id = event.get('event')
        additional_webhook = self.webhooks.get(event_id)
        if additional_webhook:
            log(self.account.config.index, 'Calling additional webhook %s for event %s' % (additional_webhook, event_id))
            self.event_sender.send_event(event, additional_webhook)
        self.event_sender.send_event(event)

    def handle_connected_state(self):
        log(self.account.config.index, 'Call is established.')
        self.connected = True
        self.reset_timeout()
        self.trigger_webhook({
            'event': 'call_established',
            'caller': self.call_info['remote_uri'] if self.call_info else 'unknown',
            'parsed_caller': self.call_info['parsed_caller'] if self.call_info else None,
            'sip_account': self.account.config.index,
            'call_id': self.call_info['call_id'] if self.call_info else None,
            'internal_id': self.callback_id,
        })
        self.handle_menu(self.menu)

    def onCallState(self, prm) -> None:
        if not self.call_info:
            self.call_info = self.get_call_info()
        ci = self.getInfo()
        if ci.state == pj.PJSIP_INV_STATE_EARLY:
            log(self.account.config.index, 'Early')
        elif ci.state == pj.PJSIP_INV_STATE_CALLING:
            log(self.account.config.index, 'Calling')
        elif ci.state == pj.PJSIP_INV_STATE_CONNECTING:
            log(self.account.config.index, 'Call connecting...')
        elif ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            log(self.account.config.index, 'Call connected')
            self.call_settled_at = time.time() + self.settle_time
        elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            log(self.account.config.index, 'Call disconnected')
            self.stop_recording()
            self.trigger_webhook({
                'event': 'call_disconnected',
                'caller': self.call_info['remote_uri'],
                'parsed_caller': self.call_info['parsed_caller'],
                'sip_account': self.account.config.index,
                'call_id': self.call_info['call_id'],
                'internal_id': self.callback_id,
            })
            self.connected = False
            self.current_input = ''
            self.player = None
            self.audio_media = None
            self.tone_gen = None
            self.command_handler.forget_call(self.callback_id)
        else:
            log(self.account.config.index, 'Unknown state: %s' % ci.state)

    def onCallMediaState(self, prm) -> None:
        call_info = self.getInfo()
        log(self.account.config.index, 'onCallMediaState call info state %s' % call_info.state)
        for media_index, media in enumerate(call_info.media):
            if media.type == pj.PJMEDIA_TYPE_AUDIO and (media.status == pj.PJSUA_CALL_MEDIA_ACTIVE or media.status == pj.PJSUA_CALL_MEDIA_REMOTE_HOLD):
                log(self.account.config.index, 'Connected media %s' % media.status)
                self.audio_media = self.getAudioMedia(media_index)
                if self.requested_recording_filename and not self.recorder:
                    self.start_recording(self.requested_recording_filename)

    def onDtmfDigit(self, prm: pj.OnDtmfDigitParam) -> None:
        if not self.playback_is_done and self.wait_for_audio_to_finish:
            self.reset_timeout()
            return
        self.stop_playback()
        self.reset_timeout()
        self.pressed_digit_list.append(prm.digit)

    def handle_dtmf_digit(self, pressed_digit: str) -> None:
        log(self.account.config.index, 'onDtmfDigit: digit %s' % pressed_digit)
        self.trigger_webhook({
            'event': 'dtmf_digit',
            'caller': self.call_info['remote_uri'] if self.call_info else 'unknown',
            'parsed_caller': self.call_info['parsed_caller'] if self.call_info else None,
            'digit': pressed_digit,
            'sip_account': self.account.config.index,
            'call_id': self.call_info['call_id'] if self.call_info else None,
            'internal_id': self.callback_id,
        })
        if not self.menu:
            return
        self.current_input += pressed_digit
        log(self.account.config.index, 'Current input: %s' % self.current_input)
        choices = self.menu.get('choices')
        if choices is not None:
            if self.current_input in choices:
                self.handle_menu(choices[self.current_input])
                return
            if self.menu.get('choices_are_pin'):
                # in PIN mode the error message will play if the input has same length than the longest PIN
                max_choice_length = max(map(lambda choice: len(choice), choices))
                if len(self.current_input) == max_choice_length:
                    log(self.account.config.index, 'No PIN matched %s' % self.current_input)
                    self.handle_menu(self.menu['default_choice'])
            else:
                # in normal mode the error will play as soon as the input does not match any choice
                still_valid = any(map(lambda choice: choice.startswith(self.current_input), choices))
                if not still_valid:
                    log(self.account.config.index, 'Invalid input %s' % self.current_input)
                    self.handle_menu(self.menu['default_choice'])

    def onCallTransferRequest(self, prm):
        log(self.account.config.index, 'onCallTransferRequest')

    def onCallTransferStatus(self, prm):
        log(self.account.config.index, 'onCallTransferStatus. Status code: %s (%s)' % (prm.statusCode, prm.reason))

    def onCallReplaceRequest(self, prm):
        log(self.account.config.index, 'onCallReplaceRequest')

    def onCallReplaced(self, prm):
        log(self.account.config.index, 'onCallReplaced')

    def onCallRxOffer(self, prm):
        log(self.account.config.index, 'onCallRxOffer')

    def onCallRxReinvite(self, prm):
        log(self.account.config.index, 'onCallRxReinvite')

    def onCallTxOffer(self, prm):
        log(self.account.config.index, 'onCallTxOffer')

    def onCallRedirected(self, prm):
        log(self.account.config.index, 'onCallRedirected')

    def handle_menu(self, menu: Optional[Menu], send_webhook_event=True, handle_action=True, reset_input=True) -> None:
        self.reset_timeout()
        if not menu:
            log(self.account.config.index, 'No menu supplied')
            return
        self.menu = menu
        menu_id = menu['id']
        if menu_id and send_webhook_event:
            self.trigger_webhook({
                'event': 'entered_menu',
                'caller': self.call_info['remote_uri'] if self.call_info else 'unknown',
                'parsed_caller': self.call_info['parsed_caller'] if self.call_info else None,
                'menu_id': menu_id,
                'sip_account': self.account.config.index,
                'call_id': self.call_info['call_id'] if self.call_info else None,
                'internal_id': self.callback_id,
            })
        if reset_input:
            self.current_input = ''
        message = menu['message']
        handle_as_template = menu['handle_as_template']
        audio_file = menu['audio_file']
        language = menu['language']
        action = menu['action']
        post_action = menu['post_action']
        should_cache = menu['cache_audio']
        wait_for_audio_to_finish = menu['wait_for_audio_to_finish']
        if message:
            if handle_as_template:
                message = ha.render_template(self.ha_config, message)
            self.play_message(message, language, should_cache, wait_for_audio_to_finish)
        if audio_file:
            self.play_audio_file(audio_file, should_cache, wait_for_audio_to_finish)
        if handle_action:
            self.handle_action(action)
        self.scheduled_post_action = post_action

    def handle_action(self, action: Optional[Command]) -> None:
        if not action:
            log(self.account.config.index, 'No action supplied')
            return
        self.command_handler.handle_command(action, self)

    def play_message(self, message: str, language: str, should_cache: bool, wait_for_audio_to_finish: bool) -> None:
        log(self.account.config.index, 'Playing message: %s' % message)
        cached_file = audio_cache.get_cached_file(should_cache, self.ha_config.cache_dir, 'message', message)
        if cached_file:
            self.set_current_playback({'type': 'message', 'message': message})
            self.play_wav_file(cached_file, False, wait_for_audio_to_finish)
            return
        sound_file_name, must_be_deleted, was_successful = ha.create_and_get_tts(self.ha_config, message, language)
        self.set_current_playback({'type': 'message', 'message': message})
        audio_cache.cache_file(should_cache and was_successful, self.ha_config.cache_dir, 'message', message, sound_file_name)
        self.play_wav_file(sound_file_name, must_be_deleted, wait_for_audio_to_finish)

    def play_audio_file(self, audio_file: str, should_cache: bool, wait_for_audio_to_finish: bool) -> None:
        log(self.account.config.index, 'Playing audio file: %s' % audio_file)
        cached_file = audio_cache.get_cached_file(should_cache, self.ha_config.cache_dir, 'audio_file', audio_file)
        if cached_file:
            self.set_current_playback({'type': 'audio_file', 'audio_file': audio_file})
            self.play_wav_file(cached_file, False, wait_for_audio_to_finish)
            return
        file_format = audio.audio_format_from_filename(audio_file)
        if not file_format:
            log(None, 'Error getting audio format from filename: %s' % audio_file)
            return
        with open(audio_file, 'rb') as f:
            audio_file_content = f.read()
            sound_file_name = audio.convert_audio_stream_to_wav_file(audio_file_content, file_format)
        if not sound_file_name:
            log(None, 'Could not convert to wav: %s' % audio_file)
            return
        self.set_current_playback({'type': 'audio_file', 'audio_file': audio_file})
        audio_cache.cache_file(should_cache, self.ha_config.cache_dir, 'audio_file', audio_file, sound_file_name)
        self.play_wav_file(sound_file_name, True, wait_for_audio_to_finish)

    def play_wav_file(self, sound_file_name: str, must_be_deleted: bool, wait_for_audio_to_finish: bool) -> None:
        if self.audio_media:
            self.playback_is_done = False
            self.wait_for_audio_to_finish = wait_for_audio_to_finish
            self.player = player.Player(self.on_playback_done)
            self.player.play_file(self.audio_media, sound_file_name)
        else:
            log(self.account.config.index, 'Audio media not connected. Cannot play audio stream!')
        if must_be_deleted:
            os.remove(sound_file_name)

    def on_playback_done(self) -> None:
        log(self.account.config.index, 'Playback done.')
        if self.current_playback and self.current_playback['type'] == 'audio_file':
            self.trigger_webhook({
                'event': 'playback_done',
                'sip_account': self.account.config.index,
                'caller': self.call_info['remote_uri'] if self.call_info else 'unknown',
                'parsed_caller': self.call_info['parsed_caller'] if self.call_info else None,
                'type': 'audio_file',
                'audio_file': self.current_playback['audio_file'],
                'call_id': self.call_info['call_id'] if self.call_info else None,
                'internal_id': self.callback_id,
            })
        elif self.current_playback and self.current_playback['type'] == 'message':
            self.trigger_webhook({
                'event': 'playback_done',
                'sip_account': self.account.config.index,
                'caller': self.call_info['remote_uri'] if self.call_info else 'unknown',
                'parsed_caller': self.call_info['parsed_caller'] if self.call_info else None,
                'type': 'message',
                'message': self.current_playback['message'],
                'call_id': self.call_info['call_id'] if self.call_info else None,
                'internal_id': self.callback_id,
            })
        self.current_playback = None
        self.playback_is_done = True
        self.player = None

    def stop_playback(self) -> None:
        if not self.playback_is_done:
            log(self.account.config.index, 'Playback interrupted.')
            if self.player:
                self.player.stopTransmit(self.audio_media)
                self.player = None
            self.playback_is_done = True

    def start_recording(self, record_filename: str) -> None:
        if self.recorder:
            assert self.audio_media is not None
            assert self.call_info is not None
            log(self.account.config.index, 'Recording already running -> reattaching')
            try:
                self.audio_media.stopTransmit(self.recorder)
            except Exception:
                pass
            try:
                self.audio_media.startTransmit(self.recorder)
            except Exception as e:
                log(self.account.config.index, f'Error: Could not reattach recorder: {e}')
            return
        if not self.audio_media:
            log(self.account.config.index, 'Audio media not connected yet. Recording will start once media is available')
            self.requested_recording_filename = record_filename
            return
        self.requested_recording_filename = None
        target_file = record_filename
        target_dir = os.path.dirname(target_file)
        if not os.path.isdir(target_dir):
            log(self.account.config.index, 'Error: Call recordings directory not found: %s' % target_dir)
            return
        self.recorder = pj.AudioMediaRecorder()
        try:
            self.recorder.createRecorder(target_file)
            self.audio_media.startTransmit(self.recorder)
        except Exception as e:
            log(self.account.config.index, 'Error: Failed to start call recording: %s' % e)
            self.stop_recording()
            return
        self.recording_file = target_file
        log(self.account.config.index, 'Call recording started: %s' % target_file)
        assert self.call_info is not None
        self.trigger_webhook({
            'event': 'recording_started',
            'caller': self.call_info['remote_uri'],
            'parsed_caller': self.call_info['parsed_caller'],
            'sip_account': self.account.config.index,
            'call_id': self.call_info['call_id'],
            'recording_file': self.recording_file,
            'internal_id': self.callback_id,
        })

    def stop_recording(self) -> None:
        self.requested_recording_filename = None
        if not self.recorder:
            return
        try:
            if self.audio_media:
                self.audio_media.stopTransmit(self.recorder)
        except Exception as e:
            log(self.account.config.index, 'Error: Failed to stop call recording: %s' % e)
        if self.recording_file:
            log(self.account.config.index, 'Call recording stopped: %s' % self.recording_file)
            assert self.call_info is not None
            self.trigger_webhook({
                'event': 'recording_stopped',
                'caller': self.call_info['remote_uri'],
                'parsed_caller': self.call_info['parsed_caller'],
                'sip_account': self.account.config.index,
                'call_id': self.call_info['call_id'],
                'recording_file': self.recording_file,
                'internal_id': self.callback_id,
            })
        self.recorder = None
        self.recording_file = None

    def accept(self, answer_mode: CallHandling, answer_after: float) -> None:
        call_prm = pj.CallOpParam()
        call_prm.statusCode = 180
        self.answer(call_prm)
        if answer_mode == CallHandling.ACCEPT:
            self.answer_at = time.time() + answer_after

    def hangup_call(self) -> None:
        log(self.account.config.index, 'Hang-up.')
        call_prm = pj.CallOpParam(True)
        self.hangup(call_prm)

    def answer_call(self, new_menu: Optional[MenuFromStdin], overwrite_webhooks: Optional[WebhookToCall]) -> None:
        log(self.account.config.index, 'Trigger answer of call (if not established already)')
        if new_menu:
            self.menu = self.normalize_menu(new_menu)
            self.menu_map = self.create_menu_map(self.menu)
            self.pretty_print_menu(self.menu)
        if overwrite_webhooks:
            self.webhooks = overwrite_webhooks
        self.answer_at = time.time()

    def transfer(self, transfer_to):
        log(self.account.config.index, 'Transfer call to %s' % transfer_to)
        xfer_param = pj.CallOpParam(True)
        self.xfer(transfer_to, xfer_param)

    def bridge_audio(self, call_two: Call):
        if self.audio_media and call_two.audio_media:
            log(self.account.config.index, 'Connect audio stream of "%s" and "%s"' % (self.callback_id, call_two.callback_id))
            self.audio_media.startTransmit(call_two.audio_media)
            call_two.audio_media.startTransmit(self.audio_media)
            log(self.account.config.index, 'Audio streams connected.')
        else:
            log(self.account.config.index, 'At least one audio media is not connected. Cannot bridge audio between calls!')

    def send_dtmf(self, digits: str, method: DtmfMethod = 'in_band') -> None:
        self.reset_timeout()
        log(self.account.config.index, 'Sending DTMF %s' % digits)
        if method == 'in_band':
            if not self.audio_media:
                log(self.account.config.index, 'Audio media not connected. Cannot send DTMF in-band!')
                return
            if not self.tone_gen:
                self.tone_gen = pj.ToneGenerator()
                self.tone_gen.createToneGenerator()
                self.tone_gen.startTransmit(self.audio_media)
            tone_digits_vector = create_tone_digit_vector(digits)
            self.tone_gen.playDigits(tone_digits_vector)
        elif method == 'rfc2833':
            dtmf_prm = pj.CallSendDtmfParam()
            dtmf_prm.method = pj.PJSUA_DTMF_METHOD_RFC2833
            dtmf_prm.duration = DEFAULT_DTMF_ON
            dtmf_prm.digits = digits
            self.sendDtmf(dtmf_prm)
        elif method == 'sip_info':
            dtmf_prm = pj.CallSendDtmfParam()
            dtmf_prm.method = pj.PJSUA_DTMF_METHOD_SIP_INFO
            dtmf_prm.duration = DEFAULT_DTMF_ON
            dtmf_prm.digits = digits
            self.sendDtmf(dtmf_prm)

    def get_callback_ids(self) -> tuple[str, List[str]]:
        if self.uri_to_call:
            # On outgoing calls we use the uri_to_call, as other info is not available yet
            parsed_caller = self.parse_caller(self.uri_to_call)
            return self.uri_to_call, [x for x in [parsed_caller] if x is not None]
        call_info = self.get_call_info()
        return call_info['remote_uri'], [x for x in [call_info['parsed_caller']] if x is not None]

    def get_call_info(self) -> CallInfo:
        ci = self.getInfo()
        parsed_caller = self.parse_caller(ci.remoteUri)
        return {
            'remote_uri': ci.remoteUri,
            'local_uri': ci.localUri,
            'parsed_caller': parsed_caller,
            'call_id': ci.callIdString,
        }

    def reset_timeout(self):
        self.last_seen = time.time()

    def set_current_playback(self, current_playback: ha.CurrentPlayback):
        self.current_playback = current_playback

    def normalize_menu(self, menu: MenuFromStdin, parent_menu: Optional[Menu] = None, is_default_or_timeout_choice=False) -> Menu:
        def parse_post_action(action: Optional[str]) -> PostAction:
            if (not action) or (action == 'noop'):
                return PostActionNoop(action='noop')
            elif action == 'hangup':
                return PostActionHangup(action='hangup')
            elif action == 'repeat_message':
                return PostActionRepeatMessage(action='repeat_message')
            elif action.startswith('return'):
                _, *params = action.split()
                level_str = utils.safe_list_get(params, 0, 1)
                level = utils.convert_to_int(level_str, 1)
                return PostActionReturn(action='return', level=level)
            elif action.startswith('jump'):
                _, *params = action.split(None)
                jump_to = utils.safe_list_get(params, 0, '')
                if not jump_to:
                    log(self.account.config.index, 'Error: jump action requires a menu id as parameter')
                return PostActionJump(action='jump', menu_id=jump_to.strip())
            else:
                log(self.account.config.index, 'Unknown post_action: %s' % action)
                return PostActionNoop(action='noop')

        def normalize_choice(item: tuple[Any, MenuFromStdin], parent_menu_for_choice: Menu) -> tuple[str, Menu]:
            choice, sub_menu = item
            normalized_choice = str(choice).lower()
            normalized_sub_menu = self.normalize_menu(sub_menu, parent_menu_for_choice, normalized_choice in ['default', 'timeout'])
            return normalized_choice, normalized_sub_menu

        def get_default_or_timeout_choice(choice: Union[Literal['default'], Literal['timeout']], parent_menu_for_choice: Menu) -> Optional[Menu]:
            if is_default_or_timeout_choice:
                return None
            elif choice in normalized_choices:
                return normalized_choices.pop(choice)
            else:
                if choice == 'default':
                    return Call.get_default_menu(parent_menu_for_choice)
                else:
                    return Call.get_timeout_menu(parent_menu_for_choice)

        menu_id = menu.get('id')
        normalized_menu: Menu = {
            'id': menu_id.strip() if menu_id else None,
            'message': menu.get('message'),
            'handle_as_template': menu.get('handle_as_template') or False,
            'audio_file': menu.get('audio_file'),
            'language': menu.get('language') or self.ha_config.tts_config['language'],
            'action': menu.get('action'),
            'choices_are_pin': menu.get('choices_are_pin') or False,
            'choices': None,
            'default_choice': None,
            'timeout_choice': None,
            'timeout': utils.convert_to_float(menu.get('timeout'), DEFAULT_RING_TIMEOUT),
            'post_action': parse_post_action(menu.get('post_action')),
            'parent_menu': parent_menu,
            'cache_audio': menu.get('cache_audio') or False,
            'wait_for_audio_to_finish': menu.get('wait_for_audio_to_finish') or False,
        }
        choices = menu.get('choices')
        normalized_choices = dict(map(lambda c: normalize_choice(c, normalized_menu), choices.items())) if choices else dict()
        default_choice = get_default_or_timeout_choice('default', normalized_menu)
        timeout_choice = get_default_or_timeout_choice('timeout', normalized_menu)
        normalized_menu['choices'] = normalized_choices
        normalized_menu['default_choice'] = default_choice
        normalized_menu['timeout_choice'] = timeout_choice
        return normalized_menu

    @staticmethod
    def create_menu_map(menu: Menu) -> dict[str, Menu]:
        def add_to_map(menu_map: dict[str, Menu], m: Menu) -> dict[str, Menu]:
            if m['id']:
                menu_map[m['id']] = m
            if m['choices']:
                for m in m['choices'].values():
                    add_to_map(menu_map, m)
            return menu_map
        return add_to_map({}, menu)

    @staticmethod
    def parse_caller(remote_uri: str) -> Optional[str]:
        parsed_caller_match = re.search('<sip:(.+?)[@;>]', remote_uri)
        if parsed_caller_match:
            return parsed_caller_match.group(1)
        parsed_caller_match_2nd_try = re.search('sip:(.+?)($|[@;])', remote_uri)
        if parsed_caller_match_2nd_try:
            return parsed_caller_match_2nd_try.group(1)
        return None

    @staticmethod
    def get_default_menu(parent_menu: Menu) -> Menu:
        return {
            'id': None,
            'message': 'Unknown option',
            'handle_as_template': False,
            'audio_file': None,
            'language': 'en',
            'action': None,
            'choices_are_pin': False,
            'choices': None,
            'default_choice': None,
            'timeout_choice': None,
            'post_action': PostActionReturn(action="return", level=1),
            'timeout': DEFAULT_RING_TIMEOUT,
            'parent_menu': parent_menu,
            'cache_audio': False,
            'wait_for_audio_to_finish': False
        }

    @staticmethod
    def get_timeout_menu(parent_menu: Menu) -> Menu:
        return {
            'id': None,
            'message': None,
            'handle_as_template': False,
            'audio_file': None,
            'language': 'en',
            'action': None,
            'choices_are_pin': False,
            'choices': None,
            'default_choice': None,
            'timeout_choice': None,
            'post_action': PostActionHangup(action="hangup"),
            'timeout': DEFAULT_RING_TIMEOUT,
            'parent_menu': parent_menu,
            'cache_audio': False,
            'wait_for_audio_to_finish': False
        }

    @staticmethod
    def get_standard_menu() -> Menu:
        standard_menu: Menu = {
            'id': None,
            'message': None,
            'handle_as_template': False,
            'audio_file': None,
            'language': 'en',
            'action': None,
            'choices_are_pin': False,
            'choices': dict(),
            'default_choice': None,
            'timeout_choice': None,
            'post_action': PostActionNoop(action="noop"),
            'timeout': DEFAULT_RING_TIMEOUT,
            'parent_menu': None,
            'cache_audio': False,
            'wait_for_audio_to_finish': False
        }
        standard_menu['default_choice'] = Call.get_default_menu(standard_menu)
        standard_menu['timeout_choice'] = Call.get_timeout_menu(standard_menu)
        return standard_menu

    @staticmethod
    def pretty_print_menu(menu: Menu) -> None:
        lines = yaml.dump(menu, sort_keys=False).split('\n')
        lines_with_pipe = map(lambda line: '| ' + line, lines)
        print('\n'.join(lines_with_pipe))


def make_call(
    ep: pj.Endpoint,
    acc: account.Account,
    uri_to_call: str,
    menu: Optional[MenuFromStdin],
    command_handler: CommandHandler,
    event_sender: EventSender,
    ha_config: ha.HaConfig,
    ring_timeout: float,
    webhooks: Optional[WebhookToCall],
) -> Call:
    new_call = Call(ep, acc, pj.PJSUA_INVALID_ID, uri_to_call, menu, command_handler, event_sender, ha_config, ring_timeout, webhooks)
    call_param = pj.CallOpParam(True)
    new_call.makeCall(uri_to_call, call_param)
    return new_call


def create_tone_digit(digit: str) -> pj.ToneDigit:
    td = pj.ToneDigit()
    td.digit = digit
    td.volume = 0
    td.on_msec = DEFAULT_DTMF_ON
    td.off_msec = DEFAULT_DTMF_OFF
    return td


def create_tone_digit_vector(digits: str) -> pj.ToneDigitVector:
    tone_digits_vector = pj.ToneDigitVector()
    for d in digits:
        tone_digits_vector.append(create_tone_digit(d))
    return tone_digits_vector

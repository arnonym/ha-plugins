from __future__ import annotations

import os
import re
import time
from enum import Enum
from typing import Dict, Optional, Callable, Union, List
from typing_extensions import Literal

import pjsua2 as pj

import account
import audio
import audio_cache
import ha
import player
import webhook
from call_state_change import CallStateChange
from command_client import Command
from command_handler import CommandHandler
from constants import DEFAULT_RING_TIMEOUT, DEFAULT_DTMF_ON
from event_sender import EventSender
from log import log
from menu import MenuFromStdin, Menu, normalize_menu, pretty_print_menu
from sip_status import REASON_PHRASES
from tone_digit import create_tone_digit_vector
from post_action import PostAction

CallCallback = Callable[[CallStateChange, str, 'Call'], None]
DtmfMethod = Union[Literal['in_band'], Literal['rfc2833'], Literal['sip_info']]


class CallHandling(Enum):
    LISTEN = 'LISTEN'
    ACCEPT = 'ACCEPT'
    REJECT = 'REJECT'

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
        webhooks: Optional[webhook.WebhookToCall],
        sip_headers: Optional[Dict[str, Optional[str]]] = None,
    ):
        pj.Call.__init__(self, sip_account, call_id)
        self.player: Optional[player.Player] = None
        self.audio_media: Optional[pj.AudioMedia] = None
        self.recorder: Optional[pj.AudioMediaRecorder] = None
        self.tone_gen: Optional[pj.ToneGenerator] = None

        self.end_point = end_point
        self.account = sip_account
        self.uri_to_call = uri_to_call
        self.direction: Literal['incoming', 'outgoing'] = 'outgoing' if uri_to_call else 'incoming'
        self.command_handler = command_handler
        self.event_sender = event_sender
        self.ha_config = ha_config
        self.ring_timeout = ring_timeout
        self.webhooks: Optional[webhook.WebhookToCall] = webhooks
        self.sip_headers: Dict[str, Optional[str]] = sip_headers if sip_headers is not None else {}

        self.recording_file: Optional[str] = None
        self.requested_recording_filename: Optional[str] = None
        self.connected = False
        self.current_input = ''
        self.scheduled_post_action: Optional[PostAction] = None
        self.playback_is_done = True
        self.wait_for_audio_to_finish = False
        self.last_seen = time.time()
        self.call_settled_at: Optional[float] = None
        self.answer_at: Optional[float] = None
        self.call_info: Optional[webhook.CallInfo] = None
        self.pressed_digit_list: List[str] = []
        self.current_playback: Optional[ha.CurrentPlayback] = None

        self.callback_id, other_ids = self.get_callback_ids()
        self.menu, self.menu_map = normalize_menu(menu, self.ha_config.tts_config['language'], self.account.config.index)
        pretty_print_menu(self.menu)
        log(self.account.config.index, f'Registering call with id {self.callback_id}')
        self.command_handler.register_call(self.callback_id, self, other_ids)

    def handle_events(self) -> None:
        if not self.connected and time.time() - self.last_seen > self.ring_timeout:
            self.trigger_webhook({'event': 'ring_timeout'})
            log(self.account.config.index, f'Ring timeout of {self.ring_timeout} triggered')
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
        timeout = self.menu and self.menu['timeout'] or DEFAULT_RING_TIMEOUT
        if time.time() - self.last_seen > timeout:
            log(self.account.config.index, f"Timeout of {timeout} triggered")
            if self.menu:
                self.handle_menu(self.menu['timeout_choice'])
                self.trigger_webhook({'event': 'timeout', 'menu_id': self.menu['id']})
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
        log(self.account.config.index, f'Scheduled post action: {post_action["action"]}')
        match post_action["action"]:
            case 'noop':
                pass
            case 'return':
                if not self.menu:
                    log(self.account.config.index, 'No menu to return to')
                    return
                m = self.menu
                for _ in range(0, post_action['level']):
                    if m:
                        m = m['parent_menu']
                if m:
                    self.handle_menu(m)
                else:
                    log(self.account.config.index, f'Could not return {post_action["level"]} level in current menu')
            case 'jump':
                new_menu = self.menu_map.get(post_action['menu_id'])
                if new_menu:
                    self.handle_menu(new_menu)
                else:
                    log(self.account.config.index, f'Could not find menu_id: "{post_action["menu_id"]}". Valid IDs are {self.menu_map.keys()}')
            case 'hangup':
                self.hangup_call()
            case 'repeat_message':
                self.handle_menu(self.menu, send_webhook_event=False, handle_action=False, reset_input=False)

    def trigger_webhook(self, event: ha.WebhookEvent):
        webhook.trigger_webhook(
            event,
            self.call_info,
            self.account.config.index,
            self.callback_id,
            self.event_sender,
            self.webhooks,
        )

    def handle_connected_state(self):
        log(self.account.config.index, 'Call is established.')
        self.connected = True
        self.reset_timeout()
        self.trigger_webhook({'event': 'call_established'})
        self.handle_menu(self.menu)

    def onCallState(self, prm) -> None:
        if not self.call_info:
            self.call_info = self.get_call_info()
        ci = self.getInfo()
        match ci.state:
            case pj.PJSIP_INV_STATE_EARLY:
                log(self.account.config.index, 'Early')
            case pj.PJSIP_INV_STATE_CALLING:
                log(self.account.config.index, 'Calling')
            case pj.PJSIP_INV_STATE_CONNECTING:
                log(self.account.config.index, 'Call connecting...')
            case pj.PJSIP_INV_STATE_CONFIRMED:
                log(self.account.config.index, 'Call connected')
                self.extract_headers_from_response(prm)
                self.call_settled_at = time.time() + self.account.config.settle_time
            case pj.PJSIP_INV_STATE_DISCONNECTED:
                log(self.account.config.index, 'Call disconnected')
                self.stop_recording()
                self.trigger_webhook({'event': 'call_disconnected'})
                self.connected = False
                self.current_input = ''
                self.player = None
                self.audio_media = None
                self.tone_gen = None
                self.command_handler.forget_call(self.callback_id)
            case _:
                log(self.account.config.index, f'Unknown state: {ci.state}')

    def onCallMediaState(self, prm) -> None:
        call_info = self.getInfo()
        log(self.account.config.index, f'onCallMediaState call info state {call_info.state}')
        for media_index, media in enumerate(call_info.media):
            if media.type == pj.PJMEDIA_TYPE_AUDIO and (media.status == pj.PJSUA_CALL_MEDIA_ACTIVE or media.status == pj.PJSUA_CALL_MEDIA_REMOTE_HOLD):
                log(self.account.config.index, f'Connected media {media.status}')
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
        log(self.account.config.index, f'onDtmfDigit: digit {pressed_digit}')
        self.trigger_webhook({'event': 'dtmf_digit', 'digit': pressed_digit})
        if not self.menu:
            return
        self.current_input += pressed_digit
        log(self.account.config.index, f'Current input: {self.current_input}')
        choices = self.menu.get('choices')
        if choices is not None:
            if self.current_input in choices:
                self.handle_menu(choices[self.current_input])
                return
            if self.menu.get('choices_are_pin'):
                # in PIN mode the error message will play if the input has same length than the longest PIN
                max_choice_length = max(map(lambda choice: len(choice), choices))
                if len(self.current_input) == max_choice_length:
                    log(self.account.config.index, f'No PIN matched {self.current_input}')
                    self.handle_menu(self.menu['default_choice'])
            else:
                # in normal mode the error will play as soon as the input does not match any choice
                still_valid = any(map(lambda choice: choice.startswith(self.current_input), choices))
                if not still_valid:
                    log(self.account.config.index, f'Invalid input {self.current_input}')
                    self.handle_menu(self.menu['default_choice'])

    def onCallTransferRequest(self, prm):
        log(self.account.config.index, 'onCallTransferRequest')

    def onCallTransferStatus(self, prm):
        log(self.account.config.index, f'onCallTransferStatus. Status code: {prm.statusCode} ({prm.reason})')

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
            self.trigger_webhook({'event': 'entered_menu', 'menu_id': menu_id})
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
        log(self.account.config.index, f'Playing message: {message}')
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
        log(self.account.config.index, f'Playing audio file: {audio_file}')
        cached_file = audio_cache.get_cached_file(should_cache, self.ha_config.cache_dir, 'audio_file', audio_file)
        if cached_file:
            self.set_current_playback({'type': 'audio_file', 'audio_file': audio_file})
            self.play_wav_file(cached_file, False, wait_for_audio_to_finish)
            return
        file_format = audio.audio_format_from_filename(audio_file)
        if not file_format:
            log(None, f'Error getting audio format from filename: {audio_file}')
            return
        with open(audio_file, 'rb') as f:
            audio_file_content = f.read()
            sound_file_name = audio.convert_audio_stream_to_wav_file(audio_file_content, file_format)
        if not sound_file_name:
            log(None, f'Could not convert to wav: {audio_file}')
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
            self.trigger_webhook({'event': 'playback_done', 'type': 'audio_file', 'audio_file': self.current_playback['audio_file']})
        elif self.current_playback and self.current_playback['type'] == 'message':
            self.trigger_webhook({'event': 'playback_done', 'type': 'message', 'message': self.current_playback['message']})
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
            log(self.account.config.index, f'Error: Call recordings directory not found: {target_dir}')
            return
        self.recorder = pj.AudioMediaRecorder()
        try:
            self.recorder.createRecorder(target_file)
            self.audio_media.startTransmit(self.recorder)
        except Exception as e:
            log(self.account.config.index, f'Error: Failed to start call recording: {e}')
            self.stop_recording()
            return
        self.recording_file = target_file
        log(self.account.config.index, f'Call recording started: {target_file}')
        assert self.call_info is not None
        self.trigger_webhook({'event': 'recording_started', 'recording_file': self.recording_file})

    def stop_recording(self) -> None:
        self.requested_recording_filename = None
        if not self.recorder:
            return
        try:
            if self.audio_media:
                self.audio_media.stopTransmit(self.recorder)
        except Exception as e:
            log(self.account.config.index, f'Error: Failed to stop call recording: {e}')
        if self.recording_file:
            log(self.account.config.index, f'Call recording stopped: {self.recording_file}')
            assert self.call_info is not None
            self.trigger_webhook({'event': 'recording_stopped', 'recording_file': self.recording_file})
        self.recorder = None
        self.recording_file = None

    def accept(self, answer_mode: CallHandling, answer_after: float) -> None:
        if answer_mode == CallHandling.REJECT:
            sip_code = self.account.config.options.reject_sip_code
            log(self.account.config.index, f'Rejecting call with SIP code {sip_code}.')
            call_prm = pj.CallOpParam()
            call_prm.statusCode = sip_code
            call_prm.reason = REASON_PHRASES.get(sip_code, "")
            self.answer(call_prm)
            return
        call_prm = pj.CallOpParam()
        call_prm.statusCode = 180
        self.answer(call_prm)
        if answer_mode == CallHandling.ACCEPT:
            self.answer_at = time.time() + answer_after

    def hangup_call(self, sip_code: int = 0) -> None:
        log(self.account.config.index, 'Hang-up.')
        call_prm = pj.CallOpParam(True)
        if sip_code and not self.connected:
            call_prm.statusCode = sip_code
            call_prm.reason = REASON_PHRASES.get(sip_code, "")
        self.hangup(call_prm)

    def answer_call(self, new_menu: Optional[MenuFromStdin], overwrite_webhooks: Optional[webhook.WebhookToCall]) -> None:
        log(self.account.config.index, 'Trigger answer of call (if not established already)')
        if new_menu:
            self.menu, self.menu_map = normalize_menu(new_menu, self.ha_config.tts_config['language'], self.account.config.index)
            pretty_print_menu(self.menu)
        if overwrite_webhooks:
            self.webhooks = overwrite_webhooks
        if self.connected:
            if new_menu:
                self.handle_menu(self.menu)
        else:
            self.answer_at = time.time()

    def transfer(self, transfer_to):
        log(self.account.config.index, f'Transfer call to {transfer_to}')
        xfer_param = pj.CallOpParam(True)
        self.xfer(transfer_to, xfer_param)

    def bridge_audio(self, call_two: Call):
        if self.audio_media and call_two.audio_media:
            log(self.account.config.index, f'Connect audio stream of "{self.callback_id}" and "{call_two.callback_id}"')
            self.audio_media.startTransmit(call_two.audio_media)
            call_two.audio_media.startTransmit(self.audio_media)
            log(self.account.config.index, 'Audio streams connected.')
        else:
            log(self.account.config.index, 'At least one audio media is not connected. Cannot bridge audio between calls!')

    def send_dtmf(self, digits: str, method: DtmfMethod = 'in_band') -> None:
        self.reset_timeout()
        log(self.account.config.index, f'Sending DTMF {digits}')
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
            parsed_uri = self.parse_sip_uri(self.uri_to_call)
            return self.uri_to_call, [x for x in [parsed_uri] if x is not None]
        call_info = self.get_call_info()
        return call_info['remote_uri'], [x for x in [call_info['parsed_remote_uri'], call_info['call_id']] if x is not None]

    def get_call_info(self) -> webhook.CallInfo:
        ci = self.getInfo()
        parsed_remote_uri = self.parse_sip_uri(ci.remoteUri)
        parsed_local_uri = self.parse_sip_uri(ci.localUri)
        return {
            'remote_uri': ci.remoteUri,
            'local_uri': ci.localUri,
            'parsed_remote_uri': parsed_remote_uri,
            'parsed_local_uri': parsed_local_uri,
            'call_id': ci.callIdString,
            'headers': self.sip_headers,
            'direction': self.direction,
        }

    def extract_headers_from_response(self, prm) -> None:
        extract_headers = self.account.config.options.extract_headers
        debug_headers = self.account.config.global_options.debug_headers
        if not extract_headers and not debug_headers:
            return
        if self.sip_headers:
            return
        try:
            whole_msg = prm.e.body.tsx_state.src.rdata.wholeMsg
            if debug_headers:
                account.Account.log_all_sip_headers(self.account.config.index, whole_msg)
            if extract_headers:
                self.sip_headers = account.Account.parse_sip_headers(whole_msg, extract_headers)
                if self.call_info:
                    self.call_info['headers'] = self.sip_headers
        except (AttributeError, TypeError):
            pass

    def reset_timeout(self):
        self.last_seen = time.time()

    def set_current_playback(self, current_playback: ha.CurrentPlayback):
        self.current_playback = current_playback

    @staticmethod
    def parse_sip_uri(sip_uri: str) -> Optional[str]:
        match = re.search('<sip:(.+?)[@;>]', sip_uri)
        if match:
            return match.group(1)
        match_fallback = re.search('sip:(.+?)($|[@;])', sip_uri)
        if match_fallback:
            return match_fallback.group(1)
        return None

def make_call(
    ep: pj.Endpoint,
    acc: account.Account,
    uri_to_call: str,
    menu: Optional[MenuFromStdin],
    command_handler: CommandHandler,
    event_sender: EventSender,
    ha_config: ha.HaConfig,
    ring_timeout: float,
    webhooks: Optional[webhook.WebhookToCall],
) -> Call:
    new_call = Call(ep, acc, pj.PJSUA_INVALID_ID, uri_to_call, menu, command_handler, event_sender, ha_config, ring_timeout, webhooks, {})
    call_param = pj.CallOpParam(True)
    new_call.makeCall(uri_to_call, call_param)
    new_call.trigger_webhook({'event': 'outgoing_call_initiated'})
    return new_call

from __future__ import annotations

import os
import time
import re
from enum import Enum
from typing import Optional, Callable, Union, Any

import pjsua2 as pj
import yaml
from typing_extensions import TypedDict, Literal

import ha
import utils
import account
import audio
import player


class CallStateChange(Enum):
    CALL = 1
    HANGUP = 2


DEFAULT_TIMEOUT = 300.0
DEFAULT_DTMF_ON = 180
DEFAULT_DTMF_OFF = 220

CallCallback = Callable[[CallStateChange, str, 'Call'], None]
PostAction = Union[Literal['return'], Literal['hangup'], Literal['noop']]
DtmfMethod = Union[Literal['in_band'], Literal['rfc2833'], Literal['sip_info']]


class Action(TypedDict):
    domain: str
    service: str
    entity_id: str


class MenuFromStdin(TypedDict):
    id: Optional[str]
    message: Optional[str]
    audio_file: Optional[str]
    language: Optional[str]
    action: Optional[Action]
    choices_are_pin: Optional[bool]
    post_action: Optional[PostAction]
    timeout: Optional[int]
    choices: Optional[dict[Any, MenuFromStdin]]


class Menu(TypedDict):
    id: Optional[str]
    message: Optional[str]
    audio_file: Optional[str]
    language: str
    action: Optional[Action]
    choices_are_pin: bool
    post_action: PostAction
    timeout: float
    choices: Optional[dict[str, Menu]]
    default_choice: Optional[Menu]
    timeout_choice: Optional[Menu]
    parent_menu: Optional[Menu]


class CallInfo(TypedDict):
    local_uri: str
    remote_uri: str
    parsed_caller: Optional[str]


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
    def __init__(self, end_point: pj.Endpoint, sip_account: account.Account, call_id: str, uri_to_call: Optional[str], menu: Optional[MenuFromStdin],
                 callback: CallCallback, ha_config: ha.HaConfig, ring_timeout: float, webhook_to_call: Optional[str]):
        pj.Call.__init__(self, sip_account, call_id)
        self.player: Optional[player.Player] = None
        self.audio_media: Optional[pj.AudioMedia] = None
        self.connected: bool = False
        self.current_input = ''
        self.end_point = end_point
        self.account = sip_account
        self.uri_to_call = uri_to_call
        self.ha_config = ha_config
        self.ring_timeout = ring_timeout
        self.settle_time = sip_account.config.settle_time
        self.webhook_to_call = webhook_to_call
        self.callback = callback
        self.scheduled_post_action: Optional[PostAction] = None
        self.playback_is_done = True
        self.last_seen = time.time()
        self.call_settled_at: Optional[float] = None
        self.answer_at: Optional[float] = None
        self.tone_gen: Optional[pj.ToneGenerator] = None
        self.call_info: Optional[CallInfo] = None
        self.pressed_digit_list = []
        self.callback_id = self.get_callback_id()
        self.menu = self.normalize_menu(menu) if menu else self.get_standard_menu()
        Call.pretty_print_menu(self.menu)
        print('| Registering call with id', self.callback_id)
        self.callback(CallStateChange.CALL, self.callback_id, self)

    def handle_events(self) -> None:
        if not self.connected and time.time() - self.last_seen > self.ring_timeout:
            print('| Ring timeout of', self.ring_timeout, 'triggered.')
            self.hangup_call()
            return
        if not self.connected and self.answer_at and self.answer_at < time.time():
            print('| Call will be answered now.')
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
            print('| Timeout of', self.menu['timeout'], 'triggered.')
            self.handle_menu(self.menu['timeout_choice'])
            return
        if self.playback_is_done and self.scheduled_post_action:
            post_action = self.scheduled_post_action
            self.scheduled_post_action = None
            print('| Scheduled post action:', post_action)
            if post_action == 'noop':
                pass
            elif post_action == 'return':
                self.handle_menu(self.menu['parent_menu'])
            elif post_action == 'hangup':
                self.hangup_call()
            else:
                print('| Unknown post_action:', post_action)
            return
        if len(self.pressed_digit_list) > 0:
            next_digit = self.pressed_digit_list.pop(0)
            self.handle_dtmf_digit(next_digit)
            return

    def handle_connected_state(self):
        print("| Call is established.")
        self.connected = True
        self.last_seen = time.time()
        if self.webhook_to_call:
            ha.trigger_webhook(self.ha_config, {
                'event': 'call_established',
                'caller': self.call_info["remote_uri"] if self.call_info else "unknown",
                'parsed_caller': self.call_info["parsed_caller"] if self.call_info else None,
            }, self.webhook_to_call)
        ha.trigger_webhook(self.ha_config, {
            'event': 'call_established',
            'caller': self.call_info["remote_uri"] if self.call_info else "unknown",
            'parsed_caller': self.call_info["parsed_caller"] if self.call_info else None,
        })
        self.handle_menu(self.menu)

    def onCallState(self, prm) -> None:
        if not self.call_info:
            self.call_info = self.get_call_info()
        ci = self.getInfo()
        if ci.state == pj.PJSIP_INV_STATE_EARLY:
            print('| Early')
        elif ci.state == pj.PJSIP_INV_STATE_CALLING:
            print('| Calling')
        elif ci.state == pj.PJSIP_INV_STATE_CONNECTING:
            print('| Call connecting...')
        elif ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            print('| Call connected')
            self.call_settled_at = time.time() + self.settle_time
        elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            print('| Call disconnected')
            ha.trigger_webhook(self.ha_config, {
                'event': 'call_disconnected',
                'caller': self.call_info["remote_uri"],
                'parsed_caller': self.call_info["parsed_caller"],
            })
            self.connected = False
            self.account.c = None
            self.account.acceptCall = False
            self.account.inCall = False
            self.account.call_id = None
            self.current_input = ''
            self.callback(CallStateChange.HANGUP, self.callback_id, self)
        else:
            print('| Unknown state:', ci.state)

    def onCallMediaState(self, prm) -> None:
        call_info = self.getInfo()
        print('| onCallMediaState call info state', call_info.state)
        for media_index, media in enumerate(call_info.media):
            if media.type == pj.PJMEDIA_TYPE_AUDIO and (media.status == pj.PJSUA_CALL_MEDIA_ACTIVE or media.status == pj.PJSUA_CALL_MEDIA_REMOTE_HOLD):
                print('| Connected media', media.status)
                self.audio_media = self.getAudioMedia(media_index)

    def onDtmfDigit(self, prm: pj.OnDtmfDigitParam) -> None:
        if not self.playback_is_done:
            print('| Playback interrupted.')
            if self.player:
                self.player.stopTransmit(self.audio_media)
            self.playback_is_done = True
        self.last_seen = time.time()
        self.pressed_digit_list.append(prm.digit)

    def handle_dtmf_digit(self, pressed_digit: str) -> None:
        print('| onDtmfDigit: digit', pressed_digit)
        ha.trigger_webhook(self.ha_config, {
            'event': 'dtmf_digit',
            'caller': self.call_info["remote_uri"] if self.call_info else "unknown",
            'parsed_caller': self.call_info["parsed_caller"] if self.call_info else None,
            'digit': pressed_digit,
        })
        if not self.menu:
            return
        self.current_input += pressed_digit
        print('| Current input:', self.current_input)
        choices = self.menu.get('choices')
        if choices is not None:
            if self.current_input in choices:
                self.handle_menu(choices[self.current_input])
                return
            if self.menu.get('choices_are_pin'):
                # in PIN mode the error message will play if the input has same length than the longest PIN
                max_choice_length = max(map(lambda choice: len(choice), choices))
                if len(self.current_input) == max_choice_length:
                    print('| No PIN matched', self.current_input)
                    self.handle_menu(self.menu['default_choice'])
            else:
                # in normal mode the error will play as soon as the input does not match any choice
                still_valid = any(map(lambda choice: choice.startswith(self.current_input), choices))
                if not still_valid:
                    print('| Invalid input', self.current_input)
                    self.handle_menu(self.menu['default_choice'])

    def onCallTransferRequest(self, prm):
        print("| onCallTransferRequest")

    def onCallTransferStatus(self, prm):
        print("| onCallTransferStatus")

    def onCallReplaceRequest(self, prm):
        print("| onCallReplaceRequest")

    def onCallReplaced(self, prm):
        print("| onCallReplaced")

    def onCallRxOffer(self, prm):
        print("| onCallRxOffer")

    def onCallRxReinvite(self, prm):
        print("| onCallRxReinvite")

    def onCallTxOffer(self, prm):
        print("| onCallTxOffer")

    def onCallRedirected(self, prm):
        print("| onCallRedirected")

    def handle_menu(self, menu: Optional[Menu]) -> None:
        if not menu:
            print('| No menu supplied')
            return
        self.menu = menu
        menu_id = menu['id']
        if menu_id:
            ha.trigger_webhook(self.ha_config, {
                'event': 'entered_menu',
                'caller': self.call_info["remote_uri"] if self.call_info else "unknown",
                'parsed_caller': self.call_info["parsed_caller"] if self.call_info else None,
                'menu_id': menu_id,
            })
        self.current_input = ''
        message = menu['message']
        audio_file = menu['audio_file']
        language = menu['language']
        action = menu['action']
        post_action = menu['post_action']
        if message:
            self.play_message(message, language)
        if audio_file:
            self.play_audio_file(audio_file)
        self.handle_action(action)
        self.scheduled_post_action = post_action

    def handle_action(self, action: Optional[Action]) -> None:
        if not action:
            print('| No action supplied')
            return
        domain = action.get('domain')
        service = action.get('service')
        entity_id = action.get('entity_id')
        if (not domain) or (not service) or (not entity_id):
            print('| Error: one of domain, service or entity_id was not provided')
            return
        print('| Calling home assistant service on domain', domain, 'service', service, 'with entity', entity_id)
        try:
            ha.call_service(self.ha_config, domain, service, entity_id)
        except Exception as e:
            print('| Error calling home-assistant service:', e)

    def play_message(self, message: str, language: str) -> None:
        print('| Playing message:', message)
        sound_file_name, must_be_deleted = ha.create_and_get_tts(self.ha_config, message, language)
        self.play_wav_file(sound_file_name, must_be_deleted)

    def play_audio_file(self, audio_file: str) -> None:
        print('| Playing audio file:', audio_file)
        sound_file_name = audio.convert_audio_to_wav(audio_file)
        if sound_file_name:
            self.play_wav_file(sound_file_name, True)

    def play_wav_file(self, sound_file_name: str, must_be_deleted: bool) -> None:
        self.player = player.Player(self.on_playback_done)
        self.playback_is_done = False
        self.player.play_file(self.audio_media, sound_file_name)
        if must_be_deleted:
            os.remove(sound_file_name)

    def on_playback_done(self) -> None:
        print('| Playback done.')
        self.playback_is_done = True

    def accept(self, answer_mode: CallHandling, answer_after: float) -> None:
        call_prm = pj.CallOpParam()
        call_prm.statusCode = 180
        self.answer(call_prm)
        if answer_mode == CallHandling.ACCEPT:
            self.answer_at = time.time() + answer_after

    def hangup_call(self) -> None:
        print('| Hang-up.')
        call_prm = pj.CallOpParam(True)
        pj.Call.hangup(self, call_prm)

    def answer_call(self, new_menu: Optional[MenuFromStdin]) -> None:
        print('| Trigger answer of call (if not established already)')
        if new_menu:
            self.menu = self.normalize_menu(new_menu)
        self.answer_at = time.time()

    def send_dtmf(self, digits: str, method: DtmfMethod = 'in_band') -> None:
        self.last_seen = time.time()
        print('| Sending DTMF', digits)
        if method == 'in_band':
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

    def get_callback_id(self) -> str:
        if self.uri_to_call:
            return self.uri_to_call
        call_info = self.get_call_info()
        if call_info['parsed_caller']:
            return call_info['parsed_caller']
        return call_info['remote_uri']

    def get_call_info(self) -> CallInfo:
        ci = self.getInfo()
        parsed_caller = self.parse_caller(ci.remoteUri)
        return {
            'remote_uri': ci.remoteUri,
            'local_uri': ci.localUri,
            'parsed_caller': parsed_caller,
        }

    def normalize_menu(self, menu: MenuFromStdin, parent_menu: Optional[Menu] = None, is_default_or_timeout_choice=False) -> Menu:
        normalized_menu: Menu = {
            'id': menu.get('id'),
            'message': menu.get('message'),
            'audio_file': menu.get('audio_file'),
            'language': menu.get('language') or self.ha_config.tts_language,
            'action': menu.get('action'),
            'choices_are_pin': menu.get('choices_are_pin') or False,
            'choices': None,
            'default_choice': None,
            'timeout_choice': None,
            'timeout': utils.convert_to_float(menu.get('timeout'), DEFAULT_TIMEOUT),
            'post_action': menu.get('post_action') or 'noop',
            'parent_menu': parent_menu,
        }
        choices = menu.get('choices')

        def normalize_choice(item: tuple[Any, MenuFromStdin]) -> tuple[str, Menu]:
            choice, sub_menu = item
            normalized_choice = str(choice).lower()
            normalized_sub_menu = self.normalize_menu(sub_menu, normalized_menu, normalized_choice in ['default', 'timeout'])
            return normalized_choice, normalized_sub_menu

        def get_default_or_timeout_choice(choice: Union[Literal['default'], Literal['timeout']]) -> Optional[Menu]:
            if is_default_or_timeout_choice:
                return None
            elif choice in normalized_choices:
                return normalized_choices.pop(choice)
            else:
                return Call.get_default_menu(normalized_menu) if choice == 'default' else Call.get_timeout_menu(normalized_menu)

        normalized_choices = dict(map(normalize_choice, choices.items())) if choices else dict()
        default_choice = get_default_or_timeout_choice('default')
        timeout_choice = get_default_or_timeout_choice('timeout')
        normalized_menu['choices'] = normalized_choices
        normalized_menu['default_choice'] = default_choice
        normalized_menu['timeout_choice'] = timeout_choice
        return normalized_menu

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
            'audio_file': None,
            'language': 'en',
            'action': None,
            'choices_are_pin': False,
            'choices': None,
            'default_choice': None,
            'timeout_choice': None,
            'post_action': 'return',
            'timeout': DEFAULT_TIMEOUT,
            'parent_menu': parent_menu,
        }

    @staticmethod
    def get_timeout_menu(parent_menu: Menu) -> Menu:
        return {
            'id': None,
            'message': None,
            'audio_file': None,
            'language': 'en',
            'action': None,
            'choices_are_pin': False,
            'choices': None,
            'default_choice': None,
            'timeout_choice': None,
            'post_action': 'hangup',
            'timeout': DEFAULT_TIMEOUT,
            'parent_menu': parent_menu,
        }

    @staticmethod
    def get_standard_menu() -> Menu:
        standard_menu: Menu = {
            'id': None,
            'message': None,
            'audio_file': None,
            'language': 'en',
            'action': None,
            'choices_are_pin': False,
            'choices': dict(),
            'default_choice': None,
            'timeout_choice': None,
            'post_action': 'noop',
            'timeout': DEFAULT_TIMEOUT,
            'parent_menu': None,
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
    account: pj.Account,
    uri_to_call: str,
    menu: Optional[MenuFromStdin],
    callback: CallCallback,
    ha_config: ha.HaConfig,
    ring_timeout: float,
    webhook_to_call: Optional[str],
) -> Call:
    new_call = Call(ep, account, pj.PJSUA_INVALID_ID, uri_to_call, menu, callback, ha_config, ring_timeout, webhook_to_call)
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

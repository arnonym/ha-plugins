from __future__ import annotations

import os
import time
import re
from enum import Enum
from typing import Optional, Callable, Union, Any, List

import pjsua2 as pj
import yaml
from typing_extensions import TypedDict, Literal

import ha
import utils
import account
import audio
import player
from log import log


class CallStateChange(Enum):
    CALL = 1
    HANGUP = 2


DEFAULT_TIMEOUT = 300.0
DEFAULT_DTMF_ON = 180
DEFAULT_DTMF_OFF = 220

CallCallback = Callable[[CallStateChange, str, 'Call'], None]
DtmfMethod = Union[Literal['in_band'], Literal['rfc2833'], Literal['sip_info']]


class WebhookToCall(TypedDict):
    call_established: Optional[str]
    entered_menu: Optional[str]
    dtmf_digit: Optional[str]
    call_disconnected: Optional[str]


class Action(TypedDict):
    domain: str
    service: str
    entity_id: str


class PostActionReturn(TypedDict):
    action: Literal['return']
    level: int


class PostActionJump(TypedDict):
    action: Literal['jump']
    menu_id: str


class PostActionHangup(TypedDict):
    action: Literal['hangup']


class PostActionNoop(TypedDict):
    action: Literal['noop']


class PostActionRepeatMessage(TypedDict):
    action: Literal['repeat_message']


PostAction = Union[PostActionReturn, PostActionJump, PostActionHangup, PostActionNoop, PostActionRepeatMessage]


class MenuFromStdin(TypedDict):
    id: Optional[str]
    message: Optional[str]
    audio_file: Optional[str]
    language: Optional[str]
    action: Optional[Action]
    choices_are_pin: Optional[bool]
    post_action: Optional[str]
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
                 callback: CallCallback, ha_config: ha.HaConfig, ring_timeout: float, webhook_to_call: Optional[str], webhooks: Optional[WebhookToCall]):
        pj.Call.__init__(self, sip_account, call_id)
        self.player: Optional[player.Player] = None
        self.audio_media: Optional[pj.AudioMedia] = None
        self.connected = False
        self.current_input = ''
        self.end_point = end_point
        self.account = sip_account
        self.uri_to_call = uri_to_call
        self.ha_config = ha_config
        self.ring_timeout = ring_timeout
        self.settle_time = sip_account.config.settle_time
        self.webhook_to_call = webhook_to_call
        self.webhooks: WebhookToCall = webhooks or WebhookToCall(call_established=None, entered_menu=None, dtmf_digit=None, call_disconnected=None)
        self.callback = callback
        self.scheduled_post_action: Optional[PostAction] = None
        self.playback_is_done = True
        self.last_seen = time.time()
        self.call_settled_at: Optional[float] = None
        self.answer_at: Optional[float] = None
        self.tone_gen: Optional[pj.ToneGenerator] = None
        self.call_info: Optional[CallInfo] = None
        self.pressed_digit_list: List[str] = []
        self.callback_id = self.get_callback_id()
        self.menu = self.normalize_menu(menu) if menu else self.get_standard_menu()
        self.menu_map = self.create_menu_map(self.menu)
        Call.pretty_print_menu(self.menu)
        log(self.account.config.index, 'Registering call with id %s' % self.callback_id)
        self.callback(CallStateChange.CALL, self.callback_id, self)

    def handle_events(self) -> None:
        if not self.connected and time.time() - self.last_seen > self.ring_timeout:
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
                log(self.account.config.index, 'Could not find menu id: %s' % post_action["menu_id"])
        elif post_action["action"] == 'hangup':
            self.hangup_call()
        elif post_action["action"] == 'repeat_message':
            self.handle_menu(self.menu, send_webhook_event=False, handle_action=False, reset_input=False)

    def trigger_webhook(self, event: ha.WebhookEvent):
        event_id = event.get('event')
        additional_webhook = self.webhooks.get(event_id)
        if additional_webhook:
            ha.trigger_webhook(self.ha_config, event, additional_webhook)
        ha.trigger_webhook(self.ha_config, event)

    def handle_connected_state(self):
        log(self.account.config.index, 'Call is established.')
        self.connected = True
        self.last_seen = time.time()
        if self.webhook_to_call:
            ha.trigger_webhook(self.ha_config, {
                'event': 'call_established',
                'caller': self.call_info['remote_uri'] if self.call_info else 'unknown',
                'parsed_caller': self.call_info['parsed_caller'] if self.call_info else None,
                'sip_account': self.account.config.index,
            }, self.webhook_to_call)
        self.trigger_webhook({
            'event': 'call_established',
            'caller': self.call_info['remote_uri'] if self.call_info else 'unknown',
            'parsed_caller': self.call_info['parsed_caller'] if self.call_info else None,
            'sip_account': self.account.config.index,
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
            self.trigger_webhook({
                'event': 'call_disconnected',
                'caller': self.call_info['remote_uri'],
                'parsed_caller': self.call_info['parsed_caller'],
                'sip_account': self.account.config.index,
            })
            self.connected = False
            self.account.c = None
            self.account.acceptCall = False
            self.account.inCall = False
            self.account.call_id = None
            self.current_input = ''
            self.callback(CallStateChange.HANGUP, self.callback_id, self)
        else:
            log(self.account.config.index, 'Unknown state: %s' % ci.state)

    def onCallMediaState(self, prm) -> None:
        call_info = self.getInfo()
        log(self.account.config.index, 'onCallMediaState call info state %s' % call_info.state)
        for media_index, media in enumerate(call_info.media):
            if media.type == pj.PJMEDIA_TYPE_AUDIO and (media.status == pj.PJSUA_CALL_MEDIA_ACTIVE or media.status == pj.PJSUA_CALL_MEDIA_REMOTE_HOLD):
                log(self.account.config.index, 'Connected media %s' % media.status)
                self.audio_media = self.getAudioMedia(media_index)

    def onDtmfDigit(self, prm: pj.OnDtmfDigitParam) -> None:
        if not self.playback_is_done:
            log(self.account.config.index, 'Playback interrupted.')
            if self.player:
                self.player.stopTransmit(self.audio_media)
            self.playback_is_done = True
        self.last_seen = time.time()
        self.pressed_digit_list.append(prm.digit)

    def handle_dtmf_digit(self, pressed_digit: str) -> None:
        log(self.account.config.index, 'onDtmfDigit: digit %s' % pressed_digit)
        self.trigger_webhook({
            'event': 'dtmf_digit',
            'caller': self.call_info['remote_uri'] if self.call_info else 'unknown',
            'parsed_caller': self.call_info['parsed_caller'] if self.call_info else None,
            'digit': pressed_digit,
            'sip_account': self.account.config.index,
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
        log(self.account.config.index, 'onCallTransferStatus')

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
            })
        if reset_input:
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
        if handle_action:
            self.handle_action(action)
        self.scheduled_post_action = post_action

    def handle_action(self, action: Optional[Action]) -> None:
        if not action:
            log(self.account.config.index, 'No action supplied')
            return
        domain = action.get('domain')
        service = action.get('service')
        entity_id = action.get('entity_id')
        if (not domain) or (not service) or (not entity_id):
            log(self.account.config.index, 'Error: one of domain, service or entity_id was not provided')
            return
        log(self.account.config.index, 'Calling home assistant service on domain %s service %s with entity %s' % (domain, service, entity_id))
        try:
            ha.call_service(self.ha_config, domain, service, entity_id)
        except Exception as e:
            log(self.account.config.index, 'Error calling home-assistant service: %s' % e)

    def play_message(self, message: str, language: str) -> None:
        log(self.account.config.index, 'Playing message: %s' % message)
        sound_file_name, must_be_deleted = ha.create_and_get_tts(self.ha_config, message, language)
        self.play_wav_file(sound_file_name, must_be_deleted)

    def play_audio_file(self, audio_file: str) -> None:
        log(self.account.config.index, 'Playing audio file: %s' % audio_file)
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
        log(self.account.config.index, 'Playback done.')
        self.playback_is_done = True

    def accept(self, answer_mode: CallHandling, answer_after: float) -> None:
        call_prm = pj.CallOpParam()
        call_prm.statusCode = 180
        self.answer(call_prm)
        if answer_mode == CallHandling.ACCEPT:
            self.answer_at = time.time() + answer_after

    def hangup_call(self) -> None:
        log(self.account.config.index, 'Hang-up.')
        call_prm = pj.CallOpParam(True)
        pj.Call.hangup(self, call_prm)

    def answer_call(self, new_menu: Optional[MenuFromStdin]) -> None:
        log(self.account.config.index, 'Trigger answer of call (if not established already)')
        if new_menu:
            self.menu = self.normalize_menu(new_menu)
        self.answer_at = time.time()

    def send_dtmf(self, digits: str, method: DtmfMethod = 'in_band') -> None:
        self.last_seen = time.time()
        log(self.account.config.index, 'Sending DTMF %s' % digits)
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
                menu_id = utils.safe_list_get(params, 0, None)
                return PostActionJump(action='jump', menu_id=menu_id)
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
            'post_action': parse_post_action(menu.get('post_action')),
            'parent_menu': parent_menu,
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
            'audio_file': None,
            'language': 'en',
            'action': None,
            'choices_are_pin': False,
            'choices': None,
            'default_choice': None,
            'timeout_choice': None,
            'post_action': PostActionReturn(action="return", level=1),
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
            'post_action': PostActionHangup(action="hangup"),
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
            'post_action': PostActionNoop(action="noop"),
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
    webhooks: Optional[WebhookToCall],
) -> Call:
    new_call = Call(ep, account, pj.PJSUA_INVALID_ID, uri_to_call, menu, callback, ha_config, ring_timeout, webhook_to_call, webhooks)
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

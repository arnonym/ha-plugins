import os
from enum import Enum
from typing import Optional, Callable, Union
import time

import pjsua2 as pj
import yaml
from typing_extensions import TypedDict, Literal

import ha
import utils
from player import Player


class CallStateChange(Enum):
    CALL = 1
    HANGUP = 2


DEFAULT_TIMEOUT = 300

CallCallback = Callable[[CallStateChange, str, 'Call'], None]
StateType = Union[str, int, bool, float]
PostAction = Union[Literal['return'], Literal['hangup'], Literal['noop']]


class Action(TypedDict):
    domain: str
    service: str
    entity_id: str


class MenuFromStdin(TypedDict):
    id: Optional[str]
    message: Optional[str]
    language: Optional[str]
    action: Optional[Action]
    choices_are_pin: Optional[bool]
    post_action: Optional[PostAction]
    timeout: Optional[int]
    choices: Optional[dict[str, 'MenuFromStdin']]  # type: ignore


class Menu(TypedDict):
    id: Optional[str]
    message: Optional[str]
    language: str
    action: Optional[Action]
    choices_are_pin: bool
    post_action: PostAction
    timeout: Optional[int]
    choices: Optional[dict[str, 'Menu']]  # type: ignore
    default_choice: Optional['Menu']  # type: ignore
    timeout_choice: Optional['Menu']  # type: ignore
    parent_menu: Optional['Menu']  # type: ignore


class Call(pj.Call):
    def __init__(self, end_point: pj.Endpoint, account: pj.Account, call_id: str, uri_to_call: str, menu: Optional[MenuFromStdin],
                 callback: CallCallback, ha_config: ha.HaConfig):
        pj.Call.__init__(self, account, call_id)
        self.player: Optional[Player] = None
        self.audio_media: Optional[pj.AudioMedia] = None
        self.connected: bool = False
        self.current_input = ""
        self.end_point = end_point
        self.account = account
        self.uri_to_call = uri_to_call
        self.ha_config = ha_config
        self.callback = callback
        self.scheduled_post_action: Optional[PostAction] = None
        self.playback_is_done = False
        self.menu = self.normalize_menu(menu)
        self.last_seen = time.time()
        Call.pretty_print_menu(self.menu)
        self.callback(CallStateChange.CALL, self.uri_to_call, self)

    def handle_events(self):
        if not self.connected:
            return
        if time.time() - self.last_seen > self.menu.get('timeout'):
            print('| Timeout of', self.menu.get('timeout'), 'triggered.')
            self.handle_menu(self.menu['timeout_choice'])
            return
        if self.playback_is_done and self.scheduled_post_action:
            post_action = self.scheduled_post_action
            self.scheduled_post_action = None
            print("| Scheduled post action:", post_action)
            if post_action == 'noop':
                pass
            elif post_action == 'return':
                self.handle_menu(self.menu['parent_menu'])
            elif post_action == 'hangup':
                self.hangup_call()
            else:
                print("| Unknown post_action:", post_action)

    def onCallState(self, prm):
        ci = self.getInfo()
        if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            print('| Call connected')
            self.connected = True
            self.last_seen = time.time()
        elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            print('| Call disconnected')
            self.connected = False
            self.account.c = None
            self.account.acceptCall = False
            self.account.inCall = False
            self.account.call_id = None
            self.current_input = ""
            self.callback(CallStateChange.HANGUP, self.uri_to_call, self)
        else:
            print('| Unknown state:', ci.state)

    def onCallMediaState(self, prm):
        call_info = self.getInfo()
        print('| onCallMediaState', call_info.state)
        for media_index, media in enumerate(call_info.media):
            if media.type == pj.PJMEDIA_TYPE_AUDIO and call_info.stateText == 'CONFIRMED':
                self.audio_media = self.getAudioMedia(media_index)
                self.handle_menu(self.menu)

    def onDtmfDigit(self, prm: pj.OnDtmfDigitParam):
        self.last_seen = time.time()
        print('| onDtmfDigit: digit', prm.digit)
        if not self.menu:
            return
        self.current_input += prm.digit
        print("| Current input:", self.current_input)
        choices = self.menu.get('choices')
        if choices:
            if self.current_input in choices:
                self.handle_menu(choices[self.current_input])
                return
            if self.menu.get('choices_are_pin'):
                # in PIN mode the error message will play if the input has same length than the longest PIN
                max_choice_length = max(map(lambda choice: len(choice), choices))
                if len(self.current_input) == max_choice_length:
                    print("| No PIN matched", self.current_input)
                    self.handle_menu(self.menu['default_choice'])
            else:
                # in normal mode the error will play as soon as the input does not match any number
                still_valid = any(map(lambda choice: choice.startswith(self.current_input), choices))
                if not still_valid:
                    print("| Invalid input", self.current_input)
                    self.handle_menu(self.menu['default_choice'])

    def handle_menu(self, menu: Optional[Menu]) -> None:
        if not menu:
            return
        self.menu = menu
        menu_id = menu['id']
        if menu_id:
            ha.trigger_webhook(self.ha_config, {'event': 'entered_menu', 'menu_id': menu_id})
        self.current_input = ""
        message = menu['message']
        language = menu['language']
        action = menu['action']
        post_action = menu['post_action']
        if message:
            self.play_message(message, language)
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
        self.player = Player(self.on_playback_done)
        self.playback_is_done = False
        self.player.play_file(self.audio_media, sound_file_name)
        if must_be_deleted:
            os.remove(sound_file_name)

    def on_playback_done(self):
        print("| Playback done.")
        self.playback_is_done = True

    def hangup_call(self):
        print("| Hang-up.")
        call_prm = pj.CallOpParam(True)
        pj.Call.hangup(self, call_prm)

    def normalize_menu(self, menu: Optional[MenuFromStdin], parent_menu: Optional[Menu] = None) -> Optional[Menu]:
        if not menu:
            return None
        normalized_menu: Menu = {
            'id': menu.get('id', None),
            'message': menu.get('message', None),
            'language': menu.get('language', self.ha_config.tts_language),
            'action': menu.get('action', None),
            'choices_are_pin': menu.get('choices_are_pin', False),
            'choices': None,
            'default_choice': None,
            'timeout_choice': None,
            'timeout': utils.convert_to_int(menu.get('timeout', DEFAULT_TIMEOUT), DEFAULT_TIMEOUT),
            'post_action': menu.get('post_action', 'noop'),
            'parent_menu': parent_menu,
        }
        choices = menu.get('choices')
        normalized_choices = dict(map(lambda v: (str(v[0]), self.normalize_menu(v[1], normalized_menu)), choices.items())) if choices else dict()
        default_choice = normalized_choices.pop('default') if 'default' in normalized_choices else Call.get_default_menu(normalized_menu)
        timeout_choice = normalized_choices.pop('timeout') if 'timeout' in normalized_choices else Call.get_timeout_menu(normalized_menu)
        normalized_menu['choices'] = normalized_choices
        normalized_menu['default_choice'] = default_choice
        normalized_menu['timeout_choice'] = timeout_choice
        return normalized_menu

    @staticmethod
    def get_default_menu(parent_menu: Menu) -> Menu:
        return {
            'id': None,
            'message': 'Unknown option',
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
    def pretty_print_menu(menu: Optional[Menu]) -> None:
        if not menu:
            print("| No menu defined")
            return
        lines = yaml.dump(menu, sort_keys=False).split('\n')
        lines_with_pipe = map(lambda line: "| " + line, lines)
        print("\n".join(lines_with_pipe))


def make_call(ep: pj.Endpoint, account: pj.Account, uri_to_call: str, menu: Optional[MenuFromStdin], callback: CallCallback, ha_config: ha.HaConfig):
    new_call = Call(ep, account, pj.PJSUA_INVALID_ID, uri_to_call, menu, callback, ha_config)
    call_param = pj.CallOpParam(True)
    new_call.makeCall(uri_to_call, call_param)
    return new_call

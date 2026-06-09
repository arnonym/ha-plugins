from __future__ import annotations

from typing import Any, Optional, Union, TYPE_CHECKING

import yaml
from typing_extensions import TypedDict, Literal

import utils
from constants import DEFAULT_RING_TIMEOUT
from log import log
from post_action import PostAction, PostActionNoop, PostActionHangup, PostActionRepeatMessage, PostActionReturn, PostActionJump

if TYPE_CHECKING:
    from command_client import Command


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


def normalize_menu(
    menu: Optional[MenuFromStdin],
    default_language: str,
    account_index: int,
    parent_menu: Optional[Menu] = None,
    is_default_or_timeout_choice: bool = False,
) -> tuple[Optional[Menu], dict[str, Menu]]:
    if not menu:
        return None, dict()
    normalized_menu = _normalize_menu(menu, default_language, account_index, parent_menu, is_default_or_timeout_choice)
    menu_map = _create_menu_map(normalized_menu)
    return normalized_menu, menu_map


def _normalize_menu(
    menu: MenuFromStdin,
    default_language: str,
    account_index: int,
    parent_menu: Optional[Menu] = None,
    is_default_or_timeout_choice: bool = False,
) -> Menu:
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
                log(account_index, 'Error: jump action requires a menu id as parameter, will be treated as noop')
                return PostActionNoop(action='noop')
            return PostActionJump(action='jump', menu_id=jump_to.strip())
        else:
            log(account_index, f'Unknown post_action: {action}')
            return PostActionNoop(action='noop')

    def normalize_choice(item: tuple[Any, MenuFromStdin], parent_menu_for_choice: Menu) -> tuple[str, Menu]:
        choice, sub_menu = item
        normalized_choice = str(choice).lower()
        normalized_sub_menu = _normalize_menu(sub_menu, default_language, account_index, parent_menu_for_choice, normalized_choice in ['default', 'timeout'])
        return normalized_choice, normalized_sub_menu

    def get_default_or_timeout_choice(choice: Union[Literal['default'], Literal['timeout']], parent_menu_for_choice: Menu) -> Optional[Menu]:
        if is_default_or_timeout_choice:
            return None
        elif choice in normalized_choices:
            return normalized_choices.pop(choice)
        else:
            if choice == 'default':
                return _get_default_menu(parent_menu_for_choice)
            else:
                return _get_timeout_menu(parent_menu_for_choice)

    menu_id = menu.get('id')
    normalized_menu: Menu = {
        'id': menu_id.strip() if menu_id else None,
        'message': menu.get('message'),
        'handle_as_template': menu.get('handle_as_template') or False,
        'audio_file': menu.get('audio_file'),
        'language': menu.get('language') or default_language,
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


def _create_menu_map(menu: Optional[Menu]) -> dict[str, Menu]:
    def add_to_map(menu_map: dict[str, Menu], m: Menu) -> dict[str, Menu]:
        if m['id']:
            menu_map[m['id']] = m
        if m['choices']:
            for choice in m['choices'].values():
                add_to_map(menu_map, choice)
        if m['default_choice']:
            add_to_map(menu_map, m['default_choice'])
        if m['timeout_choice']:
            add_to_map(menu_map, m['timeout_choice'])
        return menu_map
    if not menu:
        return {}
    return add_to_map({}, menu)


def _get_default_menu(parent_menu: Menu) -> Menu:
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


def _get_timeout_menu(parent_menu: Menu) -> Menu:
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


def _get_standard_menu() -> Menu:
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
    standard_menu['default_choice'] = _get_default_menu(standard_menu)
    standard_menu['timeout_choice'] = _get_timeout_menu(standard_menu)
    return standard_menu


def pretty_print_menu(menu: Optional[Menu]) -> None:
    if not menu:
        print('No menu defined.')
        return
    lines = yaml.dump(menu, sort_keys=False).split('\n')
    lines_with_pipe = map(lambda line: '| ' + line, lines)
    print('\n'.join(lines_with_pipe))

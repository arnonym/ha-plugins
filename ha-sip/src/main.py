#!/usr/bin/env python3

import collections.abc
import sys
from typing import Optional, TypedDict

import pjsua2 as pj
import yaml

import account
import call
import command_client
import ha
import sip
import state
import utils


class IncomingCallConfig(TypedDict):
    allowed_numbers: Optional[list[str]]
    answer_after: Optional[int]
    menu: call.MenuFromStdin


def handle_command(end_point: pj.Endpoint, sip_accounts: dict[int, pj.Account], call_state: state.State, command, ha_config: ha.HaConfig) -> None:
    if not isinstance(command, collections.abc.Mapping):
        print('| Error: Not an object:', command)
        return
    verb = command.get('command')
    number = command.get('number')
    menu = command.get('menu')
    ring_timeout = utils.convert_to_int(command.get('ring_timeout', call.DEFAULT_TIMEOUT), call.DEFAULT_TIMEOUT)
    sip_account_number = utils.convert_to_int(command.get('sip_account', -1), -1)
    if verb == 'dial':
        if not number:
            print('| Error: Missing number for command "dial"')
            return
        print('| Got "dial" command for', number)
        if call_state.is_active(number):
            print('| Warning: already in progress:', number)
            return
        sip_account = sip_accounts.get(sip_account_number, next(iter(sip_accounts.values())))
        call.make_call(end_point, sip_account, number, menu, call_state.callback, ha_config, ring_timeout)
    elif verb == 'hangup':
        if not number:
            print('| Error: Missing number for command "hangup"')
            return
        print('| Got "hangup" command for', number)
        if not call_state.is_active(number):
            print('| Warning: not in progress:', number)
            return
        current_call = call_state.get_call(number)
        current_call.hangup_call()
    elif verb == 'answer':
        if not number:
            print('| Error: Missing number for command "answer"')
            return
        print('| Got "answer" command for', number)
        if not call_state.is_active(number):
            print('| Warning: not in progress:', number)
            return
        current_call = call_state.get_call(number)
        current_call.answer_call(menu)
    elif verb == 'state':
        call_state.output()
    elif verb == 'quit':
        print('| Quit.')
        end_point.libDestroy()
        sys.exit(0)
    else:
        print('| Error: Unknown command:', verb)


def handle_command_list(command_server, end_point, new_account, call_state, ha_config) -> None:
    command_list = command_server.get_command_list()
    for command in command_list:
        handle_command(end_point, new_account, call_state, command, ha_config)


def load_menu_from_file(file_name: Optional[str]) -> Optional[IncomingCallConfig]:
    if not file_name:
        print('| No file name for incoming call config specified.')
        return None
    try:
        with open(file_name) as stream:
            content = yaml.safe_load(stream)
            print('| Loaded menu for incoming call.')
            return content
    except BaseException as e:
        print('| Error loading menu for incoming call:', e)
        return None


def main():
    if "local" in sys.argv:
        import config_local as config
    else:
        import config
    endpoint_config = sip.MyEndpointConfig(
        port=utils.convert_to_int(config.PORT, 5060),
        log_level=utils.convert_to_int(config.LOG_LEVEL, 5)
    )
    account_configs = {
        1: account.MyAccountConfig(
            enabled=config.SIP1_ENABLED.lower() == 'true',
            id_uri=config.SIP1_ID_URI,
            registrar_uri=config.SIP1_REGISTRAR_URI,
            realm=config.SIP1_REALM,
            user_name=config.SIP1_USER_NAME,
            password=config.SIP1_PASSWORD,
            mode=call.CallHandling.get_or_else(config.SIP1_ANSWER_MODE, call.CallHandling.LISTEN),
            incoming_call_config=load_menu_from_file(config.SIP1_INCOMING_CALL_FILE),
        ),
        2: account.MyAccountConfig(
            enabled=config.SIP2_ENABLED.lower() == 'true',
            id_uri=config.SIP2_ID_URI,
            registrar_uri=config.SIP2_REGISTRAR_URI,
            realm=config.SIP2_REALM,
            user_name=config.SIP2_USER_NAME,
            password=config.SIP2_PASSWORD,
            mode=call.CallHandling.get_or_else(config.SIP2_ANSWER_MODE, call.CallHandling.LISTEN),
            incoming_call_config=load_menu_from_file(config.SIP2_INCOMING_CALL_FILE),
        ),
    }
    ha_config = ha.HaConfig(config.HA_BASE_URL, config.HA_TOKEN, config.TTS_PLATFORM, config.TTS_LANGUAGE, config.HA_WEBHOOK_ID)
    call_state = state.create()
    end_point = sip.create_endpoint(endpoint_config)
    sip_accounts = {}
    is_first_enabled_account = True
    for key, config in account_configs.items():
        if config.enabled:
            sip_accounts[key] = account.create_account(end_point, config, call_state.callback, ha_config, is_first_enabled_account)
            is_first_enabled_account = False
    command_server = command_client.CommandClient()
    while True:
        end_point.libHandleEvents(20)
        handle_command_list(command_server, end_point, sip_accounts, call_state, ha_config)
        for c in list(call_state.current_call_dict.values()):
            c.handle_events()


if __name__ == '__main__':
    main()

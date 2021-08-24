#!/usr/bin/env python3

import sys

import account
import sip
import call
import command_client
import state
import collections
import config


def handle_command(end_point, sip_account, call_state, command) -> None:
    if not isinstance(command, collections.Mapping):
        print("Error: Not an object:", command)
        return
    verb = command.get('command', None)
    number = command.get('number', None)
    if verb == 'dial':
        print('Got dial command for', number)
        if call_state.is_active(number):
            print('Warning: already in progress:', number)
            return
        call.make_call(end_point, sip_account, number, call_state.callback)
    elif verb == 'hangup':
        print('Got hangup command for', number)
        if not call_state.is_active(number):
            print('Warning: not in progress:', number)
            return
        current_call = call_state.get_call(number)
        current_call.hangup_call()
    elif verb == 'state':
        call_state.output()
    elif verb == 'quit':
        print('Quit.')
        end_point.libDestroy()
        sys.exit(0)
    else:
        print("Error: Unknown command:", verb)


def main():
    endpoint_config = sip.MyEndpointConfig(
        port=config.PORT
    )
    account_config = account.MyAccountConfig(
        id_uri=config.ID_URI,
        registrar_uri=config.REGISTRAR_URI,
        realm=config.REALM,
        user_name=config.USER_NAME,
        password=config.PASSWORD,
    )
    call_state = state.create()
    end_point = sip.create_endpoint(endpoint_config)
    new_account = account.create_account(end_point, account_config, call_state.callback)
    command_server = command_client.CommandClient()
    while True:
        end_point.libHandleEvents(20)
        command_list = command_server.get_command_list()
        for command in command_list:
            handle_command(end_point, new_account, call_state, command)


if __name__ == '__main__':
    main()

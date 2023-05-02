#!/usr/bin/env python3

import collections.abc
import sys
import faulthandler
from typing import Optional

import pjsua2 as pj
import yaml

import account
import call
import command_client
import ha
import incoming_call
import sip
import state
import utils
from log import log


def handle_command(
    end_point: pj.Endpoint,
    sip_accounts: dict[int, account.Account],
    call_state: state.State,
    command: command_client.Command,
    ha_config: ha.HaConfig,
) -> None:
    if not isinstance(command, collections.abc.Mapping):
        log(None, 'Error: Not an object: %s' % command)
        return
    verb = command.get('command')
    number_unknown_type = command.get('number')
    number = str(number_unknown_type) if number_unknown_type is not None else None
    menu = command.get('menu')
    ring_timeout = utils.convert_to_float(command.get('ring_timeout'), call.DEFAULT_TIMEOUT)
    sip_account_number = utils.convert_to_int(command.get('sip_account'), -1)
    if verb == 'dial':
        if not number:
            log(None, 'Error: Missing number for command "dial"')
            return
        log(None, 'Got "dial" command for %s' % number)
        if call_state.is_active(number):
            log(None, 'Warning: call already in progress: %s' % number)
            return
        webhook_to_call = command.get('webhook_to_call_after_call_was_established')
        webhooks = command.get('webhook_to_call')
        sip_account = sip_accounts.get(sip_account_number, next(iter(sip_accounts.values())))
        call.make_call(end_point, sip_account, number, menu, call_state.callback, ha_config, ring_timeout, webhook_to_call, webhooks)
    elif verb == 'hangup':
        if not number:
            log(None, 'Error: Missing number for command "hangup"')
            return
        log(None, 'Got "hangup" command for %s' % number)
        if not call_state.is_active(number):
            log(None, 'Warning: call not in progress: %s' % number)
            return
        current_call = call_state.get_call(number)
        current_call.hangup_call()
    elif verb == 'answer':
        if not number:
            log(None, 'Error: Missing number for command "answer"')
            return
        log(None, 'Got "answer" command for %s' % number)
        if not call_state.is_active(number):
            log(None, 'Warning: call not in progress: %s' % number)
            return
        current_call = call_state.get_call(number)
        current_call.answer_call(menu)
    elif verb == 'send_dtmf':
        if not number:
            log(None, 'Error: Missing number for command "send_dtmf"')
            return
        digits = command.get('digits')
        method = command.get('method', 'in_band')
        if (method != 'in_band') and (method != 'rfc2833') and (method != 'sip_info'):
            log(None, 'Error: method must be one of in_band, rfc2833, sip_info')
            return
        if not digits:
            log(None, 'Error: Missing digits for command "send_dtmf"')
            return
        log(None, 'Got "send_dtmf" command for %s' % number)
        if not call_state.is_active(number):
            log(None, 'Warning: call not in progress: %s' % number)
            return
        current_call = call_state.get_call(number)
        current_call.send_dtmf(digits, method)
    elif verb == 'state':
        call_state.output()
    elif verb == 'quit':
        log(None, 'Quit.')
        end_point.libDestroy()
        sys.exit(0)
    else:
        log(None, 'Error: Unknown command: %s' % verb)


def handle_command_list(command_server, end_point, new_account, call_state, ha_config) -> None:
    command_list = command_server.get_command_list()
    for command in command_list:
        handle_command(end_point, new_account, call_state, command, ha_config)


def load_menu_from_file(file_name: Optional[str], sip_account_index: int) -> Optional[incoming_call.IncomingCallConfig]:
    if not file_name:
        log(sip_account_index, 'No file name for incoming call config specified.')
        return None
    try:
        with open(file_name) as stream:
            content = yaml.safe_load(stream)
            log(sip_account_index, 'Loaded menu for incoming call.')
            return content
    except BaseException as e:
        log(sip_account_index, 'Error loading menu for incoming call: %s' % e)
        return None


def main():
    if "local" in sys.argv:
        import config_local as config
    else:
        import config
    name_server = [ns.strip() for ns in config.NAME_SERVER.split(",")]
    name_server_without_empty = [ns for ns in name_server if ns]
    if name_server_without_empty:
        log(None, "Setting name server: %s" % name_server)
    endpoint_config = sip.MyEndpointConfig(
        port=utils.convert_to_int(config.PORT, 5060),
        log_level=utils.convert_to_int(config.LOG_LEVEL, 5),
        name_server=name_server_without_empty
    )
    account_configs = {
        1: account.MyAccountConfig(
            enabled=config.SIP1_ENABLED.lower() == 'true',
            index=1,
            id_uri=config.SIP1_ID_URI,
            registrar_uri=config.SIP1_REGISTRAR_URI,
            realm=config.SIP1_REALM,
            user_name=config.SIP1_USER_NAME,
            password=config.SIP1_PASSWORD,
            mode=call.CallHandling.get_or_else(config.SIP1_ANSWER_MODE, call.CallHandling.LISTEN),
            settle_time=utils.convert_to_float(config.SIP1_SETTLE_TIME, 1),
            incoming_call_config=load_menu_from_file(config.SIP1_INCOMING_CALL_FILE, 1),
        ),
        2: account.MyAccountConfig(
            enabled=config.SIP2_ENABLED.lower() == 'true',
            index=2,
            id_uri=config.SIP2_ID_URI,
            registrar_uri=config.SIP2_REGISTRAR_URI,
            realm=config.SIP2_REALM,
            user_name=config.SIP2_USER_NAME,
            password=config.SIP2_PASSWORD,
            mode=call.CallHandling.get_or_else(config.SIP2_ANSWER_MODE, call.CallHandling.LISTEN),
            settle_time=utils.convert_to_float(config.SIP2_SETTLE_TIME, 1),
            incoming_call_config=load_menu_from_file(config.SIP2_INCOMING_CALL_FILE, 2),
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
    faulthandler.enable()
    main()

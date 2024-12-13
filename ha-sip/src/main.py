#!/usr/bin/env python3

import os
import faulthandler
from typing import Optional

from dotenv import load_dotenv
import yaml
import account
import call
import ha
import incoming_call
import sip
import state
import utils
import mqtt
from command_client import CommandClient
from command_handler import CommandHandler
from log import log


def handle_command_list(command_client: CommandClient, command_handler: CommandHandler) -> None:
    command_list = command_client.get_command_list()
    for command in command_list:
        command_handler.handle_command(command, None)


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


def get_name_server(raw_name_server: str):
    name_server = [ns.strip() for ns in raw_name_server.split(",")]
    name_server_without_empty = [ns for ns in name_server if ns]
    if name_server_without_empty:
        log(None, 'Setting name server: %s' % name_server)
    return name_server_without_empty


def get_cache_dir(raw_cache_dir: str) -> Optional[str]:
    if not raw_cache_dir:
        log(None, 'No cache directory configured.')
        return None
    if not os.path.isdir(raw_cache_dir):
        log(None, 'Error: Cache directory not found.')
        return None
    log(None, "Found cache directory '%s'" % raw_cache_dir)
    return raw_cache_dir


def main():
    load_dotenv()
    import config
    name_server = get_name_server(config.NAME_SERVER)
    cache_dir = get_cache_dir(config.CACHE_DIR)
    endpoint_config = sip.MyEndpointConfig(
        port=utils.convert_to_int(config.PORT, 5060),
        log_level=utils.convert_to_int(config.LOG_LEVEL, 5),
        name_server=name_server
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
        3: account.MyAccountConfig(
            enabled=config.SIP3_ENABLED.lower() == 'true',
            index=3,
            id_uri=config.SIP3_ID_URI,
            registrar_uri=config.SIP3_REGISTRAR_URI,
            realm=config.SIP3_REALM,
            user_name=config.SIP3_USER_NAME,
            password=config.SIP3_PASSWORD,
            mode=call.CallHandling.get_or_else(config.SIP3_ANSWER_MODE, call.CallHandling.LISTEN),
            settle_time=utils.convert_to_float(config.SIP3_SETTLE_TIME, 1),
            incoming_call_config=load_menu_from_file(config.SIP3_INCOMING_CALL_FILE, 3),
        ),
    }
    ha_config = ha.HaConfig(config.HA_BASE_URL, config.HA_TOKEN, config.TTS_PLATFORM, config.TTS_LANGUAGE, config.HA_WEBHOOK_ID, cache_dir)
    call_state = state.create()
    end_point = sip.create_endpoint(endpoint_config)
    sip_accounts = {}
    is_first_enabled_account = True
    command_client = CommandClient()
    command_handler = CommandHandler(end_point, sip_accounts, call_state, ha_config)
    for key, account_config in account_configs.items():
        if account_config.enabled:
            sip_accounts[key] = account.create_account(end_point, account_config, command_handler, ha_config, is_first_enabled_account)
            is_first_enabled_account = False
    mqtt_mode = config.COMMAND_SOURCE.lower().strip() == 'mqtt'
    mqtt_client = mqtt.create_client_and_connect(command_handler) if mqtt_mode else None
    while True:
        if mqtt_client:
            mqtt_client.handle()
        end_point.libHandleEvents(10)
        handle_command_list(command_client, command_handler)
        for c in list(call_state.current_call_dict.values()):
            c.handle_events()


if __name__ == '__main__':
    faulthandler.enable()
    main()

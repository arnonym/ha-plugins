from __future__ import annotations

import re
from typing import Optional

import pjsua2 as pj

import call
import ha
import main


class MyAccountConfig(object):
    def __init__(
        self,
        enabled: bool,
        id_uri: str,
        registrar_uri: str,
        realm: str,
        user_name: str,
        password: str,
        mode: call.CallHandling,
        incoming_call_config: Optional[main.IncomingCallConfig],
    ):
        self.enabled = enabled
        self.id_uri = id_uri
        self.registrar_uri = registrar_uri
        self.realm = realm
        self.user_name = user_name
        self.password = password
        self.ice_enabled = True
        self.mode = mode
        self.incoming_call_config = incoming_call_config


class Account(pj.Account):
    def __init__(self, end_point: pj.Endpoint, callback: call.CallCallback, ha_config: ha.HaConfig):
        pj.Account.__init__(self)
        self.config: Optional[MyAccountConfig] = None
        self.end_point = end_point
        self.callback = callback
        self.ha_config = ha_config

    def create(self, config: MyAccountConfig, make_default=False) -> None:
        self.config = config
        account_config = pj.AccountConfig()
        account_config.idUri = config.id_uri
        account_config.regConfig.registrarUri = config.registrar_uri
        credentials = pj.AuthCredInfo('digest', config.realm, config.user_name, 0, config.password)
        account_config.sipConfig.authCreds.append(credentials)
        account_config.natConfig.iceEnabled = config.ice_enabled
        return pj.Account.create(self, account_config, make_default)

    def onRegState(self, prm) -> None:
        print('| OnRegState:', prm.code, prm.reason)

    def onIncomingCall(self, prm) -> None:
        if not self.config:
            print('| Error: No config set when onIncomingCall was called.')
            return
        menu = self.config.incoming_call_config.get('menu') if self.config.incoming_call_config else None
        allowed_numbers = self.config.incoming_call_config.get('allowed_numbers') if self.config.incoming_call_config else None
        answer_after = self.config.incoming_call_config.get('answer_after', 0) if self.config.incoming_call_config else 0
        c = call.Call(self.end_point, self, prm.callId, prm.callId, menu, self.callback, self.ha_config, call.DEFAULT_TIMEOUT)
        ci = c.getInfo()
        parsed_caller = self.parse_caller(ci.remoteUri)
        answer_mode = self.get_sip_return_code(self.config.mode, allowed_numbers, parsed_caller)
        print('| Incoming call  from  \'%s\' to \'%s\' (parsed: \'%s\')' % (ci.remoteUri, ci.localUri, parsed_caller))
        print('| Allowed numbers:', allowed_numbers)
        print('| Answer mode:', answer_mode.name)
        c.accept(answer_mode, answer_after)
        ha.trigger_webhook(self.ha_config, {'event': 'incoming_call', 'caller': ci.remoteUri, 'parsed_caller': parsed_caller})

    @staticmethod
    def get_sip_return_code(mode: call.CallHandling, allowed_numbers: Optional[list[str]], parsed_caller: Optional[str]) -> call.CallHandling:
        if mode == call.CallHandling.ACCEPT and allowed_numbers:
            return call.CallHandling.ACCEPT if parsed_caller in allowed_numbers else call.CallHandling.LISTEN
        else:
            return mode

    @staticmethod
    def parse_caller(remote_uri: str) -> Optional[str]:
        parsed_caller_match = re.search('<sip:(.+?)[@;>]', remote_uri)
        return parsed_caller_match.group(1) if parsed_caller_match else None


def create_account(end_point: pj.Endpoint, config: MyAccountConfig, callback: call.CallCallback, ha_config: ha.HaConfig, is_default: bool) -> Account:
    account = Account(end_point, callback, ha_config)
    account.create(config, make_default=is_default)
    return account

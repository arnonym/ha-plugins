from __future__ import annotations

from typing import Optional

import pjsua2 as pj

import call
import ha
import incoming_call
import utils
from log import log


class MyAccountConfig(object):
    def __init__(
        self,
        enabled: bool,
        index: int,
        id_uri: str,
        registrar_uri: str,
        realm: str,
        user_name: str,
        password: str,
        mode: call.CallHandling,
        settle_time: float,
        incoming_call_config: Optional[incoming_call.IncomingCallConfig],
    ):
        self.enabled = enabled
        self.index = index
        self.id_uri = id_uri
        self.registrar_uri = registrar_uri
        self.realm = realm
        self.user_name = user_name
        self.password = password
        self.ice_enabled = True
        self.mode = mode
        self.settle_time = settle_time
        self.incoming_call_config = incoming_call_config


class Account(pj.Account):
    def __init__(self, end_point: pj.Endpoint, config: MyAccountConfig, callback: call.CallCallback, ha_config: ha.HaConfig, make_default=False):
        pj.Account.__init__(self)
        self.config = config
        self.end_point = end_point
        self.callback = callback
        self.ha_config = ha_config
        self.make_default = make_default

    def create(self) -> None:
        account_config = pj.AccountConfig()
        account_config.idUri = self.config.id_uri
        account_config.regConfig.registrarUri = self.config.registrar_uri
        credentials = pj.AuthCredInfo('digest', self.config.realm, self.config.user_name, 0, self.config.password)
        account_config.sipConfig.authCreds.append(credentials)
        account_config.natConfig.iceEnabled = self.config.ice_enabled
        return pj.Account.create(self, account_config, self.make_default)

    def onRegState(self, prm) -> None:
        log(self.config.index, 'OnRegState: %s %s' % (prm.code, prm.reason))

    def onIncomingCall(self, prm) -> None:
        if not self.config:
            log(None, 'Error: No config set when onIncomingCall was called.')
            return
        menu = self.config.incoming_call_config.get('menu') if self.config.incoming_call_config else None
        allowed_numbers = self.config.incoming_call_config.get('allowed_numbers') if self.config.incoming_call_config else None
        blocked_numbers = self.config.incoming_call_config.get('blocked_numbers') if self.config.incoming_call_config else None
        answer_after = float(utils.convert_to_int(self.config.incoming_call_config.get('answer_after'), 0)) if self.config.incoming_call_config else 0.0
        incoming_call_instance = call.Call(self.end_point, self, prm.callId, None, menu, self.callback, self.ha_config, call.DEFAULT_TIMEOUT, None)
        ci = incoming_call_instance.get_call_info()
        answer_mode = self.get_sip_return_code(self.config.mode, allowed_numbers, blocked_numbers, ci["parsed_caller"])
        log(self.config.index, 'Incoming call  from  \'%s\' to \'%s\' (parsed: \'%s\')' % (ci["remote_uri"], ci["local_uri"], ci["parsed_caller"]))
        if allowed_numbers:
            log(self.config.index, 'Allowed numbers: %s' % allowed_numbers)
        if blocked_numbers:
            log(self.config.index, 'Blocked numbers: %s' % blocked_numbers)
        log(self.config.index, 'Answer mode: %s' % answer_mode.name)
        incoming_call_instance.accept(answer_mode, answer_after)
        ha.trigger_webhook(self.ha_config, {
            'event': 'incoming_call',
            'caller': ci["remote_uri"],
            'parsed_caller': ci["parsed_caller"],
            'sip_account': self.config.index,
        })

    def get_sip_return_code(
        self,
        mode: call.CallHandling,
        allowed_numbers: Optional[list[str]],
        blocked_numbers: Optional[list[str]],
        parsed_caller: Optional[str],
    ) -> call.CallHandling:
        if allowed_numbers and blocked_numbers:
            log(self.config.index, 'Error: cannot specify both of allowed and blocked numbers. Call won\'t be accepted!')
            return call.CallHandling.LISTEN
        if mode == call.CallHandling.ACCEPT and allowed_numbers:
            return call.CallHandling.ACCEPT if parsed_caller in allowed_numbers else call.CallHandling.LISTEN
        if mode == call.CallHandling.ACCEPT and blocked_numbers:
            return call.CallHandling.ACCEPT if parsed_caller not in blocked_numbers else call.CallHandling.LISTEN
        return mode


def create_account(end_point: pj.Endpoint, config: MyAccountConfig, callback: call.CallCallback, ha_config: ha.HaConfig, is_default: bool) -> Account:
    account = Account(end_point, config, callback, ha_config, is_default)
    account.create()
    return account

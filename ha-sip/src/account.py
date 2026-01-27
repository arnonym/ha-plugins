from __future__ import annotations

import re
from typing import Optional

import pjsua2 as pj

import call
import ha
import incoming_call
import utils
import webhook
from constants import DEFAULT_RING_TIMEOUT
from event_sender import EventSender
from log import log
from command_handler import CommandHandler
from options_global import GlobalOptions
from options_sip import SipOptions


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
        options: SipOptions,
        global_options: GlobalOptions,
    ):
        self.enabled = enabled
        self.index = index
        self.id_uri = id_uri
        self.registrar_uri = registrar_uri
        self.realm = realm
        self.user_name = user_name
        self.password = password
        self.mode = mode
        self.settle_time = settle_time
        self.incoming_call_config = incoming_call_config
        self.options = options
        self.global_options = global_options


class Account(pj.Account):
    def __init__(
        self,
        end_point: pj.Endpoint,
        config: MyAccountConfig,
        command_handler: CommandHandler,
        event_sender: EventSender,
        ha_config: ha.HaConfig,
        make_default=False
    ):
        pj.Account.__init__(self)
        self.config = config
        self.end_point = end_point
        self.command_handler = command_handler
        self.event_sender = event_sender
        self.ha_config = ha_config
        self.make_default = make_default

    def init(self) -> None:
        account_config = pj.AccountConfig()
        account_config.idUri = self.config.id_uri
        account_config.regConfig.registrarUri = self.config.registrar_uri
        credentials = pj.AuthCredInfo('digest', self.config.realm, self.config.user_name, 0, self.config.password)
        account_config.sipConfig.authCreds.append(credentials)
        account_config.natConfig.iceEnabled = self.config.options.enable_ice
        account_config.natConfig.contactRewriteUse = 1 if self.config.options.contact_rewrite_use else 0
        account_config.natConfig.viaRewriteUse = 1 if self.config.options.via_rewrite_use else 0
        account_config.natConfig.sdpNatRewriteUse = 1 if self.config.options.sdp_nat_rewrite_use else 0
        account_config.natConfig.sipOutboundUse = 1 if self.config.options.sip_outbound_use else 0
        if self.config.global_options.stun_server:
            account_config.natConfig.sipStunUse = pj.PJSUA_STUN_USE_DEFAULT if self.config.options.sip_stun_use else pj.PJSUA_STUN_USE_DISABLED
            account_config.natConfig.mediaStunUse = pj.PJSUA_STUN_USE_DEFAULT if self.config.options.media_stun_use else pj.PJSUA_STUN_USE_DISABLED
        if self.config.options.turn_server:
            account_config.natConfig.turnEnabled = True
            account_config.natConfig.turnServer = self.config.options.turn_server.server
            account_config.natConfig.turnConnType = self.config.options.turn_server.connection_type
            account_config.natConfig.turnUserName = self.config.options.turn_server.user
            account_config.natConfig.turnPasswordType = 0
            account_config.natConfig.turnPassword = self.config.options.turn_server.password
        if self.config.options.proxy:
            account_config.sipConfig.proxies.append(self.config.options.proxy)
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
        webhook_to_call = self.config.incoming_call_config.get('webhook_to_call') if self.config.incoming_call_config else None
        incoming_call_instance = call.Call(
            self.end_point, self, prm.callId, None, menu, self.command_handler, self.event_sender,
            self.ha_config, DEFAULT_RING_TIMEOUT, webhook_to_call,
        )
        ci = incoming_call_instance.get_call_info()
        answer_mode = self.get_sip_return_code(self.config.mode, allowed_numbers, blocked_numbers, ci['parsed_caller'])
        log(self.config.index, 'Incoming call  from  \'%s\' to \'%s\' (parsed: \'%s\')' % (ci['remote_uri'], ci['local_uri'], ci['parsed_caller']))
        if allowed_numbers:
            log(self.config.index, 'Allowed numbers: %s' % allowed_numbers)
        if blocked_numbers:
            log(self.config.index, 'Blocked numbers: %s' % blocked_numbers)
        log(self.config.index, 'Answer mode: %s' % answer_mode.name)
        incoming_call_instance.accept(answer_mode, answer_after)
        webhook.trigger_webhook(
            {'event': 'incoming_call'},
            ci,
            self.config.index,
            incoming_call_instance.callback_id,
            self.event_sender,
        )

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
            return call.CallHandling.ACCEPT if Account.is_number_in_list(parsed_caller, allowed_numbers) else call.CallHandling.LISTEN
        if mode == call.CallHandling.ACCEPT and blocked_numbers:
            return call.CallHandling.ACCEPT if not Account.is_number_in_list(parsed_caller, blocked_numbers) else call.CallHandling.LISTEN
        return mode

    @staticmethod
    def is_number_in_list(number: Optional[str], number_list: list[str]) -> bool:
        def map_to_regex(st: str) -> str:
            if st == '{*}':
                return '.*'
            if st == '{?}':
                return '.'
            return re.escape(st)
        if not number:
            return False
        for n in number_list:
            # split by {*} and {?} keeping delimiters
            n_split = re.split(r'(\{\*}|\{\?})', n)
            n_regex = '^' + ''.join(map(map_to_regex, n_split)) + '$'
            match = re.match(n_regex, number)
            if match:
                return True
        return False


def create_account(
    end_point: pj.Endpoint,
    config: MyAccountConfig,
    command_handler: CommandHandler,
    event_sender: EventSender,
    ha_config: ha.HaConfig,
    is_default: bool
) -> Account:
    account = Account(end_point, config, command_handler, event_sender, ha_config, is_default)
    account.init()
    return account

import argparse
from argparse import ArgumentParser

from pjsua2 import PJ_TURN_TP_TCP, PJ_TURN_TP_UDP, PJ_TURN_TP_TLS
from typing_extensions import Literal, Optional, Any

from log import log
from options import ALL_BOOL_VALUES, is_true


TurnConnectionType = Literal['tcp', 'udp', 'tls']


def turn_server_connection_type_to_int(connection_type: TurnConnectionType) -> Any:
    match connection_type:
        case 'tcp':
            return PJ_TURN_TP_TCP
        case 'udp':
            return PJ_TURN_TP_UDP
        case 'tls':
            return PJ_TURN_TP_TLS
        case _:
            raise ValueError(f'Unknown connection type: {connection_type}')


def int_to_turn_server_connection_type(raw: Any) -> TurnConnectionType:
    if raw == PJ_TURN_TP_TCP:
        return 'tcp'
    elif raw == PJ_TURN_TP_UDP:
        return 'udp'
    elif raw == PJ_TURN_TP_TLS:
        return 'tls'
    else:
        raise ValueError(f'Unknown connection type: {raw}')


class TurnServer:
    server: str
    connection_type: TurnConnectionType
    user: str
    password: str

    def __init__(self, server: str, connection_type: TurnConnectionType, user: str, password: str):
        self.server = server
        self.connection_type = turn_server_connection_type_to_int(connection_type)
        self.user = user
        self.password = password
        log(None, f'TURN server set to: {self.server}')
        log(None, f'TURN connection type set to: {connection_type}')
        log(None, f'TURN user set to: {self.user}')


class SipOptions:
    proxy: Optional[str]
    sip_stun_use: bool
    media_stun_use: bool
    contact_rewrite_use: bool
    via_rewrite_use: bool
    sdp_nat_rewrite_use: bool
    sip_outbound_use: bool

    def __init__(
        self,
        proxy: str,
        enable_ice: bool,
        sip_stun_use: bool,
        sip_media_use: bool,
        contact_rewrite_use: bool,
        via_rewrite_use: bool,
        sdp_nat_rewrite_use: bool,
        sip_outbound_use: bool,
        turn_server: Optional[TurnServer],
        account_index: int,
    ):
        self.proxy = proxy
        self.enable_ice = enable_ice
        self.sip_stun_use = sip_stun_use
        self.media_stun_use = sip_media_use
        self.turn_server = turn_server
        self.contact_rewrite_use = contact_rewrite_use
        self.via_rewrite_use = via_rewrite_use
        self.sdp_nat_rewrite_use = sdp_nat_rewrite_use
        self.sip_outbound_use = sip_outbound_use
        log(account_index, f'Proxy set to: {self.proxy}')
        log(account_index, f'ICE is enabled: {self.enable_ice}')
        log(account_index, f'TURN server is enabled: {self.turn_server is not None}')


def create_parser() -> ArgumentParser:
    parser = argparse.ArgumentParser(prog='sip_options')
    parser.add_argument(
        '--proxy',
        default=None,
        help='Proxy server to use for SIP (default: None)'
    )
    parser.add_argument(
        '--ice',
        choices=ALL_BOOL_VALUES,
        default='enabled',
        help='Enable or disable ICE (default: true)'
    )
    parser.add_argument(
        '--use-stun-for-sip',
        choices=ALL_BOOL_VALUES,
        default='enabled',
        help='Enable or disable STUN for sip (default: true)'
    )
    parser.add_argument(
        '--use-stun-for-media',
        choices=ALL_BOOL_VALUES,
        default='enabled',
        help='Enable or disable STUN for media (default: true)'
    )
    parser.add_argument(
        '--use-contact-rewrite',
        choices=ALL_BOOL_VALUES,
        default='enabled',
        help='Enable or disable contact rewrite for SIP (default: true)'
    )
    parser.add_argument(
        '--use-via-rewrite',
        choices=ALL_BOOL_VALUES,
        default='enabled',
        help='Enable or disable via rewrite for SIP (default: true)'
    )
    parser.add_argument(
        '--use-sdp-nat-rewrite',
        choices=ALL_BOOL_VALUES,
        default='enabled',
        help='Enable or disable SDP NAT rewrite for SIP (default: true)'
    )
    parser.add_argument(
        '--use-sip-outbound',
        choices=ALL_BOOL_VALUES,
        default='enabled',
        help='Enable or disable SIP outbound (default: true)'
    )
    parser.add_argument(
        '--turn-server',
        default=None,
        help='Set the TURN server to use for SIP (default: None)'
    )
    parser.add_argument(
        '--turn-connection-type',
        default='udp',
        choices=['tcp', 'udp', 'tls'],
        help='Set the TURN server connection protocol (default: udp)'
    )
    parser.add_argument(
        '--turn-user',
        default=None,
        help='Set the TURN user (default: None)'
    )
    parser.add_argument(
        '--turn-password',
        default=None,
        help='Set the TURN password (default: None)'
    )
    return parser


def parse_sip_options(raw: str, account_index: int = 0) -> SipOptions:
    raw_str = raw if raw else ''
    parser = create_parser()
    args = parser.parse_args(raw_str.split())
    if (
        args.turn_server and
        not args.turn_user and
        not args.turn_password
    ):
        log(account_index, 'Error: TURN server requires user and password. Disabling TURN server.')
    turn_server = TurnServer(args.turn_server, args.turn_connection_type, args.turn_user, args.turn_password) if args.turn_server else None
    return SipOptions(
        proxy=args.proxy,
        enable_ice=is_true(args.ice),
        sip_stun_use=is_true(args.use_stun_for_sip),
        sip_media_use=is_true(args.use_stun_for_media),
        contact_rewrite_use=is_true(args.use_contact_rewrite),
        via_rewrite_use= is_true(args.use_via_rewrite),
        sdp_nat_rewrite_use= is_true(args.use_sdp_nat_rewrite),
        sip_outbound_use= is_true(args.use_sip_outbound),
        turn_server=turn_server,
        account_index=account_index
    )

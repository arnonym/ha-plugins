import argparse
from typing import Optional

from log import log
from options import ALL_BOOL_VALUES, is_true


class GlobalOptions:
    stun_server: Optional[str] = None
    enable_udp: bool = True
    enable_tcp: bool = True
    enable_tls: bool = False
    tls_port: int = 5061
    debug_headers: bool = False

    def __init__(self, stun_server: Optional[str], enable_udp: bool, enable_tcp: bool, enable_tls: bool, tls_port: int, debug_headers: bool):
        self.stun_server = stun_server
        self.enable_udp = enable_udp
        self.enable_tcp = enable_tcp
        self.enable_tls = enable_tls
        self.tls_port = tls_port
        self.debug_headers = debug_headers
        log(None, f'STUN Server: {self.stun_server}')
        log(None, f'UDP Enabled: {self.enable_udp}')
        log(None, f'TCP Enabled: {self.enable_tcp}')
        log(None, f'TLS Enabled: {self.enable_tls}')
        log(None, f'TLS Port: {self.tls_port}')


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='global_options')
    parser.add_argument(
        '--stun-server',
        default=None,
        help='STUN server to use for NAT traversal (default: None)'
    )
    parser.add_argument(
        '--udp',
        choices=ALL_BOOL_VALUES,
        default='enabled',
        help='Enable or disable UDP transport (default: enabled)'
    )
    parser.add_argument(
        '--tcp',
        choices=ALL_BOOL_VALUES,
        default='enabled',
        help='Enable or disable TCP transport (default: enabled)'
    )
    parser.add_argument(
        '--tls',
        choices=ALL_BOOL_VALUES,
        default='disabled',
        help='Enable or disable TLS transport (default: disabled)'
    )
    parser.add_argument(
        '--tls-port',
        type=int,
        default=5061,
        help='Port to use for TLS transport (default: 5061)'
    )
    parser.add_argument(
        '--debug-headers',
        choices=ALL_BOOL_VALUES,
        default='disabled',
        help='Enable debug printing of extracted SIP headers (default: disabled)'
    )
    return parser

def parse_global_options(raw: Optional[str]) -> GlobalOptions:
    raw_str = raw if raw else ''
    parser = create_parser()
    args = parser.parse_args(raw_str.split())
    return GlobalOptions(
        stun_server=args.stun_server,
        enable_udp=is_true(args.udp),
        enable_tcp=is_true(args.tcp),
        enable_tls=is_true(args.tls),
        tls_port=args.tls_port,
        debug_headers=is_true(args.debug_headers),
    )

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
    enable_mqtt: bool = False
    mqtt_address: str = ''
    mqtt_port: int = 1883
    mqtt_username: str = ''
    mqtt_password: str = ''
    mqtt_topic: str = 'hasip/execute'
    mqtt_state_topic: str = 'hasip/state'

    def __init__(
        self,
        stun_server: Optional[str],
        enable_udp: bool,
        enable_tcp: bool,
        enable_tls: bool,
        tls_port: int,
        debug_headers: bool,
        enable_mqtt: bool,
        mqtt_address: str,
        mqtt_port: int,
        mqtt_username: str,
        mqtt_password: str,
        mqtt_topic: str,
        mqtt_state_topic: str,
    ):
        self.stun_server = stun_server
        self.enable_udp = enable_udp
        self.enable_tcp = enable_tcp
        self.enable_tls = enable_tls
        self.tls_port = tls_port
        self.debug_headers = debug_headers
        self.enable_mqtt = enable_mqtt
        self.mqtt_address = mqtt_address
        self.mqtt_port = mqtt_port
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        self.mqtt_topic = mqtt_topic
        self.mqtt_state_topic = mqtt_state_topic
        log(None, f'STUN Server: {self.stun_server}')
        log(None, f'UDP Enabled: {self.enable_udp}')
        log(None, f'TCP Enabled: {self.enable_tcp}')
        log(None, f'TLS Enabled: {self.enable_tls}')
        log(None, f'TLS Port: {self.tls_port}')
        log(None, f'MQTT Enabled: {self.enable_mqtt}')
        if self.enable_mqtt:
            log(None, f'MQTT Address: {self.mqtt_address}')
            log(None, f'MQTT Port: {self.mqtt_port}')
            log(None, f'MQTT Username: {self.mqtt_username}')
            log(None, f'MQTT Topic: {self.mqtt_topic}')
            log(None, f'MQTT State Topic: {self.mqtt_state_topic}')


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
    parser.add_argument(
        '--enable-mqtt',
        action='store_true',
        help='Enable MQTT as a command source (default: disabled)'
    )
    parser.add_argument(
        '--mqtt-address',
        default='',
        help='MQTT broker address (default: empty)'
    )
    parser.add_argument(
        '--mqtt-port',
        type=int,
        default=1883,
        help='MQTT broker port (default: 1883)'
    )
    parser.add_argument(
        '--mqtt-username',
        default='',
        help='MQTT broker username (default: empty)'
    )
    parser.add_argument(
        '--mqtt-password',
        default='',
        help='MQTT broker password (default: empty)'
    )
    parser.add_argument(
        '--mqtt-topic',
        default='hasip/execute',
        help='MQTT topic to subscribe to for incoming commands (default: hasip/execute)'
    )
    parser.add_argument(
        '--mqtt-state-topic',
        default='hasip/state',
        help='MQTT topic to publish call state events to (default: hasip/state)'
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
        enable_mqtt=args.enable_mqtt,
        mqtt_address=args.mqtt_address,
        mqtt_port=args.mqtt_port,
        mqtt_username=args.mqtt_username,
        mqtt_password=args.mqtt_password,
        mqtt_topic=args.mqtt_topic,
        mqtt_state_topic=args.mqtt_state_topic,
    )

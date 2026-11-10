#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["paho-mqtt>=2.1.0"]
# ///
"""Send ha-sip commands over MQTT and watch its call-state events.

Mirrors the JSON command schema documented in README.md's "Stand-alone mode"
section (the same payloads accepted via `mqtt.publish` from Home Assistant).

Usage:
    hasip_mqtt_cli.py --host 192.168.1.1 dial sip:**620@fritz.box --message "hi"
    hasip_mqtt_cli.py --host 192.168.1.1          # interactive REPL
"""

import argparse
import json
import os
import shlex
import sys

try:
    import readline  # noqa: F401  -- importing alone wires up input()'s line editing/history
except ImportError:
    readline = None  # e.g. Windows without pyreadline; REPL still works, just without history
import threading
import time

import paho.mqtt.client as mqtt

DEFAULT_PORT = 1883
DEFAULT_TOPIC = "hasip/execute"
DEFAULT_STATE_TOPIC = "hasip/state"
HISTORY_FILE = os.path.expanduser("~/.hasip_mqtt_cli_history")


def parse_kv_list(pairs):
    if not pairs:
        return None
    result = {}
    for pair in pairs:
        if "=" not in pair:
            raise argparse.ArgumentTypeError(f"expected EVENT=WEBHOOK_ID, got {pair!r}")
        key, _, value = pair.partition("=")
        result[key] = value
    return result


def build_menu(args):
    if getattr(args, "menu_json", None):
        try:
            return json.loads(args.menu_json)
        except json.JSONDecodeError as exc:
            raise argparse.ArgumentTypeError(f"--menu-json is not valid JSON: {exc}") from exc
    if getattr(args, "message", None) is None:
        return None
    menu = {"message": args.message}
    if getattr(args, "language", None):
        menu["language"] = args.language
    return menu


def strip_none(d):
    return {k: v for k, v in d.items() if v is not None}


# ---- payload builders, one per ha-sip command (field names match README.md) ----


def payload_dial(args):
    return strip_none(
        {
            "command": "dial",
            "number": args.number,
            "webhook_to_call": parse_kv_list(args.webhook_to_call),
            "ring_timeout": args.ring_timeout,
            "sip_account": args.sip_account,
            "menu": build_menu(args),
        }
    )


def payload_hangup(args):
    return strip_none({"command": "hangup", "number": args.number, "sip_code": args.sip_code})


def payload_send_dtmf(args):
    return strip_none(
        {
            "command": "send_dtmf",
            "number": args.number,
            "digits": args.digits,
            "method": args.method,
        }
    )


def payload_transfer(args):
    return {"command": "transfer", "number": args.number, "transfer_to": args.transfer_to}


def payload_bridge_audio(args):
    return {"command": "bridge_audio", "number": args.number, "bridge_to": args.bridge_to}


def payload_play_message(args):
    return strip_none(
        {
            "command": "play_message",
            "number": args.number,
            "message": args.message,
            "tts_language": args.tts_language,
            "cache_audio": args.cache_audio or None,
            "wait_for_audio_to_finish": args.wait_for_audio_to_finish or None,
            "post_action": args.post_action,
        }
    )


def payload_play_audio_file(args):
    return strip_none(
        {
            "command": "play_audio_file",
            "number": args.number,
            "audio_file": args.audio_file,
            "cache_audio": args.cache_audio or None,
            "wait_for_audio_to_finish": args.wait_for_audio_to_finish or None,
            "post_action": args.post_action,
        }
    )


def payload_stop_playback(args):
    return {"command": "stop_playback", "number": args.number}


def payload_start_recording(args):
    return {
        "command": "start_recording",
        "number": args.number,
        "recording_file": args.recording_file,
    }


def payload_stop_recording(args):
    return {"command": "stop_recording", "number": args.number}


def payload_answer(args):
    return strip_none(
        {
            "command": "answer",
            "number": args.number,
            "webhook_to_call": parse_kv_list(args.webhook_to_call),
            "menu": build_menu(args),
        }
    )


def payload_raw(args):
    try:
        payload = json.loads(args.json)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise argparse.ArgumentTypeError("raw payload must be a JSON object")
    return payload


def add_number_positional(sp):
    sp.add_argument("number", help="ha-sip number/internal_id identifying the call")


def add_command_subparsers(subparsers):
    p = subparsers.add_parser("dial", help="Start an outgoing call")
    add_number_positional(p)
    p.add_argument(
        "--webhook-to-call",
        action="append",
        metavar="EVENT=WEBHOOK_ID",
        help="repeatable; overrides the global webhook for a specific event",
    )
    p.add_argument("--ring-timeout", type=int, help="seconds to ring (default: 300)")
    p.add_argument("--sip-account", type=int)
    p.add_argument("--message", help="shorthand for menu.message (a plain TTS message, no DTMF choices)")
    p.add_argument("--language", help="TTS language for --message")
    p.add_argument("--menu-json", help="full menu JSON (as in README.md); overrides --message/--language")
    p.set_defaults(build=payload_dial)

    p = subparsers.add_parser("hangup", help="Hang up a call")
    add_number_positional(p)
    p.add_argument("--sip-code", type=int, help='e.g. 486 "Busy Here", 603 "Decline"')
    p.set_defaults(build=payload_hangup)

    p = subparsers.add_parser("send_dtmf", help="Send DTMF digits to an established call")
    add_number_positional(p)
    p.add_argument("--digits", required=True)
    p.add_argument("--method", choices=["in_band", "rfc2833", "sip_info"], default="in_band")
    p.set_defaults(build=payload_send_dtmf)

    p = subparsers.add_parser("transfer", help="Transfer a call to a different SIP URI")
    add_number_positional(p)
    p.add_argument("--transfer-to", required=True)
    p.set_defaults(build=payload_transfer)

    p = subparsers.add_parser("bridge_audio", help="Bridge the audio streams of two active calls")
    add_number_positional(p)
    p.add_argument("--bridge-to", required=True)
    p.set_defaults(build=payload_bridge_audio)

    p = subparsers.add_parser("play_message", help="Play a TTS message on an active call")
    add_number_positional(p)
    p.add_argument("--message", required=True)
    p.add_argument("--tts-language")
    p.add_argument("--cache-audio", action="store_true")
    p.add_argument("--wait-for-audio-to-finish", action="store_true")
    p.add_argument("--post-action", choices=["noop", "hangup"], default=None)
    p.set_defaults(build=payload_play_message)

    p = subparsers.add_parser("play_audio_file", help="Play an audio file on an active call")
    add_number_positional(p)
    p.add_argument("--audio-file", required=True, help="absolute path under /config or /media")
    p.add_argument("--cache-audio", action="store_true")
    p.add_argument("--wait-for-audio-to-finish", action="store_true")
    p.add_argument("--post-action", choices=["noop", "hangup"], default=None)
    p.set_defaults(build=payload_play_audio_file)

    p = subparsers.add_parser("stop_playback", help="Stop audio/message playback")
    add_number_positional(p)
    p.set_defaults(build=payload_stop_playback)

    p = subparsers.add_parser("start_recording", help="Start recording a call")
    add_number_positional(p)
    p.add_argument("--recording-file", required=True, help="absolute path, e.g. /config/www/call.wav")
    p.set_defaults(build=payload_start_recording)

    p = subparsers.add_parser("stop_recording", help="Stop recording a call")
    add_number_positional(p)
    p.set_defaults(build=payload_stop_recording)

    p = subparsers.add_parser("answer", help="Answer an incoming call")
    add_number_positional(p)
    p.add_argument("--webhook-to-call", action="append", metavar="EVENT=WEBHOOK_ID")
    p.add_argument("--message", help="shorthand for menu.message")
    p.add_argument("--language")
    p.add_argument("--menu-json", help="full menu JSON; overrides --message/--language")
    p.set_defaults(build=payload_answer)

    p = subparsers.add_parser("raw", help="Publish a raw JSON payload as-is")
    p.add_argument("json", help='e.g. \'{"command": "dial", "number": "sip:**620@fritz.box"}\'')
    p.set_defaults(build=payload_raw)


def build_top_parser():
    parser = argparse.ArgumentParser(
        prog="hasip_mqtt_cli",
        description="Send commands to ha-sip over MQTT, and watch its call-state events.",
    )
    parser.add_argument(
        "--host", default=os.environ.get("HASIP_MQTT_HOST"), help="MQTT broker host (env: HASIP_MQTT_HOST)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("HASIP_MQTT_PORT", DEFAULT_PORT)),
        help=f"MQTT broker port (env: HASIP_MQTT_PORT, default {DEFAULT_PORT})",
    )
    parser.add_argument("--username", default=os.environ.get("HASIP_MQTT_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("HASIP_MQTT_PASSWORD"))
    parser.add_argument(
        "--topic",
        default=os.environ.get("HASIP_MQTT_TOPIC", DEFAULT_TOPIC),
        help=f"command topic (env: HASIP_MQTT_TOPIC, default {DEFAULT_TOPIC})",
    )
    parser.add_argument(
        "--state-topic",
        default=os.environ.get("HASIP_MQTT_STATE_TOPIC", DEFAULT_STATE_TOPIC),
        help=f"state topic to watch (env: HASIP_MQTT_STATE_TOPIC, default {DEFAULT_STATE_TOPIC})",
    )
    parser.add_argument(
        "--listen",
        type=float,
        metavar="SECONDS",
        help="one-shot mode only: after publishing, keep watching --state-topic for SECONDS before exiting",
    )

    subparsers = parser.add_subparsers(dest="command_name")
    subparsers.add_parser("interactive", help="Start an interactive REPL (default if no command is given)")
    add_command_subparsers(subparsers)
    return parser


def build_repl_parser():
    parser = argparse.ArgumentParser(prog="", add_help=False)
    subparsers = parser.add_subparsers(dest="command_name")
    add_command_subparsers(subparsers)
    return parser


class MqttSession:
    def __init__(self, args):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if args.username:
            self.client.username_pw_set(args.username, args.password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.host = args.host
        self.port = args.port
        self.state_topic = args.state_topic
        self._connected = threading.Event()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            self._connected.set()
        else:
            print(f"error: MQTT connect failed: {reason_code}", file=sys.stderr)

    def _on_message(self, client, userdata, msg):
        try:
            pretty = json.dumps(json.loads(msg.payload.decode("utf-8")), indent=2)
        except (UnicodeDecodeError, json.JSONDecodeError):
            pretty = msg.payload.decode("utf-8", errors="replace")
        print(f"\n<- [{msg.topic}] {pretty}")

    def connect(self, subscribe_state):
        if not self.host:
            print("error: --host (or HASIP_MQTT_HOST) is required", file=sys.stderr)
            sys.exit(1)
        self.client.connect(self.host, self.port)
        self.client.loop_start()
        if not self._connected.wait(timeout=10):
            print(f"error: could not connect to {self.host}:{self.port} within 10s", file=sys.stderr)
            sys.exit(1)
        if subscribe_state:
            self.client.subscribe(self.state_topic)

    def publish(self, topic, payload):
        info = self.client.publish(topic, json.dumps(payload), qos=1)
        info.wait_for_publish(timeout=10)
        print(f"-> [{topic}] {json.dumps(payload)}")

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


def run_one_shot(args, session):
    try:
        payload = args.build(args)
    except argparse.ArgumentTypeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    session.connect(subscribe_state=bool(args.listen))
    session.publish(args.topic, payload)
    if args.listen:
        time.sleep(args.listen)
    session.close()


def run_interactive(args, session):
    session.connect(subscribe_state=True)
    print(
        f"Connected to {args.host}:{args.port}. Publishing to '{args.topic}', "
        f"watching '{args.state_topic}'. Type 'help' for commands, 'exit' to quit."
    )
    repl_parser = build_repl_parser()
    if readline:
        readline.set_history_length(1000)
        try:
            readline.read_history_file(HISTORY_FILE)
        except OSError:
            pass
    try:
        while True:
            try:
                line = input("hasip> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if line in ("exit", "quit"):
                break
            if line in ("help", "?"):
                repl_parser.print_help()
                continue
            try:
                repl_args = repl_parser.parse_args(shlex.split(line))
            except SystemExit:
                continue
            if repl_args.command_name is None:
                continue
            try:
                payload = repl_args.build(repl_args)
            except argparse.ArgumentTypeError as exc:
                print(f"error: {exc}", file=sys.stderr)
                continue
            session.publish(args.topic, payload)
    finally:
        session.close()
        if readline:
            try:
                readline.write_history_file(HISTORY_FILE)
            except OSError:
                pass


def main(argv=None):
    args = build_top_parser().parse_args(argv)
    session = MqttSession(args)
    if args.command_name in (None, "interactive"):
        run_interactive(args, session)
    else:
        run_one_shot(args, session)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

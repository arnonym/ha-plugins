from __future__ import annotations

import collections.abc
import sys
import os
from typing import Optional

import pjsua2 as pj

import account
import call
import command_client
import ha
import state
import utils
from call_state_change import CallStateChange
from constants import DEFAULT_RING_TIMEOUT
from event_sender import EventSender
from log import log


class CommandHandler(object):
    def __init__(
        self,
        end_point: pj.Endpoint,
        sip_accounts: dict[int, account.Account],
        call_state: state.State,
        ha_config: ha.HaConfig,
        event_sender: EventSender,
    ):
        self.end_point = end_point
        self.sip_accounts = sip_accounts
        self.ha_config = ha_config
        self.event_sender = event_sender
        self.call_state = call_state

    def get_call_from_state(self, caller_id: str) -> Optional[call.Call]:
        return self.call_state.get_call(caller_id)

    def get_call_from_state_unsafe(self, caller_id: str) -> call.Call:
        return self.call_state.get_call_unsafe(caller_id)

    def is_active(self, caller_id: str) -> bool:
        return self.call_state.is_active(caller_id)

    def on_state_change(self, state_change: CallStateChange, caller_id: str, new_call: call.Call) -> None:
        self.call_state.on_state_change(state_change, caller_id, new_call)

    def handle_command(self, command: command_client.Command, from_call: Optional[call.Call]) -> None:
        if not isinstance(command, collections.abc.Mapping):
            log(None, 'Error: Not an object: %s' % command)
            return
        verb = command.get('command')
        number_unknown_type = command.get('number')
        number = str(number_unknown_type) if number_unknown_type is not None else None
        match verb:
            case 'call_service' | None:
                domain = command.get('domain')
                service = command.get('service')
                entity_id = command.get('entity_id')
                service_data = command.get('service_data')
                if (not domain) or (not service) or (not entity_id):
                    log(None, 'Error: one of domain, service or entity_id was not provided')
                    return
                log(None, 'Calling home assistant service on domain %s service %s with entity %s' % (domain, service, entity_id))
                try:
                    ha.call_service(self.ha_config, domain, service, entity_id, service_data)
                except Exception as e:
                    log(None, 'Error calling home-assistant service: %s' % e)
            case 'dial':
                if not number:
                    log(None, 'Error: Missing number for command "dial"')
                    return
                log(None, 'Got "dial" command for %s' % number)
                if self.is_active(number):
                    log(None, 'Warning: call already in progress: %s' % number)
                    return
                menu = command.get('menu')
                ring_timeout = utils.convert_to_float(command.get('ring_timeout'), DEFAULT_RING_TIMEOUT)
                sip_account_number = utils.convert_to_int(command.get('sip_account'), -1)
                webhooks = command.get('webhook_to_call')
                sip_account = self.sip_accounts.get(sip_account_number, next(iter(self.sip_accounts.values())))
                call.make_call(self.end_point, sip_account, number, menu, self, self.event_sender, self.ha_config, ring_timeout, webhooks)
            case 'hangup':
                if not number:
                    log(None, 'Error: Missing number for command "hangup"')
                    return
                log(None, 'Got "hangup" command for %s' % number)
                if not self.is_active(number):
                    self.call_not_in_progress_error(number)
                    return
                current_call = self.get_call_from_state_unsafe(number)
                current_call.hangup_call()
            case 'answer':
                if not number:
                    log(None, 'Error: Missing number for command "answer"')
                    return
                log(None, 'Got "answer" command for %s' % number)
                if not self.is_active(number):
                    self.call_not_in_progress_error(number)
                    return
                menu = command.get('menu')
                webhooks = command.get('webhook_to_call')
                current_call = self.get_call_from_state_unsafe(number)
                current_call.answer_call(menu, webhooks)
            case 'transfer':
                if not number:
                    log(None, 'Error: Missing number for command "transfer"')
                    return
                transfer_to = command.get('transfer_to')
                if not transfer_to:
                    log(None, 'Error: Missing transfer_to for command "transfer_to"')
                    return
                if not self.is_active(number):
                    self.call_not_in_progress_error(number)
                    return
                current_call = self.get_call_from_state_unsafe(number)
                current_call.transfer(transfer_to)
            case 'bridge_audio':
                if not number:
                    log(None, 'Error: Missing number for command "bridge_audio"')
                    return
                bridge_to = command.get('bridge_to')
                if not bridge_to:
                    log(None, 'Error: Missing bridge_to for command "bridge_audio"')
                    return
                call_one = from_call if number == 'self' else self.get_call_from_state(number)
                call_two = from_call if bridge_to == 'self' else self.get_call_from_state(bridge_to)
                if not call_one:
                    self.call_not_in_progress_error(number)
                    return
                if not call_two:
                    self.call_not_in_progress_error(bridge_to)
                    return
                call_one.bridge_audio(call_two)
            case 'send_dtmf':
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
                if not self.is_active(number):
                    self.call_not_in_progress_error(number)
                    return
                current_call = self.get_call_from_state_unsafe(number)
                current_call.send_dtmf(digits, method)
            case 'play_audio_file':
                if not number:
                    log(None, 'Error: Missing number for command "play_audio_file"')
                    return
                if not self.is_active(number):
                    self.call_not_in_progress_error(number)
                    return
                current_call = self.get_call_from_state_unsafe(number)
                audio_file = command.get('audio_file')
                if not audio_file:
                    log(None, 'Error: Missing parameter "audio_file" for command "play_audio_file"')
                    return
                cache_audio = command.get('cache_audio') or False
                wait_for_audio_to_finish = command.get('wait_for_audio_to_finish') or False
                current_call.play_audio_file(audio_file, cache_audio, wait_for_audio_to_finish)
            case 'play_message':
                if not number:
                    log(None, 'Error: Missing number for command "play_message"')
                    return
                if not self.is_active(number):
                    self.call_not_in_progress_error(number)
                    return
                current_call = self.get_call_from_state_unsafe(number)
                message = command.get('message')
                if not message:
                    log(None, 'Error: Missing parameter "message" for command "play_message"')
                    return
                tts_language = command.get('tts_language') or self.ha_config.tts_config['language']
                cache_audio = command.get('cache_audio') or False
                wait_for_audio_to_finish = command.get('wait_for_audio_to_finish') or False
                current_call.play_message(message, tts_language, cache_audio, wait_for_audio_to_finish)
            case 'stop_playback':
                if not number:
                    log(None, 'Error: Missing number for command "stop_playback"')
                    return
                if not self.is_active(number):
                    self.call_not_in_progress_error(number)
                    return
                current_call = self.get_call_from_state_unsafe(number)
                current_call.stop_playback()
            case 'start_recording':
                if not number:
                    log(None, 'Error: Missing number for command "start_recording"')
                    return
                if not self.is_active(number):
                    self.call_not_in_progress_error(number)
                    return
                current_call = self.get_call_from_state_unsafe(number)
                recording_file = command.get('recording_file')
                if not recording_file or not os.path.isabs(recording_file):
                    log(None, 'Error: Missing recording_file or path not absolute for command "start_recording"')
                    return
                current_call.start_recording(recording_file)
            case 'stop_recording':
                if not number:
                    log(None, 'Error: Missing number for command "stop_recording"')
                    return
                if not self.is_active(number):
                    self.call_not_in_progress_error(number)
                    return
                current_call = self.get_call_from_state_unsafe(number)
                current_call.stop_recording()
            case 'state':
                self.call_state.output()
            case 'quit':
                log(None, 'Quit.')
                self.end_point.libDestroy()
                sys.exit(0)
            case _:
                log(None, 'Error: Unknown command: %s' % verb)

    def call_not_in_progress_error(self, number: str):
        log(None, 'Warning: call not in progress: %s' % number)
        self.call_state.output()

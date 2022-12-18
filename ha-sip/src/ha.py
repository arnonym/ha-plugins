from __future__ import annotations

import os
from typing import Union, Optional, Dict

import requests
from typing_extensions import TypedDict, Literal

import constants
import audio


class IncomingCallEvent(TypedDict):
    event: Literal['incoming_call']
    caller: str
    parsed_caller: Optional[str]


class CallEstablishedEvent(TypedDict):
    event: Literal['call_established']
    caller: str
    parsed_caller: Optional[str]


class CallDisconnectedEvent(TypedDict):
    event: Literal['call_disconnected']
    caller: str
    parsed_caller: Optional[str]


class EnteredMenuEvent(TypedDict):
    event: Literal['entered_menu']
    caller: str
    parsed_caller: Optional[str]
    menu_id: str


class DtmfDigitEvent(TypedDict):
    event: Literal['dtmf_digit']
    caller: str
    parsed_caller: Optional[str]
    digit: str


class Timeout(TypedDict):
    event: Literal['timeout']


WebhookEvent = Union[IncomingCallEvent, CallEstablishedEvent, CallDisconnectedEvent, EnteredMenuEvent, DtmfDigitEvent, Timeout]


class HaConfig(object):
    def __init__(self, base_url: str, token: str, tts_engine: str, tts_language: str, webhook_id: str):
        self.base_url = base_url
        self.token = token
        self.tts_engine = tts_engine
        self.tts_language = tts_language or 'en'
        self.webhook_id = webhook_id

    def create_headers(self) -> Dict[str, str]:
        return {
            'Authorization': 'Bearer ' + self.token,
            'content-type': 'application/json',
        }

    def get_tts_url(self) -> str:
        return self.base_url + '/tts_get_url'

    def get_service_url(self, domain: str, service: str) -> str:
        return self.base_url + '/services/' + domain + '/' + service

    def get_webhook_url(self, webhook_id: str) -> str:
        return self.base_url + '/webhook/' + webhook_id


def create_and_get_tts(ha_config: HaConfig, message: str, language: str) -> tuple[str, bool]:
    """
    Generates a .wav file for a given message
    :param ha_config: home assistant config
    :param message: the message passed to the TTS engine
    :param language: language the message is in
    :return: the file name of the .wav-file and if it must be deleted afterwards
    """
    headers = ha_config.create_headers()
    create_response = requests.post(ha_config.get_tts_url(), json={'platform': ha_config.tts_engine, 'message': message, 'language': language}, headers=headers)
    if create_response.status_code != 200:
        print('| Error getting tts file', create_response.status_code, create_response.content)
        error_file_name = os.path.join(constants.ROOT_PATH, 'sound/answer.wav')
        return error_file_name, False
    response_deserialized = create_response.json()
    mp3_url = response_deserialized['url']
    mp3_response = requests.get(mp3_url, headers=headers)
    wav_file_name = audio.convert_mp3_stream_to_wav(mp3_response.content)
    if not wav_file_name:
        print('| Error converting to wav:', wav_file_name)
        error_file_name = os.path.join(constants.ROOT_PATH, 'sound/answer.wav')
        return error_file_name, False
    return wav_file_name, True


def call_service(ha_config: HaConfig, domain: str, service: str, entity_id: str) -> None:
    headers = ha_config.create_headers()
    service_response = requests.post(ha_config.get_service_url(domain, service), json={'entity_id': entity_id}, headers=headers)
    print('| Service response', service_response.status_code, service_response.content)


def trigger_webhook(ha_config: HaConfig, event: WebhookEvent, overwrite_webhook_id: Optional[str] = None) -> None:
    webhook_id = overwrite_webhook_id or ha_config.webhook_id
    if not webhook_id:
        print('| Warning: No webhook defined.')
        return
    print('| Calling webhook', webhook_id, 'with data', event)
    headers = ha_config.create_headers()
    service_response = requests.post(ha_config.get_webhook_url(webhook_id), json=event, headers=headers)
    print('| Webhook response', service_response.status_code, service_response.content)

from __future__ import annotations

import os
import json
from typing import Union, Optional, Dict, Any
from typing_extensions import TypedDict, Literal

import requests
import websockets

import constants
import audio
import utils
from log import log


class WebhookBaseFields(TypedDict):
    caller: str
    parsed_caller: Optional[str]
    parsed_called: Optional[str]
    sip_account: int
    call_id: Optional[str]
    internal_id: str
    headers: Dict[str, Optional[str]]


class IncomingCallEvent(TypedDict):
    event: Literal['incoming_call']


class CallEstablishedEvent(TypedDict):
    event: Literal['call_established']


class CallDisconnectedEvent(TypedDict):
    event: Literal['call_disconnected']


class EnteredMenuEvent(TypedDict):
    event: Literal['entered_menu']
    menu_id: str


class DtmfDigitEvent(TypedDict):
    event: Literal['dtmf_digit']
    digit: str


class Timeout(TypedDict):
    event: Literal['timeout']
    menu_id: Optional[str]


class RingTimeout(TypedDict):
    event: Literal['ring_timeout']


class PlaybackDoneAudioFile(TypedDict):
    event: Literal['playback_done']
    type: Literal['audio_file']
    audio_file: str


class PlaybackDoneMessage(TypedDict):
    event: Literal['playback_done']
    type: Literal['message']
    message: str


class RecordingStarted(TypedDict):
    event: Literal['recording_started']
    recording_file: str


class RecordingStopped(TypedDict):
    event: Literal['recording_stopped']
    recording_file: str


WebhookEvent = Union[
    IncomingCallEvent,
    CallEstablishedEvent,
    CallDisconnectedEvent,
    EnteredMenuEvent,
    DtmfDigitEvent,
    Timeout,
    RingTimeout,
    PlaybackDoneAudioFile,
    PlaybackDoneMessage,
    RecordingStarted,
    RecordingStopped
]


CompleteWebhookEvent = Any


class CurrentPlaybackMessage(TypedDict):
    type: Literal['message']
    message: str


class CurrentPlaybackAudioFile(TypedDict):
    type: Literal['audio_file']
    audio_file: str


CurrentPlayback = Union[CurrentPlaybackMessage, CurrentPlaybackAudioFile]


class TtsConfigFromEnv(TypedDict):
    platform: Optional[str]
    engine_id: Optional[str]
    language: str
    voice: Optional[str]
    debug_print: Optional[str]


class TtsConfig(TypedDict):
    platform: Optional[str]
    engine_id: Optional[str]
    language: str
    voice: Optional[str]
    debug_print: bool


class HaConfig(object):
    def __init__(self, base_url: str, websocket_url: str, token: str, tts_config: TtsConfigFromEnv, webhook_id: str, cache_dir: Optional[str]):
        self.base_url = base_url
        self.websocket_url = websocket_url
        self.token = token
        self.tts_config: TtsConfig = {
            'platform': tts_config['platform'],
            'engine_id': tts_config['engine_id'],
            'language': tts_config['language'] or 'en',
            'voice': tts_config['voice'] or None,
            'debug_print': (tts_config['debug_print'] or '').lower() == 'true',
        }
        if not self.tts_config['engine_id'] and not self.tts_config['platform']:
            log(None, 'Warning: No TTS engine defined. Must be either specify engine_id or platform.')
        if self.tts_config['engine_id'] and self.tts_config['platform']:
            log(None, 'Warning: Both engine_id and platform defined. Using engine_id.')
        if self.tts_config['engine_id']:
            log(None, f"TTS: Using engine {self.tts_config['engine_id']} with language {self.tts_config['language']} with voice {self.tts_config['voice']}")
        elif self.tts_config['platform']:
            log(None, f"TTS: Using platform {self.tts_config['platform']} with language {self.tts_config['language']} with voice {self.tts_config['voice']}")
        self.webhook_id = webhook_id
        self.cache_dir = cache_dir

    def create_headers(self) -> Dict[str, str]:
        return {
            'Authorization': 'Bearer ' + self.token,
            'content-type': 'application/json',
        }

    def get_tts_url(self) -> str:
        return self.base_url + '/tts_get_url'

    def get_template_url(self) -> str:
        return self.base_url + '/template'

    def get_service_url(self, domain: str, service: str) -> str:
        return self.base_url + '/services/' + domain + '/' + service

    def get_webhook_url(self, webhook_id: str) -> str:
        return self.base_url + '/webhook/' + webhook_id


def create_and_get_tts(ha_config: HaConfig, message: str, language: str) -> tuple[str, bool, bool]:
    """
    Generates a .wav file for a given message
    :param ha_config: home assistant config
    :param message: the message passed to the TTS engine
    :param language: language the message is in
    :return: the file name of the .wav-file, if it must be deleted afterwards, and if it was successful
    """
    error_file_name = os.path.join(constants.ROOT_PATH, 'sound/error.wav')
    headers = ha_config.create_headers()
    engine_or_platform = { 'engine_id': ha_config.tts_config['engine_id'] } if ha_config.tts_config['engine_id'] else { 'platform': ha_config.tts_config['platform']}
    message_and_language = { 'message': message, 'language': language}
    options = { 'options': { 'voice': ha_config.tts_config['voice'] } } if ha_config.tts_config['voice'] else {}
    payload = options | message_and_language | engine_or_platform
    if ha_config.tts_config['debug_print']:
        log(None, f'TTS payload: {payload!r}')
    create_response = requests.post(ha_config.get_tts_url(), json=payload, headers=headers)
    if create_response.status_code != 200:
        log(None, f'Error getting tts file {create_response.status_code!r} {create_response.content!r}')
        error_file_name = os.path.join(constants.ROOT_PATH, 'sound/error.wav')
        return error_file_name, False, False
    response_deserialized = create_response.json()
    tts_url = response_deserialized['url']
    log(None, f'Getting audio from "{tts_url}"')
    try:
        tts_response = requests.get(tts_url, headers=headers)
    except Exception as e:
        log(None, f'Error getting tts audio: {e}')
        return error_file_name, False, False
    file_format = audio.audio_format_from_filename(tts_url)
    if not file_format:
        log(None, f'Error getting audio format from filename: {tts_url}')
        return error_file_name, False, False
    wav_file_name = audio.convert_audio_stream_to_wav_file(tts_response.content, file_format)
    if not wav_file_name:
        log(None, f'Error converting to wav: {wav_file_name}')
        return error_file_name, False, False
    return wav_file_name, True, True


def render_template(ha_config: HaConfig, text: str) -> str:
    log(None, f'Rendering template: {text}')
    headers = ha_config.create_headers()
    template_response = requests.post(ha_config.get_template_url(), json={'template': text}, headers=headers)
    log(None, f'Template response {template_response.status_code!r} {template_response.content!r}')
    return template_response.text if template_response.ok else text


def call_service(ha_config: HaConfig, domain: str, service: str, entity_id: Optional[str], service_data: Optional[Dict[str, Any]]) -> None:
    headers = ha_config.create_headers()
    payload: Dict[str, Any] = {}
    if entity_id:
        payload.update({'entity_id': entity_id})
    if service_data:
        payload.update(service_data)
    service_response = requests.post(ha_config.get_service_url(domain, service), json=payload, headers=headers)
    log(None, f'Service response {service_response.status_code!r} {service_response.content!r}')


def trigger_webhook(ha_config: HaConfig, event: CompleteWebhookEvent, overwrite_webhook_id: Optional[str] = None) -> None:
    webhook_id = overwrite_webhook_id or ha_config.webhook_id
    if not webhook_id:
        log(None, 'Warning: No webhook defined.')
        return
    log(None, f'Calling webhook {webhook_id} with data {event}')
    headers = ha_config.create_headers()
    service_response = requests.post(ha_config.get_webhook_url(webhook_id), json=event, headers=headers)
    log(None, f'Webhook response {service_response.status_code!r} {service_response.content!r}')


async def print_tts_providers(ha_config: HaConfig) -> None:
    ws_url = ha_config.websocket_url
    log(None, f"Connecting to websocket under URL '{ws_url}'")
    async with websockets.connect(ws_url) as websocket:
        await websocket.recv()
        # Send auth
        await websocket.send(json.dumps({
            "type": "auth",
            "access_token": ha_config.token
        }))
        auth_response = json.loads(await websocket.recv())
        if auth_response.get("type") != "auth_ok":
            raise Exception("Authentication failed!")
        # Request TTS providers
        await websocket.send(json.dumps({
            "id": 1,
            "type": "tts/engine/list"
        }))
        response = json.loads(await websocket.recv())
        if not response.get("success", False):
            raise Exception(f"tts/engine/list request failed: {response}")
        providers = response["result"]['providers']
        log(None, "Available TTS providers:")
        for provider in providers:
            chunked_langs = utils.chunks(provider['supported_languages'], 10)
            log(None, f"  {provider['engine_id']}:")
            log(None, "    Languages:")
            for langs in chunked_langs:
                log(None, f"      {', '.join(langs)}")
        engine_from_config = ha_config.tts_config['engine_id'] or ha_config.tts_config['platform']
        provider_for_config = next((provider for provider in providers if provider['engine_id'] == engine_from_config), None)
        if not provider_for_config:
            log(None, f"  Warning: No TTS provider found for engine {engine_from_config}")
            return
        has_language = ha_config.tts_config['language'] in provider_for_config['supported_languages']
        if not has_language:
            log(None, f"  Warning: Language {ha_config.tts_config['language']} not supported by TTS provider {engine_from_config}")
            return
        log(None, f"  Good news: TTS provider {engine_from_config} was found and supports language {ha_config.tts_config['language']}")
        await websocket.send(json.dumps({
            "id": 2,
            "type": "tts/engine/voices",
            "engine_id": engine_from_config,
            "language": ha_config.tts_config['language']
        }))
        response = json.loads(await websocket.recv())
        if not response.get("success", False):
            raise Exception(f"tts/engine/voices request failed: {response}")
        voices = response["result"]["voices"]
        if voices:
            log(None, "  Voices for current engine and language:")
            for voice in voices:
                log(None, f"      {voice['voice_id']}: {voice['name']}")
        else:
            log(None, "  Current engine doesn't support voices")

import pydub

import requests
import os
import constants
import tempfile


class HaConfig(object):
    def __init__(self, base_url: str, token: str, tts_engine: str, tts_language: str, webhook_id: str):
        self.base_url = base_url
        self.token = token
        self.tts_engine = tts_engine
        self.tts_language = tts_language or "en"
        self.webhook_id = webhook_id

    def create_headers(self):
        return {
            "Authorization": "Bearer " + self.token,
            "content-type": "application/json",
        }

    def get_tts_url(self) -> str:
        return self.base_url + "/tts_get_url"

    def get_service_url(self, domain: str, service: str) -> str:
        return self.base_url + '/services/' + domain + '/' + service

    def get_webhook_url(self) -> str:
        return self.base_url + "/webhook/" + self.webhook_id


def convert_mp3_to_wav(stream: bytes) -> str:
    mp3_file_handler = tempfile.NamedTemporaryFile()
    mp3_file_handler.write(stream)
    mp3_file_handler.flush()
    sound = pydub.AudioSegment.from_mp3(mp3_file_handler.name)
    wave_file_handler = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sound.export(wave_file_handler.name, format="wav")
    return wave_file_handler.name


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
    return convert_mp3_to_wav(mp3_response.content), True


def call_service(ha_config: HaConfig, domain: str, service: str, entity_id: str) -> None:
    headers = ha_config.create_headers()
    service_response = requests.post(ha_config.get_service_url(domain, service), json={'entity_id': entity_id}, headers=headers)
    print('| Service response', service_response.status_code, service_response.content)


def trigger_webhook(ha_config: HaConfig, caller: str) -> None:
    if not ha_config.webhook_id:
        print('| Warning: No webhook defined.')
        return
    webhook_data = {'caller': caller}
    print("| Calling webhook", ha_config.webhook_id, "with data", webhook_data)
    headers = ha_config.create_headers()
    service_response = requests.post(ha_config.get_webhook_url(), json=webhook_data, headers=headers)
    print('| Webhook response', service_response.status_code, service_response.content)

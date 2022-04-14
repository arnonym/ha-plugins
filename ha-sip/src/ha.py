import pydub

from config import *
import requests
import os
import constants
import tempfile


def create_headers():
    return {
        "Authorization": "Bearer " + HA_TOKEN,
        "content-type": "application/json",
    }


def convert_mp3_to_wav(stream: bytes) -> str:
    mp3_file_handler = tempfile.NamedTemporaryFile()
    mp3_file_handler.write(stream)
    mp3_file_handler.flush()
    sound = pydub.AudioSegment.from_mp3(mp3_file_handler.name)
    wave_file_handler = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sound.export(wave_file_handler.name, format="wav")
    return wave_file_handler.name


def create_and_get_tts(message: str) -> tuple[str, bool]:
    """
    Generates a .wav file for a given message
    :param message: the message passed to the TTS engine
    :return: the file name of the .wav-file and if it must be deleted afterwards
    """
    headers = create_headers()
    create_response = requests.post(HA_BASE_URL + "/tts_get_url", json={'platform': TTS_PLATFORM, 'message': message}, headers=headers)
    if create_response.status_code != 200:
        print('| Error getting tts file', create_response.status_code, create_response.content)
        error_file_name = os.path.join(constants.ROOT_PATH, 'sound/answer.wav')
        return error_file_name, False
    response_deserialized = create_response.json()
    mp3_url = response_deserialized['url']
    mp3_response = requests.get(mp3_url, headers=headers)
    return convert_mp3_to_wav(mp3_response.content), True


def call_service(domain: str, service: str, entity_id: str) -> None:
    headers = create_headers()
    service_response = requests.post(HA_BASE_URL + '/services/' + domain + '/' + service, json={'entity_id': entity_id}, headers=headers)
    print('| Service response', service_response.status_code, service_response.content)

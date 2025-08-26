from __future__ import annotations

import os
import tempfile
from typing import Optional

import pydub

from log import log


def convert_audio_to_wav(audio_file_name: str) -> Optional[str]:
    def get_audio_segment(file_name: str) -> Optional[pydub.AudioSegment]:
        _, file_extension = os.path.splitext(file_name)
        if file_extension == '.mp3':
            return pydub.AudioSegment.from_mp3(file_name)
        if file_extension == '.ogg':
            return pydub.AudioSegment.from_ogg(file_name)
        if file_extension == '.wav':
            return pydub.AudioSegment.from_wav(file_name)
        return None
    if not os.path.exists(audio_file_name):
        print('Error: could not find audio file:', audio_file_name)
        return None
    try:
        wave_file_handler = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        audio_segment = get_audio_segment(audio_file_name)
        if not audio_segment:
            log(None, f'Error: could not figure out file format (.mp3, .ogg, .wav is supported): {audio_file_name}')
            return None
        audio_segment.export(wave_file_handler.name, format='wav')
        return wave_file_handler.name
    except Exception as e:
        log(None, f'Error converting audio file to wav: {e}')
        return None


def convert_mp3_stream_to_wav_file(stream: bytes) -> Optional[str]:
    mp3_file_handler = tempfile.NamedTemporaryFile(suffix='.mp3')
    mp3_file_handler.write(stream)
    return convert_audio_to_wav(mp3_file_handler.name)


def write_wav_stream_to_wav_file(stream: bytes) -> Optional[str]:
    wav_file_handler = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    wav_file_handler.write(stream)
    return wav_file_handler.name

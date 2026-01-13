from __future__ import annotations

import subprocess
import tempfile
from typing import Optional
from enum import Enum
from pathlib import Path

from log import log


class AudioInputFormat(str, Enum):
    MP3 = "mp3"
    WAV = "wav"
    OGG = "ogg"
    FLAC = "flac"


def convert_audio_stream_to_wav_file(
    stream: bytes,
    input_format: AudioInputFormat,
) -> Optional[str]:
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel", "error",
                    "-f", input_format,
                    "-i", "pipe:0",
                    wav_file.name,
                ],
                input=stream,
                stderr=subprocess.PIPE,
                check=True,
            )
            return wav_file.name
    except subprocess.CalledProcessError as e:
        log(None, f"ffmpeg error: {e.stderr.decode(errors='ignore')}")
        return None


def audio_format_from_filename(filename: str) -> Optional[AudioInputFormat]:
    suffix = Path(filename).suffix.lower().lstrip(".")
    try:
        return AudioInputFormat(suffix)
    except ValueError:
        return None

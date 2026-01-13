import unittest

import audio

class AudioTest(unittest.TestCase):
    def test_file_name_to_format(self):
        self.assertEqual(audio.audio_format_from_filename('https://localhost:8080/something/file.mp3'), audio.AudioInputFormat.MP3)
        self.assertEqual(audio.audio_format_from_filename('http://localhost:8080/something/file.wav'), audio.AudioInputFormat.WAV)
        self.assertEqual(audio.audio_format_from_filename('https://localhost:8080/something/file.abc'), None)

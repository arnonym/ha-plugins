from typing import Callable

import pjsua2 as pj


PlaybackDoneCallback = Callable[[], None]


class Player(pj.AudioMediaPlayer):
    def __init__(self, playback_done_callback: PlaybackDoneCallback):
        self.playback_done_callback = playback_done_callback
        super().__init__()

    def onEof2(self) -> None:
        self.playback_done_callback()
        return super().onEof2()

    def play_file(self, audio_media: pj.AudioMedia, sound_file_name: str) -> None:
        self.createPlayer(file_name=sound_file_name, options=pj.PJMEDIA_FILE_NO_LOOP)
        self.startTransmit(audio_media)

    def play_playlist(self, audio_media: pj.AudioMedia, wav_playlist: list) -> None:
        self.createPlaylist(wav_playlist, "thePlaylist", pj.PJMEDIA_FILE_NO_LOOP)
        self.startTransmit(audio_media)

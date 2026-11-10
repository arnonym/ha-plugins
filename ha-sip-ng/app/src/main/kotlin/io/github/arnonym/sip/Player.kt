package io.github.arnonym.sip

import org.pjsip.pjsua2.AudioMedia
import org.pjsip.pjsua2.AudioMediaPlayer
import org.pjsip.pjsua2.pjmedia_file_player_option

class Player(private val playbackDoneCallback: () -> Unit) : AudioMediaPlayer() {
    override fun onEof2() {
        playbackDoneCallback()
        super.onEof2()
    }

    fun playFile(
        audioMedia: AudioMedia,
        soundFileName: String,
    ) {
        createPlayer(soundFileName, pjmedia_file_player_option.PJMEDIA_FILE_NO_LOOP.toLong())
        startTransmit(audioMedia)
    }
}

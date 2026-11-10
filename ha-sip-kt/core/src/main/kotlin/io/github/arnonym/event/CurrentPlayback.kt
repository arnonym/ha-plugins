package io.github.arnonym.event

sealed class CurrentPlayback {
    data class Message(val message: String) : CurrentPlayback()

    data class AudioFile(val audioFile: String) : CurrentPlayback()

    fun toPlaybackDoneEvent(): Event =
        when (this) {
            is Message -> Event.PlaybackDoneMessage(message)
            is AudioFile -> Event.PlaybackDoneAudioFile(audioFile)
        }
}

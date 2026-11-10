package io.github.arnonym.audio

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test

class AudioTest {
    @Test
    fun `conversion keeps the source rate unless one is configured`() {
        ffmpegCommand(AudioInputFormat.MP3, "/tmp/out.wav", null) shouldBe
            listOf("ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "mp3", "-i", "pipe:0", "/tmp/out.wav")
    }

    @Test
    fun `configured sample rate is passed to ffmpeg before the output file`() {
        ffmpegCommand(AudioInputFormat.WAV, "/tmp/out.wav", 8000) shouldBe
            listOf(
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "wav", "-i", "pipe:0", "-ar", "8000", "/tmp/out.wav",
            )
    }

    @Test
    fun `file name to format`() {
        audioFormatFromFilename("https://localhost:8080/something/file.mp3") shouldBe AudioInputFormat.MP3
        audioFormatFromFilename("http://localhost:8080/something/file.wav") shouldBe AudioInputFormat.WAV
        audioFormatFromFilename("https://localhost:8080/something/file.abc") shouldBe null
    }
}

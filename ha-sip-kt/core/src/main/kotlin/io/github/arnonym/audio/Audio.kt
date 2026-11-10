package io.github.arnonym.audio

import io.github.arnonym.log.log
import java.nio.file.Files

enum class AudioInputFormat(val extension: String) {
    MP3("mp3"),
    WAV("wav"),
    OGG("ogg"),
    FLAC("flac"),
    ;

    companion object {
        fun fromExtension(extension: String): AudioInputFormat? = entries.find { it.extension == extension }
    }
}

fun audioFormatFromFilename(filename: String): AudioInputFormat? {
    val lastSegment = filename.substringAfterLast('/')
    val suffix = lastSegment.substringAfterLast('.', missingDelimiterValue = "").lowercase()
    if (suffix.isEmpty()) return null
    return AudioInputFormat.fromExtension(suffix)
}

fun audioFormatFromContentType(contentType: String): AudioInputFormat? =
    when {
        contentType.contains("ogg", ignoreCase = true) -> AudioInputFormat.OGG
        contentType.contains("flac", ignoreCase = true) -> AudioInputFormat.FLAC
        contentType.contains("mpeg", ignoreCase = true) || contentType.contains("mp3", ignoreCase = true) -> AudioInputFormat.MP3
        contentType.contains("wav", ignoreCase = true) -> AudioInputFormat.WAV
        else -> null
    }

internal fun ffmpegCommand(
    inputFormat: AudioInputFormat,
    outputPath: String,
    sampleRate: Int?,
): List<String> =
    buildList {
        addAll(listOf("ffmpeg", "-y", "-hide_banner", "-loglevel", "error"))
        addAll(listOf("-f", inputFormat.extension, "-i", "pipe:0"))
        if (sampleRate != null) addAll(listOf("-ar", sampleRate.toString()))
        add(outputPath)
    }

fun convertAudioStreamToWavFile(
    stream: ByteArray,
    inputFormat: AudioInputFormat,
    sampleRate: Int? = null,
): String? {
    val wavFile = Files.createTempFile("hasip-", ".wav").toFile()
    return try {
        val process =
            ProcessBuilder(ffmpegCommand(inputFormat, wavFile.absolutePath, sampleRate))
                .redirectErrorStream(false).start()
        process.outputStream.use { it.write(stream) }
        val stderr = process.errorStream.bufferedReader().readText()
        val exitCode = process.waitFor()
        if (exitCode != 0) {
            log(null, "ffmpeg error: $stderr")
            wavFile.delete()
            return null
        }
        wavFile.absolutePath
    } catch (e: Exception) {
        log(null, "ffmpeg error: ${e.message}")
        wavFile.delete()
        null
    }
}

package io.github.arnonym.audio

import io.github.arnonym.log.log
import java.io.File
import java.security.MessageDigest

enum class CacheType(val wireValue: String) {
    AUDIO_FILE("audio_file"),
    MESSAGE("message"),
}

object AudioCache {
    fun getCachedFile(
        shouldCache: Boolean,
        cacheDir: String?,
        fileOrMessage: CacheType,
        fileNameOrMessage: String,
        sampleRate: Int? = null,
    ): String? {
        if (!shouldCache) return null
        if (cacheDir.isNullOrEmpty()) {
            log(null, "Warning: Caching enabled but no cache directory configured.")
            return null
        }
        val fileName = getCacheFileName(cacheDir, fileOrMessage, fileNameOrMessage, sampleRate)
        if (!File(fileName).isFile) {
            log(null, "Cache file not found: $fileName")
            return null
        }
        log(null, "Using cache from file: $fileName")
        return fileName
    }

    fun cacheFile(
        shouldCache: Boolean,
        cacheDir: String?,
        fileOrMessage: CacheType,
        fileNameOrMessage: String,
        fileToCache: String,
        sampleRate: Int? = null,
    ) {
        if (!shouldCache) return
        if (cacheDir.isNullOrEmpty()) {
            log(null, "Warning: Caching enabled but no cache directory configured.")
            return
        }
        val fileName = getCacheFileName(cacheDir, fileOrMessage, fileNameOrMessage, sampleRate)
        try {
            File(fileToCache).copyTo(File(fileName), overwrite = true)
        } catch (e: Exception) {
            log(null, "Could not create cache file: ${e.message}")
            return
        }
        log(null, "Created cache file: $fileName")
    }

    fun getCacheFileName(
        cacheDir: String,
        fileOrMessage: CacheType,
        fileNameOrMessage: String,
        sampleRate: Int? = null,
    ): String {
        val rateKey = sampleRate?.toString() ?: "source"
        val cacheKeyContent = "${fileOrMessage.wireValue}|$rateKey|$fileNameOrMessage"
        val digest = MessageDigest.getInstance("SHA-1").digest(cacheKeyContent.toByteArray())
        val cacheKey = digest.joinToString("") { "%02x".format(it) }.take(10)
        return File(cacheDir, "$cacheKey.wav").path
    }
}

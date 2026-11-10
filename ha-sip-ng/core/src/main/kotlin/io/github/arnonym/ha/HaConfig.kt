package io.github.arnonym.ha

import io.github.arnonym.config.TtsEnv
import io.github.arnonym.log.log

data class TtsConfig(
    val platform: String?,
    val engineId: String?,
    val language: String,
    val voice: String?,
    val debugPrint: Boolean,
) {
    companion object {
        fun from(env: TtsEnv): TtsConfig {
            val platform = env.platform.ifEmpty { null }
            val engineId = env.engineId.ifEmpty { null }
            val config =
                TtsConfig(
                    platform = platform,
                    engineId = engineId,
                    language = env.language.ifEmpty { "en" },
                    voice = env.voice.ifEmpty { null },
                    debugPrint = env.debugPrint.equals("true", ignoreCase = true),
                )
            if (config.engineId == null && config.platform == null) {
                log(null, "Warning: No TTS engine defined. Must be either specify engine_id or platform.")
            }
            if (config.engineId != null && config.platform != null) {
                log(null, "Warning: Both engine_id and platform defined. Using engine_id.")
            }
            if (config.engineId != null) {
                log(null, "TTS: Using engine ${config.engineId} with language ${config.language} with voice ${config.voice}")
            } else if (config.platform != null) {
                log(null, "TTS: Using platform ${config.platform} with language ${config.language} with voice ${config.voice}")
            }
            return config
        }
    }
}

data class HaConfig(
    val baseUrl: String,
    val websocketUrl: String,
    val token: String,
    val ttsConfig: TtsConfig,
    val webhookId: String,
    val cacheDir: String?,
    /** Target rate for every conversion, or null to keep each source's own rate. */
    val audioSampleRate: Int?,
) {
    fun createHeaders(): Map<String, String> =
        mapOf(
            "Authorization" to "Bearer $token",
        )

    fun ttsUrl(): String = "$baseUrl/tts_get_url"

    fun templateUrl(): String = "$baseUrl/template"

    fun serviceUrl(
        domain: String,
        service: String,
    ): String = "$baseUrl/services/$domain/$service"

    fun webhookUrl(webhookId: String): String = "$baseUrl/webhook/$webhookId"
}

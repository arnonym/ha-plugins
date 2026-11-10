package io.github.arnonym.config

/** ha-sip reads three fixed sets of SIP account variables: `SIP1_*`, `SIP2_*`, `SIP3_*`. */
val SIP_ACCOUNT_INDICES = 1..3

data class SipAccountEnv(
    val enabled: String,
    val idUri: String,
    val registrarUri: String,
    val realm: String,
    val userName: String,
    val password: String,
    val answerMode: String,
    val settleTime: String,
    val incomingCallFile: String,
    val options: String,
)

data class TtsEnv(
    val engineId: String,
    val platform: String,
    val language: String,
    val voice: String,
    val debugPrint: String,
)

data class HaEnv(
    val baseUrl: String,
    val websocketUrl: String,
    val token: String,
    val webhookId: String,
)

data class SensorEnv(
    val enabled: String,
    val entityPrefix: String,
)

data class AppConfig(
    val port: String,
    val logLevel: String,
    val nameServer: String,
    val cacheDir: String,
    val globalOptions: String,
    val sipAccounts: Map<Int, SipAccountEnv>,
    val tts: TtsEnv,
    val ha: HaEnv,
    val sensor: SensorEnv,
) {
    companion object {
        fun fromEnv(getenv: (String) -> String? = System::getenv): AppConfig {
            fun env(
                name: String,
                default: String = "",
            ) = getenv(name) ?: default

            fun sipAccountEnv(index: Int) =
                SipAccountEnv(
                    enabled = env("SIP${index}_ENABLED"),
                    idUri = env("SIP${index}_ID_URI"),
                    registrarUri = env("SIP${index}_REGISTRAR_URI"),
                    realm = env("SIP${index}_REALM"),
                    userName = env("SIP${index}_USER_NAME"),
                    password = env("SIP${index}_PASSWORD"),
                    answerMode = env("SIP${index}_ANSWER_MODE"),
                    settleTime = env("SIP${index}_SETTLE_TIME"),
                    incomingCallFile = env("SIP${index}_INCOMING_CALL_FILE"),
                    options = env("SIP${index}_OPTIONS"),
                )

            return AppConfig(
                port = env("PORT"),
                logLevel = env("LOG_LEVEL"),
                nameServer = env("NAME_SERVER"),
                cacheDir = env("CACHE_DIR"),
                globalOptions = env("GLOBAL_OPTIONS"),
                sipAccounts = SIP_ACCOUNT_INDICES.associateWith { sipAccountEnv(it) },
                tts =
                    TtsEnv(
                        engineId = env("TTS_ENGINE_ID"),
                        platform = env("TTS_PLATFORM"),
                        language = env("TTS_LANGUAGE"),
                        voice = env("TTS_VOICE"),
                        debugPrint = env("TTS_DEBUG_PRINT"),
                    ),
                ha =
                    HaEnv(
                        baseUrl = env("HA_BASE_URL"),
                        websocketUrl = env("HA_WEBSOCKET_URL"),
                        token = env("HA_TOKEN"),
                        webhookId = env("HA_WEBHOOK_ID"),
                    ),
                sensor =
                    SensorEnv(
                        enabled = env("SENSOR_ENABLED", "false"),
                        entityPrefix = env("SENSOR_ENTITY_PREFIX", "ha_sip"),
                    ),
            )
        }
    }
}

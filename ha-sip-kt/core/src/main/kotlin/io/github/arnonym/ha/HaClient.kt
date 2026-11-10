package io.github.arnonym.ha

import io.github.arnonym.audio.audioFormatFromContentType
import io.github.arnonym.audio.audioFormatFromFilename
import io.github.arnonym.audio.convertAudioStreamToWavFile
import io.github.arnonym.json.boolValueOrNull
import io.github.arnonym.json.stringOrNull
import io.github.arnonym.json.stringValueOrNull
import io.github.arnonym.log.log
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.websocket.DefaultClientWebSocketSession
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.plugins.websocket.webSocket
import io.ktor.client.request.get
import io.ktor.client.request.headers
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.serialization.kotlinx.json.json
import io.ktor.websocket.Frame
import io.ktor.websocket.readText
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonObjectBuilder
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.nio.file.Files
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

data class TtsResult(val fileName: String, val mustBeDeleted: Boolean, val wasSuccessful: Boolean)

private val ttsThreadCounter = AtomicInteger()

/**
 * Deadlines for everything we ask of Home Assistant, replacing the CIO engine's own 15 s
 * default -- which is longer than any of these calls has a right to take, and is inherited
 * silently enough that it reads like "no timeout" at every call site.
 *
 * These also bound the startup TTS diagnostic, which is the one caller that blocks the
 * main thread: its `incoming.receive()` against a Home Assistant that accepts the
 * connection and then says nothing would otherwise hang startup forever.
 */
private const val REQUEST_TIMEOUT_MILLIS = 30_000L
private const val CONNECT_TIMEOUT_MILLIS = 5_000L

class HaClient(private val config: HaConfig) : AutoCloseable {
    private val json = Json { ignoreUnknownKeys = true }

    private val httpClient =
        HttpClient(CIO) {
            install(ContentNegotiation) { json(json) }
            install(WebSockets)
            install(HttpTimeout) {
                requestTimeoutMillis = REQUEST_TIMEOUT_MILLIS
                connectTimeoutMillis = CONNECT_TIMEOUT_MILLIS
            }
        }

    private val rawHttpClient =
        HttpClient(CIO) {
            install(HttpTimeout) {
                requestTimeoutMillis = REQUEST_TIMEOUT_MILLIS
                connectTimeoutMillis = CONNECT_TIMEOUT_MILLIS
            }
        }

    /**
     * Runs TTS fetches off the caller's thread. Deliberately a plain pool of daemon
     * threads rather than anything pjsip knows about: nothing that runs here may touch
     * pjsua2, so these threads must never be registered with it (each registration
     * allocates a descriptor that is only freed at `libDestroy()`).
     */
    private val ttsExecutor =
        Executors.newCachedThreadPool { runnable ->
            Thread(runnable, "tts-fetch-${ttsThreadCounter.incrementAndGet()}").apply { isDaemon = true }
        }

    /**
     * [createAndGetTts] off-thread; [onResult] runs on a TTS thread once the audio has
     * landed. A synthesis round-trip is seconds of HA request plus download, and every
     * caller of the blocking form is on a thread that has other calls to service.
     *
     * Failures are already folded into [TtsResult] (an error wav, `wasSuccessful` false),
     * so [onResult] always runs.
     */
    fun createAndGetTtsAsync(
        message: String,
        language: String,
        onResult: (TtsResult) -> Unit,
    ) {
        ttsExecutor.execute {
            val result =
                try {
                    createAndGetTts(message, language)
                } catch (e: Exception) {
                    log(null, "Error getting tts file: ${e.message}")
                    TtsResult(errorWavPath(), false, false)
                }
            try {
                onResult(result)
            } catch (e: Exception) {
                log(null, "Error handling tts result: ${e.message}")
            }
        }
    }

    /**
     * POSTs [payload] as JSON to [url] with HA's auth headers.
     *
     * Returns null when the request could not be made at all -- already logged, prefixed
     * with [errorContext] so the caller does not have to repeat its own try/catch. A
     * non-2xx *response* still comes back as a response; only the caller knows whether
     * that is fatal.
     */
    private suspend fun postJson(
        url: String,
        payload: JsonObject,
        errorContext: String,
    ): HttpResponse? =
        try {
            httpClient.post(url) {
                contentType(ContentType.Application.Json)
                headers { config.createHeaders().forEach { (k, v) -> append(k, v) } }
                setBody(payload)
            }
        } catch (e: Exception) {
            log(null, "$errorContext: ${e.message}")
            null
        }

    fun createAndGetTts(
        message: String,
        language: String,
    ): TtsResult =
        runBlocking {
            fun fail(reason: String): TtsResult {
                log(null, reason)
                return TtsResult(errorWavPath(), false, false)
            }

            val tts = config.ttsConfig
            val payload =
                buildJsonObject {
                    if (tts.voice != null) {
                        putJsonObjectField("options") { put("voice", tts.voice) }
                    }
                    put("message", message)
                    put("language", language)
                    if (tts.engineId != null) put("engine_id", tts.engineId) else put("platform", tts.platform)
                }
            if (tts.debugPrint) {
                log(null, "TTS payload: $payload")
            }
            val createResponse =
                postJson(config.ttsUrl(), payload, "Error getting tts file")
                    ?: return@runBlocking TtsResult(errorWavPath(), false, false)
            if (!createResponse.status.isSuccess()) {
                return@runBlocking fail("Error getting tts file ${createResponse.status} ${createResponse.bodyAsText()}")
            }
            val ttsUrl =
                createResponse.body<JsonObject>().stringOrNull("url")
                    ?: return@runBlocking fail("Error: tts response did not contain a url")
            log(null, "Getting audio from \"$ttsUrl\"")
            val ttsResponse =
                try {
                    rawHttpClient.get(ttsUrl) {
                        headers { config.createHeaders().forEach { (k, v) -> append(k, v) } }
                    }
                } catch (e: Exception) {
                    return@runBlocking fail("Error getting tts audio: ${e.message}")
                }
            if (!ttsResponse.status.isSuccess()) {
                val bodySnippet = ttsResponse.bodyAsText().take(300)
                return@runBlocking fail(
                    "Error getting tts audio: HTTP ${ttsResponse.status.value} ${ttsResponse.status.description} — $bodySnippet",
                )
            }
            val contentType = ttsResponse.headers["Content-Type"] ?: ""
            val fileFormat =
                audioFormatFromContentType(contentType) ?: audioFormatFromFilename(ttsUrl)
                    ?: return@runBlocking fail("Error getting audio format from content-type \"$contentType\" or filename: $ttsUrl")
            val audioBytes = ttsResponse.body<ByteArray>()
            if (audioBytes.isEmpty()) {
                return@runBlocking fail("Error getting tts audio: empty response body")
            }
            val wavFileName =
                convertAudioStreamToWavFile(audioBytes, fileFormat, config.audioSampleRate)
                    ?: return@runBlocking fail(
                        "Error converting to wav (content-type: $contentType, format: $fileFormat, ${audioBytes.size} bytes)",
                    )
            TtsResult(wavFileName, true, true)
        }

    fun renderTemplate(text: String): String =
        runBlocking {
            log(null, "Rendering template: $text")
            val payload = buildJsonObject { put("template", text) }
            val response = postJson(config.templateUrl(), payload, "Error rendering template") ?: return@runBlocking text
            log(null, "Template response ${response.status} ${response.bodyAsText()}")
            if (response.status.isSuccess()) response.bodyAsText() else text
        }

    fun callService(
        domain: String,
        service: String,
        entityId: String?,
        serviceData: JsonObject?,
    ) {
        runBlocking {
            val payload =
                buildJsonObject {
                    if (entityId != null) put("entity_id", entityId)
                    serviceData?.forEach { (key, value) -> put(key, value) }
                }
            val response =
                postJson(config.serviceUrl(domain, service), payload, "Error calling home-assistant service")
                    ?: return@runBlocking
            log(null, "Service response ${response.status} ${response.bodyAsText()}")
        }
    }

    fun triggerWebhook(
        event: JsonObject,
        overwriteWebhookId: String? = null,
    ) {
        val webhookId = overwriteWebhookId ?: config.webhookId
        if (webhookId.isEmpty()) {
            log(null, "Warning: No webhook defined.")
            return
        }
        log(null, "Calling webhook $webhookId with data $event")
        runBlocking {
            val response = postJson(config.webhookUrl(webhookId), event, "Error calling webhook") ?: return@runBlocking
            log(null, "Webhook response ${response.status} ${response.bodyAsText()}")
        }
    }

    fun updateSensorState(
        entityId: String,
        state: String,
        attributes: JsonObject,
    ) {
        runBlocking {
            val payload =
                buildJsonObject {
                    put("state", state)
                    put("attributes", attributes)
                }
            val response =
                postJson("${config.baseUrl}/states/$entityId", payload, "Error updating sensor $entityId")
                    ?: return@runBlocking
            if (response.status.isSuccess()) {
                log(null, "Sensor update $entityId: ${response.status}")
            } else {
                log(null, "Sensor update $entityId failed: ${response.status} ${response.bodyAsText()}")
            }
        }
    }

    /**
     * Startup diagnostic for `TTS_DEBUG_PRINT`: lists what HA can actually synthesize and
     * says whether the configured engine/language pair is among it. Purely informational
     * -- every step logs and gives up rather than failing startup.
     */
    fun printTtsProviders() =
        runBlocking {
            log(null, "Connecting to websocket under URL '${config.websocketUrl}'")
            try {
                httpClient.webSocket(urlString = config.websocketUrl) {
                    if (!authenticateToHa()) return@webSocket
                    val providers = request(id = 1, type = "tts/engine/list")?.get("providers") as? JsonArray
                    if (providers == null) {
                        log(null, "TTS debug: tts/engine/list response carried no provider list")
                        return@webSocket
                    }
                    logProviders(providers)

                    val tts = config.ttsConfig
                    val engineFromConfig = tts.engineId ?: tts.platform
                    if (!checkConfiguredEngine(providers, engineFromConfig, tts.language)) return@webSocket

                    val voices =
                        request(id = 2, type = "tts/engine/voices") {
                            put("engine_id", engineFromConfig)
                            put("language", tts.language)
                        } ?: return@webSocket
                    logVoices(voices["voices"] as? JsonArray)
                }
            } catch (e: Exception) {
                log(null, "TTS debug: websocket error: ${e.message}")
            }
        }

    private suspend fun DefaultClientWebSocketSession.sendJson(build: JsonObjectBuilder.() -> Unit) {
        outgoing.send(Frame.Text(buildJsonObject(build).toString()))
    }

    private suspend fun DefaultClientWebSocketSession.receiveJson(): JsonObject? =
        (incoming.receive() as? Frame.Text)?.let { json.parseToJsonElement(it.readText()) as? JsonObject }

    private suspend fun DefaultClientWebSocketSession.authenticateToHa(): Boolean {
        // The server speaks first with an auth challenge; its content tells us nothing we
        // do not already know, so it is received purely to get past it.
        incoming.receive()
        sendJson {
            put("type", "auth")
            put("access_token", config.token)
        }
        val response = receiveJson()
        if (response?.get("type")?.stringValueOrNull() != "auth_ok") {
            log(null, "TTS debug: authentication failed: $response")
            return false
        }
        return true
    }

    /** Sends one command and returns its `result` object, or null (already logged) if it failed. */
    private suspend fun DefaultClientWebSocketSession.request(
        id: Int,
        type: String,
        build: JsonObjectBuilder.() -> Unit = {},
    ): JsonObject? {
        sendJson {
            put("id", id)
            put("type", type)
            build()
        }
        val response = receiveJson()
        if (response?.get("success")?.boolValueOrNull() != true) {
            log(null, "TTS debug: $type request failed: $response")
            return null
        }
        return response["result"] as? JsonObject
    }

    private fun logProviders(providers: JsonArray) {
        log(null, "Available TTS providers:")
        providers.filterIsInstance<JsonObject>().forEach { provider ->
            val engineId = provider.stringOrNull("engine_id") ?: return@forEach
            log(null, "  $engineId:")
            log(null, "    Languages:")
            provider.supportedLanguages().chunked(10).forEach { chunk -> log(null, "      ${chunk.joinToString(", ")}") }
        }
    }

    /** Returns false (already logged) when the configured engine/language pair is unusable. */
    private fun checkConfiguredEngine(
        providers: JsonArray,
        engineFromConfig: String?,
        language: String,
    ): Boolean {
        val provider =
            providers.filterIsInstance<JsonObject>()
                .firstOrNull { it.stringOrNull("engine_id") == engineFromConfig }
        if (provider == null) {
            log(null, "  Warning: No TTS provider found for engine $engineFromConfig")
            return false
        }
        if (language !in provider.supportedLanguages()) {
            log(null, "  Warning: Language $language not supported by TTS provider $engineFromConfig")
            return false
        }
        log(null, "  Good news: TTS provider $engineFromConfig was found and supports language $language")
        return true
    }

    private fun logVoices(voices: JsonArray?) {
        if (voices.isNullOrEmpty()) {
            log(null, "  Current engine doesn't support voices")
            return
        }
        log(null, "  Voices for current engine and language:")
        voices.filterIsInstance<JsonObject>().forEach { voice ->
            log(null, "      ${voice.stringOrNull("voice_id") ?: ""}: ${voice.stringOrNull("name") ?: ""}")
        }
    }

    private fun JsonObject.supportedLanguages(): List<String> =
        (this["supported_languages"] as? JsonArray)?.mapNotNull { it.stringValueOrNull() } ?: emptyList()

    override fun close() {
        ttsExecutor.shutdownNow()
        httpClient.close()
        rawHttpClient.close()
    }

    companion object {
        @Volatile
        private var cachedErrorWavPath: String? = null

        @Synchronized
        fun errorWavPath(): String {
            cachedErrorWavPath?.let { return it }
            val resource =
                HaClient::class.java.getResourceAsStream("/sound/error.wav")
                    ?: throw IllegalStateException("Bundled sound/error.wav resource not found")
            val tempFile = Files.createTempFile("hasip-error-", ".wav").toFile()
            resource.use { input -> tempFile.outputStream().use { output -> input.copyTo(output) } }
            cachedErrorWavPath = tempFile.absolutePath
            return tempFile.absolutePath
        }
    }
}

private fun JsonObjectBuilder.putJsonObjectField(
    key: String,
    build: JsonObjectBuilder.() -> Unit,
) {
    put(key, buildJsonObject(build))
}

package io.github.arnonym.sensor

import io.github.arnonym.json.objectOrNull
import io.github.arnonym.json.stringOrNull
import io.github.arnonym.log.log
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.time.LocalDateTime
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.TimeUnit

data class SensorConfig(
    val enabled: Boolean,
    val entityPrefix: String,
)

fun interface SensorSink {
    fun write(
        entityId: String,
        state: String,
        attributes: JsonObject,
    )
}

interface SensorUpdates {
    fun setCallActive(
        accountIndex: Int,
        callInfo: JsonObject,
    )

    fun setCallInactive(accountIndex: Int)

    fun updateRegistrationStatus(
        accountIndex: Int,
        code: Int,
        reason: String,
    )

    fun updateLastCall(
        accountIndex: Int,
        direction: String,
        callInfo: JsonObject? = null,
    )

    fun initializeSensors()
}

class SensorUpdater(
    private val sink: SensorSink,
    private val sensorConfig: SensorConfig,
    private val enabledAccounts: List<Int>,
) : SensorUpdates, AutoCloseable {
    private val executor =
        Executors.newSingleThreadExecutor { runnable ->
            Thread(runnable, "sensor-updates").apply { isDaemon = true }
        }

    private fun sanitizedPrefix(): String = sensorConfig.entityPrefix.replace('-', '_').lowercase()

    private fun entityId(accountIndex: Int): String = "sensor.${sanitizedPrefix()}_account_$accountIndex"

    private fun registrationEntityId(accountIndex: Int): String = "sensor.${sanitizedPrefix()}_registration_$accountIndex"

    private fun lastCallEntityId(accountIndex: Int): String = "sensor.${sanitizedPrefix()}_last_call_$accountIndex"

    private fun updateSensor(
        entityId: String,
        state: String,
        attributes: Map<String, JsonElement?>,
    ) {
        val filtered = JsonObject(attributes.filterValues { it != null }.mapValues { it.value!! })
        try {
            executor.execute { sink.write(entityId, state, filtered) }
        } catch (e: RejectedExecutionException) {
            log(null, "Dropping sensor update for $entityId during shutdown: ${e.message}")
        }
    }

    /**
     * The who-called-whom attributes shared by the "call active" and "last call" sensors.
     *
     * Each URI is published twice: once under its `caller`/`called` name and once under
     * `remote_uri`/`local_uri`. The first pair is deprecated but still in the webhook
     * payload contract, so both have to stay.
     */
    private fun callUriAttributes(callInfo: JsonObject): Map<String, JsonElement?> {
        fun uri(key: String) = callInfo.stringOrNull(key)?.toJson()
        return mapOf(
            "caller" to uri("remote_uri"),
            "called" to uri("local_uri"),
            "parsed_caller" to uri("parsed_remote_uri"),
            "parsed_called" to uri("parsed_local_uri"),
            "remote_uri" to uri("remote_uri"),
            "local_uri" to uri("local_uri"),
            "parsed_remote_uri" to uri("parsed_remote_uri"),
            "parsed_local_uri" to uri("parsed_local_uri"),
        )
    }

    override fun setCallActive(
        accountIndex: Int,
        callInfo: JsonObject,
    ) {
        if (!sensorConfig.enabled) return
        val attributes =
            mapOf(
                "friendly_name" to "SIP Account $accountIndex".toJson(),
                "icon" to "mdi:phone-in-talk".toJson(),
            ) + callUriAttributes(callInfo) +
                mapOf(
                    "sip_account" to callInfo["sip_account"],
                    "call_id" to callInfo.stringOrNull("call_id")?.toJson(),
                    "internal_id" to callInfo.stringOrNull("internal_id")?.toJson(),
                    "headers" to (callInfo.objectOrNull("headers") ?: JsonObject(emptyMap())),
                )
        updateSensor(entityId(accountIndex), "true", attributes)
    }

    override fun setCallInactive(accountIndex: Int) {
        if (!sensorConfig.enabled) return
        val attributes =
            mapOf(
                "friendly_name" to "SIP Account $accountIndex".toJson(),
                "icon" to "mdi:phone".toJson(),
            )
        updateSensor(entityId(accountIndex), "false", attributes)
    }

    override fun updateRegistrationStatus(
        accountIndex: Int,
        code: Int,
        reason: String,
    ) {
        if (!sensorConfig.enabled) return
        val (state, icon) =
            when (code) {
                200 -> "registered" to "mdi:phone-check"
                0 -> "unregistered" to "mdi:phone-off"
                else -> "failed" to "mdi:phone-alert"
            }
        val attributes =
            mapOf(
                "friendly_name" to "SIP Registration $accountIndex".toJson(),
                "icon" to icon.toJson(),
                "status_code" to code.toJson(),
                "reason" to reason.toJson(),
                "last_change" to LocalDateTime.now().toString().toJson(),
            )
        updateSensor(registrationEntityId(accountIndex), state, attributes)
    }

    override fun updateLastCall(
        accountIndex: Int,
        direction: String,
        callInfo: JsonObject?,
    ) {
        if (!sensorConfig.enabled) return
        val icon =
            when (direction) {
                "none" -> "mdi:phone"
                "incoming" -> "mdi:phone-incoming"
                else -> "mdi:phone-outgoing"
            }
        val base =
            mapOf<String, JsonElement?>(
                "friendly_name" to "SIP Last Call $accountIndex".toJson(),
                "icon" to icon.toJson(),
            )
        val attributes =
            if (callInfo == null) {
                base
            } else {
                base + callUriAttributes(callInfo) +
                    mapOf(
                        "call_id" to callInfo.stringOrNull("call_id")?.toJson(),
                        "timestamp" to LocalDateTime.now().toString().toJson(),
                    )
            }
        updateSensor(lastCallEntityId(accountIndex), direction, attributes)
    }

    override fun initializeSensors() {
        if (!sensorConfig.enabled) return
        log(null, "Initializing sensors with prefix '${sensorConfig.entityPrefix}' for accounts: $enabledAccounts")
        enabledAccounts.forEach { accountIndex ->
            setCallInactive(accountIndex)
            updateSensor(
                registrationEntityId(accountIndex),
                "unknown",
                mapOf(
                    "friendly_name" to "SIP Registration $accountIndex".toJson(),
                    "icon" to "mdi:phone-clock".toJson(),
                ),
            )
            updateLastCall(accountIndex, "none")
        }
    }

    override fun close() {
        executor.shutdown()
        if (!executor.awaitTermination(SHUTDOWN_TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
            log(null, "Warning: sensor updates still pending after ${SHUTDOWN_TIMEOUT_SECONDS}s, abandoning them.")
            executor.shutdownNow()
        }
    }

    companion object {
        private const val SHUTDOWN_TIMEOUT_SECONDS = 5L
    }
}

private fun String.toJson(): JsonElement = JsonPrimitive(this)

private fun Int.toJson(): JsonElement = JsonPrimitive(this)

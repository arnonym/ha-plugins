package io.github.arnonym.mqtt

import com.hivemq.client.mqtt.datatypes.MqttQos
import com.hivemq.client.mqtt.mqtt3.Mqtt3AsyncClient
import com.hivemq.client.mqtt.mqtt3.Mqtt3Client
import io.github.arnonym.config.GlobalOptions
import io.github.arnonym.log.log
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import java.nio.charset.StandardCharsets
import java.util.UUID

/**
 * Wraps the HiveMQ MQTT client for stand-alone-mode command intake and state
 * publishing. Direct behavioral port of mqtt.py's `MqttClient`, but using
 * HiveMQ's async client with built-in automatic reconnection instead of
 * paho-mqtt's manual `client.loop()`/`reconnect()` polling (there is no
 * `handle()` method to call periodically here -- the client manages its own
 * connection lifecycle on its own internal threads).
 *
 * @param onCommand invoked (on an HiveMQ client thread) for every successfully
 *   JSON-decoded message received on [GlobalOptions.mqttTopic] -- wire this to
 *   the same command queue/`CommandHandler.handleCommand` used for stdin, exactly
 *   like the original shared one `handle_command` code path for both sources.
 */
class MqttClient(
    private val globalOptions: GlobalOptions,
    private val onCommand: (JsonObject) -> Unit,
) {
    private val client: Mqtt3AsyncClient =
        Mqtt3Client.builder()
            .identifier("ha-sip-${UUID.randomUUID()}")
            .serverHost(globalOptions.mqttAddress)
            .serverPort(globalOptions.mqttPort)
            .automaticReconnect().applyAutomaticReconnect()
            .addConnectedListener { log(null, "Connected to mqtt broker") }
            .addDisconnectedListener { context ->
                log(null, "Lost connection to mqtt broker: ${context.cause.message}")
            }
            .buildAsync()

    fun connect() {
        val connectBuilder = client.connectWith()
        if (globalOptions.mqttUsername.isNotEmpty()) {
            connectBuilder.simpleAuth()
                .username(globalOptions.mqttUsername)
                .password(globalOptions.mqttPassword.toByteArray(StandardCharsets.UTF_8))
                .applySimpleAuth()
        }
        connectBuilder.send().whenComplete { _, throwable ->
            if (throwable != null) {
                log(null, "Could not connect to mqtt broker: ${throwable.message}")
                return@whenComplete
            }
            client.subscribeWith()
                .topicFilter(globalOptions.mqttTopic)
                .qos(MqttQos.AT_LEAST_ONCE)
                .callback { publish ->
                    val payload = StandardCharsets.UTF_8.decode(publish.payload.orElse(null) ?: return@callback).toString()
                    log(null, "Received mqtt payload: $payload on topic: ${publish.topic}")
                    val parsed =
                        try {
                            Json.parseToJsonElement(payload) as? JsonObject
                        } catch (e: Exception) {
                            null
                        }
                    if (parsed != null) onCommand(parsed) else log(null, "Could not deserialize JSON: $payload")
                }
                .send()
        }
    }

    /** Direct port of mqtt.py's `send_event`. */
    fun sendEvent(event: JsonObject) {
        val stateTopic = globalOptions.mqttStateTopic
        if (stateTopic.isEmpty()) return
        if (!client.state.isConnected) {
            log(null, "Cannot send message, mqtt client is not connected")
            return
        }
        log(null, "Sending mqtt message: $event to topic: $stateTopic")
        client.publishWith()
            .topic(stateTopic)
            .qos(MqttQos.AT_LEAST_ONCE)
            .payload(event.toString().toByteArray(StandardCharsets.UTF_8))
            .send()
    }

    fun disconnect() {
        client.disconnect()
    }
}

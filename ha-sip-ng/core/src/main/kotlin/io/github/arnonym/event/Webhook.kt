package io.github.arnonym.event

import io.github.arnonym.json.stringOrNull
import io.github.arnonym.log.log
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonObjectBuilder
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

enum class CallDirection(val wireValue: String) {
    INCOMING("incoming"),
    OUTGOING("outgoing"),
}

data class CallInfo(
    val localUri: String,
    val remoteUri: String,
    val parsedLocalUri: String?,
    val parsedRemoteUri: String?,
    val callId: String?,
    val headers: Map<String, String?>,
    val direction: CallDirection,
)

data class WebhookToCall(
    val outgoingCallInitiated: String? = null,
    val callEstablished: String? = null,
    val enteredMenu: String? = null,
    val dtmfDigit: String? = null,
    val callDisconnected: String? = null,
    val timeout: String? = null,
    val ringTimeout: String? = null,
    val playbackDone: String? = null,
) {
    fun forEventName(eventName: String): String? =
        when (eventName) {
            "outgoing_call_initiated" -> outgoingCallInitiated
            "call_established" -> callEstablished
            "entered_menu" -> enteredMenu
            "dtmf_digit" -> dtmfDigit
            "call_disconnected" -> callDisconnected
            "timeout" -> timeout
            "ring_timeout" -> ringTimeout
            "playback_done" -> playbackDone
            else -> null
        }

    companion object {
        fun fromJson(json: JsonObject?): WebhookToCall? {
            if (json == null) return null
            return WebhookToCall(
                outgoingCallInitiated = json.stringOrNull("outgoing_call_initiated"),
                callEstablished = json.stringOrNull("call_established"),
                enteredMenu = json.stringOrNull("entered_menu"),
                dtmfDigit = json.stringOrNull("dtmf_digit"),
                callDisconnected = json.stringOrNull("call_disconnected"),
                timeout = json.stringOrNull("timeout"),
                ringTimeout = json.stringOrNull("ring_timeout"),
                playbackDone = json.stringOrNull("playback_done"),
            )
        }
    }
}

fun buildWebhookEnvelope(
    event: Event,
    callInfo: CallInfo?,
    sipAccount: Int?,
    internalId: String,
): JsonObject =
    buildJsonObject {
        put("local_uri", callInfo?.localUri ?: "unknown")
        put("remote_uri", callInfo?.remoteUri ?: "unknown")
        put("parsed_local_uri", callInfo?.parsedLocalUri)
        put("parsed_remote_uri", callInfo?.parsedRemoteUri)
        put("sip_account", sipAccount)
        put("call_id", callInfo?.callId)
        put("internal_id", internalId)
        putHeaders(callInfo?.headers ?: emptyMap())
        put("call_direction", (callInfo?.direction ?: CallDirection.INCOMING).wireValue)
        // Deprecated aliases, kept for backwards compatibility.
        put("caller", callInfo?.remoteUri ?: "unknown")
        put("called", callInfo?.localUri ?: "unknown")
        put("parsed_caller", callInfo?.parsedRemoteUri)
        put("parsed_called", callInfo?.parsedLocalUri)
        put("event", event.eventName)
        event.extraFields().forEach { (key, value) -> put(key, value) }
    }

private fun JsonObjectBuilder.putHeaders(headers: Map<String, String?>) {
    put("headers", buildJsonObject { headers.forEach { (key, value) -> put(key, value) } })
}

fun sendEvent(
    event: Event,
    callInfo: CallInfo?,
    sipAccount: Int?,
    internalId: String,
    eventSender: EventSender,
    webhooks: WebhookToCall? = null,
) {
    val envelope = buildWebhookEnvelope(event, callInfo, sipAccount, internalId)
    val additionalWebhook = webhooks?.forEventName(event.eventName)
    if (additionalWebhook != null) {
        log(sipAccount, "Calling additional webhook $additionalWebhook for event ${event.eventName}")
    }
    eventSender.sendEvent(envelope, additionalWebhook)
}

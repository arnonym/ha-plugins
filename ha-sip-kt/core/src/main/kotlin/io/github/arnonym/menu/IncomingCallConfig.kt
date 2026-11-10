package io.github.arnonym.menu

import io.github.arnonym.event.WebhookToCall
import io.github.arnonym.json.intOrDefault
import io.github.arnonym.json.objectOrNull
import io.github.arnonym.json.stringValueOrNull
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject

data class IncomingCallConfig(
    val allowedNumbers: List<String>?,
    val blockedNumbers: List<String>?,
    val answerAfter: Int,
    val webhookToCall: WebhookToCall?,
    val menu: JsonObject?,
) {
    companion object {
        fun fromJson(json: JsonObject?): IncomingCallConfig? {
            if (json == null) return null
            return IncomingCallConfig(
                allowedNumbers = (json["allowed_numbers"] as? JsonArray)?.mapNotNull { it.stringValueOrNull() },
                blockedNumbers = (json["blocked_numbers"] as? JsonArray)?.mapNotNull { it.stringValueOrNull() },
                answerAfter = json.intOrDefault("answer_after", 0),
                webhookToCall = WebhookToCall.fromJson(json.objectOrNull("webhook_to_call")),
                menu = json.objectOrNull("menu"),
            )
        }
    }
}

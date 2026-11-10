package io.github.arnonym.event

import io.github.arnonym.json.stringOrNull
import io.kotest.matchers.collections.shouldContainExactly
import io.kotest.matchers.collections.shouldContainExactlyInAnyOrder
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.jupiter.api.Test
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Delivery is asynchronous, so every case here closes the sender before asserting --
 * `close()` drains the queue and waits, which is what makes these deterministic rather
 * than a race against a sleep.
 */
class EventSenderTest {
    private fun event(name: String): JsonObject = buildJsonObject { put("event", name) }

    private fun JsonObject.name(): String = stringOrNull("event") ?: "<none>"

    @Test
    fun `a matching webhook_to_call entry does not deliver the event twice`() {
        val webhookAgnosticSink = CopyOnWriteArrayList<String>()

        EventSender().use { sender ->
            sender.registerSender { event, _ -> webhookAgnosticSink.add(event.name()) }
            sendEvent(
                event = Event.CallEstablished,
                callInfo = null,
                sipAccount = 1,
                internalId = "call-1",
                eventSender = sender,
                webhooks = WebhookToCall(callEstablished = "extra-hook"),
            )
        }

        // The regression: an event with a `webhook_to_call` entry used to be dispatched
        // twice, so sinks that ignore the webhook id -- MQTT, the sensors -- saw it twice.
        webhookAgnosticSink shouldContainExactly listOf("call_established")
    }

    @Test
    fun `an event named by webhook_to_call is posted to that webhook and to the global one`() {
        // The wiring from Main: a single sink posts to the globally configured webhook, and
        // additionally to whatever id it is handed. Two webhooks configured by different
        // means are two recipients, and both are meant to see the event.
        val posted = CopyOnWriteArrayList<Pair<String, String>>()
        val globalWebhookId = "global-hook"

        EventSender().use { sender ->
            sender.registerSender { event, additionalWebhookId ->
                posted.add(globalWebhookId to event.name())
                if (additionalWebhookId != null) posted.add(additionalWebhookId to event.name())
            }
            sendEvent(
                event = Event.CallEstablished,
                callInfo = null,
                sipAccount = 1,
                internalId = "call-1",
                eventSender = sender,
                webhooks = WebhookToCall(callEstablished = "extra-hook"),
            )
        }

        posted shouldContainExactlyInAnyOrder
            listOf(
                "extra-hook" to "call_established",
                globalWebhookId to "call_established",
            )
    }

    @Test
    fun `an event with no matching webhook_to_call entry carries no webhook id`() {
        val seen = CopyOnWriteArrayList<Pair<String, String?>>()

        EventSender().use { sender ->
            sender.registerSender { event, additionalWebhookId -> seen.add(event.name() to additionalWebhookId) }
            sendEvent(
                event = Event.CallDisconnected,
                callInfo = null,
                sipAccount = 1,
                internalId = "call-1",
                eventSender = sender,
                // Configured, but for a different event.
                webhooks = WebhookToCall(callEstablished = "extra-hook"),
            )
        }

        seen shouldContainExactly listOf("call_disconnected" to null)
    }

    @Test
    fun `every sink sees a matching event exactly once`() {
        // Guards the shape of the bug rather than one symptom of it: whatever the rider
        // says, one raised event is one delivery per registered sink.
        val deliveries = CopyOnWriteArrayList<String>()

        EventSender().use { sender ->
            repeat(3) { index -> sender.registerSender { event, _ -> deliveries.add("sink-$index:${event.name()}") } }
            sendEvent(
                event = Event.CallEstablished,
                callInfo = null,
                sipAccount = 1,
                internalId = "call-1",
                eventSender = sender,
                webhooks = WebhookToCall(callEstablished = "extra-hook"),
            )
        }

        deliveries shouldContainExactlyInAnyOrder
            listOf(
                "sink-0:call_established",
                "sink-1:call_established",
                "sink-2:call_established",
            )
    }

    @Test
    fun `events are delivered in the order they were raised`() {
        val seen = CopyOnWriteArrayList<String>()
        val raised = (1..50).map { "event-$it" }

        EventSender().use { sender ->
            sender.registerSender { event, _ -> seen.add(event.name()) }
            raised.forEach { sender.sendEvent(event(it)) }
        }

        seen shouldContainExactly raised
    }

    @Test
    fun `a failing sink costs neither the other sinks nor later events`() {
        val healthy = CopyOnWriteArrayList<String>()

        EventSender().use { sender ->
            sender.registerSender { _, _ -> error("this sink is broken") }
            sender.registerSender { event, _ -> healthy.add(event.name()) }
            sender.sendEvent(event("first"))
            sender.sendEvent(event("second"))
        }

        healthy shouldContainExactly listOf("first", "second")
    }
}

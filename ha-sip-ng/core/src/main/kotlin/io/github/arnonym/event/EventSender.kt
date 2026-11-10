package io.github.arnonym.event

import io.github.arnonym.log.log
import kotlinx.serialization.json.JsonObject
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.TimeUnit

class EventSender : AutoCloseable {
    private val sinks = CopyOnWriteArrayList<(JsonObject, String?) -> Unit>()

    private val dispatcher =
        Executors.newSingleThreadExecutor { runnable ->
            Thread(runnable, "event-dispatcher").apply { isDaemon = true }
        }

    fun registerSender(callback: (event: JsonObject, additionalWebhookId: String?) -> Unit) {
        sinks.add(callback)
    }

    fun sendEvent(
        event: JsonObject,
        additionalWebhookId: String? = null,
    ) = submit { sinks.forEach { sink -> runSink { sink(event, additionalWebhookId) } } }

    private fun submit(delivery: () -> Unit) {
        try {
            dispatcher.execute(delivery)
        } catch (e: RejectedExecutionException) {
            log(null, "Dropping event, shutdown already in progress: ${e.message}")
        }
    }

    private inline fun runSink(body: () -> Unit) {
        try {
            body()
        } catch (e: Exception) {
            log(null, "Error delivering event: ${e.message}")
        }
    }

    override fun close() {
        dispatcher.shutdown()
        if (!dispatcher.awaitTermination(SHUTDOWN_TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
            log(null, "Warning: gave up waiting for pending events to be sent")
            dispatcher.shutdownNow()
        }
    }

    private companion object {
        const val SHUTDOWN_TIMEOUT_SECONDS = 5L
    }
}

package io.github.arnonym.integrationtest

import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.io.Closeable
import java.io.File
import java.net.InetSocketAddress
import java.time.Duration
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors

/** One event envelope as delivered by ha-sip, tagged with which instance sent it. */
data class ReceivedEvent(
    val instance: String,
    val receivedAtMillis: Long,
    val payload: JsonObject,
) {
    val eventName: String get() = string("event") ?: "<no event field>"
    val internalId: String? get() = string("internal_id")
    val menuId: String? get() = string("menu_id")
    val digit: String? get() = string("digit")

    private fun string(key: String): String? = (payload[key] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content

    override fun toString(): String =
        buildString {
            append("[$instance] $eventName")
            menuId?.let { append(" menu_id=$it") }
            digit?.let { append(" digit=$it") }
        }
}

/**
 * Captures every [io.github.arnonym.event.Event] emitted by the instances
 * under test.
 *
 * ha-sip's Home Assistant webhook channel is a plain `POST $HA_BASE_URL/webhook/$HA_WEBHOOK_ID`
 * carrying the full envelope built by `buildWebhookEnvelope`, so pointing `HA_BASE_URL`
 * at this server and giving each instance a distinct `HA_WEBHOOK_ID` yields a complete,
 * per-instance-attributed event stream with no broker and no real Home Assistant involved.
 */
class EventCollector : Closeable {
    private val received = CopyOnWriteArrayList<ReceivedEvent>()
    private val monitor = Object()

    /** Arrival time of the most recent event, surviving [clear] so [awaitQuiet] can use it. */
    @Volatile
    private var lastEventAtMillis = 0L

    private val server: HttpServer =
        HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
            // NOT the default (null) executor: that one serves requests on the single
            // dispatcher thread, one at a time. Each ha-sip instance delivers its events
            // from one `EventSender` thread that blocks in `runBlocking { post }`, so a
            // serial server here would serialize the two instances against *each other* --
            // corrupting the very measurements these tests exist to take.
            executor = Executors.newCachedThreadPool { r -> Thread(r, "event-collector").apply { isDaemon = true } }
            // Anything that is not a webhook (tts_get_url, template, services, ...):
            // answer immediately, so a stray call fails fast instead of parking a call's
            // thread on a connect timeout. Scenarios use audio_file menus so this should
            // never fire; if it does, the log line below says which endpoint was hit.
            createContext("/api/") { exchange ->
                System.err.println("event-collector: unexpected HA call to ${exchange.requestURI}")
                exchange.respondEmptyJson()
            }
            // Text-to-speech, stalled on demand. A synthesis request is the one thing a
            // menu does that can take seconds, so holding it open is how a test makes one
            // call's menu handling slow enough to observe what it does (and does not)
            // delay elsewhere.
            createContext("/api/tts_get_url") { exchange ->
                ttsRequests.incrementAndGet()
                val stall = ttsStallMillis.get()
                if (stall > 0) {
                    if (VERBOSE) println("  event-collector: stalling TTS for ${stall}ms")
                    Thread.sleep(stall)
                }
                val audio = ttsAudio
                if (audio == null) {
                    // ha-sip falls back to its bundled error prompt, which is fine for
                    // scenarios that care about the delay rather than about the audio.
                    exchange.use { it.sendResponseHeaders(500, -1) }
                    return@createContext
                }
                exchange.use {
                    val body = """{"url": "$baseUrl/tts-audio/speech.wav"}""".toByteArray()
                    it.responseHeaders.add("Content-Type", "application/json")
                    it.sendResponseHeaders(200, body.size.toLong())
                    it.responseBody.write(body)
                }
            }
            // The audio the URL above points at -- the second leg of the round-trip, which
            // ha-sip downloads and converts before it can play anything.
            createContext("/api/tts-audio/") { exchange ->
                val audio = ttsAudio
                if (audio == null) {
                    exchange.use { it.sendResponseHeaders(404, -1) }
                    return@createContext
                }
                val bytes = audio.readBytes()
                exchange.use {
                    it.responseHeaders.add("Content-Type", "audio/wav")
                    it.sendResponseHeaders(200, bytes.size.toLong())
                    it.responseBody.write(bytes)
                }
            }
            start()
        }

    private val ttsStallMillis = java.util.concurrent.atomic.AtomicLong(0)
    private val ttsRequests = java.util.concurrent.atomic.AtomicInteger(0)

    /**
     * Audio served for synthesis requests, or `null` to fail them with a 500.
     *
     * Null by default: most scenarios only need TTS to be slow, and a failed request
     * still exercises the whole request/playback path via the bundled error prompt.
     */
    @Volatile
    var ttsAudio: File? = null

    /** Makes every subsequent TTS request block for [millis] before answering. */
    fun stallTts(millis: Long) = ttsStallMillis.set(millis)

    /** How many synthesis requests have arrived since [clear] -- zero proves a cache hit. */
    fun ttsRequestCount(): Int = ttsRequests.get()

    val baseUrl: String get() = "http://127.0.0.1:${server.address.port}/api"

    /** Registers a webhook endpoint for [instance]; pass the same id as its `HA_WEBHOOK_ID`. */
    fun register(instance: String) {
        server.createContext("/api/webhook/$instance") { exchange ->
            val body = exchange.requestBody.readBytes().decodeToString()
            val payload =
                try {
                    Json.parseToJsonElement(body) as? JsonObject
                } catch (e: Exception) {
                    null
                }
            if (payload == null) {
                System.err.println("event-collector: could not parse body from $instance: $body")
            } else {
                val event = ReceivedEvent(instance, System.currentTimeMillis(), payload)
                received.add(event)
                lastEventAtMillis = event.receivedAtMillis
                if (VERBOSE) println("  << $event")
                synchronized(monitor) { monitor.notifyAll() }
            }
            exchange.respondEmptyJson()
        }
    }

    /** Everything received since the last [clear], in arrival order. */
    fun events(): List<ReceivedEvent> = received.toList()

    fun events(instance: String): List<ReceivedEvent> = received.filter { it.instance == instance }

    fun clear() {
        received.clear()
        ttsRequests.set(0)
    }

    /**
     * Waits until nothing has arrived for [quietMillis], or gives up after [timeout].
     *
     * ha-sip delivers events asynchronously, and `call_disconnected` is *queued* just
     * before the call leaves its registry -- so "the instance reports no active calls"
     * does not mean "no events are still in flight". Clearing on that signal alone drops
     * a straggler into the next scenario's history, where it reads as an event emitted
     * after the disconnect and fails a scenario that did nothing wrong.
     *
     * Not a fixed sleep: quiet is usually reached on the first check, since delivery is a
     * loopback POST.
     */
    fun awaitQuiet(
        quietMillis: Long = QUIET_MILLIS,
        timeout: Duration = DEFAULT_TIMEOUT,
    ) {
        val deadline = System.nanoTime() + timeout.toNanos()
        while (true) {
            val sinceLastEvent = System.currentTimeMillis() - lastEventAtMillis
            if (sinceLastEvent >= quietMillis) return
            if (System.nanoTime() >= deadline) {
                System.err.println("event-collector: events still arriving after ${timeout.toMillis()}ms, giving up on quiet")
                return
            }
            Thread.sleep((quietMillis - sinceLastEvent).coerceIn(1, quietMillis))
        }
    }

    /**
     * Waits for the first event on [instance] named [eventName] satisfying [predicate].
     *
     * Matching runs over the whole history rather than draining a queue, so an event
     * that arrived *before* the wait started still counts. That matters: the SIP stack
     * routinely emits several events faster than the test can ask for them.
     */
    fun await(
        instance: String,
        eventName: String,
        timeout: Duration = DEFAULT_TIMEOUT,
        predicate: (ReceivedEvent) -> Boolean = { true },
    ): ReceivedEvent =
        awaitProbe(timeout, "[$instance] $eventName") {
            received.firstOrNull { it.instance == instance && it.eventName == eventName && predicate(it) }
        }

    /** Waits until [instance] has emitted at least [count] events named [eventName], returning all of them. */
    fun awaitCount(
        instance: String,
        eventName: String,
        count: Int,
        timeout: Duration = DEFAULT_TIMEOUT,
    ): List<ReceivedEvent> =
        awaitProbe(timeout, "[$instance] ${count}x $eventName") {
            events(instance).filter { it.eventName == eventName }.takeIf { it.size >= count }
        }

    /**
     * Asserts [eventNames] occur on [instance] in this relative order, waiting for the
     * last of them. Unrelated events in between are allowed -- SIP emits plenty.
     */
    fun awaitSequence(
        instance: String,
        vararg eventNames: String,
        timeout: Duration = DEFAULT_TIMEOUT,
    ) {
        awaitProbe(timeout, "[$instance] sequence ${eventNames.toList()}") {
            val actual = events(instance).map { it.eventName }
            if (containsInOrder(actual, eventNames.toList())) Unit else null
        }
    }

    /** Fails if [instance] emitted anything after its (last) `call_disconnected`. */
    fun assertNothingAfterDisconnect(instance: String) {
        val instanceEvents = events(instance)
        val lastDisconnect = instanceEvents.indexOfLast { it.eventName == "call_disconnected" }
        if (lastDisconnect < 0) return
        val trailing = instanceEvents.drop(lastDisconnect + 1)
        check(trailing.isEmpty()) { "[$instance] emitted events after call_disconnected: $trailing" }
    }

    private fun <T : Any> awaitProbe(
        timeout: Duration,
        what: String,
        probe: () -> T?,
    ): T {
        val deadline = System.nanoTime() + timeout.toNanos()
        while (true) {
            probe()?.let { return it }
            val remainingMillis = (deadline - System.nanoTime()) / 1_000_000
            if (remainingMillis <= 0) {
                throw AssertionError(
                    "Timed out after ${timeout.toMillis()}ms waiting for $what.\nEvents received:\n" +
                        received.joinToString("\n") { "  $it" }.ifEmpty { "  (none)" },
                )
            }
            synchronized(monitor) { monitor.wait(remainingMillis.coerceAtMost(25)) }
        }
    }

    override fun close() {
        server.stop(0)
    }

    companion object {
        val DEFAULT_TIMEOUT: Duration = Duration.ofSeconds(20)

        /** Long enough to cover a loopback POST several times over, short enough to pay per scenario. */
        private const val QUIET_MILLIS = 150L
        private val VERBOSE = System.getProperty("hasip.verbose") == "true"

        /** True when [expected] appears as a (not necessarily contiguous) subsequence of [actual]. */
        fun containsInOrder(
            actual: List<String>,
            expected: List<String>,
        ): Boolean {
            var index = 0
            for (name in actual) {
                if (index < expected.size && name == expected[index]) index++
            }
            return index == expected.size
        }
    }
}

private fun HttpExchange.respondEmptyJson() {
    use {
        responseHeaders.add("Content-Type", "application/json")
        sendResponseHeaders(200, 2)
        responseBody.write("{}".toByteArray())
    }
}

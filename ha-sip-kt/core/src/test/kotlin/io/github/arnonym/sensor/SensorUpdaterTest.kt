package io.github.arnonym.sensor

import io.kotest.matchers.shouldBe
import kotlinx.serialization.json.JsonObject
import org.junit.jupiter.api.Test
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

class SensorUpdaterTest {
    /**
     * Records what reached Home Assistant, in the order it got there.
     *
     * [gate] stands in for the HTTP round-trip a real write is: holding the first write
     * open is what lets a test recreate the interleaving that used to lose -- the
     * placeholder issued first but delivered last.
     */
    private class RecordingSink : SensorSink {
        val writes = CopyOnWriteArrayList<Pair<String, String>>()
        val gate = CountDownLatch(1)

        @Volatile
        var blockFirstWrite = false

        override fun write(
            entityId: String,
            state: String,
            attributes: JsonObject,
        ) {
            if (blockFirstWrite) {
                blockFirstWrite = false
                check(gate.await(10, TimeUnit.SECONDS)) { "gate was never released" }
            }
            writes.add(entityId to state)
        }

        fun statesOf(entityId: String): List<String> = writes.filter { it.first == entityId }.map { it.second }
    }

    private fun updater(sink: SensorSink) = SensorUpdater(sink, SensorConfig(enabled = true, entityPrefix = "ha_sip"), listOf(1))

    @Test
    fun `registration status published after initialization wins, however slow the first write is`() {
        val sink = RecordingSink()
        val updater = updater(sink)
        sink.blockFirstWrite = true

        updater.initializeSensors()
        // A real OnRegState arrives on a pjsip callback thread while the placeholders are
        // still in flight -- the whole point of the scenario.
        val registration = thread { updater.updateRegistrationStatus(1, 200, "OK") }
        registration.join()
        sink.gate.countDown()

        updater.close()

        sink.statesOf("sensor.ha_sip_registration_1") shouldBe listOf("unknown", "registered")
    }

    @Test
    fun `initialization publishes a placeholder for every sensor of every account`() {
        val sink = RecordingSink()
        val updater =
            SensorUpdater(sink, SensorConfig(enabled = true, entityPrefix = "ha_sip"), listOf(1, 2))

        updater.initializeSensors()
        updater.close()

        sink.writes shouldBe
            listOf(
                "sensor.ha_sip_account_1" to "false",
                "sensor.ha_sip_registration_1" to "unknown",
                "sensor.ha_sip_last_call_1" to "none",
                "sensor.ha_sip_account_2" to "false",
                "sensor.ha_sip_registration_2" to "unknown",
                "sensor.ha_sip_last_call_2" to "none",
            )
    }

    @Test
    fun `close drains writes that are still queued`() {
        val sink = RecordingSink()
        val updater = updater(sink)
        sink.blockFirstWrite = true

        updater.initializeSensors()
        updater.updateRegistrationStatus(1, 200, "OK")
        sink.gate.countDown()
        updater.close()

        sink.writes.size shouldBe 4
    }

    @Test
    fun `disabled sensors write nothing at all`() {
        val sink = RecordingSink()
        val updater =
            SensorUpdater(sink, SensorConfig(enabled = false, entityPrefix = "ha_sip"), listOf(1))

        updater.initializeSensors()
        updater.updateRegistrationStatus(1, 200, "OK")
        updater.close()

        sink.writes shouldBe emptyList()
    }
}

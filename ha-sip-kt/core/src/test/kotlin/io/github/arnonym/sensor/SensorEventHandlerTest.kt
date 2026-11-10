package io.github.arnonym.sensor

import io.kotest.matchers.shouldBe
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.jupiter.api.Test

class SensorEventHandlerTest {
    private class FakeSensorUpdates : SensorUpdates {
        val activeCalls = mutableListOf<Int>()
        val inactiveCalls = mutableListOf<Int>()
        val lastCalls = mutableListOf<Pair<Int, String>>()

        override fun setCallActive(
            accountIndex: Int,
            callInfo: JsonObject,
        ) {
            activeCalls.add(accountIndex)
        }

        override fun setCallInactive(accountIndex: Int) {
            inactiveCalls.add(accountIndex)
        }

        override fun updateRegistrationStatus(
            accountIndex: Int,
            code: Int,
            reason: String,
        ) {}

        override fun updateLastCall(
            accountIndex: Int,
            direction: String,
            callInfo: JsonObject?,
        ) {
            lastCalls.add(accountIndex to direction)
        }

        override fun initializeSensors() {}
    }

    private fun event(build: kotlinx.serialization.json.JsonObjectBuilder.() -> Unit): JsonObject = buildJsonObject(build)

    @Test
    fun `incoming call tracked as incoming direction`() {
        val fake = FakeSensorUpdates()
        val handler = SensorEventHandler(fake)
        handler.handleEvent(
            event {
                put("event", "incoming_call")
                put("sip_account", 1)
            },
        )
        handler.handleEvent(
            event {
                put("event", "call_disconnected")
                put("sip_account", 1)
            },
        )
        fake.activeCalls shouldBe listOf(1)
        fake.inactiveCalls shouldBe listOf(1)
        fake.lastCalls shouldBe listOf(1 to "incoming")
    }

    @Test
    fun `outgoing call tracked as outgoing direction`() {
        val fake = FakeSensorUpdates()
        val handler = SensorEventHandler(fake)
        handler.handleEvent(
            event {
                put("event", "outgoing_call_initiated")
                put("sip_account", 2)
            },
        )
        handler.handleEvent(
            event {
                put("event", "call_established")
                put("sip_account", 2)
            },
        )
        handler.handleEvent(
            event {
                put("event", "call_disconnected")
                put("sip_account", 2)
            },
        )
        fake.activeCalls shouldBe listOf(2)
        fake.lastCalls shouldBe listOf(2 to "outgoing")
    }

    @Test
    fun `missing sip_account is ignored`() {
        val fake = FakeSensorUpdates()
        val handler = SensorEventHandler(fake)
        handler.handleEvent(event { put("event", "incoming_call") })
        fake.activeCalls shouldBe emptyList()
    }

    @Test
    fun `disconnect without prior direction defaults to incoming`() {
        val fake = FakeSensorUpdates()
        val handler = SensorEventHandler(fake)
        handler.handleEvent(
            event {
                put("event", "call_disconnected")
                put("sip_account", 3)
            },
        )
        fake.lastCalls shouldBe listOf(3 to "incoming")
    }
}

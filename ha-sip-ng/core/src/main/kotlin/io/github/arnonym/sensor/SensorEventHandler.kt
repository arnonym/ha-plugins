package io.github.arnonym.sensor

import io.github.arnonym.json.intValueOrNull
import io.github.arnonym.json.stringValueOrNull
import kotlinx.serialization.json.JsonObject
import java.util.concurrent.ConcurrentHashMap

class SensorEventHandler(private val sensorUpdater: SensorUpdates) {
    private val callDirections = ConcurrentHashMap<Int, String>()

    fun handleEvent(event: JsonObject) {
        val eventType = event["event"]?.stringValueOrNull()
        val sipAccount = event["sip_account"]?.intValueOrNull() ?: return
        when (eventType) {
            "incoming_call" -> {
                callDirections[sipAccount] = "incoming"
                sensorUpdater.setCallActive(sipAccount, event)
            }
            "outgoing_call_initiated" -> {
                callDirections[sipAccount] = "outgoing"
            }
            "call_established" -> {
                sensorUpdater.setCallActive(sipAccount, event)
            }
            "call_disconnected" -> {
                sensorUpdater.setCallInactive(sipAccount)
                val direction = callDirections.remove(sipAccount) ?: "incoming"
                sensorUpdater.updateLastCall(sipAccount, direction, event)
            }
        }
    }
}

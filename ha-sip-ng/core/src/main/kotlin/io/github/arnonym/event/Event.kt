package io.github.arnonym.event

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive

sealed class Event(val eventName: String) {
    open fun extraFields(): Map<String, JsonElement> = emptyMap()

    data object IncomingCall : Event("incoming_call")

    data object OutgoingCallInitiated : Event("outgoing_call_initiated")

    data object CallEstablished : Event("call_established")

    data object CallDisconnected : Event("call_disconnected")

    data object RingTimeout : Event("ring_timeout")

    data class EnteredMenu(val menuId: String) : Event("entered_menu") {
        override fun extraFields() = mapOf("menu_id" to JsonPrimitive(menuId))
    }

    data class DtmfDigit(val digit: String) : Event("dtmf_digit") {
        override fun extraFields() = mapOf("digit" to JsonPrimitive(digit))
    }

    data class Timeout(val menuId: String?) : Event("timeout") {
        override fun extraFields() = mapOf("menu_id" to (menuId?.let { JsonPrimitive(it) } ?: JsonNull))
    }

    data class PlaybackDoneAudioFile(val audioFile: String) : Event("playback_done") {
        override fun extraFields() =
            mapOf(
                "type" to JsonPrimitive("audio_file"),
                "audio_file" to JsonPrimitive(audioFile),
            )
    }

    data class PlaybackDoneMessage(val message: String) : Event("playback_done") {
        override fun extraFields() =
            mapOf(
                "type" to JsonPrimitive("message"),
                "message" to JsonPrimitive(message),
            )
    }

    data class RecordingStarted(val recordingFile: String) : Event("recording_started") {
        override fun extraFields() = mapOf("recording_file" to JsonPrimitive(recordingFile))
    }

    data class RecordingStopped(val recordingFile: String) : Event("recording_stopped") {
        override fun extraFields() = mapOf("recording_file" to JsonPrimitive(recordingFile))
    }
}

package io.github.arnonym.integrationtest

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test
import java.io.File

/**
 * Call recording: the one feature whose result is a file rather than an event.
 *
 * Worth driving end to end because the events alone cannot tell the difference between
 * a recorder that is attached to the call's audio and one that was created and never
 * fed -- both emit `recording_started`. Only the bytes on disk distinguish them.
 */
class RecordingTest {
    private val stack = DirectIpStack
    private val collector = DirectIpStack.collector

    @BeforeEach
    fun resetStack() = stack.reset()

    @AfterEach
    fun assertNoTrailingEvents() {
        collector.assertNothingAfterDisconnect(DirectIpStack.CALLER)
        collector.assertNothingAfterDisconnect(DirectIpStack.CALLEE)
    }

    @Test
    @DisplayName("start_recording captures the call's audio to a playable wav")
    fun recordingCapturesAudio() {
        stack.callee(CalleeConfig(Menus.navigation))
        val target = File(DirectIpStack.recordingsDir, "call.wav")
        stack.caller.dial()
        collector.await(DirectIpStack.CALLER, "call_established")

        stack.caller.startRecording(target)
        collector.await(DirectIpStack.CALLER, "recording_started")
            .payload["recording_file"].toString() shouldBe "\"${target.absolutePath}\""

        // Record across the callee's prompt, so there is real inbound audio to capture
        // rather than silence.
        collector.await(DirectIpStack.CALLEE, "playback_done")

        stack.caller.send("""{"command": "stop_recording", "number": ${DirectIpStack.calleeUri.jsonString()}}""")
        collector.await(DirectIpStack.CALLER, "recording_stopped")

        check(target.isFile) { "recording file was never created at $target" }
        // A wav header alone is 44 bytes; anything close to that means the recorder was
        // attached to nothing. One second of 8 kHz 16-bit mono is ~16 kB.
        check(target.length() > 8_000) { "recording is suspiciously small: ${target.length()} bytes" }
        check(target.readBytes().copyOfRange(0, 4).decodeToString() == "RIFF") { "recording is not a RIFF/wav file" }
        // Not the same claim as "the bytes are there": pjmedia writes the chunk sizes as
        // zero and only patches them when the file is closed, so this is what says
        // `stop_recording` actually finalized the wav rather than just detaching from it.
        // A player that trusts the header sees an empty file otherwise.
        check(awaitFinalizedWav(target).samples.size > 4_000) { "finalized recording holds too few samples" }

        stack.caller.hangup()
        collector.await(DirectIpStack.CALLER, "call_disconnected")
    }

    @Test
    @DisplayName("a recording left running is finalized when the call disconnects")
    fun disconnectFinalizesAnOpenRecording() {
        stack.callee(CalleeConfig(Menus.navigation))
        val target = File(DirectIpStack.recordingsDir, "hangup.wav")
        stack.caller.dial()
        collector.await(DirectIpStack.CALLER, "call_established")

        stack.caller.startRecording(target)
        collector.await(DirectIpStack.CALLER, "recording_started")
        collector.await(DirectIpStack.CALLEE, "playback_done")

        // No stop_recording: hanging up mid-recording is what actually happens when a
        // caller gives up, and the file still has to be closed properly.
        stack.caller.hangup()
        collector.await(DirectIpStack.CALLER, "recording_stopped")
        collector.await(DirectIpStack.CALLER, "call_disconnected")

        check(target.isFile) { "recording file was never created at $target" }
        check(awaitFinalizedWav(target).samples.size > 4_000) {
            "recording was not finalized on disconnect: ${target.length()} bytes"
        }
    }

    @Test
    @DisplayName("a recording requested before media is up starts once media arrives")
    fun recordingRequestedBeforeMediaStartsLater() {
        stack.callee(CalleeConfig(Menus.navigation))
        val target = File(DirectIpStack.recordingsDir, "early.wav")

        // Fired at `incoming_call`, which on the callee precedes media negotiation --
        // ha-sip has to remember the request and honour it in `onCallMediaState`.
        stack.caller.dial()
        val callee = stack.callee(CalleeConfig(Menus.navigation))
        val incoming = collector.await(DirectIpStack.CALLEE, "incoming_call")
        val calleeCallId = requireNotNull(incoming.internalId) { "incoming_call carried no internal_id" }
        callee.send(
            """{"command": "start_recording", "number": ${calleeCallId.jsonString()}, """ +
                """"recording_file": ${target.absolutePath.jsonString()}}""",
        )

        collector.await(DirectIpStack.CALLEE, "recording_started")
        collector.await(DirectIpStack.CALLEE, "playback_done")

        stack.caller.hangup()
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
        check(target.isFile) { "deferred recording never created a file at $target" }
        check(awaitFinalizedWav(target).samples.size > 4_000) {
            "deferred recording never captured audio: ${target.length()} bytes"
        }
    }
}

internal fun HaSipInstance.startRecording(target: File) {
    send(
        """{"command": "start_recording", "number": ${DirectIpStack.calleeUri.jsonString()}, """ +
            """"recording_file": ${target.absolutePath.jsonString()}}""",
    )
}

package io.github.arnonym.integrationtest

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test

/**
 * End-to-end call flow between two real ha-sip instances over a direct-IP SIP call.
 *
 * The backbone of the suite: establishment, DTMF, and answering. [MenuNavigationTest]
 * covers what keypresses mean once a call is up, [TimeoutTest] what happens when nothing
 * is pressed at all, and [CallScreeningTest] which calls get answered in the first place.
 */
class CallFlowTest {
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
    @DisplayName("a direct-IP call is established and the callee's menu plays")
    fun directIpCallEstablishes() {
        stack.callee(CalleeConfig(Menus.navigation))
        stack.caller.dial()

        collector.awaitSequence(DirectIpStack.CALLER, "outgoing_call_initiated", "call_established")
        collector.awaitSequence(DirectIpStack.CALLEE, "incoming_call", "call_established", "entered_menu", "playback_done")

        collector.await(DirectIpStack.CALLEE, "entered_menu").menuId shouldBe "main"
        collector.await(DirectIpStack.CALLEE, "playback_done").payload["type"].toString() shouldBe "\"audio_file\""

        // No registrar is configured on either side, so nothing should have tried to register.
        stack.caller.logContains(Regex("OnRegState")) shouldBe false
    }

    @Test
    @DisplayName("a DTMF choice enters the submenu and its post_action hangs up")
    fun dtmfChoiceNavigatesAndHangsUp() {
        stack.callee(CalleeConfig(Menus.navigation))
        stack.caller.dial()
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "main" }

        stack.caller.sendDtmf("1")

        collector.await(DirectIpStack.CALLEE, "dtmf_digit").digit shouldBe "1"
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "chosen" }
        // post_action: hangup fires once the prompt for "chosen" has finished playing.
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
        collector.await(DirectIpStack.CALLER, "call_disconnected")
    }

    @Test
    @DisplayName("multiple DTMF digits are handled in order")
    fun multipleDigitsKeepOrder() {
        stack.callee(CalleeConfig(Menus.navigation))
        stack.caller.dial()
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "main" }

        // "9" descends into level1, "2" then selects level2 -- so a reordering or a
        // dropped digit cannot reach the hangup at the bottom.
        stack.caller.sendDtmf("9")
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "level1" }
        stack.caller.sendDtmf("2")

        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "level2" }
        collector.awaitCount(DirectIpStack.CALLEE, "dtmf_digit", 2).map { it.digit } shouldBe listOf("9", "2")
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("DTMF still reaches the peer after the call has been silent for seconds")
    fun dtmfWorksLateInACall() {
        stack.callee(CalleeConfig(Menus.navigation))
        stack.caller.dial()

        // Wait out the prompt, then keep quiet well past pjsua's one-second sound-device
        // idle timer. Everything on the media path is now dormant, which is the state a
        // real automation finds a call in when it decides to press a key.
        collector.await(DirectIpStack.CALLEE, "playback_done")
        Thread.sleep(3_000)

        stack.caller.sendDtmf("1")

        collector.await(DirectIpStack.CALLEE, "dtmf_digit").digit shouldBe "1"
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "chosen" }
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("an explicit answer command connects a call the callee was only listening to")
    fun explicitAnswerCommandConnects() {
        // LISTEN means `accept()` sends 180 Ringing and never answers on its own.
        stack.callee(CalleeConfig(menuYaml = null, answerMode = "LISTEN"))
        stack.caller.dial(ringTimeout = 30.0)

        val incoming = collector.await(DirectIpStack.CALLEE, "incoming_call")
        val calleeCallId = requireNotNull(incoming.internalId) { "incoming_call carried no internal_id" }
        collector.events(DirectIpStack.CALLEE).any { it.eventName == "call_established" } shouldBe false

        stack.callee(CalleeConfig(menuYaml = null, answerMode = "LISTEN"))
            .send("""{"command": "answer", "number": ${calleeCallId.jsonString()}, "menu": ${Menus.simple("answered")}}""")

        collector.await(DirectIpStack.CALLEE, "call_established")
        collector.await(DirectIpStack.CALLEE, "entered_menu").menuId shouldBe "answered"

        stack.caller.hangup()
        collector.await(DirectIpStack.CALLER, "call_disconnected")
    }
}

/** Dials the callee by its direct-IP URI. Optionally attaches a menu for the outgoing leg. */
internal fun HaSipInstance.dial(
    ringTimeout: Double = 30.0,
    menu: String? = null,
) {
    val menuPart = menu?.let { ""","menu": $it""" } ?: ""
    send("""{"command": "dial", "number": ${DirectIpStack.calleeUri.jsonString()}, "ring_timeout": $ringTimeout$menuPart}""")
}

internal fun HaSipInstance.sendDtmf(digits: String) {
    // RFC 2833 rather than in-band: out-of-band signalling is deterministic between
    // two pjsip endpoints, whereas in-band tones depend on codec and DSP detection.
    send("""{"command": "send_dtmf", "number": ${DirectIpStack.calleeUri.jsonString()}, "digits": "$digits", "method": "rfc2833"}""")
}

internal fun HaSipInstance.hangup() {
    send("""{"command": "hangup", "number": ${DirectIpStack.calleeUri.jsonString()}}""")
}

internal fun String.jsonString(): String = "\"" + replace("\\", "\\\\").replace("\"", "\\\"") + "\""

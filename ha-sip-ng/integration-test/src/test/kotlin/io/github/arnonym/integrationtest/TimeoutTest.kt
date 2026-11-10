package io.github.arnonym.integrationtest

import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test

/**
 * ha-sip's call timing contract: ring timeout, `answer_after`, settle time, and the
 * menu inactivity timeout.
 *
 * They measure behaviour from the outside, not the shape of the code underneath: the
 * whole set went green unchanged across a rewrite of the timing machinery into per-call
 * timers and back again to the shared 10 ms tick.
 *
 * Bounds are deliberately loose at the top end (real SIP, real processes, shared CI
 * machines) and tight at the bottom end, where a regression would actually show up.
 */
class TimeoutTest {
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
    @DisplayName("ring timeout hangs up a call the callee never answers")
    fun ringTimeoutHangsUpUnansweredCall() {
        // LISTEN: `accept()` sends 180 Ringing and never answers on its own.
        stack.callee(CalleeConfig(menuYaml = null, answerMode = "LISTEN"))
        stack.caller.dial(ringTimeout = 2.0)

        val initiated = collector.await(DirectIpStack.CALLER, "outgoing_call_initiated")
        val timedOut = collector.await(DirectIpStack.CALLER, "ring_timeout")
        assertElapsedAround(initiated, timedOut, expectedMillis = 2_000, label = "ring timeout")

        collector.await(DirectIpStack.CALLER, "call_disconnected")

        // The tick would otherwise re-fire this every 10 ms until DISCONNECTED arrived,
        // since the branch reads nothing it mutates; `ringTimeoutFired` latches it.
        val count = collector.events(DirectIpStack.CALLER).count { it.eventName == "ring_timeout" }
        check(count == 1) { "expected exactly one ring_timeout, got $count" }
    }

    @Test
    @DisplayName("answer_after and settle time delay establishment on the callee")
    fun answerAfterAndSettleTimeDelayEstablishment() {
        stack.callee(CalleeConfig(Menus.deferredAnswer(answerAfter = 2), settleTime = "0.5"))
        stack.caller.dial()

        val incoming = collector.await(DirectIpStack.CALLEE, "incoming_call")
        val established = collector.await(DirectIpStack.CALLEE, "call_established")
        // answer_after (2 s, deferred answer) + settle time (0.5 s, delay between
        // CONFIRMED and entering the menu) are additive.
        assertElapsedAround(incoming, established, expectedMillis = 2_500, label = "answer_after + settle")

        collector.await(DirectIpStack.CALLEE, "entered_menu")
        stack.caller.hangup()
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("menu inactivity timeout enters the timeout choice and hangs up")
    fun menuInactivityTimeoutFires() {
        stack.callee(CalleeConfig(Menus.inactivityTimeout(timeout = 2)))
        stack.caller.dial()

        val enteredMain = collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "main" }
        val timedOut = collector.await(DirectIpStack.CALLEE, "timeout")
        // The timeout event names the menu that timed out, not the one being entered.
        check(timedOut.menuId == "main") { "expected timeout for menu 'main', got ${timedOut.menuId}" }
        assertElapsedAround(enteredMain, timedOut, expectedMillis = 2_000, label = "menu inactivity timeout")

        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "timed-out" }
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("entering a menu with a shorter timeout shortens the pending deadline immediately")
    fun shrinkingMenuTimeoutTakesEffectImmediately() {
        // The tick gets this for free by re-reading `menu.timeout` a hundred times a
        // second. It is the trap any timer-based replacement falls into: a deadline armed
        // once when the call is established waits the outer menu's 60 s instead of the
        // inner menu's 2 s.
        stack.callee(CalleeConfig(Menus.shrinkingTimeout))
        stack.caller.dial()
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "main" }

        stack.caller.sendDtmf("1")
        val enteredImpatient = collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "impatient" }

        val timedOut = collector.await(DirectIpStack.CALLEE, "timeout", timeout = java.time.Duration.ofSeconds(15))
        check(timedOut.menuId == "impatient") { "expected timeout for menu 'impatient', got ${timedOut.menuId}" }
        assertElapsedAround(enteredImpatient, timedOut, expectedMillis = 2_000, label = "shortened menu timeout")

        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("a call blocked in a slow menu action does not delay another call's timeout")
    fun concurrentCallsAreIndependent() {
        stack.callee(CalleeConfig(Menus.navigation))
        collector.stallTts(TTS_STALL_MILLIS)
        try {
            // Call 1 rings an address that never answers, so only the ring timeout can end
            // it. This is the call whose timing is under test, and it is started first so
            // its deadline falls squarely inside call 2's stall.
            stack.caller.send(
                """{"command": "dial", "number": ${DirectIpStack.blackholeUri.jsonString()}, "ring_timeout": 2}""",
            )
            val ringingSince = collector.await(DirectIpStack.CALLER, "outgoing_call_initiated")

            // Call 2 reaches the real callee with a `message` menu, so once it establishes
            // the caller blocks in createAndGetTts for TTS_STALL_MILLIS.
            stack.caller.dial(menu = Menus.spokenMessage())
            collector.await(DirectIpStack.CALLER, "call_established")

            // Call 1's ring timeout must still fire on schedule. Every call's deadlines are
            // evaluated on one shared tick thread, so this only holds because the synthesis
            // itself runs off it -- with a blocking TTS fetch this measured ~8300ms.
            val timedOut =
                collector.await(DirectIpStack.CALLER, "ring_timeout", timeout = java.time.Duration.ofSeconds(30))
            assertElapsedAround(ringingSince, timedOut, expectedMillis = 2_000, label = "ring timeout beside a slow call")
        } finally {
            collector.stallTts(0)
        }
    }
}

/** Long enough to dwarf the 2 s ring timeout it runs alongside, short enough to keep the suite quick. */
private const val TTS_STALL_MILLIS = 8_000L

/**
 * Asserts the gap between two events is close to [expectedMillis].
 *
 * Lower bound is tight (a timeout firing early is a real defect); upper bound is
 * generous, to absorb process scheduling, SIP retransmission timers and the ~1 s
 * audio prompt that plays alongside.
 */
private fun assertElapsedAround(
    from: ReceivedEvent,
    to: ReceivedEvent,
    expectedMillis: Long,
    label: String,
) {
    val elapsed = to.receivedAtMillis - from.receivedAtMillis
    val lower = (expectedMillis * 0.85).toLong()
    val upper = expectedMillis + 2_500
    check(elapsed in lower..upper) {
        "$label took ${elapsed}ms, expected ~${expectedMillis}ms (allowed $lower..${upper}ms); " +
            "measured between ${from.eventName} and ${to.eventName}"
    }
}

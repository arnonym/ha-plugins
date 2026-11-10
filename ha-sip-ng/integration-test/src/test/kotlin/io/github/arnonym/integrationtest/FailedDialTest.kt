package io.github.arnonym.integrationtest

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.MethodOrderer
import org.junit.jupiter.api.Order
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestMethodOrder
import java.time.Duration

/**
 * A `dial` that never gets an INVITE out of the door.
 *
 * pjsua rejects an unparsable destination inside `makeCall` itself, which throws before
 * the call exists as far as SIP is concerned. The `Call` object, however, has already put
 * itself in the registry by then -- its constructor does that -- so the failure path has
 * to take it back out again. Nothing else ever will: `forgetCall` runs on the DISCONNECTED
 * state transition, and that never arrives for a call pjsua never created.
 *
 * Left registered, the entry answers `state` queries forever, makes the next `dial` for
 * that number bail out with "call already in progress", and -- the one a Home Assistant
 * user actually notices -- has the tick fire a `ring_timeout` webhook for a call that
 * never rang. The scenarios below pin all three, plus the fact that the process survives
 * at all; the equivalent bug killed the Python add-on's MQTT loop outright.
 *
 * Ordered, unusually for this suite, for the sake of the *failure* message. A leaked call
 * cannot be hung up -- there is no pjsua call behind it -- so it outlives the scenario
 * that created it and the next `reset()` dies on "still has active calls". Whichever
 * scenario runs first, the suite fails; running the one that asserts on the registry
 * first is what makes the first failure name the actual defect.
 */
@TestMethodOrder(MethodOrderer.OrderAnnotation::class)
class FailedDialTest {
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
    @Order(1)
    @DisplayName("a dial to an unparsable URI leaves no call behind and fires no webhooks")
    fun failedDialLeavesNoCallBehind() {
        val caller = stack.caller
        val mark = caller.logMark()
        caller.dialRaw(UNPARSABLE_URI, ringTimeout = RING_TIMEOUT_SECONDS)

        caller.awaitLog(DIAL_FAILED, from = mark)

        // The registry view a `hangup`/`send_dtmf` command would resolve against.
        caller.registeredCallIds() shouldBe emptyList()

        // Sleep rather than await: the assertion is about an event that must *not* arrive,
        // and the deadline it would arrive on is the ring timeout. Add a margin for the
        // 10 ms tick and process scheduling.
        Thread.sleep((RING_TIMEOUT_SECONDS * 1000).toLong() + 1_500)

        // Nothing at all, not just no ring_timeout: `outgoing_call_initiated` must stay on
        // the success path too, or Home Assistant is told a call started that never did.
        collector.events(DirectIpStack.CALLER).map { it.eventName } shouldBe emptyList()
        caller.isAlive shouldBe true
    }

    @Test
    @Order(2)
    @DisplayName("the same number can be dialled again after a failed dial")
    fun failedDialDoesNotBlockRetrying() {
        val caller = stack.caller
        val firstMark = caller.logMark()
        caller.dialRaw(UNPARSABLE_URI)
        caller.awaitLog(DIAL_FAILED, from = firstMark)

        // A second attempt has to reach pjsua again. If the first one left its registry
        // entry behind, `handleDial` short-circuits on `isActive` instead -- the failure
        // mode that makes a mistyped number in an automation stick until ha-sip is
        // restarted. Whichever line comes first after the mark decides which happened.
        val secondMark = caller.logMark()
        caller.dialRaw(UNPARSABLE_URI)
        val outcome =
            caller.awaitLog(
                Regex("${DIAL_FAILED.pattern}|$ALREADY_IN_PROGRESS"),
                Duration.ofSeconds(10),
                from = secondMark,
            )
        check(!outcome.contains(ALREADY_IN_PROGRESS)) { "second dial never reached pjsua: $outcome" }
    }

    @Test
    @Order(3)
    @DisplayName("a real call still works after a failed dial")
    fun failedDialDoesNotWedgeTheStack() {
        val caller = stack.caller
        val mark = caller.logMark()
        caller.dialRaw(UNPARSABLE_URI)
        caller.awaitLog(DIAL_FAILED, from = mark)

        // The endpoint, the account and the command channel all have to be untouched by
        // the failure -- an aborted call that took the SIP stack down with it would be a
        // worse regression than the leak this guards.
        stack.callee(CalleeConfig(Menus.navigation))
        caller.dial()
        collector.awaitSequence(DirectIpStack.CALLER, "outgoing_call_initiated", "call_established")
        caller.hangup()
        collector.await(DirectIpStack.CALLER, "call_disconnected")
    }
}

/**
 * No scheme, so pjsip's URI parser rejects it and `makeCall` throws.
 *
 * Deliberately not an unreachable host: that parses fine, gets an INVITE sent, and ends
 * up in the perfectly ordinary ring-timeout path this test is trying to stay out of.
 */
private const val UNPARSABLE_URI = "definitely not a sip uri"

/**
 * The dial has failed and ha-sip has said so -- by either route.
 *
 * Handled in `makeCall`, it is the first; unhandled, the pjsua2 exception unwinds into the
 * stdin reader's catch-all and becomes the second. Matching both on purpose: an anchor
 * that only the fixed code can log would make every assertion below unreachable on the
 * broken code, and these scenarios are supposed to fail on the leak itself, not on a
 * missing log line.
 */
private val DIAL_FAILED = Regex("Error making call to|Error handling command")

private const val ALREADY_IN_PROGRESS = "call already in progress"

/** Short, because two of the three scenarios wait it out to prove nothing fires. */
private const val RING_TIMEOUT_SECONDS = 1.0

/** [dial] always targets the callee; a failed dial is precisely about some other number. */
private fun HaSipInstance.dialRaw(
    number: String,
    ringTimeout: Double = 30.0,
) = send("""{"command": "dial", "number": ${number.jsonString()}, "ring_timeout": $ringTimeout}""")

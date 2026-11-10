package io.github.arnonym.integrationtest

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test
import java.time.Duration

/**
 * Who gets answered: the answer mode, the SIP code a rejection carries, and the
 * caller-id allow/block lists.
 *
 * The distinction that matters throughout is *rejected* versus *not answered*. A
 * rejection is an immediate SIP failure response and the caller knows straight away; a
 * screened-out call is downgraded to LISTEN, which rings until something else -- here,
 * the caller's own ring timeout -- gives up. Getting these two confused is the kind of
 * mistake that silently turns a door intercom into an open line.
 */
class CallScreeningTest {
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
    @DisplayName("REJECT answers with the configured SIP code instead of connecting")
    fun rejectModeUsesConfiguredSipCode() {
        val callee =
            stack.callee(
                CalleeConfig(menuYaml = null, answerMode = "REJECT", sipOptions = "--reject-sip-code 486"),
            )
        val mark = callee.logMark()
        stack.caller.dial(ringTimeout = 30.0)

        callee.awaitLog(Regex("Rejecting call with SIP code 486"), from = mark)

        // Rejected, not merely unanswered: the caller is released immediately rather than
        // ringing out, which is the whole point of REJECT over LISTEN.
        collector.await(DirectIpStack.CALLER, "call_disconnected", timeout = Duration.ofSeconds(10))
        collector.events(DirectIpStack.CALLER).none { it.eventName == "call_established" } shouldBe true
        collector.events(DirectIpStack.CALLER).none { it.eventName == "ring_timeout" } shouldBe true
    }

    @Test
    @DisplayName("a blocked caller is not answered and rings out")
    fun blockedCallerIsNeverAnswered() {
        // The callee sees the caller's URI as `sip:a@...`, so `a` is the parsed number.
        stack.callee(CalleeConfig(Menus.screened(blocked = listOf("a"))))
        stack.caller.dial(ringTimeout = 2.0)

        // The call still arrives -- blocking downgrades the answer mode, it does not make
        // the INVITE disappear, and an automation may still want to know someone called.
        collector.await(DirectIpStack.CALLEE, "incoming_call")

        collector.await(DirectIpStack.CALLER, "ring_timeout")
        collector.events(DirectIpStack.CALLEE).none { it.eventName == "call_established" } shouldBe true
        collector.await(DirectIpStack.CALLER, "call_disconnected")
    }

    @Test
    @DisplayName("a caller on the allow list is answered normally")
    fun allowedCallerIsAnswered() {
        stack.callee(CalleeConfig(Menus.screened(allowed = listOf("a"))))
        stack.caller.dial()

        collector.await(DirectIpStack.CALLEE, "call_established")
        collector.await(DirectIpStack.CALLEE, "entered_menu").menuId shouldBe "main"

        stack.caller.hangup()
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("a caller absent from the allow list is not answered")
    fun callerNotOnAllowListIsNeverAnswered() {
        stack.callee(CalleeConfig(Menus.screened(allowed = listOf("somebody-else"))))
        stack.caller.dial(ringTimeout = 2.0)

        collector.await(DirectIpStack.CALLEE, "incoming_call")
        collector.await(DirectIpStack.CALLER, "ring_timeout")
        collector.events(DirectIpStack.CALLEE).none { it.eventName == "call_established" } shouldBe true
        collector.await(DirectIpStack.CALLER, "call_disconnected")
    }

    @Test
    @DisplayName("configuring both allow and block lists refuses to answer anyone")
    fun bothListsIsTreatedAsMisconfiguration() {
        // Ambiguous configuration, so ha-sip fails closed rather than guessing which list
        // wins -- worth pinning, because the safe direction is not the obvious one.
        val callee = stack.callee(CalleeConfig(Menus.screened(allowed = listOf("a"), blocked = listOf("b"))))
        val mark = callee.logMark()
        stack.caller.dial(ringTimeout = 2.0)

        callee.awaitLog(Regex("cannot specify both of allowed and blocked numbers"), from = mark)
        collector.await(DirectIpStack.CALLER, "ring_timeout")
        collector.events(DirectIpStack.CALLEE).none { it.eventName == "call_established" } shouldBe true
        collector.await(DirectIpStack.CALLER, "call_disconnected")
    }
}

package io.github.arnonym.integrationtest

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test

/**
 * What a caller's keypresses do to the menu tree: falling through to `default`, PIN
 * entry, walking back out with `return`, and jumping sideways with `jump`.
 *
 * These are the menu semantics an ha-sip user writes their YAML against. Each one is
 * decided in `Call.handleDtmfDigit`/`handlePostAction` from state that only exists on a
 * live call, so a real call is the only place the whole rule is visible.
 */
class MenuNavigationTest {
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
    @DisplayName("a digit that matches no choice falls through to the default menu")
    fun invalidDigitFallsThroughToDefault() {
        stack.callee(CalleeConfig(Menus.defaultChoice))
        stack.caller.dial()
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "main" }

        // `5` is not a choice and is not a prefix of one, so it is rejected on the spot.
        stack.caller.sendDtmf("5")

        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "rejected" }
        stack.caller.hangup()
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("a correct PIN is accepted only once the whole code has been entered")
    fun correctPinIsAcceptedAfterTheLastDigit() {
        stack.callee(CalleeConfig(Menus.defaultChoice))
        stack.caller.dial()
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "main" }
        stack.caller.sendDtmf("1")
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "pin-entry" }

        // Digit by digit: a prefix of the PIN must not decide anything, which is the
        // whole difference between `choices_are_pin` and ordinary choices.
        stack.caller.sendDtmf("1")
        stack.caller.sendDtmf("2")
        collector.awaitCount(DirectIpStack.CALLEE, "dtmf_digit", 3)
        collector.events(DirectIpStack.CALLEE).none { it.menuId == "pin-accepted" || it.menuId == "pin-rejected" } shouldBe true

        stack.caller.sendDtmf("3")
        stack.caller.sendDtmf("4")

        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "pin-accepted" }
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("a wrong PIN of the right length falls through to the default menu")
    fun wrongPinFallsThroughToDefault() {
        stack.callee(CalleeConfig(Menus.defaultChoice))
        stack.caller.dial()
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "main" }
        stack.caller.sendDtmf("1")
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "pin-entry" }

        // Same length as the real PIN -- the point at which a PIN menu gives up, as
        // opposed to an ordinary menu which would have given up at the first digit.
        stack.caller.sendDtmf("9")
        stack.caller.sendDtmf("9")
        stack.caller.sendDtmf("9")
        stack.caller.sendDtmf("9")

        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "pin-rejected" }
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("post_action return walks back up two levels to the root menu")
    fun returnPostActionWalksBackUp() {
        stack.callee(CalleeConfig(Menus.returnAndJump))
        stack.caller.dial()
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "main" }

        stack.caller.sendDtmf("1")
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "deep" }
        stack.caller.sendDtmf("2")
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "deepest" }

        // `deepest` carries `return` with level 2, so once its prompt finishes the call
        // must be back at `main` -- two levels up, not one and not out of the tree.
        val visited =
            collector.awaitCount(DirectIpStack.CALLEE, "entered_menu", 4).map { it.menuId }
        visited shouldBe listOf("main", "deep", "deepest", "main")

        stack.caller.hangup()
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("post_action jump moves sideways to a menu by id")
    fun jumpPostActionMovesToNamedMenu() {
        stack.callee(CalleeConfig(Menus.returnAndJump))
        stack.caller.dial()
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "main" }

        // `jumper` is not `landing`'s parent -- reaching it proves the jump resolves by
        // id across the whole tree rather than by walking the parent chain.
        stack.caller.sendDtmf("9")

        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "jumper" }
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "landing" }

        stack.caller.hangup()
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("wait_for_audio_to_finish drops digits pressed during the prompt")
    fun uninterruptiblePromptSwallowsDigits() {
        stack.callee(CalleeConfig(Menus.uninterruptiblePrompt))
        stack.caller.dial()
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "main" }

        // Pressed while the prompt is still playing: `1` is a valid choice, but the menu
        // asked not to be interrupted, so it must be dropped rather than queued.
        stack.caller.sendDtmf("1")
        collector.await(DirectIpStack.CALLEE, "playback_done")
        Thread.sleep(1_500)

        val calleeEvents = collector.events(DirectIpStack.CALLEE)
        calleeEvents.none { it.eventName == "dtmf_digit" } shouldBe true
        calleeEvents.none { it.menuId == "chosen" } shouldBe true

        // Still responsive afterwards -- dropped, not wedged.
        stack.caller.sendDtmf("1")
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "chosen" }
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }
}

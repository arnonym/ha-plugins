package io.github.arnonym.integrationtest

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test
import java.time.Duration

/**
 * Prompts that come from Home Assistant text-to-speech rather than from a file on disk.
 *
 * This is the one menu feature with a network round-trip on the critical path, and the
 * only one whose audio does not exist until the call needs it. Everything here drives it
 * through the real two-request protocol ha-sip speaks -- `POST /api/tts_get_url`, then a
 * `GET` of the URL that comes back -- served by [EventCollector].
 */
class TtsTest {
    private val stack = DirectIpStack
    private val collector = DirectIpStack.collector

    @BeforeEach
    fun resetStack() {
        stack.reset()
        collector.ttsAudio = DirectIpStack.helloWav
    }

    @AfterEach
    fun assertNoTrailingEvents() {
        collector.assertNothingAfterDisconnect(DirectIpStack.CALLER)
        collector.assertNothingAfterDisconnect(DirectIpStack.CALLEE)
    }

    @Test
    @DisplayName("a synthesized prompt is fetched, played, and reported as done")
    fun spokenPromptPlaysEndToEnd() {
        stack.callee(CalleeConfig(Menus.spokenIncoming))
        stack.caller.dial()

        collector.await(DirectIpStack.CALLEE, "entered_menu").menuId shouldBe "spoken"

        // The event that proves the audio actually reached the player: synthesis is
        // asynchronous, so entering the menu says nothing about whether anything played.
        val done = collector.await(DirectIpStack.CALLEE, "playback_done")
        done.payload["type"].toString() shouldBe "\"message\""
        done.payload["message"].toString() shouldBe "\"this prompt comes from text to speech\""
        collector.ttsRequestCount() shouldBe 1

        stack.caller.hangup()
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("a DTMF choice pressed during synthesis wins, and the prompt never plays")
    fun dtmfDuringSynthesisInterruptsThePrompt() {
        stack.callee(CalleeConfig(Menus.spokenIncoming))
        collector.stallTts(4_000)
        stack.caller.dial()

        // `entered_menu` fires before the prompt is fetched, so this is the window in
        // which the audio is still being synthesized.
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "spoken" }
        stack.caller.sendDtmf("1")

        collector.await(DirectIpStack.CALLEE, "entered_menu", timeout = Duration.ofSeconds(15)) {
            it.menuId == "interrupted"
        }

        // The interrupted prompt must be discarded rather than played late on top of the
        // menu the caller chose. Waiting out the remaining stall is the only way to tell
        // "discarded" from "not delivered yet".
        Thread.sleep(5_000)
        val spokenPlaybacks =
            collector.events(DirectIpStack.CALLEE)
                .filter { it.eventName == "playback_done" && it.payload["type"].toString() == "\"message\"" }
        check(spokenPlaybacks.isEmpty()) { "interrupted prompt was played anyway: $spokenPlaybacks" }

        stack.caller.hangup()
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("a stop_playback command discards a prompt still being synthesized")
    fun stopPlaybackDiscardsAPendingPrompt() {
        // The command-driven sibling of the DTMF case above. It matters separately because
        // `stop_playback` is the only way an automation can silence a prompt without also
        // navigating the menu, and it reaches `discardPendingTts` by a different route.
        val callee = stack.callee(CalleeConfig(Menus.spokenIncoming))
        collector.stallTts(4_000)
        stack.caller.dial()

        val incoming = collector.await(DirectIpStack.CALLEE, "incoming_call")
        val calleeCallId = requireNotNull(incoming.internalId) { "incoming_call carried no internal_id" }
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "spoken" }

        val mark = callee.logMark()
        callee.send("""{"command": "stop_playback", "number": ${calleeCallId.jsonString()}}""")
        // Only logged when playback was genuinely in flight, so this also pins that a
        // prompt still being fetched counts as playing.
        callee.awaitLog(Regex("Playback interrupted\\."), from = mark)

        // The fetch lands after the stall expires; waiting it out is the only way to tell
        // "discarded" from "not delivered yet".
        Thread.sleep(5_000)
        val spokenPlaybacks =
            collector.events(DirectIpStack.CALLEE)
                .filter { it.eventName == "playback_done" && it.payload["type"].toString() == "\"message\"" }
        check(spokenPlaybacks.isEmpty()) { "discarded prompt was played anyway: $spokenPlaybacks" }

        // Silenced, not wedged: the menu still answers a keypress afterwards.
        stack.caller.sendDtmf("1")
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "interrupted" }

        stack.caller.hangup()
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }

    @Test
    @DisplayName("cache_audio replays a prompt without asking Home Assistant again")
    fun cachedPromptSkipsTheSecondRoundTrip() {
        val callee = stack.callee(CalleeConfig(Menus.navigation))
        val spoken = Menus.spoken("spoken", cacheAudio = true)

        // First call: cache is empty (reset() wipes it), so this must synthesize.
        stack.caller.dial(menu = spoken)
        collector.await(DirectIpStack.CALLER, "playback_done")
        collector.ttsRequestCount() shouldBe 1
        stack.caller.hangup()
        collector.await(DirectIpStack.CALLER, "call_disconnected")
        // Both sides, not just the dialling one: the callee keys incoming calls by remote
        // URI, so a second call from the same caller is refused while the first is still
        // registered -- and the refusal looks exactly like a silent failure to answer.
        stack.caller.awaitNoActiveCalls()
        callee.awaitNoActiveCalls()

        // Second call, same message: served from the cache directory on disk.
        stack.caller.dial(menu = spoken)
        collector.awaitCount(DirectIpStack.CALLER, "playback_done", 2)
        collector.ttsRequestCount() shouldBe 1

        val cached = DirectIpStack.callerCacheDir.listFiles().orEmpty()
        check(cached.size == 1 && cached.single().length() > 0) {
            "expected exactly one non-empty cache file, found ${cached.map { "${it.name}=${it.length()}" }}"
        }

        stack.caller.hangup()
        // By count, and on both sides: `await` matches over the whole history, and the
        // first call's disconnect is already in it, so waiting by name would return
        // immediately and leave the second call's teardown racing the next scenario.
        collector.awaitCount(DirectIpStack.CALLER, "call_disconnected", 2)
        collector.awaitCount(DirectIpStack.CALLEE, "call_disconnected", 2)
    }

    @Test
    @DisplayName("a failed synthesis falls back to the bundled error prompt and the menu continues")
    fun failedSynthesisFallsBackToErrorPrompt() {
        // No audio configured -> the collector answers `tts_get_url` with a 500.
        collector.ttsAudio = null
        stack.callee(CalleeConfig(Menus.spokenIncoming))
        stack.caller.dial()

        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "spoken" }
        // ha-sip substitutes its bundled error.wav, so playback still completes and the
        // call stays usable rather than hanging on a prompt that will never arrive.
        collector.await(DirectIpStack.CALLEE, "playback_done")

        stack.caller.sendDtmf("1")
        collector.await(DirectIpStack.CALLEE, "entered_menu") { it.menuId == "interrupted" }

        stack.caller.hangup()
        collector.await(DirectIpStack.CALLEE, "call_disconnected")
    }
}

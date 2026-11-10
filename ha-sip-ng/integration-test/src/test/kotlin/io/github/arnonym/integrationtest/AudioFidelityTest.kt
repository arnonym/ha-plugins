package io.github.arnonym.integrationtest

import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.CsvSource
import java.io.File

/**
 * What the far end actually hears.
 *
 * Every other scenario in this suite asserts on events, which say that playback happened
 * but nothing about what came out. A beta tester on
 * [issue 208](https://github.com/arnonym/ha-plugins/issues/208) reported 16 kHz prompts
 * arriving as "pure noise" once PCMA/8000 was negotiated, while the same files at 8 kHz
 * were fine -- a claim no event-level test can confirm or refute.
 *
 * So: the callee plays a 1 kHz tone, the caller records the RTP it receives, and the
 * recording is required to still be a 1 kHz tone. The source rate and the negotiated
 * codec are the two variables, giving four cases.
 *
 * Note which direction each variable points. A 16 kHz file matches the conference
 * bridge's own clock rate (`PJSUA_DEFAULT_CLOCK_RATE`), so it is the case that needs *no*
 * resampling at all; the 8 kHz file is the one pjmedia has to resample
 * (`conference.c`, `create_conf_port`). If the report holds, the easy case is the one
 * that breaks.
 */
class AudioFidelityTest {
    private val stack = DirectIpStack
    private val collector = DirectIpStack.collector

    @BeforeEach
    fun resetStack() = stack.reset()

    @AfterEach
    fun assertNoTrailingEvents() {
        collector.assertNothingAfterDisconnect(DirectIpStack.CALLER)
        collector.assertNothingAfterDisconnect(DirectIpStack.CALLEE)
    }

    @ParameterizedTest(name = "a {0} Hz prompt survives the call with global_options [{1}]")
    @CsvSource(
        "8000, ''",
        "16000, ''",
        "8000, --codecs PCMA",
        "16000, --codecs PCMA",
        // `--audio-sample-rate` converts the prompt itself instead of leaving the rate
        // conversion to pjmedia. The tone has to survive that route too -- and a rate
        // ffmpeg rejected would show up here as silence, not as a wrong frequency.
        "16000, --audio-sample-rate 8000",
        "16000, --codecs PCMA --audio-sample-rate 8000",
        "8000, --codecs PCMA --audio-sample-rate 16000",
    )
    fun promptArrivesUndistorted(
        sourceRate: Int,
        globalOptions: String,
    ) {
        val fixture = if (sourceRate == 8000) DirectIpStack.tone8kWav else DirectIpStack.tone16kWav
        val callee = stack.callee(CalleeConfig(Menus.playing(fixture.absolutePath), globalOptions = globalOptions))

        val target = File(DirectIpStack.recordingsDir, "tone-$sourceRate-${globalOptions.hashCode()}.wav")
        stack.caller.dial()
        collector.await(DirectIpStack.CALLER, "call_established")

        stack.caller.startRecording(target)
        collector.await(DirectIpStack.CALLER, "recording_started")

        // The prompt is 2 s long; recording across the whole of it is what makes the
        // captured signal long enough to measure.
        collector.await(DirectIpStack.CALLEE, "playback_done")

        stack.caller.send("""{"command": "stop_recording", "number": ${DirectIpStack.calleeUri.jsonString()}}""")
        collector.await(DirectIpStack.CALLER, "recording_stopped")

        stack.caller.hangup()
        collector.await(DirectIpStack.CALLER, "call_disconnected")

        val recorded = awaitFinalizedWav(target)
        val dominant = dominantFrequency(recorded)
        val ratio = toneToNoiseRatio(recorded, DirectIpStack.TONE_HZ)
        val negotiated = callee.logLinesFrom(0).lastOrNull { it.contains("Offering audio codecs") } ?: "(pjsip defaults)"
        val summary =
            "source=${sourceRate}Hz options='$globalOptions' -> recorded ${recorded.sampleRate}Hz, " +
                "${recorded.samples.size} samples, rms=%.0f, dominant=%.0fHz, tone:noise=%.1f [$negotiated]"
                    .format(recorded.rms, dominant, ratio)

        check(recorded.rms > 200) { "recording is effectively silent: $summary" }
        check(kotlin.math.abs(dominant - DirectIpStack.TONE_HZ) <= 30.0) {
            "recording does not peak at the tone that was played: $summary"
        }
        // Measured 85-161 across all four cases (PCMA sits lowest, speex highest);
        // broadband noise scores about 1, so 20 fails hard without being brittle.
        check(ratio > 20.0) { "recording is dominated by something other than the tone: $summary" }
    }
}

package io.github.arnonym.config

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test

/**
 * Codec-list narrowing, the SDP-size half of `--codecs`.
 *
 * [AVAILABLE] is what pjsip 2.17 actually enumerates in this add-on's build, in its own
 * order -- the list the issue reports as pushing the INVITE past the MTU.
 */
class CodecSelectionTest {
    @Test
    fun `no request leaves the codec set alone`() {
        val plan = planCodecPriorities(AVAILABLE, emptyList())
        plan.priorities shouldBe emptyList()
        plan.unmatched shouldBe emptyList()
    }

    @Test
    fun `a bare name selects every clock rate it is available at`() {
        val plan = planCodecPriorities(AVAILABLE, listOf("speex"))
        plan.enabled() shouldBe listOf("speex/16000/1", "speex/8000/1", "speex/32000/1")
    }

    @Test
    fun `requested codecs are ranked in the order given`() {
        val plan = planCodecPriorities(AVAILABLE, listOf("PCMA", "PCMU"))
        plan.enabled() shouldBe listOf("PCMA/8000/1", "PCMU/8000/1")
        // Descending from pjsip's PJMEDIA_CODEC_PRIO_HIGHEST, so the offer keeps the order.
        plan.priorities.take(2).map { it.priority } shouldBe listOf<Short>(255, 254)
    }

    @Test
    fun `everything not requested is disabled`() {
        val plan = planCodecPriorities(AVAILABLE, listOf("PCMU", "PCMA"))
        // The whole point: the SDP shrinks because these stop being offered.
        plan.priorities.filter { it.priority.toInt() == 0 }.map { it.codecId } shouldBe
            AVAILABLE - setOf("PCMU/8000/1", "PCMA/8000/1")
        // Every codec pjsip knows about is accounted for, exactly once.
        plan.priorities.map { it.codecId }.sorted() shouldBe AVAILABLE.sorted()
    }

    @Test
    fun `a fully qualified id selects exactly one codec`() {
        planCodecPriorities(AVAILABLE, listOf("speex/16000/1")).enabled() shouldBe listOf("speex/16000/1")
    }

    @Test
    fun `matching ignores case, because pjsip's own spelling does not`() {
        planCodecPriorities(AVAILABLE, listOf("pcmu", "ILBC", "OpUs")).enabled() shouldBe
            listOf("PCMU/8000/1", "iLBC/8000/1", "opus/48000/2")
    }

    @Test
    fun `a name is not a prefix match`() {
        // "PCM" must not quietly select PCMU and PCMA -- a user who wrote that meant
        // something, and silently guessing which is worse than saying it matched nothing.
        val plan = planCodecPriorities(AVAILABLE, listOf("PCM"))
        plan.unmatched shouldBe listOf("PCM")
        plan.priorities shouldBe emptyList()
    }

    @Test
    fun `an unknown name costs that codec and nothing else`() {
        val plan = planCodecPriorities(AVAILABLE, listOf("PCMU", "G729"))
        plan.unmatched shouldBe listOf("G729")
        plan.enabled() shouldBe listOf("PCMU/8000/1")
    }

    @Test
    fun `all names unknown yields an empty plan rather than a silent endpoint`() {
        // Applying a plan that disables everything would leave an endpoint that cannot
        // place a call at all, which is a far worse outcome than a typo.
        val plan = planCodecPriorities(AVAILABLE, listOf("G729", "AMR"))
        plan.priorities shouldBe emptyList()
        plan.unmatched shouldBe listOf("G729", "AMR")
    }

    @Test
    fun `whitespace and empty entries are ignored`() {
        planCodecPriorities(AVAILABLE, listOf(" PCMU ", "", "  ")).enabled() shouldBe listOf("PCMU/8000/1")
    }

    @Test
    fun `a codec named twice is ranked once`() {
        val plan = planCodecPriorities(AVAILABLE, listOf("PCMU", "PCMU/8000/1"))
        plan.enabled() shouldBe listOf("PCMU/8000/1")
    }
}

private fun CodecPlan.enabled(): List<String> = priorities.filter { it.priority.toInt() > 0 }.map { it.codecId }

private val AVAILABLE =
    listOf(
        "speex/16000/1",
        "speex/8000/1",
        "speex/32000/1",
        "iLBC/8000/1",
        "GSM/8000/1",
        "PCMU/8000/1",
        "PCMA/8000/1",
        "G722/16000/1",
        "opus/48000/2",
    )

package io.github.arnonym.config

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test

class SipOptionsTest {
    @Test
    fun `parse without options`() {
        val options = SipOptions.parse("")
        options.proxy shouldBe null
        options.enableIce shouldBe true
        options.turnServer shouldBe null
        options.sipStunUse shouldBe true
        options.mediaStunUse shouldBe true
        options.contactRewriteUse shouldBe true
        options.viaRewriteUse shouldBe true
        options.sdpNatRewriteUse shouldBe true
        options.sipOutboundUse shouldBe true
        options.rejectSipCode shouldBe 603
    }

    @Test
    fun `parse proxy`() {
        SipOptions.parse("--proxy sip:example.com").proxy shouldBe "sip:example.com"
    }

    @Test
    fun `parse ice disabled`() {
        SipOptions.parse("--ice disabled").enableIce shouldBe false
    }

    @Test
    fun `parse ice enabled`() {
        SipOptions.parse("--ice enabled").enableIce shouldBe true
    }

    @Test
    fun `parse sip stun use`() {
        SipOptions.parse("--use-stun-for-sip disabled").sipStunUse shouldBe false
    }

    @Test
    fun `parse media stun use`() {
        SipOptions.parse("--use-stun-for-media disabled").mediaStunUse shouldBe false
    }

    @Test
    fun `parse use contact rewrite`() {
        SipOptions.parse("--use-contact-rewrite disabled").contactRewriteUse shouldBe false
    }

    @Test
    fun `parse use via rewrite`() {
        SipOptions.parse("--use-via-rewrite disabled").viaRewriteUse shouldBe false
    }

    @Test
    fun `parse use sdp nat rewrite`() {
        SipOptions.parse("--use-sdp-nat-rewrite disabled").sdpNatRewriteUse shouldBe false
    }

    @Test
    fun `parse use sip outbound`() {
        SipOptions.parse("--use-sip-outbound disabled").sipOutboundUse shouldBe false
    }

    @Test
    fun `parse turn server`() {
        val options =
            SipOptions.parse(
                "--turn-server turn:example.com:3478 --turn-connection-type udp --turn-user user --turn-password pass",
            )
        val turnServer = options.turnServer ?: error("Turn server not set")
        turnServer.server shouldBe "turn:example.com:3478"
        turnServer.connectionType shouldBe TurnConnectionType.UDP
        turnServer.user shouldBe "user"
        turnServer.password shouldBe "pass"
    }

    @Test
    fun `parse turn server type tcp`() {
        val options =
            SipOptions.parse(
                "--turn-server turn:example.com:3478 --turn-connection-type tcp --turn-user user --turn-password pass",
            )
        val turnServer = options.turnServer ?: error("Turn server not set")
        turnServer.connectionType shouldBe TurnConnectionType.TCP
    }

    @Test
    fun `parse turn server type tls`() {
        val options =
            SipOptions.parse(
                "--turn-server turn:example.com:3478 --turn-connection-type tls --turn-user user --turn-password pass",
            )
        val turnServer = options.turnServer ?: error("Turn server not set")
        turnServer.connectionType shouldBe TurnConnectionType.TLS
    }

    @Test
    fun `parse extract headers default`() {
        SipOptions.parse("").extractHeaders shouldBe emptyList()
    }

    @Test
    fun `parse extract headers single`() {
        SipOptions.parse("--extract-headers X-Custom-Header").extractHeaders shouldBe listOf("X-Custom-Header")
    }

    @Test
    fun `parse extract headers multiple`() {
        SipOptions.parse("--extract-headers X-Custom-Header,P-Asserted-Identity,X-Another").extractHeaders shouldBe
            listOf("X-Custom-Header", "P-Asserted-Identity", "X-Another")
    }

    @Test
    fun `parse reject sip code default`() {
        SipOptions.parse("").rejectSipCode shouldBe 603
    }

    @Test
    fun `parse reject sip code custom`() {
        SipOptions.parse("--reject-sip-code 486").rejectSipCode shouldBe 486
    }
}

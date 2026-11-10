package io.github.arnonym.config

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test

/** Port of tests/test_global_options.py. */
class GlobalOptionsTest {
    @Test
    fun `parse transport default`() {
        val options = GlobalOptions.parse("")
        options.enableUdp shouldBe true
        options.enableTcp shouldBe true
        options.enableTls shouldBe false
        options.stunServer shouldBe null
    }

    @Test
    fun `audio sample rate is unset by default`() {
        GlobalOptions.parse("").audioSampleRate shouldBe null
    }

    @Test
    fun `parse audio sample rate`() {
        GlobalOptions.parse("--audio-sample-rate 8000").audioSampleRate shouldBe 8000
        GlobalOptions.parse("--audio-sample-rate=16000").audioSampleRate shouldBe 16000
    }

    @Test
    fun `parse transport udp enabled`() {
        GlobalOptions.parse("--udp enabled").enableUdp shouldBe true
    }

    @Test
    fun `parse transport udp disabled`() {
        GlobalOptions.parse("--udp=disabled").enableUdp shouldBe false
    }

    @Test
    fun `parse transport tcp enabled`() {
        GlobalOptions.parse("--tcp=enabled").enableTcp shouldBe true
    }

    @Test
    fun `parse transport tcp disabled`() {
        GlobalOptions.parse("--tcp disabled").enableTcp shouldBe false
    }

    @Test
    fun `parse transport tls enabled`() {
        GlobalOptions.parse("--tls=enabled").enableTls shouldBe true
    }

    @Test
    fun `parse transport tls disabled`() {
        GlobalOptions.parse("--tls=disabled").enableTls shouldBe false
    }

    @Test
    fun `parse stun server`() {
        GlobalOptions.parse("--stun-server stun.example.com").stunServer shouldBe "stun.example.com"
    }

    @Test
    fun `parse tls port default`() {
        GlobalOptions.parse("").tlsPort shouldBe 5061
    }

    @Test
    fun `parse rtp port defaults to pjsip's own base port`() {
        // Restates DEFAULT_RTP_PORT from pjsua_core.c, which `pjsua_acc_config_default`
        // has already written into the account's rtp_cfg. Setting it explicitly is a
        // no-op, which is what lets the option be non-null.
        GlobalOptions.parse("").rtpPort shouldBe 4000
    }

    @Test
    fun `parse rtp port`() {
        GlobalOptions.parse("--rtp-port 14000").rtpPort shouldBe 14000
    }

    @Test
    fun `parse rtp port with equals`() {
        GlobalOptions.parse("--rtp-port=24000").rtpPort shouldBe 24000
    }

    @Test
    fun `parse rtp port alongside other options`() {
        val options = GlobalOptions.parse("--udp=disabled --rtp-port 30000 --tls-port 5062")
        options.rtpPort shouldBe 30000
        options.tlsPort shouldBe 5062
        options.enableUdp shouldBe false
    }

    @Test
    fun `parse rtp port range default`() {
        GlobalOptions.parse("").rtpPortRange shouldBe 0
    }

    @Test
    fun `parse rtp port range`() {
        GlobalOptions.parse("--rtp-port-range 100").rtpPortRange shouldBe 100
    }

    @Test
    fun `parse rtp port range alongside rtp port`() {
        val options = GlobalOptions.parse("--rtp-port 5000 --rtp-port-range 200")
        options.rtpPort shouldBe 5000
        options.rtpPortRange shouldBe 200
    }

    @Test
    fun `parse debug headers default`() {
        GlobalOptions.parse("").debugHeaders shouldBe false
    }

    @Test
    fun `parse debug headers enabled`() {
        GlobalOptions.parse("--debug-headers enabled").debugHeaders shouldBe true
    }

    @Test
    fun `parse debug headers disabled`() {
        GlobalOptions.parse("--debug-headers disabled").debugHeaders shouldBe false
    }

    @Test
    fun `parse mqtt defaults`() {
        val options = GlobalOptions.parse("")
        options.enableMqtt shouldBe false
        options.mqttAddress shouldBe ""
        options.mqttPort shouldBe 1883
        options.mqttUsername shouldBe ""
        options.mqttPassword shouldBe ""
        options.mqttTopic shouldBe "hasip/execute"
        options.mqttStateTopic shouldBe "hasip/state"
    }

    @Test
    fun `parse mqtt enabled`() {
        GlobalOptions.parse("--enable-mqtt").enableMqtt shouldBe true
    }

    @Test
    fun `parse mqtt full`() {
        val options =
            GlobalOptions.parse(
                "--enable-mqtt --mqtt-address 192.168.1.1 --mqtt-port 1884 " +
                    "--mqtt-username admin --mqtt-password secret " +
                    "--mqtt-topic=custom/execute --mqtt-state-topic custom/state",
            )
        options.enableMqtt shouldBe true
        options.mqttAddress shouldBe "192.168.1.1"
        options.mqttPort shouldBe 1884
        options.mqttUsername shouldBe "admin"
        options.mqttPassword shouldBe "secret"
        options.mqttTopic shouldBe "custom/execute"
        options.mqttStateTopic shouldBe "custom/state"
    }

    @Test
    fun `parse sdp defaults`() {
        val options = GlobalOptions.parse("")
        options.codecs shouldBe emptyList()
        options.textMedia shouldBe false
    }

    @Test
    fun `parse codec list`() {
        GlobalOptions.parse("--codecs PCMU,PCMA").codecs shouldBe listOf("PCMU", "PCMA")
    }

    @Test
    fun `parse codec list drops empty entries`() {
        // The option string is split on whitespace only, so a stray comma is the kind of
        // typo that reaches the parser intact.
        GlobalOptions.parse("--codecs=PCMU,,PCMA").codecs shouldBe listOf("PCMU", "PCMA")
    }

    @Test
    fun `parse text media enabled`() {
        GlobalOptions.parse("--text-media enabled").textMedia shouldBe true
    }

    @Test
    fun `parse text media disabled`() {
        GlobalOptions.parse("--text-media=disabled").textMedia shouldBe false
    }

    @Test
    fun `parse sdp options together`() {
        val options = GlobalOptions.parse("--codecs PCMU,PCMA --text-media enabled --rtp-port 5000")
        options.codecs shouldBe listOf("PCMU", "PCMA")
        options.textMedia shouldBe true
        options.rtpPort shouldBe 5000
    }
}

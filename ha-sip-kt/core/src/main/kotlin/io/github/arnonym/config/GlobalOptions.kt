package io.github.arnonym.config

import com.github.ajalt.clikt.core.NoOpCliktCommand
import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.flag
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.types.choice
import com.github.ajalt.clikt.parameters.types.int
import io.github.arnonym.log.log

data class GlobalOptions(
    val stunServer: String?,
    val enableUdp: Boolean,
    val enableTcp: Boolean,
    val enableTls: Boolean,
    val tlsPort: Int,
    val rtpPort: Int,
    val rtpPortRange: Int,
    val debugHeaders: Boolean,
    val enableMqtt: Boolean,
    val mqttAddress: String,
    val mqttPort: Int,
    val mqttUsername: String,
    val mqttPassword: String,
    val mqttTopic: String,
    val mqttStateTopic: String,
    val codecs: List<String>,
    val textMedia: Boolean,
    val audioSampleRate: Int?,
) {
    companion object {
        fun parse(raw: String?): GlobalOptions {
            val cmd = GlobalOptionsCmd()
            cmd.main(tokenize(raw))
            return GlobalOptions(
                stunServer = cmd.stunServer,
                enableUdp = cmd.enableUdp,
                enableTcp = cmd.enableTcp,
                enableTls = cmd.enableTls,
                tlsPort = cmd.tlsPort,
                rtpPort = cmd.rtpPort,
                rtpPortRange = cmd.rtpPortRange,
                debugHeaders = cmd.debugHeaders,
                enableMqtt = cmd.enableMqtt,
                mqttAddress = cmd.mqttAddress,
                mqttPort = cmd.mqttPort,
                mqttUsername = cmd.mqttUsername,
                mqttPassword = cmd.mqttPassword,
                mqttTopic = cmd.mqttTopic,
                mqttStateTopic = cmd.mqttStateTopic,
                codecs = cmd.codecs?.split(",")?.map { it.trim() }?.filter { it.isNotEmpty() } ?: emptyList(),
                textMedia = cmd.textMedia,
                audioSampleRate = cmd.audioSampleRate,
            ).also { it.logSummary() }
        }

        fun printHelp() = println(GlobalOptionsCmd().getFormattedHelp())
    }

    private fun logSummary() {
        log(null, "STUN Server: $stunServer")
        log(null, "UDP Enabled: $enableUdp")
        log(null, "TCP Enabled: $enableTcp")
        log(null, "TLS Enabled: $enableTls")
        log(null, "TLS Port: $tlsPort")
        log(
            null,
            if (rtpPortRange > 0) "RTP Port: $rtpPort-${rtpPort + rtpPortRange}" else "RTP Port: $rtpPort",
        )
        if (codecs.isNotEmpty()) log(null, "Offered codecs limited to: ${codecs.joinToString(", ")}")
        if (textMedia) log(null, "Text media (m=text) enabled")
        if (audioSampleRate != null) log(null, "Resampling all audio to $audioSampleRate Hz")
        log(null, "MQTT Enabled: $enableMqtt")
        if (enableMqtt) {
            log(null, "MQTT Address: $mqttAddress")
            log(null, "MQTT Port: $mqttPort")
            log(null, "MQTT Username: $mqttUsername")
            log(null, "MQTT Topic: $mqttTopic")
            log(null, "MQTT State Topic: $mqttStateTopic")
        }
    }
}

private class GlobalOptionsCmd : NoOpCliktCommand(name = "global_options") {
    val stunServer: String? by option(
        "--stun-server",
        help = "STUN server to use for NAT traversal (default: None)",
    )
    val enableUdp: Boolean by option(
        "--udp",
        help = "Enable or disable UDP transport (default: enabled)",
    ).choice(BOOL_MAP).default(true)
    val enableTcp: Boolean by option(
        "--tcp",
        help = "Enable or disable TCP transport (default: enabled)",
    ).choice(BOOL_MAP).default(true)
    val enableTls: Boolean by option(
        "--tls",
        help = "Enable or disable TLS transport (default: disabled)",
    ).choice(BOOL_MAP).default(false)
    val tlsPort: Int by option(
        "--tls-port",
        help = "Port to use for TLS transport (default: 5061)",
    ).int().default(5061)
    val rtpPort: Int by option(
        "--rtp-port",
        help = "First port used for RTP/RTCP media sockets (default: 4000)",
        // 4000 restates pjsip's own default (DEFAULT_RTP_PORT in pjsua_core.c, applied by
        // `pjsua_acc_config_default`), so passing it through unconditionally changes nothing.
    ).int().default(4000)
    val rtpPortRange: Int by option(
        "--rtp-port-range",
        help =
            "Number of additional ports usable for RTP/RTCP media sockets, starting at " +
                "--rtp-port, e.g. a range of 100 with the default --rtp-port allows " +
                "4000-4100 (default: 0, i.e. only --rtp-port itself is used).",
    ).int().default(0)
    val debugHeaders: Boolean by option(
        "--debug-headers",
        help = "Enable debug printing of extracted SIP headers (default: disabled)",
    ).choice(BOOL_MAP).default(false)
    val codecs: String? by option(
        "--codecs",
        help =
            "Comma-separated list of audio codecs to offer, highest priority first, e.g. " +
                "\"PCMU,PCMA\".",
    )
    val textMedia: Boolean by option(
        "--text-media",
        help =
            "Enable or disable the \"m=text\" (RFC 4103) line in the SDP. (default: disabled)",
    ).choice(BOOL_MAP).default(false)
    val audioSampleRate: Int? by option(
        "--audio-sample-rate",
        help =
            "Resample every message and audio file to this rate, in Hz, e.g. \"8000\". " +
                "Only needed where pjsip's own resampling misbehaves; leaving it unset keeps " +
                "each file at its original rate. (default: unset)",
    ).int()
    val enableMqtt: Boolean by option(
        "--enable-mqtt",
        help = "Enable MQTT as a command source (default: disabled)",
    ).flag()
    val mqttAddress: String by option(
        "--mqtt-address",
        help = "MQTT broker address (default: empty)",
    ).default("")
    val mqttPort: Int by option(
        "--mqtt-port",
        help = "MQTT broker port (default: 1883)",
    ).int().default(1883)
    val mqttUsername: String by option(
        "--mqtt-username",
        help = "MQTT broker username (default: empty)",
    ).default("")
    val mqttPassword: String by option(
        "--mqtt-password",
        help = "MQTT broker password (default: empty)",
    ).default("")
    val mqttTopic: String by option(
        "--mqtt-topic",
        help = "MQTT topic to subscribe to for incoming commands (default: hasip/execute)",
    ).default("hasip/execute")
    val mqttStateTopic: String by option(
        "--mqtt-state-topic",
        help = "MQTT topic to publish call state events to (default: hasip/state)",
    ).default("hasip/state")
}

package io.github.arnonym.config

import com.github.ajalt.clikt.core.NoOpCliktCommand
import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.types.choice
import com.github.ajalt.clikt.parameters.types.int
import io.github.arnonym.log.log

enum class TurnConnectionType {
    TCP,
    UDP,
    TLS,
    ;

    companion object {
        fun fromString(raw: String): TurnConnectionType =
            when (raw.lowercase()) {
                "tcp" -> TCP
                "udp" -> UDP
                "tls" -> TLS
                else -> throw IllegalArgumentException("Unknown connection type: $raw")
            }
    }
}

data class TurnServer(
    val server: String,
    val connectionType: TurnConnectionType,
    val user: String?,
    val password: String?,
)

data class SipOptions(
    val proxy: String?,
    val enableIce: Boolean,
    val sipStunUse: Boolean,
    val mediaStunUse: Boolean,
    val contactRewriteUse: Boolean,
    val viaRewriteUse: Boolean,
    val sdpNatRewriteUse: Boolean,
    val sipOutboundUse: Boolean,
    val turnServer: TurnServer?,
    val extractHeaders: List<String>,
    val rejectSipCode: Int,
) {
    companion object {
        fun parse(
            raw: String?,
            accountIndex: Int? = null,
        ): SipOptions {
            val cmd = SipOptionsCmd()
            cmd.main(tokenize(raw))

            val turnServerAddress = cmd.turnServer
            val turnUser = cmd.turnUser
            val turnPassword = cmd.turnPassword
            if (turnServerAddress != null && turnUser == null && turnPassword == null) {
                log(accountIndex, "Error: TURN server requires user and password. Disabling TURN server.")
            }
            val turnServer =
                if (turnServerAddress != null) {
                    TurnServer(
                        server = turnServerAddress,
                        connectionType = cmd.turnConnectionType,
                        user = turnUser,
                        password = turnPassword,
                    )
                } else {
                    null
                }

            val extractHeaders =
                cmd.extractHeaders
                    ?.split(",")
                    ?.map { it.trim() }
                    ?: emptyList()

            return SipOptions(
                proxy = cmd.proxy,
                enableIce = cmd.enableIce,
                sipStunUse = cmd.sipStunUse,
                mediaStunUse = cmd.mediaStunUse,
                contactRewriteUse = cmd.contactRewriteUse,
                viaRewriteUse = cmd.viaRewriteUse,
                sdpNatRewriteUse = cmd.sdpNatRewriteUse,
                sipOutboundUse = cmd.sipOutboundUse,
                turnServer = turnServer,
                extractHeaders = extractHeaders,
                rejectSipCode = cmd.rejectSipCode,
            ).also { it.logSummary(accountIndex) }
        }

        fun printHelp() = println(SipOptionsCmd().getFormattedHelp())
    }

    private fun logSummary(accountIndex: Int?) {
        log(accountIndex, "Proxy set to: $proxy")
        log(accountIndex, "ICE is enabled: $enableIce")
        log(accountIndex, "TURN server is enabled: ${turnServer != null}")
        if (extractHeaders.isNotEmpty()) {
            log(accountIndex, "Extract headers: $extractHeaders")
        }
    }
}

private class SipOptionsCmd : NoOpCliktCommand(name = "sip_options") {
    val proxy: String? by option(
        "--proxy",
        help = "Proxy server to use for SIP (default: None)",
    )
    val enableIce: Boolean by option(
        "--ice",
        help = "Enable or disable ICE (default: true)",
    ).choice(BOOL_MAP).default(true)
    val sipStunUse: Boolean by option(
        "--use-stun-for-sip",
        help = "Enable or disable STUN for sip (default: true)",
    ).choice(BOOL_MAP).default(true)
    val mediaStunUse: Boolean by option(
        "--use-stun-for-media",
        help = "Enable or disable STUN for media (default: true)",
    ).choice(BOOL_MAP).default(true)
    val contactRewriteUse: Boolean by option(
        "--use-contact-rewrite",
        help = "Enable or disable contact rewrite for SIP (default: true)",
    ).choice(BOOL_MAP).default(true)
    val viaRewriteUse: Boolean by option(
        "--use-via-rewrite",
        help = "Enable or disable via rewrite for SIP (default: true)",
    ).choice(BOOL_MAP).default(true)
    val sdpNatRewriteUse: Boolean by option(
        "--use-sdp-nat-rewrite",
        help = "Enable or disable SDP NAT rewrite for SIP (default: true)",
    ).choice(BOOL_MAP).default(true)
    val sipOutboundUse: Boolean by option(
        "--use-sip-outbound",
        help = "Enable or disable SIP outbound (default: true)",
    ).choice(BOOL_MAP).default(true)
    val turnServer: String? by option(
        "--turn-server",
        help = "Set the TURN server to use for SIP (default: None)",
    )
    val turnConnectionType: TurnConnectionType by option(
        "--turn-connection-type",
        help = "Set the TURN server connection protocol (default: udp)",
    ).choice(
        "tcp" to TurnConnectionType.TCP,
        "udp" to TurnConnectionType.UDP,
        "tls" to TurnConnectionType.TLS,
    ).default(TurnConnectionType.UDP)
    val turnUser: String? by option(
        "--turn-user",
        help = "Set the TURN user (default: None)",
    )
    val turnPassword: String? by option(
        "--turn-password",
        help = "Set the TURN password (default: None)",
    )
    val extractHeaders: String? by option(
        "--extract-headers",
        help = "Comma-separated list of SIP headers to extract (default: None)",
    )
    val rejectSipCode: Int by option(
        "--reject-sip-code",
        help = "SIP response code used when rejecting incoming calls in reject mode (default: 603)",
    ).int().default(603)
}

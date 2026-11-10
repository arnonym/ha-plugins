package io.github.arnonym.sip

import io.github.arnonym.config.GlobalOptions
import io.github.arnonym.config.planCodecPriorities
import io.github.arnonym.log.log
import org.pjsip.pjsua2.Endpoint
import org.pjsip.pjsua2.EpConfig
import org.pjsip.pjsua2.StringVector
import org.pjsip.pjsua2.TransportConfig
import org.pjsip.pjsua2.pjsip_transport_type_e

data class EndpointConfig(
    val port: Int,
    val logLevel: Int,
    val nameServer: List<String>,
    val globalOptions: GlobalOptions,
)

fun createEndpoint(
    config: EndpointConfig,
    threadCount: Int = 4,
): Endpoint {
    val epConfig = EpConfig()
    epConfig.logConfig.level = config.logLevel.toLong()
    epConfig.uaConfig.threadCnt = threadCount.toLong()
    epConfig.uaConfig.mainThreadOnly = false
    // Never auto-close the (null) sound device. It clocks the conference bridge, and
    // pjsua's default closes it after one second of silence -- taking the RTP transmit
    // path down with it, so an RFC 2833 `send_dtmf` later in a quiet call is accepted,
    // logged, and never actually put on the wire.
    epConfig.medConfig.sndAutoCloseTime = -1
    if (config.nameServer.isNotEmpty()) {
        val nameserver = StringVector()
        config.nameServer.forEach { nameserver.add(it) }
        epConfig.uaConfig.nameserver = nameserver
    }
    if (!config.globalOptions.stunServer.isNullOrEmpty()) {
        log(null, "STUN server enabled: ${config.globalOptions.stunServer}")
        epConfig.uaConfig.stunServer.add(config.globalOptions.stunServer)
    }

    val endpoint = Endpoint()
    endpoint.libCreate()
    endpoint.libInit(epConfig)
    val codecs = endpoint.codecEnum2()
    log(null, "Supported audio codecs: ${codecs.joinToString(", ") { it.codecId }}")
    endpoint.applyCodecPriorities(codecs.map { it.codecId }, config.globalOptions.codecs)
    endpoint.audDevManager().setNullDev()

    if (config.globalOptions.enableUdp) {
        log(null, "UDP transport enabled on port ${config.port}")
        val udpConfig = TransportConfig()
        udpConfig.port = config.port.toLong()
        endpoint.transportCreate(pjsip_transport_type_e.PJSIP_TRANSPORT_UDP, udpConfig)
    }
    if (config.globalOptions.enableTcp) {
        log(null, "TCP transport enabled on port ${config.port}")
        val tcpConfig = TransportConfig()
        tcpConfig.port = config.port.toLong()
        endpoint.transportCreate(pjsip_transport_type_e.PJSIP_TRANSPORT_TCP, tcpConfig)
    }
    if (config.globalOptions.enableTls) {
        log(null, "TLS transport enabled on port ${config.globalOptions.tlsPort}")
        val tlsConfig = TransportConfig()
        tlsConfig.port = config.globalOptions.tlsPort.toLong()
        endpoint.transportCreate(pjsip_transport_type_e.PJSIP_TRANSPORT_TLS, tlsConfig)
    }
    endpoint.libStart()
    return endpoint
}

private fun Endpoint.applyCodecPriorities(
    available: List<String>,
    requested: List<String>,
) {
    if (requested.isEmpty()) return
    val plan = planCodecPriorities(available, requested)
    if (plan.unmatched.isNotEmpty()) {
        log(null, "Warning: no such codec: ${plan.unmatched.joinToString(", ")}")
    }
    if (plan.priorities.isEmpty()) {
        log(null, "Error: --codecs matched nothing at all: keeping pjsip's default codec set")
        return
    }
    plan.priorities.forEach { (codecId, priority) ->
        try {
            codecSetPriority(codecId, priority)
        } catch (e: Exception) {
            log(null, "Warning: could not set priority of codec $codecId: ${e.message}")
        }
    }
    val enabled = plan.priorities.filter { it.priority > 0 }.map { it.codecId }
    log(null, "Offering audio codecs: ${enabled.joinToString(", ")}")
}

fun Endpoint.registerCurrentThread() {
    try {
        if (!libIsThreadRegistered()) libRegisterThread(Thread.currentThread().name)
    } catch (e: Exception) {
        log(null, "Warning: could not register thread '${Thread.currentThread().name}' with pjsip: ${e.message}")
    }
}

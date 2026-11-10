package io.github.arnonym.sip

import io.github.arnonym.command.CommandHandler
import io.github.arnonym.config.AnswerMode
import io.github.arnonym.config.Constants
import io.github.arnonym.config.GlobalOptions
import io.github.arnonym.config.SipOptions
import io.github.arnonym.config.TurnConnectionType
import io.github.arnonym.event.Event
import io.github.arnonym.event.EventSender
import io.github.arnonym.event.sendEvent
import io.github.arnonym.ha.HaClient
import io.github.arnonym.ha.HaConfig
import io.github.arnonym.log.log
import io.github.arnonym.menu.IncomingCallConfig
import org.pjsip.pjsua2.AccountConfig
import org.pjsip.pjsua2.AuthCredInfo
import org.pjsip.pjsua2.OnIncomingCallParam
import org.pjsip.pjsua2.OnRegStateParam
import org.pjsip.pjsua2.pj_turn_tp_type
import org.pjsip.pjsua2.pjsua_stun_use
import org.pjsip.pjsua2.Account as PjAccount

typealias OnRegStateCallback = (accountIndex: Int, code: Int, reason: String) -> Unit

data class MyAccountConfig(
    val enabled: Boolean,
    val index: Int,
    val idUri: String,
    val registrarUri: String,
    val realm: String,
    val userName: String,
    val password: String,
    val mode: AnswerMode,
    val settleTime: Double,
    val incomingCallConfig: IncomingCallConfig?,
    val options: SipOptions,
    val globalOptions: GlobalOptions,
)

class Account(
    val config: MyAccountConfig,
    val commandHandler: CommandHandler<Call>,
    val eventSender: EventSender,
    val haConfig: HaConfig,
    val haClient: HaClient,
    private val makeDefault: Boolean,
    private val onRegStateCallback: OnRegStateCallback?,
) : PjAccount() {
    fun init() {
        val accountConfig = AccountConfig()
        accountConfig.idUri = config.idUri
        accountConfig.regConfig.registrarUri = config.registrarUri
        val credentials = AuthCredInfo("digest", config.realm, config.userName, 0, config.password)
        accountConfig.sipConfig.authCreds.add(credentials)
        accountConfig.mediaConfig.transportConfig.port = config.globalOptions.rtpPort.toLong()
        accountConfig.mediaConfig.transportConfig.portRange = config.globalOptions.rtpPortRange.toLong()
        accountConfig.natConfig.iceEnabled = config.options.enableIce
        accountConfig.natConfig.contactRewriteUse = if (config.options.contactRewriteUse) 1 else 0
        accountConfig.natConfig.viaRewriteUse = if (config.options.viaRewriteUse) 1 else 0
        accountConfig.natConfig.sdpNatRewriteUse = if (config.options.sdpNatRewriteUse) 1 else 0
        accountConfig.natConfig.sipOutboundUse = if (config.options.sipOutboundUse) 1 else 0
        if (!config.globalOptions.stunServer.isNullOrEmpty()) {
            accountConfig.natConfig.sipStunUse =
                if (config.options.sipStunUse) pjsua_stun_use.PJSUA_STUN_USE_DEFAULT else pjsua_stun_use.PJSUA_STUN_USE_DISABLED
            accountConfig.natConfig.mediaStunUse =
                if (config.options.mediaStunUse) pjsua_stun_use.PJSUA_STUN_USE_DEFAULT else pjsua_stun_use.PJSUA_STUN_USE_DISABLED
        }
        val turnServer = config.options.turnServer
        if (turnServer != null) {
            accountConfig.natConfig.turnEnabled = true
            accountConfig.natConfig.turnServer = turnServer.server
            accountConfig.natConfig.turnConnType = turnServer.connectionType.toPjConstant()
            accountConfig.natConfig.turnUserName = turnServer.user
            accountConfig.natConfig.turnPasswordType = 0
            accountConfig.natConfig.turnPassword = turnServer.password
        }
        if (!config.options.proxy.isNullOrEmpty()) {
            accountConfig.sipConfig.proxies.add(config.options.proxy)
        }
        create(accountConfig, makeDefault)
    }

    override fun onRegState(prm: OnRegStateParam) {
        log(config.index, "OnRegState: ${prm.code} ${prm.reason}")
        onRegStateCallback?.invoke(config.index, prm.code, prm.reason)
    }

    override fun onIncomingCall(prm: OnIncomingCallParam) {
        val incomingConfig = config.incomingCallConfig
        val menu = incomingConfig?.menu
        val allowedNumbers = incomingConfig?.allowedNumbers
        val blockedNumbers = incomingConfig?.blockedNumbers
        val answerAfter = (incomingConfig?.answerAfter ?: 0).toDouble()
        val webhookToCall = incomingConfig?.webhookToCall
        val extractHeaders = config.options.extractHeaders
        var sipHeaders: Map<String, String?> = emptyMap()
        if (config.globalOptions.debugHeaders) {
            logAllSipHeaders(config.index, prm.rdata.wholeMsg)
        }
        if (extractHeaders.isNotEmpty()) {
            sipHeaders = parseSipHeaders(prm.rdata.wholeMsg, extractHeaders)
        }

        val incomingCall =
            Call(
                account = this,
                callId = prm.callId,
                uriToCall = null,
                initialMenu = menu,
                commandHandler = commandHandler,
                eventSender = eventSender,
                haConfig = haConfig,
                haClient = haClient,
                ringTimeout = Constants.DEFAULT_RING_TIMEOUT,
                webhooks = webhookToCall,
                sipHeaders = sipHeaders,
            )
        val callInfo = incomingCall.getCallInfo()
        val answerMode = getSipReturnCode(config.mode, allowedNumbers, blockedNumbers, callInfo.parsedRemoteUri)
        log(
            config.index,
            "Incoming call  from  '${callInfo.remoteUri}' (parsed: '${callInfo.parsedRemoteUri}') to " +
                "'${callInfo.localUri}' (parsed: '${callInfo.parsedLocalUri}')",
        )
        if (!allowedNumbers.isNullOrEmpty()) log(config.index, "Allowed numbers: $allowedNumbers")
        if (!blockedNumbers.isNullOrEmpty()) log(config.index, "Blocked numbers: $blockedNumbers")
        log(config.index, "Answer mode: ${answerMode.name}")
        incomingCall.accept(answerMode, answerAfter)
        sendEvent(
            Event.IncomingCall,
            callInfo,
            config.index,
            incomingCall.callbackId,
            eventSender,
        )
    }

    fun getSipReturnCode(
        mode: AnswerMode,
        allowedNumbers: List<String>?,
        blockedNumbers: List<String>?,
        parsedNumber: String?,
    ): AnswerMode {
        if (!allowedNumbers.isNullOrEmpty() && !blockedNumbers.isNullOrEmpty()) {
            log(config.index, "Error: cannot specify both of allowed and blocked numbers. Call won't be accepted!")
            return AnswerMode.LISTEN
        }
        if (mode == AnswerMode.ACCEPT && !allowedNumbers.isNullOrEmpty()) {
            return if (isNumberInList(parsedNumber, allowedNumbers)) AnswerMode.ACCEPT else AnswerMode.LISTEN
        }
        if (mode == AnswerMode.ACCEPT && !blockedNumbers.isNullOrEmpty()) {
            return if (!isNumberInList(parsedNumber, blockedNumbers)) AnswerMode.ACCEPT else AnswerMode.LISTEN
        }
        return mode
    }

    companion object {
        fun parseSipHeaders(
            wholeMsg: String,
            headerNames: List<String>,
        ): Map<String, String?> {
            val headerLines = wholeMsg.split("\r\n").takeWhile { it.isNotBlank() }
            return headerNames.associateWith { name ->
                headerLines.lastOrNull { it.lowercase().startsWith("${name.lowercase()}:") }
                    ?.substringAfter(':')?.trim()
            }
        }

        fun logAllSipHeaders(
            accountIndex: Int,
            wholeMsg: String,
        ) {
            log(accountIndex, "Available SIP headers:")
            wholeMsg.split("\r\n")
                .takeWhile { it.isNotBlank() }
                .filter { ':' in it }
                .forEach { line ->
                    val (name, value) = line.split(':', limit = 2)
                    log(accountIndex, "  ${name.trim()}: ${value.trim()}")
                }
        }

        fun isNumberInList(
            number: String?,
            numberList: List<String>,
        ): Boolean {
            if (number.isNullOrEmpty()) return false

            fun mapToRegex(part: String): String =
                when (part) {
                    "{*}" -> ".*"
                    "{?}" -> "."
                    else -> Regex.escape(part)
                }
            val delimiter = Regex("\\{\\*}|\\{\\?}")
            return numberList.any { n ->
                // Split on {*}/{?} while keeping the delimiters themselves, mirroring Python's
                // `re.split(r'(\{\*}|\{\?})', n)` (a capturing group keeps the matched delimiters
                // in the resulting list).
                val parts = mutableListOf<String>()
                var lastIndex = 0
                delimiter.findAll(n).forEach { match ->
                    parts.add(n.substring(lastIndex, match.range.first))
                    parts.add(match.value)
                    lastIndex = match.range.last + 1
                }
                parts.add(n.substring(lastIndex))
                val nRegex = "^" + parts.joinToString("") { mapToRegex(it) } + "$"
                Regex(nRegex).matches(number)
            }
        }
    }
}

private fun TurnConnectionType.toPjConstant(): Int =
    when (this) {
        TurnConnectionType.TCP -> pj_turn_tp_type.PJ_TURN_TP_TCP
        TurnConnectionType.UDP -> pj_turn_tp_type.PJ_TURN_TP_UDP
        TurnConnectionType.TLS -> pj_turn_tp_type.PJ_TURN_TP_TLS
    }

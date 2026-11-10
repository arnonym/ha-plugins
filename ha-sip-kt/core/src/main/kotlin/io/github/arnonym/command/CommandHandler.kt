package io.github.arnonym.command

import io.github.arnonym.config.Constants
import io.github.arnonym.event.WebhookToCall
import io.github.arnonym.ha.HaClient
import io.github.arnonym.json.boolOrDefault
import io.github.arnonym.json.doubleOrDefault
import io.github.arnonym.json.intOrDefault
import io.github.arnonym.json.objectOrNull
import io.github.arnonym.json.stringOrNull
import io.github.arnonym.json.stringValueOrNull
import io.github.arnonym.log.log
import io.github.arnonym.menu.PostAction
import io.github.arnonym.state.CallRegistry
import kotlinx.serialization.json.JsonObject
import java.io.File

class CommandHandler<C : CallHandle>(
    private val callRegistry: CallRegistry<C>,
    private val haClient: HaClient,
    private val defaultTtsLanguage: String,
    private val dial: (sipAccountNumber: Int, number: String, menu: JsonObject?, ringTimeout: Double, webhooks: WebhookToCall?) -> Unit,
    private val quit: () -> Unit,
) {
    fun isActive(key: String): Boolean = callRegistry.isActive(key)

    fun getCall(key: String): C? = callRegistry.getCall(key)

    fun registerCall(
        callbackId: String,
        call: C,
        additionalIds: List<String>,
    ) = callRegistry.registerCall(callbackId, call, additionalIds)

    fun forgetCall(callbackId: String) = callRegistry.forgetCall(callbackId)

    fun handleCommand(
        command: JsonObject,
        fromCall: C?,
    ) {
        val verb = command.stringOrNull("command")
        val number = command["number"]?.stringValueOrNull()

        when (verb) {
            "call_service", null -> handleCallService(command)
            "dial" -> handleDial(command, number)
            "hangup" -> handleHangup(command, number)
            "answer" -> handleAnswer(command, number)
            "transfer" -> handleTransfer(command, number)
            "bridge_audio" -> handleBridgeAudio(command, number, fromCall)
            "send_dtmf" -> handleSendDtmf(command, number)
            "play_audio_file" -> handlePlayAudioFile(command, number)
            "play_message" -> handlePlayMessage(command, number)
            "stop_playback" -> withCall("stop_playback", number) { it.stopPlayback() }
            "start_recording" -> handleStartRecording(command, number)
            "stop_recording" -> withCall("stop_recording", number) { it.stopRecording() }
            "state" -> callRegistry.output()
            "quit" -> {
                log(null, "Quit.")
                quit()
            }
            else -> log(null, "Error: Unknown command: $verb")
        }
    }

    /**
     * Resolves [number] to a live call and runs [body] on it, or logs why it could not.
     *
     * A single registry lookup on purpose: calls are forgotten from a pjsip worker thread
     * (`onCallState`, DISCONNECTED) while commands arrive on the stdin/MQTT threads, so a
     * "does it exist" check followed by a separate "give it to me" can lose the race in
     * between and throw out of the command loop.
     */
    private inline fun withCall(
        verb: String,
        number: String?,
        announce: Boolean = false,
        body: (C) -> Unit,
    ) {
        val identifier = requireNumber(verb, number) ?: return
        if (announce) log(null, "Got \"$verb\" command for $identifier")
        val call = callRegistry.getCall(identifier)
        if (call == null) {
            callNotInProgressError(identifier)
            return
        }
        body(call)
    }

    /** The `number` every call-directed command needs, or null (already logged) if absent. */
    private fun requireNumber(
        verb: String,
        number: String?,
    ): String? {
        if (number.isNullOrEmpty()) {
            log(null, "Error: Missing number for command \"$verb\"")
            return null
        }
        return number
    }

    private fun handleCallService(command: JsonObject) {
        val domain = command.stringOrNull("domain")
        val service = command.stringOrNull("service")
        val entityId = command.stringOrNull("entity_id")
        val serviceData = command.objectOrNull("service_data")
        if (domain.isNullOrEmpty() || service.isNullOrEmpty()) {
            log(null, "Error: one of domain or service was not provided")
            return
        }
        log(null, "Calling home assistant service on domain $domain service $service with entity $entityId")
        try {
            haClient.callService(domain, service, entityId, serviceData)
        } catch (e: Exception) {
            log(null, "Error calling home-assistant service: ${e.message}")
        }
    }

    private fun handleDial(
        command: JsonObject,
        number: String?,
    ) {
        val identifier = requireNumber("dial", number) ?: return
        log(null, "Got \"dial\" command for $identifier")
        if (isActive(identifier)) {
            log(null, "Warning: call already in progress: $identifier")
            return
        }
        val menu = command.objectOrNull("menu")
        val ringTimeout = command.doubleOrDefault("ring_timeout", Constants.DEFAULT_RING_TIMEOUT)
        val sipAccountNumber = command.intOrDefault("sip_account", -1)
        val webhooks = WebhookToCall.fromJson(command.objectOrNull("webhook_to_call"))
        dial(sipAccountNumber, identifier, menu, ringTimeout, webhooks)
    }

    private fun handleHangup(
        command: JsonObject,
        number: String?,
    ) = withCall("hangup", number, announce = true) { call ->
        call.hangupCall(command.intOrDefault("sip_code", 0))
    }

    private fun handleAnswer(
        command: JsonObject,
        number: String?,
    ) = withCall("answer", number, announce = true) { call ->
        val menu = command.objectOrNull("menu")
        val webhooks = WebhookToCall.fromJson(command.objectOrNull("webhook_to_call"))
        call.answerCall(menu, webhooks)
    }

    private fun handleTransfer(
        command: JsonObject,
        number: String?,
    ) {
        val identifier = requireNumber("transfer", number) ?: return
        val transferTo = command.stringOrNull("transfer_to")
        if (transferTo.isNullOrEmpty()) {
            log(null, "Error: Missing transfer_to for command \"transfer_to\"")
            return
        }
        withCall("transfer", identifier) { it.transfer(transferTo) }
    }

    private fun handleBridgeAudio(
        command: JsonObject,
        number: String?,
        fromCall: C?,
    ) {
        if (number.isNullOrEmpty()) {
            log(null, "Error: Missing number for command \"bridge_audio\"")
            return
        }
        val bridgeTo = command.stringOrNull("bridge_to")
        if (bridgeTo.isNullOrEmpty()) {
            log(null, "Error: Missing bridge_to for command \"bridge_audio\"")
            return
        }
        val callOne = if (number == "self") fromCall else getCall(number)
        val callTwo = if (bridgeTo == "self") fromCall else getCall(bridgeTo)
        if (callOne == null) {
            callNotInProgressError(number)
            return
        }
        if (callTwo == null) {
            callNotInProgressError(bridgeTo)
            return
        }
        callOne.bridgeAudio(callTwo)
    }

    private fun handleSendDtmf(
        command: JsonObject,
        number: String?,
    ) {
        val identifier = requireNumber("send_dtmf", number) ?: return
        val digits = command.stringOrNull("digits")
        val methodRaw = command.stringOrNull("method") ?: DtmfMethod.IN_BAND.wireValue
        val method = DtmfMethod.fromWireValueOrNull(methodRaw)
        if (method == null) {
            log(null, "Error: method must be one of in_band, rfc2833, sip_info")
            return
        }
        if (digits.isNullOrEmpty()) {
            log(null, "Error: Missing digits for command \"send_dtmf\"")
            return
        }
        withCall("send_dtmf", identifier, announce = true) { it.sendDtmf(digits, method) }
    }

    private fun handlePlayAudioFile(
        command: JsonObject,
        number: String?,
    ) {
        withCall("play_audio_file", number) { call ->
            val audioFile = command.stringOrNull("audio_file")
            if (audioFile.isNullOrEmpty()) {
                log(null, "Error: Missing parameter \"audio_file\" for command \"play_audio_file\"")
                return
            }
            val cacheAudio = command.boolOrDefault("cache_audio", false)
            val waitForAudioToFinish = command.boolOrDefault("wait_for_audio_to_finish", false)
            applyInlinePostAction(command, call)
            call.playAudioFile(audioFile, cacheAudio, waitForAudioToFinish)
        }
    }

    private fun handlePlayMessage(
        command: JsonObject,
        number: String?,
    ) {
        withCall("play_message", number) { call ->
            var message = command.stringOrNull("message")
            if (message.isNullOrEmpty()) {
                log(null, "Error: Missing parameter \"message\" for command \"play_message\"")
                return
            }
            if (command.boolOrDefault("handle_as_template", false)) {
                message = haClient.renderTemplate(message)
            }
            val ttsLanguage = command.stringOrNull("tts_language") ?: defaultTtsLanguage
            val cacheAudio = command.boolOrDefault("cache_audio", false)
            val waitForAudioToFinish = command.boolOrDefault("wait_for_audio_to_finish", false)
            applyInlinePostAction(command, call)
            call.playMessage(message, ttsLanguage, cacheAudio, waitForAudioToFinish)
        }
    }

    private fun handleStartRecording(
        command: JsonObject,
        number: String?,
    ) {
        withCall("start_recording", number) { call ->
            val recordingFile = command.stringOrNull("recording_file")
            if (recordingFile.isNullOrEmpty() || !File(recordingFile).isAbsolute) {
                log(null, "Error: Missing recording_file or path not absolute for command \"start_recording\"")
                return
            }
            call.startRecording(recordingFile)
        }
    }

    /** Shared `post_action` handling for `play_audio_file`/`play_message` (only "hangup" is supported inline). */
    private fun applyInlinePostAction(
        command: JsonObject,
        call: C,
    ) {
        when (command.stringOrNull("post_action")) {
            "hangup" -> call.setScheduledPostAction(PostAction.Hangup)
            "noop", null -> {}
            else -> log(null, "Only post_action \"hangup\" is supported. Assuming noop.")
        }
    }

    private fun callNotInProgressError(number: String) {
        log(null, "Warning: call not in progress: $number")
        callRegistry.output()
    }
}

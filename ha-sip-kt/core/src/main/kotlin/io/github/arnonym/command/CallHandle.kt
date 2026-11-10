package io.github.arnonym.command

import io.github.arnonym.event.WebhookToCall
import io.github.arnonym.menu.PostAction
import kotlinx.serialization.json.JsonObject

enum class DtmfMethod(val wireValue: String) {
    IN_BAND("in_band"),
    RFC2833("rfc2833"),
    SIP_INFO("sip_info"),
    ;

    companion object {
        fun fromWireValueOrNull(value: String?): DtmfMethod? = entries.find { it.wireValue == value }
    }
}

interface CallHandle {
    val callbackId: String

    fun hangupCall(sipCode: Int = 0)

    fun answerCall(
        newMenu: JsonObject?,
        overwriteWebhooks: WebhookToCall?,
    )

    fun transfer(transferTo: String)

    fun bridgeAudio(other: CallHandle)

    fun sendDtmf(
        digits: String,
        method: DtmfMethod,
    )

    fun playAudioFile(
        audioFile: String,
        cacheAudio: Boolean,
        waitForAudioToFinish: Boolean,
    )

    fun playMessage(
        message: String,
        language: String,
        cacheAudio: Boolean,
        waitForAudioToFinish: Boolean,
    )

    fun stopPlayback()

    fun startRecording(recordingFile: String)

    fun stopRecording()

    fun setScheduledPostAction(action: PostAction)
}

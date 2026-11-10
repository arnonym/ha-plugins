package io.github.arnonym.sip

import io.github.arnonym.audio.AudioCache
import io.github.arnonym.audio.CacheType
import io.github.arnonym.audio.audioFormatFromFilename
import io.github.arnonym.audio.convertAudioStreamToWavFile
import io.github.arnonym.command.CallHandle
import io.github.arnonym.command.CommandHandler
import io.github.arnonym.command.DtmfMethod
import io.github.arnonym.config.AnswerMode
import io.github.arnonym.config.Constants
import io.github.arnonym.event.CallDirection
import io.github.arnonym.event.CallInfo
import io.github.arnonym.event.CurrentPlayback
import io.github.arnonym.event.Event
import io.github.arnonym.event.EventSender
import io.github.arnonym.event.WebhookToCall
import io.github.arnonym.event.sendEvent
import io.github.arnonym.ha.HaClient
import io.github.arnonym.ha.HaConfig
import io.github.arnonym.ha.TtsResult
import io.github.arnonym.log.log
import io.github.arnonym.menu.Menu
import io.github.arnonym.menu.PostAction
import io.github.arnonym.menu.normalizeMenu
import io.github.arnonym.menu.prettyPrintMenu
import kotlinx.serialization.json.JsonObject
import org.pjsip.pjsua2.AudioMedia
import org.pjsip.pjsua2.AudioMediaRecorder
import org.pjsip.pjsua2.CallOpParam
import org.pjsip.pjsua2.CallSendDtmfParam
import org.pjsip.pjsua2.OnCallMediaStateParam
import org.pjsip.pjsua2.OnCallReplaceRequestParam
import org.pjsip.pjsua2.OnCallReplacedParam
import org.pjsip.pjsua2.OnCallRxOfferParam
import org.pjsip.pjsua2.OnCallRxReinviteParam
import org.pjsip.pjsua2.OnCallStateParam
import org.pjsip.pjsua2.OnCallTransferRequestParam
import org.pjsip.pjsua2.OnCallTransferStatusParam
import org.pjsip.pjsua2.OnCallTxOfferParam
import org.pjsip.pjsua2.OnDtmfDigitParam
import org.pjsip.pjsua2.ToneGenerator
import org.pjsip.pjsua2.pjmedia_type
import org.pjsip.pjsua2.pjsip_inv_state
import org.pjsip.pjsua2.pjsua_call_media_status
import org.pjsip.pjsua2.pjsua_dtmf_method
import java.io.File
import java.util.concurrent.TimeUnit
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock
import org.pjsip.pjsua2.Call as PjCall

fun makeCall(
    account: Account,
    uriToCall: String,
    menu: JsonObject?,
    commandHandler: CommandHandler<Call>,
    eventSender: EventSender,
    haConfig: HaConfig,
    haClient: HaClient,
    ringTimeout: Double,
    webhooks: WebhookToCall?,
): Call? {
    val newCall =
        Call(
            account, PJSUA_INVALID_ID, uriToCall, menu, commandHandler, eventSender, haConfig, haClient,
            ringTimeout, webhooks, emptyMap(),
        )
    val callParam = CallOpParam(true)
    if (!account.config.globalOptions.textMedia) callParam.opt.textCount = 0
    try {
        newCall.makeCall(uriToCall, callParam)
    } catch (e: Exception) {
        log(null, "Error making call to $uriToCall: ${e.message}")
        commandHandler.forgetCall(newCall.callbackId)
        // `isActive` is false at PJSUA_INVALID_ID, so this is destroyed on the next drain
        // rather than left for the finalizer.
        CallDisposal.enqueue(newCall)
        return null
    }
    newCall.sendEvent(Event.OutgoingCallInitiated)
    return newCall
}

const val PJSUA_INVALID_ID = -1

class Call(
    val account: Account,
    callId: Int,
    private val uriToCall: String?,
    initialMenu: JsonObject?,
    private val commandHandler: CommandHandler<Call>,
    private val eventSender: EventSender,
    val haConfig: HaConfig,
    private val haClient: HaClient,
    private val ringTimeout: Double,
    private var webhooks: WebhookToCall?,
    private var sipHeaders: Map<String, String?> = emptyMap(),
) : PjCall(account, callId), CallHandle {
    private val lock = ReentrantLock()

    private fun log(message: String) = log(account.config.index, message)

    private val pendingSipCalls = mutableListOf<() -> Unit>()

    private fun deferSipCall(action: () -> Unit) {
        pendingSipCalls.add(action)
    }

    private fun flushSipCalls() {
        while (true) {
            val next = lock.withLock { pendingSipCalls.removeFirstOrNull() } ?: return
            try {
                next()
            } catch (e: Exception) {
                log("Error: SIP operation failed: ${e.message}")
            }
        }
    }

    val direction: CallDirection = if (uriToCall != null) CallDirection.OUTGOING else CallDirection.INCOMING

    private var player: Player? = null
    var audioMedia: AudioMedia? = null
        private set
    private var recorder: AudioMediaRecorder? = null
    private var toneGen: ToneGenerator? = null

    private var recordingFile: String? = null
    private var requestedRecordingFilename: String? = null
    private var connected = false
    private var currentInput = ""
    private var scheduledPostAction: PostAction? = null
    private var playbackIsDone = true
    private var waitForAudioToFinish = false
    private var lastSeenMillis = System.currentTimeMillis()
    private var callSettledAtMillis: Long? = null
    private var answerAtMillis: Long? = null
    private var ringTimeoutFired = false

    private var disposed = false

    private var fetchedAudio: TtsResult? = null

    private var ttsGeneration = 0L
    private var callInfo: CallInfo? = null
    private val pressedDigitList = mutableListOf<String>()
    private var currentPlayback: CurrentPlayback? = null

    private var menu: Menu?
    private var menuMap: Map<String, Menu>

    override val callbackId: String

    init {
        val (normalizedMenu, map) = normalizeMenu(initialMenu, haConfig.ttsConfig.language, account.config.index)
        menu = normalizedMenu
        menuMap = map
        prettyPrintMenu(menu)
        val (id, otherIds) = getCallbackIds()
        callbackId = id
        log("Registering call with id $callbackId")
        commandHandler.registerCall(callbackId, this, otherIds)
    }

    fun handleEvents() {
        try {
            lock.withLock { tick() }
        } finally {
            // Outside the lock, and in a `finally` because `tick` returns early all over
            // the place -- this is the only thing that ever runs the deferred SIP calls.
            flushSipCalls()
        }
    }

    private fun tick() {
        // The tick iterates a snapshot of the registry, which can still contain a call
        // that disconnected (and released its pjsua2 peer) in the meantime.
        if (disposed) return
        val now = System.currentTimeMillis()
        if (!connected && !ringTimeoutFired && now - lastSeenMillis > (ringTimeout * 1000).toLong()) {
            // Latched: this branch mutates nothing the condition reads, and DISCONNECTED
            // takes a while to come back, so without it the tick re-fires the webhook
            // every 10 ms in the meantime.
            ringTimeoutFired = true
            sendEvent(Event.RingTimeout)
            log("Ring timeout of $ringTimeout triggered")
            hangupCall()
            return
        }
        val answerAt = answerAtMillis
        if (!connected && answerAt != null && answerAt < now) {
            log("Call will be answered now.")
            answerAtMillis = null
            // The only answer that carries an SDP, so the only one text media can bloat.
            val callParam = answerCallParam()
            callParam.statusCode = 200
            deferSipCall { answer(callParam) }
            return
        }
        val settledAt = callSettledAtMillis
        if (!connected && settledAt != null && settledAt < now) {
            callSettledAtMillis = null
            handleConnectedState()
            return
        }
        if (!connected) return
        val timeoutSeconds = menu?.timeout ?: MENU_LESS_IDLE_TIMEOUT_SECONDS
        if (now - lastSeenMillis > (timeoutSeconds * 1000).toLong()) {
            log("Timeout of $timeoutSeconds triggered")
            /* reset the time-out, so it doesn't keep firing every tick for menu-less calls */
            resetTimeout()
            menu?.let {
                handleMenu(it.timeoutChoice)
                sendEvent(Event.Timeout(it.id))
            }
            return
        }
        val fetched = fetchedAudio
        if (fetched != null) {
            fetchedAudio = null
            // Started here rather than on the TTS thread: creating the player is a
            // pjsua2 call, and the tick runs on a thread pjsip knows about.
            playWavFile(fetched.fileName, fetched.mustBeDeleted, waitForAudioToFinish)
            return
        }
        val postAction = scheduledPostAction
        if (playbackIsDone && postAction != null) {
            scheduledPostAction = null
            handlePostAction(postAction)
            return
        }
        if (pressedDigitList.isNotEmpty()) {
            val nextDigit = pressedDigitList.removeAt(0)
            handleDtmfDigit(nextDigit)
            return
        }
    }

    private fun handlePostAction(postAction: PostAction) {
        log("Scheduled post action: ${postAction.action}")
        when (postAction) {
            is PostAction.Noop -> {}
            is PostAction.Return -> {
                val current = menu
                if (current == null) {
                    log("No menu to return to")
                    return
                }
                val target = generateSequence(current) { it.parentMenu }.elementAtOrNull(postAction.level)
                if (target != null) handleMenu(target) else log("Could not return ${postAction.level} level in current menu")
            }
            is PostAction.Jump -> {
                val newMenu = menuMap[postAction.menuId]
                if (newMenu != null) {
                    handleMenu(newMenu)
                } else {
                    log("Could not find menu_id: \"${postAction.menuId}\". Valid IDs are ${menuMap.keys}")
                }
            }
            is PostAction.Hangup -> hangupCall()
            is PostAction.RepeatMessage -> handleMenu(menu, sendWebhookEvent = false, handleAction = false, resetInput = false)
        }
    }

    fun sendEvent(event: Event) {
        sendEvent(event, callInfo, account.config.index, callbackId, eventSender, webhooks)
    }

    private fun handleConnectedState() {
        log("Call is established.")
        connected = true
        resetTimeout()
        sendEvent(Event.CallEstablished)
        handleMenu(menu)
    }

    override fun onCallState(prm: OnCallStateParam) {
        var disconnected = false
        lock.withLock {
            if (callInfo == null) callInfo = getCallInfo()
            val ci = info
            when (ci.state) {
                pjsip_inv_state.PJSIP_INV_STATE_EARLY -> log("Early")
                pjsip_inv_state.PJSIP_INV_STATE_CALLING -> log("Calling")
                pjsip_inv_state.PJSIP_INV_STATE_CONNECTING -> log("Call connecting...")
                pjsip_inv_state.PJSIP_INV_STATE_CONFIRMED -> {
                    log("Call connected")
                    extractHeadersFromResponse(prm)
                    callSettledAtMillis = System.currentTimeMillis() + (account.config.settleTime * 1000).toLong()
                }
                pjsip_inv_state.PJSIP_INV_STATE_DISCONNECTED -> {
                    log("Call disconnected (${ci.lastStatusCode} ${ci.lastReason})")
                    stopRecording()
                    sendEvent(Event.CallDisconnected)
                    discardPendingTts()
                    connected = false
                    callSettledAtMillis = null
                    currentInput = ""
                    player = null
                    audioMedia = null
                    toneGen = null
                    // Anything still queued is an answer/hangup for a call that no longer
                    // exists. Dropping it here is what guarantees no deferred operation can
                    // reach a pjsua2 peer that [CallDisposal] has already destroyed.
                    pendingSipCalls.clear()
                    commandHandler.forgetCall(callbackId)
                    disposed = true
                    disconnected = true
                }
                else -> log("Unknown state: ${ci.state}")
            }
        }
        // The destruction itself has to wait until pjsua has released the call's id slot
        // -- see [CallDisposal], which is emphatically not a detail worth inlining here.
        if (disconnected) CallDisposal.enqueue(this)
    }

    override fun onCallMediaState(prm: OnCallMediaStateParam): Unit =
        lock.withLock {
            val ci = info
            log("onCallMediaState call info state ${ci.state}")
            ci.media.forEachIndexed { mediaIndex, media ->
                if (media.type == pjmedia_type.PJMEDIA_TYPE_AUDIO &&
                    (
                        media.status == pjsua_call_media_status.PJSUA_CALL_MEDIA_ACTIVE ||
                            media.status == pjsua_call_media_status.PJSUA_CALL_MEDIA_REMOTE_HOLD
                    )
                ) {
                    log("Connected media ${media.status}")
                    audioMedia = getAudioMedia(mediaIndex)
                    val requested = requestedRecordingFilename
                    if (requested != null && recorder == null) {
                        startRecording(requested)
                    }
                }
            }
        }

    override fun onDtmfDigit(prm: OnDtmfDigitParam): Unit =
        lock.withLock {
            if (!playbackIsDone && waitForAudioToFinish) {
                resetTimeout()
                return
            }
            stopPlayback()
            resetTimeout()
            // Queued rather than handled here: `handleDtmfDigit` can enter a menu, and
            // entering a menu can block on TTS. The tick picks it up on its own thread.
            pressedDigitList.add(prm.digit)
        }

    private fun handleDtmfDigit(pressedDigit: String) {
        log("onDtmfDigit: digit $pressedDigit")
        sendEvent(Event.DtmfDigit(pressedDigit))
        val currentMenu = menu ?: return
        currentInput += pressedDigit
        log("Current input: $currentInput")
        val choices = currentMenu.choices
        if (currentInput in choices) {
            handleMenu(choices.getValue(currentInput))
            return
        }
        if (currentMenu.choicesArePin) {
            val maxChoiceLength = choices.keys.maxOfOrNull { it.length } ?: 0
            if (currentInput.length == maxChoiceLength) {
                log("No PIN matched $currentInput")
                handleMenu(currentMenu.defaultChoice)
            }
        } else {
            val stillValid = choices.keys.any { it.startsWith(currentInput) }
            if (!stillValid) {
                log("Invalid input $currentInput")
                handleMenu(currentMenu.defaultChoice)
            }
        }
    }

    override fun onCallTransferRequest(prm: OnCallTransferRequestParam) {
        log("onCallTransferRequest")
    }

    override fun onCallTransferStatus(prm: OnCallTransferStatusParam) {
        log("onCallTransferStatus. Status code: ${prm.statusCode} (${prm.reason})")
    }

    override fun onCallReplaceRequest(prm: OnCallReplaceRequestParam) {
        log("onCallReplaceRequest")
    }

    override fun onCallReplaced(prm: OnCallReplacedParam) {
        log("onCallReplaced")
    }

    override fun onCallRxOffer(prm: OnCallRxOfferParam) {
        log("onCallRxOffer")
    }

    override fun onCallRxReinvite(prm: OnCallRxReinviteParam) {
        log("onCallRxReinvite")
    }

    override fun onCallTxOffer(prm: OnCallTxOfferParam) {
        log("onCallTxOffer")
    }

    private fun handleMenu(
        newMenu: Menu?,
        sendWebhookEvent: Boolean = true,
        handleAction: Boolean = true,
        resetInput: Boolean = true,
    ) {
        resetTimeout()
        if (newMenu == null) {
            log("No menu supplied")
            return
        }
        menu = newMenu
        val menuId = newMenu.id
        if (menuId != null && sendWebhookEvent) {
            sendEvent(Event.EnteredMenu(menuId))
        }
        if (resetInput) currentInput = ""
        var message = newMenu.message
        if (!message.isNullOrEmpty()) {
            if (newMenu.handleAsTemplate) message = haClient.renderTemplate(message)
            playMessage(message, newMenu.language, newMenu.cacheAudio, newMenu.waitForAudioToFinish)
        }
        val audioFile = newMenu.audioFile
        if (!audioFile.isNullOrEmpty()) {
            playAudioFile(audioFile, newMenu.cacheAudio, newMenu.waitForAudioToFinish)
        }
        if (handleAction) handleAction(newMenu.action)
        scheduledPostAction = newMenu.postAction
    }

    private fun handleAction(action: JsonObject?) {
        if (action == null) {
            log("No action supplied")
            return
        }
        commandHandler.handleCommand(action, this)
    }

    override fun playMessage(
        message: String,
        language: String,
        cacheAudio: Boolean,
        waitForAudioToFinish: Boolean,
    ): Unit =
        lock.withLock {
            log("Playing message: $message")
            discardPendingTts()
            val cachedFile =
                AudioCache.getCachedFile(
                    cacheAudio,
                    haConfig.cacheDir,
                    CacheType.MESSAGE,
                    message,
                    haConfig.audioSampleRate,
                )
            if (cachedFile != null) {
                currentPlayback = CurrentPlayback.Message(message)
                playWavFile(cachedFile, false, waitForAudioToFinish)
                return
            }
            // Not cached, so this needs a synthesis round-trip to HA -- seconds, on the
            // thread that ticks every other call. Fetch it off-thread and claim playback
            // now: `playbackIsDone = false` is what keeps the scheduled post action and
            // `wait_for_audio_to_finish` honest while the audio is still being made.
            currentPlayback = CurrentPlayback.Message(message)
            playbackIsDone = false
            this.waitForAudioToFinish = waitForAudioToFinish
            val generation = ttsGeneration
            haClient.createAndGetTtsAsync(message, language) { result ->
                AudioCache.cacheFile(
                    cacheAudio && result.wasSuccessful,
                    haConfig.cacheDir,
                    CacheType.MESSAGE,
                    message,
                    result.fileName,
                    haConfig.audioSampleRate,
                )
                onTtsFetched(generation, result)
            }
        }

    /**
     * Hands a finished fetch to the tick, or throws it away if the prompt it belongs to
     * is no longer current.
     *
     * Runs on a TTS thread, which pjsip knows nothing about, so storing a field is all
     * that may happen here -- the tick is what starts the player.
     */
    private fun onTtsFetched(
        generation: Long,
        result: TtsResult,
    ): Unit =
        lock.withLock {
            if (generation != ttsGeneration) {
                log("Discarding TTS audio for a prompt that is no longer current.")
                if (result.mustBeDeleted) File(result.fileName).delete()
                return
            }
            fetchedAudio = result
        }

    /** Caller holds [lock]. Invalidates a fetch in flight and drops one that already landed. */
    private fun discardPendingTts() {
        ttsGeneration++
        fetchedAudio?.let { if (it.mustBeDeleted) File(it.fileName).delete() }
        fetchedAudio = null
    }

    override fun playAudioFile(
        audioFile: String,
        cacheAudio: Boolean,
        waitForAudioToFinish: Boolean,
    ): Unit =
        lock.withLock {
            log("Playing audio file: $audioFile")
            // Supersedes a prompt still being synthesized, the way it would supersede one
            // already playing: a menu with both `message` and `audio_file` plays the file.
            discardPendingTts()
            val cachedFile =
                AudioCache.getCachedFile(
                    cacheAudio,
                    haConfig.cacheDir,
                    CacheType.AUDIO_FILE,
                    audioFile,
                    haConfig.audioSampleRate,
                )
            if (cachedFile != null) {
                currentPlayback = CurrentPlayback.AudioFile(audioFile)
                playWavFile(cachedFile, false, waitForAudioToFinish)
                return
            }
            val fileFormat = audioFormatFromFilename(audioFile)
            if (fileFormat == null) {
                log("Error getting audio format from filename: $audioFile")
                return
            }
            val audioFileContent = File(audioFile).readBytes()
            val soundFileName = convertAudioStreamToWavFile(audioFileContent, fileFormat, haConfig.audioSampleRate)
            if (soundFileName == null) {
                log("Could not convert to wav: $audioFile")
                return
            }
            currentPlayback = CurrentPlayback.AudioFile(audioFile)
            AudioCache.cacheFile(
                cacheAudio,
                haConfig.cacheDir,
                CacheType.AUDIO_FILE,
                audioFile,
                soundFileName,
                haConfig.audioSampleRate,
            )
            playWavFile(soundFileName, true, waitForAudioToFinish)
        }

    private fun playWavFile(
        soundFileName: String,
        mustBeDeleted: Boolean,
        waitForAudioToFinish: Boolean,
    ) {
        val media = audioMedia
        if (media != null) {
            playbackIsDone = false
            this.waitForAudioToFinish = waitForAudioToFinish
            val newPlayer = Player(::onPlaybackDone)
            player = newPlayer
            newPlayer.playFile(media, soundFileName)
        } else {
            log("Audio media not connected. Cannot play audio stream!")
            // Playback was claimed when the fetch was requested; release it, or the
            // scheduled post action would wait for a player that never starts.
            playbackIsDone = true
        }
        if (mustBeDeleted) File(soundFileName).delete()
    }

    private fun onPlaybackDone(): Unit =
        lock.withLock {
            log("Playback done.")
            currentPlayback?.let { sendEvent(it.toPlaybackDoneEvent()) }
            currentPlayback = null
            playbackIsDone = true
            player = null
        }

    override fun stopPlayback(): Unit =
        lock.withLock {
            if (!playbackIsDone) {
                log("Playback interrupted.")
                discardPendingTts()
                player?.let { p -> audioMedia?.let { p.stopTransmit(it) } }
                player = null
                playbackIsDone = true
            }
        }

    override fun startRecording(recordingFile: String): Unit =
        lock.withLock {
            val existingRecorder = recorder
            if (existingRecorder != null) {
                log("Recording already running -> reattaching")
                audioMedia?.let { media ->
                    try {
                        media.stopTransmit(existingRecorder)
                    } catch (_: Exception) {
                    }
                    try {
                        media.startTransmit(existingRecorder)
                    } catch (e: Exception) {
                        log("Error: Could not reattach recorder: ${e.message}")
                    }
                }
                return
            }
            val media = audioMedia
            if (media == null) {
                log("Audio media not connected yet. Recording will start once media is available")
                requestedRecordingFilename = recordingFile
                return
            }
            requestedRecordingFilename = null
            val targetDir = File(recordingFile).parentFile
            if (targetDir == null || !targetDir.isDirectory) {
                log("Error: Call recordings directory not found: $targetDir")
                return
            }
            val newRecorder = AudioMediaRecorder()
            try {
                newRecorder.createRecorder(recordingFile)
                media.startTransmit(newRecorder)
            } catch (e: Exception) {
                log("Error: Failed to start call recording: ${e.message}")
                recorder = newRecorder
                stopRecording()
                return
            }
            recorder = newRecorder
            this.recordingFile = recordingFile
            log("Call recording started: $recordingFile")
            sendEvent(Event.RecordingStarted(recordingFile))
        }

    override fun stopRecording(): Unit =
        lock.withLock {
            requestedRecordingFilename = null
            val existingRecorder = recorder ?: return
            try {
                audioMedia?.stopTransmit(existingRecorder)
            } catch (e: Exception) {
                log("Error: Failed to stop call recording: ${e.message}")
            }
            try {
                existingRecorder.delete()
            } catch (e: Exception) {
                log("Error: Failed to close call recording file: ${e.message}")
            }
            recordingFile?.let { file ->
                log("Call recording stopped: $file")
                sendEvent(Event.RecordingStopped(file))
            }
            recorder = null
            recordingFile = null
        }

    fun accept(
        answerMode: AnswerMode,
        answerAfter: Double,
    ): Unit =
        lock.withLock {
            if (answerMode == AnswerMode.REJECT) {
                val sipCode = account.config.options.rejectSipCode
                log("Rejecting call with SIP code $sipCode.")
                val callParam = CallOpParam()
                callParam.statusCode = sipCode
                callParam.reason = REASON_PHRASES[sipCode] ?: ""
                deferSipCall { answer(callParam) }
                return
            }
            val callParam = CallOpParam()
            callParam.statusCode = 180
            deferSipCall { answer(callParam) }
            if (answerMode == AnswerMode.ACCEPT) {
                answerAtMillis = System.currentTimeMillis() + (answerAfter * 1000).toLong()
            }
        }

    private fun answerCallParam(): CallOpParam =
        if (account.config.globalOptions.textMedia) {
            CallOpParam()
        } else {
            CallOpParam(true).also { it.opt.textCount = 0 }
        }

    override fun hangupCall(sipCode: Int): Unit =
        lock.withLock {
            log("Hang-up.")
            val callParam = CallOpParam(true)
            if (sipCode != 0 && !connected) {
                callParam.statusCode = sipCode
                callParam.reason = REASON_PHRASES[sipCode] ?: ""
            }
            deferSipCall { hangup(callParam) }
        }

    override fun answerCall(
        newMenu: JsonObject?,
        overwriteWebhooks: WebhookToCall?,
    ): Unit =
        lock.withLock {
            log("Trigger answer of call (if not established already)")
            if (newMenu != null) {
                val (normalized, map) = normalizeMenu(newMenu, haConfig.ttsConfig.language, account.config.index)
                menu = normalized
                menuMap = map
                prettyPrintMenu(menu)
            }
            if (overwriteWebhooks != null) webhooks = overwriteWebhooks
            if (connected) {
                if (newMenu != null) handleMenu(menu)
            } else {
                answerAtMillis = System.currentTimeMillis()
            }
        }

    override fun transfer(transferTo: String): Unit =
        lock.withLock {
            log("Transfer call to $transferTo")
            val xferParam = CallOpParam(true)
            deferSipCall { xfer(transferTo, xferParam) }
        }

    override fun bridgeAudio(other: CallHandle) {
        require(other is Call) { "bridgeAudio requires another Call instance" }
        val (firstLock, secondLock) = if (callbackId <= other.callbackId) lock to other.lock else other.lock to lock
        if (!firstLock.tryLock(BRIDGE_LOCK_TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
            log("Could not acquire lock for bridge_audio within timeout; aborting.")
            return
        }
        try {
            if (!secondLock.tryLock(BRIDGE_LOCK_TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
                log("Could not acquire partner call's lock for bridge_audio within timeout; aborting.")
                return
            }
            try {
                val myMedia = audioMedia
                val otherMedia = other.audioMedia
                if (myMedia != null && otherMedia != null) {
                    log("Connect audio stream of \"$callbackId\" and \"${other.callbackId}\"")
                    myMedia.startTransmit(otherMedia)
                    otherMedia.startTransmit(myMedia)
                    log("Audio streams connected.")
                } else {
                    log("At least one audio media is not connected. Cannot bridge audio between calls!")
                }
            } finally {
                secondLock.unlock()
            }
        } finally {
            firstLock.unlock()
        }
    }

    override fun sendDtmf(
        digits: String,
        method: DtmfMethod,
    ): Unit =
        lock.withLock {
            resetTimeout()
            log("Sending DTMF $digits")
            when (method) {
                DtmfMethod.IN_BAND -> {
                    val media = audioMedia
                    if (media == null) {
                        log("Audio media not connected. Cannot send DTMF in-band!")
                        return
                    }
                    var generator = toneGen
                    if (generator == null) {
                        generator = ToneGenerator()
                        generator.createToneGenerator()
                        generator.startTransmit(media)
                        toneGen = generator
                    }
                    generator.playDigits(createToneDigitVector(digits))
                }
                DtmfMethod.RFC2833 -> {
                    val dtmfParam = CallSendDtmfParam()
                    dtmfParam.method = pjsua_dtmf_method.PJSUA_DTMF_METHOD_RFC2833
                    dtmfParam.duration = Constants.DEFAULT_DTMF_ON
                    dtmfParam.digits = digits
                    deferSipCall { sendDtmf(dtmfParam) }
                }
                DtmfMethod.SIP_INFO -> {
                    val dtmfParam = CallSendDtmfParam()
                    dtmfParam.method = pjsua_dtmf_method.PJSUA_DTMF_METHOD_SIP_INFO
                    dtmfParam.duration = Constants.DEFAULT_DTMF_ON
                    dtmfParam.digits = digits
                    deferSipCall { sendDtmf(dtmfParam) }
                }
            }
        }

    override fun setScheduledPostAction(action: PostAction): Unit =
        lock.withLock {
            scheduledPostAction = action
        }

    private fun getCallbackIds(): Pair<String, List<String>> {
        val uri = uriToCall
        if (uri != null) {
            val parsedUri = parseSipUri(uri)
            return uri to listOfNotNull(parsedUri)
        }
        val info = getCallInfo()
        return info.remoteUri to listOfNotNull(info.parsedRemoteUri, info.callId)
    }

    fun getCallInfo(): CallInfo =
        lock.withLock {
            val ci = info
            val parsedRemoteUri = parseSipUri(ci.remoteUri)
            val parsedLocalUri = parseSipUri(ci.localUri)
            return CallInfo(
                localUri = ci.localUri,
                remoteUri = ci.remoteUri,
                parsedRemoteUri = parsedRemoteUri,
                parsedLocalUri = parsedLocalUri,
                callId = ci.callIdString,
                headers = sipHeaders,
                direction = direction,
            )
        }

    private fun extractHeadersFromResponse(prm: OnCallStateParam) {
        val extractHeaders = account.config.options.extractHeaders
        val debugHeaders = account.config.globalOptions.debugHeaders
        if (extractHeaders.isEmpty() && !debugHeaders) return
        if (sipHeaders.isNotEmpty()) return
        val wholeMsg =
            try {
                prm.e.body.tsxState.src.rdata.wholeMsg
            } catch (e: Exception) {
                null
            } ?: return
        if (debugHeaders) Account.logAllSipHeaders(account.config.index, wholeMsg)
        if (extractHeaders.isNotEmpty()) {
            sipHeaders = Account.parseSipHeaders(wholeMsg, extractHeaders)
            callInfo = callInfo?.copy(headers = sipHeaders)
        }
    }

    private fun resetTimeout() {
        lastSeenMillis = System.currentTimeMillis()
    }

    companion object {
        private const val BRIDGE_LOCK_TIMEOUT_SECONDS = 2L

        /* for testing */
        private val MENU_LESS_IDLE_TIMEOUT_SECONDS: Double =
            System.getProperty("hasip.menuLessIdleTimeoutSeconds")?.toDoubleOrNull()
                ?: Constants.DEFAULT_RING_TIMEOUT

        fun parseSipUri(sipUri: String): String? {
            val match = Regex("<sip:(.+?)[@;>]").find(sipUri)
            if (match != null) return match.groupValues[1]
            val fallback = Regex("sip:(.+?)($|[@;])").find(sipUri)
            if (fallback != null) return fallback.groupValues[1]
            return null
        }
    }
}

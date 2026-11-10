package io.github.arnonym.integrationtest

/**
 * Incoming-call menus for the callee, built as YAML strings rather than checked-in
 * fixture files so each scenario's menu sits next to the assertions about it.
 *
 * Most use `audio_file` rather than `message`, which keeps TTS -- and therefore any need
 * for a real Home Assistant -- out of the picture entirely. The handful that do speak are
 * named accordingly and belong to [TtsTest].
 */
object Menus {
    private val hello get() = DirectIpStack.helloWav.absolutePath

    /**
     * Plays one file and then sits still, for [AudioFidelityTest].
     *
     * `cache_audio: false` so every run actually goes through the ffmpeg conversion and
     * the player, which is the path under examination; the long timeout keeps the call up
     * while the caller finishes recording what arrived.
     */
    fun playing(audioFile: String): String =
        """
        answer_after: 0
        menu:
            id: main
            audio_file: $audioFile
            cache_audio: false
            wait_for_audio_to_finish: false
            post_action: noop
            timeout: 60
        """.trimIndent()

    /**
     * Two-level navigation menu with a long inactivity timeout, so timing scenarios
     * can't be perturbed by it. `9` descends a level; `1` and `9`->`2` hang up.
     */
    val navigation: String =
        """
        answer_after: 0
        menu:
            id: main
            audio_file: $hello
            cache_audio: false
            wait_for_audio_to_finish: false
            post_action: noop
            timeout: 60
            choices:
                "1":
                    id: chosen
                    audio_file: $hello
                    post_action: hangup
                "9":
                    id: level1
                    audio_file: $hello
                    post_action: noop
                    timeout: 60
                    choices:
                        "2":
                            id: level2
                            audio_file: $hello
                            post_action: hangup
        """.trimIndent()

    /** Answers only after [answerAfter] seconds -- exercises the deferred-answer path. */
    fun deferredAnswer(answerAfter: Int): String =
        """
        answer_after: $answerAfter
        menu:
            id: main
            audio_file: $hello
            post_action: noop
            timeout: 60
        """.trimIndent()

    /** Hangs up [timeout] seconds after the last caller activity, via an explicit `timeout` choice. */
    fun inactivityTimeout(timeout: Int): String =
        """
        answer_after: 0
        menu:
            id: main
            audio_file: $hello
            post_action: noop
            timeout: $timeout
            choices:
                timeout:
                    id: timed-out
                    audio_file: $hello
                    post_action: hangup
        """.trimIndent()

    /**
     * A long timeout at the top level and a short one a keypress away.
     *
     * This is the shape that catches a timeout implementation which arms its timer
     * once and never re-derives the deadline: entering `impatient` must shorten the
     * pending deadline from 60 s to 2 s immediately, not at the next 60 s expiry.
     */
    val shrinkingTimeout: String =
        """
        answer_after: 0
        menu:
            id: main
            audio_file: $hello
            post_action: noop
            timeout: 60
            choices:
                "1":
                    id: impatient
                    audio_file: $hello
                    post_action: noop
                    timeout: 2
                    choices:
                        timeout:
                            id: impatient-timed-out
                            audio_file: $hello
                            post_action: hangup
        """.trimIndent()

    /** Menu passed to an outgoing `dial`, or to an explicit `answer` command. */
    fun simple(id: String): String =
        """
        {"id": "$id", "audio_file": "$hello", "post_action": "noop", "timeout": 60}
        """.trimIndent()

    /**
     * Wrong input falls through to `default`, at both levels.
     *
     * `1` is the only valid choice, so `5` cannot be a prefix of anything and is rejected
     * as soon as it is pressed. The PIN sub-menu then only rejects once the input reaches
     * the length of the longest choice -- a different rule, exercised by the same menu.
     */
    val defaultChoice: String =
        """
        answer_after: 0
        menu:
            id: main
            audio_file: $hello
            post_action: noop
            timeout: 60
            choices:
                "1":
                    id: pin-entry
                    audio_file: $hello
                    post_action: noop
                    timeout: 60
                    choices_are_pin: true
                    choices:
                        "1234":
                            id: pin-accepted
                            audio_file: $hello
                            post_action: hangup
                        default:
                            id: pin-rejected
                            audio_file: $hello
                            post_action: hangup
                default:
                    id: rejected
                    audio_file: $hello
                    post_action: noop
                    timeout: 60
        """.trimIndent()

    /**
     * Three levels deep, navigated back out with `post_action: return`.
     *
     * `return` with a level of 2 must land on `main`, not on `deep` or on nothing --
     * the case that catches an off-by-one in the parent-menu walk.
     */
    val returnAndJump: String =
        """
        answer_after: 0
        menu:
            id: main
            audio_file: $hello
            post_action: noop
            timeout: 60
            choices:
                "1":
                    id: deep
                    audio_file: $hello
                    post_action: noop
                    timeout: 60
                    choices:
                        "2":
                            id: deepest
                            audio_file: $hello
                            post_action: return 2
                "9":
                    id: jumper
                    audio_file: $hello
                    post_action: jump landing
                "8":
                    id: landing
                    audio_file: $hello
                    post_action: noop
                    timeout: 60
        """.trimIndent()

    /**
     * A prompt that refuses to be interrupted.
     *
     * `wait_for_audio_to_finish` makes DTMF arriving mid-playback reset the inactivity
     * timeout and otherwise be dropped -- so the digit below must not navigate anywhere,
     * even though `1` is a valid choice.
     */
    val uninterruptiblePrompt: String =
        """
        answer_after: 0
        menu:
            id: main
            audio_file: $hello
            wait_for_audio_to_finish: true
            post_action: noop
            timeout: 60
            choices:
                "1":
                    id: chosen
                    audio_file: $hello
                    post_action: hangup
        """.trimIndent()

    /**
     * The navigation menu behind a caller-id filter.
     *
     * Both lists are emitted so a scenario can prove ha-sip refuses the combination too;
     * pass only one of them for the ordinary allow/block cases.
     */
    fun screened(
        allowed: List<String>? = null,
        blocked: List<String>? = null,
    ): String =
        buildString {
            allowed?.let { appendLine("allowed_numbers: [${it.joinToString(", ")}]") }
            blocked?.let { appendLine("blocked_numbers: [${it.joinToString(", ")}]") }
            append(navigation)
        }

    /** A menu whose prompt is synthesized rather than played from disk. */
    fun spoken(
        id: String,
        message: String = "this prompt comes from text to speech",
        cacheAudio: Boolean = false,
    ): String =
        """
        {"id": "$id", "message": "$message", "cache_audio": $cacheAudio, "post_action": "noop", "timeout": 60}
        """.trimIndent()

    /**
     * Incoming-call menu whose prompt is synthesized, with a choice behind it.
     *
     * On the callee rather than passed to `dial`, because the digit that interrupts the
     * prompt has to arrive at the instance that is doing the synthesizing.
     */
    val spokenIncoming: String =
        """
        answer_after: 0
        menu:
            id: spoken
            message: this prompt comes from text to speech
            cache_audio: false
            post_action: noop
            timeout: 60
            choices:
                "1":
                    id: interrupted
                    audio_file: $hello
                    post_action: noop
                    timeout: 60
        """.trimIndent()

    /**
     * The one menu that uses `message` rather than `audio_file`, so entering it goes
     * through Home Assistant TTS -- which [EventCollector.stallTts] can hold open for
     * as long as a test needs.
     */
    fun spokenMessage(): String =
        """
        {"id": "spoken", "message": "this prompt is deliberately slow", "post_action": "noop", "timeout": 60}
        """.trimIndent()
}

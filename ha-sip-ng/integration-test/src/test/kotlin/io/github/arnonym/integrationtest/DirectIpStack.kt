package io.github.arnonym.integrationtest

import java.io.File
import java.nio.file.Files

/** Callee-side configuration that is only read at ha-sip startup, so changing it forces a restart. */
data class CalleeConfig(
    val menuYaml: String?,
    val answerMode: String = "ACCEPT",
    val settleTime: String = "0.2",
    /** Appended to `SIP1_OPTIONS`, e.g. `--reject-sip-code 486`. */
    val sipOptions: String = "",
    /** Appended to `GLOBAL_OPTIONS`, e.g. `--codecs PCMA`. */
    val globalOptions: String = "",
    /** JVM options for the callee process, e.g. `-Dhasip.menuLessIdleTimeoutSeconds=1` (passed as `JAVA_TOOL_OPTIONS`). */
    val jvmOptions: String = "",
)

/**
 * The shared two-instance stack: a caller, a callee, and the webhook receiver both
 * report to.
 *
 * Started once per Gradle test JVM (starting a PJSIP endpoint costs ~1-2 s) and torn
 * down by a shutdown hook. The caller never changes -- it only ever places calls, and
 * an outgoing call's menu comes from the `dial` command. The callee's answer mode,
 * settle time and incoming-call menu are read once in `main()`, so [callee] restarts
 * it whenever a scenario asks for a different configuration and reuses it otherwise.
 */
object DirectIpStack {
    private val fixturesDir: File = Files.createTempDirectory("hasip-it-fixtures-").toFile()

    /** Short (~1 s) audio prompt. Most menus use `audio_file` so no TTS/Home Assistant is needed. */
    val helloWav: File = fixturesDir.resolve("hello.wav")

    /**
     * Single-frequency prompts for [AudioFidelityTest], one per source sample rate.
     *
     * Generated rather than committed so the sample rate stays a parameter -- the whole
     * question being asked is what happens to a file whose rate differs from the
     * conference bridge's (16 kHz) and from the negotiated codec's.
     *
     * 1 kHz sits well below PCMA's 4 kHz Nyquist limit, so a correct path has to deliver
     * it intact no matter which of the two rates it started at.
     */
    const val TONE_HZ: Double = 1000.0

    val tone8kWav: File = fixturesDir.resolve("tone-8k.wav")

    val tone16kWav: File = fixturesDir.resolve("tone-16k.wav")

    /**
     * The caller's audio cache, wiped by [reset].
     *
     * Empty by default rather than absent: `cache_audio` is only honoured when a cache
     * directory exists, and a scenario that wants to prove a *miss* needs the feature
     * enabled and the directory empty, not disabled.
     */
    val callerCacheDir: File = fixturesDir.resolve("caller-cache").apply { mkdirs() }

    /** Where `start_recording` writes, wiped by [reset]. */
    val recordingsDir: File = fixturesDir.resolve("recordings").apply { mkdirs() }

    val collector: EventCollector

    val caller: HaSipInstance

    private var calleeInstance: HaSipInstance? = null
    private var calleeConfig: CalleeConfig? = null
    private var calleePort: Int = 0

    const val CALLER = "a"
    const val CALLEE = "b"

    init {
        HaSipInstance.checkPrerequisites()
        javaClass.getResourceAsStream("/hello.wav")!!.use { input ->
            helloWav.outputStream().use { input.copyTo(it) }
        }
        writeSineWav(tone8kWav, sampleRate = 8000, frequencyHz = TONE_HZ, durationMillis = 2000)
        writeSineWav(tone16kWav, sampleRate = 16000, frequencyHz = TONE_HZ, durationMillis = 2000)

        collector = EventCollector()
        collector.register(CALLER)
        collector.register(CALLEE)

        val callerPort = HaSipInstance.freePort()
        caller = HaSipInstance(CALLER, callerPort, sipEnv(CALLER, callerPort, answerMode = "LISTEN"))
        caller.awaitReady()

        Runtime.getRuntime().addShutdownHook(
            Thread {
                calleeInstance?.close()
                caller.close()
                collector.close()
                blackhole.close()
                fixturesDir.deleteRecursively()
            },
        )
    }

    /** The direct-IP URI the caller dials -- no registrar, no proxy, just host:port. */
    val calleeUri: String get() = "sip:callee@127.0.0.1:$calleePort"

    /**
     * A bound UDP socket that is never read from, for calls that must ring forever.
     *
     * Dialling a closed port instead would get an ICMP port-unreachable and fail the
     * transaction outright, well before any ring timeout could fire. Here the datagrams
     * just sit in the receive buffer, so the INVITE goes unanswered exactly as it would
     * against an unreachable peer. `transport=udp` is required because pjsip otherwise
     * prefers TCP for a bare host:port URI, and a TCP connect would be refused.
     */
    private val blackhole = java.net.DatagramSocket(0, java.net.InetAddress.getByName("127.0.0.1"))

    val blackholeUri: String get() = "sip:nobody@127.0.0.1:${blackhole.localPort};transport=udp"

    /** Returns the callee configured as requested, restarting it only when the configuration changed. */
    fun callee(config: CalleeConfig): HaSipInstance {
        val running = calleeInstance
        if (running != null && calleeConfig == config && running.isAlive) return running

        // Clear the caller down *before* the old callee dies. A BYE to a process that is
        // already gone goes unanswered, and pjsip then sits on the call for its full 32 s
        // transaction timeout -- long enough to wedge the scenarios that follow.
        if (running != null && caller.isAlive) {
            caller.hangupAllRegisteredCalls()
            caller.awaitNoActiveCalls()
        }
        running?.close()
        calleePort = HaSipInstance.freePort()

        val menuFile =
            config.menuYaml?.let {
                fixturesDir.resolve("callee-menu-${System.nanoTime()}.yaml").apply { writeText(it) }
            }
        val instance =
            HaSipInstance(
                CALLEE,
                calleePort,
                sipEnv(
                    CALLEE,
                    calleePort,
                    answerMode = config.answerMode,
                    settleTime = config.settleTime,
                    incomingCallFile = menuFile?.absolutePath,
                    extraSipOptions = config.sipOptions,
                    extraGlobalOptions = config.globalOptions,
                    jvmOptions = config.jvmOptions,
                ),
            )
        instance.awaitReady()
        calleeInstance = instance
        calleeConfig = config
        return instance
    }

    /**
     * Per-scenario reset: tear down anything still up, then drop the event history.
     *
     * Hangs up by registered id rather than by the URI a scenario dialled. The callee is
     * restarted on a fresh port whenever a scenario needs a different configuration, so a
     * leftover call on the caller can name a port nothing is listening on any more --
     * un-hangup-uppable by URI, and enough to wedge every scenario that follows.
     */
    fun reset() {
        if (caller.isAlive) caller.hangupAllRegisteredCalls()
        calleeInstance?.takeIf { it.isAlive }?.hangupAllRegisteredCalls()
        caller.awaitNoActiveCalls()
        calleeInstance?.takeIf { it.isAlive }?.awaitNoActiveCalls()
        collector.awaitQuiet()
        collector.clear()
        collector.ttsAudio = null
        collector.stallTts(0)
        callerCacheDir.listFiles()?.forEach { it.delete() }
        recordingsDir.listFiles()?.forEach { it.delete() }
    }

    /**
     * An extra instance the caller owns and disposes of, for scenarios about the process
     * itself rather than about a call. Not registered with the collector or with [reset].
     *
     * [envOverrides] wins over the standard environment, for the scenarios that are about
     * a startup-time setting -- `GLOBAL_OPTIONS` and `LOG_LEVEL` are only read in `main()`,
     * so there is no way to reach them on an instance that is already up.
     */
    fun spawnDisposable(
        name: String,
        envOverrides: Map<String, String> = emptyMap(),
    ): HaSipInstance {
        val port = HaSipInstance.freePort()
        return HaSipInstance(name, port, sipEnv(name, port, answerMode = "LISTEN") + envOverrides)
            .also { it.awaitReady() }
    }

    private fun sipEnv(
        instance: String,
        port: Int,
        answerMode: String,
        settleTime: String = "0.2",
        incomingCallFile: String? = null,
        extraSipOptions: String = "",
        extraGlobalOptions: String = "",
        jvmOptions: String = "",
    ): Map<String, String> =
        buildMap {
            put("PORT", port.toString())
            // Read by the JVM itself at startup, so test-only system properties reach the
            // instance without a launcher change.
            if (jvmOptions.isNotBlank()) put("JAVA_TOOL_OPTIONS", jvmOptions)
            if (instance == CALLER) put("CACHE_DIR", callerCacheDir.absolutePath)
            put(
                "GLOBAL_OPTIONS",
                "--rtp-port ${if (instance == CALLER) 14000 else 24000} $extraGlobalOptions".trim(),
            )
            // Deliberately independent of `hasip.verbose`: PJSIP's level-4 trace is
            // voluminous enough to change the timing of what it is tracing, so streaming
            // the logs (-Pverbose) must not silently turn it on. Ask for it with -PsipLog.
            put("LOG_LEVEL", if (System.getProperty("hasip.sipLog") == "true") "4" else "2")

            put("SIP1_ENABLED", "True")
            put("SIP1_ID_URI", "sip:$instance@127.0.0.1:$port")
            // Registration-less, direct-IP operation: an empty registrar means pjsua
            // never sends REGISTER, and every call is addressed by host:port instead.
            put("SIP1_REGISTRAR_URI", "")
            put("SIP1_REALM", "*")
            put("SIP1_USER_NAME", instance)
            put("SIP1_PASSWORD", "")
            put("SIP1_ANSWER_MODE", answerMode)
            put("SIP1_SETTLE_TIME", settleTime)
            // ICE buys nothing between two loopback endpoints and its connectivity
            // checks would add latency to exactly the measurements being taken.
            put("SIP1_OPTIONS", "--ice false $extraSipOptions".trim())
            incomingCallFile?.let { put("SIP1_INCOMING_CALL_FILE", it) }

            // The only Home Assistant surface these tests use: the webhook sink.
            put("HA_BASE_URL", collector.baseUrl)
            put("HA_WEBHOOK_ID", instance)
            put("HA_TOKEN", "integration-test")
        }
}

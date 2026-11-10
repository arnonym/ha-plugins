package io.github.arnonym.integrationtest

import java.io.Closeable
import java.io.File
import java.net.ServerSocket
import java.nio.file.Files
import java.time.Duration
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/**
 * One ha-sip process under test.
 *
 * Runs the real shadow jar against the natively built PJSIP bindings, driven over
 * stdin (the same JSON-per-line command channel `Main.kt` reads) and observed over
 * the webhook channel via [EventCollector]. Nothing here reaches into ha-sip's
 * internals -- the instance is a black box behind its real external interfaces.
 */
class HaSipInstance(
    val name: String,
    val sipPort: Int,
    env: Map<String, String>,
) : Closeable {
    private val logLines = CopyOnWriteArrayList<String>()
    private val monitor = Object()

    /**
     * A private, empty working directory. Not cosmetic: `AppConfig.fromEnv(dotEnvLookup())`
     * reads a `.env` file relative to the process CWD, so without this the developer's
     * real `.env` at the repo root would silently override the test's env vars.
     */
    private val workDir: File = Files.createTempDirectory("hasip-it-$name-").toFile()

    private val process: Process =
        ProcessBuilder("java", "-Djava.library.path=$NATIVE_DIR/jni", "-jar", JAR)
            .directory(workDir)
            .redirectErrorStream(true)
            .also { builder ->
                builder.environment().apply {
                    // Start from a clean slate so nothing the developer exported leaks in.
                    keys.retainAll(setOf("PATH", "HOME", "LANG", "TMPDIR"))
                    put("LD_LIBRARY_PATH", "$NATIVE_DIR/runtime")
                    putAll(env)
                }
            }
            .start()

    init {
        thread(isDaemon = true, name = "hasip-$name-stdout") {
            process.inputStream.bufferedReader().forEachLine { line ->
                logLines.add(line)
                if (VERBOSE) println("  [$name] $line")
                synchronized(monitor) { monitor.notifyAll() }
            }
        }
    }

    val isAlive: Boolean get() = process.isAlive

    /** Sends one JSON command line to the instance's stdin. */
    fun send(command: String) {
        check(process.isAlive) { "[$name] process died; last log lines:\n${tail(30)}" }
        if (VERBOSE) println("  [$name] >> $command")
        process.outputStream.write((command + "\n").toByteArray())
        process.outputStream.flush()
    }

    /** Index into the log, for [awaitLog] calls that must ignore everything logged so far. */
    fun logMark(): Int = logLines.size

    /** Everything logged since [from], for assertions that need the lines and not just a match. */
    fun logLinesFrom(from: Int): List<String> = logLines.drop(from)

    /** Blocks until a log line matching [regex] appears at or after [from]. */
    fun awaitLog(
        regex: Regex,
        timeout: Duration = Duration.ofSeconds(30),
        from: Int = 0,
    ): String {
        val deadline = System.nanoTime() + timeout.toNanos()
        while (true) {
            logLines.drop(from).firstOrNull { regex.containsMatchIn(it) }?.let { return it }
            check(process.isAlive) { "[$name] process exited (code ${process.exitValue()}) while waiting for /$regex/:\n${tail(40)}" }
            val remainingMillis = (deadline - System.nanoTime()) / 1_000_000
            if (remainingMillis <= 0) {
                throw AssertionError("[$name] timed out after ${timeout.toMillis()}ms waiting for /$regex/:\n${tail(40)}")
            }
            synchronized(monitor) { monitor.wait(remainingMillis.coerceAtMost(25)) }
        }
    }

    /**
     * Waits until the SIP stack is up *and* the stdin reader is consuming commands.
     *
     * The startup marker alone only proves `main()` ran to the end; round-tripping a
     * `state` command additionally proves the command channel works, which is what
     * every scenario depends on.
     */
    fun awaitReady() {
        awaitLog(Regex("ha-sip started, listening on port $sipPort"))
        awaitNoActiveCalls()
    }

    /**
     * The callback ids currently in the call registry, as reported by `state`.
     *
     * Parsed out of the log because `state` is the only view of the registry a black-box
     * test has. Each entry is printed as an indented, comma-separated id list, of which
     * the first is the canonical callback id that commands accept.
     */
    fun registeredCallIds(): List<String> {
        val mark = logMark()
        send("""{"command": "state"}""")
        // `state` prints one header plus a line per call, and waiting for the header alone
        // would race the entries still sitting in the pipe. An unknown command right
        // behind it is rejected on the same (single) command thread, so its complaint is
        // guaranteed to be logged after the whole list.
        send("""{"command": "$LIST_SENTINEL"}""")
        awaitLog(Regex("Unknown command: $LIST_SENTINEL"), Duration.ofSeconds(10), from = mark)

        val window = logLines.drop(mark).takeWhile { !it.contains("Unknown command: $LIST_SENTINEL") }
        val headerIndex = window.indexOfLast { it.contains("Currently registered calls:") }
        if (headerIndex < 0) return emptyList()
        // Registry entries are indented by four spaces; every other log line has a single
        // space after the account tag, which is what marks the end of the list.
        val entry = Regex("""\[[^]]*]\s{2,}(\S.*)$""")
        return window.drop(headerIndex + 1)
            .map { entry.find(it)?.groupValues?.get(1) }
            .takeWhile { it != null }
            .mapNotNull { it!!.split(", ").firstOrNull()?.trim()?.takeIf(String::isNotEmpty) }
    }

    /**
     * Hangs up everything this instance still has registered.
     *
     * By id rather than by a URI the test knows, because a call can outlive the peer that
     * it points at -- the callee is restarted on a fresh port whenever a scenario needs a
     * different configuration, and the caller's leftover call still names the *old* port.
     * Nothing would ever hang that call up, and it would block every later scenario.
     */
    fun hangupAllRegisteredCalls() {
        registeredCallIds().forEach { id ->
            runCatching { send("""{"command": "hangup", "number": ${id.jsonString()}}""") }
        }
    }

    /**
     * Polls the `state` command until the call registry is empty.
     *
     * Scenarios must not inherit a call from the previous one, and observing
     * `call_disconnected` is not sufficient: that webhook fires in `onCallState`
     * a few statements *before* `forgetCall` removes the call from the registry,
     * and `dial` silently refuses a number that is still registered.
     */
    fun awaitNoActiveCalls(timeout: Duration = Duration.ofSeconds(15)) {
        val deadline = System.nanoTime() + timeout.toNanos()
        while (true) {
            val mark = logMark()
            send("""{"command": "state"}""")
            val line = awaitLog(Regex("No active calls\\.|Currently registered calls:"), Duration.ofSeconds(5), from = mark)
            if (line.contains("No active calls.")) return
            check(System.nanoTime() < deadline) { "[$name] still has active calls after ${timeout.toMillis()}ms:\n${tail(15)}" }
            Thread.sleep(100)
        }
    }

    /** Waits for the process to exit and returns its status code. */
    fun awaitExit(timeout: Duration = Duration.ofSeconds(15)): Int {
        check(process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS)) {
            "[$name] did not exit within ${timeout.toMillis()}ms:\n${tail(30)}"
        }
        return process.exitValue()
    }

    fun tail(lines: Int): String = logLines.takeLast(lines).joinToString("\n") { "    [$name] $it" }

    fun logContains(regex: Regex): Boolean = logLines.any { regex.containsMatchIn(it) }

    override fun close() {
        if (process.isAlive) {
            runCatching { send("""{"command": "quit"}""") }
            if (!process.waitFor(5, TimeUnit.SECONDS)) process.destroyForcibly()
        }
        workDir.deleteRecursively()
    }

    companion object {
        private val VERBOSE = System.getProperty("hasip.verbose") == "true"

        /** Deliberately not a real command -- see [registeredCallIds]. */
        private const val LIST_SENTINEL = "__end_of_state__"

        val JAR: String =
            requireNotNull(System.getProperty("hasip.jar")) { "hasip.jar system property not set -- run via Gradle" }

        val NATIVE_DIR: String =
            requireNotNull(System.getProperty("hasip.nativeDir")) { "hasip.nativeDir system property not set -- run via Gradle" }

        /** Fails early and legibly rather than letting a scenario time out mysteriously. */
        fun checkPrerequisites() {
            check(File(JAR).isFile) { "Shadow jar not found at $JAR -- run `./gradlew :app:shadowJar`" }
            check(File("$NATIVE_DIR/jni/libpjsua2.so").isFile) {
                "PJSIP JNI bindings not found at $NATIVE_DIR/jni/libpjsua2.so -- run `mise run extract-bindings`"
            }
            check(
                runCatching { ProcessBuilder("ffmpeg", "-version").redirectErrorStream(true).start().waitFor() == 0 }
                    .getOrDefault(false),
            ) { "ffmpeg not found on PATH -- `play_audio_file` shells out to it even for .wav input" }
        }

        /**
         * Grabs a free TCP port and hands it back. Racy in principle (the port is
         * released before the instance binds it, and ha-sip binds UDP anyway), but the
         * ephemeral range makes a collision within one test run vanishingly unlikely.
         */
        fun freePort(): Int = ServerSocket(0).use { it.localPort }
    }
}

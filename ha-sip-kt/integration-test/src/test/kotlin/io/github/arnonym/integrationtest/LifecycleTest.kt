package io.github.arnonym.integrationtest

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test
import java.time.Duration

/**
 * The process itself: coming up, and going down again on request.
 *
 * Shutdown is worth a scenario of its own because failing it is invisible everywhere
 * else. `libDestroy()` tears down PJSIP's threads and native state, and getting it wrong
 * -- calling it from the wrong thread, or while a worker is still inside pjsua2 -- ends
 * in a native crash or a hang *after* all the useful work is done. The rest of the suite
 * force-kills its instances on the way out, so it would never notice either.
 */
class LifecycleTest {
    @Test
    @DisplayName("the quit command shuts the process down cleanly")
    fun quitExitsCleanly() {
        val instance = DirectIpStack.spawnDisposable("quit")
        try {
            val mark = instance.logMark()
            instance.send("""{"command": "quit"}""")

            instance.awaitLog(Regex("Shutting down\\."), from = mark)
            // Zero, and without help: a SIGSEGV in libDestroy would surface as 139, a hang
            // as a timeout in awaitExit, and either would otherwise be hidden by the
            // destroyForcibly() in HaSipInstance.close().
            instance.awaitExit(Duration.ofSeconds(15)) shouldBe 0
        } finally {
            instance.close()
        }
    }

    @Test
    @DisplayName("an unparsable command line is reported and does not kill the process")
    fun malformedCommandIsSurvivable() {
        val instance = DirectIpStack.spawnDisposable("malformed")
        try {
            val mark = instance.logMark()
            instance.send("this is not json")
            instance.awaitLog(Regex("Could not deserialize JSON"), from = mark)

            // The command channel is fed by Home Assistant automations, so one bad line
            // must not take the SIP stack with it.
            instance.send("""{"command": "no_such_command"}""")
            instance.awaitLog(Regex("Unknown command: no_such_command"), from = mark)
            instance.awaitNoActiveCalls()
            instance.isAlive shouldBe true
        } finally {
            instance.close()
        }
    }
}

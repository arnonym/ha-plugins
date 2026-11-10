package io.github.arnonym.config

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test

class AppConfigTest {
    @Test
    fun `reads all expected env var names with empty defaults`() {
        val config = AppConfig.fromEnv { null }
        config.port shouldBe ""
        config.sensor.enabled shouldBe "false"
        config.sensor.entityPrefix shouldBe "ha_sip"
        config.sipAccounts.keys shouldBe setOf(1, 2, 3)
    }

    @Test
    fun `maps SIPn_ env vars to the right account index`() {
        val env =
            mapOf(
                "SIP2_ID_URI" to "sip:someone@example.com",
                "SIP2_ENABLED" to "true",
            )
        val config = AppConfig.fromEnv { env[it] }
        config.sipAccounts.getValue(2).idUri shouldBe "sip:someone@example.com"
        config.sipAccounts.getValue(2).enabled shouldBe "true"
        config.sipAccounts.getValue(1).idUri shouldBe ""
    }
}

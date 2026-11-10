package io.github.arnonym.config

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File

class AppConfigTest {
    @Test
    fun `reads all expected env var names with empty defaults`() {
        val config = AppConfig.fromEnv(EnvSource.of(emptyMap()))
        config.port shouldBe ""
        config.sensor.enabled shouldBe "false"
        config.sensor.entityPrefix shouldBe "ha_sip"
        config.sipAccounts shouldBe emptyMap()
    }

    @Test
    fun `maps SIPn_ env vars to the right account index`() {
        val config =
            AppConfig.fromEnv(
                EnvSource.of(
                    mapOf(
                        "SIP2_ID_URI" to "sip:someone@example.com",
                        "SIP2_ENABLED" to "true",
                    ),
                ),
            )
        config.sipAccounts.keys shouldBe setOf(2)
        config.sipAccounts.getValue(2).idUri shouldBe "sip:someone@example.com"
        config.sipAccounts.getValue(2).enabled shouldBe "true"
        // Variables the account doesn't set fall back to empty, as before.
        config.sipAccounts.getValue(2).password shouldBe ""
    }

    @Test
    fun `any number of accounts is picked up, in ascending order`() {
        val variables = (1..12).associate { "SIP${it}_ENABLED" to "true" } + ("SIP0_ENABLED" to "false")
        val config = AppConfig.fromEnv(EnvSource.of(variables))
        config.sipAccounts.keys.toList() shouldBe (0..12).toList()
    }

    @Test
    fun `account numbers come only from SIPn_ prefixes`() {
        sipAccountIndices(listOf("SIP3_ENABLED", "SIP10_OPTIONS", "SIP3_ID_URI", "SIPX_ENABLED", "MY_SIP1_ENABLED", "SIP_GLOBAL")) shouldBe
            listOf(3, 10)
    }

    @Test
    fun `accounts can be declared in a dot env file`(
        @TempDir dir: File,
    ) {
        val envFile = File(dir, ".env")
        envFile.writeText("SIP4_ENABLED=\"true\"\nSIP4_ID_URI=\"sip:four@example.com\"\n")
        val config = AppConfig.fromEnv(loadDotEnv(envFile.path))
        config.sipAccounts.getValue(4).idUri shouldBe "sip:four@example.com"
    }
}

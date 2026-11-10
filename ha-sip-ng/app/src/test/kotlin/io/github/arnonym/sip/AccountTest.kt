package io.github.arnonym.sip

import io.kotest.matchers.shouldBe
import io.kotest.matchers.string.shouldContain
import io.kotest.matchers.string.shouldNotContain
import org.junit.jupiter.api.Test
import java.io.ByteArrayOutputStream
import java.io.PrintStream

/** Port of tests/test_account.py. */
class AccountTest {
    @Test
    fun is_number_in_list() {
        Account.isNumberInList(null, listOf("12345")) shouldBe false
        Account.isNumberInList(null, emptyList()) shouldBe false
        Account.isNumberInList("12345", emptyList()) shouldBe false
        Account.isNumberInList("12345", listOf("12345")) shouldBe true
        Account.isNumberInList("1234", listOf("12345")) shouldBe false
        Account.isNumberInList("123456", listOf("1234{*}")) shouldBe true
        Account.isNumberInList("123456", listOf("1234{?}")) shouldBe false
        Account.isNumberInList("12345", listOf("1234{?}")) shouldBe true
        Account.isNumberInList("12345", listOf("1{*}5")) shouldBe true
        Account.isNumberInList("12345", listOf("12{?}45")) shouldBe true
        Account.isNumberInList("12345", listOf("{*}45")) shouldBe true
        Account.isNumberInList("12345", listOf("{?}345")) shouldBe false
        Account.isNumberInList("12345", listOf("{?}2345")) shouldBe true
        Account.isNumberInList("**620", listOf("**620")) shouldBe true
        Account.isNumberInList("**620", listOf("**{*}")) shouldBe true
    }

    @Test
    fun parse_sip_headers() {
        val msg =
            "INVITE sip:1@x SIP/2.0\r\n" +
                "X-Test: first\r\n" +
                "x-test: second\r\n" + // case-insensitive match, last one wins
                "Other: value\r\n" +
                "\r\n" + // blank line ends headers
                "X-Test: body-value" // must be ignored -- it's past the blank line
        Account.parseSipHeaders(msg, listOf("X-Test", "Missing")) shouldBe
            mapOf("X-Test" to "second", "Missing" to null)
    }

    @Test
    fun log_all_sip_headers() {
        val msg = "INVITE sip:1@x SIP/2.0\r\nX-Test: 123\r\nNoColon\r\n\r\nX-Test: body-value"
        val originalOut = System.out
        val captured = ByteArrayOutputStream()
        System.setOut(PrintStream(captured))
        try {
            Account.logAllSipHeaders(1, msg)
        } finally {
            System.setOut(originalOut)
        }
        val output = captured.toString()
        output shouldContain "Available SIP headers:"
        output shouldContain "X-Test: 123"
        output shouldNotContain "NoColon"
        output shouldNotContain "body-value"
    }
}

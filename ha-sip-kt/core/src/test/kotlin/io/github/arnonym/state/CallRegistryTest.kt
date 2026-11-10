package io.github.arnonym.state

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test

class CallRegistryTest {
    private data class FakeCall(val name: String)

    @Test
    fun `register and resolve by callback id`() {
        val registry = CallRegistry<FakeCall>()
        val call = FakeCall("call-1")
        registry.registerCall("cb-1", call, listOf("alt-1", "alt-2"))

        registry.isActive("cb-1") shouldBe true
        registry.isActive("alt-1") shouldBe true
        registry.isActive("alt-2") shouldBe true
        registry.isActive("unknown") shouldBe false
        registry.getCall("alt-2") shouldBe call
    }

    @Test
    fun `forget removes call and alt ids`() {
        val registry = CallRegistry<FakeCall>()
        registry.registerCall("cb-1", FakeCall("call-1"), listOf("alt-1"))
        registry.forgetCall("cb-1")

        registry.isActive("cb-1") shouldBe false
        registry.isActive("alt-1") shouldBe false
        registry.getCall("cb-1") shouldBe null
    }

    @Test
    fun `getCall returns null for unknown identifier`() {
        val registry = CallRegistry<FakeCall>()
        registry.getCall("missing") shouldBe null
    }

    @Test
    fun `currentCalls reflects registered calls`() {
        val registry = CallRegistry<FakeCall>()
        val a = FakeCall("a")
        val b = FakeCall("b")
        registry.registerCall("a", a, emptyList())
        registry.registerCall("b", b, emptyList())
        registry.currentCalls().toSet() shouldBe setOf(a, b)
    }
}

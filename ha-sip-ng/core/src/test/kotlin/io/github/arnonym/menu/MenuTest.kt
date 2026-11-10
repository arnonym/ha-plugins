package io.github.arnonym.menu

import io.github.arnonym.config.Constants
import io.kotest.matchers.shouldBe
import io.kotest.matchers.types.shouldBeSameInstanceAs
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import org.junit.jupiter.api.Nested
import org.junit.jupiter.api.Test

class MenuTest {
    private fun jsonMenu(build: JsonObjectBuilderScope.() -> Unit = {}): JsonObject {
        val scope = JsonObjectBuilderScope()
        scope.build()
        return buildJsonObject {
            scope.entries.forEach { (k, v) -> put(k, v) }
        }
    }

    class JsonObjectBuilderScope {
        val entries = mutableMapOf<String, kotlinx.serialization.json.JsonElement>()

        fun set(
            key: String,
            value: String?,
        ) {
            entries[key] = value?.let { kotlinx.serialization.json.JsonPrimitive(it) } ?: kotlinx.serialization.json.JsonNull
        }

        fun set(
            key: String,
            value: Boolean?,
        ) {
            entries[key] = value?.let { kotlinx.serialization.json.JsonPrimitive(it) } ?: kotlinx.serialization.json.JsonNull
        }

        fun set(
            key: String,
            value: Number?,
        ) {
            entries[key] = value?.let { kotlinx.serialization.json.JsonPrimitive(it) } ?: kotlinx.serialization.json.JsonNull
        }

        fun setChoices(build: JsonObjectBuilderScope.() -> Unit) {
            val scope = JsonObjectBuilderScope()
            scope.build()
            entries["choices"] = buildJsonObject { scope.entries.forEach { (k, v) -> put(k, v) } }
        }

        fun choice(
            key: Any,
            menu: JsonObject,
        ) {
            entries[key.toString()] = menu
        }
    }

    @Nested
    inner class NormalizeMenuNone {
        @Test
        fun `none input returns none and empty map`() {
            val (menu, menuMap) = normalizeMenu(null, "en", 0)
            menu shouldBe null
            menuMap shouldBe emptyMap()
        }
    }

    @Nested
    inner class NormalizeMenuDefaults {
        @Test
        fun `minimal menu gets defaults`() {
            val (menu, _) = normalizeMenu(jsonMenu(), "de", 1)
            requireNotNull(menu)
            menu.id shouldBe null
            menu.message shouldBe null
            menu.handleAsTemplate shouldBe false
            menu.audioFile shouldBe null
            menu.language shouldBe "de"
            menu.action shouldBe null
            menu.choicesArePin shouldBe false
            menu.postAction shouldBe PostAction.Noop
            menu.timeout shouldBe Constants.DEFAULT_RING_TIMEOUT
            menu.cacheAudio shouldBe false
            menu.waitForAudioToFinish shouldBe false
            menu.parentMenu shouldBe null
        }

        @Test
        fun `explicit values are preserved`() {
            val (menu, _) =
                normalizeMenu(
                    jsonMenu {
                        set("id", "  main  ")
                        set("message", "Hello")
                        set("handle_as_template", true)
                        set("audio_file", "/tmp/test.wav")
                        set("language", "fr")
                        set("choices_are_pin", true)
                        set("timeout", 30)
                        set("cache_audio", true)
                        set("wait_for_audio_to_finish", true)
                    },
                    "de",
                    1,
                )
            requireNotNull(menu)
            menu.id shouldBe "main"
            menu.message shouldBe "Hello"
            menu.handleAsTemplate shouldBe true
            menu.audioFile shouldBe "/tmp/test.wav"
            menu.language shouldBe "fr"
            menu.choicesArePin shouldBe true
            menu.timeout shouldBe 30.0
            menu.cacheAudio shouldBe true
            menu.waitForAudioToFinish shouldBe true
        }

        @Test
        fun `language falls back to default`() {
            val (menu, _) = normalizeMenu(jsonMenu { set("language", null as String?) }, "sv", 1)
            requireNotNull(menu)
            menu.language shouldBe "sv"
        }

        @Test
        fun `id whitespace stripped`() {
            val (menu, _) = normalizeMenu(jsonMenu { set("id", "  hello  ") }, "en", 0)
            requireNotNull(menu)
            menu.id shouldBe "hello"
        }
    }

    @Nested
    inner class PostActionParsing {
        @Test
        fun noop() {
            val (menu, _) = normalizeMenu(jsonMenu { set("post_action", "noop") }, "en", 0)
            requireNotNull(menu).postAction shouldBe PostAction.Noop
        }

        @Test
        fun `none becomes noop`() {
            val (menu, _) = normalizeMenu(jsonMenu(), "en", 0)
            requireNotNull(menu).postAction shouldBe PostAction.Noop
        }

        @Test
        fun hangup() {
            val (menu, _) = normalizeMenu(jsonMenu { set("post_action", "hangup") }, "en", 0)
            requireNotNull(menu).postAction shouldBe PostAction.Hangup
        }

        @Test
        fun `repeat message`() {
            val (menu, _) = normalizeMenu(jsonMenu { set("post_action", "repeat_message") }, "en", 0)
            requireNotNull(menu).postAction shouldBe PostAction.RepeatMessage
        }

        @Test
        fun `return default level`() {
            val (menu, _) = normalizeMenu(jsonMenu { set("post_action", "return") }, "en", 0)
            requireNotNull(menu).postAction shouldBe PostAction.Return(1)
        }

        @Test
        fun `return with level`() {
            val (menu, _) = normalizeMenu(jsonMenu { set("post_action", "return 3") }, "en", 0)
            requireNotNull(menu).postAction shouldBe PostAction.Return(3)
        }

        @Test
        fun jump() {
            val (menu, _) = normalizeMenu(jsonMenu { set("post_action", "jump submenu") }, "en", 0)
            requireNotNull(menu).postAction shouldBe PostAction.Jump("submenu")
        }

        @Test
        fun `unknown post action becomes noop`() {
            val (menu, _) = normalizeMenu(jsonMenu { set("post_action", "explode") }, "en", 0)
            requireNotNull(menu).postAction shouldBe PostAction.Noop
        }
    }

    @Nested
    inner class DefaultAndTimeoutChoice {
        @Test
        fun `auto generated default choice`() {
            val (menu, _) = normalizeMenu(jsonMenu(), "en", 0)
            requireNotNull(menu)
            val default = requireNotNull(menu.defaultChoice)
            default.message shouldBe "Unknown option"
            default.postAction shouldBe PostAction.Return(1)
            default.parentMenu shouldBeSameInstanceAs menu
        }

        @Test
        fun `auto generated timeout choice`() {
            val (menu, _) = normalizeMenu(jsonMenu(), "en", 0)
            requireNotNull(menu)
            val timeout = requireNotNull(menu.timeoutChoice)
            timeout.message shouldBe null
            timeout.postAction shouldBe PostAction.Hangup
            timeout.parentMenu shouldBeSameInstanceAs menu
        }

        @Test
        fun `custom default choice`() {
            val (menu, _) =
                normalizeMenu(
                    jsonMenu {
                        setChoices {
                            choice("1", jsonMenu { set("message", "Option 1") })
                            choice("default", jsonMenu { set("message", "Try again") })
                        }
                    },
                    "en",
                    0,
                )
            requireNotNull(menu)
            val default = requireNotNull(menu.defaultChoice)
            default.message shouldBe "Try again"
            menu.choices.keys shouldBe setOf("1")
        }

        @Test
        fun `custom timeout choice`() {
            val (menu, _) =
                normalizeMenu(
                    jsonMenu {
                        setChoices {
                            choice("1", jsonMenu { set("message", "Option 1") })
                            choice(
                                "timeout",
                                jsonMenu {
                                    set("message", "Timed out")
                                    set("post_action", "hangup")
                                },
                            )
                        }
                    },
                    "en",
                    0,
                )
            requireNotNull(menu)
            val timeout = requireNotNull(menu.timeoutChoice)
            timeout.message shouldBe "Timed out"
            menu.choices.keys shouldBe setOf("1")
        }
    }

    @Nested
    inner class Choices {
        @Test
        fun `choices normalized`() {
            val (menu, _) =
                normalizeMenu(
                    jsonMenu {
                        setChoices {
                            choice(1, jsonMenu { set("message", "First") })
                            choice(2, jsonMenu { set("message", "Second") })
                        }
                    },
                    "en",
                    0,
                )
            requireNotNull(menu)
            menu.choices.keys shouldBe setOf("1", "2")
            menu.choices.getValue("1").message shouldBe "First"
            menu.choices.getValue("2").message shouldBe "Second"
        }

        @Test
        fun `choice keys lowercased`() {
            val (menu, _) =
                normalizeMenu(
                    jsonMenu { setChoices { choice("A", jsonMenu { set("message", "Alpha") }) } },
                    "en",
                    0,
                )
            requireNotNull(menu)
            menu.choices.keys shouldBe setOf("a")
        }

        @Test
        fun `nested choices parent set`() {
            val (menu, _) =
                normalizeMenu(
                    jsonMenu { setChoices { choice("1", jsonMenu { set("message", "Sub") }) } },
                    "en",
                    0,
                )
            requireNotNull(menu)
            val sub = menu.choices.getValue("1")
            sub.parentMenu shouldBeSameInstanceAs menu
        }

        @Test
        fun `no choices gives empty map`() {
            val (menu, _) = normalizeMenu(jsonMenu(), "en", 0)
            requireNotNull(menu).choices shouldBe emptyMap()
        }
    }

    @Nested
    inner class MenuMap {
        @Test
        fun `menu map from ids`() {
            val (_, menuMap) =
                normalizeMenu(
                    jsonMenu {
                        set("id", "root")
                        setChoices {
                            choice(
                                "1",
                                jsonMenu {
                                    set("id", "child1")
                                    set("message", "C1")
                                },
                            )
                            choice(
                                "2",
                                jsonMenu {
                                    set("id", "child2")
                                    set("message", "C2")
                                },
                            )
                        }
                    },
                    "en",
                    0,
                )
            menuMap.keys shouldBe setOf("root", "child1", "child2")
            menuMap.getValue("child1").message shouldBe "C1"
        }

        @Test
        fun `menu map excludes none ids`() {
            val (_, menuMap) =
                normalizeMenu(
                    jsonMenu { setChoices { choice("1", jsonMenu { set("message", "no id") }) } },
                    "en",
                    0,
                )
            menuMap shouldBe emptyMap()
        }

        @Test
        fun `menu map nested`() {
            val (_, menuMap) =
                normalizeMenu(
                    jsonMenu {
                        set("id", "root")
                        setChoices {
                            choice(
                                "1",
                                jsonMenu {
                                    set("id", "level1")
                                    setChoices { choice("1", jsonMenu { set("id", "level2") }) }
                                },
                            )
                        }
                    },
                    "en",
                    0,
                )
            menuMap.keys shouldBe setOf("root", "level1", "level2")
        }
    }

    @Nested
    inner class DefaultTimeoutChoiceSuppression {
        @Test
        fun `default choice has no own default or timeout`() {
            val (menu, _) =
                normalizeMenu(
                    jsonMenu {
                        setChoices {
                            choice("1", jsonMenu { set("message", "Option 1") })
                            choice("default", jsonMenu { set("message", "Error") })
                        }
                    },
                    "en",
                    0,
                )
            requireNotNull(menu)
            val default = requireNotNull(menu.defaultChoice)
            default.defaultChoice shouldBe null
            default.timeoutChoice shouldBe null
        }

        @Test
        fun `timeout choice has no own default or timeout`() {
            val (menu, _) =
                normalizeMenu(
                    jsonMenu {
                        setChoices {
                            choice("1", jsonMenu { set("message", "Option 1") })
                            choice("timeout", jsonMenu { set("message", "Bye") })
                        }
                    },
                    "en",
                    0,
                )
            requireNotNull(menu)
            val timeout = requireNotNull(menu.timeoutChoice)
            timeout.defaultChoice shouldBe null
            timeout.timeoutChoice shouldBe null
        }
    }

    @Nested
    inner class PrettyPrint {
        @Test
        fun `none menu does not throw`() {
            prettyPrintMenu(null)
        }

        @Test
        fun `with menu does not throw`() {
            val (menu, _) = normalizeMenu(jsonMenu { set("message", "Hello") }, "en", 0)
            prettyPrintMenu(menu)
        }
    }
}

package io.github.arnonym.menu

import io.github.arnonym.config.Constants
import io.github.arnonym.json.boolValueOrNull
import io.github.arnonym.json.doubleValueOrNull
import io.github.arnonym.json.stringValueOrNull
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

class Menu(
    val id: String?,
    val message: String?,
    val handleAsTemplate: Boolean,
    val audioFile: String?,
    val language: String,
    val action: JsonObject?,
    val choicesArePin: Boolean,
    val postAction: PostAction,
    val timeout: Double,
    val parentMenu: Menu?,
    val cacheAudio: Boolean,
    val waitForAudioToFinish: Boolean,
) {
    var choices: Map<String, Menu> = emptyMap()
        internal set
    var defaultChoice: Menu? = null
        internal set
    var timeoutChoice: Menu? = null
        internal set
}

fun normalizeMenu(
    menu: JsonObject?,
    defaultLanguage: String,
    accountIndex: Int?,
    parentMenu: Menu? = null,
    isDefaultOrTimeoutChoice: Boolean = false,
): Pair<Menu?, Map<String, Menu>> {
    if (menu == null) return null to emptyMap()
    val normalized = normalizeMenuInternal(menu, defaultLanguage, accountIndex, parentMenu, isDefaultOrTimeoutChoice)
    return normalized to createMenuMap(normalized)
}

private fun normalizeMenuInternal(
    menu: JsonObject,
    defaultLanguage: String,
    accountIndex: Int?,
    parentMenu: Menu?,
    isDefaultOrTimeoutChoice: Boolean,
): Menu {
    val rawId = menu["id"]?.stringValueOrNull()
    val id = if (!rawId.isNullOrEmpty()) rawId.trim() else null

    val rawLanguage = menu["language"]?.stringValueOrNull()
    val language = if (!rawLanguage.isNullOrEmpty()) rawLanguage else defaultLanguage

    val timeout = menu["timeout"]?.doubleValueOrNull() ?: Constants.DEFAULT_RING_TIMEOUT

    val normalizedMenu =
        Menu(
            id = id,
            message = menu["message"]?.stringValueOrNull(),
            handleAsTemplate = menu["handle_as_template"].boolValueOrFalse(),
            audioFile = menu["audio_file"]?.stringValueOrNull(),
            language = language,
            action = menu["action"] as? JsonObject,
            choicesArePin = menu["choices_are_pin"].boolValueOrFalse(),
            postAction = PostAction.parse(menu["post_action"]?.stringValueOrNull(), accountIndex),
            timeout = timeout,
            parentMenu = parentMenu,
            cacheAudio = menu["cache_audio"].boolValueOrFalse(),
            waitForAudioToFinish = menu["wait_for_audio_to_finish"].boolValueOrFalse(),
        )

    val rawChoices =
        (menu["choices"] as? JsonObject)?.entries
            ?.associate { (key, value) ->
                val normalizedKey = key.lowercase()
                val subMenu =
                    normalizeMenuInternal(
                        value as JsonObject,
                        defaultLanguage,
                        accountIndex,
                        normalizedMenu,
                        normalizedKey == "default" || normalizedKey == "timeout",
                    )
                normalizedKey to subMenu
            }
            ?.toMutableMap()
            ?: mutableMapOf()

    fun getDefaultOrTimeoutChoice(choice: String): Menu? {
        if (isDefaultOrTimeoutChoice) return null
        val existing = rawChoices.remove(choice)
        if (existing != null) return existing
        return if (choice == "default") getDefaultMenu(normalizedMenu) else getTimeoutMenu(normalizedMenu)
    }

    val defaultChoice = getDefaultOrTimeoutChoice("default")
    val timeoutChoice = getDefaultOrTimeoutChoice("timeout")

    normalizedMenu.choices = rawChoices
    normalizedMenu.defaultChoice = defaultChoice
    normalizedMenu.timeoutChoice = timeoutChoice
    return normalizedMenu
}

/** `x or False` truthiness for a JSON boolean/scalar: only `false`/null/"" count as false. */
private fun JsonElement?.boolValueOrFalse(): Boolean = this?.boolValueOrNull() ?: false

private fun createMenuMap(menu: Menu?): Map<String, Menu> {
    if (menu == null) return emptyMap()
    val map = mutableMapOf<String, Menu>()

    fun addToMap(m: Menu) {
        if (m.id != null) map[m.id] = m
        m.choices.values.forEach(::addToMap)
        m.defaultChoice?.let(::addToMap)
        m.timeoutChoice?.let(::addToMap)
    }
    addToMap(menu)
    return map
}

private fun getDefaultMenu(parentMenu: Menu): Menu =
    Menu(
        id = null,
        message = "Unknown option",
        handleAsTemplate = false,
        audioFile = null,
        language = "en",
        action = null,
        choicesArePin = false,
        postAction = PostAction.Return(1),
        timeout = Constants.DEFAULT_RING_TIMEOUT,
        parentMenu = parentMenu,
        cacheAudio = false,
        waitForAudioToFinish = false,
    )

private fun getTimeoutMenu(parentMenu: Menu): Menu =
    Menu(
        id = null,
        message = null,
        handleAsTemplate = false,
        audioFile = null,
        language = "en",
        action = null,
        choicesArePin = false,
        postAction = PostAction.Hangup,
        timeout = Constants.DEFAULT_RING_TIMEOUT,
        parentMenu = parentMenu,
        cacheAudio = false,
        waitForAudioToFinish = false,
    )

fun prettyPrintMenu(menu: Menu?) {
    if (menu == null) {
        println("No menu defined.")
        return
    }
    dumpMenu(menu, 0).lineSequence().forEach { println("| $it") }
}

private fun dumpMenu(
    menu: Menu,
    depth: Int,
): String {
    val indent = "  ".repeat(depth)
    val sb = StringBuilder()
    sb.appendLine("${indent}id: ${menu.id}")
    sb.appendLine("${indent}message: ${menu.message}")
    sb.appendLine("${indent}language: ${menu.language}")
    sb.appendLine("${indent}post_action: ${menu.postAction}")
    sb.appendLine("${indent}timeout: ${menu.timeout}")
    if (menu.choices.isNotEmpty()) {
        sb.appendLine("${indent}choices:")
        menu.choices.forEach { (key, sub) ->
            sb.appendLine("$indent  $key:")
            sb.append(dumpMenu(sub, depth + 2))
        }
    }
    return sb.toString()
}

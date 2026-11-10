package io.github.arnonym.menu

import io.github.arnonym.config.convertToInt
import io.github.arnonym.log.log

sealed class PostAction(val action: String) {
    data object Noop : PostAction("noop")

    data object Hangup : PostAction("hangup")

    data object RepeatMessage : PostAction("repeat_message")

    data class Return(val level: Int) : PostAction("return")

    data class Jump(val menuId: String) : PostAction("jump")

    companion object {
        /** Direct port of menu.py's `_normalize_menu.parse_post_action`. */
        fun parse(
            raw: String?,
            accountIndex: Int?,
        ): PostAction {
            if (raw.isNullOrEmpty() || raw == "noop") return Noop
            if (raw == "hangup") return Hangup
            if (raw == "repeat_message") return RepeatMessage
            if (raw.startsWith("return")) {
                val params = raw.split(Regex("\\s+")).drop(1)
                val level = convertToInt(params.getOrNull(0), 1)
                return Return(level)
            }
            if (raw.startsWith("jump")) {
                val params = raw.split(Regex("\\s+")).filter { it.isNotEmpty() }.drop(1)
                val jumpTo = params.getOrNull(0)?.trim()
                if (jumpTo.isNullOrEmpty()) {
                    log(accountIndex, "Error: jump action requires a menu id as parameter, will be treated as noop")
                    return Noop
                }
                return Jump(jumpTo)
            }
            log(accountIndex, "Unknown post_action: $raw")
            return Noop
        }
    }
}

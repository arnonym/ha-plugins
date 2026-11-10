package io.github.arnonym.config

enum class AnswerMode {
    LISTEN,
    ACCEPT,
    REJECT,
    ;

    companion object {
        fun getOrElse(
            name: String?,
            default: AnswerMode,
        ): AnswerMode = entries.find { it.name.equals(name, ignoreCase = true) } ?: default
    }
}

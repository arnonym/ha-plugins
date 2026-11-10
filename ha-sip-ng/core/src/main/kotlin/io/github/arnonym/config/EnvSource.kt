package io.github.arnonym.config

import io.github.cdimascio.dotenv.Dotenv
import java.io.File

/**
 * The variables configuration is read from: a lookup by name, plus the set of names that
 * exist. The names are what lets [AppConfig.fromEnv] find however many `SIP<n>_*`
 * accounts are configured, rather than probing a fixed range.
 */
class EnvSource(
    private val lookup: (String) -> String?,
    val names: Set<String>,
) {
    operator fun get(name: String): String? = lookup(name)

    companion object {
        fun of(variables: Map<String, String>) = EnvSource(variables::get, variables.keys)

        fun system() = of(System.getenv())
    }
}

/** The process environment, with the variables of an optional `.env` file merged in. */
fun loadDotEnv(path: String = ".env"): EnvSource {
    val file = File(path)
    val dotenv =
        Dotenv.configure()
            .directory(file.parent ?: ".")
            .filename(file.name)
            .ignoreIfMissing()
            .ignoreIfMalformed()
            .load()
    return EnvSource({ key -> dotenv.get(key) }, dotenv.entries().map { it.key }.toSet())
}

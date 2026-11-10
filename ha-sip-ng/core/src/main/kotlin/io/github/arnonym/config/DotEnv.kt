package io.github.arnonym.config

import io.github.cdimascio.dotenv.Dotenv
import java.io.File

fun dotEnvLookup(path: String = ".env"): (String) -> String? {
    val file = File(path)
    val dotenv =
        Dotenv.configure()
            .directory(file.parent ?: ".")
            .filename(file.name)
            .ignoreIfMissing()
            .ignoreIfMalformed()
            .load()
    return { key -> dotenv.get(key) }
}

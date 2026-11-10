package io.github.arnonym.config

data class CodecPriority(
    val codecId: String,
    val priority: Short,
)

data class CodecPlan(
    val priorities: List<CodecPriority>,
    val unmatched: List<String>,
)

fun planCodecPriorities(
    available: List<String>,
    requested: List<String>,
): CodecPlan {
    val wanted = requested.map { it.trim() }.filter { it.isNotEmpty() }
    if (wanted.isEmpty()) return CodecPlan(emptyList(), emptyList())
    val matches = wanted.associateWith { name -> available.filter { it.matchesCodecName(name) } }
    val unmatched = wanted.filter { matches.getValue(it).isEmpty() }
    // if no codec is matched, keep going with default values
    if (unmatched.size == wanted.size) return CodecPlan(emptyList(), unmatched)
    val ranked =
        wanted.flatMap { matches.getValue(it) }
            .distinct()
            .mapIndexed { index, codecId -> CodecPriority(codecId, (HIGHEST_PRIORITY - index).coerceAtLeast(1).toShort()) }
    val rankedIds = ranked.map { it.codecId }.toSet()
    val disabled = available.filterNot { it in rankedIds }.map { CodecPriority(it, DISABLED_PRIORITY) }
    return CodecPlan(ranked + disabled, unmatched)
}

/** `PCMU` matches `PCMU/8000/1`; `PCMU/8000/1` matches only itself. Never `PCMUX/...`. */
private fun String.matchesCodecName(name: String): Boolean = equals(name, ignoreCase = true) || startsWith("$name/", ignoreCase = true)

private const val HIGHEST_PRIORITY = 255

private const val DISABLED_PRIORITY: Short = 0

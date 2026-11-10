package io.github.arnonym.config

/**
 * Shared plumbing for the two clikt-backed option strings, `GLOBAL_OPTIONS` and
 * `SIP<n>_OPTIONS`. Both accept the same generous spelling of booleans and both are
 * handed to us as one flat string that has to be split into argv the way a shell would.
 */
internal val BOOL_MAP: Map<String, Boolean> =
    mapOf(
        "enabled" to true, "enable" to true, "true" to true, "yes" to true, "on" to true, "1" to true,
        "disabled" to false, "disable" to false, "false" to false, "no" to false, "off" to false, "0" to false,
    )

internal fun tokenize(raw: String?): List<String> = raw?.trim()?.split(Regex("\\s+"))?.filter { it.isNotEmpty() } ?: emptyList()

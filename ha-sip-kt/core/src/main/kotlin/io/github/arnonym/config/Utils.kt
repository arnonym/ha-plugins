package io.github.arnonym.config

fun convertToInt(
    value: String?,
    default: Int = 0,
): Int = value?.trim()?.toIntOrNull() ?: default

fun convertToDouble(
    value: String?,
    default: Double = 0.0,
): Double = value?.trim()?.toDoubleOrNull() ?: default

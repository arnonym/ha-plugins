package io.github.arnonym.log

import java.time.LocalTime
import java.time.format.DateTimeFormatter

private val timeFormatter: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSS")

fun log(
    accountNumber: Int?,
    message: String,
) {
    val timestamp = LocalTime.now().format(timeFormatter)
    val accountTag = accountNumber?.toString() ?: " "
    println("| $timestamp [$accountTag] $message")
}

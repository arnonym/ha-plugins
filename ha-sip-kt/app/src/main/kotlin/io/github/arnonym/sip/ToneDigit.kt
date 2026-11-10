package io.github.arnonym.sip

import io.github.arnonym.config.Constants
import org.pjsip.pjsua2.ToneDigit
import org.pjsip.pjsua2.ToneDigitVector

fun createToneDigit(digit: Char): ToneDigit {
    val td = ToneDigit()
    td.digit = digit
    td.volume = 0.toShort()
    td.on_msec = Constants.DEFAULT_DTMF_ON.toShort()
    td.off_msec = Constants.DEFAULT_DTMF_OFF.toShort()
    return td
}

fun createToneDigitVector(digits: String): ToneDigitVector {
    val vector = ToneDigitVector()
    digits.forEach { digit -> vector.add(createToneDigit(digit)) }
    return vector
}

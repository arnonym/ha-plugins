import pjsua2 as pj

from constants import DEFAULT_DTMF_ON, DEFAULT_DTMF_OFF


def create_tone_digit(digit: str) -> pj.ToneDigit:
    td = pj.ToneDigit()
    td.digit = digit
    td.volume = 0
    td.on_msec = DEFAULT_DTMF_ON
    td.off_msec = DEFAULT_DTMF_OFF
    return td


def create_tone_digit_vector(digits: str) -> pj.ToneDigitVector:
    tone_digits_vector = pj.ToneDigitVector()
    for d in digits:
        tone_digits_vector.append(create_tone_digit(d))
    return tone_digits_vector

package io.github.arnonym.integrationtest

import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

/** A decoded mono 16-bit PCM wav: what both the fixtures and the recordings are. */
data class Wav(
    val sampleRate: Int,
    val channels: Int,
    val samples: ShortArray,
) {
    val rms: Double
        get() {
            if (samples.isEmpty()) return 0.0
            var sum = 0.0
            samples.forEach { sum += it.toDouble() * it.toDouble() }
            return sqrt(sum / samples.size)
        }

    // Data class with an array field: identity semantics are what the tests want (nothing
    // compares two Wavs), but overriding both keeps the contract honest.
    override fun equals(other: Any?): Boolean = this === other

    override fun hashCode(): Int = System.identityHashCode(this)
}

/**
 * Writes a mono 16-bit PCM sine wav.
 *
 * A pure tone rather than speech because the assertion these fixtures exist for is
 * "does the far end hear *this* frequency" -- which needs a signal with exactly one.
 */
fun writeSineWav(
    target: File,
    sampleRate: Int,
    frequencyHz: Double,
    durationMillis: Int,
    amplitude: Double = 0.5,
) {
    val frameCount = sampleRate * durationMillis / 1000
    val data = ByteBuffer.allocate(frameCount * 2).order(ByteOrder.LITTLE_ENDIAN)
    repeat(frameCount) { i ->
        val value = amplitude * sin(2.0 * PI * frequencyHz * i / sampleRate)
        data.putShort((value * Short.MAX_VALUE).roundToInt().toShort())
    }
    val pcm = data.array()

    val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
    header.put("RIFF".toByteArray())
    header.putInt(36 + pcm.size)
    header.put("WAVE".toByteArray())
    header.put("fmt ".toByteArray())
    header.putInt(16)
    header.putShort(1) // PCM
    header.putShort(1) // mono
    header.putInt(sampleRate)
    header.putInt(sampleRate * 2) // byte rate
    header.putShort(2) // block align
    header.putShort(16) // bits per sample
    header.put("data".toByteArray())
    header.putInt(pcm.size)

    target.outputStream().use {
        it.write(header.array())
        it.write(pcm)
    }
}

/**
 * Reads a mono/stereo 16-bit PCM wav, walking the chunk list rather than assuming the
 * canonical 44-byte header -- pjsip's recorder is not the only writer involved.
 */
fun readWav(file: File): Wav {
    val bytes = file.readBytes()
    require(bytes.size > 12) { "$file is too small to be a wav (${bytes.size} bytes)" }
    val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
    require(String(bytes, 0, 4) == "RIFF" && String(bytes, 8, 4) == "WAVE") { "$file is not a RIFF/WAVE file" }

    var sampleRate = 0
    var channels = 0
    var bitsPerSample = 0
    var samples: ShortArray? = null

    var position = 12
    while (position + 8 <= bytes.size) {
        val chunkId = String(bytes, position, 4)
        val declaredSize = buffer.getInt(position + 4)
        val body = position + 8
        // A writer that never got to patch its header leaves the size at 0, and one that
        // was killed mid-write leaves it too large. Both are readable: the samples are on
        // disk either way, so fall back to "everything that is actually there".
        val chunkSize =
            if (declaredSize <= 0 || body + declaredSize > bytes.size) bytes.size - body else declaredSize
        when (chunkId) {
            "fmt " -> {
                channels = buffer.getShort(body + 2).toInt()
                sampleRate = buffer.getInt(body + 4)
                bitsPerSample = buffer.getShort(body + 14).toInt()
            }
            "data" -> {
                require(bitsPerSample == 16) { "$file is $bitsPerSample-bit; only 16-bit PCM is supported" }
                samples = ShortArray(chunkSize / 2) { buffer.getShort(body + it * 2) }
            }
        }
        if (chunkId == "data") break
        // Chunks are word-aligned: an odd size is followed by a pad byte.
        position = body + chunkSize + (chunkSize and 1)
    }

    return Wav(sampleRate, channels, requireNotNull(samples) { "$file has no data chunk" })
}

/**
 * Blocks until the recording at [file] has been finalized, or fails.
 *
 * pjmedia tears the recorder's conference port down on its own thread, so the wav is
 * closed -- last samples flushed, chunk sizes patched -- a moment *after* ha-sip reports
 * `recording_stopped`. Polling is what makes an assertion about the finished file honest
 * rather than a race.
 */
fun awaitFinalizedWav(
    file: File,
    timeoutMillis: Long = 5_000,
): Wav {
    val deadline = System.nanoTime() + timeoutMillis * 1_000_000
    while (true) {
        val declared = runCatching { declaredDataChunkSize(file) }.getOrDefault(0)
        if (declared > 0) return readWav(file)
        check(System.nanoTime() < deadline) {
            "recording was never finalized within ${timeoutMillis}ms: data chunk still claims " +
                "$declared bytes for a ${file.length()}-byte file"
        }
        Thread.sleep(25)
    }
}

/**
 * The size the wav header *claims* the audio data has, which [readWav] deliberately
 * ignores.
 *
 * pjmedia writes this as zero and patches it when the file is closed, so it is the one
 * value that proves a recording was finalized rather than merely written to. Strict
 * readers -- and some players -- treat a zero here as an empty file.
 */
fun declaredDataChunkSize(file: File): Int {
    val bytes = file.readBytes()
    val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
    var position = 12
    while (position + 8 <= bytes.size) {
        val chunkId = String(bytes, position, 4)
        val declaredSize = buffer.getInt(position + 4)
        if (chunkId == "data") return declaredSize
        if (declaredSize <= 0) break
        position += 8 + declaredSize + (declaredSize and 1)
    }
    error("$file has no data chunk")
}

/**
 * Magnitude of one frequency bin, by the Goertzel algorithm.
 *
 * Cheaper and clearer than pulling in an FFT for what these tests ask: the strength of a
 * handful of individual frequencies, not a whole spectrum.
 */
private fun goertzelMagnitude(
    samples: ShortArray,
    sampleRate: Int,
    frequencyHz: Double,
): Double {
    if (samples.isEmpty()) return 0.0
    val coefficient = 2.0 * cos(2.0 * PI * frequencyHz / sampleRate)
    var s1 = 0.0
    var s2 = 0.0
    samples.forEach { sample ->
        val s0 = sample.toDouble() + coefficient * s1 - s2
        s2 = s1
        s1 = s0
    }
    return sqrt(s1 * s1 + s2 * s2 - coefficient * s1 * s2) / samples.size
}

/**
 * The strongest frequency in [minHz]..[maxHz], to [stepHz] resolution.
 *
 * This is the whole point of the audio fidelity scenarios: a prompt that arrives correctly
 * peaks at the frequency it was generated at, whatever resampling happened on the way.
 * Broadband noise has no such peak, and a buffer replayed at the wrong rate peaks at the
 * wrong multiple of it.
 */
fun dominantFrequency(
    wav: Wav,
    minHz: Double = 100.0,
    maxHz: Double = 3800.0,
    stepHz: Double = 5.0,
): Double {
    var bestFrequency = 0.0
    var bestMagnitude = -1.0
    var frequency = minHz
    while (frequency <= maxHz) {
        val magnitude = goertzelMagnitude(wav.samples, wav.sampleRate, frequency)
        if (magnitude > bestMagnitude) {
            bestMagnitude = magnitude
            bestFrequency = frequency
        }
        frequency += stepHz
    }
    return bestFrequency
}

/**
 * How far the tone at [frequencyHz] stands above everything else in the signal.
 *
 * Deliberately a *relative* measure rather than a share of total energy: a lossy codec
 * (pjsip's default negotiation lands on speex) spreads real quantization noise across the
 * spectrum, which drags an energy-share metric down without the prompt being any less
 * audible. What distinguishes working audio from the reported "pure noise" is whether one
 * frequency towers over the rest -- for broadband noise nothing does, and this approaches 1.
 */
fun toneToNoiseRatio(
    wav: Wav,
    frequencyHz: Double,
    guardHz: Double = 150.0,
    minHz: Double = 100.0,
    maxHz: Double = 3800.0,
): Double {
    if (wav.samples.isEmpty()) return 0.0
    var inBand = 0.0
    var offBand = 0.0
    var probe = minHz
    while (probe <= maxHz) {
        val magnitude = goertzelMagnitude(wav.samples, wav.sampleRate, probe)
        if (kotlin.math.abs(probe - frequencyHz) <= guardHz) {
            if (magnitude > inBand) inBand = magnitude
        } else if (magnitude > offBand) {
            offBand = magnitude
        }
        probe += 5.0
    }
    if (offBand == 0.0) return Double.MAX_VALUE
    return inBand / offBand
}

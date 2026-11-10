package io.github.arnonym.audio

import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test

class AudioCacheTest {
    @Test
    fun `the same prompt at a different sample rate is a different cache entry`() {
        val atSourceRate = AudioCache.getCacheFileName("/cache", CacheType.MESSAGE, "hello", null)
        val at8k = AudioCache.getCacheFileName("/cache", CacheType.MESSAGE, "hello", 8000)
        val at16k = AudioCache.getCacheFileName("/cache", CacheType.MESSAGE, "hello", 16000)

        listOf(atSourceRate, at8k, at16k).distinct().size shouldBe 3
    }

    @Test
    fun `the same prompt at the same rate is one cache entry`() {
        AudioCache.getCacheFileName("/cache", CacheType.MESSAGE, "hello", 8000) shouldBe
            AudioCache.getCacheFileName("/cache", CacheType.MESSAGE, "hello", 8000)
    }

    @Test
    fun `an audio file and a message of the same name do not collide`() {
        val message = AudioCache.getCacheFileName("/cache", CacheType.MESSAGE, "hello", 8000)
        val file = AudioCache.getCacheFileName("/cache", CacheType.AUDIO_FILE, "hello", 8000)
        (message == file) shouldBe false
    }
}

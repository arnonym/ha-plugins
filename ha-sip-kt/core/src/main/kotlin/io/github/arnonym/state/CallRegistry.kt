package io.github.arnonym.state

import io.github.arnonym.log.log
import java.util.concurrent.ConcurrentHashMap

class CallRegistry<C : Any> {
    private val currentCalls = ConcurrentHashMap<String, C>()
    private val altIdMap = ConcurrentHashMap<String, List<String>>()

    fun registerCall(
        callbackId: String,
        newCall: C,
        additionalIds: List<String>,
    ) {
        val idsToPrint = listOf(callbackId) + additionalIds
        log(null, "Add to state with IDs ${idsToPrint.joinToString(", ")}")
        currentCalls[callbackId] = newCall
        altIdMap[callbackId] = additionalIds
    }

    fun forgetCall(callbackId: String) {
        log(null, "Remove from state: $callbackId")
        currentCalls.remove(callbackId)
        altIdMap.remove(callbackId)
    }

    fun resolveCallbackId(identifier: String): String? {
        if (currentCalls.containsKey(identifier)) return identifier
        return altIdMap.entries.firstOrNull { (_, altIds) -> identifier in altIds }?.key
    }

    fun isActive(identifier: String): Boolean = resolveCallbackId(identifier) != null

    fun output() {
        if (currentCalls.isNotEmpty()) {
            log(null, "Currently registered calls:")
            currentCalls.keys.forEach { callbackId ->
                val allIds = listOf(callbackId) + altIdMap.getOrDefault(callbackId, emptyList())
                log(null, "    ${allIds.joinToString(", ")}")
            }
        } else {
            log(null, "No active calls.")
        }
    }

    fun getCall(identifier: String): C? {
        val callbackId = resolveCallbackId(identifier) ?: return null
        return currentCalls[callbackId]
    }

    /** Current live call objects -- used by the main loop to tick `handleEvents()` on each. */
    fun currentCalls(): Collection<C> = currentCalls.values.toList()
}

package io.github.arnonym.sip

import io.github.arnonym.log.log
import java.util.concurrent.ConcurrentLinkedQueue
import org.pjsip.pjsua2.Call as PjCall

object CallDisposal {
    private val pending = ConcurrentLinkedQueue<PjCall>()

    fun enqueue(call: PjCall) {
        pending.add(call)
    }

    fun drain() {
        pending.removeIf { call ->
            try {
                if (call.isActive) {
                    false
                } else {
                    call.delete()
                    true
                }
            } catch (e: Exception) {
                log(null, "Warning: could not release native call object: ${e.message}")
                true
            }
        }
    }
}

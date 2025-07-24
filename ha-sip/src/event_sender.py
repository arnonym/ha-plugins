from typing import Optional, Callable, List

import ha

type EventSenderCallback = Callable[[ha.WebhookEvent, Optional[str]], None]

class EventSender(object):
    def __init__(self):
        self.callbacks: List[EventSenderCallback] = []

    def register_sender(self, callback: EventSenderCallback):
        self.callbacks.append(callback)

    def send_event(self, event: ha.WebhookEvent, webhook_id: Optional[str] = None):
        for callback in self.callbacks:
            callback(event, webhook_id)

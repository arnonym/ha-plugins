from typing import Optional, Callable, List

import ha


class EventSender(object):
    def __init__(self):
        self.callbacks: List[Callable[[ha.WebhookEvent, Optional[str]], None]] = []

    def register_sender(self, callback: Callable[[ha.WebhookEvent, Optional[str]], None]):
        self.callbacks.append(callback)

    def send_event(self, event: ha.WebhookEvent, webhook_id: Optional[str] = None):
        for callback in self.callbacks:
            callback(event, webhook_id)

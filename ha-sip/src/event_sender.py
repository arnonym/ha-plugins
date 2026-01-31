from typing import Optional, Callable, List, Any


class EventSender(object):
    def __init__(self):
        self.callbacks: List[Callable[[Any, Optional[str]], None]] = []

    def register_sender(self, callback: Callable[[Any, Optional[str]], None]):
        self.callbacks.append(callback)

    def send_event(self, event: Any, webhook_id: Optional[str] = None):
        for callback in self.callbacks:
            callback(event, webhook_id)

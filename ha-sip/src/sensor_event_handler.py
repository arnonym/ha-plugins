from __future__ import annotations

from typing import Any, Dict, Optional

from sensor import SensorUpdater


class SensorEventHandler:
    def __init__(self, sensor_updater: SensorUpdater):
        self.sensor_updater = sensor_updater
        # Track call direction per account: account_index -> "incoming" or "outgoing"
        self.call_directions: Dict[int, str] = {}

    def handle_event(self, event: Any, webhook_id: Optional[str] = None) -> None:
        event_type = event.get("event")
        sip_account = event.get("sip_account")
        if sip_account is None:
            return
        if event_type == "incoming_call":
            self.call_directions[sip_account] = "incoming"
            self.sensor_updater.set_call_active(sip_account, event)
        elif event_type == "outgoing_call_initiated":
            self.call_directions[sip_account] = "outgoing"
        elif event_type == "call_established":
            self.sensor_updater.set_call_active(sip_account, event)
        elif event_type == "call_disconnected":
            self.sensor_updater.set_call_inactive(sip_account)
            # Update last call sensor with the direction we tracked
            direction = self.call_directions.pop(sip_account, "incoming")
            self.sensor_updater.update_last_call(sip_account, direction, event)

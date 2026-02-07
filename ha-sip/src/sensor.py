from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, List, Optional

import requests

from ha import HaConfig
from log import log


@dataclass
class SensorConfig:
    enabled: bool
    entity_prefix: str


class SensorUpdater:
    def __init__(self, ha_config: HaConfig, sensor_config: SensorConfig, enabled_accounts: List[int]):
        self.ha_config = ha_config
        self.sensor_config = sensor_config
        self.enabled_accounts = enabled_accounts

    def _get_sanitized_prefix(self) -> str:
        return self.sensor_config.entity_prefix.replace('-', '_').lower()

    def _get_entity_id(self, account_index: int) -> str:
        # Sanitize prefix: replace hyphens with underscores, lowercase only
        prefix = self._get_sanitized_prefix()
        return f"sensor.{prefix}_account_{account_index}"

    def _get_registration_entity_id(self, account_index: int) -> str:
        prefix = self._get_sanitized_prefix()
        return f"sensor.{prefix}_registration_{account_index}"

    def _get_last_call_entity_id(self, account_index: int) -> str:
        prefix = self._get_sanitized_prefix()
        return f"sensor.{prefix}_last_call_{account_index}"

    def _get_states_url(self, entity_id: str) -> str:
        return self.ha_config.base_url + '/states/' + entity_id

    def _update_sensor(self, entity_id: str, state: str, attributes: Dict[str, Any]) -> None:
        url = self._get_states_url(entity_id)
        headers = self.ha_config.create_headers()
        # Filter out None values as HA REST API doesn't accept them
        filtered_attributes = {k: v for k, v in attributes.items() if v is not None}
        payload = {
            "state": state,
            "attributes": filtered_attributes,
        }
        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.ok:
                log(None, f"Sensor update {entity_id}: {response.status_code}")
            else:
                log(None, f"Sensor update {entity_id} failed: {response.status_code} {response.text}")
        except Exception as e:
            log(None, f"Error updating sensor {entity_id}: {e}")

    def set_call_active(self, account_index: int, call_info: Dict[str, Any]) -> None:
        if not self.sensor_config.enabled:
            return
        entity_id = self._get_entity_id(account_index)
        attributes = {
            "friendly_name": f"SIP Account {account_index}",
            "icon": "mdi:phone-in-talk",
            "caller": call_info.get("caller"),
            "called": call_info.get("called"),
            "parsed_caller": call_info.get("parsed_caller"),
            "parsed_called": call_info.get("parsed_called"),
            "sip_account": call_info.get("sip_account"),
            "call_id": call_info.get("call_id"),
            "internal_id": call_info.get("internal_id"),
            "headers": call_info.get("headers", {}),
        }
        self._update_sensor(entity_id, "true", attributes)

    def set_call_inactive(self, account_index: int) -> None:
        if not self.sensor_config.enabled:
            return
        entity_id = self._get_entity_id(account_index)
        attributes = {
            "friendly_name": f"SIP Account {account_index}",
            "icon": "mdi:phone",
        }
        self._update_sensor(entity_id, "false", attributes)

    def update_registration_status(self, account_index: int, code: int, reason: str) -> None:
        if not self.sensor_config.enabled:
            return
        entity_id = self._get_registration_entity_id(account_index)
        if code == 200:
            state = "registered"
            icon = "mdi:phone-check"
        elif code == 0:
            # Code 0 typically means registration in progress or unregistered
            state = "unregistered"
            icon = "mdi:phone-off"
        else:
            state = "failed"
            icon = "mdi:phone-alert"
        attributes = {
            "friendly_name": f"SIP Registration {account_index}",
            "icon": icon,
            "status_code": code,
            "reason": reason,
            "last_change": datetime.now().isoformat(),
        }
        self._update_sensor(entity_id, state, attributes)

    def update_last_call(
        self,
        account_index: int,
        direction: str,
        call_info: Optional[Dict[str, Any]] = None
    ) -> None:
        if not self.sensor_config.enabled:
            return
        entity_id = self._get_last_call_entity_id(account_index)
        if direction == "none":
            icon = "mdi:phone"
        elif direction == "incoming":
            icon = "mdi:phone-incoming"
        else:  # outgoing
            icon = "mdi:phone-outgoing"
        attributes: Dict[str, Any] = {
            "friendly_name": f"SIP Last Call {account_index}",
            "icon": icon,
        }
        if call_info:
            attributes["caller"] = call_info.get("caller")
            attributes["called"] = call_info.get("called")
            attributes["parsed_caller"] = call_info.get("parsed_caller")
            attributes["parsed_called"] = call_info.get("parsed_called")
            attributes["call_id"] = call_info.get("call_id")
            attributes["timestamp"] = datetime.now().isoformat()
        self._update_sensor(entity_id, direction, attributes)

    def initialize_sensors(self) -> None:
        if not self.sensor_config.enabled:
            return
        log(None, f"Initializing sensors with prefix '{self.sensor_config.entity_prefix}' for accounts: {self.enabled_accounts}")
        for account_index in self.enabled_accounts:
            self.set_call_inactive(account_index)
            self._update_sensor(
                self._get_registration_entity_id(account_index),
                "unknown",
                {
                    "friendly_name": f"SIP Registration {account_index}",
                    "icon": "mdi:phone-clock",
                }
            )
            self.update_last_call(account_index, "none")

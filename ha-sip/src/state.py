from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List

from log import log

if TYPE_CHECKING:
    import call


class State(object):
    def __init__(self):
        self.current_call_dict: dict[str, call.Call] = {}
        self.alt_id_map: dict[str, List[str]] = {}

    def register_call(self, callback_id: str, new_call: call.Call, additional_ids: List[str]) -> None:
        ids_to_print = [callback_id] + additional_ids
        log(None, 'Add to state with IDs %s' % ', '.join(ids_to_print))
        self.current_call_dict[callback_id] = new_call
        self.alt_id_map[callback_id] = additional_ids

    def forget_call(self, callback_id: str) -> None:
        log(None, 'Remove from state: %s' % callback_id)
        del self.current_call_dict[callback_id]
        del self.alt_id_map[callback_id]

    def resolve_callback_id(self, identifier: str) -> Optional[str]:
        if identifier in self.current_call_dict:
            return identifier
        for callback_id, alt_ids in self.alt_id_map.items():
            if identifier in alt_ids:
                return callback_id
        return None

    def is_active(self, identifier: str) -> bool:
        return self.resolve_callback_id(identifier) is not None

    def output(self) -> None:
        if self.current_call_dict:
            log(None, 'Currently registered calls:')
            for callback_id, call_obj in self.current_call_dict.items():
                all_ids = [callback_id] + self.alt_id_map.get(callback_id, [])
                log(None, '    %s' % ', '.join(all_ids))
        else:
            log(None, 'No active calls.')

    def get_call(self, identifier: str) -> Optional[call.Call]:
        callback_id = self.resolve_callback_id(identifier)
        if callback_id:
            return self.current_call_dict.get(callback_id)
        return None

    def get_call_unsafe(self, identifier: str) -> call.Call:
        callback_id = self.resolve_callback_id(identifier)
        if callback_id:
            return self.current_call_dict[callback_id]
        raise KeyError(f'Call not found for identifier: {identifier}')


def create() -> State:
    new_state = State()
    return new_state

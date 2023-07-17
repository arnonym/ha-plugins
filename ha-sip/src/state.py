from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from call_state_change import CallStateChange
from log import log

if TYPE_CHECKING:
    import call


class State(object):
    def __init__(self):
        self.current_call_dict: dict[str, call.Call] = {}

    def on_state_change(self, state: CallStateChange, caller_id: str, new_call: call.Call) -> None:
        if state == CallStateChange.HANGUP:
            log(None, 'Remove from state: %s' % caller_id)
            del self.current_call_dict[caller_id]
        elif state == CallStateChange.CALL:
            log(None, 'Add to state: %s' % caller_id)
            self.current_call_dict[caller_id] = new_call

    def is_active(self, caller_id: str) -> bool:
        return caller_id in self.current_call_dict

    def output(self) -> None:
        for number in self.current_call_dict.keys():
            print(number)

    def get_call(self, caller_id: str) -> Optional[call.Call]:
        return self.current_call_dict.get(caller_id)

    def get_call_unsafe(self, caller_id: str) -> call.Call:
        return self.current_call_dict[caller_id]


def create() -> State:
    new_state = State()
    return new_state

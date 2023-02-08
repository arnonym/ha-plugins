import call
from log import log


class State(object):
    def __init__(self):
        self.current_call_dict: dict[str, call.Call] = {}

    def callback(self, state: call.CallStateChange, caller_id: str, new_call: call.Call) -> None:
        if state == call.CallStateChange.HANGUP:
            log(None, 'Remove from state: %s' % caller_id)
            del self.current_call_dict[caller_id]
        elif state == call.CallStateChange.CALL:
            log(None, 'Add to state: %s' % caller_id)
            self.current_call_dict[caller_id] = new_call

    def is_active(self, caller_id: str) -> bool:
        return caller_id in self.current_call_dict

    def output(self) -> None:
        for number in self.current_call_dict.keys():
            print(number)

    def get_call(self, caller_id: str) -> call.Call:
        return self.current_call_dict[caller_id]


def create() -> State:
    new_state = State()
    return new_state

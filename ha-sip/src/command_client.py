import json
import os
import fcntl
import sys
from typing import List, Union, Literal, Optional
from typing_extensions import TypedDict

import call


class Command(TypedDict):
    command: Union[Literal['dial'], Literal['hangup'], Literal['answer'], Literal['send_dtmf'], Literal['state'], Literal['quit']]
    number: Optional[str]
    menu: Optional[call.MenuFromStdin]
    ring_timeout: Optional[str]
    sip_account: Optional[str]
    webhook_to_call_after_call_was_established: Optional[str]
    digits: Optional[str]
    method: Optional[call.DtmfMethod]


class CommandClient(object):
    def __init__(self):
        self.buffer = ''
        self.stdin_fd = fcntl.fcntl(sys.stdin, fcntl.F_GETFD)
        stdin_fl = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
        fcntl.fcntl(sys.stdin, fcntl.F_SETFL, stdin_fl | os.O_NONBLOCK)

    def get_command_list(self) -> List[Command]:
        try:
            data = os.read(self.stdin_fd, 64)
        except BlockingIOError:
            data = b''
        self.buffer += data.decode('utf-8', 'ignore')
        if '\n' in self.buffer:
            *line_list, self.buffer = self.buffer.split('\n')
            return CommandClient.list_to_json(line_list)
        return []

    @staticmethod
    def list_to_json(raw_list: List[str]) -> List[Command]:
        result = []
        for entry in raw_list:
            if entry == '':
                continue
            try:
                from_json = json.loads(entry)
                result.append(from_json)
            except json.JSONDecodeError:
                print('Could not deserialize JSON:', entry)
        return result

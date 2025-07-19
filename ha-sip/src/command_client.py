from __future__ import annotations

import fcntl
import json
import os
import sys
from typing import List, Union, Literal, Optional, Dict, Any
from typing import TYPE_CHECKING

from typing_extensions import TypedDict

if TYPE_CHECKING:
    import call


class Command(TypedDict):
    command: Union[
        None,
        Literal['call_service'],
        Literal['dial'],
        Literal['hangup'],
        Literal['answer'],
        Literal['transfer'],
        Literal['bridge_audio'],
        Literal['send_dtmf'],
        Literal['stop_playback'],
        Literal['play_message'],
        Literal['play_audio_file'],
        Literal['state'],
        Literal['quit'],
    ]
    number: Optional[str]
    menu: Optional[call.MenuFromStdin]
    ring_timeout: Optional[str]
    sip_account: Optional[str]
    webhook_to_call_after_call_was_established: Optional[str]
    webhook_to_call: Optional[call.WebhookToCall]
    digits: Optional[str]
    method: Optional[call.DtmfMethod]
    bridge_to: Optional[str]
    transfer_to: Optional[str]
    domain: Optional[str]
    service: Optional[str]
    entity_id: Optional[str]
    audio_file: Optional[str]
    message: Optional[str]
    cache_audio: Optional[bool]
    wait_for_audio_to_finish: Optional[bool]
    tts_language: Optional[str]
    service_data: Optional[Dict[str, Any]]


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

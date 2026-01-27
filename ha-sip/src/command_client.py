from __future__ import annotations

import fcntl
import json
import os
import sys
from typing import List, Union, Literal, Optional, Dict, Any
from typing import TYPE_CHECKING

from typing_extensions import TypedDict

from post_action import PostActionHangup

if TYPE_CHECKING:
    import call


class CommandCallService(TypedDict):
    command: Optional[Literal['call_service']]
    domain: str
    service: str
    entity_id: Optional[str]
    service_data: Optional[Dict[str, Any]]


class CommandDial(TypedDict):
    command: Literal['dial']
    number: str
    menu: Optional[call.MenuFromStdin]
    ring_timeout: Optional[str]
    sip_account: Optional[str]
    webhook_to_call_after_call_was_established: Optional[str]
    webhook_to_call: Optional[call.WebhookToCall]


class CommandHangup(TypedDict):
    command: Literal['hangup']
    number: str


class CommandAnswer(TypedDict):
    command: Literal['answer']
    number: str
    menu: Optional[call.MenuFromStdin]
    webhook_to_call: Optional[call.WebhookToCall]


class CommandTransfer(TypedDict):
    command: Literal['transfer']
    number: str
    transfer_to: str


class CommandBridgeAudio(TypedDict):
    command: Literal['bridge_audio']
    number: str
    bridge_to: str


class CommandSendDtmf(TypedDict):
    command: Literal['send_dtmf']
    number: str
    digits: str
    method: Optional[call.DtmfMethod]


class CommandStopPlayback(TypedDict):
    command: Literal['stop_playback']
    number: str


class CommandStartRecording(TypedDict):
    command: Literal['start_recording']
    number: str
    recording_file: str


class CommandStopRecording(TypedDict):
    command: Literal['stop_recording']
    number: str


class CommandPlayMessage(TypedDict):
    command: Literal['play_message']
    number: str
    message: str
    tts_language: Optional[str]
    handle_as_template: Optional[bool]
    cache_audio: Optional[bool]
    wait_for_audio_to_finish: Optional[bool]
    post_action: Optional[PostActionHangup]


class CommandPlayAudioFile(TypedDict):
    command: Literal['play_audio_file']
    number: str
    audio_file: str
    cache_audio: Optional[bool]
    wait_for_audio_to_finish: Optional[bool]
    post_action: Optional[PostActionHangup]


class CommandState(TypedDict):
    command: Literal['state']


class CommandQuit(TypedDict):
    command: Literal['quit']


Command = Union[
    CommandCallService,
    CommandDial,
    CommandHangup,
    CommandAnswer,
    CommandTransfer,
    CommandBridgeAudio,
    CommandSendDtmf,
    CommandStopPlayback,
    CommandStartRecording,
    CommandStopRecording,
    CommandPlayMessage,
    CommandPlayAudioFile,
    CommandState,
    CommandQuit,
]


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

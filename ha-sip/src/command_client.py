import json
import os
import fcntl
import sys


class CommandClient(object):
    def __init__(self):
        self.buffer = ""
        self.stdin_fd = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
        fcntl.fcntl(sys.stdin, fcntl.F_SETFL, self.stdin_fd | os.O_NONBLOCK)

    def get_command_list(self) -> [str]:
        try:
            data = os.read(self.stdin_fd, 64)
        except BlockingIOError:
            data = b""
        self.buffer += data.decode('unicode_escape')
        if "\n" in self.buffer:
            *line_list, self.buffer = self.buffer.split("\n")
            return CommandClient.list_to_json(line_list)
        return []

    @staticmethod
    def list_to_json(raw_list: [str]) -> [dict]:
        result = []
        for entry in raw_list:
            if entry == "":
                continue
            try:
                from_json = json.loads(entry)
                result.append(from_json)
            except json.JSONDecodeError:
                print("Could not deserialize JSON:", entry)
        return result

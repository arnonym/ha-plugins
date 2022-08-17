from typing import Any


def convert_to_int(s: Any, default=0) -> int:
    try:
        i = int(s)
    except (ValueError, TypeError):
        print("| Error: Not an integer value", s)
        return default
    return i

from typing import Any


def convert_to_int(s: Any, default=0) -> int:
    try:
        i = int(s)
    except (ValueError, TypeError):
        return default
    return i


def convert_to_float(s: Any, default=0.0) -> float:
    try:
        i = float(s)
    except (ValueError, TypeError):
        return default
    return i


def safe_list_get(source_list: list, index: int, default: Any = None) -> Any:
    try:
        return source_list[index]
    except IndexError:
        return default

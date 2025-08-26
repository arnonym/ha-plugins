from typing import Any, Generator, Sequence

from typing_extensions import TypeVar


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

T = TypeVar('T')

def chunks(lst: list[T], n) -> Generator[list[T], Any, None]:
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

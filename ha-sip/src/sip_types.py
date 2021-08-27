from enum import Enum
from typing import Callable, TypedDict, Union, Optional


class CallStateChange(Enum):
    CALL = 1
    HANGUP = 2


CallCallback = Callable[[CallStateChange, str, 'Call'], None]
StateType = Union[str, int, bool, float]


class Action(TypedDict):
    domain: str
    service: str
    entity_id: str


class Menu(TypedDict):
    message: str
    action: Optional[Action]
    choices: dict[int, 'Menu']

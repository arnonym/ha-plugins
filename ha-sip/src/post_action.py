from typing import Union

from typing_extensions import TypedDict, Literal


class PostActionReturn(TypedDict):
    action: Literal['return']
    level: int


class PostActionJump(TypedDict):
    action: Literal['jump']
    menu_id: str


class PostActionHangup(TypedDict):
    action: Literal['hangup']


class PostActionNoop(TypedDict):
    action: Literal['noop']


class PostActionRepeatMessage(TypedDict):
    action: Literal['repeat_message']


PostAction = Union[PostActionReturn, PostActionJump, PostActionHangup, PostActionNoop, PostActionRepeatMessage]
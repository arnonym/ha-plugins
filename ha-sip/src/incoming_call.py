from typing import Optional

from typing_extensions import TypedDict

import call


class IncomingCallConfig(TypedDict):
    allowed_numbers: Optional[list[str]]
    blocked_numbers: Optional[list[str]]
    answer_after: Optional[int]
    webhook_to_call: Optional[call.WebhookToCall]
    menu: call.MenuFromStdin

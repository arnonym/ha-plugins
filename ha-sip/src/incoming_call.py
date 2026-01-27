from typing import Optional

from typing_extensions import TypedDict

import call
import webhook


class IncomingCallConfig(TypedDict):
    allowed_numbers: Optional[list[str]]
    blocked_numbers: Optional[list[str]]
    answer_after: Optional[int]
    webhook_to_call: Optional[webhook.WebhookToCall]
    menu: call.MenuFromStdin

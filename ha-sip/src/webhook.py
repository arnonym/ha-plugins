from __future__ import annotations

from typing import Optional

from typing_extensions import TypedDict

import ha
from event_sender import EventSender
from log import log


class WebhookToCall(TypedDict):
    call_established: Optional[str]
    entered_menu: Optional[str]
    dtmf_digit: Optional[str]
    call_disconnected: Optional[str]
    timeout: Optional[str]
    ring_timeout: Optional[str]
    playback_done: Optional[str]


class CallInfo(TypedDict):
    local_uri: str
    remote_uri: str
    parsed_caller: Optional[str]
    parsed_called: Optional[str]
    call_id: str


def trigger_webhook(
    event: ha.WebhookEvent,
    call_info: Optional[CallInfo],
    sip_account: int,
    internal_id: str,
    event_sender_callback: EventSender,
    webhooks: Optional[WebhookToCall] = None,
) -> None:
    complete_event: ha.CompleteWebhookEvent = {
        **event,
        'caller': call_info['remote_uri'] if call_info else 'unknown',
        'called': call_info['local_uri'] if call_info else 'unknown',
        'parsed_caller': call_info['parsed_caller'] if call_info else None,
        'parsed_called': call_info['parsed_called'] if call_info else None,
        'sip_account': sip_account,
        'call_id': call_info['call_id'] if call_info else None,
        'internal_id': internal_id,
    }
    event_id = event.get('event')
    if webhooks and (additional_webhook := webhooks.get(event_id)):
        log(sip_account, 'Calling additional webhook %s for event %s' % (additional_webhook, event_id))
        event_sender_callback.send_event(complete_event, additional_webhook)
    event_sender_callback.send_event(complete_event)

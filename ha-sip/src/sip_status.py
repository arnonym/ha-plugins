from __future__ import annotations

# Reason phrases taken verbatim from pjsip/src/pjsip/sip_msg.c
# init_status_phrase() (pjproject tag 2.17).
#
# pjsip_get_status_text() exists at the C level but is not exposed by the
# SWIG Python binding (only the pjsip_status_code enum constants are imported).
# We mirror the table here so that CallOpParam.reason can be set explicitly
# whenever a custom SIP status code is used on hangup.

REASON_PHRASES: dict[int, str] = {
    # 1xx Provisional
    100: "Trying",
    180: "Ringing",
    181: "Call Is Being Forwarded",
    182: "Queued",
    183: "Session Progress",
    199: "Early Dialog Terminated",

    # 2xx Success
    200: "OK",
    202: "Accepted",
    204: "No Notification",

    # 3xx Redirection
    300: "Multiple Choices",
    301: "Moved Permanently",
    302: "Moved Temporarily",
    305: "Use Proxy",
    380: "Alternative Service",

    # 4xx Request Failure
    400: "Bad Request",
    401: "Unauthorized",
    402: "Payment Required",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    407: "Proxy Authentication Required",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    411: "Length Required",
    412: "Conditional Request Failed",
    413: "Request Entity Too Large",
    414: "Request-URI Too Long",
    415: "Unsupported Media Type",
    416: "Unsupported URI Scheme",
    417: "Unknown Resource-Priority",
    420: "Bad Extension",
    421: "Extension Required",
    422: "Session Interval Too Small",
    423: "Interval Too Brief",
    424: "Bad Location Information",
    428: "Use Identity Header",
    429: "Provide Referrer Identity",
    430: "Flow Failed",
    433: "Anonymity Disallowed",
    436: "Bad Identity-Info",
    437: "Unsupported Certificate",
    438: "Invalid Identity Header",
    439: "First Hop Lacks Outbound Support",
    440: "Max-Breadth Exceeded",
    469: "Bad Info Package",
    470: "Consent Needed",
    480: "Temporarily Unavailable",
    481: "Call/Transaction Does Not Exist",
    482: "Loop Detected",
    483: "Too Many Hops",
    484: "Address Incomplete",
    485: "Ambiguous",
    486: "Busy Here",
    487: "Request Terminated",
    488: "Not Acceptable Here",
    489: "Bad Event",
    490: "Request Updated",
    491: "Request Pending",
    493: "Undecipherable",
    494: "Security Agreement Required",

    # 5xx Server Failure
    500: "Server Internal Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Server Time-out",
    505: "Version Not Supported",
    513: "Message Too Large",
    555: "Push Notification Service Not Supported",
    580: "Precondition Failure",

    # 6xx Global Failure
    600: "Busy Everywhere",
    603: "Decline",
    604: "Does Not Exist Anywhere",
    606: "Not Acceptable",
    607: "Unwanted",
    608: "Rejected",
}

"""Purpose: supply an incident record of the kind a host passes the incident example's host adapter, with sensitive values in its raw log, as a test input."""

from __future__ import annotations

from typing import Any


# A test input, never a default: the adapter prepares only from the record its caller supplies.
# am[verifies a-ie-s5-incident-host-1018@53176a]
def incident_record() -> dict[str, Any]:
    """A fresh incident record whose raw log holds customer data, an order id and a live token."""

    return {
        "service": "checkout",
        "status": "degraded",
        "summary": "Checkout payment retries are timing out.",
        "next_update": "15 minutes",
        "raw_log": {
            "customer_email": "ava@example.com",
            "order_id": "ORD-19942",
            "request_payload": "{card_token: tok_live_secret}",
            "access_token": "tok_live_secret",
            "stack_trace": "Traceback: internal checkout worker path",
            "error_code": "PAYMENT_TIMEOUT",
        },
    }

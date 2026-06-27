"""Execute the recommended action on real incident data and verify the result.

The decision layer says *what* to do; this does it and checks it. Given the actual
raw incident log (with customer emails, order IDs, tokens, ...), executing the
recommended action produces the artifact you would really send, and a leak check
proves the sensitive values are gone. That is the problem actually solved: real data
in, a safe deliverable out, verified -- not a recommendation.
"""

from __future__ import annotations

from typing import Any

# The privacy policy: fields that must never reach an external update, and the
# diagnostic fields that are safe to keep for coordination.
RESTRICTED_FIELDS = (
    "customer_email",
    "order_id",
    "request_payload",
    "access_token",
    "stack_trace",
    "raw_log",
)
ALLOWED_DIAGNOSTICS = ("error_code", "failure_mode", "affected_surface")


def default_incident() -> dict[str, Any]:
    """A realistic incident with sensitive values in the raw log."""
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


def redact(raw_log: dict[str, Any]) -> dict[str, Any]:
    """Drop restricted values, keep allowed diagnostics."""
    diagnostics: dict[str, Any] = {}
    for key, value in raw_log.items():
        if key in RESTRICTED_FIELDS:
            diagnostics[key] = "[redacted]"
        elif key in ALLOWED_DIAGNOSTICS:
            diagnostics[key] = value
    return diagnostics


def execute_action(action_id: str, incident: dict[str, Any]) -> dict[str, Any]:
    """Produce the deliverable for the chosen action, plus a leak check."""
    raw_log = incident.get("raw_log", {})
    if action_id == "publish_redacted_summary":
        artifact = {
            "service": incident.get("service"),
            "status": incident.get("status"),
            "summary": incident.get("summary"),
            "diagnostics": redact(raw_log),
            "next_update": incident.get("next_update", "15 minutes"),
        }
        return {
            "action_id": action_id,
            "channel": "external",
            "artifact": artifact,
            "leak_check": _leak_check(artifact, raw_log),
        }
    if action_id == "hold_external_update":
        return {
            "action_id": action_id,
            "channel": "internal-only",
            "artifact": {
                "external": None,
                "internal_note": "Holding external updates until the facts are verified.",
                "internal_detail_available": bool(raw_log),
            },
            "leak_check": {"sent_external": False, "leaked": [], "safe": True},
        }
    if action_id == "publish_raw_log":
        return {
            "action_id": action_id,
            "channel": "blocked",
            "artifact": None,
            "leak_check": {"sent_external": False, "leaked": [], "safe": True},
            "note": "Forbidden by the deontic gate; nothing is sent.",
        }
    return {"action_id": action_id, "channel": "none", "artifact": None}


def _sensitive_values(raw_log: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key, value in raw_log.items():
        if key in RESTRICTED_FIELDS and isinstance(value, str):
            values.append(value)
    return values


def _leak_check(artifact: dict[str, Any], raw_log: dict[str, Any]) -> dict[str, Any]:
    import json

    dumped = json.dumps(artifact)
    leaked = [value for value in _sensitive_values(raw_log) if value and value in dumped]
    return {"sent_external": True, "leaked": leaked, "safe": not leaked}

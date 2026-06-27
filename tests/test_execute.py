"""Executing the recommended action produces a safe deliverable, verified."""

import json

from goal_chainer.execute import default_incident, execute_action


def test_redacted_summary_removes_every_sensitive_value():
    incident = default_incident()
    raw = incident["raw_log"]
    result = execute_action("publish_redacted_summary", incident)

    dumped = json.dumps(result["artifact"])
    # None of the actual sensitive values survive into what gets sent.
    for value in (raw["customer_email"], raw["order_id"], raw["access_token"], raw["stack_trace"]):
        assert value not in dumped
    # The operational diagnostic that helps responders is kept.
    assert result["artifact"]["diagnostics"]["error_code"] == "PAYMENT_TIMEOUT"
    assert result["leak_check"]["safe"] is True
    assert result["leak_check"]["leaked"] == []


def test_hold_sends_nothing_external():
    result = execute_action("hold_external_update", default_incident())
    assert result["channel"] == "internal-only"
    assert result["artifact"]["external"] is None
    assert result["leak_check"]["sent_external"] is False


def test_forbidden_action_produces_no_artifact():
    result = execute_action("publish_raw_log", default_incident())
    assert result["channel"] == "blocked"
    assert result["artifact"] is None

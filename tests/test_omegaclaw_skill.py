import json

from goal_chainer.omegaclaw_skill import goalchainer_decision, run_skill


REQUEST = """
Checkout is down. Engineering wants to paste raw logs into the incident room.
Support says the logs may include customer emails, order IDs, and request payloads.
"""


def test_decision_skill_returns_recommended_action():
    payload = run_skill("goalchainer-decision", REQUEST)

    assert payload["skill"] == "goalchainer-decision"
    assert payload["release_plan"]["selected_action"] == "publish_redacted_summary"
    assert payload["release_plan"]["blocked_action"]["action_id"] == "publish_raw_log"
    assert "raw logs" in payload["release_plan"]["keep_restricted"]


def test_py_call_wrapper_returns_json_string():
    payload = json.loads(goalchainer_decision(REQUEST))

    assert payload["skill"] == "goalchainer-decision"
    assert payload["scenario"]["match"]["service_outage"]
    assert any(decision["status"] == "recommended" for decision in payload["decisions"])

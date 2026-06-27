from goal_chainer.evidence import extract_evidence
from goal_chainer.metta_reasoner import reason_over_hyperbase


PII_REQUEST = """
Checkout is down. Engineering wants to paste raw logs into the incident room.
Support says the logs may include customer emails, order IDs, and request payloads.
"""

PUBLIC_REQUEST = """
The outage is resolved. There is no sensitive data in this status, it is safe to
share publicly with engineering and support.
"""


def _evidence_by_action(request: str) -> dict[str, dict]:
    result = reason_over_hyperbase((), extract_evidence(request))
    assert result["source"] == "omega-core-lib-nal-native-metta"
    assert result["execution"]["mode"] == "native-metta"
    assert result["engine"] == "nal"
    assert all(output["stdout"] for output in result["raw_outputs"])
    return {item["action_id"]: item for item in result["action_evidence"]}


def test_pii_request_forbids_raw_log_through_native_nal():
    evidence = _evidence_by_action(PII_REQUEST)

    assert evidence["publish_raw_log"]["deontic"] == "forbidden"
    assert evidence["publish_raw_log"]["expectation"] >= 0.6
    assert evidence["publish_redacted_summary"]["deontic"] == "acceptable"
    assert evidence["publish_redacted_summary"]["strength"] > 0.8


def test_public_request_flips_raw_log_to_acceptable():
    evidence = _evidence_by_action(PUBLIC_REQUEST)

    # Same code, different request: the forbidden status is gone because the risk
    # grounding dropped, so the native forbidden expectation no longer crosses the
    # threshold and the action reads as acceptable instead.
    assert evidence["publish_raw_log"]["deontic"] == "acceptable"
    assert evidence["publish_raw_log"]["strength"] > 0.5

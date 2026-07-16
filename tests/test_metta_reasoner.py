from goal_chainer.evidence import extract_evidence
from goal_chainer.evidence_chainer import chainer_metta_dir
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
    assert result["source"] == "omega-core-petta-lib-deontic-pettachainer"
    assert result["execution"]["mode"] == "petta"
    assert result["execution"]["backward_premise_prefilter"] is True
    assert result["execution"]["pettachainer_path"] == str(chainer_metta_dir().parents[1])
    assert "lib_deontic" in result["engine"]
    # The deontic verdict came from the real engine's conclusion set.
    assert result["deontic_conclusions"]
    return {item["action_id"]: item for item in result["action_evidence"]}


def test_pii_request_forbids_raw_log_through_lib_deontic():
    evidence = _evidence_by_action(PII_REQUEST)

    assert evidence["publish_raw_log"]["deontic"] == "forbidden"
    assert evidence["publish_redacted_summary"]["deontic"] == "obligated"
    # NAL graded the redacted summary as strongly acceptable.
    assert evidence["publish_redacted_summary"]["strength"] > 0.8


def test_public_request_flips_raw_log_to_permitted():
    evidence = _evidence_by_action(PUBLIC_REQUEST)

    # Same code, different request: lib_deontic no longer forbids the raw log
    # because the risk fact is absent from the projected theory.
    assert evidence["publish_raw_log"]["deontic"] == "permitted"
    assert evidence["publish_raw_log"]["strength"] > 0.5

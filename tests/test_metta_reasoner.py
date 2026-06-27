from goal_chainer.hyperbase import incident_propositions
from goal_chainer.metta_reasoner import reason_over_hyperbase


REQUEST = """
Checkout is down. Engineering wants to paste raw logs into the incident room.
Support says the logs may include customer emails, order IDs, and request payloads.
"""


def test_hyperbase_propositions_run_through_native_nal():
    result = reason_over_hyperbase(incident_propositions(REQUEST))
    evidence = {item["action_id"]: item for item in result["action_evidence"]}

    assert result["source"] == "omega-core-lib-nal-native-metta"
    assert result["execution"]["mode"] == "native-metta"
    assert result["engine"] == "nal"
    assert evidence["publish_raw_log"]["strength"] == 0.02
    assert evidence["publish_raw_log"]["confidence"] > 0.9
    assert evidence["publish_redacted_summary"]["strength"] > 0.9
    assert evidence["hold_external_update"]["strength"] == 0.92
    assert any("revision" in query["id"] for query in result["queries"])
    assert all(output["stdout"] for output in result["raw_outputs"])

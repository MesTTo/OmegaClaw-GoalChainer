from goal_chainer.hyperbase import build_hyperbase_packet, incident_propositions, restricted_items


REQUEST = """
Checkout is down. Engineering wants to paste raw logs into the incident room.
Support says the logs may include customer emails, order IDs, and request payloads.
"""


def test_restricted_items_preserve_release_plan_artifacts():
    assert restricted_items(REQUEST) == [
        "customer emails",
        "order IDs",
        "request payloads",
        "raw logs",
    ]


def test_incident_propositions_emit_hyperbase_tree_and_facts():
    propositions = incident_propositions(REQUEST)
    first = propositions[0]

    assert first.sentence == "Raw incident logs contain customer emails."
    assert first.edge == "(contains/Pv.so raw_incident_logs/Cc customer_emails/Cc)"
    assert any('(hb tree incident-pii-1 (sh (tag P v so ()) "contains"' in fact for fact in first.facts)
    assert "(hb role kind incident-pii-1 0 s subject)" in first.facts
    assert "(hb role kind incident-pii-1 1 o object)" in first.facts
    assert all("contain raw logs" not in proposition.sentence for proposition in propositions)


def test_hyperbase_packet_contains_metta_program_and_contract():
    packet = build_hyperbase_packet(REQUEST)

    assert packet["contract"]["purpose"] == "structured propositions that HyperBase can translate into SH trees"
    assert "native MeTTa/NAL reasoner" in packet["structured_english_prompt"]
    assert "Holding the external update protects privacy." in packet["structured_english"]
    assert packet["propositions"][0]["id"] == "incident-pii-1"
    assert packet["metta_program"][0].startswith("(hb edge incident-pii-1")
    assert packet["reasoner"]["source"] == "omega-core-petta-lib-deontic-lib-nal"
    assert packet["reasoner"]["execution"]["mode"] == "petta"
    assert {item["action_id"] for item in packet["reasoner"]["action_evidence"]} == {
        "publish_raw_log",
        "publish_redacted_summary",
        "hold_external_update",
    }

import json

import pytest

from goal_chainer.omegaclaw_skill import goalchainer_decision, goalchainer_ontology_context, run_skill


REQUEST = """
Checkout is down. Engineering wants to paste raw logs into the incident room.
Support says the logs may include customer emails, order IDs, and request payloads.
"""


@pytest.fixture(autouse=True)
def colore_fixture(tmp_path, monkeypatch):
    fixture = tmp_path / "data-colore.metta"
    fixture.write_text(
        "\n".join(
            [
                '(colore module timepoints/lp_ordering "http://example/lp_ordering.clif")',
                "(colore axiom timepoints/lp_ordering a1 horn (forall ($x $y $z) (if (and (before $x $y) (before $y $z)) (before $x $z))))",
                "(colore pred timepoints/lp_ordering before 2)",
                '(colore module kinship/definitions/hasGrandchild "http://example/hasGrandchild.clif")',
                "(colore axiom kinship/definitions/hasGrandchild HGC-1 definition (forall ($x $z) (iff (hasGrandchild $x $z) (exists ($y) (and (hasChild $x $y) (hasChild $y $z))))))",
                '(colore gloss kinship/definitions/hasGrandchild HGC-1 "A person has a grandchild if their child has a child.")',
                '(colore module kinship/definitions/hasSibling "http://example/hasSibling.clif")',
                "(colore axiom kinship/definitions/hasSibling HS-1 definition (forall ($x $y) (iff (hasSibling $x $y) (exists ($z) (and (hasChild $z $x) (hasChild $z $y))))))",
            ]
        )
    )
    monkeypatch.setenv("GOALCHAINER_COLORE_FIXTURE", str(fixture))


def test_decision_skill_returns_recommended_action():
    payload = run_skill("goalchainer-decision", REQUEST)

    assert payload["skill"] == "goalchainer-decision"
    assert payload["release_plan"]["selected_action"] == "publish_redacted_summary"
    assert payload["release_plan"]["blocked_action"]["action_id"] == "publish_raw_log"
    assert "raw logs" in payload["release_plan"]["keep_restricted"]
    assert payload["ontology"]["source_available"] is True
    assert payload["hyperbase"]["propositions"][0]["edge"].startswith("(contains/Pv.so")


def test_py_call_wrapper_returns_json_string():
    payload = json.loads(goalchainer_decision(REQUEST))

    assert payload["skill"] == "goalchainer-decision"
    assert payload["scenario"]["match"]["service_outage"]
    assert any(decision["status"] == "recommended" for decision in payload["decisions"])


def test_ontology_context_skill_returns_colore_and_hyperbase_packet():
    payload = run_skill("goalchainer-ontology-context", REQUEST)

    assert payload["skill"] == "goalchainer-ontology-context"
    assert payload["ontology"]["source_available"] is True
    assert payload["ontology"]["module_count"] == 3
    assert any(rule["id"] == "time-before-transitivity" for rule in payload["ontology"]["projection_rules"])
    assert payload["hyperbase"]["propositions"][0]["tree"].startswith("(sh (tag P v so ())")


def test_ontology_py_call_wrapper_returns_json_string():
    payload = json.loads(goalchainer_ontology_context(REQUEST))

    assert payload["skill"] == "goalchainer-ontology-context"
    assert payload["hyperbase"]["contract"]["rules"]

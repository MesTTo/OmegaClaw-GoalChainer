from types import SimpleNamespace

from goal_chainer.petta_bridge import PeTTaChainerReasoner, ScenarioReasoner, parse_stv
from goal_chainer.scenarios import incident_response_scenario


def test_parse_stv_from_petta_projection():
    text = "(: (generated-context) (Fly tweety) (STV 0.009500000000000008 0.99))"

    assert parse_stv(text) == (0.009500000000000008, 0.99)


def test_scenario_reasoner_uses_explicit_scenario_scores():
    action = incident_response_scenario().actions[0]

    projection = ScenarioReasoner().project(action)

    assert projection.strength == action.default_strength
    assert projection.confidence == action.default_confidence
    assert projection.source == "scenario-explicit"


def test_pettachainer_reasoner_enables_backward_premise_prefilter():
    calls = []

    class FakeChainer:
        def set_backward_premise_prefilter(self, enabled):
            calls.append(("prefilter", enabled))

        def add_atoms_no_check(self, atoms):
            calls.append(("add", tuple(atoms)))

        def contextual_query(self, query, *, steps, timeout_sec):
            calls.append(("query", query, steps, timeout_sec))
            return SimpleNamespace(
                projection="(: (generated-context) (Acceptable safe) (STV 0.8 0.9))",
                proofs=("(: source (Acceptable safe) (STV 0.8 0.9))",),
            )

    action = incident_response_scenario().actions[0]
    reasoner = object.__new__(PeTTaChainerReasoner)
    reasoner.quiet = False
    reasoner._chainer_cls = FakeChainer

    projection = reasoner.project(action)

    assert calls == [
        ("prefilter", True),
        ("add", action.evidence_atoms),
        ("query", action.evidence_query, 20, 0),
    ]
    assert projection.strength == 0.8
    assert projection.confidence == 0.9

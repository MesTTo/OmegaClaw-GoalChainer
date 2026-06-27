from goal_chainer.petta_bridge import ScenarioReasoner, parse_stv
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

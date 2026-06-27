from goal_chainer.petta_bridge import ScenarioReasoner
from goal_chainer.scenarios import incident_response_scenario
from goal_chainer.scoring import DecisionEngine


def test_incident_scenario_recommends_redacted_summary():
    decisions = DecisionEngine(ScenarioReasoner()).rank(incident_response_scenario())

    assert decisions[0].action_id == "publish_redacted_summary"
    assert decisions[0].status == "recommended"
    assert decisions[0].norm_status == "obligated"


def test_raw_log_is_blocked_by_privacy_norm():
    decisions = DecisionEngine(ScenarioReasoner()).rank(incident_response_scenario())
    by_id = {decision.action_id: decision for decision in decisions}

    raw_log = by_id["publish_raw_log"]

    assert raw_log.status == "blocked"
    assert raw_log.score == -1.0
    assert raw_log.norm_status == "forbidden"


def test_hold_update_keeps_privacy_but_misses_collective_requirements():
    decisions = DecisionEngine(ScenarioReasoner()).rank(incident_response_scenario())
    hold = {decision.action_id: decision for decision in decisions}["hold_external_update"]

    assert hold.individual_score == 1.0
    assert hold.collective_score == 0.0
    assert set(hold.missing_required_goals) == {"restore_service", "coordinate_team"}

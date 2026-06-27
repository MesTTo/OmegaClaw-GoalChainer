"""Unit tests for the scoring math, with the deontic status supplied directly."""

from goal_chainer.models import CandidateAction, EvidenceProjection, GoalScenario
from goal_chainer.scenarios import incident_goals
from goal_chainer.scoring import DecisionEngine


class StubReasoner:
    """Return a fixed evidence projection per action, so scoring is tested alone."""

    def __init__(self, table: dict[str, EvidenceProjection]) -> None:
        self.table = table

    def project(self, action: CandidateAction) -> EvidenceProjection:
        return self.table[action.id]


def _action(action_id: str, satisfies: tuple[str, ...]) -> CandidateAction:
    return CandidateAction(
        id=action_id,
        label=action_id,
        description="",
        satisfies=satisfies,
        evidence_query="",
        evidence_atoms=(),
        default_strength=0.5,
    )


def _decide(action: CandidateAction, evidence: EvidenceProjection):
    scenario = GoalScenario("t", incident_goals(), (), (action,))
    return DecisionEngine(StubReasoner({action.id: evidence})).rank(scenario)[0]


def test_forbidden_action_is_blocked():
    evidence = EvidenceProjection(
        strength=0.07, confidence=0.73, source="x", deontic="forbidden", expectation=0.81
    )
    decision = _decide(_action("publish_raw_log", ("restore_service", "coordinate_team")), evidence)

    assert decision.status == "blocked"
    assert decision.score == -1.0
    assert decision.norm_status == "forbidden"


def test_acceptable_action_covering_all_goals_is_recommended():
    evidence = EvidenceProjection(
        strength=0.85, confidence=0.81, source="x", deontic="acceptable", expectation=0.78
    )
    action = _action(
        "publish_redacted_summary", ("preserve_privacy", "restore_service", "coordinate_team")
    )
    decision = _decide(action, evidence)

    assert decision.status == "recommended"
    assert decision.norm_status == "acceptable"


def test_acceptable_action_missing_required_goals_is_not_recommended():
    evidence = EvidenceProjection(
        strength=0.83, confidence=0.62, source="x", deontic="acceptable", expectation=0.70
    )
    decision = _decide(_action("hold_external_update", ("preserve_privacy",)), evidence)

    assert decision.status in {"weak", "candidate"}
    assert decision.individual_score == 1.0
    assert decision.collective_score == 0.0
    assert set(decision.missing_required_goals) == {"restore_service", "coordinate_team"}

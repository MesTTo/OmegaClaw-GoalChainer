"""Rank actions by goal coverage, derived deontic status, and native evidence."""

from __future__ import annotations

from .models import CandidateAction, Decision, EvidenceProjection, Goal, GoalScenario

BLOCKING_STATUSES = {"forbidden", "conflict"}


class DecisionEngine:
    def __init__(self, reasoner) -> None:
        self.reasoner = reasoner

    def rank(self, scenario: GoalScenario) -> list[Decision]:
        decisions = [self.evaluate_action(scenario, action) for action in scenario.actions]
        return sorted(decisions, key=lambda item: item.score, reverse=True)

    def evaluate_action(self, scenario: GoalScenario, action: CandidateAction) -> Decision:
        evidence = self.reasoner.project(action)
        goal_scores = _goal_scores(scenario.goals, action.satisfies)
        deontic = evidence.deontic
        missing_required = _missing_required_goals(scenario.goals, action.satisfies)

        warnings: list[str] = []
        if missing_required:
            warnings.append("missing required goals: " + ", ".join(missing_required))
        if deontic in BLOCKING_STATUSES:
            warnings.append(f"native deontic status: {deontic}")

        score = _combined_score(
            goal_score=goal_scores["all"],
            individual_score=goal_scores["individual"],
            collective_score=goal_scores["collective"],
            evidence=evidence,
            deontic=deontic,
        )
        status = _decision_status(deontic, score, missing_required)

        return Decision(
            action_id=action.id,
            label=action.label,
            status=status,
            score=score,
            goal_score=goal_scores["all"],
            individual_score=goal_scores["individual"],
            collective_score=goal_scores["collective"],
            evidence=evidence,
            norm_status=deontic,
            norm_reasons=(f"expectation={evidence.expectation:.3f}",),
            satisfied_goals=tuple(action.satisfies),
            missing_required_goals=tuple(missing_required),
            warnings=tuple(warnings),
            metadata={"deontic_expectation": f"{evidence.expectation:.6f}"},
        )


def _goal_scores(goals: tuple[Goal, ...], satisfied: tuple[str, ...]) -> dict[str, float]:
    satisfied_set = set(satisfied)
    all_score = _weighted_coverage(goals, satisfied_set)
    individual = tuple(goal for goal in goals if goal.kind == "individual")
    collective = tuple(goal for goal in goals if goal.kind == "collective")
    return {
        "all": all_score,
        "individual": _weighted_coverage(individual, satisfied_set),
        "collective": _weighted_coverage(collective, satisfied_set),
    }


def _weighted_coverage(goals: tuple[Goal, ...], satisfied: set[str]) -> float:
    total = sum(goal.weight for goal in goals)
    if total == 0:
        return 0.0
    covered = sum(goal.weight for goal in goals if goal.id in satisfied)
    return covered / total


def _missing_required_goals(goals: tuple[Goal, ...], satisfied: tuple[str, ...]) -> list[str]:
    satisfied_set = set(satisfied)
    return [goal.id for goal in goals if goal.required and goal.id not in satisfied_set]


def _combined_score(
    *,
    goal_score: float,
    individual_score: float,
    collective_score: float,
    evidence: EvidenceProjection,
    deontic: str,
) -> float:
    if deontic in BLOCKING_STATUSES:
        return -1.0
    # lib_deontic obligates the action it positively requires (strong endorsement);
    # a merely permitted action gets none.
    deontic_bonus = 0.1 if deontic == "obligated" else 0.0
    evidence_score = evidence.strength * evidence.confidence
    fairness_floor = min(individual_score, collective_score)
    return (0.42 * goal_score) + (0.38 * evidence_score) + (0.12 * fairness_floor) + deontic_bonus


def _decision_status(deontic: str, score: float, missing_required: list[str]) -> str:
    if deontic in BLOCKING_STATUSES:
        return "blocked"
    if score >= 0.72 and not missing_required:
        return "recommended"
    if score >= 0.5:
        return "candidate"
    return "weak"

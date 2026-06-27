"""Rank actions by goal coverage, derived deontic status, and native evidence."""

from __future__ import annotations

from .models import CandidateAction, Decision, EvidenceProjection, Goal, GoalScenario

BLOCKING_STATUSES = {"forbidden", "conflict"}


class DecisionEngine:
    def __init__(self, reasoner, motivation_scores: dict[str, float] | None = None) -> None:
        self.reasoner = reasoner
        # When MetaMo motivation scores are supplied, they replace the static goal
        # coverage as the goal-preference term (the individual/collective consensus).
        # Without them, the engine behaves exactly as before (offline default).
        self.motivation_scores = motivation_scores or {}

    def rank(self, scenario: GoalScenario) -> list[Decision]:
        motivation = _normalized_motivation(scenario, self.motivation_scores)
        native = self._native_decisions(scenario, motivation)
        decisions = [
            self.evaluate_action(scenario, action, motivation.get(action.id), native.get(action.id))
            for action in scenario.actions
        ]
        return sorted(decisions, key=lambda item: item.score, reverse=True)

    def _native_decisions(
        self, scenario: GoalScenario, motivation: dict[str, float]
    ) -> dict[str, tuple[float, str]]:
        """Compute the full verdict (score and status) as Prolog on PeTTa for the
        motivation path. Empty if MetaMo or the runtime is unavailable."""
        if not motivation:
            return {}
        from . import native_score

        if not native_score.available():
            return {}
        rows = []
        for action in scenario.actions:
            if action.id not in motivation:
                return {}
            evidence = self.reasoner.project(action)
            has_missing = 1 if _missing_required_goals(scenario.goals, action.satisfies) else 0
            rows.append(
                (evidence.deontic, evidence.strength, evidence.confidence, motivation[action.id], has_missing)
            )
        try:
            verdicts = native_score.decide_actions(rows)
        except Exception:
            return {}
        return {action.id: verdict for action, verdict in zip(scenario.actions, verdicts)}

    def evaluate_action(
        self,
        scenario: GoalScenario,
        action: CandidateAction,
        motivation: float | None = None,
        native: tuple[float, str] | None = None,
    ) -> Decision:
        evidence = self.reasoner.project(action)
        goal_scores = _goal_scores(scenario.goals, action.satisfies)
        deontic = evidence.deontic
        missing_required = _missing_required_goals(scenario.goals, action.satisfies)

        warnings: list[str] = []
        if missing_required:
            warnings.append("missing required goals: " + ", ".join(missing_required))
        if deontic in BLOCKING_STATUSES:
            warnings.append(f"native deontic status: {deontic}")

        if native is not None:
            score, status = native
        else:
            score = _combined_score(
                goal_score=goal_scores["all"],
                individual_score=goal_scores["individual"],
                collective_score=goal_scores["collective"],
                evidence=evidence,
                deontic=deontic,
                motivation=motivation,
            )
            status = _decision_status(deontic, score, missing_required)
        metadata = {"deontic_expectation": f"{evidence.expectation:.6f}"}
        if motivation is not None:
            metadata["motivation"] = f"{motivation:.4f}"
        if native is not None:
            metadata["score_engine"] = "prolog-on-petta"

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
            metadata=metadata,
        )


def _normalized_motivation(
    scenario: GoalScenario, motivation_scores: dict[str, float]
) -> dict[str, float]:
    """Min-max normalize the MetaMo consensus scores to [0,1] across the actions."""
    values = [motivation_scores[a.id] for a in scenario.actions if a.id in motivation_scores]
    if len(values) < len(scenario.actions) or not values:
        return {}
    low, high = min(values), max(values)
    span = high - low
    return {
        a.id: ((motivation_scores[a.id] - low) / span if span else 1.0)
        for a in scenario.actions
    }


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
    motivation: float | None = None,
) -> float:
    if deontic in BLOCKING_STATUSES:
        return -1.0
    # lib_deontic obligates the action it positively requires (strong endorsement);
    # a merely permitted action gets none.
    deontic_bonus = 0.1 if deontic == "obligated" else 0.0
    evidence_score = evidence.strength * evidence.confidence
    if motivation is not None:
        # MetaMo's consensus already folds goal coverage and the individual/collective
        # fairness penalty into one score, so it takes the goal + fairness weight.
        return (0.54 * motivation) + (0.38 * evidence_score) + deontic_bonus
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

"""Purpose: hand a compiled review to the MeTTa ranking policy and read its typed answer back as records and plain-English reasons.

The policy itself is `policy/ranking.metta`: the five steps of the paper's section 9.3, the
section 13.2 escalation triggers, the five dispositions and the licensed authority ceiling, with
a motivational step for a domain that declares needs, whose snapshot this module hands it too.
This module builds the policy's input as atoms from validated names and numbers, and turns the
typed reasons it answers into the sentences the review record and the CLI show. Nothing here
decides anything, a candidate's deontic status included: the policy answers it from the status
rule the incident decision and the scorer share.

    propose        one candidate survives and nothing calls for judgment;
    escalate       a section 13.2 trigger holds;
    blocked        steps 1 and 2 removed every candidate, each removal named;
    hold           in a domain with needs, the motivational step removed every candidate that
                   steps 1 and 2 left, since none could reduce a need or serve another goal;
    no-candidates  the theory made no action a candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, get_args

from ..deontic_engine import DEONTIC_STATUSES
from ..runtime.budget import RunBudget
from .derived import Candidate, DerivedReview
from .errors import RelevanceError
from .motivation import MotivationSnapshot
from .policy import body, constant, evaluate, is_nothing, items, symbol, term, text

Disposition = Literal["propose", "escalate", "blocked", "hold", "no-candidates"]
DISPOSITIONS: frozenset[str] = frozenset(get_args(Disposition))


# A value whose unknowns leave it anywhere from low to high; a known value is a point.
# am[implements a-v2m-drive-paths-1019@65a7d5] am[rests-on c-v2m-interval-machinery-1019@cd9844]
@dataclass(frozen=True)
class Interval:
    low: float
    high: float

    def to_dict(self) -> dict[str, float]:
        return {"low": round(self.low, 6), "high": round(self.high, 6)}


# am[implements a-rel-ranking-1016@334372]
@dataclass(frozen=True)
class Elimination:
    action: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"action": self.action, "reason": self.reason}


# am[implements a-rel-ranking-1016@334372]
@dataclass(frozen=True)
class RankingStep:
    """One stage of the sequence: who survived it and what it removed."""

    name: str
    survivors: tuple[str, ...]
    eliminated: tuple[Elimination, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "survivors": list(self.survivors),
            "eliminated": [item.to_dict() for item in self.eliminated],
        }


# am[implements a-rel-ranking-1016@334372]
@dataclass(frozen=True)
class GoalPath:
    """One action's contribution through one goal, carrying the priority and who declared it."""

    goal: str
    kind: str
    priority: float
    priority_source: str
    band: str
    value: float

    def to_dict(self) -> dict[str, object]:
        return {
            "goal": self.goal,
            "kind": self.kind,
            "priority": self.priority,
            "priority_source": self.priority_source,
            "band": self.band,
            "value": round(self.value, 6),
        }


# A goal a need regulates, valued as the goal's priority times the action's reduction of the
# need's urgency, an interval wherever the need's level or the action's change is unknown.
# am[implements a-v2m-drive-paths-1019@65a7d5]
@dataclass(frozen=True)
class NeedPath:
    goal: str
    kind: str
    priority: float
    priority_source: str
    need: str
    value: Interval

    def to_dict(self) -> dict[str, object]:
        return {
            "goal": self.goal,
            "kind": self.kind,
            "priority": self.priority,
            "priority_source": self.priority_source,
            "need": self.need,
            "value": self.value.to_dict(),
        }


# Why a review of a domain with needs holds: the needs whose levels lie in their bands, and those
# outside them through which no remaining candidate's path is worth more than 0, because none
# reduces the need or the goal it regulates has priority 0.
# am[implements a-v2m-hold-1019@be4f47] am[addresses i-v2r-priority-zero-unserved-1020]
@dataclass(frozen=True)
class Hold:
    satisfied: tuple[str, ...]
    unreduced: tuple[str, ...]

    def to_dict(self) -> dict[str, list[str]]:
        return {"satisfied": list(self.satisfied), "unserved": list(self.unreduced)}


# am[implements a-rel-ranking-1016@334372] am[addresses i-rel-authority-1016@ab7bf8]
@dataclass(frozen=True)
class AuthorityLimit:
    """An estimate whose class licenses less than the action's own rung, and so lowered it."""

    basis: str
    estimator: str
    ceiling: str

    def to_dict(self) -> dict[str, str]:
        return {"basis": self.basis, "estimator": self.estimator, "ceiling": self.ceiling}


# am[implements a-rel-ranking-1016@334372] am[addresses i-rel-authority-1016@ab7bf8]
@dataclass(frozen=True)
class Appraisal:
    """Everything the policy computed about one candidate from that candidate alone."""

    action: str
    paths: tuple[GoalPath, ...]
    need_paths: tuple[NeedPath, ...]
    aggregates: dict[str, Interval]
    local: dict[str, Interval]
    hive: dict[str, Interval]
    projection: float
    unknown_dimensions: tuple[str, ...]
    action_authority_ceiling: str
    licensed_authority_ceiling: str
    authority_limits: tuple[AuthorityLimit, ...]
    carrying: GoalPath | NeedPath | None
    """The goal path whose priority carries most of this action's value (section 9.5)."""


# am[implements a-rel-ranking-1016@334372]
@dataclass(frozen=True)
class Ranking:
    review: DerivedReview
    disposition: Disposition
    steps: tuple[RankingStep, ...]
    appraisals: dict[str, Appraisal]
    selected: Candidate | None
    decided_at: str | None
    escalation_reasons: tuple[str, ...]
    contested: tuple[str, ...]
    blockers: tuple[Elimination, ...]
    motive_tension: tuple[str, str] | None
    unserved_required: tuple[str, ...]
    display_order: tuple[tuple[str, float], ...]
    standing: dict[str, str]
    """Each candidate's deontic status by the shared rule, one of deontic_engine's
    DEONTIC_STATUSES."""
    hold: Hold | None = None


# am[implements a-rel-ranking-1016@334372] am[implements a-rel-metta-policy-1016@fdaa20]
# am[implements a-v2m-drive-paths-1019@65a7d5]
def rank(review: DerivedReview, budget: RunBudget, motivation: MotivationSnapshot | None = None) -> Ranking:
    """Run the MeTTa ranking policy over the review, charged to what is left of its budget; a
    review of a domain with needs reads `motivation`, its snapshot at the review's instant."""

    return read_ranking(review, evaluate("gc-relevance-rank", policy_input(review, motivation), budget=budget))


# A readset signal whose readings are in dispute, conflicted or with a contested reading, is
# conflicting evidence; the authority ceilings read only the supporting readings' classes.
# am[implements a-rel-ranking-1016@334372] am[implements a-rel-metta-policy-1016@fdaa20]
# am[implements a-rel-rr-p-escalation-1018@86a7bb] am[rests-on c6bd00cd@8dffaf]
def policy_input(review: DerivedReview, motivation: MotivationSnapshot | None = None) -> Any:
    """The RankInput atom ranking.metta reads, with every value a string, number or boolean."""

    domain = review.domain
    return term(
        "RankInput",
        term("Goals", items(term("Goal", g.id, g.kind, float(g.weight), g.priority_source) for g in domain.goals)),
        term("Dimensions", items(domain.dimension_ids)),
        term("Tiers", items(term("Tier", t.id, t.rank) for t in domain.authorities)),
        term("Ceilings", items(term("Ceiling", estimator, tier) for estimator, tier in domain.estimator_ceilings)),
        term("Required", items(review.required_goals)),
        term("Obligations", items(review.obligations)),
        term("OtherDilemmas", items(range(len(review.other_dilemmas)))),
        term("Conflicted", items(name for name in sorted(review.readset) if review.readings[name].disputed)),
        term(
            "Support",
            items(
                term("Support", name, items(r.estimator for r in reading.support))
                for name, reading in sorted(review.readings.items())
                if reading.state in ("detected", "refuted")
            ),
        ),
        term("Candidates", items(_candidate(c) for c in review.candidates)),
        term("Motivation", _motivation(review, motivation)),
    )


# A domain without needs hands None, so its ranking has no motivational step. With needs, the
# snapshot gives each regulated goal's need, each need's level state and band distance, and each
# candidate's reduction interval of each need with the classes it rests on: every observation
# agreeing on the level, and the change's class once the change is known.
# am[implements a-v2m-drive-paths-1019@65a7d5] am[implements a-v2m-need-authority-1019@52deb8]
def _motivation(review: DerivedReview, snapshot: MotivationSnapshot | None) -> Any:
    needs = review.domain.needs
    if not needs:
        return constant("None")
    if snapshot is None:
        raise RelevanceError("invalid-motivation", f"{review.domain.source} declares needs, so its ranking needs their snapshot")
    levels = {level.need: level for level in snapshot.levels}
    return term(
        "Regulation",
        items(term("Regulates", need.id, need.goal) for need in needs),
        items(term("NeedState", need.id, levels[need.id].state,
                   constant("None") if levels[need.id].distance is None else levels[need.id].distance)
              for need in needs),
        items(
            term("Reduction", candidate.id, need.id,
                 term("Interval", snapshot.reduction(candidate.id, need.id).low, snapshot.reduction(candidate.id, need.id).high),
                 items(sorted({estimator for _, estimator in levels[need.id].support}) if levels[need.id].known else ()),
                 items((snapshot.change(candidate.id, need.id).estimator,) if snapshot.change(candidate.id, need.id).known else ()))
            for candidate in review.candidates
            for need in needs
        ),
    )


# am[implements a-rel-ranking-1016@334372]
# am[implements a-rel-status-symbols-1016@0aaea4]
def _candidate(c: Candidate) -> Any:
    return term(
        "Candidate",
        c.id,
        c.action.authority,
        items(constant(mode) for mode in sorted(c.modes)),
        c.dilemma,
        items(term("Effect", q.dimension, q.band, q.estimator) for q in c.profile.quantities),
        items(term("Contrib", x.goal, x.band) for x in c.contributions),
        items(sorted(c.readset)),
    )


# --- reading the policy's answer -------------------------------------------------------------


# Time: linear in the size of the answer.
# am[implements a-rel-ranking-1016@334372]
def read_ranking(review: DerivedReview, answer: Any) -> Ranking:
    """The Ranking a policy answer describes; any shape the policy never answers is engine-output-invalid."""

    try:
        (head, disposition, selected, decided_at, steps, escalations, contested, blockers, tension,
         unserved, appraisals, display, standing, held) = answer
        if symbol(head) != "Ranking" or text(disposition) not in DISPOSITIONS:
            raise ValueError(f"not a ranking: {head!r} {disposition!r}")
        by_id = {c.id: c for c in review.candidates}
        return Ranking(
            review=review,
            disposition=disposition,
            steps=tuple(_step(step) for step in body(steps, "Steps")),
            appraisals={appraisal.action: appraisal for appraisal in map(_appraisal, body(appraisals, "Appraisals"))},
            selected=None if is_nothing(selected) else by_id[text(selected)],
            decided_at=None if is_nothing(decided_at) else text(decided_at),
            escalation_reasons=tuple(_escalation(review, item) for item in body(escalations, "Escalations")),
            contested=tuple(map(text, body(contested, "Contested"))),
            blockers=tuple(_elimination(item) for item in body(blockers, "Blockers")),
            motive_tension=_tension(tension),
            unserved_required=tuple(map(text, body(unserved, "Unserved"))),
            display_order=tuple(_shown(item) for item in body(display, "Display")),
            standing=dict(map(_status, body(standing, "Standing"))),
            hold=_hold(held),
        )
    except (KeyError, ValueError, TypeError, IndexError) as error:
        raise RelevanceError(
            "engine-output-invalid", f"the ranking policy answered an unreadable ranking: {error}"
        ) from error


# am[implements a-rel-ranking-1016@334372]
def _parts(value: Any, head: str, size: int) -> tuple:
    """The arguments of `(HEAD ARGUMENT ...)` with exactly `size` arguments."""

    if not isinstance(value, tuple) or len(value) != size + 1 or symbol(value[0]) != head:
        raise ValueError(f"expected ({head} with {size} arguments), got {value!r}")
    return value[1:]


# am[implements a-rel-ranking-1016@334372]
def _step(step: Any) -> RankingStep:
    name, survivors, removed = _parts(step, "Step", 3)
    return RankingStep(text(name), tuple(map(text, survivors)), tuple(map(_elimination, removed)))


# am[implements a-rel-ranking-1016@334372]
def _elimination(item: Any) -> Elimination:
    action, reason = _parts(item, "Elim", 2)
    return Elimination(text(action), _reason(reason))


# am[implements a-rel-ranking-1016@334372]
def _path(item: Any) -> GoalPath:
    goal, kind, priority, source, band, value = _parts(item, "Path", 6)
    point = _interval(value)
    if point.low != point.high:
        raise ValueError(f"a band path's value must be a point, got {item!r}")
    return GoalPath(text(goal), text(kind), float(priority), text(source), text(band), point.low)


# am[implements a-v2m-drive-paths-1019@65a7d5]
def _need_path(item: Any) -> NeedPath:
    goal, kind, priority, source, need, value = _parts(item, "NeedPath", 6)
    return NeedPath(text(goal), text(kind), float(priority), text(source), text(need), _interval(value))


# A path of either kind, by its constructor.
# am[implements a-v2m-drive-paths-1019@65a7d5]
def _any_path(item: Any) -> GoalPath | NeedPath:
    return _need_path(item) if isinstance(item, tuple) and item and symbol(item[0]) == "NeedPath" else _path(item)


# am[implements a-v2m-drive-paths-1019@65a7d5]
def _interval(item: Any) -> Interval:
    low, high = _parts(item, "Interval", 2)
    if isinstance(low, bool) or isinstance(high, bool) or not float(low) <= float(high):
        raise ValueError(f"not an interval: {item!r}")
    return Interval(float(low), float(high))


# am[implements a-v2m-hold-1019@be4f47]
def _hold(item: Any) -> Hold | None:
    if not isinstance(item, tuple) and symbol(item) == "NoHold":
        return None
    satisfied, unreduced = _parts(item, "Hold", 2)
    return Hold(tuple(map(text, _parts(satisfied, "Satisfied", 1)[0])), tuple(map(text, _parts(unreduced, "Unreduced", 1)[0])))


# am[implements a-rel-ranking-1016@334372]
# am[implements a-rel-aggregation-rules-1017@b47aa6]
def _appraisal(item: Any) -> Appraisal:
    (action, paths, aggregates, motives, projection, unknown, own, licensed, limits,
     carrying) = _parts(item, "Appraisal", 10)
    (by_rule,) = _parts(aggregates, "Aggregates", 1)
    (by_motive,) = _parts(motives, "Motives", 1)
    motive = dict(map(_motive, by_motive))
    read = tuple(map(_any_path, paths))
    return Appraisal(
        action=text(action),
        paths=tuple(path for path in read if isinstance(path, GoalPath)),
        need_paths=tuple(path for path in read if isinstance(path, NeedPath)),
        aggregates=_by_rule(by_rule),
        local=motive["local"],
        hive=motive["hive"],
        projection=float(projection),
        unknown_dimensions=tuple(map(text, unknown)),
        action_authority_ceiling=text(own),
        licensed_authority_ceiling=text(licensed),
        authority_limits=tuple(_limit(limit) for limit in limits),
        carrying=None if is_nothing(carrying) else _any_path(_parts(carrying, "Some", 1)[0]),
    )


# am[implements a-rel-ranking-1016@334372]
# am[implements a-rel-aggregation-rules-1017@b47aa6]
def _by_rule(items: Any) -> dict[str, Interval]:
    """`((By RULE (Interval LOW HIGH)) ...)`, one value per aggregation rule the policy declares."""

    return {text(rule): _interval(value) for rule, value in (_parts(item, "By", 2) for item in items)}


# am[implements a-rel-aggregation-rules-1017@b47aa6]
def _motive(item: Any) -> tuple[str, dict[str, Interval]]:
    name, by_rule = _parts(item, "Motive", 2)
    return text(name), _by_rule(by_rule)


# am[implements a-rel-ranking-1016@334372]
def _limit(item: Any) -> AuthorityLimit:
    kind, name, estimator, tier = _parts(item, "Limit", 4)
    return AuthorityLimit(f"{text(kind)}:{text(name)}", text(estimator), text(tier))


# am[implements a-rel-ranking-1016@334372]
def _tension(tension: Any) -> tuple[str, str] | None:
    if not isinstance(tension, tuple) and symbol(tension) == "NoTension":
        return None
    local, hive = _parts(tension, "Tension", 2)
    return text(local), text(hive)


# am[implements a-rel-ranking-1016@334372]
def _shown(item: Any) -> tuple[str, float]:
    action, value = _parts(item, "Shown", 2)
    return text(action), round(float(value), 6)


# am[implements a-rel-status-answer-1016@c302a1]
def _status(item: Any) -> tuple[str, str]:
    action, status = _parts(item, "For", 2)
    name = symbol(status)
    if name not in DEONTIC_STATUSES:
        raise ValueError(f"expected one of {DEONTIC_STATUSES}, got {status!r}")
    return text(action), name


# am[implements a-rel-ranking-1016@334372]
def _coordinate(item: Any) -> str:
    kind = {"OnGoal": "goal", "OnDimension": "dimension", "OnNeed": "need"}[symbol(item[0])]
    (name,) = _parts(item, symbol(item[0]), 1)
    return f"{kind}:{text(name)}"


# am[implements a-rel-ranking-1016@334372]
def _reason(reason: Any) -> str:
    """The sentence a typed elimination reason stands for."""

    if not isinstance(reason, tuple):
        return {
            "Forbidden": "forbidden by the theory",
            "ObligedAndForbidden": "the theory proves it both obliged and forbidden",
            "PermittedAndForbidden": "the theory proves it both permitted and forbidden",
            "InDilemma": "a duty about it and its opposite both apply and neither prevails",
            "PermissionWithdrawn": "obliged, but the theory withdrew its permission",
            "NoPermission": "the theory grants no permission for it",
            "NotCandidate": "it is not a candidate",
            "Unmotivated": "no goal path could be worth more than 0: every need it moves is satisfied or made worse "
                           "and it serves no other goal",
        }[symbol(reason)]
    head = symbol(reason[0])
    if head == "ObligationInForce":
        (duties,) = _parts(reason, head, 1)
        return f"an obligation is in force: {', '.join(map(text, duties))}"
    if head == "HarmsRequired":
        goal, band = _parts(reason, head, 2)
        return f"pushes the required goal {text(goal)} backwards ({text(band)})"
    if head == "DominatedBy":
        better, coordinates = _parts(reason, head, 2)
        return (
            f"dominated by {text(better)}: at least as good on everything either claims, "
            f"better on {', '.join(map(_coordinate, coordinates))}"
        )
    if head == "MotivesPrefer":
        (better,) = _parts(reason, head, 1)
        return f"both the local and the hive motive prefer {text(better)}"
    if head == "ProjectionLead":
        (leader,) = _parts(reason, head, 1)
        return f"{text(leader)} leads it under every aggregation rule, whatever the unknown effects are"
    raise ValueError(f"unknown elimination reason {head}")


# am[implements a-rel-ranking-1016@334372] am[implements a-rel-rr-p-escalation-1018@86a7bb]
# am[implements a-v2r-undecided-need-named-1020]
def _escalation(review: DerivedReview, reason: Any) -> str:
    """The sentence a typed section 13.2 trigger stands for."""

    if not isinstance(reason, tuple):
        if symbol(reason) == "AllDutiesHarm":
            return "every obliged action pushes a required goal backwards"
        raise ValueError(f"unknown escalation {reason!r}")
    head = symbol(reason[0])
    if head == "EvidenceConflict":
        name = text(_parts(reason, head, 1)[0])
        reading = review.readings[name]
        return f"evidence about {name} conflicts: " + "; ".join(
            f"{r.source} says {r.state.value}" for r in (*reading.support, *reading.contested)
        )
    if head == "OtherDilemma":
        (index,) = _parts(reason, head, 1)
        return f"the theory leaves the duty {review.other_dilemmas[int(index)]} in a dilemma"
    if head == "CandidateConflict":
        action, why = _parts(reason, head, 2)
        return f"{text(action)}: {_reason(why)}"
    if head == "UndischargedDuty":
        action, why = _parts(reason, head, 2)
        return f"{text(action)} is obliged but has no admissible discharge: {_reason(why)}"
    if head == "SeveralDuties":
        (duties,) = _parts(reason, head, 1)
        return (
            f"several obligations are in force at once ({', '.join(map(text, duties))}); "
            "one proposal cannot discharge them all"
        )
    if head == "EstimatorConflict":
        action, dimension, claims = _parts(reason, head, 3)
        rendered = " vs ".join(
            f"{text(dimension)} {text(band)} [{text(estimator)}]"
            for band, estimator in (_parts(claim, "Claim", 2) for claim in claims)
        )
        return f"estimators disagree about {text(action)} {rendered}"
    if head == "AggregationDisagree":
        (selections,) = _parts(reason, head, 1)
        return "the aggregation rules disagree: " + ", ".join(
            f"{text(rule)} selects {text(winner)}" for rule, winner in (_parts(s, "Selects", 2) for s in selections)
        )
    if head == "NotDecisive":
        survivors, rules, slack, needs = _parts(reason, head, 4)
        unknowns = ([f"unknown or conflicting effects on {', '.join(map(text, slack))}"] if slack else []) + (
            [f"the unknown levels or expected changes of {', '.join(map(text, needs))}"] if needs else [])
        return (
            f"the projection is not decisive among {', '.join(map(text, survivors))} under "
            f"{', '.join(map(text, rules))}: "
            + (f"{' and '.join(unknowns)} could reverse the order" if unknowns else "no candidate leads every other, and nothing unknown is left to change that")
        )
    if head == "NeedsUnknown":
        (needs,) = _parts(reason, head, 1)
        return (
            f"no candidate is motivated by what is known, but the levels of {', '.join(map(text, needs))} are "
            "unknown, so the review cannot hold: observe them"
        )
    if head == "NotRobustlyMotivated":
        action, needs = _parts(reason, head, 2)
        unknown = ", ".join(map(text, needs))
        return (
            f"{text(action)} is not better than holding under every aggregation rule"
            + (f", whatever {unknown} turn out to be" if unknown else "")
        )
    raise ValueError(f"unknown escalation {head}")


"""Purpose: define the immutable values exchanged with SNARS: the evidence a caller gives it and
what it answers. Its failures are goal_chainer.errors'."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isclose
from typing import Literal

from .runtime.numbers import finite_float

# Protocol values may pass through decimal text before becoming floats. This
# absolute tolerance accepts ordinary conversion noise while still rejecting an
# opinion whose belief, disbelief, and uncertainty do not form a simplex.
OPINION_SUM_TOLERANCE = 1e-9

GoalKind = Literal["individual", "collective"]
ClockKind = Literal["logical", "real"]
# A condition cut once on an opinion's probability interval [b, b + u] against a threshold
# (snars/truth.metta, sn condition); a route's leaf is that or an open premise.
# am[implements a-rt-ob-session-1017@f1468f] am[rests-on c-integrate-condition-projection-endpoints-1017@364ddb]
ConditionStatus = Literal["Holds", "Fails", "Undecided"]
LeafStatus = Literal["Holds", "Fails", "Undecided", "Open"]
SearchStatus = Literal["Witness", "Incomplete"]


# A number no finite float holds, an integer beyond the float range included, is a ValueError here,
# where float() had raised OverflowError.
# am[implements a-rt-nr-repair-1018@72901e] am[rests-on c-rt-nr-probe-bfd71102-1018@029356]
def _finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number")
    result = finite_float(value)
    if result is None:
        raise ValueError(f"{name} must be finite")
    return result


def _probability(name: str, value: float) -> float:
    result = _finite(name, value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return result


def _nonnegative(name: str, value: float) -> float:
    result = _finite(name, value)
    if result < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return result


def _nonempty(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must be nonempty")
    return value


def _typed_tuple(
    name: str,
    values: tuple[object, ...],
    item_type: type | tuple[type, ...],
) -> tuple:
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be a tuple")
    for value in values:
        if not isinstance(value, item_type):
            item_types = item_type if isinstance(item_type, tuple) else (item_type,)
            expected = " or ".join(candidate.__name__ for candidate in item_types)
            raise TypeError(f"{name} must contain only {expected} values")
    return values


def _string_tuple(name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    _typed_tuple(name, values, str)
    for value in values:
        _nonempty(f"{name} item", value)
    return values


@dataclass(frozen=True)
class SubjectiveOpinion:
    """A binomial Subjective Logic opinion.

    Belief, disbelief, and uncertainty must sum to one within
    ``OPINION_SUM_TOLERANCE``. The projected expectation is ``b + a*u``.
    """

    belief: float
    disbelief: float
    uncertainty: float
    base_rate: float

    def __post_init__(self) -> None:
        for field_name in ("belief", "disbelief", "uncertainty", "base_rate"):
            object.__setattr__(
                self,
                field_name,
                _probability(field_name, getattr(self, field_name)),
            )
        total = self.belief + self.disbelief + self.uncertainty
        if not isclose(
            total,
            1.0,
            rel_tol=0.0,
            abs_tol=OPINION_SUM_TOLERANCE,
        ):
            raise ValueError(
                "belief + disbelief + uncertainty must equal 1 "
                f"within {OPINION_SUM_TOLERANCE:g}"
            )
        if not 0.0 <= self.expectation <= 1.0:
            raise ValueError("opinion expectation must be in [0, 1]")

    @property
    def expectation(self) -> float:
        return self.belief + self.base_rate * self.uncertainty


# What a caller gives SNARS about one statement: units for and against it and, when the caller has
# one, the base rate they are read against. SNARS reads a rate not given as its configured default,
# (sn config default-rate) in snars_library/snars/config.metta, the prior's one home, so no caller
# keeps a copy of it. A copy would disagree with the library once either changed, and because SNARS
# keeps the newest unit's rate, the prior would then depend on the order evidence was fused.
# am[implements a-ev-br-evidence-type-1017@81ce8a] am[addresses i-ev-base-rate-two-homes-1017@6a1343]
# am[rests-on c-ev-snars-rate-last-writer-1017@8b6dde]
@dataclass(frozen=True)
class Evidence:
    """Evidence given to SNARS: nonnegative positive and negative units and a base rate in [0, 1],
    or None to leave the rate to SNARS's configured default."""

    positive: float
    negative: float
    base_rate: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "positive", _nonnegative("positive", self.positive))
        object.__setattr__(self, "negative", _nonnegative("negative", self.negative))
        if self.base_rate is not None:
            object.__setattr__(self, "base_rate", _probability("base_rate", self.base_rate))


# A statement's evidence as SNARS answers it, (evidence P N RATE), so it always carries the rate
# SNARS applied. Given back to SNARS as evidence, that rate is the caller's. The field() makes the
# rate required: a bare annotation would inherit Evidence's None default.
# am[implements a-ev-br-evidence-type-1017@81ce8a]
@dataclass(frozen=True)
class EvidenceCounts(Evidence):
    """The evidence SNARS holds for a statement, with the base rate it applied."""

    base_rate: float = field()

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_rate", _probability("base_rate", self.base_rate))
        super().__post_init__()


@dataclass(frozen=True)
class EvidenceReceipt:
    receipt_id: str
    source: str
    statement_id: str
    trust: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "receipt_id", _nonempty("receipt_id", self.receipt_id))
        object.__setattr__(self, "source", _nonempty("source", self.source))
        object.__setattr__(self, "statement_id", _nonempty("statement_id", self.statement_id))
        object.__setattr__(self, "trust", _probability("trust", self.trust))


@dataclass(frozen=True)
class SnarsProof:
    kind: str
    conclusion: str
    premises: tuple[SnarsProof | SnarsBelief, ...]
    axiom_stamps: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _nonempty("kind", self.kind))
        object.__setattr__(self, "conclusion", _nonempty("conclusion", self.conclusion))
        _typed_tuple("premises", self.premises, (SnarsProof, SnarsBelief))
        _string_tuple("axiom_stamps", self.axiom_stamps)


@dataclass(frozen=True)
class SnarsBelief:
    statement_id: str
    canonical_statement: str
    opinion: SubjectiveOpinion
    evidence: EvidenceCounts
    receipts: tuple[EvidenceReceipt, ...]
    proofs: tuple[SnarsProof, ...]
    sources: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement_id", _nonempty("statement_id", self.statement_id))
        object.__setattr__(
            self,
            "canonical_statement",
            _nonempty("canonical_statement", self.canonical_statement),
        )
        if not isinstance(self.opinion, SubjectiveOpinion):
            raise TypeError("opinion must be a SubjectiveOpinion")
        if not isinstance(self.evidence, EvidenceCounts):
            raise TypeError("evidence must be EvidenceCounts")
        _typed_tuple("receipts", self.receipts, EvidenceReceipt)
        _typed_tuple("proofs", self.proofs, SnarsProof)
        _string_tuple("sources", self.sources)


@dataclass(frozen=True)
class SnarsCounterfactual:
    """A transactional SNARS result with proof of state rollback."""

    hypothesis: str
    query: str
    opinion: SubjectiveOpinion
    proofs: tuple[SnarsProof, ...]
    state_before: str
    state_after: str
    digest_before: str
    digest_after: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "hypothesis", _nonempty("hypothesis", self.hypothesis))
        object.__setattr__(self, "query", _nonempty("query", self.query))
        if not isinstance(self.opinion, SubjectiveOpinion):
            raise TypeError("opinion must be a SubjectiveOpinion")
        _typed_tuple("proofs", self.proofs, SnarsProof)
        for field_name in (
            "state_before",
            "state_after",
            "digest_before",
            "digest_after",
        ):
            object.__setattr__(
                self,
                field_name,
                _nonempty(field_name, getattr(self, field_name)),
            )
        if self.state_before != self.state_after:
            raise ValueError("counterfactual state was not rolled back")
        if self.digest_before != self.digest_after:
            raise ValueError("counterfactual state digest changed")


@dataclass(frozen=True)
class SnarsGoal:
    """A registered SNARS goal and the GoalChainer metadata it must preserve."""

    goal_id: str
    canonical_statement: str
    owner: str
    kind: GoalKind
    desire: float
    required: bool
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_id", _nonempty("goal_id", self.goal_id))
        object.__setattr__(
            self,
            "canonical_statement",
            _nonempty("canonical_statement", self.canonical_statement),
        )
        object.__setattr__(self, "owner", _nonempty("owner", self.owner))
        if self.kind not in ("individual", "collective"):
            raise ValueError("kind must be 'individual' or 'collective'")
        object.__setattr__(self, "desire", _probability("desire", self.desire))
        if not isinstance(self.required, bool):
            raise TypeError("required must be a bool")
        object.__setattr__(self, "source", _nonempty("source", self.source))


@dataclass(frozen=True)
class TemporalOccurrence:
    """One statement occurrence on a deterministic logical or real clock."""

    statement_id: str
    tick: float
    clock: ClockKind = "logical"

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement_id", _nonempty("statement_id", self.statement_id))
        object.__setattr__(self, "tick", _finite("tick", self.tick))
        if self.clock not in ("logical", "real"):
            raise ValueError("clock must be 'logical' or 'real'")


@dataclass(frozen=True)
class TemporalInterval:
    """A closed interval constructed from occurrences of one statement."""

    statement_id: str
    start_tick: float
    end_tick: float
    clock: ClockKind = "logical"

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement_id", _nonempty("statement_id", self.statement_id))
        object.__setattr__(self, "start_tick", _finite("start_tick", self.start_tick))
        object.__setattr__(self, "end_tick", _finite("end_tick", self.end_tick))
        if self.start_tick > self.end_tick:
            raise ValueError("start_tick must not exceed end_tick")
        if self.clock not in ("logical", "real"):
            raise ValueError("clock must be 'logical' or 'real'")


# An open premise carries no opinion of its own: the route's hypothesis stands in for it.
# am[implements a-rt-ob-session-1017@f1468f]
@dataclass(frozen=True)
class ObligationLeaf:
    """One leaf of a route: an open premise, or a held statement or edge with its condition."""

    statement: str
    status: LeafStatus
    statement_id: str | None = None
    opinion: SubjectiveOpinion | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement", _nonempty("statement", self.statement))
        if self.status not in ("Holds", "Fails", "Undecided", "Open"):
            raise ValueError("leaf status must be Holds, Fails, Undecided or Open")
        held = self.status != "Open"
        if held != (self.statement_id is not None) or held != (self.opinion is not None):
            raise ValueError("a held leaf names its statement id and opinion; an open one neither")
        if self.statement_id is not None:
            object.__setattr__(self, "statement_id", _nonempty("statement_id", self.statement_id))
        if self.opinion is not None and not isinstance(self.opinion, SubjectiveOpinion):
            raise TypeError("opinion must be a SubjectiveOpinion")

    @property
    def discharged(self) -> bool:
        """Only evidence that makes the leaf meet the condition discharges it."""

        return self.status == "Holds"


# The scenario is the opinion the statement would hold were every open premise to carry the
# hypothesis: a labelled supposition, not attainable confidence, an information value or a bound.
# Its status is SNARS's cut of it at the obligations threshold, true only under that hypothesis.
# am[implements a-rt-ob-session-1017@f1468f] am[rests-on c-integrate-hypothetical-route-not-bound-1017@bbaece]
@dataclass(frozen=True)
class ObligationRoute:
    """One structural route to a statement within the size bound, with its leaves."""

    leaves: tuple[ObligationLeaf, ...]
    scenario: SubjectiveOpinion
    scenario_status: ConditionStatus
    proof: str
    size: int

    def __post_init__(self) -> None:
        _typed_tuple("leaves", self.leaves, ObligationLeaf)
        if not self.leaves:
            raise ValueError("a route has at least one leaf")
        if not isinstance(self.scenario, SubjectiveOpinion):
            raise TypeError("scenario must be a SubjectiveOpinion")
        if self.scenario_status not in ("Holds", "Fails", "Undecided"):
            raise ValueError("scenario status must be Holds, Fails or Undecided")
        object.__setattr__(self, "proof", _nonempty("proof", self.proof))
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 1:
            raise ValueError("route size must be a positive integer")

    @property
    def unmet(self) -> tuple[ObligationLeaf, ...]:
        """The leaves this route still needs: open, undecided or failed."""

        return tuple(leaf for leaf in self.leaves if not leaf.discharged)

    # Leaves that all hold aren't enough, since each deduction step discounts belief: two steps
    # from premises at (8, 0) give the statement 0.512, Undecided at threshold 0.6.
    # am[implements a-rt-ob-established-1017@31d188] am[rests-on c-rt-ob-established-rule-1017@0ccb43]
    # am[rests-on c-integrate-held-leaves-not-held-goal-1017@43c6c3]
    @property
    def established(self) -> bool:
        """Whether this route alone shows the statement meets the condition: nothing is unmet, so the
        scenario supposes nothing and is the opinion the route's proof gives, and that opinion Holds."""

        return not self.unmet and self.scenario_status == "Holds"


# Every structural route is kept in the order SNARS sorted them, which states no preference.
# am[implements a-rt-ob-session-1017@f1468f] am[rests-on c-rt-pm-interface-shape-v6-1017@ec7b8c]
@dataclass(frozen=True)
class SnarsObligations:
    """What each route to a statement still needs at a threshold, under a stated hypothesis."""

    statement: str
    threshold: float
    hypothesis: SubjectiveOpinion
    routes: tuple[ObligationRoute, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement", _nonempty("statement", self.statement))
        object.__setattr__(self, "threshold", _probability("threshold", self.threshold))
        if not isinstance(self.hypothesis, SubjectiveOpinion):
            raise TypeError("hypothesis must be a SubjectiveOpinion")
        _typed_tuple("routes", self.routes, ObligationRoute)


# The attention search's result, classified in the batch that ran it. A negated condition is the
# literal (Not S): its opinion is the complement of S's, and the status is the cut of that.
# am[implements a-rt-ob-session-1017@f1468f] am[rests-on c-integrate-runtime-obligations-ruling-1017@6a2fe6]
# am[implements a-rt-ob-negation-track-1017@a1a80d]
@dataclass(frozen=True)
class SnarsCondition:
    """A statement's condition at a threshold after the attention forward search."""

    statement: str
    statement_id: str
    threshold: float
    negated: bool
    status: ConditionStatus
    search: SearchStatus
    steps: int
    opinion: SubjectiveOpinion

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement", _nonempty("statement", self.statement))
        object.__setattr__(self, "statement_id", _nonempty("statement_id", self.statement_id))
        object.__setattr__(self, "threshold", _probability("threshold", self.threshold))
        if not isinstance(self.negated, bool):
            raise TypeError("negated must be a bool")
        if self.status not in ("Holds", "Fails", "Undecided"):
            raise ValueError("condition status must be Holds, Fails or Undecided")
        if self.search not in ("Witness", "Incomplete"):
            raise ValueError("search must be Witness or Incomplete")
        if self.search == "Incomplete" and self.status != "Undecided":
            raise ValueError("an incomplete search leaves the condition Undecided")
        if isinstance(self.steps, bool) or not isinstance(self.steps, int) or self.steps < 0:
            raise ValueError("steps must be a non-negative integer")
        if not isinstance(self.opinion, SubjectiveOpinion):
            raise TypeError("opinion must be a SubjectiveOpinion")


# A track record's projection: the opinion SNARS gives counts a caller attributed, at SNARS's
# default rate, and its cut, computed afresh each time rather than believed.
# am[implements a-rt-ob-negation-track-1017@a1a80d]
@dataclass(frozen=True)
class SnarsTrack:
    """The opinion of `positive` and `negative` counts and its condition at `threshold`."""

    positive: float
    negative: float
    threshold: float
    opinion: SubjectiveOpinion
    status: ConditionStatus

    def __post_init__(self) -> None:
        object.__setattr__(self, "positive", _nonnegative("positive", self.positive))
        object.__setattr__(self, "negative", _nonnegative("negative", self.negative))
        object.__setattr__(self, "threshold", _probability("threshold", self.threshold))
        if not isinstance(self.opinion, SubjectiveOpinion):
            raise TypeError("opinion must be a SubjectiveOpinion")
        if self.status not in ("Holds", "Fails", "Undecided"):
            raise ValueError("track status must be Holds, Fails or Undecided")


__all__ = [
    "ClockKind",
    "Evidence",
    "EvidenceCounts",
    "EvidenceReceipt",
    "GoalKind",
    "OPINION_SUM_TOLERANCE",
    "SnarsBelief",
    "SnarsCounterfactual",
    "SnarsGoal",
    "SnarsProof",
    "SubjectiveOpinion",
    "TemporalInterval",
    "TemporalOccurrence",
]

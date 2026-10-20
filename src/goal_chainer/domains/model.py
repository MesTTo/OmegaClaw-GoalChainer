"""Purpose: the immutable records a domain file is read into: its candidate actions, goals,
signals, dimensions, authority tiers, estimator ceilings and theory rules, its optional reading,
bigraph and needs sections, whose records their section modules hold, and the error a domain that
cannot be read raises."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ..models import Goal

# The section modules import DomainError from here, so their records are named for the type
# checker alone and never imported at run time.
if TYPE_CHECKING:
    from .bigraph import BigraphSection
    from .needs import Need, NeedExpectation, NeedSection
    from .readings import ReadingDeclaration


# am[implements a-rel-domain-1016@6f8fc8] am[implements a-rel-nd-validation-runner-1018@f3f0b6]
class DomainError(ValueError):
    """A domain file that cannot be read as a decision problem. `faults` lists, a line each, every
    fault the domain's relational checks found, and is empty for a fault found while reading."""

    def __init__(self, message: str, faults: Iterable[str] = ()) -> None:
        super().__init__(message)
        self.faults = tuple(faults)


# am[implements a-rel-domain-1016@6f8fc8]
@dataclass(frozen=True)
class AuthorityTier:
    """A rung on the authority ladder. `rank` orders them, lowest is weakest."""

    id: str
    rank: int
    description: str


# am[implements a-rel-domain-1016@6f8fc8] am[addresses i-rel-authority-1016@ab7bf8]
@dataclass(frozen=True)
class DomainAction:
    """A candidate action and the highest authority rung it may be applied at.

    `authority` is a ceiling, not a permission requirement: once every other check has passed,
    the action may be applied at most at this rung, and the estimator ceilings of the evidence
    under it can lower that further but never raise it. Who actually grants an application is
    the host's policy, outside the review.

    There is deliberately no default strength. A bare number attached to an action hides a value
    judgment behind a scalar; what an action is worth is derived per review, as typed effects
    with estimator provenance.
    """

    id: str
    label: str
    description: str
    authority: str


# am[implements a-rel-domain-1016@6f8fc8] am[rests-on c-rel-absent-cue-refutes-1016@26eafb]
@dataclass(frozen=True)
class Signal:
    """A condition a review packet reports on and the theory reasons over.

    The description says what an observation of it means, for whoever compiles the packet.
    There are no text cues: a phrase that does not appear in a request is not evidence that the
    condition is absent, so signals arrive only as explicit readings.
    """

    id: str
    description: str


# am[implements a-rel-domain-1016@6f8fc8]
@dataclass(frozen=True)
class Dimension:
    """A material dimension actions are compared on.

    `polarity` says which direction of the underlying quantity is good. Effects are stated as
    signed bands toward our welfare, so the polarity documents meaning and does not flip
    comparisons.
    """

    id: str
    polarity: Literal["benefit", "cost"]
    description: str


# am[implements a-rel-domain-1016@6f8fc8]
@dataclass(frozen=True)
class Pattern:
    """A literal a rule reads or concludes, with sign and deontic mode stripped.

    `args` are atom texts; a `?name` argument is a variable and a nested term is rendered
    canonically, the way the deontic engine prints it.
    """

    functor: str
    args: tuple[str, ...]

    def render(self) -> str:
        return "(" + " ".join((self.functor, *self.args)) + ")"


# am[implements a-rel-domain-1016@6f8fc8]
@dataclass(frozen=True)
class Rule:
    """One `always`, `normally` or `except` rule: the literals it reads and those it concludes.

    `norms` are the concluded literals that sit under a deontic operator, the duties,
    permissions and prohibitions the rule bears on.
    """

    label: str | None
    kind: str
    body: tuple[Pattern, ...]
    heads: tuple[Pattern, ...]
    norms: tuple[Pattern, ...] = ()


# am[implements a-rel-domain-1016@6f8fc8]
@dataclass(frozen=True)
class Domain:
    title: str
    policy_version: str
    source: str
    digest: str
    actions: tuple[DomainAction, ...]
    goals: tuple[Goal, ...]
    signals: tuple[Signal, ...]
    dimensions: tuple[Dimension, ...]
    authorities: tuple[AuthorityTier, ...]
    estimator_ceilings: tuple[tuple[str, str], ...]
    theory: str
    rules: tuple[Rule, ...]
    facts: tuple[Pattern, ...]
    unestimated_dimensions: tuple[str, ...]
    readings: ReadingDeclaration | None = None
    bigraph: BigraphSection | None = None
    # The needs section, whose needs the review regulates; None when the domain declares none, so
    # its reviews rank exactly as a domain without motivation does.
    # am[implements a-v2m-need-forms-1019@6ee59c]
    motivation: NeedSection | None = None
    # The declared signals no rule body reads, sorted. A reading of one changes nothing a review
    # concludes, but a shared domain may declare a condition only planning or classification reads,
    # so the domain lists them rather than refusing them.
    # am[implements a-rel-nd-unread-signals-1018@f57790]
    unread_signals: tuple[str, ...] = ()

    # A review sums an action's goal paths in the goals' declaration order, each path one goal's
    # priority times a value in [-1, 1] and no goal giving an action two paths, so the priorities
    # added in that order bound every aggregate, motive, midpoint and projection the review records.
    # A domain whose sum overflows is refused: two goals of priority 1e308 that one action serves
    # fully gave a projection of inf, which no record holds (c-v2m-priority-sum-bound-1020). The
    # loop adds as the policy's fold does; math.fsum rounds once and can stay finite where the fold
    # overflows.
    # Time: one addition per goal.
    # am[implements a-v2m-priority-sum-finite-1020@7596cf] am[rests-on c-v2m-priority-sum-bound-1020@7fb487]
    def __post_init__(self) -> None:
        total = 0.0
        for goal in self.goals:
            total += goal.weight
        if not math.isfinite(total):
            raise DomainError(
                f"{self.source}: the goals' priorities, added in declaration order, pass the largest "
                "double, so a review could not record an action that serves them all"
            )

    @property
    def action_ids(self) -> tuple[str, ...]:
        return tuple(action.id for action in self.actions)

    @property
    def goal_ids(self) -> tuple[str, ...]:
        return tuple(goal.id for goal in self.goals)

    @property
    def signal_ids(self) -> tuple[str, ...]:
        return tuple(signal.id for signal in self.signals)

    @property
    def dimension_ids(self) -> tuple[str, ...]:
        return tuple(dimension.id for dimension in self.dimensions)

    @property
    def authority_ids(self) -> tuple[str, ...]:
        return tuple(tier.id for tier in self.authorities)

    # am[implements a-v2m-need-forms-1019@6ee59c]
    @property
    def needs(self) -> tuple[Need, ...]:
        return () if self.motivation is None else self.motivation.needs

    # am[implements a-v2m-need-forms-1019@6ee59c]
    @property
    def need_expectations(self) -> tuple[NeedExpectation, ...]:
        return () if self.motivation is None else self.motivation.expectations

    # am[implements a-v2m-need-forms-1019@6ee59c]
    @property
    def need_ids(self) -> tuple[str, ...]:
        return tuple(need.id for need in self.needs)

    # am[implements a-v2m-need-forms-1019@6ee59c]
    def need(self, need_id: str) -> Need:
        for candidate in self.needs:
            if candidate.id == need_id:
                return candidate
        raise DomainError(f"no such need in {self.source}: {need_id}")

    def action(self, action_id: str) -> DomainAction:
        for candidate in self.actions:
            if candidate.id == action_id:
                return candidate
        raise DomainError(f"no such action in {self.source}: {action_id}")

    def goal(self, goal_id: str) -> Goal:
        for candidate in self.goals:
            if candidate.id == goal_id:
                return candidate
        raise DomainError(f"no such goal in {self.source}: {goal_id}")

    def dimension(self, dimension_id: str) -> Dimension:
        for candidate in self.dimensions:
            if candidate.id == dimension_id:
                return candidate
        raise DomainError(f"no such dimension in {self.source}: {dimension_id}")

    def authority(self, authority_id: str) -> AuthorityTier:
        for candidate in self.authorities:
            if candidate.id == authority_id:
                return candidate
        raise DomainError(f"no such authority tier in {self.source}: {authority_id}")

    def ceiling_for(self, estimator_class: str) -> str:
        """The highest authority rung a field of this estimator class can license."""

        for estimator, tier in self.estimator_ceilings:
            if estimator == estimator_class:
                return tier
        raise DomainError(
            f"{self.source}: no gc-estimator-ceiling declared for {estimator_class}"
        )

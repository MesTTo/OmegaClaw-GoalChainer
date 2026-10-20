"""Purpose: the goal record a domain declares."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

GoalKind = Literal["individual", "collective"]


# am[implements a-rel-domain-1016@6f8fc8]
@dataclass(frozen=True)
class Goal:
    """A desired state with a priority and the provenance of that priority.

    `weight` is the priority: human- or policy-declared importance, never inferred from
    activity volume. `priority_source` records who declared it, because a derived score that
    loses its source launders the value judgment behind the number. Relevance reviews name
    the source of the goal path that carried a decision; a goal whose priority nobody declared
    leaves it empty.
    """

    id: str
    owner: str
    statement: str
    weight: float
    kind: GoalKind
    required: bool = False
    priority_source: str = ""

    # A priority multiplies and sums into every path through the goal, so a NaN or infinite one
    # would make those values unrecordable: a review's fingerprint refuses them. math.isfinite
    # converts an int to float, so an integer beyond the float range, which has no float priority,
    # raises OverflowError there and is refused with the same ValueError, named rather than written
    # out (c-rel-num-goal-direct-only-1018). Every accepted weight is kept as given.
    # am[implements a-rel-finite-priority-1017@262e4d] am[addresses i-rel-nonfinite-priority-1017@5fba78]
    # am[implements a-integrate-relevance-numeric-boundaries-1018@4c2a7d]
    def __post_init__(self) -> None:
        try:
            finite = math.isfinite(self.weight)
        except OverflowError:
            raise ValueError(
                f"goal priority must be a finite non-negative number: {self.id} has an integer beyond the float range"
            ) from None
        if not finite or self.weight < 0:
            raise ValueError(f"goal priority must be a finite non-negative number: {self.id} has {self.weight}")

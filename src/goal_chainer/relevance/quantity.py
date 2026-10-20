"""Purpose: typed effect quantities and per-action profiles that keep every derived estimate and its estimator class.

Section 9.2 of the goal relevance governor paper lists what must stay distinct in the
internal representation: priority, causal belief, confidence, goal delta, urgency, direct
cost, opportunity cost, hazard, irreversibility, governance overhead, option value and
authority. "Contribution is not ordinary truth, priority is not probability, and low
evidential support is not the same as high operational risk."

A quantity is one action's signed effect on our welfare through one dimension, as an ordinal
band (section 8.2: fields are ordinal by default) with the estimator class that produced it.
On a cost dimension a positive band means the action reduces that cost, so every dimension
compares in one direction without a weight.

A profile keeps every claim per dimension, so a disagreement stays visible. How the ranking reads
a profile is `policy/ranking.metta`'s decision: one claim is a point, several span their lowest to
their highest band, and no claim is unknown, the whole scale [-1, 1], never neutral, because
section 7.4 asks for the whole predicted transformation and a missing part of it is missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domains.loader import vocabulary
from .errors import RelevanceError

# A band's position on the shared vocabulary's scale, worst first; a band outside it has none.
# am[implements a-rel-nd-vocabulary-down-1018@6e6c8d]
def band_position(band: str) -> int:
    return vocabulary().bands.index(band)


# am[implements a-rel-compiler-1016@c69c38]
@dataclass(frozen=True)
class Quantity:
    """One action's level on one dimension, with the provenance of that level."""

    dimension: str
    band: str
    estimator: str

    def __post_init__(self) -> None:
        if self.band not in vocabulary().bands:
            raise RelevanceError(
                "theory-defect",
                f"{self.dimension}: {self.band} is not an ordinal band; "
                f"expected one of {', '.join(vocabulary().bands)}",
            )
        if self.estimator not in vocabulary().classes:
            raise RelevanceError(
                "theory-defect",
                f"{self.dimension}: {self.estimator} is not an estimator class; "
                f"expected one of {', '.join(vocabulary().classes)}",
            )

    def describe(self) -> str:
        return f"{self.dimension} {self.band} [{self.estimator}]"

    def to_dict(self) -> dict[str, object]:
        return {"dimension": self.dimension, "band": self.band, "estimator": self.estimator}


# am[implements a-rel-compiler-1016@c69c38] am[addresses i-rel-govcost-1016@e950e5]
@dataclass(frozen=True)
class QuantityConflict:
    """Two surviving claims about one action's level on one dimension.

    A band is a literal argument rather than a sign, so the defeasible engine does not treat
    differing bands as attacking each other and both can survive. Claims from one estimator
    class contradict each other, which is a defect in the theory; claims from different classes
    are a genuine evidential disagreement, which section 13.2 lists as an escalation trigger.
    """

    action: str
    dimension: str
    claims: tuple[Quantity, ...]

    @property
    def is_theory_defect(self) -> bool:
        return len({claim.estimator for claim in self.claims}) == 1

    def describe(self) -> str:
        rendered = " vs ".join(claim.describe() for claim in self.claims)
        return f"{self.action} {self.dimension}: {rendered}"

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "dimension": self.dimension,
            "claims": [claim.to_dict() for claim in self.claims],
        }


# am[implements a-rel-ranking-1016@334372] am[addresses i-rel-unknown-neutral-1016@7e3679]
@dataclass(frozen=True)
class Profile:
    """Every typed quantity derived about one action, indexed by dimension."""

    action: str
    claims: dict[str, tuple[Quantity, ...]] = field(default_factory=dict)

    @property
    def conflicts(self) -> tuple[QuantityConflict, ...]:
        return tuple(
            QuantityConflict(self.action, dimension, claims)
            for dimension, claims in sorted(self.claims.items())
            if len({claim.band for claim in claims}) > 1
        )

    @property
    def quantities(self) -> tuple[Quantity, ...]:
        return tuple(
            claim for dimension in sorted(self.claims) for claim in self.claims[dimension]
        )


# am[implements a-rel-compiler-1016@c69c38]
def build_profile(action: str, claims: list[Quantity]) -> Profile:
    """Group one action's derived quantities by dimension, duplicates removed, order fixed."""

    grouped: dict[str, set[Quantity]] = {}
    for claim in claims:
        grouped.setdefault(claim.dimension, set()).add(claim)
    return Profile(
        action=action,
        claims={
            dimension: tuple(sorted(group, key=lambda q: (band_position(q.band), q.estimator)))
            for dimension, group in grouped.items()
        },
    )

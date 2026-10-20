"""Purpose: the typed result of compiling one review: candidates, their deontic standing, effects, contributions and readsets.

Everything here is read off one bounded run of the domain's theory; nothing is decided. The
ranking policy reads these records, encoded as atoms, and never the theory run itself.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from ..deontic_engine import DeonticSupport
from ..domains.model import Domain, DomainAction
from .packet import ReviewPacket
from .quantity import Profile
from .signals import EffectiveReading


# am[implements a-rel-compiler-1016@c69c38]
@dataclass(frozen=True)
class Contribution:
    """What one action does for one goal, on the ordinal scale.

    Kept per goal path and never pre-collapsed, because section 9.5 requires that the
    aggregation rule be an explicit choice and that every explanation name the path whose
    priority carried the decision. A goal an action has no derived contribution to is no path,
    not an unknown one: contribution edges exist only where the theory derives them.
    """

    goal: str
    band: str

    def to_dict(self) -> dict[str, object]:
        return {"goal": self.goal, "band": self.band}


# am[implements a-rel-compiler-1016@c69c38] am[addresses i-rel-unpermitted-admissible-1016@1d4f81]
@dataclass(frozen=True)
class Candidate:
    """An action whose preconditions hold, with everything the theory derived about it."""

    action: DomainAction
    modes: frozenset[str]
    dilemma: bool
    profile: Profile
    contributions: tuple[Contribution, ...]
    readset: frozenset[str]

    @property
    def id(self) -> str:
        return self.action.id


# am[implements a-rel-compiler-1016@c69c38]
@dataclass(frozen=True)
class EngineRecord:
    """Which engine produced the conclusions; what the review cost is its budget's to say."""

    runtime: str
    runtime_digest: str
    plugin_digest: str
    swipl_version: str

    def identity(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in ENGINE_IDENTITY_FIELDS}


# The fields a review keeps of the engine's identity, which the freshness check compares.
ENGINE_IDENTITY_FIELDS: tuple[str, ...] = tuple(field.name for field in fields(EngineRecord))


# am[implements a-rel-compiler-1016@c69c38] am[implements a-integrate-deontic-support-trees-1019@508ecf]
@dataclass(frozen=True)
class DerivedReview:
    """One review packet compiled against one domain: the input the ranking decides over."""

    domain: Domain
    packet: ReviewPacket
    readings: dict[str, EffectiveReading]
    candidates: tuple[Candidate, ...]
    obligations: tuple[str, ...]
    required_goals: tuple[str, ...]
    other_dilemmas: tuple[str, ...]
    readset: frozenset[str]
    engine: EngineRecord
    theory: str
    deontic_support: tuple[DeonticSupport, ...]

    def candidate(self, action_id: str) -> Candidate:
        for candidate in self.candidates:
            if candidate.id == action_id:
                return candidate
        raise KeyError(action_id)

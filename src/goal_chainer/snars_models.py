"""Immutable values exchanged with the native PeTTa-backed SNARS runtime."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping

# Protocol values may pass through decimal text before becoming floats. This
# absolute tolerance accepts ordinary conversion noise while still rejecting an
# opinion whose belief, disbelief, and uncertainty do not form a simplex.
OPINION_SUM_TOLERANCE = 1e-9

GoalKind = Literal["individual", "collective"]
ClockKind = Literal["logical", "real"]


def _finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not isfinite(result):
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


def _path(name: str, value: Path) -> Path:
    if not isinstance(value, Path):
        raise TypeError(f"{name} must be a pathlib.Path")
    if not str(value).strip():
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


@dataclass(frozen=True)
class EvidenceCounts:
    positive: float
    negative: float
    base_rate: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "positive", _nonnegative("positive", self.positive))
        object.__setattr__(self, "negative", _nonnegative("negative", self.negative))
        object.__setattr__(self, "base_rate", _probability("base_rate", self.base_rate))


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
class SnarsActionAssessment:
    """Native action beliefs used by the GoalChainer decision gate."""

    action_id: str
    acceptable: SnarsBelief
    risky: SnarsBelief
    forbidden: SnarsBelief
    conflict_degree: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_id", _nonempty("action_id", self.action_id))
        for field_name in ("acceptable", "risky", "forbidden"):
            if not isinstance(getattr(self, field_name), SnarsBelief):
                raise TypeError(f"{field_name} must be a SnarsBelief")
        object.__setattr__(
            self,
            "conflict_degree",
            _probability("conflict_degree", self.conflict_degree),
        )


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


@dataclass(frozen=True)
class RuntimeDiagnostics:
    """Resolved native-runtime paths and the exact Mettabase revision."""

    mettabase_dir: Path
    mettabase_commit: str
    snars_program: Path
    snars_kernel: Path
    hyperbase_program: Path
    petta_dir: Path
    petta_main: Path
    swipl: Path
    python_package: Path | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "mettabase_dir",
            "snars_program",
            "snars_kernel",
            "hyperbase_program",
            "petta_dir",
            "petta_main",
            "swipl",
        ):
            object.__setattr__(self, field_name, _path(field_name, getattr(self, field_name)))
        object.__setattr__(
            self,
            "mettabase_commit",
            _nonempty("mettabase_commit", self.mettabase_commit),
        )
        if self.python_package is not None:
            object.__setattr__(
                self,
                "python_package",
                _path("python_package", self.python_package),
            )


class SnarsError(Exception):
    """Base class for stable, machine-readable SNARS failures."""

    code = "snars_error"

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.message = _nonempty("message", message)
        if details is not None and not isinstance(details, Mapping):
            raise TypeError("details must be a mapping")
        self.details: Mapping[str, object] = MappingProxyType(dict(details or {}))
        super().__init__(self.message)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }


class SnarsDependencyUnavailableError(SnarsError):
    code = "dependency_unavailable"


class SnarsInvalidInputError(SnarsError):
    code = "invalid_input"


class SnarsTimeoutError(SnarsError):
    code = "timeout"


class SnarsProtocolError(SnarsError):
    code = "protocol_error"


class SnarsPettaExecutionError(SnarsError):
    code = "petta_execution_error"


class SnarsPersistenceError(SnarsError):
    code = "persistence_error"


class SnarsUnsupportedCapabilityError(SnarsError):
    code = "unsupported_design_only_capability"


__all__ = [
    "ClockKind",
    "EvidenceCounts",
    "EvidenceReceipt",
    "GoalKind",
    "OPINION_SUM_TOLERANCE",
    "RuntimeDiagnostics",
    "SnarsActionAssessment",
    "SnarsBelief",
    "SnarsCounterfactual",
    "SnarsDependencyUnavailableError",
    "SnarsError",
    "SnarsGoal",
    "SnarsInvalidInputError",
    "SnarsPersistenceError",
    "SnarsPettaExecutionError",
    "SnarsProof",
    "SnarsProtocolError",
    "SnarsTimeoutError",
    "SnarsUnsupportedCapabilityError",
    "SubjectiveOpinion",
    "TemporalInterval",
    "TemporalOccurrence",
]

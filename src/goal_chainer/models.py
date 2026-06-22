"""Data models for goal, norm, and evidence-aware action ranking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

GoalKind = Literal["individual", "collective"]
NormMode = Literal["oblige", "permit", "forbid"]


@dataclass(frozen=True)
class Goal:
    id: str
    owner: str
    statement: str
    weight: float
    kind: GoalKind
    required: bool = False

    def __post_init__(self) -> None:
        if self.weight < 0:
            raise ValueError(f"goal weight must be non-negative: {self.id}")


@dataclass(frozen=True)
class Norm:
    id: str
    mode: NormMode
    target_action: str
    reason: str
    priority: int = 0


@dataclass(frozen=True)
class CandidateAction:
    id: str
    label: str
    description: str
    satisfies: tuple[str, ...]
    evidence_query: str
    evidence_atoms: tuple[str, ...]
    default_strength: float
    default_confidence: float = 0.99

    def __post_init__(self) -> None:
        if not 0.0 <= self.default_strength <= 1.0:
            raise ValueError(f"default_strength outside [0, 1]: {self.id}")
        if not 0.0 <= self.default_confidence <= 1.0:
            raise ValueError(f"default_confidence outside [0, 1]: {self.id}")


@dataclass(frozen=True)
class EvidenceProjection:
    strength: float
    confidence: float
    source: str
    projection: str | None = None
    proofs: tuple[str, ...] = ()


@dataclass(frozen=True)
class GoalScenario:
    title: str
    goals: tuple[Goal, ...]
    norms: tuple[Norm, ...]
    actions: tuple[CandidateAction, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Decision:
    action_id: str
    label: str
    status: str
    score: float
    goal_score: float
    individual_score: float
    collective_score: float
    evidence: EvidenceProjection
    norm_status: str
    norm_reasons: tuple[str, ...] = ()
    satisfied_goals: tuple[str, ...] = ()
    missing_required_goals: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "label": self.label,
            "status": self.status,
            "score": round(self.score, 6),
            "goal_score": round(self.goal_score, 6),
            "individual_score": round(self.individual_score, 6),
            "collective_score": round(self.collective_score, 6),
            "evidence": {
                "strength": round(self.evidence.strength, 6),
                "confidence": round(self.evidence.confidence, 6),
                "source": self.evidence.source,
                "projection": self.evidence.projection,
                "proofs": list(self.evidence.proofs),
            },
            "norm_status": self.norm_status,
            "norm_reasons": list(self.norm_reasons),
            "satisfied_goals": list(self.satisfied_goals),
            "missing_required_goals": list(self.missing_required_goals),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


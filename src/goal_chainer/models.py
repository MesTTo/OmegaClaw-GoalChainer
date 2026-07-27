"""Data models for goal, norm, and evidence-aware action ranking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .snars_models import (
    EvidenceCounts,
    EvidenceReceipt,
    SnarsBelief,
    SnarsProof,
    SubjectiveOpinion,
)

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
    """Decision evidence with native SNARS values as the authority.

    ``strength`` and ``confidence`` remain for payload compatibility. Native
    decisions use ``expectation`` directly.
    """

    strength: float
    confidence: float
    source: str
    projection: str | None = None
    proofs: tuple[str, ...] = ()
    deontic: str = "unregulated"
    expectation: float = 0.0
    opinion: SubjectiveOpinion | None = None
    counts: EvidenceCounts | None = None
    receipts: tuple[EvidenceReceipt, ...] = ()
    native_proofs: tuple[SnarsProof, ...] = ()
    sources: tuple[str, ...] = ()
    conflict_degree: float = 0.0


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
                "expectation": round(self.evidence.expectation, 6),
                "source": self.evidence.source,
                "projection": self.evidence.projection,
                "proofs": list(self.evidence.proofs),
                "opinion": _opinion_dict(self.evidence.opinion),
                "counts": _counts_dict(self.evidence.counts),
                "receipts": [
                    _receipt_dict(receipt) for receipt in self.evidence.receipts
                ],
                "native_proofs": [
                    _proof_dict(proof) for proof in self.evidence.native_proofs
                ],
                "sources": list(self.evidence.sources),
                "conflict_degree": round(self.evidence.conflict_degree, 6),
            },
            "norm_status": self.norm_status,
            "norm_reasons": list(self.norm_reasons),
            "satisfied_goals": list(self.satisfied_goals),
            "missing_required_goals": list(self.missing_required_goals),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def _opinion_dict(opinion: SubjectiveOpinion | None) -> dict[str, float] | None:
    if opinion is None:
        return None
    return {
        "belief": round(opinion.belief, 6),
        "disbelief": round(opinion.disbelief, 6),
        "uncertainty": round(opinion.uncertainty, 6),
        "base_rate": round(opinion.base_rate, 6),
        "expectation": round(opinion.expectation, 6),
    }


def _counts_dict(counts: EvidenceCounts | None) -> dict[str, float] | None:
    if counts is None:
        return None
    return {
        "positive": round(counts.positive, 6),
        "negative": round(counts.negative, 6),
        "base_rate": round(counts.base_rate, 6),
    }


def _receipt_dict(receipt: EvidenceReceipt) -> dict[str, object]:
    return {
        "receipt_id": receipt.receipt_id,
        "source": receipt.source,
        "statement_id": receipt.statement_id,
        "trust": round(receipt.trust, 6),
    }


def _proof_dict(proof: SnarsProof) -> dict[str, object]:
    return {
        "kind": proof.kind,
        "conclusion": proof.conclusion,
        "premises": [
            _proof_dict(premise)
            if isinstance(premise, SnarsProof)
            else _belief_reference(premise)
            for premise in proof.premises
        ],
        "axiom_stamps": list(proof.axiom_stamps),
    }


def _belief_reference(belief: SnarsBelief) -> dict[str, object]:
    return {
        "kind": "belief",
        "statement_id": belief.statement_id,
        "canonical_statement": belief.canonical_statement,
        "opinion": _opinion_dict(belief.opinion),
        "sources": list(belief.sources),
    }

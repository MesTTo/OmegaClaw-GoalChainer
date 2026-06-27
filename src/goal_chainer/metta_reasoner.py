"""Action evidence from OmegaClaw on PeTTa: lib_deontic status + lib_nal belief.

Everything runs on the PeTTa runtime (MeTTa compiled to SWI-Prolog), never on a
hyperon binary. Two real OmegaClaw libraries are combined:

- lib_deontic answers the normative question (forbidden / obligated / permitted)
  via defeasible + standard deontic logic. See `deontic_engine.py`.
- lib_nal grades how strongly each action is believed acceptable, using NAL
  deduction over evidence-derived premises.

Both the deontic theory and the NAL premise truths are derived from the request's
`IncidentEvidence`, so the result changes with the request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .deontic_engine import ACTION_ORDER, derive_deontic
from .evidence import IncidentEvidence
from .models import CandidateAction, EvidenceProjection
from .petta_runtime import petta_dir, petta_swipl, run_metta

NATIVE_REASONER_SOURCE = "omega-core-petta-lib-deontic-lib-nal"
NAL_IMPORT = "!(import! &self (library OmegaClaw-Core lib_nal))"
# Standing NAL rule: a good action is acceptable. Constant, inspectable.
ACCEPTABLE_RULE = "((--> good_action acceptable_action) (stv 0.92 0.88))"

_CONCLUSION_RE = re.compile(
    r"\(\(-->\s+(?P<subject>[^\s()]+)\s+(?P<predicate>[^\s()]+)\)\s+"
    r"\(stv\s+(?P<f>[0-9.eE+-]+)\s+(?P<c>[0-9.eE+-]+)\)\)"
)


@dataclass(frozen=True)
class Truth:
    frequency: float
    confidence: float

    def metta(self) -> str:
        return f"(stv {self.frequency:.4f} {self.confidence:.4f})"


class HyperBaseMettaReasoner:
    """Expose native PeTTa conclusions as GoalChainer action evidence."""

    source = NATIVE_REASONER_SOURCE

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self._evidence = {
            action["action_id"]: action for action in result.get("action_evidence", [])
        }

    def project(self, action: CandidateAction) -> EvidenceProjection:
        row = self._evidence.get(action.id)
        if row is None:
            raise RuntimeError(f"PeTTa reasoner returned no evidence for {action.id}")
        return EvidenceProjection(
            strength=float(row["strength"]),
            confidence=float(row["confidence"]),
            source=self.source,
            projection=str(row["projection"]),
            proofs=tuple(row["proofs"]),
            deontic=str(row["deontic"]),
            expectation=float(row["expectation"]),
        )


def reason_over_hyperbase(
    propositions: tuple[Any, ...],
    evidence: IncidentEvidence,
) -> dict[str, Any]:
    """Run the deontic engine and NAL belief grading over request-derived premises."""

    deontic = derive_deontic(evidence)
    nal_beliefs, nal_program, nal_outputs = _nal_beliefs(evidence)
    action_evidence = _action_evidence(deontic.status_by_action, nal_beliefs)
    return {
        "source": NATIVE_REASONER_SOURCE,
        "engine": "lib_deontic + lib_nal",
        "execution": {
            "mode": "petta",
            "runtime": str(petta_dir()),
            "swipl": petta_swipl(),
            "deontic_source": "OmegaClaw-Core lib_deontic (defeasible + SDL) on PeTTa",
            "belief_source": "OmegaClaw-Core lib_nal deduction on PeTTa",
        },
        "input": "evidence read from the request",
        "evidence": evidence.to_dict(),
        "deontic_theory": deontic.theory,
        "deontic_conclusions": deontic.conclusions,
        "nal_program": nal_program,
        "raw_outputs": nal_outputs,
        "action_evidence": action_evidence,
    }


def _nal_beliefs(evidence: IncidentEvidence) -> tuple[dict[str, Truth], str, list[str]]:
    """Grade each action's acceptability belief with one NAL deduction on PeTTa."""

    groundings = {action_id: _acceptability_truth(action_id, evidence) for action_id in ACTION_ORDER}
    program_lines = [NAL_IMPORT]
    for action_id, truth in groundings.items():
        grounding = f"((--> {action_id} good_action) {truth.metta()})"
        program_lines.append(f"!(|-nal {grounding} {ACCEPTABLE_RULE})")
    program = "\n".join(program_lines) + "\n"
    outputs = run_metta(program)

    beliefs: dict[str, Truth] = {}
    for action_id in ACTION_ORDER:
        term = f"(--> {action_id} acceptable_action)"
        match = _find_conclusion(term, outputs)
        if match is None:
            raise RuntimeError(f"PeTTa lib_nal did not derive {term}: {outputs}")
        beliefs[action_id] = Truth(float(match["f"]), float(match["c"]))
    return beliefs, program, outputs


def _acceptability_truth(action_id: str, evidence: IncidentEvidence) -> Truth:
    if action_id == "publish_raw_log":
        if evidence.privacy_at_stake:
            count = len(evidence.sensitive_categories)
            # More sensitive categories -> less acceptable, more confidently so.
            return Truth(max(0.05, 0.35 - 0.06 * count), min(0.95, 0.6 + 0.07 * count))
        return Truth(0.9, 0.85)
    if action_id == "publish_redacted_summary":
        return Truth(0.95, 0.9) if evidence.facts_ready else Truth(0.6, 0.72)
    if action_id == "hold_external_update":
        return Truth(0.95, 0.92) if not evidence.facts_ready else Truth(0.9, 0.85)
    return Truth(0.5, 0.5)


def _action_evidence(
    status_by_action: dict[str, str],
    beliefs: dict[str, Truth],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for action_id in ACTION_ORDER:
        status = status_by_action.get(action_id, "unregulated")
        belief = beliefs[action_id]
        rows.append(
            {
                "action_id": action_id,
                "deontic": status,
                "expectation": round(_expectation(belief), 6),
                "strength": round(belief.frequency, 6),
                "confidence": round(belief.confidence, 6),
                "projection": f"(--> {action_id} acceptable_action) {belief.metta()}",
                "proofs": [
                    f"deontic: lib_deontic derived {status} for {action_id}",
                    f"belief: lib_nal graded acceptability {belief.metta()}",
                ],
            }
        )
    return rows


def _expectation(truth: Truth) -> float:
    return truth.confidence * (truth.frequency - 0.5) + 0.5


def _find_conclusion(term: str, outputs: list[str]) -> dict[str, str] | None:
    for line in outputs:
        for match in _CONCLUSION_RE.finditer(line):
            if f"(--> {match.group('subject')} {match.group('predicate')})" == term:
                return match.groupdict()
    return None

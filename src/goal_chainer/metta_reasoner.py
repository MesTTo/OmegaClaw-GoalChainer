"""Action evidence from OmegaClaw on PeTTa: lib_deontic verdict + PeTTaChainer belief.

Everything runs on the PeTTa runtime (MeTTa compiled to SWI-Prolog), never on a
hyperon binary. Two of the user's MeTTa systems are combined:

- lib_deontic answers the normative question (forbidden / obligated / permitted)
  via defeasible + standard deontic logic. See `deontic_engine.py`.
- PeTTaChainer grades how strongly each action is believed acceptable with a PLN
  contextual query that returns a truth value and a proof. See `evidence_chainer.py`.

Both the deontic theory and the PLN statements are derived from the request's
`IncidentEvidence`, so the result changes with the request.
"""

from __future__ import annotations

from typing import Any

from .deontic_engine import ACTION_ORDER, derive_deontic
from .evidence import IncidentEvidence
from .evidence_chainer import Belief, grade_beliefs
from .models import CandidateAction, EvidenceProjection
from .petta_runtime import petta_dir, petta_swipl

NATIVE_REASONER_SOURCE = "omega-core-petta-lib-deontic-pettachainer"


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
    """Run lib_deontic and PeTTaChainer over request-derived premises, on PeTTa."""

    deontic = derive_deontic(evidence)
    beliefs, chainer_program, chainer_outputs = grade_beliefs(evidence)
    action_evidence = _action_evidence(deontic.status_by_action, beliefs)
    return {
        "source": NATIVE_REASONER_SOURCE,
        "engine": "lib_deontic + PeTTaChainer PLN",
        "execution": {
            "mode": "petta",
            "runtime": str(petta_dir()),
            "swipl": petta_swipl(),
            "deontic_source": "OmegaClaw-Core lib_deontic (defeasible + SDL) on PeTTa",
            "belief_source": "PeTTaChainer PLN contextual query on PeTTa",
        },
        "input": "evidence read from the request",
        "evidence": evidence.to_dict(),
        "deontic_theory": deontic.theory,
        "deontic_conclusions": deontic.conclusions,
        "chainer_program": chainer_program,
        "raw_outputs": chainer_outputs,
        "action_evidence": action_evidence,
    }


def _action_evidence(
    status_by_action: dict[str, str],
    beliefs: dict[str, Belief],
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
                "strength": round(belief.strength, 6),
                "confidence": round(belief.confidence, 6),
                "projection": f"(Acceptable {action_id}) (STV {belief.strength:.4f} {belief.confidence:.4f})",
                "proofs": [
                    f"deontic: lib_deontic derived {status} for {action_id}",
                    f"belief: {belief.proof}",
                ],
            }
        )
    return rows


def _expectation(belief: Belief) -> float:
    return belief.confidence * (belief.strength - 0.5) + 0.5

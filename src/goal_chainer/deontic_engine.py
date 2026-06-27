"""Derive each action's deontic status from OmegaClaw-Core's lib_deontic on PeTTa.

This replaces the earlier Truth_Expectation heuristic with the real engine. The
request's evidence is projected into a defeasible-deontic theory (facts; defeasible
`normally` rules; deontic operators must/may/forbidden), the theory is run through
`(library OmegaClaw-Core lib_deontic)` on PeTTa, and each action's forbidden /
obligated / permitted status is read straight off the tagged conclusion set.

A positive defeasible conclusion `(pd (lit pos MODE none ACTION ()))` means the
engine proved ACTION carries deontic MODE (F/O/P). Forbidden dominates obligated
dominates permitted.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .evidence import IncidentEvidence
from .petta_runtime import run_metta

ACTION_ORDER = ("publish_raw_log", "publish_redacted_summary", "hold_external_update")

# A proven positive defeasible deontic literal: (pd (lit pos <MODE> none <action> ()))
_VERDICT_RE = re.compile(r"\(pd \(lit pos (?P<mode>[FOP]) none (?P<action>[a-z_]+) \(\)\)\)")

_MODE_TO_STATUS = {"F": "forbidden", "O": "obligated", "P": "permitted"}
_STATUS_RANK = {"forbidden": 3, "obligated": 2, "permitted": 1, "unregulated": 0}


@dataclass(frozen=True)
class DeonticResult:
    status_by_action: dict[str, str]
    theory: str
    conclusions: str

    def status(self, action_id: str) -> str:
        return self.status_by_action.get(action_id, "unregulated")


def derive_deontic(evidence: IncidentEvidence) -> DeonticResult:
    theory = build_theory(evidence)
    conclusions = _run_engine(theory)
    status_by_action = _parse_status(conclusions)
    for action_id in ACTION_ORDER:
        status_by_action.setdefault(action_id, "unregulated")
    return DeonticResult(status_by_action=status_by_action, theory=theory, conclusions=conclusions)


def build_theory(evidence: IncidentEvidence) -> str:
    """Project the evidence into a pure-MeTTa defeasible-deontic theory."""

    lines: list[str] = []
    # publish_raw_log: forbidden when identifiable data is at stake, otherwise a
    # permission rule fires (nothing to protect).
    if evidence.privacy_at_stake:
        lines += [
            "(given (risky publish_raw_log))",
            "(normally rRawForbid (risky publish_raw_log) (forbidden publish_raw_log))",
        ]
    else:
        lines += [
            "(given (safe publish_raw_log))",
            "(normally rRawPermit (safe publish_raw_log) (may publish_raw_log))",
        ]
    # publish_redacted_summary: obliged when facts are ready, otherwise only permitted.
    lines.append("(given (protects publish_redacted_summary))")
    if evidence.facts_ready:
        lines.append(
            "(normally rRedOblige (protects publish_redacted_summary) (must publish_redacted_summary))"
        )
    else:
        lines.append(
            "(normally rRedPermit (protects publish_redacted_summary) (may publish_redacted_summary))"
        )
    # hold_external_update: obliged while facts are not ready, otherwise permitted.
    if not evidence.facts_ready:
        lines += [
            "(given (factsUnready))",
            "(normally rHoldOblige (factsUnready) (must hold_external_update))",
        ]
    else:
        lines.append("(given (may hold_external_update))")
    return "\n".join(lines) + "\n"


def _run_engine(theory: str) -> str:
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".metta", encoding="utf-8") as handle:
        theory_path = Path(handle.name)
        handle.write(theory)
    try:
        driver = (
            "!(import! &self (library OmegaClaw-Core lib_deontic))\n"
            f'!(dl-run-deontic "{theory_path}")\n'
            "!(dl-conclusions)\n"
        )
        lines = run_metta(driver)
    finally:
        theory_path.unlink(missing_ok=True)
    # The conclusion set is the longest line (every other line is a run acknowledgement).
    return max(lines, key=len) if lines else ""


def _parse_status(conclusions: str) -> dict[str, str]:
    status: dict[str, str] = {}
    for match in _VERDICT_RE.finditer(conclusions):
        action = match.group("action")
        candidate = _MODE_TO_STATUS[match.group("mode")]
        if _STATUS_RANK[candidate] > _STATUS_RANK.get(status.get(action, "unregulated"), 0):
            status[action] = candidate
    return status

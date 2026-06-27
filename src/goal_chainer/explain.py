"""Render the decision's proof chain in English (a why!-style explanation).

This does not invent anything: it reads the real artifacts the pipeline already
produced — lib_deontic's forbidden/obligated/permitted verdict, PeTTaChainer's
graded belief and its proof term, the Subjective-Logic opinion, and goal coverage —
and states why the recommended action won and why the others lost.
"""

from __future__ import annotations

from typing import Any

from .models import Decision


def explain_decisions(decisions: list[Decision], reasoner_result: dict[str, Any]) -> list[str]:
    evidence_by_action = {
        row["action_id"]: row for row in reasoner_result.get("action_evidence", [])
    }
    lines: list[str] = []
    top = decisions[0]
    lines.append(f"Recommended: {top.label} (score {top.score:.3f}).")
    lines.append("  " + _why(top, evidence_by_action.get(top.action_id)))
    if top.satisfied_goals:
        lines.append("  It satisfies: " + ", ".join(top.satisfied_goals) + ".")

    for decision in decisions[1:]:
        verdict = "blocked" if decision.status == "blocked" else "not chosen"
        lines.append(f"{verdict.capitalize()}: {decision.label} (score {decision.score:.3f}).")
        lines.append("  " + _why(decision, evidence_by_action.get(decision.action_id)))
        if decision.missing_required_goals:
            lines.append("  Missing required goals: " + ", ".join(decision.missing_required_goals) + ".")
    return lines


def _why(decision: Decision, evidence_row: dict[str, Any] | None) -> str:
    deontic = decision.norm_status
    opinion = (evidence_row or {}).get("opinion", {})
    op = ""
    if opinion:
        op = f" PeTTaChainer belief b={opinion['b']}, d={opinion['d']}, u={opinion['u']}."
    if deontic == "forbidden":
        return f"lib_deontic derived this action forbidden, so the score is forced negative.{op}"
    if deontic == "obligated":
        return f"lib_deontic derived this action obligated (the norm positively requires it).{op}"
    if deontic == "permitted":
        return f"lib_deontic derived this action permitted (allowed, not required).{op}"
    return f"lib_deontic left this action unregulated.{op}"

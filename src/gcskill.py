"""OmegaClaw skill entry for GoalChainer.

OmegaClaw Core dispatches a skill by `eval`-ing the command the agent emits, which
`py-call`s a two-part `module.function` (e.g. `agentverse.technical_analysis`).
PeTTa's py-call cannot resolve a three-part path, so this single top-level module is
the callable surface: `(py-call (gcskill.decision "..."))`. It returns short, plain
strings (the agent reads the result as feedback), wrapping the full pipeline in
`goal_chainer.omegaclaw_skill`.
"""

from __future__ import annotations

from typing import Any

from goal_chainer.omegaclaw_skill import (
    decision_payload,
    motivation_payload,
    snars_payload,
    solve_payload,
    system_prompt_payload,
)


def _recommended(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    return next((d for d in decisions if d["status"] == "recommended"), decisions[0])


def _blocked(decisions: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((d for d in decisions if d["status"] == "blocked"), None)


def _reasoning_lines(decisions: list[dict[str, Any]], motivation: dict[str, Any] | None) -> list[str]:
    """The shared 'why' lines: the blocked alternative and the motivation consensus."""
    lines: list[str] = []
    blocked = _blocked(decisions)
    if blocked:
        lines.append(f"  blocked:     {blocked['action_id']}  (lib_deontic: {blocked['norm_status']})")
    if motivation:
        lines.append(
            f"  individual -> {motivation['goal_pull']['individual']} ; "
            f"collective -> {motivation['goal_pull']['collective']}"
        )
        lines.append(f"  consensus (MetaMo): {motivation['consensus']}")
    return lines


def system_prompt() -> str:
    return system_prompt_payload()["prompt"]


def decision(request: str) -> str:
    payload = decision_payload(request)
    decisions = payload["decisions"]
    top = _recommended(decisions)
    lines = [
        "DECISION (GoalChainer on PeTTa: lib_deontic + PeTTaChainer + MetaMo)",
        f"  recommended: {top['action_id']}  (score {top['score']})",
    ]
    lines.extend(_reasoning_lines(decisions, payload.get("motivation")))
    return "\n".join(lines)


def solve(request: str) -> str:
    payload = solve_payload(request)
    executed = payload["executed"]
    leak = executed["leak_check"]
    lines = [
        f"SOLVE: decided {payload['decided']} ({payload['status']}), channel {executed['channel']}",
    ]
    lines.extend(_reasoning_lines(payload.get("decisions", []), payload.get("motivation")))
    artifact = executed.get("artifact")
    if artifact and "diagnostics" in artifact:
        kept = artifact["diagnostics"].get("error_code")
        redacted = [k for k, v in artifact["diagnostics"].items() if v == "[redacted]"]
        lines.append(f"  redacted: {', '.join(redacted)}")
        lines.append(f"  kept: error_code={kept}")
    lines.append(f"  leak check: safe={leak['safe']} leaked={leak['leaked']}")
    return "\n".join(lines)


def motivation(request: str) -> str:
    payload = motivation_payload(request)
    if not payload.get("consensus"):
        return "motivation: MetaMo runtime unavailable"
    return (
        f"MOTIVATION: individual -> {payload['goal_pull']['individual']} ; "
        f"collective -> {payload['goal_pull']['collective']} ; "
        f"consensus -> {payload['consensus']}"
    )


def snars(request: str) -> str:
    payload = snars_payload(request)
    if not payload.get("opinion"):
        return "snars: runtime unavailable"
    op = payload["opinion"]
    return (
        f"SNARS: {payload['claim']}  (derived={payload.get('derived')})  "
        f"opinion b={op['b']} d={op['d']} u={op['u']}"
    )

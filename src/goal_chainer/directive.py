"""Feed the GoalChainer decision into OmegaClaw's directive (task) layer on PeTTa.

This closes the loop: once the decision is made, the recommended action becomes a
claimable task in OmegaClaw Core's `lib_directive`, the obligated action is ready,
the forbidden action is blocked, and a permitted alternative sits in the backlog.

The deontic-status -> task-state mapping is a Prolog relation injected into PeTTa
and called as a MeTTa function. PeTTa exposes `assertzPredicate` / `Predicate` /
`import_prolog_function` (see `metta.pl`), so the relation is defined as Prolog
clauses, registered, and then `(gc_task_state obligated)` returns `ready` from
MeTTa. That is "inject Prolog, use it as MeTTa", used to drive the plan.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from .deontic_engine import ACTION_ORDER
from .petta_runtime import run_metta

# Inject the deontic -> task-state relation as Prolog clauses, then register it as
# a MeTTa-callable function.
PROLOG_INJECTION = (
    "!(assertzPredicate (Predicate (gc_task_state obligated ready)))",
    "!(assertzPredicate (Predicate (gc_task_state forbidden blocked)))",
    "!(assertzPredicate (Predicate (gc_task_state permitted backlog)))",
    "!(assertzPredicate (Predicate (gc_task_state unregulated backlog)))",
    "!(import_prolog_function gc_task_state)",
)
TASK_STATES = ("ready", "blocked", "backlog")
AGENT = "responder"

_LIST_RE = {
    "ready": re.compile(r"\(ready \(([^)]*)\)\)"),
    "blocked": re.compile(r"\(blocked \(([^)]*)\)\)"),
    "claimed": re.compile(r"\(claimed \(([^)]*)\)\)"),
}
_NEXT_RE = re.compile(r"\(assign (?P<task>[a-z_]+) (?P<agent>[a-z_]+) (?P<rule>[a-z_-]+)\)")
_CLAIM_RE = re.compile(r"\(claimed (?P<task>[a-z_]+) (?P<version>\d+)\)")


def register_directive(deontic_by_action: dict[str, str]) -> dict[str, Any]:
    """Classify each action via injected Prolog, build a plan, schedule and claim."""

    states, classification_output = classify_task_states(deontic_by_action)
    plan = build_plan(states)
    ready_actions = [action for action in ACTION_ORDER if states.get(action) == "ready"]

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".metta", encoding="utf-8") as handle:
        plan_path = Path(handle.name)
        handle.write(plan)
    try:
        status, next_actions = _read_plan(plan_path)
        claim = _claim(plan_path, ready_actions[0]) if ready_actions else None
    finally:
        plan_path.unlink(missing_ok=True)

    return {
        "skill": "goalchainer-directive",
        "runtime": "OmegaClaw-Core lib_directive on PeTTa",
        "prolog_injection": {
            "relation": "gc_task_state/2 (deontic -> task state)",
            "mechanism": "assertzPredicate + Predicate + import_prolog_function",
            "classification": dict(zip(ACTION_ORDER, classification_output)),
        },
        "task_states": states,
        "plan": plan,
        "status": status,
        "next_actions": next_actions,
        "claim": claim,
    }


def classify_task_states(deontic_by_action: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    calls = [f"!(gc_task_state {deontic_by_action.get(action, 'unregulated')})" for action in ACTION_ORDER]
    program = "\n".join((*PROLOG_INJECTION, *calls)) + "\n"
    outputs = run_metta(program)
    states = [line for line in outputs if line in TASK_STATES]
    if len(states) != len(ACTION_ORDER):
        raise RuntimeError(f"injected gc_task_state returned {states} for {ACTION_ORDER}")
    return dict(zip(ACTION_ORDER, states)), states


def build_plan(states: dict[str, str]) -> str:
    lines = [
        '(meta plan (id "GC-INCIDENT") (title "GoalChainer incident decision")'
        ' (version "1.0.0") (status "active") (created "2026-06-28") (author "agent:goalchainer"))',
        f"(given agent-{AGENT}-available)",
    ]
    for action in ACTION_ORDER:
        lines.append(f"(given task-{action})")
    for action in ACTION_ORDER:
        state = states.get(action, "backlog")
        if state == "ready":
            lines += [
                f"(given no-deps-{action})",
                f"(normally r-{action} (and task-{action} no-deps-{action}) ready-{action})",
                f"(normally assign-{action} (and ready-{action} agent-{AGENT}-available)"
                f" assign-to-{action}-{AGENT})",
            ]
        elif state == "blocked":
            lines += [
                f"(given forbid-{action})",
                f"(normally blk-{action} forbid-{action} blocked-{action})",
            ]
        # backlog: the bare task with no readiness rule stays in the backlog.
    return "\n".join(lines) + "\n"


def _read_plan(plan_path: Path) -> tuple[dict[str, list[str]], list[dict[str, str]]]:
    driver = (
        "!(import! &self (library OmegaClaw-Core lib_directive))\n"
        f'!(directive-status "{plan_path}")\n'
        f'!(directive-next "{plan_path}")\n'
    )
    outputs = run_metta(driver)
    status = {key: [] for key in _LIST_RE}
    next_actions: list[dict[str, str]] = []
    for line in outputs:
        for key, pattern in _LIST_RE.items():
            found = pattern.search(line)
            if found:
                status[key] = found.group(1).split()
        for match in _NEXT_RE.finditer(line):
            next_actions.append(match.groupdict())
    return status, next_actions


def _claim(plan_path: Path, task: str) -> dict[str, Any]:
    driver = (
        "!(import! &self (library OmegaClaw-Core lib_directive))\n"
        f'!(directive-claim "{plan_path}" {task} {AGENT} False)\n'
    )
    outputs = run_metta(driver)
    for line in outputs:
        match = _CLAIM_RE.search(line)
        if match:
            return {"task": match.group("task"), "version": int(match.group("version")), "agent": AGENT}
    return {"task": task, "error": outputs}

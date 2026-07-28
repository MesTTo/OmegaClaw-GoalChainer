"""Shared decide-and-execute pipeline, used by the CLI and the skill bridge."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .execute import default_incident, execute_action
from .hyperbase import build_hyperbase_packet
from .metta_reasoner import HyperBaseMettaReasoner
from .ontology import load_colore_context
from .scenarios import incident_response_scenario
from .scoring import DecisionEngine


def decide_incident(
    request: str,
    *,
    mode: str | None = None,
    store_path: str | Path | None = None,
    execute=None,
) -> dict[str, Any]:
    """Run the native decision path or the explicitly labelled offline path."""

    selected_mode = _decision_mode(mode)
    if selected_mode == "native":
        from .snars_decision import native_decision_payload

        return native_decision_payload(
            request,
            store_path=store_path,
            execute=execute,
        )
    return _offline_decision(request)


def solve_incident(
    request: str,
    *,
    mode: str | None = None,
    store_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run the full decision and execute the recommended action on real data.

    solve decides AND executes, so the report carries the same ranked decisions and
    motivation consensus a bare goalchainer-decision returns, then the executed,
    leak-checked deliverable. One genuine command tells the whole story.
    """
    incident = default_incident()
    report = decide_incident(
        request,
        mode=mode,
        store_path=store_path,
        execute=lambda action_id: execute_action(action_id, incident),
    )
    decisions = report["decisions"]
    recommended = next(
        (decision for decision in decisions if decision["status"] == "recommended"),
        decisions[0],
    )
    executed = report.get("execution")
    if executed is None:
        executed = execute_action(recommended["action_id"], incident)
    authorized = executed.get("authorized", True)
    return {
        "request": request,
        "mode": report["mode"],
        "native_snars_ran": report["native_snars_ran"],
        "runtime": report["runtime"],
        "state": report.get("state"),
        "decided": recommended["action_id"] if authorized else None,
        "label": recommended["label"],
        "status": recommended["status"] if authorized else "requires-selection",
        "decisions": decisions,
        "motivation": report.get("motivation"),
        "feedback": report.get("feedback"),
        "incident": incident,
        "executed": executed,
    }


def _offline_decision(request: str) -> dict[str, Any]:
    from .motivation import available as metamo_available
    from .motivation import consensus_decision
    from .motivation import summary as motivation_summary

    scenario = incident_response_scenario(request)
    hyperbase = build_hyperbase_packet(request, load_colore_context())
    reasoner = HyperBaseMettaReasoner(hyperbase["reasoner"])
    motivation = (
        consensus_decision(scenario, reasoner)
        if metamo_available()
        else None
    )
    scores = motivation["consensus_scores"] if motivation else {}
    decisions = DecisionEngine(reasoner, scores).rank(scenario)
    return {
        "request": request,
        "mode": "offline",
        "native_snars_ran": False,
        "runtime": {
            "reasoner": reasoner.source,
            "native_execution": hyperbase["reasoner"]["execution"],
            "warning": "Native Mettabase SNARS did not run.",
        },
        "scenario": {
            "title": scenario.title,
            "notes": list(scenario.notes),
        },
        "hyperbase": hyperbase,
        "goals": [
            {
                "id": goal.id,
                "owner": goal.owner,
                "statement": goal.statement,
                "weight": goal.weight,
                "kind": goal.kind,
                "required": goal.required,
            }
            for goal in scenario.goals
        ],
        "decisions": [decision.to_dict() for decision in decisions],
        "motivation": motivation_summary(motivation),
    }


def _decision_mode(mode: str | None) -> str:
    value = mode or os.environ.get("GOALCHAINER_MODE", "native")
    normalized = value.strip().lower()
    if normalized not in {"native", "offline"}:
        raise ValueError("GoalChainer mode must be native or offline.")
    return normalized


__all__ = ["decide_incident", "solve_incident"]

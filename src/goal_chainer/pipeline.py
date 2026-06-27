"""Shared decide-and-execute pipeline, used by the CLI and the skill bridge."""

from __future__ import annotations

from typing import Any

from .execute import default_incident, execute_action
from .hyperbase import build_hyperbase_packet
from .metta_reasoner import HyperBaseMettaReasoner
from .ontology import load_colore_context
from .scenarios import incident_response_scenario
from .scoring import DecisionEngine


def solve_incident(request: str) -> dict[str, Any]:
    """Run the full decision and execute the recommended action on real data.

    solve decides AND executes, so the report carries the same ranked decisions and
    motivation consensus a bare goalchainer-decision returns, then the executed,
    leak-checked deliverable. One genuine command tells the whole story.
    """
    from .motivation import available as metamo_available
    from .motivation import consensus_decision
    from .motivation import summary as motivation_summary

    scenario = incident_response_scenario(request)
    hyperbase = build_hyperbase_packet(request, load_colore_context())
    reasoner = HyperBaseMettaReasoner(hyperbase["reasoner"])
    motivation = consensus_decision(scenario, reasoner) if metamo_available() else None
    scores = motivation["consensus_scores"] if motivation else {}
    decisions = DecisionEngine(reasoner, scores).rank(scenario)
    recommended = next((d for d in decisions if d.status == "recommended"), decisions[0])
    incident = default_incident()
    return {
        "request": request,
        "decided": recommended.action_id,
        "label": recommended.label,
        "status": recommended.status,
        "decisions": [decision.to_dict() for decision in decisions],
        "motivation": motivation_summary(motivation),
        "incident": incident,
        "executed": execute_action(recommended.action_id, incident),
    }

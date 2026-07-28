"""Native SNARS decision orchestration for the incident scenario."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, TypedDict, Unpack

from .deontic_engine import derive_deontic
from .evidence import IncidentEvidence
from .motivation import available as metamo_available
from .motivation import consensus_decision
from .motivation import summary as motivation_summary
from .scenarios import incident_scenario
from .scoring import DecisionEngine
from .snars_models import (
    EvidenceCounts,
    SnarsBelief,
    SnarsProtocolError,
    SnarsRequestContext,
)
from .snars_reasoner import SnarsActionReasoner, SnarsSession
from .snars_runtime import SnarsRuntime

REQUEST_SOURCE = "goalchainer:request"
GOAL_SOURCE = "goalchainer:scenario"
ExecuteCallback = Callable[[str], dict[str, Any]]
OrchestrateCallback = Callable[
    [str, dict[str, str], ExecuteCallback],
    tuple[dict[str, Any], dict[str, Any]],
]


class NativeDecisionOptions(TypedDict, total=False):
    store_path: str | Path | None
    runtime: SnarsRuntime | None
    execute: ExecuteCallback | None
    orchestrate: OrchestrateCallback | None


def native_decision(
    request: str,
    *,
    store_path: str | Path | None = None,
    runtime: SnarsRuntime | None = None,
    execute: ExecuteCallback | None = None,
    orchestrate: OrchestrateCallback | None = None,
) -> dict[str, Any]:
    """Run parsed SH evidence through SNARS, lib_deontic, MetaMo, and scoring."""

    native_runtime = runtime or SnarsRuntime(require_text_ingestion=True)
    session = (
        SnarsSession.ephemeral(native_runtime)
        if store_path is None
        else SnarsSession.persistent(native_runtime, store_path)
    )
    with session:
        session.ingest_text(request, source=REQUEST_SOURCE)
        ingestion = session.last_ingestion_payload
        context = session.request_context()
        evidence = _incident_evidence(request, context)
        scenario = incident_scenario(evidence)

        registered_goals = []
        subgoals = []
        for goal in scenario.goals:
            statement = session.builder.codec.emit(
                session.builder.codec.binary_statement(
                    "goal",
                    goal.id,
                    goal.statement,
                )
            )
            registered_goals.append(
                session.register_goal(
                    statement,
                    owner=goal.owner,
                    kind=goal.kind,
                    desire=goal.weight,
                    required=goal.required,
                    source=GOAL_SOURCE,
                )
            )
            subgoals.append(session.subgoals(statement).payload)

        assessments = session.assess_actions()
        deontic = derive_deontic(evidence)
        reasoner = SnarsActionReasoner(
            assessments,
            deontic.status_by_action,
            session=session,
        )
        motivation = (
            consensus_decision(scenario, reasoner)
            if metamo_available()
            else None
        )
        scores = motivation["consensus_scores"] if motivation else {}
        decisions = DecisionEngine(reasoner, scores).rank(scenario)
        ranking = reasoner.score_audit
        if ranking is None:
            raise SnarsProtocolError(
                "Native SNARS scorer returned no ranking audit."
            )

        counterfactual = _public_raw_counterfactual(session)
        execution = None
        orchestration = None
        feedback = None
        if execute is not None and ranking["automatic"]:
            selected = decisions[0]
            trust_before = session.trust().payload
            if orchestrate is None:
                execution = execute(selected.action_id)
            else:
                execution, orchestration = orchestrate(
                    selected.action_id,
                    deontic.status_by_action,
                    execute,
                )
            safe = bool(execution.get("leak_check", {}).get("safe"))
            feedback = session.record_outcome(
                _action_property(session, selected.action_id, "acceptable"),
                evidence=(
                    EvidenceCounts(1.0, 0.0, 0.5)
                    if safe
                    else EvidenceCounts(0.0, 1.0, 0.5)
                ),
                source="goalchainer:execution",
            ).payload
            trust_after = session.trust().payload
            feedback = {
                "safe": safe,
                "native_outcome": feedback,
                "trust_before": trust_before,
                "trust_after": trust_after,
            }
        elif execute is not None:
            execution = {
                "authorized": False,
                "reason": "SNARS ranking is tied or has no recommended action.",
                "tied": ranking["tied"],
            }
        return {
            "mode": "native",
            "native_snars_ran": True,
            "state": session.state_payload(),
            "runtime": _runtime_payload(native_runtime),
            "scenario": scenario,
            "evidence": evidence,
            "request_context": context,
            "ingestion": ingestion,
            "registered_goals": registered_goals,
            "subgoals": subgoals,
            "assessments": assessments,
            "deontic": deontic,
            "motivation": motivation_summary(motivation),
            "decisions": decisions,
            "ranking": ranking,
            "counterfactual": counterfactual,
            "execution": execution,
            "orchestration": orchestration,
            "feedback": feedback,
        }


def native_decision_payload(
    request: str,
    **options: Unpack[NativeDecisionOptions],
) -> dict[str, Any]:
    """Return the native decision as a JSON-compatible audit payload."""

    result = native_decision(request, **options)
    scenario = result["scenario"]
    evidence = result["evidence"]
    deontic = result["deontic"]
    decisions = result["decisions"]
    return {
        "request": request,
        "mode": result["mode"],
        "native_snars_ran": result["native_snars_ran"],
        "state": result["state"],
        "runtime": result["runtime"],
        "scenario": {
            "title": scenario.title,
            "notes": list(scenario.notes),
        },
        "evidence": evidence.to_dict(),
        "ingestion": result["ingestion"],
        "request_context": _context_payload(result["request_context"]),
        "goals": [asdict(goal) for goal in result["registered_goals"]],
        "subgoals": result["subgoals"],
        "assessments": [
            {
                "action_id": row.action_id,
                "acceptable": _belief_payload(row.acceptable),
                "risky": _belief_payload(row.risky),
                "forbidden": _belief_payload(row.forbidden),
                "conflict_degree": row.conflict_degree,
            }
            for row in result["assessments"]
        ],
        "deontic": {
            "status_by_action": deontic.status_by_action,
            "theory": deontic.theory,
            "conclusions": deontic.conclusions,
        },
        "decisions": [decision.to_dict() for decision in decisions],
        "ranking": result["ranking"],
        "motivation": result["motivation"],
        "counterfactual": _counterfactual_payload(result["counterfactual"]),
        "execution": result["execution"],
        "orchestration": result["orchestration"],
        "feedback": result["feedback"],
    }


def _incident_evidence(
    request: str,
    context: SnarsRequestContext,
) -> IncidentEvidence:
    sensitive = _supported(context.sensitive)
    public = _supported(context.public)
    unverified = _supported(context.unverified)
    coordination = _supported(context.coordination)
    return IncidentEvidence(
        request=request,
        sensitive_categories=("parsed sensitive data",) if sensitive else (),
        public_declared=public,
        facts_ready=not unverified,
        coordination_needed=coordination,
        propositions=tuple(
            belief.canonical_statement
            for belief in (
                context.sensitive,
                context.public,
                context.unverified,
                context.coordination,
            )
            if _supported(belief)
        ),
        provenance="mettabase-snars",
        concept_scores={
            "sensitive": context.sensitive.opinion.expectation,
            "public": context.public.opinion.expectation,
            "unverified": context.unverified.opinion.expectation,
            "coordination": context.coordination.opinion.expectation,
        },
        risk_grounding="Mettabase SH labels and native SNARS receipts",
    )


def _supported(belief: SnarsBelief) -> bool:
    return belief.evidence.positive > 0.0 and belief.opinion.expectation > 0.5


def _public_raw_counterfactual(session: SnarsSession):
    hypothesis = session.builder.codec.emit(
        session.builder.codec.binary_statement(
            "has-property",
            "request",
            "public-data",
        )
    )
    query = session.builder.codec.emit(
        session.builder.codec.binary_statement(
            "has-property",
            "publish_raw_log",
            "acceptable",
        )
    )
    return session.what_if(
        hypothesis,
        query,
        source="goalchainer:counterfactual",
    )


def _action_property(
    session: SnarsSession,
    action_id: str,
    property_name: str,
) -> str:
    return session.builder.codec.emit(
        session.builder.codec.binary_statement(
            "has-property",
            action_id,
            property_name,
        )
    )


def _runtime_payload(runtime: SnarsRuntime) -> dict[str, Any]:
    diagnostics = runtime.diagnostics
    return {
        "reasoner": "mettabase-snars-on-petta",
        "mettabase_dir": str(diagnostics.mettabase_dir),
        "mettabase_commit": diagnostics.mettabase_commit,
        "snars_program": str(diagnostics.snars_program),
        "petta_dir": str(diagnostics.petta_dir),
        "petta_main": str(diagnostics.petta_main),
        "swipl": str(diagnostics.swipl),
    }


def _context_payload(context: SnarsRequestContext) -> dict[str, Any]:
    return {
        field_name: _belief_payload(getattr(context, field_name))
        for field_name in (
            "sensitive",
            "public",
            "unverified",
            "coordination",
        )
    }


def _belief_payload(belief: SnarsBelief) -> dict[str, Any]:
    return {
        "statement_id": belief.statement_id,
        "canonical_statement": belief.canonical_statement,
        "opinion": {
            **asdict(belief.opinion),
            "expectation": belief.opinion.expectation,
        },
        "evidence": asdict(belief.evidence),
        "receipts": [asdict(receipt) for receipt in belief.receipts],
        "proofs": [asdict(proof) for proof in belief.proofs],
        "sources": list(belief.sources),
    }


def _counterfactual_payload(counterfactual) -> dict[str, Any]:
    return {
        "hypothesis": counterfactual.hypothesis,
        "query": counterfactual.query,
        "opinion": {
            **asdict(counterfactual.opinion),
            "expectation": counterfactual.opinion.expectation,
        },
        "proofs": [asdict(proof) for proof in counterfactual.proofs],
        "state_before": counterfactual.state_before,
        "state_after": counterfactual.state_after,
        "digest_before": counterfactual.digest_before,
        "digest_after": counterfactual.digest_after,
        "rolled_back": (
            counterfactual.state_before == counterfactual.state_after
            and counterfactual.digest_before == counterfactual.digest_after
        ),
    }


__all__ = ["native_decision", "native_decision_payload"]

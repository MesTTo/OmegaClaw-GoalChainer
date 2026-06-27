"""Differential evidence that the decision depends on the input.

This runs the full native pipeline (evidence -> NAL premises -> derived deontic
status -> ranking) over a battery of contrasting requests and checks that the
decision changes as it should. It is the acceptance test for the claim that the
reasoning is not hardcoded: the same code, given different requests, blocks the
raw log in one case and recommends it in another.

Run it as `python -m goal_chainer.cli validate` or via the test that wraps it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .hyperbase import build_hyperbase_packet
from .metta_reasoner import HyperBaseMettaReasoner
from .scenarios import incident_response_scenario
from .scoring import DecisionEngine


@dataclass(frozen=True)
class ValidationCase:
    name: str
    request: str
    summary: str


CASES: tuple[ValidationCase, ...] = (
    ValidationCase(
        name="pii_incident",
        request=(
            "Checkout is down. Engineering wants to paste raw logs into the incident "
            "room. Support says the logs may include customer emails, order IDs, and "
            "request payloads."
        ),
        summary="sensitive data present, facts ready",
    ),
    ValidationCase(
        name="public_no_data",
        request=(
            "The outage is resolved. There is no sensitive data in this status, it is "
            "safe to share publicly with engineering and support."
        ),
        summary="no sensitive data, declared safe to share",
    ),
    ValidationCase(
        name="facts_not_ready",
        request=(
            "Checkout is down. Engineering wants to share raw logs with customer emails "
            "and order IDs, but the root cause is unknown and the facts are not ready."
        ),
        summary="sensitive data present, facts not ready",
    ),
)


def run_validation() -> dict[str, Any]:
    results = [_run_case(case) for case in CASES]
    raw_status = {result["name"]: result["deontic"]["publish_raw_log"] for result in results}
    top_action = {result["name"]: result["top_action"] for result in results}

    cross_checks = [
        _check(
            "raw log forbidden only when privacy is at stake",
            raw_status["pii_incident"] == "forbidden"
            and raw_status["public_no_data"] != "forbidden",
        ),
        _check(
            "the recommended action differs across the three requests",
            len({top_action["pii_incident"], top_action["public_no_data"], top_action["facts_not_ready"]})
            >= 2,
        ),
    ]
    passed = all(result["passed"] for result in results) and all(c["passed"] for c in cross_checks)
    return {
        "passed": passed,
        "cases": results,
        "cross_checks": cross_checks,
        "raw_log_status_by_case": raw_status,
        "top_action_by_case": top_action,
    }


def _run_case(case: ValidationCase) -> dict[str, Any]:
    scenario = incident_response_scenario(case.request)
    hyperbase = build_hyperbase_packet(case.request)
    reasoner = HyperBaseMettaReasoner(hyperbase["reasoner"])
    decisions = DecisionEngine(reasoner).rank(scenario)
    by_id = {decision.action_id: decision for decision in decisions}
    deontic = {action_id: decision.norm_status for action_id, decision in by_id.items()}
    top = decisions[0]
    checks = _case_checks(case.name, by_id, top)
    return {
        "name": case.name,
        "summary": case.summary,
        "request": case.request,
        "evidence": hyperbase["evidence"],
        "top_action": top.action_id,
        "deontic": deontic,
        "ranking": [
            {
                "action_id": decision.action_id,
                "status": decision.status,
                "score": round(decision.score, 4),
                "deontic": decision.norm_status,
                "evidence_strength": round(decision.evidence.strength, 4),
            }
            for decision in decisions
        ],
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
    }


def _case_checks(name: str, by_id: dict[str, Any], top: Any) -> list[dict[str, Any]]:
    raw = by_id["publish_raw_log"]
    if name == "pii_incident":
        return [
            _check("raw log is blocked", raw.status == "blocked"),
            _check("raw log deontic is forbidden", raw.norm_status == "forbidden"),
            _check("redacted summary is recommended", top.action_id == "publish_redacted_summary"),
        ]
    if name == "public_no_data":
        return [
            _check("raw log is not blocked", raw.status != "blocked"),
            _check("raw log deontic is permitted", raw.norm_status == "permitted"),
        ]
    if name == "facts_not_ready":
        return [
            _check("raw log is blocked", raw.status == "blocked"),
            _check("holding outranks publishing", top.action_id == "hold_external_update"),
        ]
    return []


def _check(label: str, condition: bool) -> dict[str, Any]:
    return {"check": label, "passed": bool(condition)}

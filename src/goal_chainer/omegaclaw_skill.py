"""OmegaClaw skill bridge for GoalChainer decisions."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .deontic import resolve_norms
from .hyperbase import build_hyperbase_packet, restricted_items
from .ontology import load_colore_context
from .petta_bridge import reasoner_from_env
from .scenarios import incident_response_scenario
from .scoring import DecisionEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
PETTACHAINER_DIR = Path(os.environ.get("PETTACHAINER_DIR", "/home/user/Dev/PeTTaChainer"))


def goalchainer_decision(request: str) -> str:
    return _json_for_skill(decision_payload(request))


def goalchainer_proof_audit(request: str) -> str:
    return _json_for_skill(proof_audit_payload(request))


def goalchainer_ontology_context(request: str) -> str:
    return _json_for_skill(ontology_context_payload(request))


def goalchainer_tests(request: str = "") -> str:
    return _json_for_skill(test_payload(request))


def run_skill(name: str, request: str) -> dict[str, Any]:
    normalized = name.replace("_", "-").removeprefix("omegaclaw.")
    if normalized == "goalchainer-decision":
        return decision_payload(request)
    if normalized == "goalchainer-proof-audit":
        return proof_audit_payload(request)
    if normalized == "goalchainer-ontology-context":
        return ontology_context_payload(request)
    if normalized == "goalchainer-tests":
        return test_payload(request)
    raise ValueError(f"unknown GoalChainer skill: {name}")


def decision_payload(request: str) -> dict[str, Any]:
    scenario = incident_response_scenario()
    ontology = load_colore_context()
    hyperbase = build_hyperbase_packet(request, ontology)
    reasoner_error = None
    try:
        decisions = DecisionEngine(reasoner_from_env()).rank(scenario)
        reasoner_mode = decisions[0].evidence.source if decisions else "none"
    except Exception as exc:
        reasoner_error = f"{type(exc).__name__}: {exc}"
        decisions = DecisionEngine().rank(scenario)
        reasoner_mode = "scenario-default"
    decision_dicts = [decision.to_dict() for decision in decisions]
    recommended = _best_decision(decision_dicts, "recommended") or decision_dicts[0]
    blocked = _best_decision(decision_dicts, "blocked")
    weak = _best_decision(decision_dicts, "weak") or _best_decision(decision_dicts, "candidate")

    return {
        "skill": "goalchainer-decision",
        "request": _compact(request),
        "scenario": {
            "title": scenario.title,
            "match": _scenario_match(request),
            "notes": list(scenario.notes),
        },
        "runtime": {
            "reasoner": reasoner_mode,
            "reasoner_error": reasoner_error,
        },
        "ontology": {
            "source_available": ontology.source_available,
            "source_path": str(ontology.source_path),
            "module_count": ontology.module_count,
            "axiom_count": ontology.axiom_count,
            "predicate_count": ontology.predicate_count,
            "projection_rules": list(ontology.projection_rules),
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
        "choices": [
            {
                "id": action.id,
                "label": action.label,
                "description": action.description,
                "satisfies": list(action.satisfies),
                "evidence_query": action.evidence_query,
                "default_strength": action.default_strength,
            }
            for action in scenario.actions
        ],
        "norms": _norm_payload(scenario),
        "decisions": decision_dicts,
        "counterfactuals": _counterfactuals(recommended, blocked, weak),
        "release_plan": _release_plan(request, recommended, blocked, weak),
    }


def ontology_context_payload(request: str) -> dict[str, Any]:
    ontology = load_colore_context()
    return {
        "skill": "goalchainer-ontology-context",
        "request": _compact(request),
        "ontology": ontology.to_dict(),
        "hyperbase": build_hyperbase_packet(request, ontology),
    }


def proof_audit_payload(request: str) -> dict[str, Any]:
    result_path = PETTACHAINER_DIR / "artifacts/showcase/showcase-result.json"
    packet_path = PETTACHAINER_DIR / "artifacts/showcase/showcase-forensic-packet.json"
    verdict_path = PETTACHAINER_DIR / "artifacts/showcase/showcase-audit-verdict.md"
    verifier_path = PETTACHAINER_DIR / "artifacts/showcase/showcase-verify-all.py"

    payload: dict[str, Any] = {
        "skill": "goalchainer-proof-audit",
        "request": _compact(request),
        "pettachainer_path": str(PETTACHAINER_DIR),
        "available": result_path.exists() and packet_path.exists(),
    }
    if not payload["available"]:
        payload["error"] = "PeTTaChainer showcase artifacts were not found"
        return payload

    result = _read_json(result_path)
    packet = _read_json(packet_path)
    incident = result.get("incident", {})
    truth_values = incident.get("truth_values", {})
    proof = packet.get("proof_structure", {})
    red_team = packet.get("red_team", {})
    dispatch = result.get("dispatch", {}).get("timings", [])
    noise_stability = result.get("noise_stability", [])

    payload.update(
        {
            "forensic_packet": {
                "verifier_checks_pass": packet.get("verdict", {}).get("verifier_checks_pass"),
                "red_team_rejections_pass": packet.get("verdict", {}).get("red_team_rejections_pass"),
                "packet_root_sha256": packet.get("packet_root_sha256"),
            },
            "incident_proof": {
                "facts": incident.get("facts"),
                "rules": incident.get("rules"),
                "noise_edges": incident.get("noise_edges"),
                "truth_values": truth_values,
                "certificate_passes": proof.get("certificate_passes"),
                "proof_sha256": proof.get("proof_sha256"),
                "operator_counts": proof.get("operator_counts"),
            },
            "routing": {
                "timings": dispatch,
                "best_path": _best_dispatch_path(dispatch),
            },
            "noise_stability": noise_stability[-1] if noise_stability else None,
            "red_team": {
                "case_count": red_team.get("case_count"),
                "mutation_families": red_team.get("mutation_families"),
            },
            "audit_verdict": _extract_verdict_lines(verdict_path),
        }
    )

    if verifier_path.exists():
        payload["verifier"] = _run_verifier(verifier_path)
    return payload


def test_payload(request: str) -> dict[str, Any]:
    collected = _run(
        ["python3", "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT,
        env={"PYTHONPATH": "src"},
    )
    result = _run(["python3", "-m", "pytest", "-q"], cwd=REPO_ROOT, env={"PYTHONPATH": "src"})
    return {
        "skill": "goalchainer-tests",
        "request": _compact(request),
        "collect_exit": collected.returncode,
        "test_exit": result.returncode,
        "collected_tests": [
            line.strip() for line in collected.stdout.splitlines() if "::test_" in line
        ],
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _norm_payload(scenario) -> list[dict[str, Any]]:
    rows = []
    for action in scenario.actions:
        resolution = resolve_norms(action.id, scenario.norms)
        rows.append(
            {
                "action_id": action.id,
                "status": resolution.status,
                "blocks_action": resolution.blocks_action,
                "priority": resolution.priority,
                "reasons": list(resolution.reasons),
            }
        )
    return rows


def _counterfactuals(
    recommended: dict[str, Any],
    blocked: dict[str, Any] | None,
    weak: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    rows = [
        {
            "case": "selected",
            "action_id": recommended["action_id"],
            "label": recommended["label"],
            "status": recommended["status"],
            "satisfied_goals": recommended["satisfied_goals"],
            "missing_required_goals": recommended["missing_required_goals"],
            "norm_status": recommended["norm_status"],
            "score": recommended["score"],
        }
    ]
    for case, decision in (("blocked_alternative", blocked), ("weak_alternative", weak)):
        if decision is None:
            continue
        rows.append(
            {
                "case": case,
                "action_id": decision["action_id"],
                "label": decision["label"],
                "status": decision["status"],
                "satisfied_goals": decision["satisfied_goals"],
                "missing_required_goals": decision["missing_required_goals"],
                "norm_status": decision["norm_status"],
                "score": decision["score"],
            }
        )
    return rows


def _release_plan(
    request: str,
    recommended: dict[str, Any],
    blocked: dict[str, Any] | None,
    weak: dict[str, Any] | None,
) -> dict[str, Any]:
    restricted = _restricted_items(request)
    plan = {
        "selected_action": recommended["action_id"],
        "selected_label": recommended["label"],
        "publish_external": _customer_update(request),
        "publish_internal": [
            "redacted incident summary",
            "affected surface and current mitigation",
            "owner, next check, and facts already verified",
        ],
        "keep_restricted": restricted,
        "human_review_gate": "security owner checks the redaction before any external update",
    }
    if blocked is not None:
        plan["blocked_action"] = {
            "action_id": blocked["action_id"],
            "label": blocked["label"],
            "status": blocked["status"],
            "norm_status": blocked["norm_status"],
            "missing_required_goals": blocked["missing_required_goals"],
        }
    if weak is not None:
        plan["weaker_fallback"] = {
            "action_id": weak["action_id"],
            "label": weak["label"],
            "status": weak["status"],
            "missing_required_goals": weak["missing_required_goals"],
        }
    return plan


def _customer_update(request: str) -> str:
    surface = "checkout" if "checkout" in request.lower() else "service"
    return (
        f"We are investigating a {surface} issue and are working to restore service. "
        "We will share verified updates as facts are confirmed."
    )


def _restricted_items(request: str) -> list[str]:
    return restricted_items(request)


def _scenario_match(request: str) -> dict[str, bool]:
    lower = request.lower()
    return {
        "service_outage": any(word in lower for word in ("down", "outage", "failing", "restore")),
        "customer_data_risk": any(word in lower for word in ("customer", "email", "order", "payload", "pii")),
        "team_coordination": any(word in lower for word in ("engineering", "support", "responders", "coordinate")),
    }


def _best_decision(decisions: list[dict[str, Any]], status: str) -> dict[str, Any] | None:
    matches = [decision for decision in decisions if decision["status"] == status]
    if not matches:
        return None
    return max(matches, key=lambda item: float(item["score"]))


def _best_dispatch_path(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return min(rows, key=lambda item: float(item.get("median_s", 999999)))


def _extract_verdict_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    wanted = ("Verdict:", "Claims verified:", "Evidence sources sealed:", "Red-team cases:")
    lines = []
    for line in path.read_text().splitlines():
        stripped = line.lstrip("- ").strip()
        if any(key in stripped for key in wanted):
            lines.append(stripped)
    return lines


def _run_verifier(verifier_path: Path) -> dict[str, Any]:
    result = _run(["python3", str(verifier_path), "artifacts/showcase"], cwd=PETTACHAINER_DIR)
    return {
        "exit": result.returncode,
        "stdout_tail": _tail_lines(result.stdout),
        "stderr_tail": _tail_lines(result.stderr),
    }


def _tail_lines(text: str, limit: int = 5) -> list[str]:
    return [line for line in text.splitlines() if line.strip()][-limit:]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _compact(text: str) -> str:
    return " ".join(text.split())


def _json_for_skill(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True)


def _run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        check=False,
        capture_output=True,
        text=True,
    )


def _read_request(args: argparse.Namespace) -> str:
    if args.request_file:
        return Path(args.request_file).read_text()
    return args.request or ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="goalchainer-skill")
    parser.add_argument(
        "skill",
        choices=(
            "goalchainer-decision",
            "goalchainer-proof-audit",
            "goalchainer-ontology-context",
            "goalchainer-tests",
        ),
    )
    parser.add_argument("--request", default="")
    parser.add_argument("--request-file")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    payload = run_skill(args.skill, _read_request(args))
    if args.pretty:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Structured command-line surface for native SNARS sessions."""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .snars_decision import native_decision_payload
from .snars_models import EvidenceCounts, SnarsInvalidInputError
from .snars_reasoner import SnarsOperation, SnarsSession
from .snars_runtime import SnarsRuntime

OPERATIONS = (
    "decision",
    "assess",
    "ask",
    "prove",
    "explain",
    "why-not",
    "discover",
    "goal",
    "subgoals",
    "what-if",
    "temporal",
    "trust",
    "mine",
    "inspect",
    "truth",
    "control",
    "structural",
    "guard",
    "transform",
    "compiled-prove",
)
GROUP_OPERATIONS = {
    "decision": {"decision"},
    "evidence": {"assess", "ask", "prove"},
    "explanation": {"explain", "why-not"},
    "counterfactual": {"what-if"},
    "goal-temporal": {"goal", "subgoals", "temporal"},
    "trust-discovery": {
        "trust",
        "mine",
        "discover",
        "inspect",
        "truth",
        "control",
        "structural",
        "guard",
        "transform",
        "compiled-prove",
    },
}
REQUEST_FIELDS = {
    "group",
    "operation",
    "request",
    "statement",
    "hypothesis",
    "query",
    "database",
    "source",
    "trust",
    "positive",
    "negative",
    "base_rate",
    "depth",
    "size",
    "owner",
    "kind",
    "desire",
    "required",
    "now",
    "budget",
    "minimum_support",
    "threshold",
    "guard_goal",
    "guard_rules",
    "transform_kind",
    "other_statement",
}


def add_snars_arguments(parser: argparse.ArgumentParser, default_request: str) -> None:
    parser.set_defaults(snars_default_request=default_request)
    parser.add_argument("operation", nargs="?", choices=OPERATIONS, default="decision")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--request", help="text to ingest")
    parser.add_argument("--statement", help="ground statement or query pattern")
    parser.add_argument("--hypothesis", help="counterfactual hypothesis statement")
    parser.add_argument("--query", help="counterfactual query statement")
    parser.add_argument("--database", type=Path, help="explicit persistent SQLite path")
    parser.add_argument("--source", default="cli", help="stable evidence source")
    parser.add_argument("--trust", type=float, default=1.0)
    parser.add_argument("--positive", type=float, default=1.0)
    parser.add_argument("--negative", type=float, default=0.0)
    parser.add_argument("--base-rate", type=float, default=0.5)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--size", type=int, default=12)
    parser.add_argument("--owner", default="cli")
    parser.add_argument("--kind", choices=("individual", "collective"), default="individual")
    parser.add_argument("--desire", type=float, default=1.0)
    parser.add_argument("--required", action="store_true")
    parser.add_argument("--now", type=float, default=0.0)
    parser.add_argument("--budget", type=int, default=8)
    parser.add_argument("--minimum-support", type=int, default=2)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--guard-goal")
    parser.add_argument("--guard-rule", dest="guard_rules", action="append", default=[])
    parser.add_argument(
        "--transform-kind",
        choices=("marginal", "similarity", "symmetric", "disjunction"),
    )
    parser.add_argument("--other-statement")


def run_snars_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.operation == "decision":
        request = args.request or getattr(args, "snars_default_request", None)
        return native_decision_payload(
            _required(request, "--request"),
            store_path=args.database,
        )

    request = args.request or ""
    runtime = SnarsRuntime(require_text_ingestion=bool(request))
    session = (
        SnarsSession.ephemeral(runtime)
        if args.database is None
        else SnarsSession.persistent(runtime, args.database)
    )
    with session:
        if request:
            session.ingest_text(
                request,
                source=args.source,
                trust=args.trust,
            )
        result = _dispatch(args, session)
        return {
            "operation": args.operation,
            "mode": "native",
            "native_snars_ran": True,
            "state": session.state_payload(),
            "runtime": {
                "mettabase_commit": runtime.diagnostics.mettabase_commit,
                "mettabase_dir": str(runtime.diagnostics.mettabase_dir),
                "petta_dir": str(runtime.diagnostics.petta_dir),
                "swipl": str(runtime.diagnostics.swipl),
            },
            "result": _json_value(result),
        }


def run_snars_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Run one validated OmegaClaw JSON request through the CLI operation core."""

    if not isinstance(payload, dict):
        raise SnarsInvalidInputError("SNARS dispatch request must be a JSON object.")
    unknown = sorted(set(payload) - REQUEST_FIELDS)
    if unknown:
        raise SnarsInvalidInputError(
            "SNARS dispatch request contains unknown fields.",
            details={"fields": unknown},
        )
    group = payload.get("group")
    operation = payload.get("operation")
    if not isinstance(group, str) or group not in GROUP_OPERATIONS:
        raise SnarsInvalidInputError(
            "SNARS dispatch group is invalid.",
            details={"allowed": sorted(GROUP_OPERATIONS)},
        )
    if not isinstance(operation, str) or operation not in GROUP_OPERATIONS[group]:
        raise SnarsInvalidInputError(
            "SNARS operation is not allowed in its dispatch group.",
            details={
                "group": group,
                "allowed": sorted(GROUP_OPERATIONS[group]),
            },
        )
    values = {
        "operation": operation,
        "json": True,
        "request": "",
        "statement": None,
        "hypothesis": None,
        "query": None,
        "database": None,
        "source": "omegaclaw",
        "trust": 1.0,
        "positive": 1.0,
        "negative": 0.0,
        "base_rate": 0.5,
        "depth": 4,
        "size": 12,
        "owner": "omegaclaw",
        "kind": "individual",
        "desire": 1.0,
        "required": False,
        "now": 0.0,
        "budget": 8,
        "minimum_support": 2,
        "threshold": 0.5,
        "guard_goal": None,
        "guard_rules": [],
        "transform_kind": None,
        "other_statement": None,
    }
    values.update({key: value for key, value in payload.items() if key != "group"})
    if values["database"] is not None:
        if not isinstance(values["database"], str):
            raise SnarsInvalidInputError("database must be a path string.")
        values["database"] = Path(values["database"])
    result = run_snars_command(argparse.Namespace(**values))
    result["group"] = group
    return result


def _dispatch(args: argparse.Namespace, session: SnarsSession) -> Any:
    if args.operation == "assess":
        return {
            "context": session.request_context(),
            "actions": session.assess_actions(),
        }
    if args.operation == "ask":
        return session.ask(_required(args.statement, "--statement"))
    if args.operation == "prove":
        return session.prove(
            _required(args.statement, "--statement"),
            max_depth=args.depth,
            max_size=args.size,
        )
    if args.operation in {"explain", "why-not"}:
        result = session.explain(
            _required(args.statement, "--statement"),
            max_depth=args.depth,
        )
        if args.operation == "why-not":
            payload = result.payload
            if isinstance(payload, list) and len(payload) >= 3:
                return payload[2]
        return result
    if args.operation == "discover":
        return session.discover(_required(args.statement, "--statement"))
    if args.operation == "goal":
        return session.register_goal(
            _required(args.statement, "--statement"),
            owner=args.owner,
            kind=args.kind,
            desire=args.desire,
            required=args.required,
            source=args.source,
        )
    if args.operation == "subgoals":
        return session.subgoals(_required(args.statement, "--statement"))
    if args.operation == "what-if":
        return session.what_if(
            _required(args.hypothesis, "--hypothesis"),
            _required(args.query, "--query"),
            evidence=_evidence(args),
            source=args.source,
            trust=args.trust,
            max_depth=args.depth,
        )
    if args.operation == "temporal":
        return session.temporal(
            _required(args.statement, "--statement"),
            now=args.now,
            budget=args.budget,
        )
    if args.operation == "trust":
        return session.trust()
    if args.operation == "mine":
        return session.mine(args.minimum_support)
    if args.operation == "inspect":
        return session.inspect()
    if args.operation == "truth":
        return session.truth(
            _required(args.statement, "--statement"),
            threshold=args.threshold,
        )
    if args.operation == "control":
        return session.control(args.budget)
    if args.operation == "structural":
        return session.structural()
    if args.operation == "guard":
        return session.guard(
            _required(args.guard_goal, "--guard-goal"),
            rules=tuple(args.guard_rules),
        )
    if args.operation == "transform":
        return session.transform(
            _required(args.transform_kind, "--transform-kind"),
            _required(args.statement, "--statement"),
            other_statement=args.other_statement,
            base_rate=args.base_rate,
        )
    if args.operation == "compiled-prove":
        return session.compiled_prove(
            _required(args.statement, "--statement")
        )
    raise SnarsInvalidInputError(
        "Unsupported SNARS CLI operation.",
        details={"operation": args.operation},
    )


def _evidence(args: argparse.Namespace) -> EvidenceCounts:
    return EvidenceCounts(args.positive, args.negative, args.base_rate)


def _required(value: str | None, option: str) -> str:
    if value is None or not value.strip():
        raise SnarsInvalidInputError(f"{option} is required for this operation.")
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, SnarsOperation):
        return {
            "operation": value.operation,
            "payload": value.payload,
            "raw": value.raw,
        }
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


__all__ = [
    "GROUP_OPERATIONS",
    "OPERATIONS",
    "add_snars_arguments",
    "run_snars_command",
    "run_snars_request",
]

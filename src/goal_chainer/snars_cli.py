"""Purpose: give native SNARS conditions, proof obligations and session operations a
command-line and JSON surface. Each command runs under the one RunBudget its caller built from the
request's limits, the goalchainer CLI's bounded flags or the skill's typed envelope; forward
queries, conditions and obligations report the inferences they charged to it. Text a command
ingests is read with the reading section of the domain its caller selects, and an operation on
statements alone needs no domain."""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .domains.loader import selected_domain
from .domains.model import DomainError
from .runtime.budget import RunBudget
from .snars_models import Evidence
from .errors import InvalidInputError
from .snars_reasoner import DEFAULT_HYPOTHESIS, SnarsOperation, SnarsSession, runtime_payload
from .semantic_reader import SemanticReader, domain_reader

# am[implements a-integrate-ecan-forward-query-interface-1017]
# am[implements a-integrate-planning-session-surface-1017@f5132a]
# am[implements a-integrate-domain-surface-1018@759698] am[implements a-ie-s7-python-1018@e9b9d4]
OPERATIONS = (
    "ask",
    "forward-query",
    "condition",
    "obligations",
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
# am[implements a-integrate-ecan-forward-query-interface-1017]
# am[implements a-integrate-planning-session-surface-1017@f5132a]
# am[implements a-integrate-domain-surface-1018@759698] am[implements a-ie-s7-python-1018@e9b9d4]
GROUP_OPERATIONS = {
    "evidence": {"ask", "prove", "forward-query", "condition"},
    "explanation": {"explain", "why-not"},
    "counterfactual": {"what-if"},
    "goal-temporal": {"goal", "subgoals", "temporal", "obligations"},
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
# am[implements a-integrate-ecan-forward-query-interface-1017]
# am[implements a-integrate-planning-session-surface-1017@f5132a]
REQUEST_FIELDS = {
    "group",
    "operation",
    "request",
    "domain",
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
    "negated",
    "guard_goal",
    "guard_rules",
    "transform_kind",
    "other_statement",
}


# am[implements a-ev-br-callers-1017@1261b7]
# am[implements a-integrate-ecan-forward-query-interface-1017]
# am[implements a-integrate-planning-session-surface-1017@f5132a]
# am[implements a-integrate-domain-surface-1018@759698] am[implements a-ie-sr-select-domain-1018@577734]
def add_snars_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("operation", choices=OPERATIONS)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--request", help="text to ingest")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--domain", help="the packaged domain whose reading section reads --request")
    choice.add_argument("--domain-file", type=Path, help="a domain .metta file whose reading section reads --request")
    parser.add_argument("--statement", help="ground statement or query pattern")
    parser.add_argument("--hypothesis", help="counterfactual hypothesis statement")
    parser.add_argument("--query", help="counterfactual query statement")
    parser.add_argument("--database", type=Path, help="explicit persistent SQLite path")
    parser.add_argument("--source", default="cli", help="stable evidence source")
    parser.add_argument("--trust", type=float, default=1.0)
    parser.add_argument("--positive", type=float, default=None,
                        help="hypothetical positive evidence; the operation's default when omitted")
    parser.add_argument("--negative", type=float, default=None,
                        help="hypothetical negative evidence; the operation's default when omitted")
    parser.add_argument(
        "--base-rate",
        type=float,
        default=None,
        help="base rate for the evidence or marginal; SNARS's configured default when omitted",
    )
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--size", type=int, default=12)
    parser.add_argument("--owner", default="cli")
    parser.add_argument("--kind", choices=("individual", "collective"), default="individual")
    parser.add_argument("--desire", type=float, default=1.0)
    parser.add_argument("--required", action="store_true")
    parser.add_argument("--now", type=float, default=0.0)
    parser.add_argument("--budget", type=int, default=8)
    parser.add_argument("--minimum-support", type=int, default=2)
    parser.add_argument("--threshold", type=float, default=None,
                        help="condition threshold; omitted uses the operation's own default")
    parser.add_argument("--negated", action="store_true", help="classify the complement of a condition")
    # am[implements a-integrate-guard-metta-build-1019@e688cb]
    parser.add_argument("--guard-goal", help="one MeTTa goal expression, e.g. '(safe redacted)'")
    parser.add_argument("--guard-rule", dest="guard_rules", action="append", default=[],
                        help="one MeTTa fact or (:- HEAD BODY) rule; repeat for more clauses")
    parser.add_argument(
        "--transform-kind",
        choices=("marginal", "similarity", "symmetric", "disjunction"),
    )
    parser.add_argument("--other-statement")


# Every session batch charges the caller's budget, which the goalchainer CLI's
# bounded flags or the skill's envelope built once; nothing here builds another.
# am[implements a-rt-snars-batch-speculative-1017@451056] am[implements a-rt-rbr-snars-envelope-1018@920fe4]
# am[rests-on c-integrate-typed-budget-envelope-1018@f097bf]
# am[implements a-integrate-domain-surface-1018@759698] am[implements a-ie-sr-text-needs-domain-1018@8f7f0b]
def run_snars_command(args: argparse.Namespace, *, budget: RunBudget) -> dict[str, Any]:
    request = args.request or ""
    if request and args.domain is None and args.domain_file is None:
        raise InvalidInputError(
            "Request text is read against the domain its caller selects: name one with --domain or "
            "--domain-file, or domain in a JSON request.",
        )
    reader = _reader(args, budget)
    session = (
        SnarsSession.ephemeral(budget=budget, reader=reader)
        if args.database is None
        else SnarsSession.persistent(args.database, budget=budget, reader=reader)
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
            "runtime": runtime_payload(),
            "result": _json_value(result),
        }


# The reader of the domain the caller selected, read under the command's budget, or none for a
# command that selected none. A session reads a domain for its reading section alone, so a domain
# that declares none is refused whether or not the command gives text, and a selection the loader
# refuses is InvalidInputError, as the domain request words it.
# am[implements a-ie-sr-select-domain-1018@577734] am[implements a-ie-sr-text-needs-domain-1018@8f7f0b]
def _reader(args: argparse.Namespace, budget: RunBudget) -> SemanticReader | None:
    if args.domain is None and args.domain_file is None:
        return None
    try:
        domain = selected_domain(path=args.domain_file, packaged=args.domain, budget=budget)
    except DomainError as error:
        raise InvalidInputError(
            str(error),
            details={"domain": args.domain, "domain_file": None if args.domain_file is None else str(args.domain_file)},
        ) from error
    return domain_reader(domain)


# am[implements a-ev-br-callers-1017@1261b7]
# am[implements a-integrate-ecan-forward-query-interface-1017] am[implements a-rt-rbr-snars-envelope-1018@920fe4]
# am[implements a-integrate-planning-session-surface-1017@f5132a]
# am[rests-on c-integrate-typed-budget-envelope-1018@f097bf]
# am[implements a-integrate-domain-surface-1018@759698] am[implements a-ie-sr-select-domain-1018@577734]
# am[implements a-v2-snars-dispatch-input-1020@a10217]
def run_snars_request(payload: dict[str, Any], *, budget: RunBudget) -> dict[str, Any]:
    """Run one validated OmegaClaw JSON request through the CLI operation core under `budget`,
    which the skill's envelope built from the request's limits before it handed on the rest. Its
    `domain`, when given, selects a domain as a domain request does: {"packaged": NAME} or
    {"path": PATH}."""

    if not isinstance(payload, dict):
        raise InvalidInputError("SNARS dispatch request must be a JSON object.")
    unknown = sorted(set(payload) - REQUEST_FIELDS)
    if unknown:
        raise InvalidInputError(
            "SNARS dispatch request contains unknown fields.",
            details={"fields": unknown},
        )
    group = payload.get("group")
    operation = payload.get("operation")
    if not isinstance(group, str) or group not in GROUP_OPERATIONS:
        raise InvalidInputError(
            "SNARS dispatch group is invalid.",
            details={"allowed": sorted(GROUP_OPERATIONS)},
        )
    if not isinstance(operation, str) or operation not in GROUP_OPERATIONS[group]:
        raise InvalidInputError(
            "SNARS operation is not allowed in its dispatch group.",
            details={
                "group": group,
                "allowed": sorted(GROUP_OPERATIONS[group]),
            },
        )
    if "guard_rules" in payload:
        rules = payload["guard_rules"]
        if not isinstance(rules, list) or any(not isinstance(rule, str) for rule in rules):
            raise InvalidInputError("guard_rules must be an array of MeTTa rule strings.")
    parser = argparse.ArgumentParser(add_help=False)
    add_snars_arguments(parser)
    values = vars(parser.parse_args([operation]))
    values.update(json=True, source="omegaclaw", owner="omegaclaw")
    values.update({key: value for key, value in payload.items() if key not in {"group", "domain"}})
    if "domain" in payload:
        from .requests import domain_selection  # noqa: PLC0415 (the request surface loads its review stages)

        selection = domain_selection(payload["domain"])
        values.update(domain=selection.get("packaged"),
                      domain_file=None if "path" not in selection else Path(selection["path"]))
    if values["database"] is not None:
        if not isinstance(values["database"], str):
            raise InvalidInputError("database must be a path string.")
        values["database"] = Path(values["database"])
    result = run_snars_command(argparse.Namespace(**values), budget=budget)
    result["group"] = group
    return result


# A forward query, condition or obligations search reports the inferences it charged of the
# request's allowance, which the request's ingestion shares, so the report reads the session
# budget's spend before and after the operation.
# am[implements a-integrate-ecan-forward-query-interface-1017] am[implements a-rt-rbs-session-budget-1018@8c3da2]
# am[implements a-integrate-planning-session-surface-1017@f5132a]
def _dispatch(args: argparse.Namespace, session: SnarsSession) -> Any:
    if args.operation == "ask":
        return session.ask(_required(args.statement, "--statement"))
    if args.operation in {"forward-query", "condition", "obligations"}:
        statement = _required(args.statement, "--statement")
        before = session.budget.spent
        if args.operation == "forward-query":
            answer = session.forward_query(statement)
        elif args.operation == "condition":
            answer = session.condition(statement, threshold=args.threshold, negated=args.negated)
        else:
            answer = session.obligations(
                statement,
                hypothesis=_evidence(args, default=DEFAULT_HYPOTHESIS),
                threshold=args.threshold,
                max_size=args.size,
            )
        return {"answer": answer,
                "computation": {"inference_budget": session.budget.inference_budget,
                                "inferences": session.budget.spent - before}}
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
            **({} if args.threshold is None else {"threshold": args.threshold}),
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
    raise InvalidInputError(
        "Unsupported SNARS CLI operation.",
        details={"operation": args.operation},
    )


# am[implements a-ev-br-callers-1017@1261b7]
# am[implements a-integrate-planning-session-surface-1017@f5132a]
# Evidence the model refuses, an amount beyond the float range, NaN or a negative count among it,
# is the request's typed input error, where the model's ValueError left the skill untyped.
# am[implements a-rt-nr-repair-1018@72901e] am[rests-on c-rt-nr-probe-bfd71102-1018@029356]
def _evidence(args: argparse.Namespace, *, default: Evidence = Evidence(1.0, 0.0)) -> Evidence:
    try:
        return Evidence(
            default.positive if args.positive is None else args.positive,
            default.negative if args.negative is None else args.negative,
            default.base_rate if args.base_rate is None else args.base_rate,
        )
    except (TypeError, ValueError) as error:
        raise InvalidInputError(f"The request's evidence is invalid: {error}.") from error


# am[addresses i-integrate-dispatch-nontext-statement-1018@40d89f]
def _required(value: Any, option: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"{option} is required for this operation.")
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

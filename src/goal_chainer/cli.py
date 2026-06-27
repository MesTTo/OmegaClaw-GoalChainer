"""Command line interface for the GoalChainer prototype."""

from __future__ import annotations

import argparse
import json

from .codebase_demo import run_codebase_demo
from .hyperbase import build_hyperbase_packet
from .metta_reasoner import HyperBaseMettaReasoner
from .ontology import load_colore_context
from .scenarios import incident_response_scenario
from .scoring import DecisionEngine
from .validation import run_validation

DEFAULT_INCIDENT_REQUEST = (
    "Checkout is down. Engineering wants to paste raw logs into the incident room. "
    "Support says the logs may include customer emails, order IDs, and request payloads."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="goalchainer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo_parser = subparsers.add_parser("demo", help="run the built-in incident response demo")
    demo_parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    demo_parser.add_argument("--request", default=DEFAULT_INCIDENT_REQUEST, help="natural language incident request")
    codebase_parser = subparsers.add_parser(
        "codebase-demo",
        help="regenerate and repair the checkout-status demo repo",
    )
    codebase_parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    codebase_parser.add_argument("--request", default="", help="natural language repair request")
    codebase_parser.add_argument("--repo-path", help="where to regenerate the demo repo")
    validate_parser = subparsers.add_parser(
        "validate",
        help="run the differential battery proving the decision depends on the input",
    )
    validate_parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args(argv)

    if args.command == "demo":
        scenario = incident_response_scenario(args.request)
        ontology = load_colore_context()
        hyperbase = build_hyperbase_packet(args.request, ontology)
        reasoner = HyperBaseMettaReasoner(hyperbase["reasoner"])
        decisions = DecisionEngine(reasoner).rank(scenario)
        payload = {
            "scenario": scenario.title,
            "notes": list(scenario.notes),
            "runtime": {"reasoner": reasoner.source},
            "hyperbase": hyperbase,
            "decisions": [decision.to_dict() for decision in decisions],
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            _print_text(payload)
        return 0
    if args.command == "codebase-demo":
        payload = run_codebase_demo(args.request, args.repo_path)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            _print_codebase_demo(payload)
        return 0
    if args.command == "validate":
        report = run_validation()
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            _print_validation(report)
        return 0 if report["passed"] else 1
    return 2


def _print_text(payload: dict[str, object]) -> None:
    print(payload["scenario"])
    print(f"reasoner: {payload['runtime']['reasoner']}")
    print()
    for decision in payload["decisions"]:
        print(f"{decision['status']:>11}  {decision['score']:.3f}  {decision['label']}")
        print(f"             norm={decision['norm_status']} evidence={decision['evidence']['strength']:.3f}")
        for warning in decision["warnings"]:
            print(f"             warning: {warning}")
    print()
    for note in payload["notes"]:
        print(f"- {note}")


def _print_validation(report: dict[str, object]) -> None:
    print(f"input-sensitivity battery: {'PASS' if report['passed'] else 'FAIL'}")
    print()
    for case in report["cases"]:
        print(f"[{case['name']}] {case['summary']}")
        for row in case["ranking"]:
            print(
                f"  {row['status']:>11}  {row['score']:.3f}  {row['action_id']}"
                f"  (deontic={row['deontic']})"
            )
        for check in case["checks"]:
            mark = "ok" if check["passed"] else "XX"
            print(f"    [{mark}] {check['check']}")
        print()
    print("cross-case checks")
    for check in report["cross_checks"]:
        mark = "ok" if check["passed"] else "XX"
        print(f"  [{mark}] {check['check']}")
    print()
    print(f"raw-log status by case: {report['raw_log_status_by_case']}")


def _print_codebase_demo(payload: dict[str, object]) -> None:
    reasoning = payload["reasoning"]
    assert isinstance(reasoning, dict)
    patch = payload["patch"]
    assert isinstance(patch, dict)

    print(payload["issue"]["title"])
    print(f"repo: {payload['repo_path']}")
    print()
    print("workflow")
    for step in payload["workflow"]:
        print(f"- {step}")
    print()
    print(
        "tests: "
        f"before={payload['pre_patch_tests']['exit_code']} "
        f"after={payload['post_patch_tests']['exit_code']} "
        f"success={payload['success']}"
    )
    print()
    print("findings")
    for finding in reasoning["findings"]:
        source = finding["source"]
        print(f"- {finding['id']} at {source['path']}:{source['line']}: {finding['claim']}")
    print()
    print("goals and norms")
    goal_model = reasoning["goal_model"]
    for goal in goal_model["individual_goals"] + goal_model["collective_goals"]:
        print(f"- required {goal['id']}: {goal['statement']}")
    for norm in goal_model["norms"]:
        print(f"- {norm['status']} {norm['target']} priority={norm['priority']}")
    print()
    print("counterfactuals")
    for counterfactual in reasoning["counterfactuals"]:
        print(f"- {counterfactual['status']}: {counterfactual['action']}")
    print()
    print("propositions")
    for proposition in reasoning["propositions"]:
        print(f"- {proposition['id']}: {proposition['sentence']}")
    print()
    post_contract = payload["post_patch_contract"]
    print(
        "post-patch contract: "
        f"returns={', '.join(post_contract['implementation_returns'])}; "
        f"raw_log_passthrough={post_contract['raw_log_passthrough']}"
    )
    print()
    print("patch")
    print(patch["diff"])


if __name__ == "__main__":
    raise SystemExit(main())

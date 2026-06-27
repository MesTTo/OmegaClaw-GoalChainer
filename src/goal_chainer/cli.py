"""Command line interface for the GoalChainer prototype."""

from __future__ import annotations

import argparse
import json

from .codebase_demo import run_codebase_demo
from .petta_bridge import reasoner_from_env
from .scenarios import incident_response_scenario
from .scoring import DecisionEngine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="goalchainer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo_parser = subparsers.add_parser("demo", help="run the built-in incident response demo")
    demo_parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    codebase_parser = subparsers.add_parser(
        "codebase-demo",
        help="regenerate and repair the checkout-status demo repo",
    )
    codebase_parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    codebase_parser.add_argument("--request", default="", help="natural language repair request")
    codebase_parser.add_argument("--repo-path", help="where to regenerate the demo repo")
    args = parser.parse_args(argv)

    if args.command == "demo":
        scenario = incident_response_scenario()
        decisions = DecisionEngine(reasoner_from_env()).rank(scenario)
        payload = {
            "scenario": scenario.title,
            "notes": list(scenario.notes),
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
    return 2


def _print_text(payload: dict[str, object]) -> None:
    print(payload["scenario"])
    print()
    for decision in payload["decisions"]:
        print(f"{decision['status']:>11}  {decision['score']:.3f}  {decision['label']}")
        print(f"             norm={decision['norm_status']} evidence={decision['evidence']['strength']:.3f}")
        for warning in decision["warnings"]:
            print(f"             warning: {warning}")
    print()
    for note in payload["notes"]:
        print(f"- {note}")


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

"""Command line interface for the GoalChainer prototype."""

from __future__ import annotations

import argparse
import json

from .petta_bridge import reasoner_from_env
from .scenarios import incident_response_scenario
from .scoring import DecisionEngine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="goalchainer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo_parser = subparsers.add_parser("demo", help="run the built-in incident response demo")
    demo_parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
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


if __name__ == "__main__":
    raise SystemExit(main())


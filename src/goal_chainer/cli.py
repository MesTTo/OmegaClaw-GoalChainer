"""Purpose: expose domain and motivation requests and a readable account of their results, directive operations,
relevance reviews, SNARS sessions and bounded developer diagnostics of a MeTTa expression."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .diagnose_cli import add_diagnose_arguments, run_diagnose
from .directive import run_directive_request
from .domains.forms import input_text
from .errors import GoalChainerError, InvalidInputError
from .json_input import loads
from .relevance_cli import add_relevance_arguments, run_relevance
from .runtime.budget import RunBudget
from .snars_cli import add_snars_arguments, run_snars_command
from .snars_engine import start_worlds_from_images


# am[implements a-integrate-domain-surface-1018@759698]
# am[implements a-integrate-cli-typed-errors-1018@160cf8]
# am[implements a-dg-cli-1019@996a1b]
# am[implements a-v2-cli-skill-surface-1020@6f755c]
def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    try:
        return _main(arguments)
    except GoalChainerError as error:
        if "--json" in arguments or arguments[:1] in (["request"], ["directive"], ["diagnose"], ["motivation"]):
            print(json.dumps({"ok": False, "error": error.to_dict()}, sort_keys=True))
        else:
            print(f"GoalChainer error [{error.code}]: {error}", file=sys.stderr)
        return 1


# Each command creates its allowance once, before reading or evaluating the request.
# am[implements a-integrate-domain-surface-1018@759698]
# am[implements a-integrate-request-budget-surface-1018@d6882c]
# am[implements a-dg-cli-1019@996a1b]
# am[implements a-v2-cli-skill-surface-1020@6f755c]
def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="goalchainer")
    commands = parser.add_subparsers(dest="command", required=True)
    request_parser = commands.add_parser("request", help="review, plan or admit against a selected domain")
    directive_parser = commands.add_parser("directive", help="apply a typed directive operation")
    motivation_parser = commands.add_parser("motivation", help="record need observations or host attempts, or inspect a stream")
    show_parser = commands.add_parser("show", help="print a readable account of a request result")
    for command in (request_parser, directive_parser, motivation_parser, show_parser):
        command.add_argument("--input", default="-", help="JSON input file, or - for standard input")
    snars_parser = commands.add_parser("snars", help="query or update a native SNARS session")
    add_snars_arguments(snars_parser)
    for command in (request_parser, directive_parser, motivation_parser, snars_parser):
        command.add_argument("--inference-budget", type=int, required=True,
                             help="maximum engine inferences for this request")
        command.add_argument("--timeout-seconds", type=float, required=True,
                             help="wall-clock limit for this request")
    relevance_parser = commands.add_parser("relevance", help="inspect domains, review tasks and assess receipts")
    add_relevance_arguments(relevance_parser)
    # Each diagnostic takes its own required limits, as add_diagnose_arguments gives them.
    diagnose_parser = commands.add_parser("diagnose", help="profile, explain or match one MeTTa expression "
                                                           "in a module group, bounded")
    add_diagnose_arguments(diagnose_parser)
    args = parser.parse_args(argv)
    if args.command == "relevance":
        return run_relevance(args)
    # An account of a saved result evaluates nothing, so it takes no limits.
    # am[implements a-dd-show-1018@f9e4e9]
    if args.command == "show":
        from .request_text import account

        text, status = account(_read_payload(args.input))
        print(text)
        return status
    budget = RunBudget(inference_budget=args.inference_budget, timeout_seconds=args.timeout_seconds)
    if args.command == "snars":
        result = run_snars_command(args, budget=budget)
    elif args.command == "diagnose":
        result = run_diagnose(args, budget=budget)
    else:
        payload = _read_payload(args.input)
        budget.remaining()
        if args.command == "request":
            from .requests import run_request

            result = run_request(payload, budget=budget)
        elif args.command == "motivation":
            from .motivation.requests import run_motivation_request

            result = run_motivation_request(payload, budget=budget)
        else:
            result = run_directive_request(payload, budget=budget)
    budget.remaining()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


# A domain or motivation request, a directive operation or a result to show, each one JSON object. json.loads
# raises RecursionError for JSON nested deeper than its parser reaches, and ValueError, of which
# JSONDecodeError is one kind, for malformed text and for an integer of more digits than the
# interpreter reads (c-sn-overflow-and-digit-limits-1018), all unreadable input. The text itself is
# read by domains.forms.input_text, a file or standard input's bytes as UTF-8 alike, so standard
# input means what a file of the same bytes means under any locale.
# Time and space: linear in the input's JSON length.
# am[implements a-integrate-domain-surface-1018@759698] am[implements a-dd-show-1018@f9e4e9]
# am[implements a-sb-reader-recursion-1018@e6fda1] am[implements a-sn-contract-numbers-1018@c1d969]
# am[implements a-integrate-cli-stdin-repair-1018@a5f985]
# am[implements a-v2-json-input-1020@b37a9e]
def _read_payload(path: str) -> dict[str, Any]:
    def unreadable(message: str) -> InvalidInputError:
        return InvalidInputError(f"Cannot read JSON input: {message}", details={"input": path})

    text = input_text(path, unreadable)
    try:
        value = loads(text)
    except (ValueError, RecursionError) as error:
        raise unreadable(str(error)) from error
    if not isinstance(value, dict):
        raise InvalidInputError("The JSON input must be an object.")
    return value


# Process startup configures image loading; in-process callers retain their engine configuration.
# am[implements a-rt-image-console-main-1017@87159d] am[rests-on c-rt-main-called-in-process-1017@fe5086]
def console_main() -> int:
    start_worlds_from_images()
    return main()


if __name__ == "__main__":
    raise SystemExit(console_main())

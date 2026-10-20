"""Purpose: dispatch bounded domain, motivation, directive and SNARS requests in the GoalChainer skill process."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .directive import run_directive_request
from .domains.forms import input_text
from .errors import GoalChainerError, InvalidInputError
from .json_input import loads
from .runtime.budget import RunBudget
from .snars_cli import run_snars_request
from .snars_engine import start_worlds_from_images


# am[implements a-integrate-domain-surface-1018@759698]
# am[implements a-v2-cli-skill-surface-1020@6f755c]
SYSTEM_PROMPT = (
    "Use goalchainer-request with JSON naming an operation (review, plan or admit), "
    "a domain selected by path or packaged name, and an attributed context. "
    "Include positive inference_budget and timeout_seconds limits in each request. "
    "If semantic reading is needed, put the user's original words in reading.text "
    "with observed_at and valid_until; the selected domain declares how Jev reads them. "
    "A goalchainer-snars-dispatch request that gives text in request selects its domain the same "
    "way, as domain; an operation on statements alone needs none. "
    "A plan describes model-valid steps. An inquiry names evidence still needed. "
    "Admission rechecks a returned step against current evidence. "
    "Record need observations and host-reported attempts with goalchainer-motivation-dispatch; "
    "a review never records an attempt. "
    "These results do not authorize execution or confirm an effect. "
    "Keep the current review, applicable norms, host authorization and observed receipts separate."
)


# am[implements a-integrate-domain-surface-1018@759698]
def request_payload(payload: dict[str, Any], *, budget: RunBudget) -> dict[str, Any]:
    from .requests import run_request

    return {"skill": "goalchainer-request", **run_request(payload, budget=budget)}


# am[implements a-integrate-domain-surface-1018@759698]
def snars_dispatch_payload(payload: dict[str, Any], *, budget: RunBudget) -> dict[str, Any]:
    return {"skill": "goalchainer-snars-dispatch", **run_snars_request(payload, budget=budget)}


# am[implements a-integrate-domain-surface-1018@759698]
def directive_dispatch_payload(payload: dict[str, Any], *, budget: RunBudget) -> dict[str, Any]:
    return {"skill": "goalchainer-directive-dispatch", **run_directive_request(payload, budget=budget)}


# am[implements a-v2-cli-skill-surface-1020@6f755c]
def motivation_dispatch_payload(payload: dict[str, Any], *, budget: RunBudget) -> dict[str, Any]:
    from .motivation.requests import run_motivation_request

    return {"skill": "goalchainer-motivation-dispatch", **run_motivation_request(payload, budget=budget)}


# The dispatch table also supplies the process's accepted names.
# am[implements a-integrate-domain-surface-1018@759698]
# am[implements a-v2-cli-skill-surface-1020@6f755c]
DISPATCH = {
    "goalchainer-request": request_payload,
    "goalchainer-directive-dispatch": directive_dispatch_payload,
    "goalchainer-snars-dispatch": snars_dispatch_payload,
    "goalchainer-motivation-dispatch": motivation_dispatch_payload,
}


# am[implements a-integrate-domain-surface-1018@759698]
def system_prompt_payload() -> dict[str, Any]:
    return {"skill": "goalchainer-system-prompt", "prompt": SYSTEM_PROMPT}


# am[implements a-integrate-domain-surface-1018@759698]
def run_skill(name: str, request: str) -> dict[str, Any]:
    if name == "goalchainer-system-prompt":
        return system_prompt_payload()
    if name not in DISPATCH:
        raise InvalidInputError(f"Unknown GoalChainer skill: {name}")
    payload, budget = _bounded_request(request)
    result = DISPATCH[name](payload, budget=budget)
    budget.remaining()
    return result


# json.loads raises ValueError, of which JSONDecodeError is one kind, for malformed text and for an
# integer of more digits than the interpreter reads, RecursionError for JSON nested deeper than its
# parser reaches, as cli._read_payload refuses them (c-rt-rr-skill-json-digits-1018), and TypeError
# for a request that is not text: each is the request's InvalidInputError.
# Time and space: linear in the JSON request length.
# am[implements a-integrate-request-budget-surface-1018@d6882c] am[implements a-rt-rr-json-read-1018@305497]
# am[rests-on c-rt-rr-skill-json-digits-1018@1df21f]
# am[implements a-v2-json-input-1020@b37a9e]
def _bounded_request(request: str) -> tuple[dict[str, Any], RunBudget]:
    try:
        payload = loads(request)
    except (TypeError, ValueError, RecursionError) as error:
        raise InvalidInputError("Skill request must be a valid JSON object.") from error
    if not isinstance(payload, dict):
        raise InvalidInputError("Skill request must be a JSON object.")
    inference_budget = payload.pop("inference_budget", None)
    if inference_budget is None:
        raise InvalidInputError("inference_budget is required and must be a positive integer.")
    budget = RunBudget(inference_budget=inference_budget,
                       timeout_seconds=payload.pop("timeout_seconds", None))
    return payload, budget


# Requests enter over standard input so their text never becomes a shell argument.
# am[implements a-rt-skill-process-boundary-1016@a36729]
# am[implements a-integrate-domain-surface-1018@759698]
# am[implements a-v2-skill-utf8-1020@3763d0]
def _read_request(args: argparse.Namespace) -> str:
    if args.request_file:
        return input_text(args.request_file, InvalidInputError)
    return args.request or ""


# am[implements a-rt-skill-process-boundary-1016@a36729]
# am[implements a-integrate-domain-surface-1018@759698]
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="goalchainer-skill")
    parser.add_argument("skill", choices=("goalchainer-system-prompt", *DISPATCH))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--request", default="")
    source.add_argument("--request-file")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = run_skill(args.skill, _read_request(args))
    except GoalChainerError as error:
        print(json.dumps({"ok": False, "error": error.to_dict()}, sort_keys=True))
        return 1
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


# Process startup configures image loading; in-process callers retain their engine configuration.
# am[implements a-rt-image-console-main-1017@87159d] am[rests-on c-rt-main-called-in-process-1017@fe5086]
def console_main() -> int:
    start_worlds_from_images()
    return main()


if __name__ == "__main__":
    raise SystemExit(console_main())

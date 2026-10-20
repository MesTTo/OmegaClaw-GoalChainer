#!/usr/bin/env python3
"""Purpose: build the explicit goalchainer-request the OmegaClaw demos send for an incident, a review
of the packaged incident domain in a context naming the caller, with the user's words unchanged in
reading.text, observed at the given instant, under the demos' explicit inference and time limits;
and decide whether an agent's goalchainer-request argument is that request, refusing with the
members it changes when it is not.

The shell drivers, and the recorders that run them, run this file: `build` takes the user's words
on standard input and prints the request observed now as one JSON line, the json_request argument
the agent's goalchainer-request tool call carries; `match` takes the agent's argument on standard
input, exits 0 when it is the request and otherwise prints the refusal and exits 1:

    REQUEST="$(printf '%s' "$INCIDENT" | python3 -I omega_request.py build --review-id omegaclaw-loop)"
    printf '%s' "$arg" | python3 -I omega_request.py match "$REQUEST"
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

# The demos' explicit per-request allowances.
# am[implements a-integrate-request-budget-surface-1018@d6882c]
LIMITS = {"inference_budget": 1_000_000_000, "timeout_seconds": 600}


# The demos' explicit selection: a review of the packaged incident domain, whose reading section
# reads the user's words from reading.text, in a context that names the caller and brings no
# reading of its own. `at` is when the words were observed and the review's reference time. The
# incident domain packages no procedures, so a review is the only operation it answers.
# am[implements a-od-request-builder-1018@cf0f5a] am[rests-on c-cd-rec-incident-review-only-1018@eed4da]
# am[rests-on c-od-incident-has-no-procedures-1018@5e5c8c]
def incident_request(text: str, at: str, review_id: str) -> dict:
    return {
        "operation": "review",
        "domain": {"packaged": "incident"},
        "context": {
            "review_id": review_id,
            "subject": "checkout",
            "trigger": "incident-report",
            "as_of": at,
            "authority": "advisory",
            "policy_version": "incident-v1",
            "readings": [],
        },
        "reading": {"text": text, "observed_at": at, "valid_until": None},
        **LIMITS,
    }


# An argument is decoded as strict JSON, as I-JSON (RFC 7493) requires and as
# src/goal_chainer/semantic_reader.py decodes Jev's replays: json.loads keeps the last of repeated
# keys and reads NaN, so {"operation": "plan", "operation": "review", ...} would otherwise pass as
# something it never said. Time: one pass over each object's keys.
# am[implements a-od-request-match-value-1018@e60dde]
def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for name, _value in pairs:
        if name in seen:
            raise ValueError(f"the key {name!r} appears more than once")
        seen.add(name)
    return dict(pairs)


# am[implements a-od-request-match-value-1018@e60dde]
def _no_constant(name: str) -> Any:
    raise ValueError(f"{name} is not a JSON number")


# A JSON text as its value: objects, arrays, strings, true, false and null as Python reads them, and
# every number as a Decimal, since RFC 8259 section 6 gives a JSON number no integer or float kind:
# 600, 600.0 and 6e2 are one number. Raises ValueError for anything but strict JSON.
# am[implements a-od-request-match-value-1018@e60dde]
def _decode(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_strict_object, parse_constant=_no_constant,
                      parse_float=Decimal, parse_int=Decimal)


# The members where `payload` differs from `request`, as dotted paths such as "reading.text" or
# "context.readings.0.state": a key only one side has, a list of another length, or a value of
# another JSON type or value. Spacing and key order are not part of a value, so they never differ.
# Time: n visits + sum(k log k) key comparisons + p path characters, n = visited values,
# k = keys per object, p = cumulative path lengths. Space: keys and paths held by the
# current recursion, plus the reported differences.
# am[implements a-od-request-match-value-1018@e60dde]
def changed(request: Any, payload: Any, path: str = "") -> list[str]:
    if isinstance(request, dict) and isinstance(payload, dict):
        found: list[str] = []
        for key in sorted(request.keys() | payload.keys()):
            if key in request and key in payload:
                found += changed(request[key], payload[key], f"{path}{key}.")
            else:
                found.append(f"{path}{key}")
        return found
    if isinstance(request, list) and isinstance(payload, list) and len(request) == len(payload):
        return [found for index, (want, got) in enumerate(zip(request, payload))
                for found in changed(want, got, f"{path}{index}.")]
    same = type(request) is type(payload) and request == payload
    return [] if same else [path.removesuffix(".") or "the whole request"]


# Whether an agent's goalchainer-request argument is this run's request: the same JSON value, so
# spacing, key order and the way a number is written may differ and nothing else may. None when it
# is, else the refusal the host shows the agent instead of evaluating it, naming what to fix so the
# agent can send the request exactly on a later turn. Whether the request is valid stays the
# skill's to answer: a budget written 1e9 is this number, and the skill answers it.
# am[implements a-od-request-match-value-1018@e60dde]
def refusal(request: dict, argument: str) -> str | None:
    try:
        payload = _decode(argument)
    except ValueError as error:
        return ("goalchainer-request refused, not evaluated: its argument is not strict JSON "
                f"({error}). Send this run's REQUEST exactly.")
    differences = changed(_decode(json.dumps(request)), payload)
    if not differences:
        return None
    return (f"goalchainer-request refused, not evaluated: its argument changes {', '.join(differences)}. "
            "Send this run's REQUEST exactly; only spacing, key order and number formatting may differ.")


# am[implements a-od-request-builder-1018@cf0f5a] am[implements a-od-request-match-value-1018@e60dde]
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0].removeprefix("Purpose: "))
    actions = parser.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build", help="print the request for the user's words on standard input, observed now")
    build.add_argument("--review-id", required=True, help="the review id naming the caller")
    match = actions.add_parser("match", help="exit 0 when the argument on standard input is REQUEST, else print the refusal and exit 1")
    match.add_argument("request", help="this run's REQUEST, as build printed it")
    arguments = parser.parse_args(argv)
    if arguments.action == "build":
        at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        print(json.dumps(incident_request(sys.stdin.read(), at, arguments.review_id), sort_keys=True))
        return 0
    reason = refusal(json.loads(arguments.request), sys.stdin.read())
    if reason is None:
        return 0
    print(reason)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

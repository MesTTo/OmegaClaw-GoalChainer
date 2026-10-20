"""Purpose: argument parsing, dispatch, rendering and typed error reporting for the proposal-only `goalchainer relevance` commands, and the review record's text, which other commands reuse.

    goalchainer relevance review --packet PACKET.json [--domain NAME | --domain-file PATH] [--motivation STREAM.json] [--json]
    goalchainer relevance check  --review REVIEW.json --packet PACKET.json [--domain NAME | --domain-file PATH] [--motivation STREAM.json] [--json]
    goalchainer relevance assess --review REVIEW.json --receipt RECEIPT.json [--next-attempt-at TIME] --inference-budget N --timeout-seconds S [--json]
    goalchainer relevance domain [--domain NAME | --domain-file PATH] --inference-budget N --timeout-seconds S [--json]

`review` runs one bounded review and prints its record; `check` says whether a stored record
still has its support; `assess` grades a host's receipt for one attempt against the proposal it
applied, with `--next-attempt-at` the time the same subject's next applied attempt was applied;
`domain` validates a domain and lists its vocabulary, with the packaged task-control domain,
which a wheel installs, as the default. `review` and `check` load the domain under the one budget
the packet declares, which the review then spends. `--motivation` selects an existing store and
stream as JSON, read at the packet's `as_of` under that same budget. `assess` and `domain` have no packet, so they
run under the bounds their command line gives. None of them applies an effect: the paper's section
10.7 keeps the apply path separate and privileged, and this group has none. A path of `-` reads
JSON from standard input. A command that cannot produce its result prints a typed error,
`{"ok": false, "error": {"code": ..., "message": ..., "details": {...}}}` with `--json` or one
line on standard error without it, and exits 1.

`format_review(record)` is a review record's text. `review` prints it, and a command that shows
a review prints it too, or indents it under its own heading, so a review is worded in one place.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from typing import Any, Mapping

from .domains.forms import input_text
from .domains.loader import selected_domain
from .domains.model import Domain, DomainError
from .errors import InvalidInputError, PersistenceError
from .json_input import loads
from .relevance import assess_receipt, check_freshness, engine_identity, parse_packet, parse_receipt, review
from .relevance.errors import RelevanceError
from .relevance.instants import parse_instant
from .relevance.policy import stopped
from .runtime.budget import BudgetExhausted, RunBudget

DEFAULT_DOMAIN = "task-control"


# am[implements a-rel-cli-1016@8f8ec8]
# am[implements a-v2-cli-freshness-stream-1020@14de3d]
def add_relevance_arguments(parser: argparse.ArgumentParser) -> None:
    operations = parser.add_subparsers(dest="relevance_operation", required=True)
    review_parser = operations.add_parser("review", help="run one bounded review of a packet")
    review_parser.add_argument("--packet", required=True, help="review packet JSON, or - for stdin")
    _domain_arguments(review_parser)
    check = operations.add_parser("check", help="check a stored review against a current packet")
    check.add_argument("--review", required=True, help="the stored review record JSON")
    check.add_argument("--packet", required=True, help="the current review packet JSON")
    _domain_arguments(check)
    for command in (review_parser, check):
        command.add_argument("--motivation", help="JSON file naming the motivation store and stream, or - for stdin")
    assess = operations.add_parser("assess", help="assess a host receipt against its proposal")
    assess.add_argument("--review", required=True, help="the review record the host acted on")
    assess.add_argument("--receipt", required=True, help="the host's receipt JSON")
    assess.add_argument(
        "--next-attempt-at",
        help="when the same subject's next applied attempt was applied, ISO-8601 with an offset; "
        "observations after it are not this attempt's",
    )
    _limit_arguments(assess, "checking and assessing the receipt")
    assess.add_argument("--json", action="store_true")
    describe = operations.add_parser("domain", help="validate a domain and list its vocabulary")
    _domain_arguments(describe)
    _limit_arguments(describe, "checking the domain")


# A command with no packet to declare its bounds takes them on its command line, both required,
# and runs under the one budget they make.
# am[implements a-rel-nd-validation-runner-1018@f3f0b6] am[implements a-rel-mig-cli-1018@2adefb]
def _limit_arguments(parser: argparse.ArgumentParser, work: str) -> None:
    parser.add_argument("--inference-budget", type=_positive(int), required=True,
                        help=f"maximum engine inferences for {work}")
    parser.add_argument("--timeout-seconds", type=_positive(float), required=True,
                        help=f"maximum seconds for {work}")


# am[implements a-rel-mig-cli-1018@2adefb]
def _limits(args: argparse.Namespace) -> RunBudget:
    return RunBudget(inference_budget=args.inference_budget, timeout_seconds=args.timeout_seconds)


# A bound the command line gives must be a positive number, refused as a usage error before any
# budget is made. An inference bound is a whole number of any size, so only a float bound is checked
# for finiteness: math.isfinite converts an int to float, which overflows past the float range
# (c-rel-num-cli-int-bound-1018).
# am[implements a-rel-nd-validation-runner-1018@f3f0b6] am[implements a-integrate-relevance-numeric-boundaries-1018@4c2a7d]
def _positive(kind: type) -> Any:
    def read(written: str) -> Any:
        try:
            value = kind(written)
        except ValueError:
            raise argparse.ArgumentTypeError(f"not a number: {written!r}") from None
        if value <= 0 or (isinstance(value, float) and not math.isfinite(value)):
            raise argparse.ArgumentTypeError(f"must be a positive finite number: {written!r}")
        return value

    return read


# am[implements a-rel-cli-1016@8f8ec8]
def _domain_arguments(parser: argparse.ArgumentParser) -> None:
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--domain", default=DEFAULT_DOMAIN, help="a packaged domain name")
    choice.add_argument("--domain-file", help="a domain .metta file instead of a packaged one")
    parser.add_argument("--json", action="store_true")


# am[implements a-rel-cli-1016@8f8ec8] am[addresses i-rel-unreachable-1016@f105ff]
def run_relevance(args: argparse.Namespace) -> int:
    """Run one relevance operation: print its result and answer 0, or print a typed error and answer 1."""

    try:
        payload = _result(args)
    except DomainError as error:
        return _fail({"code": "invalid-domain", "message": str(error), "details": {}}, args.json)
    except RelevanceError as error:
        return _fail(error.to_dict(), args.json)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print(args.relevance_operation, payload)
    return 0


# am[implements a-rel-cli-1016@8f8ec8] am[implements a-rel-rcpt-v2-assessment-1017@25ad31]
# am[implements a-integrate-domain-review-budget-1018@a84bf4] am[implements a-rel-mig-cli-1018@2adefb]
# am[implements a-v2-cli-freshness-stream-1020@14de3d]
# am[implements a-v2-relevance-error-boundary-1020@bd1acf]
def _result(args: argparse.Namespace) -> dict[str, object]:
    operation = args.relevance_operation
    if operation == "assess":
        budget = _limits(args)
        return assess_receipt(
            _read_json(args.review, "invalid-record"),
            parse_receipt(_read_json(args.receipt, "invalid-record"), budget=budget),
            budget=budget,
            next_attempt_at=None if args.next_attempt_at is None else _instant(args.next_attempt_at, "--next-attempt-at"),
        )
    if operation == "domain":
        return _describe(_domain(args, _limits(args)))
    # The packet's bounds make the one budget the domain is checked under and the review spends.
    packet = parse_packet(_read_json(args.packet, "invalid-packet"))
    budget = packet.budget.run_budget()
    domain = _domain(args, budget)
    motivation = None
    if args.motivation is not None:
        from .motivation.requests import stream_snapshot

        try:
            motivation = stream_snapshot(_read_json(args.motivation, "invalid-motivation"), domain,
                                         as_of=packet.as_of, budget=budget)
        except BudgetExhausted as error:
            raise stopped(error) from error
        except (InvalidInputError, PersistenceError) as error:
            raise RelevanceError("invalid-motivation", str(error), details=error.details) from error
    if operation == "review":
        return review(domain, packet, budget=budget, motivation=motivation).to_dict()
    # am[implements a-ie-host-freshness-1018@ff618a]
    engine = engine_identity(budget=budget)
    return check_freshness(_read_json(args.review, "invalid-record"), domain, packet, engine,
                           budget=budget, motivation=motivation).to_dict()


# am[implements a-rel-rcpt-v2-instants-1017@3a3b0d]
def _instant(written: str, where: str) -> datetime:
    try:
        return parse_instant(written)
    except ValueError as error:
        raise RelevanceError("invalid-record", f"{where} {error}, got {written!r}") from None


# am[implements a-rel-cli-1016@8f8ec8]
def _fail(error: dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": error}, indent=2, sort_keys=True))
    else:
        print(f"goalchainer relevance error [{error['code']}]: {error['message']}", file=sys.stderr)
    return 1


# A domain is checked under the command's budget, and a budget it uses up stops the command with
# the review's own typed error.
# am[implements a-rel-cli-1016@8f8ec8] am[implements a-rel-nd-validation-runner-1018@f3f0b6]
# am[implements a-ie-sr-select-domain-1018@577734]
def _domain(args: argparse.Namespace, budget: RunBudget) -> Domain:
    try:
        return selected_domain(path=args.domain_file, packaged=None if args.domain_file else args.domain, budget=budget)
    except BudgetExhausted as error:
        raise stopped(error) from error


# A JSON input, or the input's typed error, whatever stops the read (c-rel-cli-reader-leaks-1018):
# domains.forms.input_text reads a file, or standard input's bytes, as UTF-8 whatever the process
# locale, and refuses in file_text's words what is no UTF-8 text, a standard input with no byte
# stream to read included, such as the None fd 0 closed leaves (c-rel-stdin-closed-none-1018). Then
# json.loads raises JSONDecodeError for malformed text, a plain ValueError for an integer literal
# longer than the interpreter's digit limit, so a packet whose number has 5001 digits is an invalid
# packet as a malformed one is (c-rel-num-reader-digit-limit-1018), and RecursionError for JSON
# nested deeper than it reaches.
# am[implements a-rel-cli-1016@8f8ec8] am[implements a-integrate-packet-number-refusal-1018@aecbf3]
# am[rests-on c-sn-overflow-and-digit-limits-1018@0e7f7d] am[implements a-rel-cli-reader-unreadable-1018@cbbab6]
# am[implements a-rel-cli-stdin-utf8-1018@18df88] am[implements a-sc-relevance-reads-input-text-1018@0fe1b8]
# am[implements a-v2-json-input-1020@b37a9e]
def _read_json(path: str, code: str) -> Any:
    def refuse(message: str) -> RelevanceError:
        return RelevanceError(code, message)  # type: ignore[arg-type]

    text = input_text(path, refuse)
    try:
        return loads(text)
    except json.JSONDecodeError as error:
        raise refuse(f"{path} is not JSON: {error}") from None
    except (ValueError, RecursionError) as error:
        raise refuse(f"{path} cannot be read as JSON: {error}") from None


# am[implements a-rel-cli-1016@8f8ec8] am[implements a-rel-nd-unread-signals-1018@f57790]
def _describe(domain: Domain) -> dict[str, object]:
    return {
        "title": domain.title,
        "source": domain.source,
        "policy_version": domain.policy_version,
        "digest": domain.digest,
        "authorities": [{"id": t.id, "rank": t.rank, "description": t.description} for t in domain.authorities],
        "estimator_ceilings": dict(domain.estimator_ceilings),
        "actions": [{"id": a.id, "label": a.label, "authority": a.authority} for a in domain.actions],
        "goals": [
            {"id": g.id, "kind": g.kind, "priority": g.weight, "priority_source": g.priority_source}
            for g in domain.goals
        ],
        "signals": [{"id": s.id, "description": s.description} for s in domain.signals],
        "dimensions": [{"id": d.id, "polarity": d.polarity} for d in domain.dimensions],
        "unestimated_dimensions": list(domain.unestimated_dimensions),
        "unread_signals": list(domain.unread_signals),
        "rules": len(domain.rules),
    }


# am[implements a-rel-cli-1016@8f8ec8]
def _print(operation: str, payload: dict[str, Any]) -> None:
    """A readable account of a relevance result; `--json` prints the record itself."""

    if operation == "review":
        print(format_review(payload))
    elif operation == "check":
        _print_check(payload)
    elif operation == "assess":
        _print_assessment(payload)
    else:
        _print_domain(payload)


# am[implements a-rel-cli-1016@8f8ec8]
def _print_domain(payload: dict[str, Any]) -> None:
    print(f"{payload['title']} ({payload['policy_version']}, {payload['digest']})")
    print(f"  {len(payload['actions'])} actions, {len(payload['goals'])} goals, "
          f"{len(payload['signals'])} signals, {len(payload['dimensions'])} dimensions, "
          f"{payload['rules']} rules")
    if payload["unestimated_dimensions"]:
        print(f"  no rule estimates: {', '.join(payload['unestimated_dimensions'])}")


# am[implements a-rel-cli-1016@8f8ec8]
# am[implements a-v2-cli-freshness-stream-1020@14de3d]
def _print_check(payload: dict[str, Any]) -> None:
    print(f"review {payload['review_id']} is {payload['status']} ({payload['fingerprint']})")
    for change in payload["changes"]:
        print(f"  {change['signal']}: {change['was']['state']} -> {change['now']['state']}")
    for flag in ("policy_changed", "review_policy_changed", "engine_changed", "authority_changed", "motivation_changed"):
        if payload[flag]:
            print(f"  {flag.replace('_', ' ')}")
    if payload["status"] == "stale":
        print("  the earlier result lost its support; review again, and read nothing into alternatives")


# am[implements a-rel-cli-1016@8f8ec8] am[implements a-rel-rcpt-v2-assessment-1017@25ad31]
def _print_assessment(payload: dict[str, Any]) -> None:
    window = [f"applied {payload['applied_at']}" if payload["applied"] else "not applied", f"issued {payload['issued_at']}"]
    if payload["next_attempt_at"] is not None:
        window.append(f"next attempt {payload['next_attempt_at']}")
    print(f"receipt for {payload['action']}, attempt {payload['attempt']} ({', '.join(window)})")
    for item in payload["effects"]:
        print(f"  effect {item['dimension']} {item['band']}: {_graded(item)}")
    for item in payload["contributions"]:
        print(f"  contribution to {item['goal']} {item['band']}: {_graded(item)}")
    for goal in payload["goals"]:
        print(f"  goal {goal['goal']}: achievement {goal['achievement']}")
    for entry in payload["uncounted"]:
        observation = entry["observation"]
        print(f"  not counted ({entry['reason']}): {observation['about']} {observation['target']} "
              f"from {observation['source']}")


# A confirmed or missed prediction says whether the attempt was named as producing what was seen,
# since the outcome having been seen after it is not the attempt having caused it.
# am[implements a-rel-rcpt-v2-assessment-1017@25ad31]
def _graded(item: dict[str, Any]) -> str:
    if item["status"] not in ("confirmed", "missed"):
        return item["status"]
    credited = "attributed to the attempt" if item["attribution"] == "asserted" else "not attributed"
    return f"{item['status']}, {credited}"


# Text, not printing, so a caller can indent it under its own heading or print it as it is.
# Time: linear in the displayed proposal, need, authority, escalation and ranking fields.
# am[implements a-rel-cli-1016@8f8ec8] am[implements a-rel-format-review-public-1018@e7baab]
# am[rests-on c-rel-review-text-printed-directly-1018@ef41f6]
# am[implements a-v2-cli-skill-surface-1020@6f755c]
# am[implements a-v2-hold-label-1020@4c7833]
def format_review(record: Mapping[str, Any]) -> str:
    """The review record's text, one line per fact, as `goalchainer relevance review` prints it."""

    lines = [f"relevance review {record['review_id']} of {record['subject']} "
             f"({record['domain']['policy_version']}, {record['fingerprint']})"]
    proposal = record["proposal"]
    if proposal is not None:
        lines.append(f"disposition: propose {proposal['action']} ({proposal['deontic']}, decided at {proposal['decided_at']})")
        lines.append(f"  action authority ceiling {proposal['action_authority_ceiling']}; "
                     f"licensed ceiling {proposal['licensed_authority_ceiling']}; authorization {proposal['authorization']}")
        for limit in proposal["authority_limits"]:
            lines.append(f"    lowered by {limit['basis']} [{limit['estimator']}] to {limit['ceiling']}")
        path = proposal["carrying_path"]
        if path is not None:
            value = (f"need {path['need']}, value [{path['value']['low']}, {path['value']['high']}]"
                     if "need" in path else path["band"])
            lines.append(f"  carrying path: {path['goal']} (priority {path['priority']} from "
                         f"{path['priority_source']}) {value}")
        for change in proposal.get("predicted_need_changes", []):
            expected = "unknown" if change["expected_change"] is None else change["expected_change"]
            reduction = change["reduction"]
            lines.append(f"  predicted need {change['need']}: change {expected}, "
                         f"urgency reduction [{reduction['low']}, {reduction['high']}]")
    else:
        lines.append(f"disposition: {record['disposition']}")
    if record.get("hold") is not None:
        for field, label in (("satisfied", "needs in their target bands"), ("unserved", "needs outside their target bands")):
            if record["hold"][field]:
                lines.append(f"  {label}: {', '.join(record['hold'][field])}")
    if record.get("motivation") is not None:
        motivation = record["motivation"]
        lines.append(f"  motivation at {motivation['as_of']} (stream {motivation['stream']})")
        for level in motivation["levels"]:
            value = "unknown" if level["level"] is None else level["level"]
            urgency = "unknown" if level["urgency"] is None else level["urgency"]
            lines.append(f"    {level['need']}: {level['state']}, level {value}, urgency {urgency}")
    if record["escalation"] is not None:
        for reason in record["escalation"]["reasons"]:
            lines.append(f"  escalate: {reason}")
    for blocker in record["blockers"]:
        lines.append(f"  blocked: {blocker['action']}: {blocker['reason']}")
    for step in record["steps"]:
        removed = "; ".join(f"{item['action']} ({item['reason']})" for item in step["eliminated"])
        lines.append(f"  {step['name']}: {removed or 'nothing removed'}")
    missing = record["missing_information"]
    if missing["unknown_signals"]:
        lines.append(f"  unknown and decision-relevant: {', '.join(missing['unknown_signals'])}")
    if missing["unestimated_dimensions"]:
        lines.append(f"  no estimate anywhere for: {', '.join(missing['unestimated_dimensions'])}")
    lines.append(f"  engine inferences: {record['engine']['inferences']} of {record['engine']['budget']['inferences']}")
    lines.append("  applies effects: no")
    return "\n".join(lines)

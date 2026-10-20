"""Purpose: give the readable account `goalchainer show` prints of a `goalchainer request` result: the
review and its motivational support, any text reading, the plan, inquiry or no-plan answer or the admission verdict, and what the
request leaves to its host, each line read off the result's own records.

The account evaluates nothing and needs no budget, so it can be printed from a saved result, and it
says nothing the result does not: a step line names the step's kind, procedure, step id, application,
instance and bound entities; an inquiry names the literal and the investigator the planner chose, then
each branch; a no-plan answer names each unestablished goal literal with the planner's reason. The
review is worded as `goalchainer relevance review` words it. A result that is a typed error is shown as
that error with status 1, as the request command answered. An input that is no request result, or any
part of which the account reads holds a value of another kind than a request writes there, a number
outside what its producer writes included, is refused as InvalidInputError before anything is worded, so
the account never fails otherwise and never words a value as something it is not.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .errors import InvalidInputError
from .planning.procedures import literal_text
from .planning.projection import (
    Admitted,
    Ambiguous,
    Answer,
    Blocked,
    Inquiry,
    NoPlan,
    Plan,
    PlanStep,
    Progress,
    Verdict,
)
from .planning.transport import decode
from .relevance.errors import RelevanceError
from .relevance.motivation import LEVEL_STATES
from .relevance.records import check_record
from .relevance_cli import format_review
from .requests import REQUEST_PROTOCOL

# What each operation's result carries beside the review: the key the planner's answer is under.
# am[implements a-dd-show-1018@f9e4e9]
_ANSWER_KEY = {"review": None, "plan": "planning", "admit": "admission"}

# Every part of a result the account reads, as check_record shapes: what the request writes there, so
# no later read can fail or word a value of another kind. A part that is only required present here,
# `object`, is checked where it is read: a number by _number, an object that may be null by its own
# shape once it is not, and the planner's answer by the transport.
# am[implements a-sb-shape-boundary-1018@917de5] am[rests-on c-sb-check-record-convention-1018@eff188]
_RESULT = {"protocol": str, "operation": str, "review": object, "authorization": str, "applies_effects": bool,
           "inferences": object}
_ERROR = {"error": {"code": str, "message": str}}
# What format_review reads of the review record (relevance_cli.format_review).
_REVIEW = {
    "review_id": str, "subject": str, "domain": {"policy_version": str}, "fingerprint": str, "disposition": str,
    "proposal": object, "escalation": object,
    "blockers": [{"action": str, "reason": str}],
    "steps": [{"name": str, "eliminated": [{"action": str, "reason": str}]}],
    "missing_information": {"unknown_signals": [str], "unestimated_dimensions": [str]},
    "engine": {"inferences": object, "budget": {"inferences": object}},
}
_PROPOSAL = {
    "action": str, "deontic": str, "decided_at": str, "action_authority_ceiling": str,
    "licensed_authority_ceiling": str, "authorization": str,
    "authority_limits": [{"basis": str, "estimator": str, "ceiling": str}], "carrying_path": object,
}
_CARRYING_PATH = {"goal": str, "priority": object, "priority_source": str}
# am[implements a-v2-cli-skill-surface-1020@6f755c]
_HOLD = {"satisfied": [str], "unserved": [str]}
_MOTIVATION = {"stream": (str, type(None)), "as_of": str,
               "levels": [{"need": str, "state": str, "level": object, "urgency": object}]}
# A prediction names the level observed now and its state apart from the level it predicts.
# am[implements a-v2r-predicted-level-1020]
_PREDICTED_NEEDS = [{"need": str, "expected_change": object, "observed_level": object, "level_state": str,
                     "predicted_level": object, "reduction": object, "status": str}]
_ESCALATION = {"reasons": [str]}
_READING = {
    "model": str, "domain": str, "declaration": str,
    "propositions": [{"id": str, "answer": str, "direction": str, "probability": object}],
    "choices": [{"id": str, "answer": str, "probability": object}],
}


# The account in the order a person checks it: what the model found, the review first, then any reading
# and the planner's answer, then the request's own line, which says the host still decides and that
# nothing was applied.
# Time and space: linear in the size of the result.
# am[implements a-dd-show-1018@f9e4e9] am[implements a-sb-shape-boundary-1018@917de5]
def account(result: Any) -> tuple[str, int]:
    """The readable account of `result` and the status to exit with: 1 for a typed error, else 0."""

    if not isinstance(result, Mapping):
        raise InvalidInputError(f"The input is no JSON object, so it is no {REQUEST_PROTOCOL} result.")
    try:
        if result.get("ok") is False:
            error = check_record(result, _ERROR, "error result")["error"]
            return f"GoalChainer error [{error['code']}]: {error['message']}", 1
        operation = result.get("operation")
        if result.get("protocol") != REQUEST_PROTOCOL or not isinstance(operation, str) or operation not in _ANSWER_KEY:
            raise InvalidInputError(f"The input is not a {REQUEST_PROTOCOL} result.",
                                    details={"protocol": result.get("protocol"), "operation": operation})
        key = _ANSWER_KEY[operation]
        _check(result, key)
        answer = None if key is None else decode(result[key], Answer if operation == "plan" else Verdict)
        _planner_numbers(answer, key)
    except RelevanceError as error:
        raise InvalidInputError(f"The input is no {REQUEST_PROTOCOL} result the account can read: {error.message}.",
                                details={"fault": error.message}) from None
    lines = [format_review(result["review"])]
    if "reading" in result:
        lines += _reading(result["reading"])
    if operation == "plan":
        lines += _answer(answer, 0)
    elif operation == "admit":
        lines.append(_verdict(answer))
    lines.append(f"request: authorization {result['authorization']}, "
                 f"applies effects {'yes' if result['applies_effects'] else 'no'}, {result['inferences']} inferences")
    return "\n".join(lines), 0


# Every part of the result the account words, before any is worded: the result's own fields and its
# answer's presence, the review record's, each proposal, carrying path and escalation it holds, and any
# reading's, each number against what its producer writes there (c-sn-producer-number-contracts-1018):
# an inference count as RunBudget charges one, the review's budget as a packet requires one, a goal
# priority as a Goal holds one and a probability as the semantic reader writes one.
# Time: linear in the size of the checked parts.
# am[implements a-sb-shape-boundary-1018@917de5] am[rests-on c-sb-check-record-convention-1018@eff188]
# am[implements a-sn-contract-numbers-1018@c1d969] am[rests-on c-sn-producer-number-contracts-1018@f9ac2e]
# am[implements a-v2-cli-skill-surface-1020@6f755c]
def _check(result: Mapping[str, Any], key: str | None) -> None:
    check_record(result, {**_RESULT, **({key: object} if key else {})}, "request result")
    _number(result["inferences"], "request result.inferences", 0, whole=True)
    review = check_record(result["review"], _REVIEW, "review record")
    _number(review["engine"]["inferences"], "review record.engine.inferences", 0, whole=True)
    _number(review["engine"]["budget"]["inferences"], "review record.engine.budget.inferences", 1, whole=True)
    proposal = review["proposal"]
    if proposal is not None:
        check_record(proposal, _PROPOSAL, "review record.proposal")
        if proposal["carrying_path"] is not None:
            path = check_record(proposal["carrying_path"], _CARRYING_PATH, "review record.proposal.carrying_path")
            _number(path["priority"], "review record.proposal.carrying_path.priority", 0)
            if ("need" in path) == ("band" in path):
                raise RelevanceError("invalid-record", "a carrying path must name either a need or a contribution band")
            if "need" in path:
                check_record(path, {"need": str, "value": object}, "review record.proposal.carrying_path")
                _interval(path["value"], "review record.proposal.carrying_path.value")
            else:
                check_record(path, {"band": str}, "review record.proposal.carrying_path")
        for index, prediction in enumerate(check_record(proposal.get("predicted_need_changes", []),
                                                        _PREDICTED_NEEDS, "review record.proposal.predicted_need_changes")):
            where = f"review record.proposal.predicted_need_changes[{index}]"
            if prediction["status"] != "predicted":
                raise RelevanceError("invalid-record", f"{where}.status must be predicted")
            if prediction["level_state"] not in LEVEL_STATES:
                raise RelevanceError("invalid-record", f"{where}.level_state must be one of {', '.join(LEVEL_STATES)}")
            if (prediction["observed_level"] is None) == (prediction["level_state"] == "observed"):
                raise RelevanceError("invalid-record", f"{where}.observed_level must be a number exactly when the level is observed")
            for name in ("observed_level", "expected_change"):
                if prediction[name] is not None:
                    _number(prediction[name], f"{where}.{name}", -math.inf)
            _interval(prediction["predicted_level"], f"{where}.predicted_level")
            _interval(prediction["reduction"], f"{where}.reduction", -1, 1)
    held = review.get("hold")
    if held is not None or review["disposition"] == "hold":
        check_record(held, _HOLD, "review record.hold")
    if review.get("motivation") is not None:
        motivation = check_record(review["motivation"], _MOTIVATION, "review record.motivation")
        for index, level in enumerate(motivation["levels"]):
            where = f"review record.motivation.levels[{index}]"
            for name, least, most in (("level", -math.inf, None), ("urgency", 0, 1)):
                if level[name] is not None:
                    _number(level[name], f"{where}.{name}", least, most)
    if review["escalation"] is not None:
        check_record(review["escalation"], _ESCALATION, "review record.escalation")
    if "reading" in result:
        reading = check_record(result["reading"], _READING, "reading record")
        for part in ("propositions", "choices"):
            for index, item in enumerate(reading[part]):
                _number(item["probability"], f"reading record.{part}[{index}].probability", 0, 1)


# am[implements a-v2-cli-skill-surface-1020@6f755c]
def _interval(value: Any, what: str, least: float = -math.inf, most: float | None = None) -> None:
    check_record(value, {"low": object, "high": object}, what)
    for endpoint in ("low", "high"):
        _number(value[endpoint], f"{what}.{endpoint}", least, most)
    if value["low"] > value["high"]:
        raise RelevanceError("invalid-record", f"{what}.low must not exceed high")


# The planner's numbers the account words, against what the planner writes: each step's application,
# which projection._steps numbers from 0, and an ambiguous verdict's successor classes, of which there
# are more than one (projection.Ambiguous).
# Time: linear in the answer's steps and branches.
# am[implements a-sn-contract-numbers-1018@c1d969] am[rests-on c-sn-producer-number-contracts-1018@f9ac2e]
def _planner_numbers(answer: Answer | Verdict | None, path: str | None) -> None:
    if isinstance(answer, Plan):
        for index, step in enumerate(answer.steps):
            _number(step.application, f"{path}.steps[{index}].application", 0, whole=True)
    elif isinstance(answer, Inquiry):
        _planner_numbers(answer.if_true, f"{path}.if_true")
        _planner_numbers(answer.if_false, f"{path}.if_false")
    elif isinstance(answer, NoPlan) and answer.alternative is not None:
        _planner_numbers(answer.alternative, f"{path}.alternative")
    elif isinstance(answer, Ambiguous):
        _number(answer.classes, f"{path}.classes", 2, whole=True)


# A number the account words, a whole one where `whole`, else a finite one, from `least` up to `most`.
# check_record reads a leaf with isinstance, which counts a JSON true or false, a Python bool, as an int,
# so a boolean is refused here as the repository's other JSON readers refuse one where a number is
# declared. The bounds are compared before anything converts the number, so ten to the thousandth is
# refused rather than overflowing a float, and NaN fails as a non-finite float; a whole number must also
# be one the interpreter can write as text (c-sn-overflow-and-digit-limits-1018).
# am[implements a-sb-shape-boundary-1018@917de5] am[rests-on c-sb-bool-number-predicate-1018@ab0821]
# am[implements a-sn-contract-numbers-1018@c1d969] am[rests-on c-sn-overflow-and-digit-limits-1018@0e7f7d]
def _number(value: Any, what: str, least: float, most: float | None = None, *, whole: bool = False) -> None:
    kind = isinstance(value, int) if whole else (isinstance(value, int) or (isinstance(value, float) and math.isfinite(value)))
    if (isinstance(value, bool) or not kind or value < least or (most is not None and value > most)
            or not _writable(value)):
        bounds = f"from {least} to {most}" if most is not None else f"of at least {least}"
        raise RelevanceError("invalid-record", f"{what} must be {'a whole' if whole else 'a finite'} number {bounds}")


# Whether the interpreter writes `value` as text: an int of more digits than
# sys.get_int_max_str_digits() raises ValueError when written, as json.dumps would too.
# am[implements a-sn-contract-numbers-1018@c1d969] am[rests-on c-sn-overflow-and-digit-limits-1018@0e7f7d]
def _writable(value: float) -> bool:
    if isinstance(value, float):
        return True
    try:
        str(value)
    except ValueError:
        return False
    return True


# A reading's answer for each proposition and choice, with the probability the model gave it; the
# rows it adds enter the review as model-proposed observations, which the review's account lists.
# am[implements a-dd-show-1018@f9e4e9]
def _reading(reading: Mapping[str, Any]) -> list[str]:
    lines = [f"reading by {reading['model']} under {reading['domain']} ({reading['declaration']})"]
    lines += [f"  {item['id']}: {item['answer']} ({item['direction']}, probability {item['probability']:.2f})"
              for item in reading["propositions"]]
    lines += [f"  {item['id']}: {item['answer']} (probability {item['probability']:.2f})" for item in reading["choices"]]
    return lines


# One planner answer, an inquiry's branches indented beneath it.
# Time: linear in the answer's steps and branches.
# am[implements a-dd-show-1018@f9e4e9]
def _answer(answer: Answer, depth: int) -> list[str]:
    pad = "  " * depth
    if isinstance(answer, Plan):
        assumed = f", assuming {', '.join(map(literal_text, answer.assumptions))}" if answer.assumptions else ""
        state = "established" if answer.established else "not yet established"
        lines = [f"{pad}plan: {len(answer.steps)} {'step' if len(answer.steps) == 1 else 'steps'}, {state}{assumed}"]
        return lines + [f"{pad}  {number}. {_step(step)}" for number, step in enumerate(answer.steps, 1)]
    if isinstance(answer, Inquiry):
        lines = [f"{pad}inquiry: {answer.investigator} can observe {literal_text(answer.literal)}"]
        for label, branch in (("if it holds", answer.if_true), ("if it does not", answer.if_false)):
            lines += [f"{pad}  {label}:", *_answer(branch, depth + 2)]
        return lines
    lines = [f"{pad}no plan"]
    for unsolved in answer.unsolved:
        waiting = f", waiting on {', '.join(map(literal_text, unsolved.unknowable))}" if unsolved.unknowable else ""
        lines.append(f"{pad}  {literal_text(unsolved.literal)}: {unsolved.reason}{waiting}")
    if answer.alternative is not None:
        lines += [f"{pad}  alternative, never a plan to act on:", *_answer(answer.alternative, depth + 2)]
    return lines


# A step as its fields give it: its kind, procedure and step id, its application, its instance when the
# journal started it, and the declared entities its binding names, each once in binding order.
# am[implements a-dd-show-1018@f9e4e9]
def _step(step: PlanStep) -> str:
    parts = [f"{step.kind} {step.procedure}" + (f" {step.step}" if step.step is not None else ""),
             f"application {step.application}"]
    if step.instance_id is not None:
        parts.append(f"instance {step.instance_id}")
    entities = list(dict.fromkeys(entity for _, entity in step.binding))
    if entities:
        parts.append(f"on {', '.join(entities)}")
    return ", ".join(parts)


# am[implements a-dd-show-1018@f9e4e9]
def _verdict(verdict: Verdict) -> str:
    if isinstance(verdict, Admitted):
        return f"admission: admitted, occurrence {verdict.occurrence}"
    if isinstance(verdict, Blocked):
        return f"admission: blocked, waiting on {', '.join(_waiting(item) for item in verdict.waiting_on)}"
    if isinstance(verdict, Ambiguous):
        return (f"admission: ambiguous, the matching occurrences fall in {verdict.classes} successor classes, "
                "and the executor must not choose")
    return f"admission: stale, the step's rules changed since the plan ({verdict.expected} planned, {verdict.found} now)"


# am[implements a-dd-show-1018@f9e4e9]
def _waiting(item: Any) -> str:
    if isinstance(item, Progress):
        return f"instance {item.instance_id} step {item.step} {'done' if item.done else 'not done'}"
    return literal_text(item)


__all__ = ["account"]

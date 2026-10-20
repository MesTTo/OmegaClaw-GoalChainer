"""Purpose: run GoalChainer's justification kernel, planning/justification.metta, through
goal_chainer.runtime's evaluator as the module group JUSTIFICATION under the caller's RunBudget, and
read each answer as typed labels.

The kernel owns the reasoning (c-integrate-user-metta-policy-1016). Its group loads the shared
vocabulary module, goal_chainer/domains/vocabulary.metta, whose estimator classes, source tiers,
establishing cut and reading expiry the kernel calls, then the kernel, into a space of its own once
per process, and compiles them with a warm-up no caller's inferences pay for. Each call evaluates
one typed entry on one immutable snapshot inside that space's speculative scope, keeping nothing
between calls:

    justify(rows, at=AS_OF, budget=budget)            -> Justification
    justify_frame(frame, budget=budget)               -> Justification over an abstract frame
    knowledge(literal, justification, budget=budget)  -> Knowledge

The first call prepares the group inside its own deadline; a caller wanting that work done earlier
calls goal_chainer.runtime.evaluator.prepare(JUSTIFICATION, budget=budget), which answers the
group's identity.

Rows, frames and literals are pymetta atoms, built with metta.S and metta.Expression, and cross as
holes, never as source text. A call without a RunBudget raises InvalidInputError. A snapshot the
kernel refuses raises JustificationRefused naming each problem; a budget the evaluation exhausts
raises InferenceBudgetExceeded or ReviewTimeout and is charged what it spent; a call the kernel
answers other than once, or with an answer outside the grammar its entries declare, raises
ProtocolError before any record is built, and one the engine refuses MettaEngineError.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Literal, get_args, get_type_hints

from ..domains.loader import VOCABULARY_FILE
from ..errors import InvalidInputError, ProtocolError
from ..runtime.budget import RunBudget
from ..runtime.evaluator import ModuleGroup, evaluate, plain_value

KERNEL = Path(__file__).resolve().with_name("justification.metta")
# The estimator classes, their tiers, the establishing cut and reading expiry have one home, the
# shared vocabulary module below relevance and the kernel, which reads only core operations, so the
# group loads it by path to define what the kernel calls. Every group holding the kernel, the
# planner's among them, imports its own copy of both from the same pinned bytes. The warm-up runs
# each entry once per process outside any speculation, since an evaluation compiles inside a
# speculative scope that discards what it compiled.
# am[implements a-jk-placement-1018@a9cf03] am[implements a-jk-rr-kernel-shared-1018@0d101b]
# am[implements a-rt-rb-migrate-justification-1018@439e90]
# am[rests-on c-jk-ev-warm-up-load-bearing-1018@7fcf34] am[rests-on c-jk-ev-no-prepare-alias-1018@b9a688]
JUSTIFICATION = ModuleGroup("justification", (VOCABULARY_FILE, KERNEL), warm_ups=("gc-justification-warm-up",))

Status = Literal["Accepted", "Refuted", "Undecided", "Unsupported"]
Check = Literal["Checked", "Unchecked"]
State = Literal["Holds", "Withdrawn", "Undecided"]


# One argument's answer, as plain values. In a snapshot's answer the argument is its reference,
# (Claim CLAIM), (Observation OBS), (Row ROW) or (Stated TERM), so two arguments spelled alike stay
# two; in a frame's it is the caller's own name.
# am[implements a-jk-metta-kernel-1018@258f74] am[implements a-jk-rr-row-report-1018@6747d2]
# am[implements a-jk-typed-boundary-1018@dee690]
@dataclass(frozen=True, slots=True)
class Label:
    argument: Any
    status: Status
    check: Check


# One link's state by undercut alone: a From row's support of its claim in a snapshot's answer,
# keyed by (Row ROW), any declared link in a frame's. A row grounds its claim when its Label is
# Accepted and its Link Holds; a current row that lost to a preferred contrary is Refuted with its
# Link holding.
# am[implements a-jk-metta-kernel-1018@258f74] am[implements a-jk-rr-row-report-1018@6747d2]
# am[implements a-jk-typed-boundary-1018@dee690]
@dataclass(frozen=True, slots=True)
class Link:
    link: Any
    state: State


# The kernel's answer to one snapshot. `term` is the answer atom itself, to hand back to MeTTa, as
# knowledge() does, so no caller rebuilds it.
# am[implements a-jk-metta-kernel-1018@258f74]
@dataclass(frozen=True, slots=True)
class Justification:
    labels: tuple[Label, ...]
    links: tuple[Link, ...]
    term: Any


# What one snapshot knows about one literal: value None is Unknown, nothing observed, never False.
# am[implements a-jk-knowledge-witness-1018@861c8d]
@dataclass(frozen=True, slots=True)
class Knowledge:
    value: bool | None
    check: Check | None


# A snapshot the kernel refused. details["problems"] lists each (Problem KIND DETAIL) in MeTTa's
# own syntax, JSON-ready for the CLI, and `problems` keeps them as plain values.
# am[implements a-jk-metta-kernel-1018@258f74] am[rests-on c-rt-jk-placement-answers-1018@68df20]
class JustificationRefused(InvalidInputError):
    def __init__(self, problems: tuple[Any, ...], rendered: list[str]) -> None:
        super().__init__(
            f"the justification kernel refused the snapshot: {'; '.join(rendered)}",
            details={"problems": rendered},
        )
        self.problems = problems


# Time: one evaluation of gc-justify, the kernel's fixpoint over the snapshot, charged to `budget`,
# after the group's preparation once per process.
# am[implements a-jk-metta-kernel-1018@258f74] am[implements a-jk-contract-literal-rows-1018@5a7264]
# am[implements a-jk-rr-row-report-1018@6747d2] am[implements a-rt-rb-migrate-justification-1018@439e90]
def justify(rows: Iterable[Any], *, at: int, budget: RunBudget) -> Justification:
    """The labels of one snapshot of evidence rows at AS-OF `at`, microseconds since the epoch.

    Each row is (From CLAIM SOURCE) or (Withdrawn (From CLAIM SOURCE) REASON) as a pymetta atom, a
    SOURCE (Observation OBS) or (Claim CLAIM) and a REASON any of those, (Row ROW) or
    (Stated TERM); the kernel documents the contract. Every argument is labelled by that reference,
    and each row's Link, keyed (Row ROW), gives the state of its support of the claim. Row order and
    repetition never change the answer.
    """

    from metta import Expression, S  # noqa: PLC0415 (pymetta loads with the engine)

    return _read(evaluate(JUSTIFICATION, "gc-justify", S.At(at), Expression(*rows), budget=budget))


# Time: one evaluation of gc-justify-frame charged to `budget`, after the group's preparation.
# am[implements a-jk-semantics-1018@8cb82d] am[implements a-rt-rb-migrate-justification-1018@439e90]
def justify_frame(frame: Any, *, budget: RunBudget) -> Justification:
    """The labels of an abstract frame, (Frame ARGS SUPPORTS ATTACKS UNDERCUTS ESTABLISHED)."""

    return _read(evaluate(JUSTIFICATION, "gc-justify-frame", frame, budget=budget))


# Time: one evaluation of gc-justification-knowledge charged to `budget`, after the group's
# preparation.
# am[implements a-jk-knowledge-witness-1018@861c8d] am[implements a-rt-rb-migrate-justification-1018@439e90]
# am[implements a-integrate-justification-result-refusal-1018@9a83ce]
def knowledge(literal: Any, justification: Justification, *, budget: RunBudget) -> Knowledge:
    """What `justification` knows about `literal`: True from its own Accepted label, False from its
    contrary's, each with that label's check, and Unknown otherwise. The kernel answers Unknown or
    (Known BOOL CHECK); any other answer raises ProtocolError."""

    answer = plain_value(evaluate(JUSTIFICATION, "gc-justification-knowledge", literal, justification.term, budget=budget))
    if _symbol(answer) == "Unknown":
        return Knowledge(None, None)
    if isinstance(answer, tuple) and len(answer) == 3 and _symbol(answer[0]) == "Known" and isinstance(answer[1], bool):
        check = _member(answer[2], Check)
        if check is not None:
            return Knowledge(answer[1], check)  # type: ignore[arg-type]
    raise ProtocolError("The justification kernel answered knowledge out of contract.", details={"answer": repr(answer)})


# Each row kind of a (Justification ROW ...) answer, by its head symbol, with the record it builds
# and the Literal of each value after its term. A row is (KIND TERM VALUE ...): TERM, any term at
# all, becomes the record's first field as it stands, a frame's own names and a snapshot's
# references alike, and each VALUE must be a symbol naming a value its field's Literal declares. The
# table is read off Label and Link themselves, so each kind, arity and value has one definition.
# am[implements a-integrate-justification-result-refusal-1018@9a83ce]
_ROWS: dict[str, tuple[type, tuple[Any, ...]]] = {
    record.__name__: (record, tuple(get_type_hints(record)[field.name] for field in fields(record)[1:]))
    for record in (Label, Link)
}


# The kernel's answer read against the grammar its entries declare, before any record is built:
#   (Justification ROW ...)               each ROW as _ROWS reads it, no row at all included
#   (Refused (Problem KIND DETAIL) ...)   one problem or more, each KIND a symbol
# Anything else raises ProtocolError naming what it found: an answer of another head, a row that is
# no expression or of an unknown or misspelled kind or another arity, a value its Literal does not
# name, a String where a symbol belongs, or a refusal with no well-formed problem.
# Time: linear in the size of the answer.
# am[implements a-jk-metta-kernel-1018@258f74] am[implements a-integrate-justification-result-refusal-1018@9a83ce]
def _read(answer: Any) -> Justification:
    value = plain_value(answer)
    head = _symbol(value[0]) if isinstance(value, tuple) and value else None
    if head == "Refused":
        if len(value) == 1 or not all(_problem(problem) for problem in value[1:]):
            raise ProtocolError("The justification kernel answered a refusal out of contract.", details={"answer": str(answer)})
        raise JustificationRefused(value[1:], [str(problem) for problem in answer.children[1:]])
    if head != "Justification":
        raise ProtocolError("The justification kernel answered out of contract.", details={"answer": str(answer)})
    rows = [_row(row) for row in value[1:]]
    return Justification(tuple(row for row in rows if isinstance(row, Label)),
                         tuple(row for row in rows if isinstance(row, Link)), answer)


# One row of a Justification answer as its record; ProtocolError for a row out of contract.
# am[implements a-integrate-justification-result-refusal-1018@9a83ce]
def _row(row: Any) -> Label | Link:
    record, literals = _ROWS.get(_symbol(row[0]) if isinstance(row, tuple) and row else None, (None, ()))
    values = [_member(part, literal) for part, literal in zip(row[2:], literals)] if record else []
    if record is None or len(row) != 2 + len(literals) or None in values:
        raise ProtocolError("The justification kernel answered a row out of contract.", details={"row": repr(row)})
    return record(row[1], *values)


# Whether a refusal's item is (Problem KIND DETAIL) with KIND a symbol, as every refusal reads it.
# am[implements a-integrate-justification-result-refusal-1018@9a83ce]
def _problem(problem: Any) -> bool:
    return isinstance(problem, tuple) and len(problem) == 3 and _symbol(problem[0]) == "Problem" and _symbol(problem[1]) is not None


# The name of a symbol that is one of `literal`'s values, or None for anything else, a String spelled
# the same included, so a value is accepted exactly when its declared type names it.
# am[implements a-integrate-justification-result-refusal-1018@9a83ce]
def _member(value: Any, literal: Any) -> str | None:
    name = _symbol(value)
    return name if name in get_args(literal) else None


# A symbol's name, or None for anything else, so a String never passes for a constructor.
# am[implements a-jk-metta-kernel-1018@258f74]
def _symbol(value: Any) -> str | None:
    from metta import Symbol  # noqa: PLC0415

    return str(value) if isinstance(value, Symbol) else None


__all__ = [
    "JUSTIFICATION",
    "Justification",
    "JustificationRefused",
    "Knowledge",
    "Label",
    "Link",
    "justify",
    "justify_frame",
    "knowledge",
]

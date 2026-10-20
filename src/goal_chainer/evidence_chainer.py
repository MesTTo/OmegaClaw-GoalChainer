"""Purpose: answer every PLN belief PeTTaChainer proves about each caller target from the caller's statements, run in-process on pymetta as one speculative call under the caller's RunBudget.

PeTTaChainer is a MeTTa library. It loads once per process, as the library `pettachainer` bound to
the checkout the runtime resolves, into the module group pettachainer's own space, followed by
policy/goalchainer_pettachainer.metta, whose warm-up compiles the chainer outside any speculation
and then returns it to its loaded state. A statement is (: NAME CLAIM (STV S C)). One speculative
call of gc-pettachainer-grade, under what is left of the caller's RunBudget, adds every statement
to one knowledge base and queries (: $proof TARGET $tv) for each target, so nothing the grading
writes outlives it. Each answer is a PLN belief whose proof term names the statements it came
from, e.g.

    (: (merge/revision (rule-proof redaction_to_accept red_redacted) (rule-proof support_to_accept red_support))
       (Acceptable publish_redacted_summary) (STV 0.9335 0.9714))

A target the chainer proves nothing about has no answer. That is not a false belief, which is an
answer of strength 0: the caller decides what an unproved target means.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metta import Expression, Grounded, Symbol, Variable

from .errors import InvalidInputError, ProtocolError
from .runtime import evaluator
from .runtime.budget import RunBudget
from .runtime.checkouts import PETTACHAINER, checkout_dir
from .runtime.evaluator import ModuleGroup
from .runtime.modules import MettaLibrary, register_metta_library
from .runtime.numbers import finite_float

QUERY_STEPS = 20
BACKWARD_PREMISE_PREFILTER = True
GRADING_POLICY = Path(__file__).resolve().parent / "policy" / "goalchainer_pettachainer.metta"
# The library name the resolved checkout is bound to, and the module group grading runs in.
LIBRARY = "pettachainer"
GROUP = "pettachainer"
# The grading policy's entry, (gc-pettachainer-grade STATEMENTS TARGETS STEPS PREFILTER).
ENTRY = "gc-pettachainer-grade"


# One answer: its strength and confidence, and the answer atom's text, whose proof term names the
# statements it came from.
@dataclass(frozen=True)
class Belief:
    strength: float
    confidence: float
    proof: str


# What one grading answered: for each target in order, every answer in the chainer's order, an
# empty tuple where it proved nothing; and the MeTTa call that graded them.
# am[implements a-hh-gp-callable-1018]
@dataclass(frozen=True)
class Grading:
    answers: tuple[tuple[Belief, ...], ...]
    call: str


# am[implements a-rt-vendored-defaults-1016@182749]
def chainer_metta_dir() -> Path:
    return checkout_dir(PETTACHAINER) / "pettachainer" / "metta"


# PeTTaChainer loads as a registered library so the group's identity is the digest of the whole
# MeTTa tree it imports, every module under chainer/ and context/ included, not of the entry file
# alone. register_metta_library refuses a second directory under the same name and prepare a second
# group under the same name, so one process grades with one checkout. The binding takes the engine
# alone only the first time, so a grading waits for no running evaluation.
# am[implements a-hh-pc-port-1018] am[rests-on c-hh-pc-use-module-needs-lib-import-1018]
# am[implements a-rel-nd-section-warm-ups-1018@df1a66]
# am[implements a-rt-cc-rw-pool-1018]
# am[implements a-integrate-runtime-wait-deadline-1018@a74406]
def grading_group(*, budget: RunBudget | None) -> ModuleGroup:
    """The module group grading runs in, with PeTTaChainer bound as a library first, waiting for
    a first binding only until `budget`'s deadline."""

    register_metta_library(LIBRARY, chainer_metta_dir(), budget=budget)
    return ModuleGroup(
        GROUP,
        (MettaLibrary(LIBRARY, "petta_chainer"), MettaLibrary(LIBRARY, "logic_configs/pln"), GRADING_POLICY),
        warm_ups=("gc-pettachainer-warm-up",),
    )


# The one form a statement takes. Its values stay exact, since statements cross as atoms.
# am[implements a-hh-gp-callable-1018] am[implements a-hh-pc-port-1018]
def statement(name: str, claim: Any, strength: float, confidence: float) -> Expression:
    """(: NAME CLAIM (STV STRENGTH CONFIDENCE)), e.g. statement("red_redacted",
    Expression(Symbol("Redacted"), Symbol("publish_redacted_summary")), 1.0, 0.97)."""

    truth = Expression(Symbol("STV"), Grounded(float(strength)), Grounded(float(confidence)))
    return Expression(Symbol(":"), Symbol(name), claim, truth)


# Time: on a process's first call, the group's preparation: about 1 s of loading and a warm-up of
# about 115 million inferences (c-hh-pc-compile-survives-only-outside-1018), inside budget's deadline
# but charged no inferences; then one engine call of s compileadds and t bounded queries for s
# statements and t targets, about 0.6 million inferences and 0.2 s for the incident appraisal's 8
# to 10 statements and 3 targets, all charged to budget; and a check linear in their size first.
# am[implements a-hh-gp-callable-1018] am[implements a-hh-pc-port-1018]
# am[rests-on c-hh-pc-speculation-rolls-back-1018] am[rests-on c-hh-pc-scratch-equal-1018]
# am[implements a-integrate-runtime-wait-deadline-1018@a74406]
def grade(statements: Sequence[Any], targets: Sequence[Any], *, budget: RunBudget) -> Grading:
    """Query PeTTaChainer for every belief `statements` prove about each of `targets`, in-process
    under `budget`.

    Answers each target's answers in order, an empty tuple for a target the chainer proved nothing
    about, and the MeTTa call. The group's preparation and the grading run under `budget`, the
    caller's; the grading is one speculative call, so no grading sees another's statements on any
    path.

    Raises InvalidInputError, before anything runs, for a statement that is not
    (: NAME CLAIM (STV S C)) with S and C in [0, 1], two statements under one name, or a target
    holding a variable; InferenceBudgetExceeded or ReviewTimeout when `budget` stops the grading;
    ProtocolError when an answer is not a PLN belief about its target; MettaEngineError when the
    engine refuses the grading; DependencyUnavailableError without a PeTTaChainer checkout; and
    whatever the group's preparation raises.
    """

    _check(statements, targets)
    arguments = grading_arguments(statements, targets)
    answer = evaluator.evaluate(grading_group(budget=budget), ENTRY, *arguments, budget=budget)
    call = f"!({ENTRY} " + " ".join(str(argument) for argument in arguments) + ")"
    return Grading(_answers(answer, targets), call)


# am[implements a-hh-gp-callable-1018] am[implements a-hh-pc-port-1018]
def grading_arguments(statements: Sequence[Any], targets: Sequence[Any]) -> tuple[Expression, Expression, int, bool]:
    """The grading entry's arguments: the statements, the targets in order, the query's agenda
    steps and whether the backward premise prefilter runs."""

    return Expression(*statements), Expression(*targets), QUERY_STEPS, BACKWARD_PREMISE_PREFILTER


# Of several answers, the belief is the one with the highest confidence, the first on a tie.
# Time: linear in the answers.
# am[implements a-hh-gp-callable-1018]
def most_confident(answers: Sequence[Belief]) -> Belief | None:
    """The answer with the highest confidence, the first of equals; None for no answer."""

    best: Belief | None = None
    for belief in answers:
        if best is None or belief.confidence > best.confidence:
            best = belief
    return best


# What crosses the boundary, checked before the engine runs. A proof names its sources by statement
# name, so two statements under one name would leave a proof ambiguous, and a target holding a
# variable would be a pattern, whose answers are not about one claim.
# Time: linear in the statements' and targets' size.
# am[implements a-hh-gp-callable-1018] am[rests-on c-hh-gp-names-unique-1018]
def _check(statements: Sequence[Any], targets: Sequence[Any]) -> None:
    names: set[str] = set()
    for index, given in enumerate(statements):
        children = tuple(given.children) if isinstance(given, Expression) else ()
        truth = tuple(children[3].children) if len(children) == 4 and isinstance(children[3], Expression) else ()
        if (len(children) != 4 or str(children[0]) != ":" or not isinstance(children[1], Symbol)
                or len(truth) != 3 or str(truth[0]) != "STV" or not all(_unit(value) for value in truth[1:])):
            raise InvalidInputError(
                f"Statement {index} is not (: NAME CLAIM (STV S C)) with S and C in [0, 1]: {given}.",
                details={"index": index, "statement": str(given)},
            )
        name = str(children[1])
        if name in names:
            raise InvalidInputError(
                f"Statement {index} reuses the name {name}; a proof names its sources by statement name.",
                details={"index": index, "name": name},
            )
        names.add(name)
    for index, target in enumerate(targets):
        if not _ground(target):
            raise InvalidInputError(
                f"Target {index} holds a variable: {target}. A target is one claim, answered about itself.",
                details={"index": index, "target": str(target)},
            )


# am[implements a-hh-gp-callable-1018]
def _ground(atom: Any) -> bool:
    if isinstance(atom, Variable):
        return False
    return not isinstance(atom, Expression) or all(_ground(child) for child in atom.children)


# A truth value's strength or confidence: a finite number in [0, 1]. pymetta reads a long integer literal as a
# Python int, and finite_float answers None for one beyond the float range where float() would raise
# OverflowError, so _check refuses it as InvalidInputError and _belief as ProtocolError (a-ev-nr-finite-float-1018).
# am[implements a-hh-gp-callable-1018@f10634] am[implements a-ev-nr-finite-float-1018@6fcba4]
def _unit(value: Any) -> bool:
    number = finite_float(evaluator.plain_value(value))
    return number is not None and 0.0 <= number <= 1.0


# The grading answers (Graded ROWS): ROWS holds one row (TARGET ANSWERS) per target in order, and
# ANSWERS every (: PROOF TARGET (STV S C)) the chainer gave. ROWS and each ANSWERS must be
# expressions, the empty one () included. Anything else in their place is a malformed answer, never
# read as no answer, so only an empty collection means the chainer proved nothing about a target.
# Time: linear in the answers' size.
# am[implements a-hh-gp-callable-1018] am[implements a-hh-pc-port-1018] am[implements a-integrate-pln-result-refusal-1018]
def _answers(answer: Any, targets: Sequence[Any]) -> tuple[tuple[Belief, ...], ...]:
    rows = _collection(_children(answer, "Graded", 2)[1], "rows", answer)
    graded = [str(row.children[0]) if isinstance(row, Expression) and len(row.children) == 2 else None
              for row in rows]
    if graded != [str(target) for target in targets]:
        raise ProtocolError(
            "PeTTaChainer's grading must answer one row per target, in order.",
            details={"targets": [str(target) for target in targets], "answer": str(answer)},
        )
    return tuple(
        tuple(_belief(target, candidate) for candidate in _collection(row.children[1], f"answers about {target}", answer))
        for target, row in zip(targets, rows)
    )


# The children of a position the grading answers a collection in, which must be an expression.
# am[implements a-integrate-pln-result-refusal-1018]
def _collection(atom: Any, what: str, answer: Any) -> tuple[Any, ...]:
    if not isinstance(atom, Expression):
        raise ProtocolError(f"PeTTaChainer's grading answered {atom} where a collection of {what} was required.",
                            details={"collection": what, "answer": str(answer)})
    return tuple(atom.children)


# am[implements a-hh-gp-callable-1018] am[implements a-hh-pc-port-1018]
def _belief(target: Any, candidate: Any) -> Belief:
    _, _, claim, truth = _children(candidate, ":", 4)
    if str(claim) != str(target):
        raise ProtocolError(f"PeTTaChainer answered {candidate} for {target}.",
                            details={"target": str(target), "answer": str(candidate)})
    _, strength, confidence = _children(truth, "STV", 3)
    if not (_unit(strength) and _unit(confidence)):
        raise ProtocolError(f"PeTTaChainer answered a truth value outside [0, 1]: {candidate}.",
                            details={"target": str(target), "answer": str(candidate)})
    return Belief(float(evaluator.plain_value(strength)), float(evaluator.plain_value(confidence)), str(candidate))


# am[implements a-hh-pc-port-1018]
def _children(atom: Any, head: str, arity: int) -> tuple[Any, ...]:
    children: tuple[Any, ...] = tuple(atom.children) if isinstance(atom, Expression) else ()
    if len(children) != arity or str(children[0]) != head:
        raise ProtocolError(f"PeTTaChainer's grading answered {atom} where ({head} ...) was required.",
                            details={"head": head, "answer": str(atom)})
    return children

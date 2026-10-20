"""Purpose: hold a caller's bounds on a run and make engine calls under them, a MeTTa run or any
other bounded call such as a profile. Budgets are the caller's: a `RunBudget` holds one caller's
inference bound and a deadline on the monotonic clock, and every stage of that caller's run runs
under what is left of it and is charged what it spent; exhausting either bound raises
InferenceBudgetExceeded or ReviewTimeout naming the whole bound. A stopped evaluation keeps the
writes it already made unless it ran inside the engine's speculate() scope, which discards every
write of the call."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

from ..errors import GoalChainerError, InvalidInputError, MettaEngineError, safe_repr
from .numbers import finite_float

_Result = TypeVar("_Result")

# SWI-Prolog keeps a run's inference limit in an int64_t and refuses a larger one ('$inference_limit'/2:
# Cannot represent due to `int64_t'), and no run spends that many, so a larger bound reaches the
# engine as this one while the spend is still compared with the whole bound.
# am[implements a-rt-nr-repair-1018@72901e] am[rests-on c-rt-nr-engine-int64-limits-1018@5798a2]
ENGINE_INFERENCE_LIMIT = 2**63 - 1


# am[implements a-rel-deontic-run-1016@be58d5] am[implements a-rt-run-budget-1016@e046b0]
class BudgetExhausted(GoalChainerError):
    """A run reached a bound its caller set; whatever it was computing is discarded."""

    code = "budget_exhausted"


# am[implements a-rel-deontic-run-1016@be58d5] am[implements a-rt-run-budget-1016@e046b0]
class InferenceBudgetExceeded(BudgetExhausted):
    """The run spent `used` inferences, every stage charged to its RunBudget counted, against a
    budget of `budget`."""

    code = "inference_budget_exceeded"

    def __init__(self, budget: int, used: int) -> None:
        super().__init__(
            f"The run was stopped after {used} inferences, over its budget of {budget}.",
            details={"budget": budget, "used": used},
        )
        self.budget = budget
        self.used = used


# am[implements a-rel-deontic-run-1016@be58d5] am[implements a-rt-run-budget-1016@e046b0]
class ReviewTimeout(BudgetExhausted):
    """The run outlived its wall-clock budget, counted from when its RunBudget was made."""

    code = "review_timeout"

    def __init__(self, timeout_seconds: float) -> None:
        super().__init__(
            f"The run exceeded its {timeout_seconds:g} second budget.",
            details={"timeout_seconds": timeout_seconds},
        )
        self.timeout_seconds = timeout_seconds


# Go's context deadlines and EVM gas are the model: a stage gets what its caller has left and
# its spend comes off the caller's, so no stage of a run can be handed a fresh bound.
# am[implements a-rt-run-budget-1016@e046b0] am[implements a-rt-rr-safe-repr-1018@ec9700]
class RunBudget:
    """The bounds one caller sets for a run of any number of engine stages, and what the stages
    have spent of them.

    The deadline is fixed on the monotonic clock when the budget is made, and every stage is
    charged the inferences it used, so a later stage only ever gets what is left: a review whose
    deontic run took 40 of its 60 seconds and 700,000 of its 5,000,000 inferences gives its
    ranking stage 20 seconds and 4,300,000 inferences. `inference_budget` is a positive integer,
    or None for a run its caller bounds by wall time alone; `timeout_seconds` is always finite and
    positive. A budget belongs to one run, whose stages charge it one at a time: a stage running
    on an engine pool worker charges it while its caller waits for that stage.
    """

    __slots__ = ("_deadline", "_spent", "inference_budget", "timeout_seconds")

    def __init__(self, *, inference_budget: int | None, timeout_seconds: float) -> None:
        if inference_budget is not None and (
            isinstance(inference_budget, bool)
            or not isinstance(inference_budget, int)
            or inference_budget <= 0
        ):
            raise InvalidInputError(
                "inference_budget must be a positive integer, or None for no inference bound.",
                details={"inference_budget": safe_repr(inference_budget)},
            )
        # A timeout is refused only where no finite float holds it, an integer beyond the float
        # range included, which isfinite() raised OverflowError for.
        # am[implements a-rt-nr-repair-1018@72901e] am[rests-on c-rt-nr-probe-bfd71102-1018@029356]
        seconds = finite_float(timeout_seconds)
        if seconds is None or seconds <= 0:
            raise InvalidInputError(
                "timeout_seconds must be a finite positive number.",
                details={"timeout_seconds": safe_repr(timeout_seconds)},
            )
        self.inference_budget = inference_budget
        self.timeout_seconds = seconds
        self._deadline = time.monotonic() + self.timeout_seconds
        self._spent = 0

    @property
    def spent(self) -> int:
        """The inferences every stage so far was charged."""

        return self._spent

    def remaining(self) -> tuple[int | None, float]:
        """What the next stage may spend: inferences (None when unbounded) and seconds.

        Raises InferenceBudgetExceeded or ReviewTimeout, naming the whole bound, once either is
        used up, so an exhausted run never starts another stage.
        """

        if self.inference_budget is not None and self._spent >= self.inference_budget:
            raise InferenceBudgetExceeded(self.inference_budget, self._spent)
        seconds = self._deadline - time.monotonic()
        if seconds <= 0:
            raise ReviewTimeout(self.timeout_seconds)
        left = None if self.inference_budget is None else self.inference_budget - self._spent
        return left, seconds

    # One Lock.acquire or Condition.wait takes at most threading.TIMEOUT_MAX seconds and raises
    # OverflowError beyond it, while a positive finite timeout may lie further off, so a wait toward
    # the deadline is made of slices no longer than that and every timeout the budget admits is kept.
    # Time: one wait_once call per threading.TIMEOUT_MAX seconds waited, about 292 years on Linux.
    # am[implements a-rt-nr-repair-1018@72901e] am[rests-on c-rt-nr-waits-chunk-not-refuse-1018@7102fe]
    def wait(self, wait_once: Callable[[float], bool]) -> bool:
        """Call `wait_once(seconds)` until it answers True or this budget's deadline passes, each
        call given what is left, at most threading.TIMEOUT_MAX; answer whether it answered True.
        It raises nothing itself, so a caller holding queued work can still withdraw it."""

        while (left := self._deadline - time.monotonic()) > 0:
            if wait_once(min(left, threading.TIMEOUT_MAX)):
                return True
        return False

    # A count that fell was read on two Prolog engines, as a thread holding no engine of its own
    # reads it (c-rt-bare-thread-temporary-engines-1018); crediting it would hand the run inferences
    # it never had, so the stage fails closed instead.
    # am[implements a-rt-run-budget-1016@e046b0] am[implements a-rt-cc-rw-pool-1018]
    def charge(self, used: int) -> None:
        """Count a stage's inferences against the budget. The engine stages do this themselves.

        Raises MettaEngineError for a negative count, which no run spends, leaving the budget as
        it was."""

        if used < 0:
            raise MettaEngineError(
                "A stage's inference count fell while it ran, so it was read on more than one "
                "Prolog engine and cannot be charged.",
                details={"inferences": used, "spent": self._spent},
            )
        self._spent += used

    # The child copies the absolute deadline instead of rebuilding one from the seconds left, so
    # no delay between this call's clock read and the child's use can move it.
    # am[implements a-rt-rb-evaluator-api-1018@9374f4] am[rests-on c-rel-one-deadline-1016@75de2a]
    # am[implements a-integrate-runtime-deadline-preservation-1018@d52ba4]
    def deadline_only(self) -> RunBudget:
        """A budget with this one's deadline and timeout and no inference bound, for fixed startup
        work a request is charged no inferences for but its wall clock still covers: it stops at
        the request's own deadline and a stop names the request's whole timeout. Raises
        InferenceBudgetExceeded or ReviewTimeout, like remaining(), once this budget is used up,
        so an exhausted request is stopped even where its startup work is done."""

        self.remaining()
        child = RunBudget.__new__(RunBudget)
        child.inference_budget = None
        child.timeout_seconds = self.timeout_seconds
        child._deadline = self._deadline
        child._spent = 0
        return child


# Work that runs only under its caller's budget refuses anything else before it starts, so a
# missing budget is a typed error where the work is entered, never a fresh bound and never an
# AttributeError deep inside a run.
# am[implements a-rt-rb-one-budget-1018@550ffd] am[implements a-rt-rbs-session-budget-1018@8c3da2]
# am[implements a-rt-rr-safe-repr-1018@ec9700]
def caller_budget(budget: object, holder: str) -> RunBudget:
    """`budget` when it is a RunBudget; otherwise InvalidInputError saying `holder`, the work being
    entered, runs only under its caller's RunBudget, never unbounded."""

    if not isinstance(budget, RunBudget):
        raise InvalidInputError(
            f"{holder} runs only under its caller's RunBudget, never unbounded.",
            details={"budget": safe_repr(budget)},
        )
    return budget


# Time: one engine call, bounded by what is left of the budget, and two reads of SWI's counters.
# am[implements a-rt-run-budget-1016@e046b0] am[implements a-rt-pymetta-engine-1016@296784]
# am[rests-on c-rt-guard-overshoot-1016@271832] am[implements a-rt-spend-over-remaining-1016@70b7b8]
# am[implements a-integrate-pymetta-public-errors-1019@05202a] am[rests-on c-dg-public-errors-identical-1019@7375e3]
# am[implements a-dg-bounded-call-1019@a8caca] am[rests-on c-dg-match-cursor-uncounted-1019@458a46]
def bounded_call(
    engine: Any, call: Callable[[int | None, float], _Result], *, budget: RunBudget
) -> tuple[_Result, int]:
    """Make one engine call under what is left of `budget`, charge the inferences it spent, and
    answer its result with that spend. `call(inferences, seconds)` gets the two bounds to hand
    the engine, inferences None when the budget has none: run_bounded passes them to
    engine.run, a profile to Space.profile. Call it holding metta_engine or inside
    shared_evaluation work, where every call runs on one Prolog engine. The spend is what
    `engine.stats()` counts on this thread, so a call whose work runs in a cursor engine, as
    Space.match's does, is not charged whole and does not belong here.

    pymetta checks the inference bound only where it can interrupt the engine, not inside a
    function's first-call compilation, so a call it stops can have spent several times what it
    had left; that spend is real and is what gets charged. A call is charged on every way out, a
    failure included, and a stop by either bound is raised as InferenceBudgetExceeded or
    ReviewTimeout naming the whole bound. A call that returns having spent more than it had left
    is exhausted too: a guard interrupt caught inside the program shows only that way, and what
    such a call answers may come from a different path.

    The engine's two stops are pymetta's InferenceLimitError and TimeLimitError, imported from
    metta.errors, the error family's public module; the package root does not re-export them.
    """

    from metta.errors import InferenceLimitError, TimeLimitError  # noqa: PLC0415 (pymetta is imported only once an engine exists)

    inferences, seconds = budget.remaining()
    failure: Exception | None = None
    with engine.stats() as spent:
        try:
            limit = None if inferences is None else min(inferences, ENGINE_INFERENCE_LIMIT)
            result = call(limit, seconds)
        except Exception as error:  # charged below, then raised as the bound it hit or as itself
            failure = error
    budget.charge(spent.inferences)
    over = inferences is not None and spent.inferences > inferences
    if isinstance(failure, InferenceLimitError) or (failure is None and over):
        # The engine stops a run on inferences only when it was given an inference bound.
        raise InferenceBudgetExceeded(cast(int, budget.inference_budget), budget.spent) from failure
    if isinstance(failure, TimeLimitError):
        raise ReviewTimeout(budget.timeout_seconds) from failure
    if failure is not None:
        raise failure
    return result, spent.inferences


# Time: one engine run, bounded by what is left of the budget, and two reads of SWI's counters.
# am[implements a-rt-run-budget-1016@e046b0] am[implements a-rt-pymetta-engine-1016@296784]
# am[implements a-dg-bounded-call-1019@a8caca]
def run_bounded(
    engine: Any, source: str, *, budget: RunBudget, **holes: Any
) -> tuple[list[list[Any]], int]:
    """Run MeTTa source under what is left of `budget` as bounded_call makes a call, charge the
    inferences it spent, and answer its result groups with that spend, raising as bounded_call
    raises. Call it holding metta_engine or inside shared_evaluation work.

    `holes` are pymetta's `{name}` values: a str enters the program as one String atom, so a
    path or a name never needs escaping."""

    return bounded_call(
        engine,
        lambda inferences, seconds: engine.run(source, inferences=inferences, timeout=seconds, **holes),
        budget=budget,
    )

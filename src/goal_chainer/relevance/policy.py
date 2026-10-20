"""Purpose: evaluate the relevance review's MeTTa policy as one module group under each caller's RunBudget, and read its answers back as plain values.

The policy files under `policy/` own the review's reasoning (c-integrate-user-metta-policy-1016),
with the vocabulary every domain consumer shares, the justification kernel that labels the
review's readings, the fault-table reader every checking policy shares, and the deontic status
rule the incident decision and the scorer share. They load once per process, in order, into the
module group's own space, and each call runs one typed entry of the group through
`goal_chainer.runtime.evaluator`, beside other evaluations on the engine's pool, under the
budget its caller holds:

    prepare(budget)                                    load and compile the policy; answer its identity
    evaluate("gc-relevance-rank", atom, budget=budget)

Inputs are pymetta atoms built with `term` and `items` and passed to the engine as holes, so no
value is ever spliced into MeTTa text, and every value is a string, a number or a boolean
(policy/prelude.metta's data rule). An answer comes back through
`goal_chainer.runtime.evaluator.plain_value`: an expression as a tuple, a grounded atom as its
Python value, and a symbol as a pymetta atom, so a reader can always tell the policy's own None
from a domain name "None".

Preparation is charged to no review's inferences. Importing the policy and compiling it costs
about 4.4 million inferences in a fresh process (measured), a fixed per-process cost, so charged
to a budget it could fail a tight one only in the first review a process ran. It still runs
inside the deadline of the request that needs it: the module imports and the warm-ups that
compile the policy are stopped there. A failure the engine reports is a RelevanceError with the
review's codes; a call without a RunBudget, or of an entry that declares no type, is the
evaluator's InvalidInputError, a defect of the caller rather than an outcome of a review.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..domains.loader import FAULT_TABLES, VOCABULARY_FILE
from ..errors import DependencyUnavailableError, MettaEngineError, ModuleChanged, ProtocolError
from ..evidence_policy import POLICY_DIRECTORY as SHARED_POLICY_DIRECTORY
from ..planning.justification import KERNEL
from ..runtime import evaluator
from ..runtime.budget import BudgetExhausted, InferenceBudgetExceeded, ReviewTimeout, RunBudget
from ..runtime.evaluator import ModuleGroup, plain_value
from .errors import RelevanceError

POLICY_DIRECTORY = Path(__file__).resolve().parent / "policy"
# The status rule the ranking reads: the one file evidence_policy loads, so the engine imports it
# once.
# am[implements a-rel-status-module-1016@db512b]
STATUS_RULE = SHARED_POLICY_DIRECTORY / "goalchainer_deontic.metta"
# The modules the policy shares with other module groups: the shared vocabulary of bands and
# estimator classes, the justification kernel the evidence policy reads its labels from, the
# fault-table reader the receipt's and the assessment's tables are read by, and the status rule.
# am[implements a-rel-rr-shared-module-1018@13aee9] am[implements a-rel-rr-projection-1018@a05ccf]
# am[implements a-rel-nd-shared-table-reader-1018@24e3dd]
SHARED_MODULES: tuple[Path, ...] = (VOCABULARY_FILE, KERNEL, FAULT_TABLES, STATUS_RULE)
# Every .metta file the policy directory holds, in name order, then the shared modules. Load
# order does not change what the policy does: modules only define functions, which resolve when
# called, and the warm-ups run once all are loaded. The fixed order makes the group's identity
# one value per set of files, and a file added to the directory can never be left out of it. A
# review record lists each file by its path inside the goal_chainer package.
POLICY_FILES: tuple[Path, ...] = (*sorted(POLICY_DIRECTORY.glob("*.metta")), *SHARED_MODULES)
POLICY_MODULES: tuple[str, ...] = tuple(
    path.relative_to(POLICY_DIRECTORY.parents[1]).as_posix() for path in POLICY_FILES
)
# The policy's module group. It names the justification kernel's warm-up and then its own, one
# warm-up per owner of its modules, so each compiles what its owner's entries call.
# am[implements a-rel-mig-group-1018@28c337] am[implements a-rel-nd-section-warm-ups-1018@df1a66]
RELEVANCE_POLICY = ModuleGroup(
    "relevance-policy", POLICY_FILES, warm_ups=("gc-justification-warm-up", "gc-relevance-warm-up")
)


# A review record's review_policy digest is this identity, which names the bytes the engine
# imported for each module, so editing any policy file, the shared status rule included, changes
# every review fingerprint resting on it.
# Time: on a process's first call, one import per module and both warm-ups, about 4.4 million
# inferences; on every later call, one read of the clock.
# am[implements a-rel-metta-policy-1016@fdaa20] am[implements a-rel-mig-group-1018@28c337]
# am[implements a-rel-mig-digest-1018@c0f5c0]
def prepare(budget: RunBudget) -> str:
    """Load and compile every policy module once per process; answer the group's identity,
    'sha256:' and the SHA-256 over the group's name and each module's loader digest in order.

    A failed load or warm-up leaves the process unprepared, and the next call starts again: each
    module already imported answers the digest it was imported with, and a module that changed on
    disk since is an engine-failed error, since the engine keeps what it imported and only a fresh
    process loads the new bytes. The compilation is fixed per-process work, so its inferences are
    charged to nothing, but it runs inside `budget`'s deadline, and a budget already used up is a
    review-timeout or review-budget-exceeded even in a prepared process.
    """

    with _engine_failures():
        return evaluator.prepare(RELEVANCE_POLICY, budget=budget)


# Time: one prepare, then one engine run bounded by what is left of the budget.
# am[implements a-rel-metta-policy-1016@fdaa20] am[implements a-rt-run-budget-1016@e046b0]
# am[implements a-rel-mig-group-1018@28c337]
def evaluate(function: str, *arguments: Any, budget: RunBudget) -> Any:
    """The single answer of `(FUNCTION ARGUMENT ...)` as plain values.

    FUNCTION must declare its type in its policy file. The call is charged to `budget` and
    stopped by what is left of it, and any preparation the process still needs runs first inside
    its deadline.
    """

    with _engine_failures():
        answer = evaluator.evaluate(RELEVANCE_POLICY, function, *arguments, budget=budget)
    return plain_value(answer)


# The review's error codes for what the evaluator raises: a stop by the budget, a missing
# runtime, a module the engine refused or that changed since it was imported, and an answer that
# was not exactly one; anything else is a defect of the call and passes unchanged.
# am[implements a-rel-mig-group-1018@28c337] am[implements a-rel-loads-refuse-1016@654aad]
# am[rests-on c-rel-mig-caller-defects-invalid-input-1018@0f439f]
@contextmanager
def _engine_failures() -> Iterator[None]:
    try:
        yield
    except BudgetExhausted as error:
        raise stopped(error) from error
    except DependencyUnavailableError as error:
        raise RelevanceError("runtime-unavailable", str(error), details=dict(error.details)) from error
    except (ModuleChanged, MettaEngineError) as error:
        raise RelevanceError("engine-failed", str(error), details=dict(error.details)) from error
    except ProtocolError as error:
        raise RelevanceError("engine-output-invalid", str(error), details=dict(error.details)) from error


# am[implements a-rel-review-contract-1016@d0bea9] am[implements a-rt-run-budget-1016@e046b0]
def stopped(error: BudgetExhausted) -> RelevanceError:
    """The typed review error for a stage its budget stopped, naming the whole bound and spend."""

    if isinstance(error, InferenceBudgetExceeded):
        return RelevanceError(
            "review-budget-exceeded",
            f"the review was stopped after {error.used} inferences, over its budget of {error.budget}",
            details={"budget": error.budget, "used": error.used},
        )
    if isinstance(error, ReviewTimeout):
        return RelevanceError(
            "review-timeout",
            f"the review did not finish within {error.timeout_seconds} seconds",
            details={"timeout_seconds": error.timeout_seconds},
        )
    return RelevanceError("engine-failed", str(error), details={"code": error.code})


# am[implements a-rel-metta-policy-1016@fdaa20]
def term(head: str, *arguments: Any) -> Any:
    """`(HEAD ARGUMENT ...)` as a pymetta atom. HEAD is one of the policy's own constructors."""

    from metta import S  # noqa: PLC0415

    return S[head](*arguments)


# am[implements a-rel-metta-policy-1016@fdaa20]
def items(values: Any) -> Any:
    """A MeTTa list of the given values or atoms."""

    from metta import Expression  # noqa: PLC0415

    return Expression(*values)


# am[implements a-rel-metta-policy-1016@fdaa20]
def constant(name: str) -> Any:
    """One of the policy's nullary constructors, such as None, Wild or Forever."""

    from metta import S  # noqa: PLC0415

    return S[name]


# am[implements a-rel-metta-policy-1016@fdaa20]
def symbol(value: Any) -> str:
    """The name of a symbol in an answer; a string or anything else in that position is unreadable."""

    from metta import Symbol  # noqa: PLC0415

    if not isinstance(value, Symbol):
        raise ValueError(f"expected a symbol, got {value!r}")
    return str(value)


# am[implements a-rel-metta-policy-1016@fdaa20]
def is_nothing(value: Any) -> bool:
    """Whether an answer position holds the policy's None, never a string that reads None."""

    from metta import Symbol  # noqa: PLC0415

    return isinstance(value, Symbol) and str(value) == "None"


# am[implements a-rel-metta-policy-1016@fdaa20]
def text(value: Any) -> str:
    """A string in an answer; a symbol in that position is unreadable."""

    if not isinstance(value, str):
        raise ValueError(f"expected a string, got {value!r}")
    return value


# am[implements a-rel-metta-policy-1016@fdaa20]
def body(wrapped: Any, head: str) -> tuple:
    """The contents of `(HEAD CONTENTS)`."""

    if not isinstance(wrapped, tuple) or len(wrapped) != 2 or symbol(wrapped[0]) != head:
        raise ValueError(f"expected ({head} ...), got {wrapped!r}")
    contents = wrapped[1]
    if not isinstance(contents, tuple):
        raise ValueError(f"expected a list inside ({head} ...), got {contents!r}")
    return contents

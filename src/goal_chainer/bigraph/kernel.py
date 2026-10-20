"""Purpose: run the bigraph structural kernel, kernel.metta, through goal_chainer.runtime's evaluator: each
operation is one call of a typed one-answer entry of the bigraph module group, under the caller's
RunBudget and inside the group space's speculative scope, raising a typed error for a refused input, a
kernel error or an exhausted budget, never a partial answer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from goal_chainer.errors import InvalidInputError, ProtocolError
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.runtime.evaluator import ModuleGroup, evaluate

KERNEL = Path(__file__).resolve().with_name("kernel.metta")
# The kernel's own group. Its warm-up runs every entry once per process outside speculation, since an
# evaluator call compiles inside a speculative scope that discards what it compiled.
# am[implements a-brs-k-evaluator-1018@39680b] am[rests-on c-brs-k-evaluator-agreed-1018@e9d6d0]
# am[implements a-rel-nd-section-warm-ups-1018@df1a66]
GROUP = ModuleGroup("bigraph", (KERNEL,), warm_ups=("bg-warm-up",))


# am[implements a-brs-k-python-1018@10bb44] am[implements a-brs-k-evaluator-1018@39680b]
class BigraphFault(InvalidInputError):
    """A term, rule or composition the kernel refused, with every fault it found."""

    code = "bigraph_fault"

    def __init__(self, operation: str, faults: tuple[Any, ...]) -> None:
        super().__init__(
            f"The bigraph kernel refused {operation}: {', '.join(repr(f) for f in faults)}.",
            details={"operation": operation, "faults": tuple(repr(f) for f in faults)},
        )
        self.operation = operation
        self.faults = faults


# am[implements a-brs-k-python-1018@10bb44] am[implements a-brs-k-evaluator-1018@39680b]
class BigraphKernelError(ProtocolError):
    """An (Error ...) answer of the kernel, such as an application condition no clause decides."""

    code = "bigraph_kernel_error"

    def __init__(self, operation: str, error: Any) -> None:
        super().__init__(
            f"The bigraph kernel answered an error for {operation}: {error!r}.",
            details={"operation": operation, "error": repr(error)},
        )
        self.operation = operation
        self.error = error


# The one answer of ENTRY on ATOMS. An entry given a state and rules checks them first and answers
# (BgFaulty State FAULTS) or (BgFaulty (Rule NAME) FAULTS) instead of running on a faulty one, and apply
# answers (BgFaulty Occurrence FAULTS) for an occurrence the state does not have; each is raised here.
# Time: one engine run charged to the budget, after the group's preparation once per process.
# am[implements a-brs-k-evaluator-1018@39680b] am[implements a-brs-k-python-1018@10bb44]
def _call(entry: str, *atoms: Any, budget: RunBudget) -> Any:
    answer = evaluate(GROUP, entry, *atoms, budget=budget)
    if _headed(answer, "BgFaulty"):
        part = answer.children[1]
        named = {"State": "the state", "Occurrence": "the occurrence"}.get(repr(part))
        operation = named or (f"rule {part.children[1]!r}" if _headed(part, "Rule") else "a rule")
        raise BigraphFault(operation, tuple(answer.children[2].children))
    return answer


# Every answer an entry collected, none an (Error ...).
# am[implements a-brs-k-python-1018@10bb44]
def _answers(entry: str, *atoms: Any, budget: RunBudget) -> tuple[Any, ...]:
    answers = tuple(_call(entry, *atoms, budget=budget).children)
    for answer in answers:
        if _headed(answer, "Error"):
            raise BigraphKernelError(entry, answer)
    return answers


# am[implements a-brs-k-python-1018@10bb44]
def _headed(atom: Any, head: str) -> bool:
    from metta import Expression  # noqa: PLC0415 (a dependency only in-process callers load)

    return isinstance(atom, Expression) and len(atom.children) > 0 and str(atom.children[0]) == head


# am[implements a-brs-k-python-1018@10bb44]
def faults(signature: Any, term: Any, *, budget: RunBudget) -> tuple[Any, ...]:
    """Every well-formedness fault of TERM against SIGNATURE, () when it is well-formed."""

    return tuple(_call("bg-run-faults", signature, term, budget=budget).children)


# am[implements a-brs-k-python-1018@10bb44]
def rule_faults(signature: Any, rule: Any, *, budget: RunBudget) -> tuple[Any, ...]:
    """Every fault of RULE against SIGNATURE, () when the kernel can run it."""

    return tuple(_call("bg-run-rule-faults", signature, rule, budget=budget).children)


# am[implements a-brs-k-python-1018@10bb44]
def occurrences(signature: Any, rule: Any, state: Any, *, budget: RunBudget) -> tuple[Any, ...]:
    """Every occurrence of RULE in STATE whose conditions hold, one per embedding."""

    return _answers("bg-run-occurrences", signature, rule, state, budget=budget)


# am[implements a-brs-k-python-1018@10bb44] am[implements a-brs-k-checked-apply-1018@f3812e]
def apply(signature: Any, rule: Any, state: Any, occurrence: Any, *, budget: RunBudget) -> Any:
    """RULE applied at OCCURRENCE, which must be one of RULE's occurrences in STATE now: (Successor NAME
    OCC STATE') or (Refused NAME OCC REASON). An occurrence STATE does not have, such as one kept from an
    earlier state, raises BigraphFault; a condition no clause decides raises BigraphKernelError."""

    answer = _call("bg-run-apply", signature, rule, state, occurrence, budget=budget)
    if _headed(answer, "Error"):
        raise BigraphKernelError("bg-run-apply", answer)
    return answer


# am[implements a-brs-k-python-1018@10bb44]
def outcomes(signature: Any, rule: Any, state: Any, *, budget: RunBudget) -> tuple[Any, ...]:
    """Every outcome of RULE in STATE, one per occurrence, refusals included."""

    return _answers("bg-run-outcomes", signature, rule, state, budget=budget)


# am[implements a-brs-k-python-1018@10bb44]
def successors(signature: Any, rules: tuple[Any, ...], state: Any, *, budget: RunBudget) -> tuple[Any, ...]:
    """Every (Step NAME OCC STATE') of the highest priority class of RULES that has one."""

    return _answers("bg-run-successors", signature, _list(rules), state, budget=budget)


# am[implements a-brs-k-python-1018@10bb44]
def transitions(signature: Any, rules: tuple[Any, ...], state: Any, *, budget: RunBudget) -> tuple[Any, ...]:
    """The successors merged by isomorphism: (Transition STATE' ((Fired NAME COUNT OCC) ...)) each."""

    return _answers("bg-run-transitions", signature, _list(rules), state, budget=budget)


# am[implements a-brs-k-python-1018@10bb44]
def isomorphic(a: Any, b: Any, *, budget: RunBudget) -> bool:
    """Whether A and B are one state under the contract's isomorphism."""

    return _call("bg-run-iso", a, b, budget=budget).value is True


# am[implements a-brs-k-python-1018@10bb44]
def bucket(state: Any, *, budget: RunBudget) -> Any:
    """STATE's isomorphism-invariant bucket key."""

    return _call("bg-run-bucket", state, budget=budget)


# am[implements a-brs-k-python-1018@10bb44]
def decompose(occurrence: Any, state: Any, *, budget: RunBudget) -> Any:
    """OCCURRENCE's decomposition of the ground STATE: (Decomposition CONTEXT PARAMETER)."""

    return _call("bg-run-decompose", occurrence, state, budget=budget)


# A product the kernel refuses answers (Refused OPERATION FAULTS).
# am[implements a-brs-k-python-1018@10bb44]
def _algebra(entry: str, f: Any, g: Any, budget: RunBudget) -> Any:
    answer = _call(entry, f, g, budget=budget)
    if _headed(answer, "Refused"):
        raise BigraphFault(entry, tuple(answer.children[2].children))
    return answer


# am[implements a-brs-k-python-1018@10bb44]
def compose(f: Any, g: Any, *, budget: RunBudget) -> Any:
    """F o G, refused with BigraphFault when the interfaces differ or the supports overlap."""

    return _algebra("bg-run-compose", f, g, budget)


# am[implements a-brs-k-python-1018@10bb44]
def tensor(f: Any, g: Any, *, budget: RunBudget) -> Any:
    """F x G, refused when supports or names overlap."""

    return _algebra("bg-run-tensor", f, g, budget)


# am[implements a-brs-k-python-1018@10bb44]
def parallel(f: Any, g: Any, *, budget: RunBudget) -> Any:
    """F || G, outer names shared, refused when supports or inner names overlap."""

    return _algebra("bg-run-parallel", f, g, budget)


# am[implements a-brs-k-python-1018@10bb44]
def merge_product(f: Any, g: Any, *, budget: RunBudget) -> Any:
    """F | G: the parallel product with its roots merged into one."""

    return _algebra("bg-run-merge-product", f, g, budget)


# am[implements a-brs-k-python-1018@10bb44]
def _list(items: tuple[Any, ...]) -> Any:
    from metta import Expression  # noqa: PLC0415

    return Expression(*items)

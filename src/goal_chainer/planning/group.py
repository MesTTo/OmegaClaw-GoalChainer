"""Purpose: the planner's MeTTa module group, which goal_chainer.planning.procedures accepts libraries in
and goal_chainer.planning.projection plans and admits steps in, and the reading of the refusal both
answer when their input does not fit.

The group holds the shared vocabulary, whose reading-row rule turns readings into justification
rows; the procedure policy; the bigraph structural kernel; the justification kernel; the planning
projection's knowledge, compile, search and entry modules; and the feedback rules that turn the
journal's receipts into procedure tracks. It loads once per process into a space of
its own and is warmed by gc-pk-warm-up, which runs acceptance, a plan and an admission once outside
any speculation, so a caller's budget pays only for its own call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..bigraph.kernel import KERNEL as BIGRAPH_KERNEL
from ..domains.loader import VOCABULARY_FILE
from ..runtime.evaluator import ModuleGroup
from .justification import KERNEL as JUSTIFICATION_KERNEL

_PLANNING = Path(__file__).resolve().parent

# Load order defines nothing: the modules only define functions, which resolve when called, and the
# warm-up runs once every module is loaded.
# am[implements a-ev-pk-rb-group-1018@ba3846] am[implements a-ev-pk-python-api-1018@db9b94]
# am[implements a-ev-pk-feedback-1018@84fec1]
MODULES: tuple[Path, ...] = (
    VOCABULARY_FILE,
    _PLANNING.parent / "policy" / "goalchainer_procedure.metta",
    BIGRAPH_KERNEL,
    JUSTIFICATION_KERNEL,
    _PLANNING / "knowledge.metta",
    _PLANNING / "compile.metta",
    _PLANNING / "search.metta",
    _PLANNING / "projection.metta",
    _PLANNING / "feedback.metta",
)
# am[implements a-ev-pk-rb-group-1018@ba3846]
# am[implements a-rel-nd-section-warm-ups-1018@df1a66]
PLANNING = ModuleGroup("planning", MODULES, warm_ups=("gc-pk-warm-up",))


# Each problem of a (Refused (Problem KIND DETAIL) ...) answer as text a person reads, its kind and
# detail written as MeTTa writes them except that a string stands bare, so the procedure p and the
# signal nonesuch read (p nonesuch), as every refusal of the procedure policy always has.
# am[implements a-ev-pk-python-api-1018@db9b94]
def refused(answer: Any) -> tuple[str, ...] | None:
    """The problems a (Refused PROBLEM ...) answer names, or None for any other answer."""

    from metta import Expression  # noqa: PLC0415 (pymetta is imported only once an engine exists)

    if not (isinstance(answer, Expression) and answer.children and str(answer.children[0]) == "Refused"):
        return None
    return tuple(
        " ".join(_plain(part) for part in problem.children[1:])
        if isinstance(problem, Expression) and problem.children and str(problem.children[0]) == "Problem"
        else _plain(problem)
        for problem in answer.children[1:]
    )


# am[implements a-ev-pk-python-api-1018@db9b94]
def _plain(atom: Any) -> str:
    from metta import Expression, Grounded  # noqa: PLC0415

    if isinstance(atom, Expression):
        return "(" + " ".join(_plain(child) for child in atom.children) + ")"
    if isinstance(atom, Grounded) and isinstance(atom.value, str):
        return atom.value
    return str(atom)


__all__ = ["MODULES", "PLANNING", "refused"]

"""Purpose: evaluate GoalChainer's memory and deontic-status MeTTa policy as one module group under each caller's RunBudget, and read back each answer.

The policy files under `policy/` own the rules (c-integrate-user-metta-policy-1016). They load once
per process, in order, into the module group's own space, and each call runs one typed entry of
the group through goal_chainer.runtime.evaluator under the budget its caller holds, so a decision's
policy calls share its one deadline and inference allowance. Values cross as pymetta holes, never
as source text, so a caller's belief id or action name is one String atom whatever characters it
holds (c-ev-pymetta-term-transport). An answer comes back through `plain_value`: expressions as
tuples, grounded values as Python values, symbols as atoms.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .runtime import evaluator
from .runtime.budget import RunBudget
from .runtime.evaluator import ModuleGroup, plain_value

POLICY_DIRECTORY = Path(__file__).resolve().parent / "policy"
# am[implements a-ie-s5-incident-host-1018@53176a] am[implements a-ie-c5b-modules-1018]
POLICY_MODULES = (
    "goalchainer_memory.metta",
    "goalchainer_deontic.metta",
)
# am[implements a-rt-rb-migrate-evidence-1018@4fa74b]
EVIDENCE_POLICY = ModuleGroup("evidence-policy", tuple(POLICY_DIRECTORY / module for module in POLICY_MODULES))


# am[implements a-ev-mr-host@bb60d1] am[implements a-rt-rb-migrate-evidence-1018@4fa74b]
# am[implements a-ev-rb-pipeline-budget-1018@988a39] am[rests-on c-integrate-request-budget-required-1018@16dacf]
def evaluate(function: str, *arguments: Any, budget: RunBudget) -> Any:
    """The one answer of `(FUNCTION ARGUMENT ...)` in the evidence policy, as plain values.

    Each argument enters as a hole, e.g.
    evaluate("gc-memory-admit", Expression(*terms), Expression(*candidates), digest, budget=budget).
    The entry must declare its type in its policy file. Raises InvalidInputError for an untyped
    entry or another number of arguments, ProtocolError unless the call answers exactly once,
    InferenceBudgetExceeded or ReviewTimeout when `budget` runs out, and DependencyUnavailableError
    without pymetta.
    """

    return plain_value(evaluator.evaluate(EVIDENCE_POLICY, function, *arguments, budget=budget))


__all__ = ["EVIDENCE_POLICY", "POLICY_DIRECTORY", "POLICY_MODULES", "evaluate"]

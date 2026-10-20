"""Purpose: prove that exhausted request bounds stop both engine entry points before preparation."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from goal_chainer import deontic_engine, snars_engine
from goal_chainer.runtime import budget as budgets
from goal_chainer.snars_program import SnarsBatch


# The preparation sentinel fails even if a later budget check would refuse correctly.
# No engine is needed and the fake clock advances without sleeping.
# am[verifies a-rt-rbr-read-before-engine-1018@b0a647]
@pytest.mark.parametrize("stage", ["snars", "deontic"])
@pytest.mark.parametrize("bound", ["inferences", "deadline"])
def test_exhausted_bounds_stop_before_preparation(monkeypatch, stage: str, bound: str) -> None:
    clock = Mock(return_value=10.0)
    monkeypatch.setattr(budgets, "time", SimpleNamespace(monotonic=clock))
    budget = budgets.RunBudget(inference_budget=100, timeout_seconds=1.0)
    if bound == "inferences":
        budget.charge(100)
        refusal = budgets.InferenceBudgetExceeded
    else:
        clock.return_value = 11.0
        refusal = budgets.ReviewTimeout
    preparation = Mock(side_effect=AssertionError("exhausted request reached engine preparation"))
    if stage == "snars":
        monkeypatch.setattr(snars_engine, "_prepared_world", preparation)
        entry = snars_engine.run_snars_batch
        payload = SnarsBatch((), frozenset(), "(gc inspect-record)")
    else:
        monkeypatch.setattr(deontic_engine, "initialize_once", preparation)
        entry = deontic_engine.run_deontic_theory
        payload = "(given (ready))"

    with pytest.raises(refusal):
        entry(payload, budget=budget)

    preparation.assert_not_called()
    assert budget.spent == (100 if bound == "inferences" else 0)

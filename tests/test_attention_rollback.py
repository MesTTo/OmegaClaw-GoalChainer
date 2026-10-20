"""Purpose: verify that attention query state and native inference state vanish on every exit."""

import pytest

from goal_chainer.runtime.budget import InferenceBudgetExceeded, RunBudget
from goal_chainer.snars_engine import run_snars_batch
from goal_chainer.errors import MettaEngineError
from goal_chainer.snars_program import SnarsBatch, SnarsProgramBuilder, parse_statement

from test_attention_session import EDGE_AB, EDGE_BC, QUERY


# Observe every attention fact family and native stores affected by this two-edge query.
# am[verifies a-integrate-ecan-packaged-query-1017]
STATE = """(State
 (gc-attention-rows)
 (collapse (match &self (gc-attention-indexed $sid) $sid))
 (gc-attention-active?)
 (sn frontier)
 (collapse (match &self (sn stmt $sid $tree) (Statement $sid $tree)))
 (collapse (match &self (sn proof $sid $proof) (Proof $sid $proof)))
 (collapse (match &self (sn receipt $sid $source $hash) (Receipt $sid $source $hash)))
 (sn_tr_rs src "edge-0") (sn_tr_rs src "edge-1"))"""


# The stop has a charged limit; ordinary calls use the suite's existing wall allowance.
# am[verifies a-integrate-ecan-packaged-query-1017]
def _budget(limit=None):
    return RunBudget(inference_budget=limit, timeout_seconds=900)


# Successful derivation, a later exception and a charged interruption all return to the same base.
# The final rerun must still derive the identical witness; no stale queue or proof may answer it.
# am[verifies a-integrate-ecan-packaged-query-1017]
# am[rests-on c-integrate-query-state-observables-1017]
def test_attention_and_native_stores_rollback_after_every_exit():
    builder = SnarsProgramBuilder()
    codec = builder.codec
    effects = tuple(builder.belief_effect(
        parse_statement(statement), positive=8, negative=0, base_rate=None,
        source=f"edge-{index}", trust=1.0,
    ) for index, statement in enumerate((EDGE_AB, EDGE_BC)))
    operation = codec.expression("gc", codec.symbol("forward-query-record"), parse_statement(QUERY))
    batch = builder.batch(operation, effects=effects, includes={"attention"})
    observe = SnarsBatch((), frozenset({"attention"}), STATE)
    base = run_snars_batch(observe, budget=_budget()).output_lines
    assert base == ("(State () () False () () () () (0.0 0.0) (0.0 0.0))",)
    complete = run_snars_batch(batch, budget=_budget())
    assert "(status Witness)" in "\n".join(complete.output_lines)
    assert run_snars_batch(observe, budget=_budget()).output_lines == base
    failing = SnarsBatch(batch.facts, batch.includes,
                         f"(let $answer {batch.directive} (py-call (operator.truediv 1 0)))")
    with pytest.raises(MettaEngineError):
        run_snars_batch(failing, budget=_budget())
    assert run_snars_batch(observe, budget=_budget()).output_lines == base
    stopped = _budget(max(1, complete.inferences // 2))
    with pytest.raises(InferenceBudgetExceeded):
        run_snars_batch(batch, budget=stopped)
    assert stopped.spent >= stopped.inference_budget
    assert run_snars_batch(observe, budget=_budget()).output_lines == base
    assert run_snars_batch(batch, budget=_budget()).output_lines == complete.output_lines

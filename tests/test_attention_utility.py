"""Purpose: measure packaged query attention against native controls on the frozen distractor case."""

import json
from pathlib import Path

import pytest
from snars_differential import tree

from goal_chainer.sexpr.forms import top_level_forms
from goal_chainer.runtime.budget import InferenceBudgetExceeded, RunBudget
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.snars_engine import prepare_snars_world, run_snars_batch
from goal_chainer.snars_program import SnarsBatch, SnarsProgramBuilder, parse_statement


# Frozen before the packaged implementation: 4 target edges and a 9x9 distracting fan.
# This is a synthetic counterexample test, not a claim about general workloads or latency.
# am[rests-on c-integrate-compiled-controls-four-edge-1017]
# am[rests-on c-integrate-current-controls-budget-rule-1017]
# am[verifies a-integrate-ecan-current-query-controls-1017]
SEARCH_ALLOWANCE = 20_261_036


# am[verifies a-integrate-ecan-current-query-controls-1017]
def _statement(left, right):
    return f'(sn p so "is" ((arg s (sn c {json.dumps(left)})) (arg o (sn c {json.dumps(right)}))))'


# Native controls use the production search's exact support and stopping predicates.
# Loading this pure consumer definition is preparation, as loading the attention world is.
# am[verifies a-integrate-ecan-current-query-controls-1017]
@pytest.fixture(scope="module")
def native_consumer():
    builder = SnarsProgramBuilder()
    source = (Path(__file__).parents[1] / "src/goal_chainer/policy/goalchainer_attention_query.metta").read_text()
    forms = [form.text for form in top_level_forms(source) if not form.directive]
    definitions = [form for form in forms
                   if builder.codec.emit(builder.codec.parse(form)[1][0]) == "gc-attention-search!"]
    assert len(definitions) == 1
    world = prepare_snars_world()
    with metta_engine(None) as engine:
        space = engine.space(world.space)
        space.run(definitions[0])
    yield
    with metta_engine(None) as engine:
        engine.space(world.space).remove(engine.space(world.space).parse(definitions[0]))


# Time: O(E) program construction; native replay, graph work and inference are charged by the engine.
# am[verifies a-integrate-ecan-current-query-controls-1017]
def _batch(strategy, target_first):
    builder = SnarsProgramBuilder()
    codec = builder.codec
    target = [(f"target-{i}", f"target-{i+1}", 0.25) for i in range(4)]
    fan = [(f"other-in-{i}", "other-hub", 8.0) for i in range(9)]
    fan += [("other-hub", f"other-out-{i}", 8.0) for i in range(9)]
    edges = target + fan if target_first else fan + target
    effects = [builder.belief_effect(parse_statement(_statement(left, right)),
               positive=weight, negative=0.0, base_rate=None, source=f"edge-{index}", trust=1.0)
               for index, (left, right, weight) in enumerate(edges)]
    query = _statement("target-0", "target-4")
    if strategy == "attention":
        operation = codec.parse(f"(gc forward-query-record {query})")
        return builder.batch(operation, effects=effects, includes={"attention"})
    bindings = [f"($canonical (sn canon {query}))", "($sid (sn sid $canonical))"]
    if strategy == "native-query":
        bindings += ["($seed (sn seed-keys! $canonical 1.0))",
                     "($diffuse (sn diffuse! (sn config diffuse-budget)))"]
    if strategy == "zero":
        bindings += ["($graph (gc-attention-build!))", "($diffuse (gc-attention-diffuse!))",
                     "($active (add-atom &self (gc-attention-active)))"]
    if strategy != "native":
        bindings += ["($cleared (sn_cell_put sn-frontier ()))",
                     "($statements (msort (unique-atom (collapse (match &self (sn stmt $candidate $tree) $candidate)))))",
                     "($admitted (collapse (let $candidate (superpose $statements) "
                     "(if (sn supported? $candidate) (sn fr-touch! $candidate) (empty)))))"]
    operation = codec.parse(f"(let* ({' '.join(bindings)}) (gc-attention-search! $canonical $sid 0))")
    return builder.batch(operation, effects=effects, includes={"attention"} if strategy == "zero" else ())


# A native control reaching the witness at equal or less work defeats the claimed advantage here.
# Print every result as JSON before asserting; stopped runs remain part of the evidence.
# am[verifies a-integrate-ecan-current-query-controls-1017]
@pytest.mark.parametrize("target_first", [True, False], ids=["target-first", "target-last"])
def test_query_attention_finishes_the_frozen_case_with_less_charged_work(native_consumer, target_first):
    codec = SnarsProgramBuilder().codec
    native = _batch("native", target_first)
    replay = codec.parse(native.directive)
    replay[-1] = codec.parse(
        "(size-atom (collapse (match &self (sn receipt $sid $source $hash) ($sid $source $hash))))"
    )
    measured = run_snars_batch(SnarsBatch(native.facts, native.includes, codec.emit(replay)),
                              budget=RunBudget(inference_budget=None, timeout_seconds=900))
    assert measured.output_lines == ("22",)
    limit = measured.inferences + SEARCH_ALLOWANCE
    print(json.dumps({"target_first": target_first, "replay_inferences": measured.inferences,
                      "search_allowance": SEARCH_ALLOWANCE, "inference_budget": limit}), flush=True)
    results = {}
    for strategy in ("native", "native-rebuilt", "native-query", "zero", "attention"):
        budget = RunBudget(inference_budget=limit, timeout_seconds=900)
        batch = _batch(strategy, target_first)
        try:
            result = run_snars_batch(batch, budget=budget)
        except InferenceBudgetExceeded:
            status, steps = "inference-limit", None
        else:
            assert len(result.output_lines) == 1, result.output_lines
            record = tree(result.output_lines[0])
            if strategy == "attention":
                fields = {row[0]: row[1] for row in record[3][1:]}
                status, steps = fields["status"], int(fields["steps"])
            else:
                assert record[0] == "Search"
                status, steps = record[1], int(record[2])
        results[strategy] = {"status": status, "steps": steps, "inferences": budget.spent}
        print(json.dumps({"strategy": strategy, "target_first": target_first,
                          "inference_budget": limit, **results[strategy]}), flush=True)
    attention = results["attention"]
    assert attention["status"] == "Witness", results
    assert all(row["status"] != "Witness" or attention["inferences"] < row["inferences"]
               for name, row in results.items() if name != "attention"), results

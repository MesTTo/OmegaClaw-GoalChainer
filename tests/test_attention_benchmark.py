"""Purpose: verify that attention measurements preserve evidence, report bounded search honestly and
stop a query waiting for the engine at its own deadline."""

import random

import engine_meeting
import pytest

from benchmarks import attention
# am[verifies a-integrate-parent-artifacts-compose-1018@e3c6d7]
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.runtime.engine import metta_engine


# am[verifies a-integrate-cairn-verification-1018@4f7c66]
def test_seeded_priority_is_pure_and_independent_of_comparison_order():
    pairs = [(f"left-{i}", f"right-{j}") for i in range(4) for j in range(4)]
    first = {pair: attention.random_priority(17, *pair) for pair in pairs}
    random.Random(2).shuffle(pairs)
    assert {pair: attention.random_priority(17, *pair) for pair in pairs} == first
    assert len(set(first.values())) == len(pairs)
    assert {pair: attention.random_priority(18, *pair) for pair in pairs} != first


# A-B-C-D needs B-C although neither endpoint is named in the query A-D.
# am[verifies a-integrate-cairn-verification-1018@4f7c66]
def test_frozen_bridge_workload_keeps_internal_links_and_has_a_stable_identity():
    workload = attention.chain(3, 2)
    assert workload == attention.chain(3, 2)
    assert workload.digest == attention.chain(3, 2).digest
    assert ("chain-1", "chain-2") in workload.edges
    assert not set(("chain-1", "chain-2")) & set(workload.goal)
    assert workload.digest != attention.chain(3, 2, missing=True).digest
    assert len(workload.edges) == 7
    for length, distractors in ((0, 0), (1, -1)):
        with pytest.raises(ValueError):
            attention.chain(length, distractors)


# am[verifies a-integrate-cairn-verification-1018@4f7c66]
@pytest.fixture(scope="module")
def prepared():
    identity = attention.prepare()
    assert identity["modules"] and identity["runtime"]
    return identity


# am[verifies a-integrate-cairn-verification-1018@4f7c66]
@pytest.mark.parametrize("arm", attention.ARMS)
def test_existing_and_unreachable_queries_are_distinct_and_speculative(prepared, arm):
    answers = []
    for missing in (False, True):
        budget = RunBudget(inference_budget=None, timeout_seconds=180)
        result = attention.run(attention.chain(1, 0, missing=missing), arm, seed=17,
                               budget=budget)
        assert result["status"] == ("Incomplete" if missing else "Witness")
        assert result["steps"] == 0
        assert result["inferences"] == budget.spent > 0
        answers.append(result)
    assert len(answers[0]["receipts"]) == 1
    assert answers[1]["receipts"] == []
    with metta_engine(None) as engine:
        assert str(engine.space(attention.SPACE).run("!(gc-benchmark-evidence)")[0][0]) == "()"


# Successful schedules may return different proofs; every witness retains the same authored receipts.
# am[verifies a-integrate-cairn-verification-1018@4f7c66]
@pytest.mark.parametrize("arm", attention.ARMS)
def test_all_schedules_can_reach_a_three_edge_bridge(prepared, arm):
    result = attention.run(attention.chain(3, 0), arm, seed=17,
                           budget=RunBudget(inference_budget=None, timeout_seconds=180))
    assert result["status"] == "Witness", result
    assert result["steps"] > 0
    assert len(result["receipts"]) == 3
    assert result["answers"]


# am[verifies a-integrate-cairn-verification-1018@4f7c66]
@pytest.mark.parametrize("arm", attention.ARMS)
def test_exhaustion_is_reported_without_a_false_or_partial_answer(prepared, arm):
    budget = RunBudget(inference_budget=1, timeout_seconds=180)
    stopped = attention.run(attention.chain(3, 0), arm, seed=17, budget=budget)
    assert stopped["status"] == "InferenceBudgetExceeded"
    assert stopped["inferences"] == budget.spent >= 1
    assert stopped["answers"] is None and stopped["steps"] is None
    with metta_engine(None) as engine:
        assert str(engine.space(attention.SPACE).run("!(gc-benchmark-evidence)")[0][0]) == "()"


# am[verifies a-integrate-cairn-verification-1018@4f7c66]
def test_repeated_seed_replays_the_same_random_schedule(prepared):
    results = [attention.run(attention.chain(2, 1), "random", seed=23,
                             budget=RunBudget(inference_budget=None, timeout_seconds=180))
               for _ in range(2)]
    for result in results:
        result.pop("seconds")
        result.pop("inferences")
    assert results[0] == results[1]


# A query waiting for the engine while a load holds it alone stops at its whole-query deadline: it
# reports ReviewTimeout, with no answer and nothing charged, while the load still holds the engine
# rather than once the load lets go, and the next query answers.
# am[verifies a-integrate-benchmark-hold-budget-1018@1bd14c]
def test_a_query_waiting_for_a_load_stops_at_its_deadline(prepared):
    budget = engine_meeting.short_budget()
    stopped = {}

    def query():
        stopped.update(attention.run(attention.chain(1, 0), "native", seed=17, budget=budget))

    assert engine_meeting.while_held_alone(query)
    assert stopped["status"] == "ReviewTimeout"
    assert stopped["answers"] is None and stopped["steps"] is None
    assert stopped["inferences"] == budget.spent == 0
    answered = attention.run(attention.chain(1, 0), "native", seed=17,
                             budget=RunBudget(inference_budget=None, timeout_seconds=180))
    assert answered["status"] == "Witness"

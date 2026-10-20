"""Purpose: verify the in-process SNARS executor on the real pymetta engine: one world per set of
optional features, each compiled once and blind to the modules it did not load; every batch
leaving its world as it found it, whether it answered, raised or was stopped by its budget; and the
world's identity naming what was compiled."""

from __future__ import annotations

import pytest
from snars_differential import records

from goal_chainer.runtime.budget import InferenceBudgetExceeded, RunBudget
from goal_chainer.snars_engine import (
    compiled_worlds,
    prepare_snars_world,
    run_snars_batch,
    snars_identity,
)
from goal_chainer.errors import MettaEngineError
from goal_chainer.snars_program import (
    SnarsBatch,
    SnarsProgramBuilder,
    parse_statement,
    world_modules,
)
from reading_support import INCIDENT, incident_reader

BUILDER = SnarsProgramBuilder()
CODEC = BUILDER.codec
STATEMENT = parse_statement('(sn p so "is" ((arg s (sn c "alpha")) (arg o (sn c "beta"))))')
INSPECT = CODEC.expression("gc", CODEC.symbol("inspect-record"))


# A budget no batch here comes near: compiling a world takes about 20 s.
# am[verifies a-rt-snars-batch-speculative-1017@451056]
def _budget() -> RunBudget:
    return RunBudget(inference_budget=None, timeout_seconds=900)


# The statements an inspect record lists, the part of SNARS's state a belief changes.
# am[verifies a-rt-snars-batch-speculative-1017@451056]
def _statements(lines) -> str:
    (record,) = records("\n".join(lines))
    parsed = CODEC.parse(record)
    inspection = parsed[3]
    state = next(part for part in inspection[1:] if CODEC.emit(part[0]) == "state")
    return CODEC.emit(next(part for part in state[1][1:] if CODEC.emit(part[0]) == "statements"))


# A batch that believes the statement before it inspects, so its record shows the belief.
# am[verifies a-rt-snars-batch-speculative-1017@451056]
def _believing(includes=frozenset()) -> SnarsBatch:
    effect = BUILDER.belief_effect(STATEMENT, positive=2.0, negative=1.0, base_rate=0.5, source="test", trust=1.0)
    return _builder(includes).batch(INSPECT, effects=(effect,), includes=includes)


# The builder of a batch with these features: the policy reads its batch's declaration rows, so a
# policy batch comes from a builder holding the incident reader, and any other from the readerless one.
# am[verifies a-dr-sr-snars-batch-declaration-1018@5c965d]
def _builder(includes) -> SnarsProgramBuilder:
    return SnarsProgramBuilder(incident_reader()) if "policy" in includes else BUILDER


# am[verifies a-rt-snars-worlds-by-includes-1017@54c05f]
def test_each_feature_set_compiles_one_world_that_names_what_it_compiled() -> None:
    plain = prepare_snars_world((), budget=_budget())
    policy = prepare_snars_world({"policy"}, budget=_budget())

    assert (plain.space, policy.space) == ("&goalchainer-snars", "&goalchainer-snars-policy")
    assert (plain.includes, policy.includes) == ((), ("policy",))
    assert [name for name, _ in policy.modules] == [path.name for path in world_modules(frozenset({"policy"}))]
    assert plain.snars_identity == policy.snars_identity == snars_identity()
    assert plain.runtime.startswith("pymetta ") and plain.runtime_digest == policy.runtime_digest
    assert prepare_snars_world({"policy"}) is policy
    assert {world.space for world in compiled_worlds()} >= {plain.space, policy.space}


# The protocol's own functions reduce the policy's where it is loaded, so a world that never loaded
# the policy answers nothing for a call to one of its functions.
# am[verifies a-rt-snars-worlds-by-includes-1017@54c05f] am[verifies c-rt-preloaded-definitions-reach-other-batches-v2-1017@f05590]
# am[verifies a-ie-s7-metta-1018@0ca8fe]
def test_a_world_without_the_policy_never_sees_its_functions() -> None:
    call = CODEC.expression("gc", CODEC.symbol("has-property"), CODEC.string("x"), CODEC.string("acceptable"))
    plain = SnarsBatch((), frozenset(), CODEC.emit(call))
    policy = SnarsBatch((), frozenset({"policy"}), CODEC.emit(call), INCIDENT)

    answered = [run_snars_batch(batch, budget=_budget()).output_lines for batch in (plain, policy)]

    assert answered[0] == ()
    assert answered[1] == (CODEC.emit(parse_statement(
        '(sh (tag P d so ()) "has-property" (args ((arg s (sh-atom (tag C c NoRoles ()) "x")) '
        '(arg o (sh-atom (tag C c NoRoles ()) "acceptable")))))'
    )),)


# A belief one batch authors is gone for the next, in every world, whatever ran before.
# am[verifies a-rt-snars-batch-speculative-1017@451056]
@pytest.mark.parametrize("includes", [frozenset(), frozenset({"policy"})])
def test_a_batch_leaves_its_world_as_it_found_it(includes) -> None:
    empty = _statements(run_snars_batch(_builder(includes).batch(INSPECT, includes=includes), budget=_budget()).output_lines)

    believed = _statements(run_snars_batch(_believing(includes), budget=_budget()).output_lines)
    after = _statements(run_snars_batch(_builder(includes).batch(INSPECT, includes=includes), budget=_budget()).output_lines)

    assert '"alpha"' in believed and '"alpha"' not in empty
    assert after == empty


# A stopped batch is charged what it spent and raises the whole bound; a failing one raises the
# engine's error; neither leaves its belief behind.
# am[verifies a-rt-snars-batch-speculative-1017@451056]
def test_a_stopped_or_failing_batch_leaves_nothing_behind() -> None:
    empty = _statements(run_snars_batch(BUILDER.batch(INSPECT), budget=_budget()).output_lines)
    budget = RunBudget(inference_budget=1000, timeout_seconds=900)

    with pytest.raises(InferenceBudgetExceeded):
        run_snars_batch(_believing(), budget=budget)
    believing = _believing()
    failing = SnarsBatch((), frozenset(), f"(let* (($x {believing.directive}) ($y (py-call (operator.truediv 1 0)))) $x)")
    with pytest.raises(MettaEngineError):
        run_snars_batch(failing, budget=_budget())

    assert budget.spent >= 1000
    assert _statements(run_snars_batch(BUILDER.batch(INSPECT), budget=_budget()).output_lines) == empty

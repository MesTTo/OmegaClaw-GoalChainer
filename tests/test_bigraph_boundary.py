"""Purpose: tests of the bigraph kernel's Python boundary: every call is charged to the caller's one
RunBudget and an exhausted budget raises its typed error with no partial answer; a refused input raises
BigraphFault; kernel terms survive a text round trip; calls from several threads give one answer; the
kernel's module group prepares with a warm-up answering True; the engine memoizes none of the kernel's
functions; and the kernel writes nothing into its group's space."""

from __future__ import annotations

import threading

import pytest
from metta import parse

import bigraph_oracle as o
from goal_chainer.bigraph import kernel
from goal_chainer.runtime.budget import InferenceBudgetExceeded, ReviewTimeout, RunBudget
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.evaluator import plain_value, prepare

SIG = parse(o.signature_text(o.SIGNATURE))


# am[verifies a-brs-k-python-1018@10bb44]
def text(atom) -> str:
    return " ".join(repr(atom).split())


# A growing workload: a box with N tokens and a rule copying everything under it, so the successors of
# the bigger states cost more than a small inference budget allows.
# am[verifies a-brs-k-python-1018@10bb44]
def boxes(n: int):
    nodes = [("(new w b)", "A")] + [(f"(new w {i})", "T") for i in range(n)]
    place = [("(new w b)", ("root", 0))] + [(f"(new w {i})", "(new w b)") for i in range(n)]
    return parse(o.term(o.Big(0, (), 1, (), dict(nodes), dict(place))))


TAKE = parse(o.rule_text(o.Rule(
    "take",
    o.Big(1, (), 1, (), {"X": "A", "Y": "T"}, {"X": ("root", 0), "Y": "X", ("site", 0): "X"}),
    o.Big(2, (), 1, (), {"X": "A", "Z": "A"}, {"X": ("root", 0), ("site", 0): "X", "Z": ("root", 0), ("site", 1): "Z"}),
    {0: 0, 1: 0},
)))


# A warm call's raw count moves by a few percent with the engine's compilation history, so the tight
# budget is half of one warm call rather than one inference under it.
# am[verifies a-brs-k-python-1018@10bb44] am[verifies a-integrate-brs-structural-kernel-1018@dc4d19]
# am[rests-on c-rt-plain-warm-counts-drift-1016@484ac8]
def test_one_budget_is_charged_across_calls_and_exhaustion_raises_without_an_answer():
    roomy = RunBudget(inference_budget=None, timeout_seconds=600)
    first = kernel.successors(SIG, (TAKE,), boxes(3), budget=roomy)
    assert len(first) == 3 and roomy.spent > 0
    spent = roomy.spent
    kernel.successors(SIG, (TAKE,), boxes(3), budget=roomy)
    assert roomy.spent > spent, "a second call is charged to the same budget"
    tight = RunBudget(inference_budget=(roomy.spent - spent) // 2, timeout_seconds=600)
    with pytest.raises(InferenceBudgetExceeded):
        kernel.successors(SIG, (TAKE,), boxes(3), budget=tight)
    with pytest.raises(InferenceBudgetExceeded):
        kernel.successors(SIG, (TAKE,), boxes(3), budget=tight)  # an exhausted budget starts no stage


# am[verifies a-brs-k-python-1018@10bb44]
def test_a_deadline_raises_review_timeout():
    expired = RunBudget(inference_budget=None, timeout_seconds=1e-9)
    with pytest.raises(ReviewTimeout):
        kernel.successors(SIG, (TAKE,), boxes(6), budget=expired)


# am[verifies a-brs-k-python-1018@10bb44]
def test_an_ill_formed_state_or_rule_is_refused_with_every_fault():
    budget = RunBudget(inference_budget=None, timeout_seconds=600)
    broken = parse("(Bigraph (Inner 0 ()) (Outer 1 ()) (Nodes (N a A) (N a T)) (Place (In a (Root 0))) (Link))")
    with pytest.raises(kernel.BigraphFault) as refused:
        kernel.successors(SIG, (TAKE,), broken, budget=budget)
    assert "(DuplicateNode a)" in refused.value.details["faults"]
    not_solid = parse(o.rule_text(o.Rule("idle", o.Big(0, (), 2, (), {"X": "A"}, {"X": ("root", 0)}),
                                         o.Big(0, (), 2, (), {"X": "A"}, {"X": ("root", 0)}), {})))
    with pytest.raises(kernel.BigraphFault) as refused:
        kernel.occurrences(SIG, not_solid, boxes(1), budget=budget)
    assert any("IdleRoot" in f for f in refused.value.details["faults"])


# am[verifies a-brs-k-python-1018@10bb44]
def test_kernel_terms_survive_a_text_round_trip():
    budget = RunBudget(inference_budget=None, timeout_seconds=600)
    for step in kernel.successors(SIG, (TAKE,), boxes(2), budget=budget):
        for part in step.children[2:]:
            assert parse(repr(part)) == part


# am[verifies a-brs-k-python-1018@10bb44]
def test_threads_share_the_engine_and_get_one_answer():
    expected = [text(s) for s in kernel.successors(SIG, (TAKE,), boxes(3), budget=RunBudget(inference_budget=None, timeout_seconds=600))]
    results: list[list[str]] = []
    errors: list[BaseException] = []

    # am[verifies a-brs-k-python-1018@10bb44]
    def work() -> None:
        try:
            got = kernel.successors(SIG, (TAKE,), boxes(3), budget=RunBudget(inference_budget=None, timeout_seconds=600))
            results.append([text(s) for s in got])
        except BaseException as error:  # reported below
            errors.append(error)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and results == [expected] * 4


# am[verifies a-brs-k-evaluator-1018@39680b]
def test_the_group_prepares_with_a_warm_up_that_answers_true():
    identity = prepare(kernel.GROUP, budget=RunBudget(inference_budget=None, timeout_seconds=600))
    assert identity.startswith("sha256:")
    with metta_engine(None) as engine:
        answers = engine.space(kernel.GROUP.space).run("!(bg-warm-up)")
    assert [[plain_value(a) for a in answered] for answered in answers] == [[True]]


# pymetta memoizes a recursive group that one equation body calls twice and keys each call by its
# arguments, which made the tree builder quadratic in its rows; a memoized function's compiled clauses
# call cache_call.
# am[verifies a-brs-k-no-auto-memo-1018@69c76e] am[rests-on c-brs-k-auto-memo-1018@9c39b3]
def test_the_engine_memoizes_no_kernel_function():
    prepare(kernel.GROUP, budget=RunBudget(inference_budget=None, timeout_seconds=600))
    with metta_engine(None) as engine:
        space = engine.space(kernel.GROUP.space)
        names = {text(atom.children[1].children[0]) for atom in space.atoms()
                 if text(atom.children[0]) == "=" and atom.children[1].children}
        memoized = sorted(name for name in names if "cache_call" in space.fn[name].compiled)
    assert {"bg--build", "bg--tree-row", "bg-iso", "bg-warm-up"} <= names
    assert memoized == []


# am[verifies a-brs-k-python-1018@10bb44] am[verifies a-brs-k-evaluator-1018@39680b]
def test_the_kernel_writes_nothing_into_its_groups_space():
    budget = RunBudget(inference_budget=None, timeout_seconds=600)
    kernel.successors(SIG, (TAKE,), boxes(2), budget=budget)  # prepares the group
    with metta_engine(None) as engine:
        before = len(engine.space(kernel.GROUP.space))
    kernel.successors(SIG, (TAKE,), boxes(3), budget=budget)
    kernel.transitions(SIG, (TAKE,), boxes(3), budget=budget)
    with metta_engine(None) as engine:
        assert len(engine.space(kernel.GROUP.space)) == before

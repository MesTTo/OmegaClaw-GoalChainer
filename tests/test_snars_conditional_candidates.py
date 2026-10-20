"""Purpose: verify that SNARS enumerates both conditional rules' candidates, modus ponens on an
antecedent and abductive modus ponens on a consequent: the frontier admits each rule's pair of a
supported premise and its edge whichever of the premise, the other end and the edge arrives last,
never the pair of an end that is only interned, for binary and tuple premises alike; the derive!
sweep fires both and never fires an interned end back into the premise; a concept spelling a
referenced sid is never paired, a conclusion never feeds back through the edge it came by, every
firing grafts what direct derivation grafts."""

from __future__ import annotations

from functools import cache
from itertools import product

import pytest
from snars_differential import tree

from goal_chainer.runtime.budget import RunBudget
from goal_chainer.snars_engine import run_snars_batch
from goal_chainer.snars_program import SnarsBatch

# Each arity's (antecedent, consequent), no label shared, so no other rule pairs them.
STATEMENTS = {
    "binary": ('(sn p so "is" ((arg s (sn c "alpha")) (arg o (sn c "beta"))))',
               '(sn p so "is" ((arg s (sn c "gamma")) (arg o (sn c "delta"))))'),
    "tuple": ('(sn p sor "gives" ((arg s (sn c "ann")) (arg o (sn c "book")) (arg r (sn c "bob"))))',
              '(sn p sor "takes" ((arg s (sn c "cat")) (arg o (sn c "dish")) (arg r (sn c "dan"))))'),
}
# Each rule's premise variable, the end it grafts into and its proof head: modus ponens reads the
# antecedent $a into the consequent $b, abductive modus ponens the consequent $b into $a.
DIRECTIONS = {"modus ponens": ("$a", "$b", "mp"), "abduction": ("$b", "$a", "mpa")}
EDGE = ('($e (believe! (sh (tag P d so ()) "==>" (args ((arg s (sn-ref $a)) (arg o (sn-ref $b))))) '
        '((source "conditional") (trust 1.0) (domain conditional))))')


# Binding steps over one statement: believed, interned without evidence as conditional extraction
# interns an edge's clauses, or only named by its sid; `later` binds a step under a fresh name.
# am[verifies a-rt-conditional-enumeration-commit-1017@9831fa]
def _step(kind: str, var: str, statement: str, later: bool = False) -> str:
    form = {
        "believe": f'(believe! {statement} ((source "{var[1:]}") (trust 1.0)))',
        "intern": f'(sn intern-ref! {statement} "conditional-test")',
        "sid": f"(sn sid (sn pl-canon (sn peel {statement})))",
    }[kind]
    return f"(${var[1:]}-later {form})" if later else f"({var} {form})"


# Each order binds both ends before the edge, which needs their sids, and leaves the premise
# believed and the other end interned without evidence, as conditional extraction interns an
# edge's clauses, so only the order of arrival differs.
ORDERS = {
    "the premise before its edge": lambda p, t: [("believe", p), ("intern", t), "edge"],
    "the edge before its premise": lambda p, t: [("sid", p), ("intern", t), "edge", ("believe", p, True)],
    "the premise interned before its edge and believed after":
        lambda p, t: [("intern", p), ("intern", t), "edge", ("believe", p, True)],
    "the other end after the edge": lambda p, t: [("believe", p), ("sid", t), "edge", ("intern", t, True)],
}


# The bindings a step list makes for one direction and arity.
# am[verifies a-rt-conditional-enumeration-commit-1017@9831fa]
def _bindings(steps, direction: str, arity: str) -> str:
    premise, target, _ = DIRECTIONS[direction]
    trees = dict(zip(("$a", "$b"), STATEMENTS[arity]))
    return " ".join(EDGE if step == "edge" else _step(step[0], step[1], trees[step[1]], *step[2:])
                    for step in steps(premise, target))


# A frontier case: what the frontier holds once everything has arrived, what one step proves, the
# end it grafts into, and the premise's proofs once the frontier has been drained.
# am[verifies a-rt-conditional-enumeration-commit-1017@9831fa]
def _frontier_program(order: str, direction: str, arity: str) -> str:
    premise, target, _ = DIRECTIONS[direction]
    return (f"(let* ({_bindings(ORDERS[order], direction, arity)} ($frontier (sn frontier)) "
            f"($step (collapse (sn step!))) ($proofs (collapse (match &self (sn proof {target} $x) $x))) "
            f"($evidence (sn evidence {target})) ($drained (sn focus! 8)) "
            f"($feedback (collapse (match &self (sn proof {premise} $x) $x)))) "
            f"(conditional-case {premise} {target} $e $frontier $step $proofs $evidence $feedback))")


# The same premises fired directly instead of through the frontier.
# am[verifies a-rt-conditional-enumeration-commit-1017@9831fa]
def _direct_program(direction: str, arity: str) -> str:
    premise, target, _ = DIRECTIONS[direction]
    return (f"(let* ({_bindings(ORDERS['the premise before its edge'], direction, arity)} "
            f"($step (collapse (sn derive-pair! {premise} $e))) "
            f"($proofs (collapse (match &self (sn proof {target} $x) $x))) ($evidence (sn evidence {target}))) "
            f"(conditional-case {premise} {target} $e () $step $proofs $evidence ()))")


# Two sweeps over the premise believed and the other end interned without evidence before the edge:
# the first fires the rule; the second finds nothing more.
# am[verifies a-rt-derive-sweep-conditional-partners-1017@4b66c3]
def _sweep_program(direction: str, arity: str) -> str:
    premise, target, _ = DIRECTIONS[direction]
    return (f"(let* ({_bindings(ORDERS['the premise before its edge'], direction, arity)} ($cycles (sn cycles 2)) "
            f"($proofs (collapse (match &self (sn proof {target} $x) $x))) ($evidence (sn evidence {target})) "
            f"($feedback (collapse (match &self (sn proof {premise} $x) $x)))) "
            f"(conditional-sweep {premise} {target} $e $proofs $evidence $feedback))")


# An edge-shaped statement with one typed reference and, on the other side, an ordinary concept
# whose label is the referenced sid. Believed, the label becomes a string; interned raw it keeps
# the sid's symbol and shares its key. Both ends are believed after it, the edge already there,
# and it is touched itself; then the rows under each end's key, the frontier and what direct
# derivation fires on each end with it.
SPELLINGS = {
    "antecedent": '(sh (tag P d so ()) "==>" (args ((arg s (sh-atom (tag C c NoRoles ()) $a)) (arg o (sn-ref $b)))))',
    "consequent": '(sh (tag P d so ()) "==>" (args ((arg s (sn-ref $a)) (arg o (sh-atom (tag C c NoRoles ()) $b)))))',
}
INTRODUCTIONS = {
    "believed": lambda spelling: f'($c (believe! {spelling} ((source "spelling") (trust 1.0) (domain conditional))))',
    "interned raw": lambda spelling: f"($c (sn sid {spelling})) ($raw (sn intern! $c {spelling} instance aleatory))",
}


# am[verifies a-rt-conditional-enumeration-commit-1017@9831fa]
def _spelling_program(side: str, introduction: str) -> str:
    antecedent, consequent = STATEMENTS["binary"]
    return (f"(let* ({_step('sid', '$a', antecedent)} {_step('sid', '$b', consequent)} {EDGE} "
            f"{INTRODUCTIONS[introduction](SPELLINGS[side])} {_step('believe', '$a', antecedent, True)} "
            f"{_step('believe', '$b', consequent, True)} ($touched (sn fr-touch! $c)) "
            "($antecedent-rows (collapse (match &self (sn sub $a $x) $x))) "
            "($consequent-rows (collapse (match &self (sn obj $b $x) $x))) ($frontier (sn frontier)) "
            "($fired (collapse (superpose ((sn derive-pair! $a $c) (sn derive-pair! $b $c)))))) "
            "(conditional-spelling $a $b $e $c $antecedent-rows $consequent-rows $frontier $fired))")


CASES = list(product(ORDERS, DIRECTIONS, STATEMENTS))
PAIRS = list(product(DIRECTIONS, STATEMENTS))
PROGRAMS = {
    **{f"frontier: {o}, {d}, {a}": _frontier_program(o, d, a) for o, d, a in CASES},
    **{f"direct: {d}, {a}": _direct_program(d, a) for d, a in PAIRS},
    **{f"sweep: {d}, {a}": _sweep_program(d, a) for d, a in PAIRS},
    **{f"spelling: {s}, {i}": _spelling_program(s, i) for s, i in product(SPELLINGS, INTRODUCTIONS)},
}


# The batch's one result line.
# am[verifies a-rt-conditional-enumeration-commit-1017@9831fa]
def _result(lines) -> str:
    found = [line for line in lines if line.startswith("(conditional-")]
    assert len(found) == 1, lines
    return found[0]


# A program's result line from the in-process engine, run once per test process.
# am[verifies a-rt-conditional-enumeration-commit-1017@9831fa]
@cache
def _in_process(name: str) -> str:
    batch = SnarsBatch((), frozenset(), PROGRAMS[name])
    return _result(run_snars_batch(batch, budget=RunBudget(inference_budget=None, timeout_seconds=900)).output_lines)


# am[verifies a-rt-conditional-enumeration-commit-1017@9831fa]
def _case(name: str) -> list:
    return tree(_in_process(name))


# The (first premise, second premise) pairs a frontier holds, from its (Fr value tick s1 s2) items.
# am[verifies a-rt-conditional-enumeration-commit-1017@9831fa]
def _pairs(frontier) -> set[tuple[str, str]]:
    assert all(item[0] == "Fr" and len(item) == 5 for item in frontier), frontier
    return {(item[3], item[4]) for item in frontier}


# The frontier holds the premise's pair alone: the other end has neither a receipt nor a proof, so
# fr-push! refuses its pair. A step pops the premise's pair, proving the rule into the other end.
# Before 61877b2 no conditional pair was admitted at all, and before this commit no abductive one.
# am[verifies a-rt-fr-admit-abductive-mp-1017@1889cf] am[verifies a-rt-conditional-enumeration-commit-1017@9831fa]
# am[rests-on c-rt-support-is-receipt-or-proof-1017@6c065e]
@pytest.mark.parametrize("order, direction, arity", CASES)
def test_the_frontier_admits_each_rules_pair_whichever_premise_arrives_last(order, direction, arity):
    _, premise, target, edge, frontier, step, proofs, _, _ = _case(f"frontier: {order}, {direction}, {arity}")

    assert _pairs(frontier) == {(premise, edge)}
    assert step == [["stmt", target, ["sn-ref", target]]]
    assert proofs == [[DIRECTIONS[direction][2], premise, edge]]


# The step grafts what direct derivation grafts, to the last bit, and draining the frontier, which
# by then holds the reverse pair the graft made, proves nothing back into the premise: the graft
# carries the edge's stamp.
# am[verifies a-rt-conditional-enumeration-commit-1017@9831fa] am[rests-on c-rt-fr-stamps-block-mp-feedback-1017@da2658]
@pytest.mark.parametrize("order, direction, arity", CASES)
def test_a_step_grafts_what_direct_derivation_grafts_and_never_feeds_back(order, direction, arity):
    *_, step, proofs, evidence, feedback = _case(f"frontier: {order}, {direction}, {arity}")
    *_, direct_step, direct_proofs, direct_evidence, _ = _case(f"direct: {direction}, {arity}")

    assert (step, proofs, evidence) == (direct_step, direct_proofs, direct_evidence)
    assert evidence[1:3] != ["0.0", "0.0"]
    assert feedback == []


# Two cycles fire the rule once, with direct derivation's evidence, and nothing back into the premise.
# The sweep tries an edge's antecedent first, so on the abductive side the interned end would fire
# modus ponens back into the premise were it a premise, and that graft's stamp would block the
# abduction.
# am[verifies a-rt-derive-sweep-conditional-partners-1017@4b66c3] am[rests-on c-integrate-conditional-enumerators-scope-1017@87de90]
# am[rests-on c-rt-support-is-receipt-or-proof-1017@6c065e]
@pytest.mark.parametrize("direction, arity", PAIRS)
def test_the_sweep_fires_each_rule_on_any_arity_without_feeding_back(direction, arity):
    _, premise, target, edge, proofs, evidence, feedback = _case(f"sweep: {direction}, {arity}")
    *_, direct_evidence, _ = _case(f"direct: {direction}, {arity}")

    assert proofs == [[DIRECTIONS[direction][2], premise, edge]]
    assert evidence == direct_evidence
    assert feedback == []


# The spelling statement shares a key with one end through its typed reference, and with the other
# only when interned raw; neither conditional rule fires on it, and the frontier pairs each end with
# the real edge alone.
# am[verifies a-rt-conditional-enumeration-commit-1017@9831fa] am[rests-on c-rt-fr-canonical-labels-are-strings-1017@01da14]
@pytest.mark.parametrize("side, introduction", list(product(SPELLINGS, INTRODUCTIONS)))
def test_a_concept_spelling_a_referenced_sid_is_never_paired(side, introduction):
    _, a, b, e, c, antecedent_rows, consequent_rows, frontier, fired = _case(f"spelling: {side}, {introduction}")
    spelled, typed = (antecedent_rows, consequent_rows) if side == "antecedent" else (consequent_rows, antecedent_rows)

    assert e in antecedent_rows and e in consequent_rows and c in typed
    assert (c in spelled) is (introduction == "interned raw")
    assert fired == []
    assert _pairs(frontier) == {(a, e), (b, e)}

"""Purpose: verify native frontier insertion, decayed selection, stable ties and truncation,
and that one replaceable comparison controls both sites without escaping a batch."""

from __future__ import annotations

import itertools
import random

import pytest
from snars_differential import tree

from goal_chainer.runtime.budget import RunBudget
from goal_chainer.snars_engine import run_snars_batch
from goal_chainer.errors import MettaEngineError
from goal_chainer.snars_program import SnarsBatch


# Exhaustive two-item key/tick combinations include the sentinel and equal raw keys.
# Seeded longer lists exercise stable retention after insertion at every capacity.
# am[verifies a-integrate-frontier-order-hook-1017@dab0ee]
def _cases():
    values = (-2.0, -1.0, -0.0, 0.5, 1.0)
    result = [([(left, lt, "old")], (right, rt, "new"), 4, 1)
              for left, right, lt, rt in itertools.product(values, values, (0, 2), (0, 2))]
    rng = random.Random(20261017)
    for _ in range(128):
        rows = [(rng.choice(values), rng.randrange(4), f"item{i}") for i in range(rng.randrange(8))]
        rows.sort(key=lambda row: -row[0])
        result.append((rows, (rng.choice(values), rng.randrange(4), "new"), 5, rng.randrange(9)))
    return result


# am[verifies a-integrate-frontier-order-hook-1017@dab0ee]
def _row(item):
    value, tick, identity = item
    return f"(Fr {value} {tick} {identity} right)"


# Observe native records directly; projecting repeated patterns can bind sibling expressions.
# Time: each fixture selects once, truncates once and inserts once.
# am[rests-on c-integrate-frontier-observer-captures-1017@64e0a4]
# am[verifies a-integrate-frontier-order-hook-1017@dab0ee]
def _program():
    cases = " ".join(f"(Case {i} ({' '.join(map(_row, rows))}) {_row(item)} {now} {cap})"
                     for i, (rows, item, now, cap) in enumerate(_cases()))
    return (f"(frontier-orders (sn config decay) (collapse "
            f"(let (Case $i $rows $item $now $cap) (superpose ({cases})) "
            "(let* (($inserted (sn fr-insert $rows $item)) "
            "($kept (sn fr-take $cap $inserted)) "
            "($best (sn fr-best $rows $now NoItem -1.0))) "
            "(Order $i $inserted $best $kept)))))")


# am[verifies a-integrate-frontier-order-hook-1017@dab0ee]
def _result(lines):
    found = [line for line in lines if line.startswith("(frontier-orders")]
    assert len(found) == 1, lines
    return tree(found[0])


# The engine executes the public batch. Only its ordering result is observed.
# am[verifies a-integrate-frontier-order-hook-1017@dab0ee]
def _run(program):
    batch = SnarsBatch((), frozenset(), program)
    return _result(run_snars_batch(batch, budget=RunBudget(inference_budget=None, timeout_seconds=900)).output_lines)


# Stable sorting is an independent list oracle for raw insertion and cap retention.
# Selection maximizes the decayed key above the native sentinel, taking the first tie.
# am[verifies a-integrate-frontier-order-hook-1017@dab0ee]
def test_native_order_uses_raw_insertion_decayed_selection_and_stable_ties():
    _, decay, results = _run(_program())
    assert len(results) == len(_cases())
    for result, (rows, item, now, cap) in zip(results, _cases(), strict=True):
        _, index, inserted, selected, retained = result
        assert int(index) < len(results)
        expected = [row[2] for row in sorted([*rows, item], key=lambda row: -row[0])]
        eligible = [(value * float(decay) ** (now - tick), identity) for value, tick, identity in rows
                    if value * float(decay) ** (now - tick) > -1.0]
        best = max(eligible, key=lambda row: row[0])[1] if eligible else "NoItem"
        observed = ([row[3] for row in inserted],
                    selected if selected == "NoItem" else selected[3],
                    [row[3] for row in retained])
        assert observed == (expected, best, expected[:cap])


# The first pop still meets the sentinel's native bound; later ones use the replacement.
# am[verifies a-integrate-frontier-order-hook-1017@dab0ee]
def _replacement(raising=False):
    bindings = (
        "($removed (remove-atom &self (= (sn fr-before $a $av $b $bv) $body))) "
        "($added (add-atom &self (= (sn fr-before $a $av $b $bv) (< $av $bv)))) "
        "($inserted (sn fr-insert ((Fr 1.0 0 old right)) (Fr 0.0 0 new right))) "
        "($selected (sn fr-best ((Fr 1.0 0 old right) (Fr 0.0 0 new right)) 0 NoItem -1.0)) "
    )
    if raising:
        bindings += "($failed (py-call (operator.truediv 1 0))) "
    return (f"(let* ({bindings}) (frontier-orders $inserted $selected "
            "(sn fr-best ((Fr -2.0 0 below right)) 0 NoItem -1.0)))")


# A replacement that changes only pop or only insertion fails this observation.
# am[verifies a-integrate-frontier-order-hook-1017@dab0ee]
def test_one_comparison_controls_retention_and_selection():
    _, inserted, selected, sentinel = _run(_replacement())
    assert [item[3] for item in inserted] == ["new", "old"]
    assert selected[3] == "new"
    assert sentinel == "NoItem"


# Normal and raised-error speculation must restore the actual comparator equation.
# am[verifies a-integrate-frontier-order-hook-1017@dab0ee]
def test_a_comparator_replacement_cannot_escape_its_batch():
    before = _run(_program())
    _run(_replacement())
    assert _run(_program()) == before
    with pytest.raises(MettaEngineError):
        _run(_replacement(raising=True))
    assert _run(_program()) == before

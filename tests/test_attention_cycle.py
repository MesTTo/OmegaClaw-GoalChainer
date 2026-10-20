"""Purpose: check the actual attention transition against exact arithmetic."""

from fractions import Fraction
import json
import math
from pathlib import Path

from hypothesis import given, settings, strategies as st
import pytest

from goal_chainer.runtime.modules import load_metta_module
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.evaluator import plain_value

POLICY = Path(__file__).parents[1] / "src/goal_chainer/policy/goalchainer_attention.metta"


# Direct exact transfers do not use the implementation's credit sorting or grouped fold.
# Time: V+E rational additions; Space: V rational balances.
# am[verifies a-integrate-ecan-conserved-cycle-code-1017]
def _oracle(values, graph, fraction):
    result = list(values)
    floor = min(values, default=Fraction(0))
    for source, neighbors in enumerate(graph):
        targets = neighbors - {source}
        if targets:
            transfer = fraction * (values[source] - floor)
            result[source] -= transfer
            for target in targets:
                result[target] += transfer / len(targets)
    assert sum(result) == sum(values)
    assert all(value >= 0 for value in result)
    return result


# Generated nodes and edges are closed and unique by shape; equal keys cannot denote two nodes.
# am[verifies a-integrate-ecan-conserved-cycle-code-1017]
@st.composite
def _closed_graphs(draw):
    count = draw(st.integers(0, 14))
    weights = draw(st.lists(st.integers(0, 100), min_size=count, max_size=count))
    total = sum(weights) or 1
    graph = [draw(st.sets(st.integers(0, count - 1))) for _ in range(count)]
    return [Fraction(weight, total) for weight in weights], graph


# Only quoted string nodes enter the MeTTa expression; a node cannot execute as a function.
# am[verifies a-integrate-ecan-conserved-cycle-code-1017]
def _call(values, graph, fraction):
    rows = []
    for index, (value, neighbors) in enumerate(zip(values, graph, strict=True)):
        keys = " ".join(json.dumps(f"n{item:04d}") for item in sorted(neighbors))
        rows.append(f'(Row "n{index:04d}" {float(value)!r} ({keys}))')
    return f"(gc-attention-cycle ({' '.join(rows)}) {float(fraction)!r})"


# A named test space keeps the pure policy separate from the process's reasoning worlds.
# am[verifies a-integrate-ecan-conserved-cycle-code-1017]
def _evaluate(call):
    with metta_engine(None) as engine:
        space = engine.space("goalchainer-attention-cycle-test")
        load_metta_module(engine, POLICY, space=space)
        groups = space.run("!" + call)
        assert len(groups) == len(groups[0]) == 1, groups
        return plain_value(groups[0][0])


# The tolerance describes floating evaluation; the rational oracle above conserves exactly.
# am[verifies a-integrate-ecan-conserved-cycle-code-1017]
def _check(actual, values, graph, fraction):
    expected = _oracle(values, graph, fraction)
    assert len(actual) == len(values)
    for index, (row, wanted) in enumerate(zip(actual, expected, strict=True)):
        tag, key, value, neighbors = row
        assert str(tag) == "Row" and str(key) == f"n{index:04d}"
        assert [str(item) for item in neighbors] == [f"n{item:04d}" for item in sorted(graph[index])]
        assert math.isfinite(float(value)) and float(value) >= 0
        assert float(value) == pytest.approx(float(wanted), rel=1e-12, abs=5e-324)
    assert math.fsum(float(row[2]) for row in actual) == pytest.approx(float(sum(values)), rel=1e-12, abs=5e-324)


# am[verifies a-integrate-ecan-conserved-cycle-code-1017]
@settings(deadline=None, max_examples=60)
@given(_closed_graphs(), st.integers(0, 16))
def test_cycle_matches_rational_transfer_on_closed_graphs(case, numerator):
    values, graph = case
    fraction = Fraction(numerator, 16)
    _check(_evaluate(_call(values, graph, fraction)), values, graph, fraction)


# Empty, zero, equal, isolated, self-only, directed, mixed-degree and tiny balances.
# am[verifies a-integrate-ecan-conserved-cycle-code-1017]
def _edge_cases():
    yield [], []
    yield [Fraction(1)], [{0}]
    yield [Fraction(0)] * 4, [set(), {0}, {2}, {1, 3}]
    yield [Fraction(1, 4)] * 4, [{1}, {0, 2}, {1, 3}, {2}]
    yield [Fraction(3, 4), Fraction(1, 4), Fraction(0)], [{1, 2}, set(), {0, 2}]
    yield [Fraction(1, 10**300), Fraction(0)], [{1}, set()]
    yield [Fraction(1, 1001)] * 1001, [set() for _ in range(1001)]


# Every edge case is checked against the rational oracle.
# am[verifies a-integrate-ecan-conserved-cycle-code-1017]
@pytest.mark.parametrize("fraction", [Fraction(0), Fraction(1, 5), Fraction(2, 5), Fraction(1)])
def test_edge_cases_match_the_rational_oracle(fraction):
    for values, graph in _edge_cases():
        _check(_evaluate(_call(values, graph, fraction)), values, graph, fraction)


# Intervening cycles and different graphs must not change the answer to the original input.
# am[verifies a-integrate-ecan-conserved-cycle-code-1017]
def test_repeated_cycles_keep_the_graph_and_do_not_leak_between_calls():
    values, graph = list(_edge_cases())[4]
    original = _call(values, graph, Fraction(2, 5))
    first = _evaluate(original)
    for _ in range(20):
        actual = _evaluate(_call(values, graph, Fraction(2, 5)))
        _check(actual, values, graph, Fraction(2, 5))
        values = [Fraction.from_float(float(row[2])) for row in actual]
    _evaluate(_call([Fraction(1), Fraction(0)], [{1}, {0}], Fraction(1)))
    assert _evaluate(original) == first

"""Purpose: verify typed attention incidence, normalized query cues and speculative graph state."""

import json
import math
from pathlib import Path

from snars_differential import tree

from goal_chainer.runtime.budget import RunBudget, run_bounded
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.snars_engine import prepare_snars_world

GRAPH = Path(__file__).parents[1] / "src/goal_chainer/policy/goalchainer_attention_graph.metta"


# Authored trees go through real SNARS canonicalization and index construction.
# am[verifies a-integrate-ecan-packaged-graph-1017]
def _atom(label):
    return f'(sh-atom (tag C c NoRoles ()) {json.dumps(label)})'


# am[verifies a-integrate-ecan-packaged-graph-1017]
def _statement(label, arguments):
    roles = "".join(role for role, _ in arguments) or "NoRoles"
    args = " ".join(f"(arg {role} {value})" for role, value in arguments)
    return f'(sh (tag P d {roles} ()) {json.dumps(label)} (args ({args})))'


# Include ordinary labels equal to statement IDs, repeated roles and recursive connectors.
# am[verifies a-integrate-ecan-packaged-graph-1017]
def _body():
    first = _statement("is", [("s", _atom("alpha")), ("o", _atom("beta"))])
    target = _statement("is", [("s", _atom("gamma")), ("o", _atom("delta"))])
    conditional = _statement("==>", [("s", "(sn-ref $first)"), ("o", "(sn-ref $target)")])
    collision = _statement("is", [("s", "(sh-atom (tag C c NoRoles ()) $first)"),
                                   ("o", _atom("if"))])
    repeated = _statement("many", [("r", _atom("alpha")), ("r", _atom("alpha")),
                                   ("x", f'(sh-conn {_atom("beta")} (args ()))')])
    query = _statement("query", [("s", _atom("alpha")), ("o", _atom("alpha")),
                                 ("r", "(sn-ref $first)"), ("x", _atom("missing"))])
    later = _statement("later", [("s", _atom("new")), ("o", _atom("alpha"))])
    absent = _statement("absent", [("s", _atom("missing"))])
    bindings = [
        '($empty (gc-attention-rows))',
        f'($first (believe! {first} ((source "first") (trust 1.0))))',
        f'($canonical (sn canon {target}))', '($target (sn sid $canonical))',
        '($interned (sn intern! $target $canonical instance aleatory))',
        f'($conditional (believe! {conditional} ((source "conditional") (trust 1.0))))',
        f'($collision (believe! {collision} ((source "collision") (trust 1.0))))',
        f'($repeated (believe! {repeated} ((source "repeated") (trust 1.0))))',
        f'($isolated (believe! {_atom("isolated")} ((source "isolated") (trust 1.0))))',
        '($built (gc-attention-build!))', '($before (gc-attention-rows))',
        '($rebuilt (gc-attention-build!))', '($again (gc-attention-rows))',
        f'($seeded (gc-attention-seed! (sn canon {query})))',
        '($seed (gc-attention-rows))',
        f'($later (believe! {later} ((source "later") (trust 1.0))))',
        '($added (gc-attention-add-statement! $later))',
        '($after (gc-attention-rows))',
        '($duplicate (gc-attention-add-statement! $later))',
        '($final (gc-attention-rows))',
        f'($absent (gc-attention-seed! (sn canon {absent})))',
        '($zero (gc-attention-rows))',
        f'($reseeded (gc-attention-seed! (sn canon {query})))',
        '($restored (gc-attention-rows))',
        '($statements (msort (collapse (match &self (sn stmt $sid $term) (Statement $sid $term)))))',
    ]
    return ('(let* (' + ' '.join(bindings) + ') '
            '(GraphCase $empty $first $before $again $seeded $seed $after $duplicate $final '
            '$absent $zero $restored $statements))')


# Compiling the operation keeps collection metadata proportional to the observable answer.
# Definition, native ingestion, graph work and result all remain inside one charged batch.
# am[rests-on c-integrate-compiled-query-natural-boundary-1017]
# am[verifies a-integrate-ecan-packaged-graph-1017]
# am[addresses i-integrate-graph-test-helper-unresolved-1017]
def _run():
    assert GRAPH.is_file()
    source = (GRAPH.read_text() + f'\n(= (attention-graph-case) {_body()})\n'
              '!(attention-graph-result (attention-graph-case))')
    world = prepare_snars_world()
    with metta_engine(None) as engine:
        space = engine.space(world.space)
        with space.speculative(), space.capture():
            answers, _ = run_bounded(space, source, budget=RunBudget(
                inference_budget=None, timeout_seconds=900))
        lines = [str(atom) for group in answers for atom in group]
    records = [line for line in lines if line.startswith("(attention-graph-result ")]
    assert len(records) == 1, lines
    value = tree(records[0])[1]
    assert value[0] == "GraphCase", value
    return value


# Canonical argument structure is the oracle; it calls no attention projection or native index reader.
# Time: one argument traversal and set insertion per incidence.
# am[rests-on c-integrate-native-index-typed-closure-1017]
# am[verifies a-integrate-ecan-packaged-graph-1017]
def _expected(statements):
    adjacency = {}
    for _, sid, canonical in statements:
        source = ("AttentionStatement", sid)
        adjacency.setdefault(source, set())
        if canonical[0] != "sh":
            continue
        for _, _, filler in canonical[3][1]:
            original = filler
            while filler[0] == "sh-conn":
                filler = filler[1]
            key = filler[1] if filler[0] == "sn-ref" else filler[2]
            kind = "AttentionStatement" if original[0] == "sn-ref" else "AttentionConcept"
            target = (kind, key)
            adjacency[source].add(target)
            adjacency.setdefault(target, set()).add(source)
    return adjacency


# Rebuilding cannot mint nodes or currency; one query divides one unit among its distinct present cues.
# am[verifies a-integrate-ecan-packaged-graph-1017]
def test_graph_matches_canonical_incidence_and_normalizes_distinct_query_cues():
    value = _run()
    (_, empty, first, before, again, seeded, seed, after, duplicate, final,
     absent, zero, restored, statements) = value
    assert empty == []
    assert before == again
    assert duplicate in ("False", "false")
    assert after == final
    assert absent == []
    assert all(float(balance) == 0.0 for _, _, balance, _ in zero)
    assert restored == final
    expected = _expected(statements)
    actual = {tuple(key): {tuple(neighbor) for neighbor in neighbors}
              for _, key, balance, neighbors in after}
    assert actual == expected
    assert len(actual) == len(after)
    assert all(len(neighbors) == len(set(map(tuple, neighbors))) for _, _, _, neighbors in after)
    assert all(tuple(neighbor) in actual for _, _, _, neighbors in after for neighbor in neighbors)
    assert all(float(balance) == 0.0 for _, _, balance, _ in before)
    cues = {("AttentionStatement", first), ("AttentionConcept", '"alpha"')}
    assert set(map(tuple, seeded)) == cues
    balances = {tuple(key): float(balance) for _, key, balance, _ in seed}
    assert {key for key, balance in balances.items() if balance} == cues
    assert all(balances[key] == 0.5 for key in cues)
    assert math.fsum(float(balance) for _, _, balance, _ in after) == 1.0
    assert all(float(balance) == balances.get(tuple(key), 0.0) for _, key, balance, _ in after)


# The second call sees no graph state from the first, even in a shared prepared world.
# am[verifies a-integrate-ecan-packaged-graph-1017]
def test_graph_state_does_not_escape_a_completed_batch():
    assert _run() == _run()

"""Purpose: the bigraph kernel against BigraphER on random models of their shared fragment. For every
model in tests/data/bigraph/bigrapher-random.json, which bigraph_bigrapher_reference.py generated from
BigraphER's GBS solver, the kernel's closure from the model's agent has BigraphER's numbers of states,
transitions and occurrences, and its states correspond one to one with BigraphER's under isomorphism; and
the models together exercise every feature of the fragment, so the comparison is never vacuous."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from metta import parse

import bigraph_oracle as o
from goal_chainer.bigraph import kernel
from goal_chainer.runtime.budget import RunBudget

DATA = json.loads((Path(__file__).resolve().parent / "data" / "bigraph" / "bigrapher-random.json").read_text())


# am[verifies a-brs-k-bigrapher-1018@994f8c]
def budget() -> RunBudget:
    return RunBudget(inference_budget=None, timeout_seconds=600)


# am[verifies a-brs-k-bigrapher-1018@994f8c]
def text(atom) -> str:
    return " ".join(repr(atom).split())


# am[verifies a-brs-k-bigrapher-1018@994f8c]
def closure(signature, rules, start):
    """Every state reachable from START, one per isomorphism class, compared by bucket and then by
    isomorphism, with the transitions and occurrences BigraphER's full mode counts, and the states by
    bucket."""

    buckets = {text(kernel.bucket(start, budget=budget())): [start]}
    states, frontier, transitions, occurrences = [start], [start], 0, 0
    while frontier:
        current = frontier.pop(0)
        for t in kernel.transitions(signature, rules, current, budget=budget()):
            successor = t.children[1]
            transitions += 1
            occurrences += sum(int(f.children[2].value) for f in t.children[2].children)
            same = buckets.setdefault(text(kernel.bucket(successor, budget=budget())), [])
            if not any(kernel.isomorphic(successor, known, budget=budget()) for known in same):
                same.append(successor)
                states.append(successor)
                frontier.append(successor)
    return states, transitions, occurrences, buckets


# am[verifies a-brs-k-bigrapher-1018@994f8c] am[verifies a-brs-k-successors-1018@311dd0]
# am[verifies a-brs-k-iso-1018@f2617a]
@pytest.mark.parametrize("model", DATA["models"], ids=[m["name"] for m in DATA["models"]])
def test_the_kernel_closure_matches_bigrapher(model):
    signature, rules, start = parse(model["signature"]), tuple(parse(r) for r in model["rules"]), parse(model["agent"])
    states, transitions, occurrences, buckets = closure(signature, rules, start)
    assert (len(states), transitions, occurrences) == (len(model["states"]), model["transitions"], model["occurrences"]), model["model"]
    for theirs in map(parse, model["states"]):
        same = buckets.get(text(kernel.bucket(theirs, budget=budget())), [])
        assert sum(kernel.isomorphic(theirs, mine, budget=budget()) for mine in same) == 1, (text(theirs), model["model"])


# am[verifies a-brs-k-bigrapher-1018@994f8c]
def test_the_reference_models_exercise_the_whole_shared_fragment():
    seen = dict.fromkeys(("copies", "discards", "regions", "closed_edges", "names", "classes", "rules", "loops", "steps"), 0)
    for model in DATA["models"]:
        rules = [parse(r) for r in model["rules"]]
        seen["rules"] += len(rules) > 1
        seen["classes"] += len({text(r.children[6]) for r in rules}) > 1
        seen["steps"] += model["transitions"] > 0
        seen["loops"] += model["transitions"] >= len(model["states"])
        for rule in rules:
            redex = o.from_atom(rule.children[2])
            eta = [int(e.children[1].value) for e in rule.children[4].children[1:]]
            seen["copies"] += len(eta) != len(set(eta))
            seen["discards"] += len(set(range(redex.sites)) - set(eta)) > 0
            seen["regions"] += redex.roots > 1
            seen["closed_edges"] += bool(redex.edges())
            seen["names"] += bool(redex.outer)
    assert all(count > 0 for count in seen.values()), seen

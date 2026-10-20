"""Purpose: property tests of the bigraph kernel's algebra on random bigraphs: composition and tensor agree
with the oracle's definitions exactly and satisfy associativity, identity and interchange, the merge
product is BigraphER's par, refusals name their faults, and composing every occurrence's own decomposition
with its redex gives back the agent."""

from __future__ import annotations

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from metta import parse

import bigraph_oracle as o
from goal_chainer.bigraph import kernel
from goal_chainer.runtime.budget import RunBudget


# am[verifies a-brs-k-algebra-1018@e81ae4]
def budget() -> RunBudget:
    return RunBudget(inference_budget=None, timeout_seconds=600)


# am[implements a-brs-k-algebra-1018@e81ae4]
def random_bigraph(rng: random.Random, sites: int, inner: tuple, roots: int, outer: tuple, tag: str) -> o.Big:
    """A well-formed bigraph with the given faces, its node ids and edges prefixed by TAG so that two
    bigraphs drawn with different tags have disjoint supports. A face without roots holds no node and
    no site."""

    b = o.Big(sites, inner, roots, outer)
    hosts: list[str] = []
    for i in range(rng.randint(0, 4) if roots else 0):
        node = f"(new {tag} {i})" if rng.random() < 0.7 else f"{tag}{i}"
        control = rng.choice(list(o.SIGNATURE))
        b.controls[node] = control
        b.parent[node] = rng.choice([("root", j) for j in range(roots)] + hosts)
        if o.SIGNATURE[control].kind != "atomic":
            hosts.append(node)
    for k in range(sites):
        b.parent[("site", k)] = rng.choice([("root", j) for j in range(roots)] + hosts)
    targets = [("name", y) for y in outer] + [("edge", f"{tag}e{i}") for i in range(2)]
    for node, control in list(b.controls.items()):
        for k in range(o.SIGNATURE[control].arity):
            b.links[("port", node, k)] = rng.choice(targets)
    for x in inner:
        b.links[("inner", x)] = rng.choice(targets)
    return b


# am[implements a-brs-k-algebra-1018@e81ae4]
def places(rng: random.Random, count: int) -> list[int]:
    """Place counts for a chain of COUNT faces, inner to outer: once a face has a place every later one
    does, since a bigraph with no root can hold no site."""

    counts = [rng.randint(0, 2) for _ in range(count)]
    for i in range(1, count):
        if counts[i - 1] and not counts[i]:
            counts[i] = 1
    return counts


# am[verifies a-brs-k-algebra-1018@e81ae4]
def names(rng: random.Random) -> tuple:
    return tuple(f"n{i}" for i in range(rng.randint(0, 2)))


# am[verifies a-brs-k-algebra-1018@e81ae4]
def atom(b: o.Big):
    return parse(o.term(b))


# am[verifies a-brs-k-algebra-1018@e81ae4]
def same(kernel_atom, oracle_big) -> bool:
    return o.from_atom(kernel_atom).key() == oracle_big.key()


# am[verifies a-brs-k-algebra-1018@e81ae4]
@settings(deadline=None, max_examples=120)
@given(rng=st.randoms(use_true_random=False))
def test_composition_matches_the_definition_and_is_associative_with_identities(rng):
    m, n, k, j = places(rng, 4)
    xs, ys, zs, ws = names(rng), names(rng), names(rng), names(rng)
    h = random_bigraph(rng, m, xs, n, ys, "h")
    g = random_bigraph(rng, n, ys, k, zs, "g")
    f = random_bigraph(rng, k, zs, j, ws, "f")
    fg = kernel.compose(atom(f), atom(g), budget=budget())
    assert same(fg, o.compose(f, g))
    left = kernel.compose(fg, atom(h), budget=budget())
    right = kernel.compose(atom(f), kernel.compose(atom(g), atom(h), budget=budget()), budget=budget())
    assert o.from_atom(left).key() == o.from_atom(right).key()
    assert same(kernel.compose(atom(o.identity(j, ws)), atom(f), budget=budget()), f)
    assert same(kernel.compose(atom(f), atom(o.identity(k, zs)), budget=budget()), f)


# am[verifies a-brs-k-algebra-1018@e81ae4]
@settings(deadline=None, max_examples=120)
@given(rng=st.randoms(use_true_random=False))
def test_tensor_matches_the_definition_and_satisfies_interchange(rng):
    m1, n1, k1 = places(rng, 3)
    m2, n2, k2 = places(rng, 3)
    g1 = random_bigraph(rng, m1, ("a",), n1, ("b",), "p")
    f1 = random_bigraph(rng, n1, ("b",), k1, ("c",), "q")
    g2 = random_bigraph(rng, m2, ("d",), n2, ("e",), "r")
    f2 = random_bigraph(rng, n2, ("e",), k2, ("f",), "s")
    assert same(kernel.tensor(atom(f1), atom(f2), budget=budget()), o.tensor(f1, f2))
    before = kernel.compose(kernel.tensor(atom(f1), atom(f2), budget=budget()),
                            kernel.tensor(atom(g1), atom(g2), budget=budget()), budget=budget())
    after = kernel.tensor(kernel.compose(atom(f1), atom(g1), budget=budget()),
                          kernel.compose(atom(f2), atom(g2), budget=budget()), budget=budget())
    assert o.from_atom(before).key() == o.from_atom(after).key()


# am[verifies a-brs-k-algebra-1018@e81ae4]
def test_products_and_refusals():
    a = o.Big(0, (), 1, ("x",), {"(new a 0)": "B"}, {"(new a 0)": ("root", 0)}, {("port", "(new a 0)", 0): ("name", "x")})
    b = o.Big(0, (), 1, ("x",), {"(new b 0)": "B"}, {"(new b 0)": ("root", 0)}, {("port", "(new b 0)", 0): ("name", "x")})
    merged = o.from_atom(kernel.merge_product(atom(a), atom(b), budget=budget()))
    assert merged.roots == 1 and set(merged.parent.values()) == {("root", 0)} and merged.outer == ("x",)
    parallel = o.from_atom(kernel.parallel(atom(a), atom(b), budget=budget()))
    assert parallel.roots == 2 and parallel.outer == ("x",)
    with pytest.raises(kernel.BigraphFault) as refused:
        kernel.tensor(atom(a), atom(b), budget=budget())
    assert refused.value.details["faults"] == ("(SharedName Outer x)",)
    with pytest.raises(kernel.BigraphFault) as refused:
        kernel.compose(atom(a), atom(b), budget=budget())
    assert any("InterfaceMismatch" in f for f in refused.value.details["faults"])
    # Matching interfaces, but both sides hold node (new a 0).
    holder = o.Big(1, ("x",), 1, ("x",), {"(new a 0)": "B"}, {"(new a 0)": ("root", 0), ("site", 0): ("root", 0)},
                   {("port", "(new a 0)", 0): ("name", "x"), ("inner", "x"): ("name", "x")})
    with pytest.raises(kernel.BigraphFault) as refused:
        kernel.compose(atom(holder), atom(a), budget=budget())
    assert refused.value.details["faults"] == ("(SharedNode (new a 0))",)


# am[verifies a-brs-k-react-algebra-1018@fd3d1f] am[verifies a-brs-k-algebra-1018@e81ae4]
@settings(deadline=None, max_examples=120)
@given(rng=st.randoms(use_true_random=False))
def test_each_occurrence_recomposes_to_its_agent(rng):
    sig = parse(o.signature_text(o.SIGNATURE))
    g = o.random_agent(rng, o.SIGNATURE)
    redex = o.random_redex(rng, o.SIGNATURE, g)
    rule = parse(o.rule_text(o.Rule("r", redex, redex, {k: k for k in range(redex.sites)})))
    for occurrence in kernel.occurrences(sig, rule, atom(g), budget=budget()):
        decomposition = kernel.decompose(occurrence, atom(g), budget=budget())
        context, parameter = decomposition.children[1], decomposition.children[2]
        phi = {repr(r.children[1]): repr(r.children[2]) for r in occurrence.children[3].children[1:]}
        edges = {repr(r.children[1]): repr(r.children[2]) for r in occurrence.children[4].children[1:]}
        vias = tuple(x for x in o.from_atom(context).inner if x.startswith("(Via"))
        middle = kernel.tensor(atom(o.redex_image(redex, phi, edges)), atom(o.identity(0, vias)), budget=budget())
        whole = kernel.compose(context, kernel.compose(middle, parameter, budget=budget()), budget=budget())
        assert o.from_atom(whole).key() == g.key(), o.term(g)

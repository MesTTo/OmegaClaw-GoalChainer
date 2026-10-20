"""Purpose: property tests of the bigraph kernel against the independent brute-force oracle in
bigraph_oracle.py on random agents and solid rules with indexed ports, sites, several regions, passive
controls, inner names, named nodes and application conditions: occurrence sets, reaction outcomes up to
isomorphism, successor well-formedness and isomorphism decisions; and a check that the generator reaches
every one of those behaviours, so the properties are never vacuous."""

from __future__ import annotations

import random

from hypothesis import given, settings
from hypothesis import strategies as st
from metta import parse

import bigraph_oracle as o
from goal_chainer.bigraph import kernel
from goal_chainer.runtime.budget import RunBudget

SIG = parse(o.signature_text(o.SIGNATURE))


# am[verifies a-brs-k-oracle-1018@f988b3]
def budget() -> RunBudget:
    return RunBudget(inference_budget=None, timeout_seconds=600)


# am[verifies a-brs-k-oracle-1018@f988b3]
def text(atom) -> str:
    return " ".join(repr(atom).split())


# am[implements a-brs-k-oracle-1018@f988b3]
def random_case(rng: random.Random):
    while True:
        g = o.random_agent(rng, o.SIGNATURE)
        redex = o.random_redex(rng, o.SIGNATURE, g)
        reactum, eta = o.random_reactum(rng, o.SIGNATURE, redex)
        if o.well_formed(reactum, o.SIGNATURE):
            conditions = [o.random_condition(rng, o.SIGNATURE, redex) for _ in range(rng.choice((0, 0, 1, 2)))]
            return g, o.Rule("r", redex, reactum, eta, conditions)


# am[verifies a-brs-k-oracle-1018@f988b3] am[verifies a-brs-k-occurrence-1018@0ed298] am[verifies a-brs-k-react-1018@41ec8d]
# am[verifies c-integrate-brs-positional-oracle-1018@6f9f3a]
@settings(deadline=None, max_examples=200)
@given(rng=st.randoms(use_true_random=False))
def test_occurrences_and_reactions_agree_with_the_oracle(rng):
    g, rule = random_case(rng)
    rule_atom, state = parse(o.rule_text(rule)), parse(o.term(g))
    expected = {o.normal_occurrence(occ): parts for occ, parts in o.occurrences(o.SIGNATURE, rule, g)}
    answers = kernel.occurrences(SIG, rule_atom, state, budget=budget())
    actual = {o.normal_occurrence(o.occurrence_key(a)): a for a in answers}
    assert set(actual) == set(expected), (o.term(g), o.rule_text(rule))
    assert len(answers) == len(actual), "each occurrence is answered once"
    for occ, parts in expected.items():
        outcome = o.react(rule, g, occ, parts)
        answer = kernel.apply(SIG, rule_atom, state, actual[occ], budget=budget())
        if outcome[0] == "refused":
            assert text(answer.children[0]) == "Refused"
            assert text(answer.children[3]) == f"(DuplicatesNamed ({' '.join(outcome[1])}))"
        else:
            successor = o.from_atom(answer.children[3])
            assert o.well_formed(successor, o.SIGNATURE), text(answer)
            assert o.isomorphic(successor, outcome[1]), (text(answer), o.term(outcome[1]))
            assert kernel.isomorphic(answer.children[3], parse(o.term(outcome[1])), budget=budget())


# am[verifies a-brs-k-oracle-1018@f988b3] am[verifies a-brs-k-iso-1018@f2617a]
@settings(deadline=None, max_examples=200)
@given(rng=st.randoms(use_true_random=False))
def test_isomorphism_agrees_with_brute_force(rng):
    g = o.random_agent(rng, o.SIGNATURE, max_nodes=7)
    anonymous = sorted(n for n in g.controls if o.anonymous(n))
    order = list(range(len(anonymous)))
    rng.shuffle(order)
    renamed = o.rename(g, {n: f"(new h {i})" for n, i in zip(anonymous, order)}, {e: f"z{e}" for e in g.edges()})
    choice = rng.random()
    other = renamed if choice < 0.4 else mutate(rng, renamed) if choice < 0.8 else o.random_agent(rng, o.SIGNATURE, max_nodes=7)
    want = o.isomorphic(g, other)
    assert kernel.isomorphic(parse(o.term(g)), parse(o.term(other)), budget=budget()) == want, (o.term(g), o.term(other))


# The generator, run against the oracle alone over fixed seeds, reaches every behaviour the properties
# compare: occurrences, successors, refusals, conditions that filter, passive blocking, several regions,
# two outer names on one link, parameter ports joining a redex edge through an inner name, and
# isomorphic and non-isomorphic pairs.
# am[verifies a-brs-k-oracle-1018@f988b3]
def test_the_generator_reaches_every_compared_behaviour():
    rng = random.Random(20261018)
    seen = dict.fromkeys(("occurrences", "successors", "refused", "conditioned", "passive", "regions",
                          "shared_names", "inner_extras"), 0)
    for _ in range(600):
        g, rule = random_case(rng)
        found = o.occurrences(o.SIGNATURE, rule, g)
        unconditioned = list(o.embeddings(o.SIGNATURE, rule.redex, g))
        seen["occurrences"] += len(found)
        seen["conditioned"] += len(unconditioned) - len(found)
        seen["passive"] += len(list(o.embeddings(o.SIGNATURE, rule.redex, g, check_active=False))) - len(unconditioned)
        seen["regions"] += len(found) if rule.redex.roots > 1 else 0
        for occ, parts in found:
            seen["refused" if o.react(rule, g, occ, parts)[0] == "refused" else "successors"] += 1
            links = [link for _, link in occ.names]
            seen["shared_names"] += len(links) != len(set(links))
            for redex_edge, agent_edge in occ.edges:
                ports = sum(1 for pt, link in rule.redex.links.items() if pt[0] == "port" and link == ("edge", redex_edge))
                seen["inner_extras"] += sum(1 for link in g.links.values() if link == ("edge", agent_edge)) > ports
    assert all(count > 0 for count in seen.values()), seen


# am[verifies a-brs-k-oracle-1018@f988b3]
def mutate(rng: random.Random, b: o.Big) -> o.Big:
    """B with one port link changed, two ports swapped or one node moved, which may or may not keep it
    isomorphic."""

    out = o.Big(b.sites, b.inner, b.roots, b.outer, dict(b.controls), dict(b.parent), dict(b.links))
    ports = [pt for pt in out.links if pt[0] == "port"]
    kind = rng.choice(["link", "parent", "swap"])
    if kind == "link" and ports:
        out.links[rng.choice(ports)] = rng.choice(sorted(set(out.links.values())) + [("edge", "zz")])
    elif kind == "swap" and len(ports) >= 2:
        a, c = rng.sample(ports, 2)
        out.links[a], out.links[c] = out.links[c], out.links[a]
    elif out.controls:
        n = rng.choice(sorted(out.controls))
        hosts = [h for h in sorted(out.controls) if h != n and o.SIGNATURE[out.controls[h]].kind != "atomic"
                 and n not in out.below([h]) and h not in out.below([n])]
        out.parent[n] = rng.choice([("root", j) for j in range(out.roots)] + hosts)
    return out

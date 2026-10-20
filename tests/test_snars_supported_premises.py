"""Purpose: verify that a SNARS statement is a premise exactly when it is supported, observed with a
receipt or derived with a proof: through a direct pair, the frontier, the derive! sweep, the backward
prover, ask!, an on-demand conversion and modus ponens, an authored statement takes part whatever its
evidence, negative and vacuous included, a derived one takes part, and a statement only interned, as
a conditional's endpoint, a query, a claim or raw, takes part in none of them; and that the rule miner
counts a statement toward a pattern, a chain or a closing edge exactly when it is supported, once
however many receipts or proofs it has."""

from __future__ import annotations

from functools import cache
from itertools import product

import pytest
from snars_differential import tree

from goal_chainer.runtime.budget import RunBudget
from goal_chainer.snars_engine import run_snars_batch
from goal_chainer.snars_program import SnarsBatch

# P, the statement under test, chains with Q into "alpha is gamma" by deduction.
P = '(sn p so "is" ((arg s (sn c "alpha")) (arg o (sn c "beta"))))'
Q = '(sn p so "is" ((arg s (sn c "beta")) (arg o (sn c "gamma"))))'
CANON = f"(sn pl-canon (sn peel {P}))"
BELIEVE_Q = f'($q (believe! {Q} ((source "partner") (trust 1.0))))'

# How P comes to be in the store, and whether that supports it. A derived P has a proof from two
# believed statements; every interned P has neither a receipt nor a proof.
KINDS = {
    "believed": (True, f'($p (believe! {P} ((source "premise") (trust 1.0))))'),
    "believed with negative evidence":
        (True, f'($p (believe! {P} ((source "premise") (trust 1.0) (evidence 0.0 1.0))))'),
    "believed with no evidence": (True, f'($p (believe! {P} ((source "premise") (trust 1.0) (evidence 0.0 0.0))))'),
    "derived": (True, '($m1 (believe! (sn p so "is" ((arg s (sn c "alpha")) (arg o (sn c "mu")))) ((source "chain") (trust 1.0)))) '
                      '($m2 (believe! (sn p so "is" ((arg s (sn c "mu")) (arg o (sn c "beta")))) ((source "chain") (trust 1.0)))) '
                      f'($derived (collapse (sn derive-pair! $m1 $m2))) ($p (sn sid {CANON}))'),
    "interned as a conditional's endpoint": (False, f'($p (sn intern-ref! {P} "premise-test"))'),
    "interned as a query": (False, f'($p (sn ingest-query! {CANON} "premise-test"))'),
    "interned raw": (False, f"($p (sn sid {CANON})) ($raw (sn intern! $p {CANON} instance aleatory))"),
}

# Each path P could take part in, as the bindings after P's and what it found: proofs it made, a
# frontier pair, backward proofs or answers. Empty when P took no part.
PATHS = {
    "a direct pair": f"{BELIEVE_Q} ($fired (collapse (sn derive-pair! $p $q))) "
                     "($found (collapse (match &self (sn proof $x (ded $p $q)) $x)))",
    "the frontier": f"{BELIEVE_Q} ($queue (sn frontier)) ($pairs (collapse (let (Fr $v $t $s1 $s2) (superpose $queue) "
                    "(if (and (== $s1 $p) (== $s2 $q)) ($s1 $s2) (empty))))) "
                    "($found $pairs)",
    "the derive! sweep": f"{BELIEVE_Q} ($cycles (sn cycles 1)) ($found (collapse (match &self (sn proof $x (ded $p $q)) $x)))",
    "the backward prover": f"($found (collapse (sn prove {P} 1)))",
    # On demand, convert! matches the statement itself and commits through weak-quantum-d!, so only
    # the commit's own check stands between it and an unsupported premise.
    "a unary conversion": "($found (collapse (sn convert! $p)))",
    "ask!": f"($found (collapse (ask! {P})))",
    "modus ponens": ('($b (sn intern-ref! (sn p so "is" ((arg s (sn c "gamma")) (arg o (sn c "delta")))) "premise-test")) '
                     '($e (believe! (sh (tag P d so ()) "==>" (args ((arg s (sn-ref $p)) (arg o (sn-ref $b))))) '
                     '((source "conditional") (trust 1.0) (domain conditional)))) '
                     "($fired (collapse (sn derive-pair! $p $e))) ($found (collapse (match &self (sn proof $b (mp $p $e)) True)))"),
}
# A claim statement, "observer claims Q", interned beside a believed Q, and the two queries that
# could answer with it.
CLAIM = '(sh (tag P d sr ()) "claim" (args ((arg s (sh-atom (tag C p NoRoles ()) "observer")) (arg r (sn-ref $q)))))'
# A believed antecedent, its consequent interned, and the edge between them believed or interned
# raw; the backward prover asked for the consequent, which only the edge's rule can prove.
CONSEQUENT = '(sn p so "is" ((arg s (sn c "gamma")) (arg o (sn c "delta"))))'
EDGE_TREE = '(sh (tag P d so ()) "==>" (args ((arg s (sn-ref $p)) (arg o (sn-ref $b)))))'
EDGES = {
    "believed": (True, f'($e (believe! {EDGE_TREE} ((source "conditional") (trust 1.0) (domain conditional))))'),
    "interned raw": (False, f"($e (sn sid {EDGE_TREE})) ($raw (sn intern! $e {EDGE_TREE} conditional aleatory))"),
}

# P for the miner's count: each kind, P believed from two sources, and P derived from two pairs, with
# how many receipts and proofs P then has.
SECOND_PAIR = ('($n1 (believe! (sn p so "is" ((arg s (sn c "alpha")) (arg o (sn c "nu")))) ((source "chain") (trust 1.0)))) '
               '($n2 (believe! (sn p so "is" ((arg s (sn c "nu")) (arg o (sn c "beta")))) ((source "chain") (trust 1.0)))) '
               '($again (collapse (sn derive-pair! $n1 $n2)))')
COUNTED = {
    **{kind: (int(supported), binding) for kind, (supported, binding) in KINDS.items()},
    "believed from two sources": (2, f'{KINDS["believed"][1]} ($again (believe! {P} ((source "second") (trust 1.0))))'),
    "derived from two pairs": (2, f'{KINDS["derived"][1]} {SECOND_PAIR}'),
}

# A transitivity chain x->m->y and its closing edge x->y, each statement believed once (B), believed
# from two sources (BB) or interned as a conditional's endpoint (R); the closing edge may instead be
# deduced from the chain's own statements through the deduction commit (D), its proof its only
# support, or be absent (A). Every count the miner makes is per copula, so each arrangement gets its
# own copula and all of them share one program.
OPERANDS = ("B", "BB", "R")
ARRANGEMENTS = list(product(OPERANDS, OPERANDS, OPERANDS + ("D", "A")))


# am[verifies a-rt-miner-supported-statements-1017@1e8790]
def _copula(arrangement: tuple[str, str, str]) -> str:
    return "chain-" + "-".join(arrangement)


# The bindings that put the statement at POSITION, xm, my or xy, of arrangement INDEX into the store;
# its variable is named by both, so the shared program's names stay distinct. A deduced closing edge
# commits through derived! from the arrangement's own operands, which refuses when either is
# unsupported, so collapse keeps the program going. Through derive-pair! the same operands would
# also conclude y->x by exemplification, adding chains to the copula.
# am[verifies a-rt-miner-supported-statements-1017@1e8790] am[rests-on c-rt-exe-fires-on-chains-1017@b5c2da]
def _statement(index: int, position: str, kind: str, copula: str) -> str:
    subject, obj = position
    tree = f'(sn p so "{copula}" ((arg s (sn c "{subject}")) (arg o (sn c "{obj}"))))'
    name = f"$s{index}{position}"
    believed = f'({name} (believe! {tree} ((source "miner") (trust 1.0))))'
    return {
        "B": believed,
        "BB": f'{believed} ({name}-again (believe! {tree} ((source "second") (trust 1.0))))',
        "R": f'({name} (sn intern-ref! {tree} "miner-test"))',
        "D": f"({name} (collapse (sn derived! (sn pl-canon (sn peel {tree})) $s{index}xm $s{index}my 0.5)))",
        "A": "",
    }[kind]


# P's receipts and proofs are read right after it arrives, an oracle for its support written from
# the rows themselves, then the path runs. No behaviour program calls the library's predicate, so
# the same programs run on a library that has none.
# am[verifies a-rt-sp-boundary-1017@5b3a0e] am[verifies a-rt-sp-consumers-1017@a7097b]
def _program(kind: str, path: str) -> str:
    return f"(let* ({KINDS[kind][1]} {ROWS} {PATHS[path]}) (premise-case $p $receipts $proofs $found))"


# am[verifies a-rt-sp-consumers-1017@a7097b]
def _claim_program() -> str:
    return (f"(let* ({CLAIM_KIND} {ROWS} ($found (collapse (superpose ((ask! {CLAIM}) (sn prove {CLAIM} 1)))))) "
            "(premise-case $p $receipts $proofs $found))")


# am[verifies a-rt-sp-consumers-1017@a7097b]
def _edge_program(binding: str) -> str:
    return (f"(let* ({KINDS['believed'][1]} ($b (sn intern-ref! {CONSEQUENT} \"premise-test\")) {binding} "
            "($receipts (collapse (match &self (sn receipt $e $sigma $h) $h))) ($proofs ()) "
            f"($found (collapse (sn prove {CONSEQUENT} 2)))) (premise-case $e $receipts $proofs $found))")


# The library's predicate on each kind, beside the rows it reads.
# am[verifies a-rt-sp-boundary-1017@5b3a0e]
def _support_program(binding: str) -> str:
    return f"(let* ({binding} {ROWS} ($supported (sn supported? $p))) (premise-support $p $receipts $proofs $supported))"


# The miner's support of P's own tree, beside P's rows.
# am[verifies a-rt-miner-supported-statements-1017@1e8790]
def _count_program(binding: str) -> str:
    return f"(let* ({binding} {ROWS} ($tree {CANON}) ($count (sn support $tree))) (miner-count $p $receipts $proofs $count))"


# Every arrangement's statements, then its chains and hits, then what mine! proposes over all of them.
# am[verifies a-rt-miner-supported-statements-1017@1e8790]
def _chain_program() -> str:
    bindings, counts = [], []
    for index, arrangement in enumerate(ARRANGEMENTS):
        copula = _copula(arrangement)
        bindings += [_statement(index, position, kind, copula) for position, kind in zip(("xm", "my", "xy"), arrangement)]
        bindings.append(f'($k{index} (sn trans-chains "{copula}")) ($h{index} (sn trans-hits "{copula}"))')
        counts.append(f'("{copula}" $k{index} $h{index})')
    return (f"(let* ({' '.join(binding for binding in bindings if binding)} ($mined (collapse (sn mine! 1)))) "
            f"(miner-chains ({' '.join(counts)}) $mined))")


ROWS = ("($receipts (collapse (match &self (sn receipt $p $sigma $h) $h))) "
        "($proofs (collapse (match &self (sn proof $p $x) $x)))")
CLAIM_KIND = f'{BELIEVE_Q} ($p (sn claimify! $q "observer"))'
CASES = list(product(KINDS, PATHS))
SUPPORT = {**{kind: binding for kind, (_, binding) in KINDS.items()}, "a claim": CLAIM_KIND}
PROGRAMS = {
    **{f"{kind}, {path}": _program(kind, path) for kind, path in CASES},
    "claim": _claim_program(),
    **{f"edge: {edge}": _edge_program(binding) for edge, (_, binding) in EDGES.items()},
    **{f"support: {kind}": _support_program(binding) for kind, binding in SUPPORT.items()},
    **{f"count: {kind}": _count_program(binding) for kind, (_, binding) in COUNTED.items()},
    "chains": _chain_program(),
}


# am[verifies a-rt-sp-verify-docs-1017@7dd74f]
def _result(lines) -> str:
    found = [line for line in lines if line.startswith(("(premise-case", "(premise-support", "(miner-count", "(miner-chains"))]
    assert len(found) == 1, lines
    return found[0]


# A program's result line from the in-process engine, run once per test process.
# am[verifies a-rt-sp-verify-docs-1017@7dd74f]
@cache
def _in_process(name: str) -> str:
    batch = SnarsBatch((), frozenset(), PROGRAMS[name])
    return _result(run_snars_batch(batch, budget=RunBudget(inference_budget=None, timeout_seconds=900)).output_lines)


# Supported statements take part exactly as before. An interned one used to: a direct pair, a
# frontier step and the sweep deduced from it, the backward prover and ask! answered with it as an
# axiom, convert! converted it, and modus ponens fired on it as an antecedent. It now takes part in
# none.
# am[verifies a-rt-sp-boundary-1017@5b3a0e] am[verifies a-rt-sp-consumers-1017@a7097b] am[verifies a-integrate-snars-supported-premises-1017@5186a3]
@pytest.mark.parametrize("kind, path", CASES)
def test_a_statement_is_a_premise_exactly_when_it_is_supported(kind, path):
    _, _, receipts, proofs, found = tree(_in_process(f"{kind}, {path}"))

    assert bool(receipts or proofs) is KINDS[kind][0]
    assert bool(found) is KINDS[kind][0]


# The library's predicate says what the receipt and proof rows say, for every kind and a claim.
# am[verifies a-rt-sp-boundary-1017@5b3a0e]
@pytest.mark.parametrize("kind", SUPPORT)
def test_the_support_predicate_reads_receipts_and_proofs(kind):
    _, _, receipts, proofs, supported = tree(_in_process(f"support: {kind}"))

    assert supported == str(bool(receipts or proofs))


# A claim records who claimed what; it asserts nothing, so it is unsupported and no query answers
# with it.
# am[verifies a-rt-sp-consumers-1017@a7097b]
def test_a_claim_statement_is_unsupported_and_answers_no_query():
    _, _, receipts, proofs, found = tree(_in_process("claim"))

    assert (receipts, proofs, found) == ([], [], [])


# A stored conditional is a backward rule only when the edge itself is supported; its ends are only
# the rule's types. Before, a raw edge proved its consequent from a believed antecedent.
# am[verifies a-rt-sp-consumers-1017@a7097b]
@pytest.mark.parametrize("edge", EDGES)
def test_a_conditional_edge_is_a_backward_rule_exactly_when_it_is_supported(edge):
    _, _, receipts, _, found = tree(_in_process(f"edge: {edge}"))

    assert bool(receipts) is EDGES[edge][0]
    assert bool(found) is EDGES[edge][0]


# The miner counts P toward its own pattern once when P has a receipt or a proof, however many, and
# not at all when P is only interned.
# am[verifies a-rt-miner-supported-statements-1017@1e8790]
@pytest.mark.parametrize("kind", COUNTED)
def test_the_miner_counts_a_statement_once_exactly_when_it_is_supported(kind):
    _, _, receipts, proofs, count = tree(_in_process(f"count: {kind}"))

    assert len(receipts) + len(proofs) == COUNTED[kind][0]
    assert count == str(min(COUNTED[kind][0], 1))


# A chain counts when both its statements are supported, and closes when its direct edge is
# supported too; a statement with two receipts counts once. An edge deduced from the chain's own
# statements exists only when they could be premises, and then closes the chain as an observed one
# does: its proof is provenance, not an independent observation. mine! 1 proposes exactly the
# copulas with a hit, each with the chains and hits counted here. Before, a bare operand made a
# chain and a bare closing edge made a hit.
# am[verifies a-rt-miner-supported-statements-1017@1e8790] am[verifies a-rt-miner-derived-closing-test-1017@e23981]
@pytest.mark.parametrize("arrangement", ARRANGEMENTS, ids="-".join)
def test_the_miner_chains_and_closes_only_supported_statements(arrangement):
    _, counts, mined = tree(_in_process("chains"))
    copula = f'"{_copula(arrangement)}"'
    xm, my = (kind in ("B", "BB") for kind in arrangement[:2])
    chains = int(xm and my)
    hits = int(chains and arrangement[2] in ("B", "BB", "D"))

    assert [copula, str(chains), str(hits)] in counts
    assert [record[3:5] for record in mined if record[2] == copula] == ([[str(chains), str(hits)]] if hits else [])

"""Purpose: verify selected deontic support trees, their transport and public review boundary."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from goal_chainer.deontic_engine import DeonticOutputError, read_review_payload, run_deontic_theory
from goal_chainer.relevance import parse_packet
from goal_chainer.sexpr.codec import SexprCodec
from relevance_support import reviewed, task_control
from test_deontic_engine import CHAIN, DEFEAT, DILEMMA, ENGINE, _budget, _literal


# am[verifies a-integrate-deontic-support-trees-1019@508ecf]
def test_support_tracks_the_actual_rule_chain_and_preserves_arguments():
    run = run_deontic_theory(CHAIN, budget=_budget())
    tree = next(s for s in run.support if s.literal == _literal("O", "ship"))
    assert tree.kind == "rule" and tree.label == "r2"
    ready, = tree.premises
    assert ready.kind == "rule" and ready.label == "r1"
    fact, = ready.premises
    assert fact.kind == "fact"
    assert fact.literal == _literal("none", "score", "item", "0.5", "3", '"label"')
    assert len(run.support) == len({c.literal for c in run.conclusions} | set(run.dilemmas))


# am[verifies a-integrate-deontic-support-trees-1019@508ecf]
@pytest.mark.parametrize("theory", [DEFEAT, DILEMMA])
def test_no_positive_support_is_not_a_proof_of_negation_or_a_permission(theory):
    run = run_deontic_theory(theory, budget=_budget())
    action = "act" if theory == DEFEAT else "send_report"
    tree = next(s for s in run.support if s.literal == _literal("O", action))
    assert tree.to_dict() == {"kind": "no-proof", "literal": _literal("O", action).render()}
    assert all(c.literal != tree.literal for c in run.conclusions if c.is_provable)


# am[verifies a-integrate-deontic-support-trees-1019@508ecf]
def test_strict_support_and_a_cycle_remain_explicit():
    theory = "(given (p))\n(always aLoop (p) (p))\n(always bOut (p) (q))\n"
    run = run_deontic_theory(theory, budget=_budget())
    tree = next(s for s in run.support if s.literal == _literal("none", "q"))
    assert tree.label == "bOut"
    loop, = tree.premises
    assert loop.label == "aLoop"
    cycle, = loop.premises
    assert cycle.kind == "cycle" and cycle.literal == loop.literal


# am[verifies a-integrate-deontic-support-trees-1019@508ecf]
@pytest.mark.parametrize("support", [
    "()", "(garbage)", "((proof (lit pos none none p ()) (fact)))",
    "((proof (lit pos none none p ()) (rule r not-a-list)))",
    "((proof (lit pos none none p ()) (rule r ((wrong (lit pos none none p ()))))))",
    "((no-proof (lit pos none none other ())))",
    "((no-proof (lit pos none none p ())) (no-proof (lit pos none none p ())))",
])
def test_malformed_missing_extra_or_duplicate_support_is_refused(support):
    codec = SexprCodec()
    payload = codec.parse(f"(complete 7 100117 1 ((pd (lit pos none none p ()))) () {support})")
    with pytest.raises(DeonticOutputError):
        read_review_payload(payload, codec, ENGINE)


_LITERAL = "(lit pos none none p ())"
_LEAVES = [
    (f"(no-proof {_LITERAL})", {"kind": "no-proof", "literal": _LITERAL}),
    (f"(cycle {_LITERAL})", {"kind": "cycle", "literal": _LITERAL}),
    (f'(proof {_LITERAL} (fact "label"))', {"kind": "fact", "literal": _LITERAL, "label": '"label"'}),
]


# Every tree shape transports nested subtrees without turning labels into executable text.
# am[verifies a-integrate-deontic-support-trees-1019@508ecf]
@given(st.recursive(st.sampled_from(_LEAVES),
                    lambda children: st.lists(children, max_size=3).map(lambda xs: (
                        f"(proof {_LITERAL} (rule rule-name (" + " ".join(x[0] for x in xs) + ")))",
                        {"kind": "rule", "literal": _LITERAL, "label": "rule-name",
                         "premises": [x[1] for x in xs]})), max_leaves=20))
def test_recursive_support_transport(tree_and_expected):
    tree, expected = tree_and_expected
    codec = SexprCodec()
    payload = codec.parse(f"(complete 7 100117 1 ((pd {_LITERAL})) () ({tree}))")
    support, = read_review_payload(payload, codec, ENGINE).support
    assert support.to_dict() == expected


# am[verifies a-integrate-deontic-support-trees-1019@508ecf]
def test_public_support_is_derived_output_and_never_changes_the_fingerprint_or_authority():
    fixture = Path(__file__).parents[1] / "examples/relevance/chemistry-contention.packet.json"
    result = reviewed(task_control(), parse_packet(json.loads(fixture.read_text(encoding="utf-8"))))
    rendered = result.to_dict()
    assert rendered["deontic_support"] == [s.to_dict() for s in result.derived.deontic_support]
    assert rendered["deontic_support"]
    without = replace(result, derived=replace(result.derived, deontic_support=()))
    assert result.fingerprint == without.fingerprint
    assert result.ranking == without.ranking
    assert rendered["applies_effects"] is False
    assert rendered["proposal"]["action"] == "pause_recoverably"
    assert rendered["proposal"]["authorization"] == "unresolved"

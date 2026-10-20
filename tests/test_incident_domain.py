"""Purpose: verify that the incident domain keeps the retired incident theory's norms and its appraisal's required goals and coverage, case by recorded case."""

import json
from itertools import product
from pathlib import Path

import pytest

from goal_chainer.deontic_engine import run_deontic_theory
from goal_chainer.domains.loader import load_domain
from request_support import budget


DOMAIN_FILE = Path(__file__).parents[1] / "src/goal_chainer/domains/data/incident.metta"
DIRECTIONS = ("supported", "contradicted", "unknown")
# What the retired incident theory concluded, and its appraisal required and covered, for each reading
# case, recorded once by tests/record_incident_norm_oracle.py before both were retired, and the
# recorder left with them; its provenance names the revision, the files and the engine it was
# recorded from.
# am[verifies a-ie-s4-norm-oracle-1018@272300]
ORACLE = json.loads((Path(__file__).parent / "data" / "incident-theory-norms.json").read_text(encoding="utf-8"))
# The context literals the retired theory concluded beside its actions' norms.
CONTEXT_LITERALS = ("privacyAtStake", "factsReady")


# am[verifies a-integrate-incident-declarations-1018@89a9c1]
@pytest.fixture(scope="module")
def domain():
    return load_domain(DOMAIN_FILE, budget=budget())


# am[verifies a-integrate-incident-declarations-1018@89a9c1]
def test_the_domain_declares_the_readers_conditions_and_proposal_ceiling(domain):
    assert set(domain.signal_ids) == {p.id for p in domain.readings.propositions}
    assert {action.authority for action in domain.actions} == {"advisory"}
    assert {ceiling for _, ceiling in domain.estimator_ceilings} == {"advisory"}
    assert all(not hasattr(action, "default_strength") for action in domain.actions)


# The recorded cases are the whole case space of the domain's own sensitive categories: every
# direction of the general, public and verification readings; each category supported with the
# public and verification readings varying, since every category witnesses the same schematic rule;
# and each category denied alone, which must not become a privacy premise. A category the domain
# adds or drops would leave a case unrecorded, which this refuses.
# am[verifies a-ie-s4-norm-oracle-1018@272300] am[verifies a-integrate-incident-norm-equivalence-1018@479ae5]
def test_the_oracle_records_every_case_of_the_domains_categories(domain):
    categories = [fact.args[0] for fact in domain.facts if fact.functor == "sensitive-category"]
    expected = (
        [{"sensitive-data": s, "public-data": p, "unverified": u} for s, p, u in product(DIRECTIONS, repeat=3)]
        + [{c: "supported", "public-data": p, "unverified": u} for c in categories
           for p, u in product(DIRECTIONS, repeat=2)]
        + [{c: "contradicted"} for c in categories]
    )
    assert ORACLE["categories"] == categories
    assert sorted(map(_key, (case["readings"] for case in ORACLE["cases"]))) == sorted(map(_key, expected))


# The generic compiler names an action as (do ACTION), where the retired theory used the bare action
# literal, so each side's answers are read by the action they name.
# am[verifies a-integrate-incident-norm-equivalence-1018@479ae5]
def norm_answers(run, action_ids):
    answers = set()
    for row in run.conclusions:
        literal = row.literal
        if literal.functor == "do" and len(literal.args) == 1 and literal.args[0] in action_ids:
            name = literal.args[0]
        elif literal.functor in {*action_ids, *CONTEXT_LITERALS}:
            name = literal.functor
        else:
            continue
        answers.add((row.tag, literal.sign, literal.mode, literal.temporal, name))
    return answers


# Each case's readings reach the domain theory as the generic review supplies them: (signal ID) for a
# supported reading, its explicit contrary for a contradicted one, and nothing for an unknown one.
# am[verifies a-integrate-incident-norm-equivalence-1018@479ae5] am[verifies a-ie-s4-norm-oracle-1018@272300]
@pytest.mark.parametrize("case", ORACLE["cases"], ids=lambda case: "-".join(map("=".join, case["readings"].items())))
def test_the_domain_keeps_the_retired_theorys_norms_and_coverage(domain, case):
    facts = []
    for name, answer in case["readings"].items():
        if answer == "supported":
            facts.append(f"(given (signal {name}))")
        elif answer == "contradicted":
            facts.append(f"(given (not (signal {name})))")
    current = run_deontic_theory(domain.theory + "\n".join(facts), budget=budget())
    assert norm_answers(current, domain.action_ids) == {tuple(row) for row in case["norms"]}
    established = [row.literal for row in current.conclusions if row.is_provable]
    assert {literal.args[0] for literal in established if literal.functor == "required"} == set(case["required_goals"])
    coverage = {(literal.args[0], literal.args[1]) for literal in established if literal.functor == "contributes"}
    assert coverage == {tuple(pair) for pair in case["coverage"]}


# am[verifies a-ie-s4-norm-oracle-1018@272300]
def _key(readings):
    return tuple(sorted(readings.items()))

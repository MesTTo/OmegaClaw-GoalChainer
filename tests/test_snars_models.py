"""Purpose: test the immutable SNARS values: opinions, the evidence a caller gives SNARS and the
evidence it answers, receipts, proofs, beliefs, goals, counterfactuals, temporal values and
diagnostics."""

from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

from goal_chainer.snars_models import (
    OPINION_SUM_TOLERANCE,
    Evidence,
    EvidenceCounts,
    EvidenceReceipt,
    SnarsBelief,
    SnarsCounterfactual,
    SnarsGoal,
    SnarsProof,
    SubjectiveOpinion,
    TemporalInterval,
    TemporalOccurrence,
)


def _opinion() -> SubjectiveOpinion:
    return SubjectiveOpinion(0.6, 0.1, 0.3, 0.5)


def _belief(
    statement_id: str = "statement-1",
    *,
    proofs: tuple[SnarsProof, ...] = (),
) -> SnarsBelief:
    receipt = EvidenceReceipt("receipt-1", "request", statement_id, 0.9)
    return SnarsBelief(
        statement_id=statement_id,
        canonical_statement="(acceptable publish_summary)",
        opinion=_opinion(),
        evidence=EvidenceCounts(6.0, 1.0, 0.5),
        receipts=(receipt,),
        proofs=proofs,
        sources=("request",),
    )


def test_subjective_opinion_exposes_native_expectation_and_is_frozen():
    opinion = _opinion()

    assert opinion.expectation == pytest.approx(0.75)
    with pytest.raises(FrozenInstanceError):
        opinion.belief = 0.5


# An integer beyond the float range is no finite float either, and is refused as one rather than
# escaping float() as OverflowError.
# am[verifies a-rt-nr-repair-1018@72901e]
@pytest.mark.parametrize("field_name", ["belief", "disbelief", "uncertainty", "base_rate"])
@pytest.mark.parametrize("value", [nan, inf, -inf, 10**400, -(10**400)])
def test_subjective_opinion_rejects_nonfinite_components(field_name, value):
    values = _valid_opinion_values()
    values[field_name] = value

    with pytest.raises(ValueError, match="finite"):
        SubjectiveOpinion(**values)


@pytest.mark.parametrize("field_name", ["belief", "disbelief", "uncertainty", "base_rate"])
@pytest.mark.parametrize("value", [-0.001, 1.001])
def test_subjective_opinion_rejects_components_outside_unit_interval(field_name, value):
    values = _valid_opinion_values()
    values[field_name] = value

    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        SubjectiveOpinion(**values)


def _valid_opinion_values():
    return {
        "belief": 0.6,
        "disbelief": 0.1,
        "uncertainty": 0.3,
        "base_rate": 0.5,
    }


def test_subjective_opinion_documents_and_enforces_simplex_tolerance():
    accepted = SubjectiveOpinion(
        0.6,
        0.1,
        0.3 + OPINION_SUM_TOLERANCE / 2.0,
        0.5,
    )

    assert accepted.expectation <= 1.0
    with pytest.raises(ValueError, match="must equal 1"):
        SubjectiveOpinion(
            0.6,
            0.1,
            0.3 + OPINION_SUM_TOLERANCE * 2.0,
            0.5,
        )


def test_subjective_opinion_grid_keeps_expectation_in_unit_interval():
    for belief_tenths in range(11):
        for disbelief_tenths in range(11 - belief_tenths):
            belief = belief_tenths / 10.0
            disbelief = disbelief_tenths / 10.0
            uncertainty = (10 - belief_tenths - disbelief_tenths) / 10.0
            for base_rate_tenths in range(11):
                opinion = SubjectiveOpinion(
                    belief,
                    disbelief,
                    uncertainty,
                    base_rate_tenths / 10.0,
                )
                assert 0.0 <= opinion.expectation <= 1.0


# Evidence given to SNARS and evidence SNARS answers check their counts and rates alike.
# am[verifies a-ev-br-evidence-type-1017@81ce8a]
@pytest.mark.parametrize("kind", [Evidence, EvidenceCounts])
@pytest.mark.parametrize("field_name", ["positive", "negative"])
@pytest.mark.parametrize("value", [-1.0, nan, inf])
def test_evidence_counts_reject_invalid_counts(kind, field_name, value):
    values = {"positive": 1.0, "negative": 2.0, "base_rate": 0.5}
    values[field_name] = value

    with pytest.raises(ValueError):
        kind(**values)


# am[verifies a-ev-br-evidence-type-1017@81ce8a]
@pytest.mark.parametrize("kind", [Evidence, EvidenceCounts])
@pytest.mark.parametrize("value", [nan, inf, -0.01, 1.01])
def test_evidence_counts_reject_invalid_base_rate(kind, value):
    with pytest.raises(ValueError):
        kind(1.0, 2.0, value)


# Evidence a caller gives may leave its rate to SNARS; an answer always states the rate SNARS
# applied, and given back to SNARS it is evidence with that rate.
# am[verifies a-ev-br-evidence-type-1017@81ce8a]
def test_given_evidence_may_leave_its_rate_to_snars_and_an_answer_states_its_own():
    answer = EvidenceCounts(2.0, 1.0, 0.7)

    assert Evidence(2.0, 1.0).base_rate is None
    assert Evidence(2.0, 1.0, 0.7).base_rate == 0.7
    assert isinstance(answer, Evidence) and answer.base_rate == 0.7
    with pytest.raises(TypeError):
        EvidenceCounts(2.0, 1.0)
    with pytest.raises(TypeError):
        EvidenceCounts(2.0, 1.0, None)


@pytest.mark.parametrize("field_name", ["receipt_id", "source", "statement_id"])
@pytest.mark.parametrize("value", ["", " \t"])
def test_receipt_rejects_empty_identity_fields(field_name, value):
    values = {
        "receipt_id": "receipt-1",
        "source": "request",
        "statement_id": "statement-1",
        "trust": 1.0,
    }
    values[field_name] = value

    with pytest.raises(ValueError, match="nonempty"):
        EvidenceReceipt(**values)


@pytest.mark.parametrize("trust", [nan, inf, -0.01, 1.01])
def test_receipt_rejects_invalid_trust(trust):
    with pytest.raises(ValueError):
        EvidenceReceipt("receipt-1", "request", "statement-1", trust)


def test_belief_preserves_recursive_proof_tree():
    leaf = _belief("premise-1")
    nested = SnarsProof(
        kind="deduction",
        conclusion="intermediate",
        premises=(leaf,),
        axiom_stamps=("receipt-1",),
    )
    root = SnarsProof(
        kind="deduction",
        conclusion="result",
        premises=(nested, leaf),
        axiom_stamps=("receipt-1", "rule-1"),
    )
    belief = _belief("result", proofs=(root,))

    assert belief.proofs[0].premises == (nested, leaf)
    assert isinstance(belief.proofs[0].premises[0], SnarsProof)
    assert isinstance(belief.proofs[0].premises[1], SnarsBelief)


@pytest.mark.parametrize(
    ("constructor", "match"),
    [
        (
            lambda: SnarsProof("", "result", (), ()),
            "kind",
        ),
        (
            lambda: SnarsProof("axiom", " ", (), ()),
            "conclusion",
        ),
        (
            lambda: SnarsProof("axiom", "result", (), ("",)),
            "axiom_stamps",
        ),
        (
            lambda: _belief(" "),
            "statement_id",
        ),
    ],
)
def test_proof_and_belief_reject_empty_required_text(constructor, match):
    with pytest.raises(ValueError, match=match):
        constructor()


def test_proof_and_belief_require_immutable_typed_tuples():
    with pytest.raises(TypeError, match="premises must be a tuple"):
        SnarsProof("axiom", "result", [], ())
    with pytest.raises(TypeError, match="premises must contain"):
        SnarsProof("axiom", "result", ("not-a-proof",), ())
    with pytest.raises(TypeError, match="receipts must be a tuple"):
        SnarsBelief(
            "statement-1",
            "canonical",
            _opinion(),
            EvidenceCounts(1.0, 0.0, 0.5),
            [],
            (),
            (),
        )


def test_goal_preserves_goalchainer_metadata():
    goal = SnarsGoal(
        goal_id="goal-1",
        canonical_statement="(protect customer_data)",
        owner="ava",
        kind="individual",
        desire=0.9,
        required=True,
        source="scenario",
    )

    assert goal.desire == 0.9
    assert goal.required is True
    with pytest.raises(FrozenInstanceError):
        goal.owner = "other"


def test_counterfactual_requires_identical_before_and_after_state():
    values = {
        "hypothesis": "(public request)",
        "query": "(acceptable raw)",
        "opinion": _opinion(),
        "proofs": (),
        "state_before": "(state a)",
        "state_after": "(state a)",
        "digest_before": "digest",
        "digest_after": "digest",
    }

    assert SnarsCounterfactual(**values).state_after == "(state a)"
    with pytest.raises(ValueError, match="rolled back"):
        SnarsCounterfactual(**{**values, "state_after": "(state b)"})
    with pytest.raises(ValueError, match="digest"):
        SnarsCounterfactual(**{**values, "digest_after": "changed"})


@pytest.mark.parametrize("desire", [nan, inf, -0.01, 1.01])
def test_goal_rejects_invalid_desire(desire):
    with pytest.raises(ValueError):
        SnarsGoal("goal-1", "statement", "owner", "collective", desire, False, "scenario")


def test_goal_rejects_invalid_kind_and_required_type():
    with pytest.raises(ValueError, match="kind"):
        SnarsGoal("goal-1", "statement", "owner", "team", 0.5, False, "scenario")
    with pytest.raises(TypeError, match="required"):
        SnarsGoal("goal-1", "statement", "owner", "collective", 0.5, 1, "scenario")


def test_temporal_values_preserve_clock_and_closed_interval():
    occurrence = TemporalOccurrence("statement-1", 7, "logical")
    interval = TemporalInterval("statement-1", 7, 9, "logical")

    assert occurrence.tick == 7.0
    assert interval.start_tick == 7.0
    assert interval.end_tick == 9.0


# am[verifies a-rt-nr-repair-1018@72901e]
@pytest.mark.parametrize("value", [nan, inf, -inf, 10**400, -(10**400)])
def test_temporal_values_reject_nonfinite_ticks(value):
    with pytest.raises(ValueError, match="finite"):
        TemporalOccurrence("statement-1", value)
    with pytest.raises(ValueError, match="finite"):
        TemporalInterval("statement-1", 0.0, value)


def test_temporal_interval_rejects_reversed_bounds_and_unknown_clock():
    with pytest.raises(ValueError, match="start_tick"):
        TemporalInterval("statement-1", 2.0, 1.0)
    with pytest.raises(ValueError, match="clock"):
        TemporalOccurrence("statement-1", 1.0, "wall")


# Evidence a caller gives is refused, not overflowed, when an amount or its rate is an integer
# beyond the float range.
# am[verifies a-rt-nr-repair-1018@72901e]
def test_evidence_beyond_the_float_range_is_refused_as_not_finite():
    with pytest.raises(ValueError, match="positive must be finite"):
        Evidence(10**400, 0.0)
    with pytest.raises(ValueError, match="base_rate must be finite"):
        Evidence(1.0, 0.0, 10**400)

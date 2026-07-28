from dataclasses import FrozenInstanceError
from math import inf, nan
from pathlib import Path

import pytest

from goal_chainer.snars_models import (
    OPINION_SUM_TOLERANCE,
    EvidenceCounts,
    EvidenceReceipt,
    RuntimeDiagnostics,
    SnarsActionAssessment,
    SnarsBelief,
    SnarsCounterfactual,
    SnarsDependencyUnavailableError,
    SnarsError,
    SnarsGoal,
    SnarsInvalidInputError,
    SnarsPersistenceError,
    SnarsPettaExecutionError,
    SnarsProof,
    SnarsProtocolError,
    SnarsRequestContext,
    SnarsTimeoutError,
    SnarsUnsupportedCapabilityError,
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


@pytest.mark.parametrize("field_name", ["belief", "disbelief", "uncertainty", "base_rate"])
@pytest.mark.parametrize("value", [nan, inf, -inf])
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


@pytest.mark.parametrize("field_name", ["positive", "negative"])
@pytest.mark.parametrize("value", [-1.0, nan, inf])
def test_evidence_counts_reject_invalid_counts(field_name, value):
    values = {"positive": 1.0, "negative": 2.0, "base_rate": 0.5}
    values[field_name] = value

    with pytest.raises(ValueError):
        EvidenceCounts(**values)


@pytest.mark.parametrize("value", [nan, inf, -0.01, 1.01])
def test_evidence_counts_reject_invalid_base_rate(value):
    with pytest.raises(ValueError):
        EvidenceCounts(1.0, 2.0, value)


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


def test_action_assessment_preserves_native_beliefs_and_conflict():
    assessment = SnarsActionAssessment(
        "publish_raw_log",
        _belief("acceptable"),
        _belief("risky"),
        _belief("forbidden"),
        0.25,
    )

    assert assessment.acceptable.opinion.expectation == pytest.approx(0.75)
    assert assessment.conflict_degree == 0.25


def test_request_context_requires_four_native_beliefs():
    context = SnarsRequestContext(
        sensitive=_belief("sensitive"),
        public=_belief("public"),
        unverified=_belief("unverified"),
        coordination=_belief("coordination"),
    )

    assert context.public.statement_id == "public"
    with pytest.raises(TypeError, match="coordination"):
        SnarsRequestContext(
            sensitive=_belief("sensitive"),
            public=_belief("public"),
            unverified=_belief("unverified"),
            coordination="invalid",
        )


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


@pytest.mark.parametrize("conflict", [-0.01, 1.01, nan, inf])
def test_action_assessment_rejects_invalid_conflict(conflict):
    with pytest.raises(ValueError):
        SnarsActionAssessment(
            "publish_raw_log",
            _belief("acceptable"),
            _belief("risky"),
            _belief("forbidden"),
            conflict,
        )


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


@pytest.mark.parametrize("value", [nan, inf, -inf])
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


def test_runtime_diagnostics_carries_resolved_paths_and_revision():
    diagnostics = RuntimeDiagnostics(
        mettabase_dir=Path("/deps/mettabase"),
        mettabase_commit="5da3c47",
        snars_program=Path("/deps/mettabase/lib/mettabase/snars.metta"),
        snars_kernel=Path("/deps/mettabase/lib/mettabase/snars/kernel.pl"),
        hyperbase_program=Path("/deps/mettabase/lib/mettabase/hyperbase.metta"),
        petta_dir=Path("/deps/petta"),
        petta_main=Path("/deps/petta/src/main.pl"),
        swipl=Path("/bin/swipl"),
        python_package=Path("/deps/mettabase/src/mettabase"),
    )

    assert diagnostics.mettabase_commit == "5da3c47"
    assert diagnostics.petta_main == Path("/deps/petta/src/main.pl")
    assert diagnostics.python_package == Path("/deps/mettabase/src/mettabase")


def test_runtime_diagnostics_rejects_empty_revision_and_non_path_fields():
    values = {
        "mettabase_dir": Path("/deps/mettabase"),
        "mettabase_commit": "5da3c47",
        "snars_program": Path("/deps/mettabase/lib/mettabase/snars.metta"),
        "snars_kernel": Path("/deps/mettabase/lib/mettabase/snars/kernel.pl"),
        "hyperbase_program": Path("/deps/mettabase/lib/mettabase/hyperbase.metta"),
        "petta_dir": Path("/deps/petta"),
        "petta_main": Path("/deps/petta/src/main.pl"),
        "swipl": Path("/bin/swipl"),
    }
    with pytest.raises(ValueError, match="mettabase_commit"):
        RuntimeDiagnostics(**{**values, "mettabase_commit": " "})
    with pytest.raises(TypeError, match="swipl"):
        RuntimeDiagnostics(**{**values, "swipl": "/bin/swipl"})


@pytest.mark.parametrize(
    ("error_type", "code"),
    [
        (SnarsDependencyUnavailableError, "dependency_unavailable"),
        (SnarsInvalidInputError, "invalid_input"),
        (SnarsTimeoutError, "timeout"),
        (SnarsProtocolError, "protocol_error"),
        (SnarsPettaExecutionError, "petta_execution_error"),
        (SnarsPersistenceError, "persistence_error"),
        (
            SnarsUnsupportedCapabilityError,
            "unsupported_design_only_capability",
        ),
    ],
)
def test_snars_error_hierarchy_has_stable_codes_and_details(error_type, code):
    error = error_type("operation failed", details={"operation": "ask"})

    assert isinstance(error, SnarsError)
    assert str(error) == "operation failed"
    assert error.to_dict() == {
        "code": code,
        "message": "operation failed",
        "details": {"operation": "ask"},
    }
    with pytest.raises(TypeError):
        error.details["operation"] = "prove"


def test_snars_error_copies_details_and_rejects_empty_messages():
    details = {"path": "/missing"}
    error = SnarsDependencyUnavailableError("runtime missing", details=details)
    details["path"] = "/changed"

    assert error.details["path"] == "/missing"
    with pytest.raises(ValueError, match="message"):
        SnarsError(" ")

"""Negative test matrix for the GoalChainer → ThreadKeeper adapter validator.

Covers the GGB Gate 1 "Goal/task adapter conformance" requirements:
  * unknown status
  * duplicate / empty action ID
  * forbidden-high-score action (forbidden norm with high score still blocked)
  * missing evidence
  * malformed score
  * malformed norm status
  * batch duplicate detection
  * non-dict decision
  * contract mapping returns None for all non-queue-eligible decisions

All tests are artifact-only: no provider, live queue, Telegram, runtime bridge,
memory write, or authority change.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure src is on path
GOALCHAINER_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(GOALCHAINER_SRC))

from goal_chainer.goal_task_adapter_validator import (  # noqa: E402
    validate_decision,
    validate_batch,
    validated_decision_to_contract,
    BatchValidation,
    DecisionValidation,
    KNOWN_STATUSES,
    KNOWN_NORM_STATUSES,
    QUEUE_ELIGIBLE_STATUSES,
    QUEUE_EXCLUDED_STATUSES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _good_decision(
    action_id: str = "publish_redacted_summary",
    status: str = "recommended",
    norm: str = "obliged",
    score: float = 0.95,
    proofs: tuple[str, ...] = ("fixture-proof-1",),
) -> dict:
    """Return a well-formed decision dict."""
    return {
        "action_id": action_id,
        "label": action_id,
        "status": status,
        "score": score,
        "norm_status": norm,
        "evidence": {"proofs": list(proofs)},
        "missing_required_goals": [],
        "norm_reasons": [],
    }


# ---------------------------------------------------------------------------
# Positive tests (baseline)
# ---------------------------------------------------------------------------

class TestPositiveBaseline:
    def test_valid_recommended_decision(self):
        d = _good_decision()
        v = validate_decision(d)
        assert v.valid
        assert v.queue_eligible
        assert len(v.errors) == 0

    def test_valid_candidate_decision(self):
        v = validate_decision(_good_decision(status="candidate"))
        assert v.valid
        assert v.queue_eligible

    def test_held_is_valid_but_not_queued(self):
        v = validate_decision(_good_decision(status="held"))
        assert v.valid
        assert not v.queue_eligible

    def test_weak_is_valid_but_not_queued(self):
        v = validate_decision(_good_decision(status="weak"))
        assert v.valid
        assert not v.queue_eligible

    def test_blocked_is_valid_but_not_queued(self):
        v = validate_decision(_good_decision(status="blocked"))
        assert v.valid
        assert not v.queue_eligible


# ---------------------------------------------------------------------------
# Unknown status
# ---------------------------------------------------------------------------

class TestUnknownStatus:
    def test_unknown_status_fails_closed(self):
        d = _good_decision(status="approved")
        v = validate_decision(d)
        assert not v.valid
        assert not v.queue_eligible
        assert any("unknown status" in e for e in v.errors)

    def test_empty_status_fails_closed(self):
        d = _good_decision(status="")
        v = validate_decision(d)
        assert not v.valid
        assert not v.queue_eligible

    def test_none_status_fails_closed(self):
        d = _good_decision()
        d["status"] = None
        v = validate_decision(d)
        assert not v.valid

    def test_numeric_status_fails_closed(self):
        d = _good_decision()
        d["status"] = 42
        v = validate_decision(d)
        assert not v.valid


# ---------------------------------------------------------------------------
# Empty / missing action ID
# ---------------------------------------------------------------------------

class TestEmptyActionID:
    def test_empty_action_id_fails_closed(self):
        d = _good_decision(action_id="")
        v = validate_decision(d)
        assert not v.valid
        assert any("action_id is empty" in e for e in v.errors)

    def test_whitespace_action_id_fails_closed(self):
        d = _good_decision(action_id="   ")
        v = validate_decision(d)
        assert not v.valid
        assert any("action_id is empty" in e for e in v.errors)

    def test_missing_action_id_fails_closed(self):
        d = _good_decision()
        del d["action_id"]
        v = validate_decision(d)
        assert not v.valid
        assert any("missing required field: action_id" in e for e in v.errors)


# ---------------------------------------------------------------------------
# Duplicate action IDs
# ---------------------------------------------------------------------------

class TestDuplicateActionID:
    def test_duplicate_in_batch_detected(self):
        decisions = [
            _good_decision(action_id="act_a"),
            _good_decision(action_id="act_b"),
            _good_decision(action_id="act_a"),  # duplicate
        ]
        bv = validate_batch(decisions)
        assert bv.invalid_count >= 1
        assert any("duplicate action_id" in e for e in bv.batch_errors)

    def test_duplicate_marked_invalid_in_results(self):
        decisions = [
            _good_decision(action_id="act_a"),
            _good_decision(action_id="act_a"),
        ]
        bv = validate_batch(decisions)
        # First is valid, second is invalid
        assert bv.results[0].valid
        assert not bv.results[1].valid
        assert any("duplicate" in e for e in bv.results[1].errors)

    def test_unique_batch_all_valid(self):
        decisions = [
            _good_decision(action_id="act_a"),
            _good_decision(action_id="act_b"),
            _good_decision(action_id="act_c"),
        ]
        bv = validate_batch(decisions)
        assert bv.valid_count == 3
        assert bv.invalid_count == 0
        assert len(bv.batch_errors) == 0


# ---------------------------------------------------------------------------
# Forbidden high-score action
# ---------------------------------------------------------------------------

class TestForbiddenHighScore:
    def test_forbidden_norm_blocks_queueing_with_high_score(self):
        d = _good_decision(
            action_id="publish_raw_log",
            status="recommended",
            norm="forbidden",
            score=0.99,
        )
        v = validate_decision(d)
        assert v.valid  # shape is valid
        assert not v.queue_eligible  # but forbidden blocks queueing
        assert any("forbidden" in w for w in v.warnings)

    def test_forbidden_candidate_not_queued(self):
        d = _good_decision(
            action_id="dangerous_action",
            status="candidate",
            norm="forbidden",
            score=0.8,
        )
        v = validate_decision(d)
        assert v.valid
        assert not v.queue_eligible

    def test_forbidden_with_max_score_still_blocked(self):
        d = _good_decision(norm="forbidden", score=1.0)
        v = validate_decision(d)
        assert v.valid
        assert not v.queue_eligible

    def test_contract_none_for_forbidden(self):
        d = _good_decision(norm="forbidden")
        assert validated_decision_to_contract(d) is None


# ---------------------------------------------------------------------------
# Missing evidence
# ---------------------------------------------------------------------------

class TestMissingEvidence:
    def test_missing_evidence_field(self):
        d = _good_decision()
        del d["evidence"]
        v = validate_decision(d)
        assert not v.valid
        assert any("evidence is missing" in e for e in v.errors)

    def test_none_evidence(self):
        d = _good_decision()
        d["evidence"] = None
        v = validate_decision(d)
        assert not v.valid

    def test_empty_proofs(self):
        d = _good_decision()
        d["evidence"] = {"proofs": []}
        v = validate_decision(d)
        assert not v.valid
        assert any("proofs is empty" in e for e in v.errors)

    def test_missing_proofs(self):
        d = _good_decision()
        d["evidence"] = {}
        v = validate_decision(d)
        assert not v.valid
        assert any("proofs is missing" in e for e in v.errors)

    def test_evidence_not_dict(self):
        d = _good_decision()
        d["evidence"] = "just a string"
        v = validate_decision(d)
        assert not v.valid


# ---------------------------------------------------------------------------
# Malformed score
# ---------------------------------------------------------------------------

class TestMalformedScore:
    def test_score_above_one(self):
        v = validate_decision(_good_decision(score=1.5))
        assert not v.valid
        assert any("outside" in e for e in v.errors)

    def test_score_below_zero(self):
        v = validate_decision(_good_decision(score=-0.1))
        assert not v.valid

    def test_score_infinite(self):
        v = validate_decision(_good_decision(score=float("inf")))
        assert not v.valid
        assert any("not finite" in e for e in v.errors)

    def test_score_nan(self):
        v = validate_decision(_good_decision(score=float("nan")))
        assert not v.valid
        assert any("not finite" in e for e in v.errors)

    def test_score_string(self):
        d = _good_decision()
        d["score"] = "0.9"
        v = validate_decision(d)
        assert not v.valid

    def test_score_missing(self):
        d = _good_decision()
        del d["score"]
        v = validate_decision(d)
        assert not v.valid


# ---------------------------------------------------------------------------
# Malformed norm status
# ---------------------------------------------------------------------------

class TestMalformedNorm:
    def test_unknown_norm_status(self):
        d = _good_decision(norm="encouraged")
        v = validate_decision(d)
        assert not v.valid
        assert any("unknown norm_status" in e for e in v.errors)

    def test_empty_norm_status(self):
        d = _good_decision(norm="")
        v = validate_decision(d)
        assert not v.valid


# ---------------------------------------------------------------------------
# Non-dict decisions
# ---------------------------------------------------------------------------

class TestNonDictDecision:
    def test_string_input_fails_closed(self):
        v = validate_decision("not a dict")  # type: ignore
        assert not v.valid

    def test_none_input_fails_closed(self):
        v = validate_decision(None)  # type: ignore
        assert not v.valid

    def test_list_input_fails_closed(self):
        v = validate_decision([1, 2, 3])  # type: ignore
        assert not v.valid

    def test_batch_with_non_dict(self):
        bv = validate_batch([_good_decision(), "not a dict", _good_decision(action_id="b")])
        assert bv.invalid_count >= 1
        assert not bv.results[1].valid


# ---------------------------------------------------------------------------
# Contract mapping
# ---------------------------------------------------------------------------

class TestContractMapping:
    def test_valid_recommended_produces_contract(self):
        d = _good_decision()
        contract = validated_decision_to_contract(d)
        assert contract is not None
        assert contract["requires_adjudication"] is True
        assert contract["patch_proposal_only"] is True
        assert "publish_redacted_summary" in contract["objective"]

    def test_held_produces_no_contract(self):
        d = _good_decision(status="held")
        assert validated_decision_to_contract(d) is None

    def test_weak_produces_no_contract(self):
        d = _good_decision(status="weak")
        assert validated_decision_to_contract(d) is None

    def test_blocked_produces_no_contract(self):
        d = _good_decision(status="blocked")
        assert validated_decision_to_contract(d) is None

    def test_invalid_produces_no_contract(self):
        d = _good_decision()
        d["status"] = "unknown"
        assert validated_decision_to_contract(d) is None

    def test_forbidden_produces_no_contract(self):
        d = _good_decision(norm="forbidden")
        assert validated_decision_to_contract(d) is None

    def test_contract_has_done_criteria_from_proofs(self):
        d = _good_decision(proofs=("proof_a", "proof_b"))
        contract = validated_decision_to_contract(d)
        assert contract is not None
        assert len(contract["done_criteria"]) == 2
        assert "proof_a" in contract["done_criteria"][0]

    def test_contract_empty_proofs_falls_back_to_action_id(self):
        d = _good_decision()
        d["evidence"]["proofs"] = []
        # This decision should fail validation (empty proofs)
        v = validate_decision(d)
        assert not v.valid
        # And contract mapping returns None
        assert validated_decision_to_contract(d) is None


# ---------------------------------------------------------------------------
# Batch summary
# ---------------------------------------------------------------------------

class TestBatchSummary:
    def test_mixed_batch_counts(self):
        decisions = [
            _good_decision(action_id="a"),               # valid, queue-eligible
            _good_decision(action_id="b", status="held"), # valid, not queued
            _good_decision(action_id=""),                  # invalid
            _good_decision(action_id="d", norm="forbidden"),  # valid, not queued (forbidden)
            "not a dict",                                  # invalid
        ]
        bv = validate_batch(decisions)
        assert bv.valid_count == 3  # a, b, d
        assert bv.invalid_count == 2  # empty id, non-dict
        assert bv.queue_eligible_count == 1  # only a

    def test_empty_batch(self):
        bv = validate_batch([])
        assert bv.valid_count == 0
        assert bv.invalid_count == 0
        assert bv.queue_eligible_count == 0
        assert len(bv.batch_errors) == 0


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------

class TestConstants:
    def test_known_statuses_partition(self):
        assert QUEUE_ELIGIBLE_STATUSES | QUEUE_EXCLUDED_STATUSES == KNOWN_STATUSES
        assert QUEUE_ELIGIBLE_STATUSES & QUEUE_EXCLUDED_STATUSES == frozenset()

    def test_forbidden_is_known_norm(self):
        assert "forbidden" in KNOWN_NORM_STATUSES

"""Tests for the petta-memory → heuristic belief grader bridge.

These tests verify that promoted petta-memory evidence packets can be fed
as read-only inputs to the heuristic PLN belief grader, adjusting the
keyword-derived ground facts via subjective-logic fusion.

Covers:
- parse_memory_evidence: STV and EC atom parsing
- grade_beliefs_heuristic_with_memory: belief adjustment from memory items
- No-memory baseline equivalence
- Multiple memory items for the same action
- reason_over_hyperbase with memory_items passthrough
- solve_incident end-to-end with memory_items
"""

from __future__ import annotations

import os

import pytest

from goal_chainer.evidence import extract_evidence
from goal_chainer.heuristic_beliefs import (
    MemoryEvidenceItem,
    grade_beliefs_heuristic,
    grade_beliefs_heuristic_with_memory,
    parse_memory_evidence,
)
from goal_chainer.pipeline import solve_incident


PII_REQUEST = (
    "Checkout is down. Engineering wants to paste raw logs into the incident room. "
    "Support says the logs may include customer emails, order IDs, and request payloads."
)

PUBLIC_REQUEST = (
    "The outage is resolved. There is no sensitive data in this status, it is safe to "
    "share publicly with engineering and support."
)


def _stv_item(action: str, strength: float, confidence: float) -> dict:
    return {
        "goalchainer_slot": "acceptability-belief-evidence",
        "belief_id": f"b-{action}",
        "cluster_id": "mc-test",
        "promotion_event": f"pe-{action}",
        "promotion_domain": "incident-response",
        "source_kind": "pettachainer-stv-statement",
        "atom": f"(: b-{action} (Acceptable {action}) (STV {strength} {confidence}))",
        "boundary": "read-only evidence for appraisal; not a directive or task claim",
    }


def _ec_item(action: str, support: float, opposition: float) -> dict:
    return {
        "goalchainer_slot": "contextual-appraisal-evidence",
        "belief_id": f"b-{action}",
        "cluster_id": "mc-test",
        "promotion_event": f"pe-{action}",
        "promotion_domain": "incident-response",
        "source_kind": "pettachainer-evidence-packet",
        "atom": (
            f"(EvidencePacket (Acceptable {action}) (EC {support} {opposition}) "
            f"((domain incident-response) (promotion-rule explicit-smoke)) pe-{action})"
        ),
        "boundary": "read-only evidence for appraisal; not a directive or task claim",
    }


# ---------------------------------------------------------------------------
# parse_memory_evidence tests
# ---------------------------------------------------------------------------

class TestParseMemoryEvidence:
    def test_parse_stv_item(self):
        items = [_stv_item("publish_redacted_summary", 0.91, 0.74)]
        parsed = parse_memory_evidence(items)
        assert len(parsed) == 1
        assert parsed[0].action_id == "publish_redacted_summary"
        assert parsed[0].source == "stv"
        assert parsed[0].strength == pytest.approx(0.91)
        assert parsed[0].confidence == pytest.approx(0.74)
        assert parsed[0].belief_id == "b-publish_redacted_summary"

    def test_parse_ec_item(self):
        items = [_ec_item("publish_redacted_summary", 9, 1)]
        parsed = parse_memory_evidence(items)
        assert len(parsed) == 1
        assert parsed[0].action_id == "publish_redacted_summary"
        assert parsed[0].source == "ec"
        assert parsed[0].strength == pytest.approx(0.9)
        assert parsed[0].confidence == pytest.approx(10 / 12)

    def test_parse_mixed_items(self):
        items = [
            _stv_item("publish_redacted_summary", 0.91, 0.74),
            _ec_item("publish_raw_log", 1, 9),
        ]
        parsed = parse_memory_evidence(items)
        assert len(parsed) == 2
        actions = {p.action_id for p in parsed}
        assert actions == {"publish_redacted_summary", "publish_raw_log"}

    def test_parse_skips_unparseable(self):
        items = [
            {"goalchainer_slot": "acceptability-belief-evidence", "atom": "not a valid atom"},
            {"goalchainer_slot": "unknown-slot", "atom": "(Acceptable foo) (STV 0.5 0.5)"},
            "not a dict",
        ]
        parsed = parse_memory_evidence(items)
        assert len(parsed) == 0

    def test_parse_ec_zero_total_skipped(self):
        items = [_ec_item("publish_redacted_summary", 0, 0)]
        parsed = parse_memory_evidence(items)
        assert len(parsed) == 0

    def test_parse_stv_clamped(self):
        items = [_stv_item("publish_redacted_summary", 1.5, -0.2)]
        parsed = parse_memory_evidence(items)
        assert len(parsed) == 1
        assert parsed[0].strength == 1.0
        assert parsed[0].confidence == 0.0


# ---------------------------------------------------------------------------
# grade_beliefs_heuristic_with_memory tests
# ---------------------------------------------------------------------------

class TestGradeBeliefsHeuristicWithMemory:
    def test_no_memory_items_matches_baseline(self):
        evidence = extract_evidence(PII_REQUEST)
        base_beliefs, _, _ = grade_beliefs_heuristic(evidence)
        mem_beliefs, _, _ = grade_beliefs_heuristic_with_memory(evidence, None)
        assert set(base_beliefs.keys()) == set(mem_beliefs.keys())
        for action_id in base_beliefs:
            assert mem_beliefs[action_id].strength == pytest.approx(base_beliefs[action_id].strength)
            assert mem_beliefs[action_id].confidence == pytest.approx(base_beliefs[action_id].confidence)

    def test_empty_memory_list_matches_baseline(self):
        evidence = extract_evidence(PII_REQUEST)
        base_beliefs, _, _ = grade_beliefs_heuristic(evidence)
        mem_beliefs, _, _ = grade_beliefs_heuristic_with_memory(evidence, [])
        for action_id in base_beliefs:
            assert mem_beliefs[action_id].strength == pytest.approx(base_beliefs[action_id].strength)

    def test_stv_memory_adjusts_belief(self):
        """A strong STV memory item for publish_redacted_summary should
        shift the belief compared to keyword-only baseline."""
        evidence = extract_evidence(PII_REQUEST)
        base_beliefs, _, _ = grade_beliefs_heuristic(evidence)

        # Feed a strong memory item that agrees with the keyword evidence.
        items = [_stv_item("publish_redacted_summary", 0.99, 0.95)]
        mem_beliefs, program, outputs = grade_beliefs_heuristic_with_memory(evidence, items)

        # The memory-adjusted belief should be different from the baseline
        # (fusion of additional evidence changes the result).
        redacted_base = base_beliefs["publish_redacted_summary"]
        redacted_mem = mem_beliefs["publish_redacted_summary"]
        assert redacted_mem.strength != pytest.approx(redacted_base.strength, abs=1e-6)
        # With a strong positive memory item, strength should be pulled toward it.
        assert redacted_mem.strength > redacted_base.strength - 0.05
        # Program should mention memory evidence.
        assert "memory" in program.lower()

    def test_ec_memory_adjusts_belief(self):
        """An EC packet with high support should strengthen the belief."""
        evidence = extract_evidence(PII_REQUEST)
        base_beliefs, _, _ = grade_beliefs_heuristic(evidence)

        items = [_ec_item("publish_redacted_summary", 19, 1)]
        mem_beliefs, _, outputs = grade_beliefs_heuristic_with_memory(evidence, items)

        redacted_mem = mem_beliefs["publish_redacted_summary"]
        assert redacted_mem.proof
        assert "memory" in redacted_mem.proof

    def test_conflicting_memory_lowers_strength(self):
        """An STV memory item with low strength should pull belief down."""
        evidence = extract_evidence(PII_REQUEST)
        base_beliefs, _, _ = grade_beliefs_heuristic(evidence)

        items = [_stv_item("publish_redacted_summary", 0.1, 0.9)]
        mem_beliefs, _, _ = grade_beliefs_heuristic_with_memory(evidence, items)

        redacted_base = base_beliefs["publish_redacted_summary"]
        redacted_mem = mem_beliefs["publish_redacted_summary"]
        # A low-strength memory item should pull the overall strength down.
        assert redacted_mem.strength < redacted_base.strength

    def test_memory_for_unsupported_action_creates_ground(self):
        """Memory evidence for an action with no keyword grounds still produces
        a belief (from the memory ground alone)."""
        evidence = extract_evidence(PUBLIC_REQUEST)  # no privacy risk

        # In the public case, publish_raw_log gets support_to_accept grounds.
        # Feed a conflicting memory item.
        items = [_stv_item("publish_raw_log", 0.05, 0.95)]
        mem_beliefs, _, _ = grade_beliefs_heuristic_with_memory(evidence, items)

        raw_belief = mem_beliefs["publish_raw_log"]
        # The low-strength memory item should pull strength down from baseline.
        assert raw_belief.strength < 0.95

    def test_multiple_memory_items_fused(self):
        """Multiple memory items for the same action are fused together."""
        evidence = extract_evidence(PII_REQUEST)
        items = [
            _stv_item("publish_redacted_summary", 0.99, 0.9),
            _ec_item("publish_redacted_summary", 19, 1),
        ]
        mem_beliefs, program, _ = grade_beliefs_heuristic_with_memory(evidence, items)

        redacted = mem_beliefs["publish_redacted_summary"]
        # Same provenance (helpers mint identical ids): dedup keeps the STV
        # representative; the EC ground must not double-count.
        assert "memory_stv" in redacted.proof
        assert "memory_ec" not in redacted.proof
        assert "memory" in program.lower()

    def test_proof_tags_memory_evidence(self):
        evidence = extract_evidence(PII_REQUEST)
        items = [_stv_item("publish_redacted_summary", 0.91, 0.74)]
        mem_beliefs, _, _ = grade_beliefs_heuristic_with_memory(evidence, items)

        proof = mem_beliefs["publish_redacted_summary"].proof
        assert "memory_stv" in proof
        assert "+memory" in proof


# ---------------------------------------------------------------------------
# reason_over_hyperbase with memory_items passthrough
# ---------------------------------------------------------------------------

class TestReasonOverHyperbaseWithMemory:
    def test_memory_items_adjust_beliefs_in_reasoner(self):
        from goal_chainer.metta_reasoner import reason_over_hyperbase

        evidence = extract_evidence(PII_REQUEST)
        base_result = reason_over_hyperbase((), evidence)
        base_strength = next(
            item["strength"] for item in base_result["action_evidence"]
            if item["action_id"] == "publish_redacted_summary"
        )

        items = [_stv_item("publish_redacted_summary", 0.1, 0.9)]
        mem_result = reason_over_hyperbase((), evidence, memory_items=items)
        mem_strength = next(
            item["strength"] for item in mem_result["action_evidence"]
            if item["action_id"] == "publish_redacted_summary"
        )

        assert mem_strength < base_strength
        assert "memory" in mem_result.get("input", "")

    def test_no_memory_items_matches_baseline_reasoner(self):
        from goal_chainer.metta_reasoner import reason_over_hyperbase

        evidence = extract_evidence(PII_REQUEST)
        base_result = reason_over_hyperbase((), evidence)
        no_mem_result = reason_over_hyperbase((), evidence, memory_items=None)

        for base_item, no_mem_item in zip(
            base_result["action_evidence"],
            no_mem_result["action_evidence"],
        ):
            assert base_item["strength"] == pytest.approx(no_mem_item["strength"])
            assert base_item["confidence"] == pytest.approx(no_mem_item["confidence"])


# ---------------------------------------------------------------------------
# solve_incident end-to-end with memory_items
# ---------------------------------------------------------------------------

class TestSolveIncidentWithMemory:
    def test_solve_incident_with_memory_items_produces_correct_decision(self):
        # Force heuristic path
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            items = [_stv_item("publish_redacted_summary", 0.99, 0.95)]
            result = solve_incident(PII_REQUEST, memory_items=items)

            assert result["decided"] == "publish_redacted_summary"
            assert result["status"] == "recommended"
            # Raw log should be blocked by deontic regardless of memory.
            raw_log = next(
                d for d in result["decisions"] if d["action_id"] == "publish_raw_log"
            )
            assert raw_log["status"] == "blocked"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_solve_incident_conflicting_memory_still_correct_decision(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            # Even with a conflicting low-strength item for redacted summary,
            # the deontic layer should still block raw_log and the decision
            # should remain publish_redacted_summary.
            items = [_stv_item("publish_redacted_summary", 0.1, 0.5)]
            result = solve_incident(PII_REQUEST, memory_items=items)

            assert result["decided"] == "publish_redacted_summary"
            raw_log = next(
                d for d in result["decisions"] if d["action_id"] == "publish_raw_log"
            )
            assert raw_log["status"] == "blocked"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]





import unittest
import goal_chainer.heuristic_beliefs as heuristic_beliefs
from goal_chainer.evidence import IncidentEvidence

class TestProvenanceDedup(unittest.TestCase):
    """Duplicate provenance items must not be fused as independent evidence."""

    def _incident(self):
        return extract_evidence(PII_REQUEST)

    def _cache_item(self, slot, atom, **meta):
        item = {"goalchainer_slot": slot, "atom": atom}
        item.update(meta)
        return item

    def test_stv_ec_same_belief_id_deduplicate(self):
        items = [
            self._cache_item(
                "acceptability-belief-evidence",
                "(Acceptable publish_redacted_summary) (STV 0.9100 0.7400)",
                belief_id="b-shared"),
            self._cache_item(
                "contextual-appraisal-evidence",
                "(EvidencePacket (Acceptable publish_redacted_summary) (EC 9.0 1.0))",
                belief_id="b-shared"),
        ]
        parsed_stv = heuristic_beliefs.parse_memory_evidence(items)
        deduped = heuristic_beliefs._dedup_provenance(parsed_stv)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].source, "stv")
        self.assertEqual(deduped[0].strength, 0.91)
        self.assertEqual(deduped[0].confidence, 0.74)

    def test_distinct_belief_ids_not_deduplicated(self):
        items = [
            self._cache_item(
                "acceptability-belief-evidence",
                "(Acceptable publish_redacted_summary) (STV 0.9100 0.7400)",
                belief_id="b-one"),
            self._cache_item(
                "acceptability-belief-evidence",
                "(Acceptable publish_redacted_summary) (STV 0.6000 0.5000)",
                belief_id="b-two"),
        ]
        parsed = heuristic_beliefs.parse_memory_evidence(items)
        deduped = heuristic_beliefs._dedup_provenance(parsed)
        self.assertEqual(len(deduped), 2)

    def test_cluster_plus_promotion_event_key(self):
        items = [
            self._cache_item(
                "acceptability-belief-evidence",
                "(Acceptable publish_raw_log) (STV 0.2000 0.8000)",
                cluster_id="mc-1", promotion_event="pe-1"),
            self._cache_item(
                "contextual-appraisal-evidence",
                "(EvidencePacket (Acceptable publish_raw_log) (EC 2.0 8.0))",
                cluster_id="mc-1", promotion_event="pe-1"),
        ]
        parsed = heuristic_beliefs.parse_memory_evidence(items)
        deduped = heuristic_beliefs._dedup_provenance(parsed)
        self.assertEqual(len(deduped), 1)

    def test_end_to_end_dedup_equals_stv_only(self):
        """Dup provenance cache (STV+EC same belief_id) must fuse identically to
        the STV item alone; naive fusion double-counts toward ~0.998 confidence."""
        stv_item = self._cache_item(
            "acceptability-belief-evidence",
            "(Acceptable publish_redacted_summary) (STV 0.9100 0.7400)",
            belief_id="b-dup")
        ec_item = self._cache_item(
            "contextual-appraisal-evidence",
            "(EvidencePacket (Acceptable publish_redacted_summary) (EC 9.0 1.0))",
            belief_id="b-dup")
        evidence = self._incident()

        dup_beliefs, _, _ = heuristic_beliefs.grade_beliefs_heuristic_with_memory(
            evidence, [stv_item, ec_item])
        stv_only_beliefs, _, _ = heuristic_beliefs.grade_beliefs_heuristic_with_memory(
            evidence, [stv_item])
        naive_beliefs, _, _ = heuristic_beliefs.grade_beliefs_heuristic_with_memory(
            evidence, [stv_item, dict(ec_item, belief_id="b-other")])

        self.assertAlmostEqual(
            dup_beliefs["publish_redacted_summary"].confidence,
            stv_only_beliefs["publish_redacted_summary"].confidence, places=6)
        self.assertLess(
            dup_beliefs["publish_redacted_summary"].confidence,
            naive_beliefs["publish_redacted_summary"].confidence)

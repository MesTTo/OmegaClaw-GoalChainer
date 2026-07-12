"""Multi-scenario smoke for the GoalChainer memory-evidence bridge.

Verifies that the heuristic belief grader with petta-memory evidence produces
differentiated decisions across diverse incident types and conflicting memory
evidence packets. This is the next gate after the initial memory-evidence
bridge gate (20260706-goalchainer-memory-evidence-bridge).

Scenarios tested:
1. PII incident (privacy at stake, facts ready) — baseline, no memory
2. Public data (no sensitive data, facts ready) — raw log not blocked
3. Unverified facts (privacy at stake, facts not ready) — hold preferred
4. Public + unverified (no privacy, facts not ready) — raw log recommended
5. Conflicting memory: PII scenario with memory saying raw log is acceptable
6. Conflicting memory: PII scenario with memory saying redacted is bad
7. Conflicting memory: public scenario with memory saying raw log is excellent
8. Conflicting memory: unverified scenario with memory boosting hold

Each scenario asserts:
- The deontic layer correctly blocks/permits actions
- The belief strengths differ across scenarios
- Memory evidence shifts beliefs in the expected direction
- The final decision is correct for the scenario's evidence+memory combination
"""

from __future__ import annotations

import os

import pytest

from goal_chainer.evidence import extract_evidence
from goal_chainer.heuristic_beliefs import (
    grade_beliefs_heuristic,
    grade_beliefs_heuristic_with_memory,
)
from goal_chainer.pipeline import solve_incident


# ---------------------------------------------------------------------------
# Scenario requests
# ---------------------------------------------------------------------------

PII_REQUEST = (
    "Checkout is down. Engineering wants to paste raw logs into the incident room. "
    "Support says the logs may include customer emails, order IDs, and request payloads."
)

PUBLIC_REQUEST = (
    "The outage is resolved. There is no sensitive data in this status, "
    "it is safe to share publicly with engineering and support."
)

UNVERIFIED_REQUEST = (
    "Checkout is down. Engineering wants to paste raw logs into the incident room. "
    "Support says the logs may include customer emails, order IDs, and request payloads. "
    "The root cause is unknown and facts are not verified yet."
)

PUBLIC_UNVERIFIED_REQUEST = (
    "The service is degraded. There is no sensitive data, it is safe to share. "
    "The root cause is unknown and facts are not verified yet."
)


# ---------------------------------------------------------------------------
# Memory evidence helpers
# ---------------------------------------------------------------------------

def _stv_item(action: str, strength: float, confidence: float) -> dict:
    return {
        "goalchainer_slot": "acceptability-belief-evidence",
        "belief_id": f"b-{action}",
        "cluster_id": "mc-multi",
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
        "cluster_id": "mc-multi",
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
# Scenario 1: PII incident — baseline (no memory)
# ---------------------------------------------------------------------------

class TestPIIScenarioBaseline:
    """Standard PII incident with privacy at stake and facts ready."""

    def test_decision_is_redacted_summary(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            result = solve_incident(PII_REQUEST)
            assert result["decided"] == "publish_redacted_summary"
            assert result["status"] == "recommended"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_raw_log_is_blocked_by_deontic(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            result = solve_incident(PII_REQUEST)
            raw_log = next(
                d for d in result["decisions"] if d["action_id"] == "publish_raw_log"
            )
            assert raw_log["status"] == "blocked"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_hold_is_weak_not_recommended(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            result = solve_incident(PII_REQUEST)
            hold = next(
                d for d in result["decisions"] if d["action_id"] == "hold_external_update"
            )
            assert hold["status"] == "weak"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_evidence_has_privacy_at_stake(self):
        evidence = extract_evidence(PII_REQUEST)
        assert evidence.privacy_at_stake is True
        assert evidence.facts_ready is True


# ---------------------------------------------------------------------------
# Scenario 2: Public data — no privacy risk
# ---------------------------------------------------------------------------

class TestPublicDataScenario:
    """Public data with no sensitive categories and facts ready."""

    def test_decision_is_redacted_summary(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            result = solve_incident(PUBLIC_REQUEST)
            assert result["decided"] == "publish_redacted_summary"
            assert result["status"] == "recommended"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_raw_log_is_recommended_not_blocked(self):
        """Without privacy at stake, raw log should not be blocked."""
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            result = solve_incident(PUBLIC_REQUEST)
            raw_log = next(
                d for d in result["decisions"] if d["action_id"] == "publish_raw_log"
            )
            assert raw_log["status"] == "recommended"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_evidence_has_no_privacy_at_stake(self):
        evidence = extract_evidence(PUBLIC_REQUEST)
        assert evidence.privacy_at_stake is False
        assert evidence.facts_ready is True

    def test_raw_log_strength_higher_than_pii_scenario(self):
        """The raw log belief strength should be much higher in the public
        scenario than in the PII scenario."""
        pii_evidence = extract_evidence(PII_REQUEST)
        public_evidence = extract_evidence(PUBLIC_REQUEST)
        pii_beliefs, _, _ = grade_beliefs_heuristic(pii_evidence)
        public_beliefs, _, _ = grade_beliefs_heuristic(public_evidence)
        assert public_beliefs["publish_raw_log"].strength > pii_beliefs["publish_raw_log"].strength


# ---------------------------------------------------------------------------
# Scenario 3: Unverified facts — hold preferred
# ---------------------------------------------------------------------------

class TestUnverifiedFactsScenario:
    """PII incident with unverified facts — hold should be preferred over
    redacted summary because facts are not ready."""

    def test_decision_is_hold(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            result = solve_incident(UNVERIFIED_REQUEST)
            assert result["decided"] == "hold_external_update"
            assert result["status"] == "candidate"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_raw_log_is_blocked_by_deontic(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            result = solve_incident(UNVERIFIED_REQUEST)
            raw_log = next(
                d for d in result["decisions"] if d["action_id"] == "publish_raw_log"
            )
            assert raw_log["status"] == "blocked"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_redacted_summary_is_weak_not_recommended(self):
        """With facts not ready, redacted summary should be weak."""
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            result = solve_incident(UNVERIFIED_REQUEST)
            redacted = next(
                d for d in result["decisions"] if d["action_id"] == "publish_redacted_summary"
            )
            assert redacted["status"] == "weak"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_evidence_has_facts_not_ready(self):
        evidence = extract_evidence(UNVERIFIED_REQUEST)
        assert evidence.privacy_at_stake is True
        assert evidence.facts_ready is False

    def test_hold_strength_higher_than_pii_scenario(self):
        """Hold should have higher strength when facts are not ready."""
        pii_evidence = extract_evidence(PII_REQUEST)
        unverified_evidence = extract_evidence(UNVERIFIED_REQUEST)
        pii_beliefs, _, _ = grade_beliefs_heuristic(pii_evidence)
        unverified_beliefs, _, _ = grade_beliefs_heuristic(unverified_evidence)
        assert unverified_beliefs["hold_external_update"].strength > pii_beliefs["hold_external_update"].strength


# ---------------------------------------------------------------------------
# Scenario 4: Public + unverified — raw log recommended
# ---------------------------------------------------------------------------

class TestPublicUnverifiedScenario:
    """No privacy risk but facts not ready — raw log should be recommended
    because deontic does not block it, even though redacted summary is weak."""

    def test_decision_is_raw_log(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            result = solve_incident(PUBLIC_UNVERIFIED_REQUEST)
            assert result["decided"] == "publish_raw_log"
            assert result["status"] == "recommended"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_redacted_summary_is_weak(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            result = solve_incident(PUBLIC_UNVERIFIED_REQUEST)
            redacted = next(
                d for d in result["decisions"] if d["action_id"] == "publish_redacted_summary"
            )
            assert redacted["status"] == "weak"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_evidence_has_no_privacy_facts_not_ready(self):
        evidence = extract_evidence(PUBLIC_UNVERIFIED_REQUEST)
        assert evidence.privacy_at_stake is False
        assert evidence.facts_ready is False


# ---------------------------------------------------------------------------
# Scenario 5: Conflicting memory — PII with memory saying raw log is acceptable
# ---------------------------------------------------------------------------

class TestConflictingMemoryRawLogOk:
    """PII scenario with memory evidence claiming raw log is acceptable.
    The deontic layer should still block raw_log, but the belief strength
    should shift upward compared to baseline."""

    def test_decision_remains_redacted_summary(self):
        """Despite memory saying raw log is OK, deontic blocks it."""
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            items = [_stv_item("publish_raw_log", 0.95, 0.9)]
            result = solve_incident(PII_REQUEST, memory_items=items)
            assert result["decided"] == "publish_redacted_summary"
            assert result["status"] == "recommended"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_raw_log_remains_blocked(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            items = [_stv_item("publish_raw_log", 0.95, 0.9)]
            result = solve_incident(PII_REQUEST, memory_items=items)
            raw_log = next(
                d for d in result["decisions"] if d["action_id"] == "publish_raw_log"
            )
            assert raw_log["status"] == "blocked"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_raw_log_belief_strength_increases_with_memory(self):
        """The conflicting memory should increase raw_log belief strength."""
        evidence = extract_evidence(PII_REQUEST)
        base_beliefs, _, _ = grade_beliefs_heuristic(evidence)
        items = [_stv_item("publish_raw_log", 0.95, 0.9)]
        mem_beliefs, _, _ = grade_beliefs_heuristic_with_memory(evidence, items)
        assert mem_beliefs["publish_raw_log"].strength > base_beliefs["publish_raw_log"].strength

    def test_redacted_summary_belief_unchanged(self):
        """Memory for raw_log should not affect redacted_summary belief."""
        evidence = extract_evidence(PII_REQUEST)
        base_beliefs, _, _ = grade_beliefs_heuristic(evidence)
        items = [_stv_item("publish_raw_log", 0.95, 0.9)]
        mem_beliefs, _, _ = grade_beliefs_heuristic_with_memory(evidence, items)
        assert mem_beliefs["publish_redacted_summary"].strength == pytest.approx(
            base_beliefs["publish_redacted_summary"].strength
        )


# ---------------------------------------------------------------------------
# Scenario 6: Conflicting memory — PII with memory saying redacted is bad
# ---------------------------------------------------------------------------

class TestConflictingMemoryRedactedBad:
    """PII scenario with memory evidence claiming redacted summary is bad.
    The decision should still be redacted summary (deontic blocks raw_log),
    but its belief strength should decrease."""

    def test_decision_remains_redacted_summary(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            items = [_stv_item("publish_redacted_summary", 0.05, 0.9)]
            result = solve_incident(PII_REQUEST, memory_items=items)
            assert result["decided"] == "publish_redacted_summary"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_redacted_strength_decreases(self):
        evidence = extract_evidence(PII_REQUEST)
        base_beliefs, _, _ = grade_beliefs_heuristic(evidence)
        items = [_stv_item("publish_redacted_summary", 0.05, 0.9)]
        mem_beliefs, _, _ = grade_beliefs_heuristic_with_memory(evidence, items)
        assert mem_beliefs["publish_redacted_summary"].strength < base_beliefs["publish_redacted_summary"].strength

    def test_redacted_confidence_increases_or_stable(self):
        """Fusion with additional evidence should not decrease confidence
        below the baseline (more evidence = higher or equal confidence)."""
        evidence = extract_evidence(PII_REQUEST)
        base_beliefs, _, _ = grade_beliefs_heuristic(evidence)
        items = [_stv_item("publish_redacted_summary", 0.05, 0.9)]
        mem_beliefs, _, _ = grade_beliefs_heuristic_with_memory(evidence, items)
        assert mem_beliefs["publish_redacted_summary"].confidence >= base_beliefs["publish_redacted_summary"].confidence - 0.01


# ---------------------------------------------------------------------------
# Scenario 7: Public data with memory boosting raw log
# ---------------------------------------------------------------------------

class TestPublicDataWithRawLogMemory:
    """Public data scenario with memory evidence saying raw log is excellent.
    Raw log is already recommended without memory; memory should boost it further."""

    def test_decision_remains_redacted_summary(self):
        """Redacted summary still wins because it satisfies all goals."""
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            items = [_stv_item("publish_raw_log", 0.99, 0.95)]
            result = solve_incident(PUBLIC_REQUEST, memory_items=items)
            assert result["decided"] == "publish_redacted_summary"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_raw_log_strength_increases(self):
        evidence = extract_evidence(PUBLIC_REQUEST)
        base_beliefs, _, _ = grade_beliefs_heuristic(evidence)
        items = [_stv_item("publish_raw_log", 0.99, 0.95)]
        mem_beliefs, _, _ = grade_beliefs_heuristic_with_memory(evidence, items)
        assert mem_beliefs["publish_raw_log"].strength > base_beliefs["publish_raw_log"].strength


# ---------------------------------------------------------------------------
# Scenario 8: Unverified facts with memory boosting hold
# ---------------------------------------------------------------------------

class TestUnverifiedWithHoldMemory:
    """Unverified facts scenario with memory evidence saying hold is excellent.
    Hold is already the candidate decision; memory should strengthen it."""

    def test_decision_is_hold(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            items = [_stv_item("hold_external_update", 0.99, 0.95)]
            result = solve_incident(UNVERIFIED_REQUEST, memory_items=items)
            assert result["decided"] == "hold_external_update"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_hold_strength_increases(self):
        evidence = extract_evidence(UNVERIFIED_REQUEST)
        base_beliefs, _, _ = grade_beliefs_heuristic(evidence)
        items = [_stv_item("hold_external_update", 0.99, 0.95)]
        mem_beliefs, _, _ = grade_beliefs_heuristic_with_memory(evidence, items)
        assert mem_beliefs["hold_external_update"].strength > base_beliefs["hold_external_update"].strength

    def test_hold_status_remains_candidate_or_better(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            items = [_stv_item("hold_external_update", 0.99, 0.95)]
            result = solve_incident(UNVERIFIED_REQUEST, memory_items=items)
            hold = next(
                d for d in result["decisions"] if d["action_id"] == "hold_external_update"
            )
            assert hold["status"] in ("candidate", "recommended")
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]


# ---------------------------------------------------------------------------
# Cross-scenario differentiation: verify decisions actually differ
# ---------------------------------------------------------------------------

class TestCrossScenarioDifferentiation:
    """Verify that different scenarios produce different decisions and
    different belief profiles, not a single cookie-cutter answer."""

    def test_pii_and_public_produce_different_raw_log_status(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            pii = solve_incident(PII_REQUEST)
            public = solve_incident(PUBLIC_REQUEST)
            pii_raw = next(d for d in pii["decisions"] if d["action_id"] == "publish_raw_log")
            public_raw = next(d for d in public["decisions"] if d["action_id"] == "publish_raw_log")
            assert pii_raw["status"] == "blocked"
            assert public_raw["status"] == "recommended"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_pii_and_unverified_produce_different_decisions(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            pii = solve_incident(PII_REQUEST)
            unverified = solve_incident(UNVERIFIED_REQUEST)
            assert pii["decided"] == "publish_redacted_summary"
            assert unverified["decided"] == "hold_external_update"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_public_and_public_unverified_produce_different_redacted_status(self):
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            public = solve_incident(PUBLIC_REQUEST)
            public_unv = solve_incident(PUBLIC_UNVERIFIED_REQUEST)
            public_red = next(d for d in public["decisions"] if d["action_id"] == "publish_redacted_summary")
            public_unv_red = next(d for d in public_unv["decisions"] if d["action_id"] == "publish_redacted_summary")
            assert public_red["status"] == "recommended"
            assert public_unv_red["status"] == "weak"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_belief_profiles_differ_across_scenarios(self):
        """The belief strength vectors should be distinct across scenarios."""
        scenarios = {
            "pii": extract_evidence(PII_REQUEST),
            "public": extract_evidence(PUBLIC_REQUEST),
            "unverified": extract_evidence(UNVERIFIED_REQUEST),
            "public_unv": extract_evidence(PUBLIC_UNVERIFIED_REQUEST),
        }
        profiles = {}
        for name, ev in scenarios.items():
            beliefs, _, _ = grade_beliefs_heuristic(ev)
            profiles[name] = tuple(
                round(beliefs[a].strength, 4) for a in ("publish_raw_log", "publish_redacted_summary", "hold_external_update")
            )
        # All four profiles should be distinct
        unique = set(profiles.values())
        assert len(unique) == 4, f"Expected 4 distinct profiles, got {len(unique)}: {profiles}"

    def test_conflicting_memory_does_not_override_deontic(self):
        """Even with strong memory saying raw log is acceptable, the deontic
        layer must still block it when privacy is at stake."""
        os.environ["GOALCHAINER_USE_HEURISTIC_PLN"] = "1"
        try:
            # Very strong STV memory for raw log
            items = [
                _stv_item("publish_raw_log", 0.99, 0.99),
                _ec_item("publish_raw_log", 99, 1),
            ]
            result = solve_incident(PII_REQUEST, memory_items=items)
            raw_log = next(
                d for d in result["decisions"] if d["action_id"] == "publish_raw_log"
            )
            assert raw_log["status"] == "blocked"
            assert result["decided"] == "publish_redacted_summary"
        finally:
            del os.environ["GOALCHAINER_USE_HEURISTIC_PLN"]

    def test_ec_memory_also_adjusts_beliefs_across_scenarios(self):
        """EC (EvidencePacket) memory items should also shift beliefs."""
        pii_evidence = extract_evidence(PII_REQUEST)
        base_beliefs, _, _ = grade_beliefs_heuristic(pii_evidence)

        # EC with strong opposition for raw_log (confirms keyword evidence)
        items = [_ec_item("publish_raw_log", 1, 19)]
        mem_beliefs, _, _ = grade_beliefs_heuristic_with_memory(pii_evidence, items)
        # More opposition should push strength even lower
        assert mem_beliefs["publish_raw_log"].strength < base_beliefs["publish_raw_log"].strength

        # EC with strong support for redacted (confirms keyword evidence)
        items = [_ec_item("publish_redacted_summary", 19, 1)]
        mem_beliefs2, _, _ = grade_beliefs_heuristic_with_memory(pii_evidence, items)
        assert mem_beliefs2["publish_redacted_summary"].strength > base_beliefs["publish_redacted_summary"].strength - 0.01

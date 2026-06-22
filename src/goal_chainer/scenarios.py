"""Built-in scenarios for demos and tests."""

from __future__ import annotations

from .models import CandidateAction, Goal, GoalScenario, Norm


def incident_response_scenario() -> GoalScenario:
    goals = (
        Goal(
            id="preserve_privacy",
            owner="ava",
            statement="Do not expose identifiable user data.",
            weight=0.95,
            kind="individual",
            required=True,
        ),
        Goal(
            id="restore_service",
            owner="ops-team",
            statement="Restore the failing service quickly.",
            weight=0.9,
            kind="collective",
            required=True,
        ),
        Goal(
            id="coordinate_team",
            owner="incident-team",
            statement="Give responders enough shared context to coordinate.",
            weight=0.75,
            kind="collective",
            required=True,
        ),
    )
    norms = (
        Norm(
            id="no-raw-pii",
            mode="forbid",
            target_action="publish_raw_log",
            priority=20,
            reason="raw incident logs contain personal data",
        ),
        Norm(
            id="share-redacted-status",
            mode="oblige",
            target_action="publish_redacted_summary",
            priority=12,
            reason="responders need a status artifact that protects privacy",
        ),
        Norm(
            id="temporary-hold-permitted",
            mode="permit",
            target_action="hold_external_update",
            priority=5,
            reason="a short hold is allowed while facts are checked",
        ),
    )
    actions = (
        CandidateAction(
            id="publish_raw_log",
            label="Publish raw incident log",
            description="Share the full raw log with the whole response channel.",
            satisfies=("restore_service", "coordinate_team"),
            evidence_query="(: $prf (Acceptable publish_raw_log) $tv)",
            evidence_atoms=_raw_log_atoms(),
            default_strength=0.18,
        ),
        CandidateAction(
            id="publish_redacted_summary",
            label="Publish redacted summary",
            description="Share a summary with identifiers removed and enough detail to coordinate.",
            satisfies=("preserve_privacy", "restore_service", "coordinate_team"),
            evidence_query="(: $prf (Acceptable publish_redacted_summary) $tv)",
            evidence_atoms=_redacted_summary_atoms(),
            default_strength=0.91,
        ),
        CandidateAction(
            id="hold_external_update",
            label="Hold external update",
            description="Keep information internal until the team checks the evidence.",
            satisfies=("preserve_privacy",),
            evidence_query="(: $prf (Acceptable hold_external_update) $tv)",
            evidence_atoms=_hold_update_atoms(),
            default_strength=0.58,
        ),
    )
    return GoalScenario(
        title="Incident response with individual privacy and collective repair goals",
        goals=goals,
        norms=norms,
        actions=actions,
        notes=(
            "The raw log advances collective coordination but is blocked by a higher-priority privacy norm.",
            "The redacted summary satisfies all required goals and is obligated by the deontic layer.",
            "The hold protects privacy but misses the required collective repair and coordination goals.",
        ),
    )


def _raw_log_atoms() -> tuple[str, ...]:
    return (
        "(: good_status (Acceptable clean_status) (STV 0.96 0.99))",
        "(: bad_dump (Acceptable pii_dump) (STV 0.02 0.99))",
        "(: raw_is_pii (ContainsPII publish_raw_log) (STV 1.0 0.99))",
        "(: dump_is_pii (ContainsPII pii_dump) (STV 1.0 0.99))",
        "(: raw_supports_team (SupportsCollective publish_raw_log) (STV 1.0 0.99))",
        "(: support_to_accept (Implication (Premises (SupportsCollective $x)) (Conclusions (Acceptable $x))) (STV 0.92 0.99))",
    )


def _redacted_summary_atoms() -> tuple[str, ...]:
    return (
        "(: clean_status (Acceptable clean_status) (STV 0.96 0.99))",
        "(: redacted_supports_team (SupportsCollective publish_redacted_summary) (STV 1.0 0.99))",
        "(: redacted_no_pii (Redacted publish_redacted_summary) (STV 1.0 0.99))",
        "(: support_to_accept (Implication (Premises (SupportsCollective $x)) (Conclusions (Acceptable $x))) (STV 0.92 0.99))",
        "(: redaction_to_accept (Implication (Premises (Redacted $x)) (Conclusions (Acceptable $x))) (STV 0.95 0.99))",
    )


def _hold_update_atoms() -> tuple[str, ...]:
    return (
        "(: careful_hold (Acceptable hold_external_update) (STV 0.58 0.99))",
        "(: hold_protects_privacy (ProtectsPrivacy hold_external_update) (STV 0.9 0.99))",
    )


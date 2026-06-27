"""Incident scenario whose action/goal links are derived from the evidence."""

from __future__ import annotations

from .evidence import IncidentEvidence, extract_evidence
from .models import CandidateAction, Goal, GoalScenario, Norm

DEFAULT_INCIDENT_REQUEST = (
    "Checkout is down. Engineering wants to paste raw logs into the incident room. "
    "Support says the logs may include customer emails, order IDs, and request payloads."
)


def incident_goals() -> tuple[Goal, ...]:
    return (
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


def policy_norms() -> tuple[Norm, ...]:
    """The standing deontic policy, kept for display. The decision uses the
    deontic status derived natively per action, not this static table."""
    return (
        Norm(
            id="no-raw-pii",
            mode="forbid",
            target_action="publish_raw_log",
            priority=20,
            reason="raw incident logs may contain personal data",
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


def incident_scenario(evidence: IncidentEvidence) -> GoalScenario:
    """Build the scenario for this request. Each action's satisfied goals follow
    from the evidence, so the ranking changes when the request changes."""

    actions = (
        CandidateAction(
            id="publish_raw_log",
            label="Publish raw incident log",
            description="Share the full raw log with the whole response channel.",
            satisfies=_raw_log_satisfies(evidence),
            evidence_query="(: $prf (Acceptable publish_raw_log) $tv)",
            evidence_atoms=(),
            default_strength=0.18,
        ),
        CandidateAction(
            id="publish_redacted_summary",
            label="Publish redacted summary",
            description="Share a summary with identifiers removed and enough detail to coordinate.",
            satisfies=_redacted_satisfies(evidence),
            evidence_query="(: $prf (Acceptable publish_redacted_summary) $tv)",
            evidence_atoms=(),
            default_strength=0.91,
        ),
        CandidateAction(
            id="hold_external_update",
            label="Hold external update",
            description="Keep information internal until the team checks the evidence.",
            satisfies=("preserve_privacy",),
            evidence_query="(: $prf (Acceptable hold_external_update) $tv)",
            evidence_atoms=(),
            default_strength=0.58,
        ),
    )
    return GoalScenario(
        title="Incident response with individual privacy and collective repair goals",
        goals=incident_goals(),
        norms=policy_norms(),
        actions=actions,
        notes=_notes(evidence),
    )


def incident_response_scenario(request: str = DEFAULT_INCIDENT_REQUEST) -> GoalScenario:
    """Backward-compatible builder from a request string."""
    return incident_scenario(extract_evidence(request))


def _raw_log_satisfies(evidence: IncidentEvidence) -> tuple[str, ...]:
    goals = ["restore_service", "coordinate_team"]
    if not evidence.privacy_at_stake:
        # Nothing identifiable to expose, so the privacy goal is not threatened.
        goals.insert(0, "preserve_privacy")
    return tuple(goals)


def _redacted_satisfies(evidence: IncidentEvidence) -> tuple[str, ...]:
    goals = ["preserve_privacy"]
    if evidence.facts_ready:
        # An external status only advances repair/coordination once facts hold;
        # broadcasting an unverified status can mislead responders.
        goals += ["restore_service", "coordinate_team"]
    return tuple(goals)


def _notes(evidence: IncidentEvidence) -> tuple[str, ...]:
    if not evidence.privacy_at_stake:
        return (
            "The request carries no identifiable data, so the raw log is no longer "
            "privacy-risky and becomes an acceptable option.",
            "The redacted summary still covers every goal and stays the safe default.",
        )
    if not evidence.facts_ready:
        return (
            "The raw log is blocked by the derived privacy prohibition.",
            "Facts are not ready, so an external update is premature and holding wins.",
        )
    return (
        "The raw log advances coordination but is blocked by the derived privacy prohibition.",
        "The redacted summary satisfies all required goals and is the recommended action.",
        "The hold protects privacy but misses the required collective goals.",
    )

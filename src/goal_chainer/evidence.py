"""Extract decision-relevant evidence from a natural-language request.

This is the layer that makes the decision depend on the input. Everything
downstream (NAL premise truth values, derived deontic status, goal satisfaction)
is a function of the `IncidentEvidence` produced here, so a different request
produces different premises and a different decision.

The extraction is deliberately simple and deterministic (keyword signals), so it
is testable on its own. In the deployed skill the structured-English step can
supply these signals directly instead of relying on keywords.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


# Sensitive-data categories and the request words that signal each. Shared with
# hyperbase.py so proposition rendering and evidence extraction agree.
SENSITIVE_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("customer emails", ("email", "e-mail")),
    ("order IDs", ("order",)),
    ("request payloads", ("payload",)),
    ("tokens or secrets", ("token", "secret", "credential", "api key", "apikey")),
    ("full traces", ("trace", "stack trace", "stacktrace")),
    ("raw logs", ("raw log", "logs", "log line")),
)

# Phrases that explicitly assert the data is safe to share in full.
_PUBLIC_SIGNALS: tuple[str, ...] = (
    "no sensitive data",
    "no personal data",
    "no customer data",
    "nothing sensitive",
    "no pii",
    "not sensitive",
    "safe to share",
    "safe to publish",
    "publicly",
    "public information",
    "already public",
)

# Phrases that say the facts are not yet established.
_NOT_READY_SIGNALS: tuple[str, ...] = (
    "not verified",
    "unverified",
    "not confirmed",
    "unconfirmed",
    "facts are not ready",
    "facts not ready",
    "still investigating",
    "do not know yet",
    "don't know yet",
    "root cause is unknown",
    "no root cause",
)

# Phrases that show responders need shared context.
_COORDINATION_SIGNALS: tuple[str, ...] = (
    "engineering",
    "support",
    "responders",
    "coordinate",
    "incident room",
    "incident channel",
    "team",
    "on-call",
    "oncall",
)


@dataclass(frozen=True)
class IncidentEvidence:
    """Decision-relevant signals read off the request."""

    request: str
    sensitive_categories: tuple[str, ...]
    public_declared: bool
    facts_ready: bool
    coordination_needed: bool
    propositions: tuple[str, ...] = ()
    provenance: str = "keyword"
    concept_scores: dict[str, float] = field(default_factory=dict)
    mood: str = "declarative"

    @property
    def has_sensitive_data(self) -> bool:
        return bool(self.sensitive_categories)

    @property
    def privacy_at_stake(self) -> bool:
        """True when there is identifiable data the agent must protect."""
        return self.has_sensitive_data and not self.public_declared

    def to_dict(self) -> dict[str, object]:
        return {
            "sensitive_categories": list(self.sensitive_categories),
            "public_declared": self.public_declared,
            "facts_ready": self.facts_ready,
            "coordination_needed": self.coordination_needed,
            "privacy_at_stake": self.privacy_at_stake,
            "provenance": self.provenance,
            "propositions": list(self.propositions),
            "concept_scores": dict(self.concept_scores),
            "mood": self.mood,
        }


def extract_evidence(request: str) -> IncidentEvidence:
    """Extract evidence, preferring the semantic SH path when enabled.

    Set GOALCHAINER_SEMANTIC=1 to parse the request into SH propositions and detect
    concepts by Ollama-embedding similarity (real paraphrase matching). The keyword
    path is the offline fallback and the default, so tests stay fast and local.
    """

    if os.environ.get("GOALCHAINER_SEMANTIC") in {"1", "true", "yes"}:
        from .mettabase_bridge import available
        from .semantic_evidence import extract_semantic_evidence

        if available():
            try:
                return extract_semantic_evidence(request)
            except Exception:
                pass  # fall through to the keyword extractor
    return _extract_keyword_evidence(request)


def _extract_keyword_evidence(request: str) -> IncidentEvidence:
    lower = request.lower()
    categories = tuple(
        label
        for label, signals in SENSITIVE_CATEGORIES
        if any(signal in lower for signal in signals)
    )
    public_declared = _any_signal(lower, _PUBLIC_SIGNALS)
    facts_ready = not _any_signal(lower, _NOT_READY_SIGNALS)
    coordination_needed = _any_signal(lower, _COORDINATION_SIGNALS)
    return IncidentEvidence(
        request=request,
        sensitive_categories=categories,
        public_declared=public_declared,
        facts_ready=facts_ready,
        coordination_needed=coordination_needed,
    )


def _any_signal(lower_request: str, signals: tuple[str, ...]) -> bool:
    return any(signal in lower_request for signal in signals)

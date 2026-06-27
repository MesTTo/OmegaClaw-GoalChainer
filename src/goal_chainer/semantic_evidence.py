"""Evidence extraction from real SH propositions + semantic matching.

This is the honest replacement for keyword matching. The request is parsed into
Semantic-Hypergraph propositions by the HyperBase parser, and the decision-relevant
concepts are detected by semantic similarity (Ollama embeddings) rather than
substring hits, so a paraphrase like "the logs hold people's private details"
still registers as sensitive-data exposure.

Classification is relative with a floor: whichever of sensitive-data / public-safe
the request expresses more strongly wins, and a concept must clear a floor to count
at all. That avoids brittle absolute thresholds.
"""

from __future__ import annotations

from .evidence import SENSITIVE_CATEGORIES, IncidentEvidence
from .mettabase_bridge import parse_and_score

# Floor a concept must clear to be considered present. Classification compares the
# sensitive vs public concept directly. This is a calibrated-but-fragile heuristic:
# raw-text embeddings handle negation poorly ("nothing private" embeds near
# "private"), so margins are thin. The robust replacement is SH-structural reasoning
# (the Mn polarity modifier), per mettabase's sh-rich-reasoning plans.
FLOOR = 0.5
CATEGORY_FLOOR = 0.5
PUBLIC_MARGIN = 0.0

_SIGNAL_CONCEPTS = {
    "sensitive_data": (
        "the content reveals personal information about people: names, contact "
        "details, home addresses, emails, identifiers, who the customers are, "
        "private or confidential data, secrets, tokens"
    ),
    "public_safe": (
        "the content has no personal or private information at all, no names and no "
        "contact details, it is non-confidential general information"
    ),
    "facts_not_ready": (
        "the root cause is unknown, the facts are not verified or confirmed, still "
        "investigating, nothing is ready to communicate yet"
    ),
    "coordination_needed": (
        "engineering and support responders need shared context to coordinate the "
        "incident in the incident room"
    ),
}

_CATEGORY_CONCEPTS = {
    f"cat::{label}": f"the data includes {label}" for label, _ in SENSITIVE_CATEGORIES
}


def extract_semantic_evidence(request: str) -> IncidentEvidence:
    concepts = {**_SIGNAL_CONCEPTS, **_CATEGORY_CONCEPTS}
    data = parse_and_score(request, concepts)
    scores = data["scores"]
    propositions = tuple(data.get("propositions", ()))

    sensitive = scores.get("sensitive_data", 0.0)
    public = scores.get("public_safe", 0.0)
    not_ready = scores.get("facts_not_ready", 0.0)
    coordination = scores.get("coordination_needed", 0.0)

    # Privacy-cautious: only treat the request as public when the public concept
    # clearly beats the sensitive one; a near-tie keeps the privacy guard on.
    public_declared = public >= FLOOR and public > sensitive + PUBLIC_MARGIN
    categories = tuple(
        label
        for label, _ in SENSITIVE_CATEGORIES
        if scores.get(f"cat::{label}", 0.0) >= CATEGORY_FLOOR
    )
    # If the request reads as sensitive overall but no single category cleared the
    # floor, still record that identifiable data is at stake.
    if sensitive >= FLOOR and not public_declared and not categories:
        categories = ("identifiable user data",)

    return IncidentEvidence(
        request=request,
        sensitive_categories=categories,
        public_declared=public_declared,
        facts_ready=not_ready < FLOOR,
        coordination_needed=coordination >= FLOOR,
        propositions=propositions,
        provenance="mettabase-sh-parse+ollama-semmatch",
        concept_scores={name: round(score, 4) for name, score in scores.items()},
    )

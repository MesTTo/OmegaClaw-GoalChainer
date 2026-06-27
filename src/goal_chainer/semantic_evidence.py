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

# Floor a concept must clear to count as present in a sentence. Classification is
# vote-based across sentences with structural polarity from TNF peel, so negation is
# handled (a negated "sensitive" sentence votes public), not guessed from raw cosine.
FLOOR = 0.5
CATEGORY_FLOOR = 0.5

# Concepts are stated POSITIVELY so TNF negation flips them cleanly: a sentence
# that matches "sensitive_data" but peels to negated ("no private data") votes
# public, and a negated "facts_ready" ("facts are not ready") votes not-ready.
_SIGNAL_CONCEPTS = {
    "sensitive_data": (
        "the content reveals personal information about people: names, contact "
        "details, home addresses, emails, identifiers, who the customers are, "
        "private or confidential data, secrets, tokens"
    ),
    "public_safe": (
        "this is general public information that anyone may openly read, "
        "non-confidential and freely shareable"
    ),
    "facts_ready": (
        "the facts are verified and confirmed, the root cause is known, the "
        "situation is understood and ready to communicate"
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
    propositions = tuple(data.get("propositions", ()))
    sentences = data.get("sentences") or [
        {"text": request, "negated": False, "scores": data.get("request_scores", {})}
    ]

    # Tally each signal across sentences. Negation flips the contribution: a
    # sentence matching "sensitive" but peeled to negated ("no private data") is a
    # public/safe signal, not a sensitive one. This is the structural fix raw-text
    # embeddings could not do (TNF peel from mettabase).
    sensitive_votes = public_votes = not_ready_votes = ready_votes = 0
    coordination = False
    categories: set[str] = set()
    for sentence in sentences:
        scores = sentence.get("scores", {})
        negated = bool(sentence.get("negated"))
        if scores.get("sensitive_data", 0.0) >= FLOOR:
            if negated:
                public_votes += 1
            else:
                sensitive_votes += 1
        if scores.get("public_safe", 0.0) >= FLOOR:
            if negated:
                sensitive_votes += 1
            else:
                public_votes += 1
        if scores.get("facts_ready", 0.0) >= FLOOR:
            if negated:
                not_ready_votes += 1
            else:
                ready_votes += 1
        if scores.get("coordination_needed", 0.0) >= FLOOR:
            coordination = True
        if not negated:
            for label, _ in SENSITIVE_CATEGORIES:
                if scores.get(f"cat::{label}", 0.0) >= CATEGORY_FLOOR:
                    categories.add(label)

    # Privacy-protective default: only drop the guard when public evidence strictly
    # outweighs sensitive evidence. A tie (e.g. "we want to share" reads as both)
    # stays sensitive, which for a privacy tool is the safe failure direction.
    public_declared = public_votes > sensitive_votes
    facts_ready = not_ready_votes == 0 or ready_votes >= not_ready_votes
    if sensitive_votes > 0 and not public_declared and not categories:
        categories.add("identifiable user data")

    ordered = tuple(label for label, _ in SENSITIVE_CATEGORIES if label in categories)
    if "identifiable user data" in categories:
        ordered = ordered + ("identifiable user data",)

    return IncidentEvidence(
        request=request,
        sensitive_categories=ordered,
        public_declared=public_declared,
        facts_ready=facts_ready,
        coordination_needed=coordination,
        propositions=propositions,
        provenance="mettabase-sh-parse+tnf-polarity+ollama-semmatch",
        concept_scores={
            "sensitive_votes": sensitive_votes,
            "public_votes": public_votes,
            "not_ready_votes": not_ready_votes,
            "ready_votes": ready_votes,
        },
    )

"""Semantic evidence extraction: real SH parse + Ollama matching.

Guarded: skips when the mettabase venv or the Ollama endpoint is not reachable, so
the default (keyword) test run stays offline and fast.
"""

import pytest

from goal_chainer.mettabase_bridge import available, parse_and_score


def _ollama_up() -> bool:
    if not available():
        return False
    try:
        parse_and_score("the data has names and contact details", {"x": "personal data"})
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _ollama_up(), reason="mettabase venv / Ollama not available")


def test_semantic_catches_paraphrase_without_keywords():
    from goal_chainer.semantic_evidence import extract_semantic_evidence

    # No trigger words (no log/email/order/payload/token/trace), but clearly sensitive.
    ev = extract_semantic_evidence(
        "The dump we want to share reveals who our shoppers are and their home addresses."
    )
    assert ev.privacy_at_stake is True
    assert "tnf-polarity" in ev.provenance
    assert ev.propositions  # real SH propositions came back from the parser


def test_tnf_negation_makes_facts_not_ready():
    from goal_chainer.semantic_evidence import extract_semantic_evidence

    # "facts are not ready" matches the positive facts_ready concept, and TNF peel
    # marks it negated, so the structural polarity yields facts_ready=False.
    ev = extract_semantic_evidence(
        "Checkout is down but the root cause is unknown and the facts are not ready."
    )
    assert ev.facts_ready is False


def test_negated_action_still_guards_the_sensitive_data():
    from goal_chainer.semantic_evidence import extract_semantic_evidence

    # The negation scopes the action, not the data: a concrete category keeps the
    # privacy guard on (safe direction), it does not flip the request to public.
    ev = extract_semantic_evidence(
        "Do not publish the raw logs that expose customer emails."
    )
    assert ev.privacy_at_stake is True

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
    assert ev.provenance == "mettabase-sh-parse+ollama-semmatch"
    assert ev.propositions  # real SH propositions came back from the parser


def test_semantic_public_paraphrase_not_at_stake():
    from goal_chainer.semantic_evidence import extract_semantic_evidence

    ev = extract_semantic_evidence(
        "The incident note we want to post has nothing private in it, anyone can read it."
    )
    assert ev.public_declared is True
    assert ev.privacy_at_stake is False

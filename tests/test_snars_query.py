"""SNARS assessment: believe! -> ask! -> why! returns an opinion + provenance.

Guarded: skips when the mettabase/PeTTa SNARS runtime is not reachable.
"""

import pytest

from goal_chainer.snars_query import assess, available


def _snars_up() -> bool:
    if not available():
        return False
    try:
        return bool(assess("a", "rel", "b").get("opinion"))
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _snars_up(), reason="SNARS runtime not available")


def test_snars_returns_opinion_and_provenance():
    result = assess("publish_raw_log", "exposes", "personal_data", source="request")

    opinion = result["opinion"]
    # A Subjective-Logic opinion: belief/disbelief/uncertainty/base-rate.
    assert set(opinion) == {"b", "d", "u", "a"}
    assert 0.0 <= opinion["b"] <= 1.0
    assert opinion["u"] > 0.0  # asserted-once evidence keeps residual uncertainty
    assert result["expectation"] is not None
    # The why-receipt carries provenance back to the source.
    assert "because" in result["why"]
    assert "request" in result["why"]

"""The Prolog-on-PeTTa scorer must agree with the Python combined score.

Guarded: skips when the PeTTa runtime is not reachable.
"""

import pytest

from goal_chainer.models import EvidenceProjection
from goal_chainer.native_score import available, decide_actions, score_actions
from goal_chainer.scoring import _combined_score, _decision_status


def _python_score(deontic: str, strength: float, confidence: float, motivation: float) -> float:
    evidence = EvidenceProjection(strength=strength, confidence=confidence, source="x", deontic=deontic)
    return _combined_score(
        goal_score=0.0,
        individual_score=0.0,
        collective_score=0.0,
        evidence=evidence,
        deontic=deontic,
        motivation=motivation,
    )


def _up() -> bool:
    if not available():
        return False
    try:
        return len(score_actions([("permitted", 0.5, 0.5, 0.5)])) == 1
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _up(), reason="PeTTa runtime not available")


def test_prolog_score_matches_python():
    rows = [
        ("obligated", 0.934, 0.977, 1.0),
        ("permitted", 0.752, 0.812, 0.5256),
        ("forbidden", 0.05, 0.7, 0.0),
        ("unregulated", 0.6, 0.6, 0.3),
    ]
    native = score_actions(rows)
    for (deontic, strength, confidence, motivation), got in zip(rows, native):
        want = _python_score(deontic, strength, confidence, motivation)
        assert abs(got - want) < 1e-9, f"{deontic}: prolog {got} != python {want}"


def test_prolog_decide_matches_python_score_and_status():
    # (deontic, strength, confidence, motivation, has_missing) and the expected status.
    rows = [
        ("obligated", 0.934, 0.977, 1.0, 0),       # high score, nothing missing -> recommended
        ("permitted", 0.752, 0.812, 0.5256, 1),    # mid score -> candidate
        ("permitted", 0.5, 0.4, 0.1, 1),           # low score -> weak
        ("forbidden", 0.05, 0.7, 0.0, 1),          # forbidden -> blocked
    ]
    for (deontic, strength, confidence, motivation, has_missing), (score, status) in zip(
        rows, decide_actions(rows)
    ):
        want_score = _python_score(deontic, strength, confidence, motivation)
        want_status = _decision_status(deontic, want_score, ["x"] if has_missing else [])
        assert abs(score - want_score) < 1e-9
        assert status == want_status, f"{deontic}: prolog {status} != python {want_status}"

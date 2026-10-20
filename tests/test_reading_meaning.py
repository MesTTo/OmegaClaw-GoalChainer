"""Purpose: hold reading propositions to what real Jev answers, replayed from tests/data/jev, make of
short texts that support one, contradict it and stay silent on it, so a question's wording cannot
drift from its meaning unnoticed."""

from __future__ import annotations

import pytest

from goal_chainer import semantic_reader as sr
from request_support import budget


# unverified counts only a stated verification status. The first text reports an incident and
# says nothing about whether its facts are verified, which an earlier wording read as unverified.
# am[verifies a-jev-unverified-question-1016@8ecfa0]
@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("Checkout is down. Raw logs include customer emails. Engineering needs the incident room.", "unknown"),
        ("The facts are unverified. Engineering is still investigating the incident.", "supported"),
        ("Checkout is down but the root cause is unknown and the facts are not ready.", "supported"),
        ("The root cause is confirmed and the facts are verified. Engineering needs the incident room.", "contradicted"),
    ],
)
def test_unverified_reads_only_what_a_text_says_about_verification(text, answer) -> None:
    assert sr.default_reader(budget=budget()).read(text, budget=budget()).proposition("unverified").answer == answer

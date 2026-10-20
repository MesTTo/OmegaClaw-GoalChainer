"""Purpose: build relevance packets and derived reviews by hand, so ranking and contract tests run the MeTTa policy without a theory run, call the policy's untyped helpers in its module group's space, and run test scripts in a fresh process."""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from goal_chainer.domains.loader import packaged_domain
from goal_chainer.domains.model import Domain
from goal_chainer.relevance.dependency import dependency_index
from goal_chainer.relevance.derived import Candidate, Contribution, DerivedReview, EngineRecord
from goal_chainer.relevance.freshness import FreshnessReport, check_freshness
from goal_chainer.relevance.packet import ReviewBudget, ReviewPacket
from goal_chainer.relevance.policy import RELEVANCE_POLICY
from goal_chainer.relevance.quantity import Quantity, build_profile
from goal_chainer.relevance.review import ReviewResult, review
from goal_chainer.relevance.signals import SignalReading, effective_readings
from policy_support import group_answers
from request_support import budget as request_budget

ROOT = Path(__file__).resolve().parents[1]
AS_OF = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
_DEFAULT = object()
# The least integer float() cannot convert: 2**1024 - 2**970 is halfway between the largest float and
# 2**1024, so it rounds up and overflows, and every smaller integer rounds to at most the largest float.
# am[related a-integrate-relevance-numeric-boundaries-1018@4c2a7d] am[related c-rel-num-packet-timeout-edge-1018@c829b4]
FLOAT_EDGE = 2**1024 - 2**970
# How a refusal names an integer beyond the float range instead of writing it out.
BEYOND_FLOAT = "an integer beyond the float range"
ENGINE = EngineRecord(
    runtime="pymetta 0.9.4",
    runtime_digest="runtime-digest",
    plugin_digest="plugin-digest",
    swipl_version="10.1.17",
)


# am[related a-rel-ranking-1016@334372]
def task_control() -> Domain:
    return packaged_domain("task-control", budget=request_budget())


# am[related a-rel-ranking-1016@334372]
def reading(signal: str, state: str = "detected", estimator=_DEFAULT, **fields) -> SignalReading:
    """A reading with a test source; definite readings default to a deterministic estimator."""

    if estimator is _DEFAULT:
        estimator = None if state == "unknown" else "deterministic"
    return SignalReading(signal=signal, state=state, source=fields.pop("source", f"test:{signal}"),
                         estimator=estimator, **fields)


# am[related a-rel-ranking-1016@334372]
def packet(*readings: SignalReading, authority: str = "advisory", as_of: datetime = AS_OF) -> ReviewPacket:
    return ReviewPacket(
        review_id="rr-test",
        subject="task-under-review",
        trigger="test",
        as_of=as_of,
        authority=authority,
        budget=ReviewBudget(inferences=50_000_000, timeout_seconds=120.0),
        readings=tuple(readings),
    )


# A review or a freshness check under the one budget the packet's bounds make, as the relevance
# CLI runs them at its boundary.
# am[related a-integrate-domain-review-budget-1018@a84bf4]
def reviewed(domain: Domain, review_packet: ReviewPacket) -> ReviewResult:
    return review(domain, review_packet, budget=review_packet.budget.run_budget())


# am[related a-integrate-domain-review-budget-1018@a84bf4]
def checked_freshness(prior: Any, domain: Domain, review_packet: ReviewPacket, engine: Any) -> FreshnessReport:
    return check_freshness(prior, domain, review_packet, engine, budget=review_packet.budget.run_budget())


# am[related a-rel-ranking-1016@334372]
def candidate(
    domain: Domain,
    action: str,
    *,
    modes: str = "P",
    dilemma: bool = False,
    effects: dict[str, tuple[str, str] | list[tuple[str, str]]] | None = None,
    contributions: dict[str, str] | None = None,
) -> Candidate:
    """A candidate with the given deontic modes, effects {dimension: (band, estimator)} and
    contributions {goal: band}; a dimension may map to several claims. Its readset is filled in
    by `derived`, which asks the readset policy once for every candidate of the review."""

    claims: list[Quantity] = []
    for dimension, value in (effects or {}).items():
        for band, estimator in value if isinstance(value, list) else [value]:
            claims.append(Quantity(dimension, band, estimator))
    return Candidate(
        action=domain.action(action),
        modes=frozenset(modes),
        dilemma=dilemma,
        profile=build_profile(action, claims),
        contributions=tuple(Contribution(goal, band) for goal, band in sorted((contributions or {}).items())),
        readset=frozenset(),
    )


# am[related a-rel-ranking-1016@334372] am[related a-integrate-deontic-support-trees-1019@508ecf]
def derived(
    domain: Domain,
    candidates: list[Candidate],
    *,
    readings: tuple[SignalReading, ...] = (),
    obligations: tuple[str, ...] | None = None,
    required: tuple[str, ...] = (),
    review_packet: ReviewPacket | None = None,
) -> DerivedReview:
    review_packet = review_packet or packet(*readings)
    budget = request_budget()
    readsets = dependency_index(domain, budget=budget).readsets([c.id for c in candidates], budget=budget)
    return DerivedReview(
        domain=domain,
        packet=review_packet,
        readings=effective_readings(review_packet.readings, domain.signal_ids, review_packet.as_of, budget=budget),
        candidates=tuple(dataclasses.replace(c, readset=readsets.candidates[c.id]) for c in candidates),
        obligations=tuple(c.id for c in candidates if "O" in c.modes) if obligations is None else obligations,
        required_goals=required,
        other_dilemmas=(),
        readset=readsets.review,
        engine=ENGINE,
        theory="",
        deontic_support=(),
    )


# am[related a-rel-ranking-1016@334372]
def later(minutes: int) -> datetime:
    return AS_OF + timedelta(minutes=minutes)


# Every answer of (FUNCTION ARGUMENT ...) in the relevance policy's space, each argument a hole,
# for a test of a helper the evaluator cannot call because it declares no type.
# am[verifies a-rel-mig-tests-1018@3b8517]
def helper_answers(function: str, *arguments: Any) -> list[Any]:
    holes = {f"argument{index}": argument for index, argument in enumerate(arguments)}
    return group_answers(RELEVANCE_POLICY, "(" + " ".join([function, *("{" + name + "}" for name in holes)]) + ")", **holes)


# am[verifies a-rel-mig-tests-1018@3b8517]
def helper_call(function: str, *arguments: Any) -> Any:
    """The one answer of (FUNCTION ARGUMENT ...) in the relevance policy's space."""

    answers = helper_answers(function, *arguments)
    assert len(answers) == 1, (function, answers)
    return answers[0]


# A fresh interpreter, so the process-wide engine and everything prepared in it start empty.
# am[related a-rel-metta-policy-1016@fdaa20]
def fresh_process(script: str, *args: str) -> Any:
    """The JSON a script prints last, run as `python -c SCRIPT ARGS` with this checkout's src
    first on the path."""

    env = child_environment()
    completed = subprocess.run(
        [sys.executable, "-c", script, *args], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


# The environment a child process of this checkout runs in: this process's, with the checkout's src
# first on the path and each override set, or removed where it is None.
# am[related a-rel-cli-stdin-utf8-1018@18df88]
def child_environment(**overrides: str | None) -> dict[str, str]:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH")]))}
    for name, value in overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return env

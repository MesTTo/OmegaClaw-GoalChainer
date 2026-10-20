"""Purpose: the motivation tests' shared fixtures: a small companion domain with needs, plain records
with the fields a stream's observations and attempts carry, instants by the second, a reference
of the reduction formula written independently of the MeTTa policy, and a snapshot call under a
test budget."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from goal_chainer.domains.loader import read_domain
from goal_chainer.domains.model import Domain
from goal_chainer.motivation import Attempt, MotivationHistory, NeedObservation
from goal_chainer.relevance.motivation import MotivationSnapshot, motivation_snapshot
from goal_chainer.runtime.budget import RunBudget

EPOCH = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)

CORE = """
(gc-domain "Companion fixture")
(gc-policy-version companion-fixture-v1)
(gc-authority advisory 1 "A recommendation for the host.")
(gc-authority preauthorized 2 "Applied inside a declared envelope.")
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling receipt-calibrated preauthorized)
(gc-estimator-ceiling measured preauthorized)
(gc-estimator-ceiling deterministic preauthorized)
(gc-estimator-ceiling human-asserted preauthorized)
(gc-action empathize "Empathize" "Reflect the feeling back." (authority preauthorized))
(gc-action guide_breath "Guide breath" "Lead a breathing practice." (authority preauthorized))
(gc-action stay_silent "Stay silent" "Let the silence hold." (authority preauthorized))
(gc-goal nurturing agent individual 0.9 "The student's suffering is eased." (priority-source human:designer))
(gc-goal competence agent individual 0.6 "The guidance is effective." (priority-source human:designer))
(gc-signal session_open "a session is open")
(normally rCandEmpathize (signal session_open) (candidate empathize))
(normally rCandBreath (signal session_open) (candidate guide_breath))
(normally rCandSilent (signal session_open) (candidate stay_silent))
(normally rPermit (candidate ?a) (may (do ?a)))
"""

NEEDS = """
(gc-need nurture nurturing (scale 0 1) (band 0.6 0.9) (drive 2) (need-source human:designer))
(gc-need calm competence (scale 0 1) (band 0.4 0.6) (drive 1) (need-source human:designer))
(gc-need-expectation empathize nurture 0.3 human-asserted (expectation-source human:designer))
(gc-need-expectation stay_silent nurture 0.0 human-asserted (expectation-source human:designer))
(gc-need-expectation stay_silent calm 0.0 human-asserted (expectation-source human:designer))
"""


# am[verifies a-v2m-levels-1019@387e68]
def at(seconds: float) -> datetime:
    return EPOCH + timedelta(seconds=seconds)


# A stream observation through the store's own constructor, which keeps every rule a record must
# satisfy; `name`, when given, becomes its source, so observations a test tells apart have their
# own ids, which are their identities' fingerprints.
# am[verifies a-v2m-levels-1019@387e68]
def Obs(need: str, level: float, observed_at: datetime, *, estimator: str = "measured",
        scale: tuple[float, float] = (0.0, 1.0), valid_until: datetime | None = None,
        produced_by: str | None = None, source: str = "fixture", name: str = "") -> NeedObservation:
    return NeedObservation(need=need, level=level, scale=scale, estimator=estimator, source=name or source,
                           observed_at=observed_at, valid_until=valid_until, produced_by=produced_by)


# am[verifies a-v2m-expectations-1019@b13468]
def Att(attempt: str, action: str, applied_at: datetime | None, review_fingerprint: str | None = None) -> Attempt:
    return Attempt(attempt=attempt, action=action, applied_at=applied_at, review_fingerprint=review_fingerprint)


# am[verifies a-v2m-levels-1019@387e68]
def History(observations=(), attempts=()) -> MotivationHistory:
    return MotivationHistory(tuple(observations), tuple(attempts), "sha256:fixture")


# am[verifies a-v2m-levels-1019@387e68]
def budget() -> RunBudget:
    return RunBudget(inference_budget=None, timeout_seconds=300)


# am[verifies a-v2m-levels-1019@387e68]
def domain(text: str = CORE + NEEDS) -> Domain:
    return read_domain(text, "companion.metta", budget=budget())


# am[verifies a-v2m-levels-1019@387e68]
def snapshot(regulated: Domain, observations=(), attempts=(), *, now: float = 1000.0,
             stream: str | None = "fixture") -> MotivationSnapshot:
    return motivation_snapshot(regulated, History(tuple(observations), tuple(attempts)), stream=stream,
                               as_of=at(now), budget=budget())


# The reduction formula, written from c-v2m-reduction-formula-1019 independently of the policy.
# am[verifies a-v2m-drive-paths-1019@65a7d5]
def distance(scale: tuple[float, float], band: tuple[float, float], level: float) -> float:
    (lo, hi), (low, high) = scale, band
    span = max(low - lo, hi - high)
    gap = max(low - level, 0.0) + max(level - high, 0.0)
    return min(1.0, gap / span) if span > 0 else 0.0


# am[verifies a-v2m-drive-paths-1019@65a7d5]
def reduction(scale: tuple[float, float], band: tuple[float, float], drive: float, level: float, change: float) -> float:
    moved = min(scale[1], max(scale[0], level + change))
    return math.pow(distance(scale, band, level), drive) - math.pow(distance(scale, band, moved), drive)

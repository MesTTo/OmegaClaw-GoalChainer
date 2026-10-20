"""Purpose: verify the motivation policy's snapshot: each need's level at the review instant, which
attempts give measured samples and why others do not, the learned expected changes with their
residuals, and each action's reduction interval of each need's urgency, against a reference of the
formula written apart from the policy, with input order, provenance and float boundaries."""

from __future__ import annotations

import itertools
import math
import random

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from goal_chainer.domains.needs import Need, NeedSection
from goal_chainer.errors import InvalidInputError
from goal_chainer.relevance.motivation import motivation_snapshot
from motivation_support import CORE, Att, History, Obs, at, budget, domain, reduction, snapshot
from motivation_oracle import expected, random_stream

from dataclasses import replace


# am[verifies a-v2m-levels-1019@387e68]
@pytest.fixture(scope="module")
def companion():
    return domain()


# A need nothing has observed is unobserved, never satisfied, and every change of it is unknown
# except the declared ones.
# am[verifies a-v2m-levels-1019@387e68] am[verifies c-v2m-whole-range-cases-1019@b4864a]
def test_an_empty_stream_leaves_every_need_unobserved_and_only_declared_changes_known(companion) -> None:
    taken = snapshot(companion)

    assert [(level.need, level.state, level.value) for level in taken.levels] == [("nurture", "unobserved", None), ("calm", "unobserved", None)]
    assert taken.change("empathize", "nurture").state == "declared" and taken.change("empathize", "nurture").change == 0.3
    assert taken.change("empathize", "calm").state == "unknown"
    # An unknown level and a known change: the range over the breakpoints; both unknown: [-1, 1].
    assert (taken.reduction("empathize", "calm").low, taken.reduction("empathize", "calm").high) == (-1.0, 1.0)
    assert (taken.reduction("stay_silent", "calm").low, taken.reduction("stay_silent", "calm").high) == (0.0, 0.0)


# am[verifies a-v2m-levels-1019@387e68] am[verifies c-v2m-latest-is-state-1019@c5a57e]
def test_the_latest_observation_at_or_before_the_instant_is_the_level(companion) -> None:
    first, latest, future = Obs("nurture", 0.2, at(10), name="a"), Obs("nurture", 0.7, at(20), name="b"), \
        Obs("nurture", 0.1, at(5000), name="future")
    taken = snapshot(companion, [first, latest, future], now=100)
    level = taken.level("nurture")

    assert (level.state, level.value, level.support) == ("observed", 0.7, ((latest.id, "measured"),))
    assert (level.distance, level.urgency) == (0.0, 0.0)
    # 0.2 against [0.6, 0.9] on [0, 1]: gap 0.4 over the span max(0.6, 0.1) = 0.6, squared.
    early = snapshot(companion, [Obs("nurture", 0.2, at(10), name="a")], now=15).level("nurture")
    assert early.distance == pytest.approx(0.4 / 0.6) and early.urgency == pytest.approx((0.4 / 0.6) ** 2)


# An expired latest observation leaves the level unknown; an older one never stands in for it.
# am[verifies a-v2m-levels-1019@387e68]
def test_an_expired_latest_observation_is_expired_and_never_falls_back(companion) -> None:
    old, new = Obs("nurture", 0.7, at(10), name="old"), Obs("nurture", 0.2, at(20), valid_until=at(30), name="new")
    taken = snapshot(companion, [old, new], now=40)

    assert (taken.level("nurture").state, taken.level("nurture").value) == ("expired", None)
    assert taken.level("nurture").support == ((new.id, "measured"),)


# am[verifies a-v2m-levels-1019@387e68]
def test_simultaneous_disagreeing_observations_are_conflicted_and_agreeing_ones_share_support(companion) -> None:
    x, y = Obs("calm", 0.5, at(10), name="x"), Obs("calm", 0.5, at(10), estimator="model-proposed", name="y")
    conflicted = snapshot(companion, [x, Obs("calm", 0.3, at(10), name="y")])
    agreeing = snapshot(companion, [x, y])

    assert conflicted.level("calm").state == "conflicted"
    assert agreeing.level("calm").state == "observed"
    assert sorted(agreeing.level("calm").support) == sorted([(x.id, "measured"), (y.id, "model-proposed")])


# am[verifies a-v2m-levels-1019@387e68]
def test_an_observation_of_an_undeclared_need_or_on_another_scale_is_excluded(companion) -> None:
    thirst, wide = Obs("thirst", 0.5, at(10), name="t"), Obs("calm", 0.5, at(10), scale=(0.0, 2.0), name="s")
    taken = snapshot(companion, [thirst, wide])

    assert set(taken.excluded) == {(wide.id, "scale-changed"), (thirst.id, "undeclared-need")}
    assert taken.level("calm").state == "unobserved"


# A record the store accepted under an older vocabulary stays readable; the policy excludes it.
# am[verifies a-v2m-levels-1019@387e68] am[verifies a-v2m-snapshot-identity-1019@118a4b]
def test_an_observation_of_an_estimator_class_the_vocabulary_lacks_is_excluded(companion) -> None:
    legacy = Obs("calm", 0.5, at(10), estimator="survey-weighted", name="legacy")
    taken = snapshot(companion, [legacy])

    assert taken.excluded == ((legacy.id, "unknown-estimator"),) and taken.level("calm").state == "unobserved"


# What reaches the policy is the store's own validated records: a duck record, a foreign container
# or a stream that is no text is refused before any engine work, and a record no constructor can
# build never exists.
# am[verifies a-v2m-snapshot-identity-1019@118a4b] am[rests-on c-v2m-store-surface-1019@49737f]
def test_a_history_not_built_from_the_stores_records_is_refused_before_the_engine(companion) -> None:
    from types import SimpleNamespace  # noqa: PLC0415

    from goal_chainer.motivation import MotivationHistory  # noqa: PLC0415

    duck = SimpleNamespace(id="x", need="calm", level=True, scale=(0.0, 1.0), estimator="measured",
                           observed_at=at(10), valid_until=None, produced_by=None)
    refusals = [
        dict(history=MotivationHistory((duck,), (), "sha256:x")),
        dict(history=SimpleNamespace(observations=(), attempts=())),
        dict(history=MotivationHistory([Obs("calm", 0.5, at(10))], (), "sha256:x")),
        dict(history=None, stream=""),
        dict(history=None, stream=7),
    ]
    for arguments in refusals:
        with pytest.raises(InvalidInputError):
            motivation_snapshot(companion, arguments["history"], stream=arguments.get("stream", "s"),
                                as_of=at(100), budget=budget())
    for bad in (dict(level=True), dict(level=float("nan")), dict(level=1.5), dict(observed_at=at(10).replace(tzinfo=None)),
                dict(valid_until=at(5))):
        with pytest.raises(InvalidInputError):
            Obs(**{"need": "calm", "level": 0.5, "observed_at": at(10), **bad})


# One attributed attempt gives one sample: its change, the declared prior it was observed against
# and the residual; the measured mean then replaces the declaration.
# am[verifies a-v2m-expectations-1019@b13468] am[verifies c-v2m-sample-mean-convex-1019@5e2db0]
def test_an_attributed_attempt_is_a_sample_with_its_residual_against_the_declared_change(companion) -> None:
    before, after = Obs("nurture", 0.2, at(10), estimator="human-asserted", name="b"), \
        Obs("nurture", 0.7, at(30), estimator="human-asserted", produced_by="t1", name="a")
    observations = [before, after]
    taken = snapshot(companion, observations, [Att("t1", "empathize", at(20))])

    (sample,) = taken.samples
    assert (sample.key.attempt, sample.key.before, sample.key.after) == ("t1", (before.id,), (after.id,))
    assert sample.change == pytest.approx(0.5) and sample.prior == 0.3 and sample.residual == pytest.approx(0.2)
    change = taken.change("empathize", "nurture")
    assert (change.state, change.samples, change.estimator) == ("measured", 1, "receipt-calibrated")
    assert change.change == pytest.approx(0.5)


# am[verifies a-v2m-expectations-1019@b13468] am[verifies c-v2m-sample-mean-convex-1019@5e2db0]
def test_the_expected_change_is_the_running_mean_of_samples_in_the_order_applied(companion) -> None:
    observations = [Obs("calm", 0.5, at(10), name="c0"), Obs("calm", 0.8, at(30), produced_by="t1", name="c1"),
                    Obs("calm", 0.6, at(50), produced_by="t2", name="c2")]
    attempts = [Att("t2", "guide_breath", at(40)), Att("t1", "guide_breath", at(20))]
    taken = snapshot(companion, observations, attempts)

    first, second = taken.samples
    assert first.key.attempt == "t1" and first.prior is None and first.residual is None
    assert second.key.attempt == "t2" and second.prior == pytest.approx(0.3)
    assert second.change == pytest.approx(-0.2) and second.residual == pytest.approx(-0.5)
    assert taken.change("guide_breath", "calm").change == pytest.approx(0.05)


# Each refusal names the first rule the attempt fails.
# am[verifies a-v2m-expectations-1019@b13468] am[verifies c-v2m-receipt-window-1019@9fe31b] am[verifies c-v2m-window-subject-1019@077441]
@pytest.mark.parametrize(
    "observations, attempts, reason",
    [
        ([Obs("calm", 0.5, at(10)), Obs("calm", 0.7, at(50), produced_by="t1")],
         [Att("t1", "empathize", at(20)), Att("t2", "guide_breath", at(40))], "outside-window"),
        ([Obs("calm", 0.5, at(10)), Obs("calm", 0.7, at(30), produced_by="t1")],
         [Att("t1", "empathize", at(20)), Att("t2", "guide_breath", at(20))], "simultaneous-attempt"),
        ([Obs("calm", 0.5, at(10)), Obs("calm", 0.7, at(30), produced_by="t1", estimator="model-proposed")],
         [Att("t1", "empathize", at(20))], "outcome-not-establishing"),
        ([Obs("calm", 0.5, at(10), estimator="model-proposed"), Obs("calm", 0.7, at(30), produced_by="t1")],
         [Att("t1", "empathize", at(20))], "baseline-not-establishing"),
        ([Obs("calm", 0.7, at(30), produced_by="t1")], [Att("t1", "empathize", at(20))], "no-baseline"),
        ([Obs("calm", 0.5, at(10)), Obs("calm", 0.7, at(30), produced_by="t1", source="p"),
          Obs("calm", 0.6, at(30), produced_by="t1", source="q")],
         [Att("t1", "empathize", at(20))], "conflicted-outcome"),
        ([Obs("calm", 0.5, at(10), source="p"), Obs("calm", 0.4, at(10), source="q"),
          Obs("calm", 0.7, at(30), produced_by="t1")], [Att("t1", "empathize", at(20))], "conflicted-baseline"),
        # The parent's case: a baseline valid until 11 is no pre-state at an application at 20, and the
        # older observation at 5 is never resurrected.
        ([Obs("calm", 0.1, at(5)), Obs("calm", 0.3, at(10), valid_until=at(11)), Obs("calm", 0.6, at(30), produced_by="t1")],
         [Att("t1", "empathize", at(20))], "baseline-expired"),
    ],
)
def test_an_attempt_that_gives_no_sample_says_why(companion, observations, attempts, reason) -> None:
    taken = snapshot(companion, observations, attempts)

    assert [item for item in taken.not_sampled if item[1] == "calm"][0] == (attempts[0].attempt, "calm", reason)
    assert all(sample.need != "calm" or sample.key.attempt != attempts[0].attempt for sample in taken.samples)


# An attempt the host did not apply, or applies after the instant, gives nothing to learn from.
# am[verifies a-v2m-expectations-1019@b13468]
def test_an_unapplied_or_future_attempt_gives_no_sample(companion) -> None:
    observations = [Obs("calm", 0.5, at(10)), Obs("calm", 0.7, at(30), produced_by="t1"), Obs("calm", 0.9, at(70), produced_by="t2")]
    taken = snapshot(companion, observations, [Att("t1", "empathize", None), Att("t2", "empathize", at(60))], now=50)

    assert taken.samples == () and taken.not_sampled == ()
    assert taken.change("empathize", "calm").state == "unknown"


# An endpoint is every agreeing observation at its instant and establishes when any of them does,
# so the order the stream holds them in decides nothing (c-v2m-endpoint-order-free-1019).
# am[verifies a-v2m-expectations-1019@b13468] am[verifies c-v2m-endpoint-order-free-1019@6a9e43]
def test_a_sample_and_its_provenance_do_not_depend_on_the_order_of_the_stream(companion) -> None:
    observations = [Obs("nurture", 0.2, at(10), estimator="model-proposed", name="b1"), Obs("nurture", 0.2, at(10), name="b2"),
                    Obs("nurture", 0.5, at(30), estimator="model-proposed", produced_by="t1", name="a1"),
                    Obs("nurture", 0.5, at(30), produced_by="t1", name="a2")]
    attempts = [Att("t1", "empathize", at(20))]
    identities = {repr(snapshot(companion, list(order), attempts).identity(["empathize"]))
                  for order in itertools.permutations(observations)}

    (identity,) = identities
    (sample,) = snapshot(companion, observations, attempts).samples
    assert (sorted(sample.key.before), sorted(sample.key.after)) == (
        sorted(o.id for o in observations[:2]), sorted(o.id for o in observations[2:]))
    assert "receipt-calibrated" in identity


# The parent's counterexample: band [0.4, 0.6] at level 0.9 with D = max(0.4, 0.4) = 0.4.
# am[verifies a-v2m-drive-paths-1019@65a7d5] am[verifies c-v2m-reduction-formula-1019@0fcd08]
def test_a_change_toward_the_band_reduces_urgency_and_one_away_raises_it() -> None:
    text = CORE + """
(gc-need calm competence (scale 0 1) (band 0.4 0.6) (drive 1) (need-source human:designer))
(gc-need-expectation empathize calm 0.1 measured (expectation-source pilot))
(gc-need-expectation guide_breath calm -0.4 measured (expectation-source pilot))
"""
    taken = snapshot(domain(text), [Obs("calm", 0.9, at(10))])

    assert taken.reduction("empathize", "calm").low == pytest.approx(-0.25)
    assert taken.reduction("guide_breath", "calm").low == pytest.approx(0.75)
    assert taken.reduction("guide_breath", "calm").low == taken.reduction("guide_breath", "calm").high


# A level inside its band can only be kept or left, so no change has a positive reduction: being
# satisfied never asks for more (no endless maximisation).
# am[verifies a-v2m-drive-paths-1019@65a7d5] am[verifies a-v2m-hold-1019@be4f47]
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(level=st.floats(0.6, 0.9), change=st.floats(-1.0, 1.0))
def test_a_level_in_its_band_has_no_positive_reduction(companion, level, change) -> None:
    regulated = replace(companion, motivation=NeedSection(needs=companion.needs, expectations=(
        replace(companion.need_expectations[0], change=change),)))
    taken = snapshot(regulated, [Obs("nurture", level, at(10))])

    assert taken.reduction("empathize", "nurture").high <= 0.0


# The policy's reduction equals the formula's for known levels and changes, and its interval for
# an unknown level contains the formula's value at every level: a dense grid, compared, never the
# source of the bound.
# am[verifies a-v2m-drive-paths-1019@65a7d5] am[verifies c-v2m-breakpoints-1019@8e56ef] am[verifies c-v2m-whole-range-cases-1019@b4864a]
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(low=st.floats(-1.0, 1.0), width=st.floats(0.0, 1.0), drive=st.sampled_from([1.0, 1.5, 2.0, 3.0]),
       level=st.floats(-1.0, 1.0), change=st.floats(-2.0, 2.0))
def test_the_reductions_match_the_formula_and_the_unknown_level_range_holds_every_level(
        companion, low, width, drive, level, change) -> None:
    high = min(1.0, low + width)
    need = Need("calm", "competence", (-1.0, 1.0), (low, high), drive, "test")
    regulated = replace(companion, motivation=NeedSection(needs=(need,), expectations=(
        replace(companion.need_expectations[0], need="calm", change=change),)))
    known = snapshot(regulated, [Obs("calm", level, at(10), scale=(-1.0, 1.0))]).reduction("empathize", "calm")
    unknown = snapshot(regulated).reduction("empathize", "calm")

    expected = reduction(need.scale, need.band, drive, level, change)
    assert known.low == known.high and known.low == pytest.approx(expected, abs=1e-12)
    grid = [reduction(need.scale, need.band, drive, -1.0 + 2.0 * i / 400, change) for i in range(401)]
    assert unknown.low <= min(grid) + 1e-12 and max(grid) - 1e-12 <= unknown.high


# A representable scale near the float limit computes without overflowing: the parent's case
# n = 1.7e308, d = 3e307 on [1.4e308, 1.7e308] stays at the top of the scale.
# am[verifies a-v2m-drive-paths-1019@65a7d5] am[verifies a-v2m-need-forms-1019@6ee59c]
def test_a_scale_near_the_float_limit_never_overflows(companion) -> None:
    need = Need("big", "competence", (1.4e308, 1.7e308), (1.5e308, 1.6e308), 1.0, "test")
    regulated = replace(companion, motivation=NeedSection(needs=(need,), expectations=(
        replace(companion.need_expectations[0], need="big", change=3e307),)))
    taken = snapshot(regulated, [Obs("big", 1.7e308, at(10), scale=(1.4e308, 1.7e308))])

    item = taken.reduction("empathize", "big")
    assert math.isfinite(item.low) and item.low == item.high == 0.0
    assert taken.level("big").urgency == 1.0


# am[verifies a-v2m-snapshot-identity-1019@118a4b]
def test_a_domain_without_needs_or_a_naive_instant_is_refused(companion) -> None:
    from datetime import datetime  # noqa: PLC0415

    plain = domain(CORE)
    with pytest.raises(InvalidInputError, match="declares no needs"):
        motivation_snapshot(plain, History(), stream=None, as_of=at(0), budget=budget())
    with pytest.raises(InvalidInputError, match="timezone offset"):
        motivation_snapshot(companion, History(), stream=None, as_of=datetime(2026, 1, 1), budget=budget())


# Every bound the policy promises holds on arbitrary streams: levels on the scale, urgencies in
# [0, 1], reductions in [-1, 1] and each mean within the range of its samples.
# am[verifies a-v2m-levels-1019@387e68] am[verifies a-v2m-expectations-1019@b13468] am[verifies c-v2m-sample-mean-convex-1019@5e2db0]
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(seed=st.integers(0, 10_000))
def test_every_bound_holds_on_random_streams(companion, seed) -> None:
    pick = random.Random(seed)
    attempts = [Att(f"t{i}", pick.choice(companion.action_ids), at(10 * i + 5)) for i in range(pick.randint(0, 5))]
    observations = [
        Obs(pick.choice(("nurture", "calm")), round(pick.random(), 3), at(pick.randint(0, 60)),
            estimator=pick.choice(("measured", "human-asserted", "model-proposed")),
            produced_by=pick.choice([None, *(a.attempt for a in attempts)]), source=f"s{i}")
        for i in range(pick.randint(0, 12))
    ]
    taken = snapshot(companion, observations, attempts, now=pick.randint(0, 80))

    for level in taken.levels:
        assert level.known == (level.value is not None)
        if level.known:
            assert 0.0 <= level.value <= 1.0 and 0.0 <= level.distance <= 1.0 and 0.0 <= level.urgency <= 1.0
    assert all(-1.0 <= item.low <= item.high <= 1.0 for item in taken.reductions)
    for change in taken.changes:
        if change.state == "measured":
            values = [s.change for s in taken.samples if (s.action, s.need) == (change.action, change.need)]
            assert len(values) == change.samples and min(values) - 1e-12 <= change.change <= max(values) + 1e-12
    shuffled = list(observations)
    pick.shuffle(shuffled)
    assert snapshot(companion, shuffled, list(reversed(attempts)), now=taken.as_of.timestamp() - at(0).timestamp()
                    ).identity(companion.action_ids) == taken.identity(companion.action_ids)


# The exact real reduction at a candidate level, with rationals for an integer exponent: every float
# is a rational, so the band, the change and the level are exact and only the power of a non-integer
# exponent is rounded, once.
# am[verifies a-v2m-exact-candidates-1019@98545a]
def _exact(need: Need, level, change, drive: float):
    from fractions import Fraction  # noqa: PLC0415

    lo, hi = map(Fraction, need.scale)
    low, high = map(Fraction, need.band)
    span = max(low - lo, hi - high)

    def urgency(value):
        gap = max(low - value, Fraction(0)) + max(value - high, Fraction(0))
        x = gap / span if span else Fraction(0)
        return x ** int(drive) if drive == int(drive) else Fraction(float(x) ** drive)

    return urgency(level) - urgency(min(hi, max(lo, level + change)))


# elton-hwang's case (i-v2li-float-round-trip-1020), band [0.05, 0.65] and change -0.19, at exponents
# the runtime accepts: the unknown-level interval is the real candidate extremes to float accuracy,
# since a shifted candidate's target is its band edge exactly and no n + d is rounded across it.
# am[verifies a-v2m-exact-candidates-1019@98545a] am[verifies c-v2m-candidate-differences-1019@741b12]
@pytest.mark.parametrize("drive", [1.0, 1.5, 2.0])
def test_elton_hwangs_band_and_change_reach_the_real_candidate_extremes(companion, drive) -> None:
    from fractions import Fraction  # noqa: PLC0415

    need = Need("calm", "competence", (0.0, 1.0), (0.05, 0.65), drive, "test")
    regulated = replace(companion, motivation=NeedSection(needs=(need,), expectations=(
        replace(companion.need_expectations[0], need="calm", change=-0.19),)))
    item = snapshot(regulated).reduction("empathize", "calm")

    change = Fraction(-0.19)
    ends = [Fraction(value) for value in (*need.scale, *need.band)]
    candidates = [*ends, *(b - change for b in ends if Fraction(need.scale[0]) <= b - change <= Fraction(need.scale[1]))]
    values = [_exact(need, level, change, drive) for level in candidates]
    assert item.low == pytest.approx(float(min(values)), abs=1e-15)
    assert item.high == pytest.approx(float(max(values)), abs=1e-15)


# A narrow band on a scale far from 0 and an enormous exponent stay finite and typed: every level
# and reduction is a number inside its bounds, never NaN or an overflow.
# am[verifies a-v2m-exact-candidates-1019@98545a] am[verifies c-v2m-drive-convex-1019@292811]
@pytest.mark.parametrize(
    "scale, band, drive, level, change",
    [
        ((1e8, 1e8 + 1e-3), (1e8 + 4e-4, 1e8 + 4e-4 + 1e-9), 1.5, 1e8 + 9e-4, -5e-4),
        ((0.0, 1.0), (0.5, 0.5 + 1e-12), 1.0, 0.9, -0.4),
        ((0.0, 1.0), (0.4, 0.6), 1e6, 0.9, -0.4),
        ((0.0, 1.0), (0.4, 0.6), 1e300, 0.0, 0.3),
    ],
)
def test_narrow_bands_and_large_exponents_stay_finite_and_bounded(companion, scale, band, drive, level, change) -> None:
    need = Need("calm", "competence", scale, band, drive, "test")
    regulated = replace(companion, motivation=NeedSection(needs=(need,), expectations=(
        replace(companion.need_expectations[0], need="calm", change=change),)))
    for observations in ([Obs("calm", level, at(10), scale=scale)], []):
        taken = snapshot(regulated, observations)
        item = taken.reduction("empathize", "calm")
        assert all(math.isfinite(value) for value in (item.low, item.high)) and -1.0 <= item.low <= item.high <= 1.0
        known = taken.level("calm")
        if known.known:
            assert 0.0 <= known.distance <= 1.0 and 0.0 <= known.urgency <= 1.0


# The vocabulary's classes and which of them establish, read through the vocabulary's own rule.
# am[verifies a-v2m-snapshot-sweep-1020@fefbd6]
@pytest.fixture(scope="module")
def vocabulary_classes():
    from goal_chainer.domains.loader import vocabulary  # noqa: PLC0415
    from relevance_support import helper_call  # noqa: PLC0415

    classes = vocabulary().classes
    return classes, {name for name in classes if helper_call("gc-establishes", name) is True}


# The snapshot's records, held to the oracle and to themselves under shuffled, repeated input.
# am[verifies a-v2m-snapshot-sweep-1020@fefbd6]
def _held_to_oracle(companion, vocabulary_classes, observations, attempts, now: float) -> dict:
    classes, establishing = vocabulary_classes
    taken = snapshot(companion, observations, attempts, now=now).to_dict()
    wanted = expected(companion, observations, attempts, at(now), classes=classes, establishing=establishing)
    assert {part: taken[part] for part in wanted} == wanted
    return taken


# The cases a traversal most easily gets wrong, each held to the oracle: two attempts at one instant;
# a window the stream's next applied attempt closes, whatever its action; a latest baseline that
# expired before the application, with an older valid one that must not stand in; an outcome whose
# validity ran out before the review; agreeing and disagreeing observations sharing an instant; and
# a record repeated.
# am[verifies a-v2m-snapshot-sweep-1020@fefbd6] am[verifies c-v2m-window-subject-1019@077441] am[verifies c-v2m-endpoint-order-free-1019@6a9e43]
def test_the_sweep_answers_what_the_oracle_does_on_its_hardest_cases(companion, vocabulary_classes) -> None:
    cases = {
        "simultaneous": ([Obs("nurture", 0.3, at(5)), Obs("nurture", 0.5, at(12), produced_by="a1"),
                          Obs("nurture", 0.6, at(12), produced_by="a2", name="b")],
                         [Att("a1", "empathize", at(10)), Att("a2", "stay_silent", at(10))]),
        "next-applied": ([Obs("nurture", 0.3, at(5)), Obs("nurture", 0.5, at(25), produced_by="a1")],
                         [Att("a1", "empathize", at(10)), Att("a2", "stay_silent", at(20))]),
        "expired-latest": ([Obs("nurture", 0.3, at(5)), Obs("nurture", 0.4, at(8), valid_until=at(9)),
                            Obs("nurture", 0.6, at(12), produced_by="a1")],
                           [Att("a1", "empathize", at(10))]),
        "outcome-expired": ([Obs("nurture", 0.3, at(5)), Obs("nurture", 0.6, at(12), valid_until=at(13), produced_by="a1")],
                            [Att("a1", "empathize", at(10))]),
        "tied-agreeing": ([Obs("calm", 0.5, at(5)), Obs("calm", 0.4, at(12), produced_by="a1"),
                           Obs("calm", 0.4, at(12), produced_by="a1", estimator="model-proposed", name="b")],
                          [Att("a1", "guide_breath", at(10))]),
        "tied-conflicting": ([Obs("calm", 0.5, at(5)), Obs("calm", 0.4, at(12), produced_by="a1"),
                              Obs("calm", 0.3, at(12), produced_by="a1", name="b")],
                             [Att("a1", "guide_breath", at(10))]),
        "repeated": ([Obs("nurture", 0.3, at(5))] * 2 + [Obs("nurture", 0.6, at(12), produced_by="a1")],
                     [Att("a1", "empathize", at(10))] * 2),
    }
    reasons = {}
    for name, (observations, attempts) in cases.items():
        taken = _held_to_oracle(companion, vocabulary_classes, observations, attempts, 30.0)
        reasons[name] = [item["reason"] for item in taken["not_sampled"]] or [len(taken["samples"])]
    assert reasons == {"simultaneous": ["simultaneous-attempt", "simultaneous-attempt"], "next-applied": ["outside-window"],
                       "expired-latest": ["baseline-expired"], "outcome-expired": [1], "tied-agreeing": [1],
                       "tied-conflicting": ["conflicted-outcome"], "repeated": [1]}


# On any stream, ties, foreign producers, other scales, unknown classes, expiries and attempts after
# the instant included, the snapshot's samples, reasons, changes and exclusions are the oracle's,
# and shuffling or repeating the stream's records changes nothing in the snapshot.
# am[verifies a-v2m-snapshot-sweep-1020@fefbd6] am[verifies c-v2m-endpoint-order-free-1019@6a9e43]
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(seed=st.integers(0, 10**6))
def test_the_sweep_answers_what_the_oracle_does_on_any_stream(companion, vocabulary_classes, seed) -> None:
    pick = random.Random(seed)
    observations, attempts, now = random_stream(pick, companion.action_ids)
    taken = _held_to_oracle(companion, vocabulary_classes, observations, attempts, now)

    shuffled = observations + pick.sample(observations, k=min(3, len(observations)))
    pick.shuffle(shuffled)
    again = attempts + attempts[:1]
    pick.shuffle(again)
    # The history names what was read, so repeated records change its count; nothing derived changes.
    again_taken = snapshot(companion, shuffled, again, now=now).to_dict()
    assert {**again_taken, "history": None} == {**taken, "history": None}


# A record repeated in a history counts once, as the store keeps it once; only the history reference
# names what was given, repeats included. Two different attempts under one attempt id are no
# stream's history and are refused before the engine runs.
# am[verifies a-v2m-snapshot-sweep-1020@fefbd6] am[verifies a-v2r-record-digest-1020]
def test_a_repeated_record_counts_once_and_a_conflicting_attempt_is_refused(companion) -> None:
    observations = [Obs("nurture", 0.3, at(5)), Obs("nurture", 0.6, at(12), produced_by="a1")]
    once = snapshot(companion, observations, [Att("a1", "empathize", at(10))])
    twice = snapshot(companion, observations * 2, [Att("a1", "empathize", at(10))] * 2)

    assert {**twice.to_dict(), "history": None} == {**once.to_dict(), "history": None} and len(once.samples) == 1
    assert (once.history.event_count, twice.history.event_count) == (3, 6)
    with pytest.raises(InvalidInputError, match="states attempt a1 otherwise"):
        snapshot(companion, observations, [Att("a1", "empathize", at(10)), Att("a1", "guide_breath", at(10))])

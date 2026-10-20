"""Purpose: check the mathematical contracts the relevance review and SNARS keep against generated
cases on the actual MeTTa policies: robust order over intervals under relabeling, the authority
ceiling, outcome and signal statuses that never turn a model claim or an unknown into a fact, one
evidence identity counted once, and the ordinal-sum counterexample; and check that the planning model
record proofs/PlanningModel.lean's main compares the Lean model with is what planning_oracle answers now.
Generated regulated-need cases compare the native arithmetic with exact rational calculations and
check the interval and invariance contracts of proofs/Motivation.lean; generated binary64 needs over
the whole accepted domain compare every reduction's sign with the real model's and its magnitude with
an 800-digit evaluation of it."""

from decimal import Context, Decimal, localcontext
from fractions import Fraction as Q
import json
import math
from pathlib import Path
import sys

from hypothesis import given, settings, strategies as st
import pytest

from goal_chainer.domains.needs import Need
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.relevance import parse_packet
from goal_chainer.relevance.policy import constant, evaluate as review_policy, is_nothing, items, term
from goal_chainer.relevance.ranking import rank
from goal_chainer.snars_models import EvidenceCounts
from goal_chainer.snars_reasoner import SnarsSession

from relevance_support import candidate, derived, helper_call, reviewed, task_control
from reading_support import incident_reader
from record_planning_model_conformance import RECORDED, text as planning_model_record


# am[verifies a-math-conformance-1016@9e5589]
def budget():
    return RunBudget(inference_budget=50_000_000, timeout_seconds=120)


# am[verifies a-math-conformance-1016@9e5589]
def policy(function, *arguments):
    return review_policy(function, *arguments, budget=budget())


# Time: linear in the generated dimension count; no policy ranking helper computes the oracle.
# am[verifies a-math-conformance-1016@9e5589]
@settings(max_examples=60, deadline=None)
@given(st.lists(st.tuples(st.integers(-3, 3), st.integers(-3, 3),
                         st.integers(-3, 3), st.integers(-3, 3),
                         st.booleans(), st.booleans()), min_size=1, max_size=5))
def test_actual_robust_pareto_is_ordinal_and_never_fills_an_unknown_with_neutral(coordinates):
    pairs = []
    for al, ah, bl, bh, ak, bk in coordinates:
        pairs.append((tuple(sorted((al, ah))) if ak else (-3, 3),
                      tuple(sorted((bl, bh))) if bk else (-3, 3), ak, bk))
    expected = (all(a[0] >= b[1] for a, b, ak, bk in pairs if ak or bk)
                and any(a[0] > b[1] for a, b, ak, bk in pairs if ak or bk))
    for relabel in (dict(zip(range(-3, 4), range(-3, 4))),
                    dict(zip(range(-3, 4), (-30, -8, -1, 0, 2, 3, 19)))):
        left, right = [], []
        for index, (a, b, ak, bk) in enumerate(pairs):
            left.append(term("Coordinate", term("Dimension", f"d{index}"), relabel[a[0]], relabel[a[1]], ak))
            right.append(term("Coordinate", term("Dimension", f"d{index}"), relabel[b[0]], relabel[b[1]], bk))
        result = helper_call("gc-relevance-dominates", items(left), items(right))
        assert (isinstance(result, tuple) and str(result[0]) == "Some") == expected
    unknown = helper_call("gc-relevance-interval-of", items(()))
    assert str(unknown[0]) == "Interval" and unknown[1:] == (-1.0, 1.0)


# Each observation is made after the application at microsecond 10, which follows the review at
# microsecond 0, so only its class and its agreement with the others decide.
# am[verifies a-math-conformance-1016@9e5589] am[related a-rel-rcpt-v2-counting-1017@ae46fe]
def test_model_claims_never_establish_an_effect_and_conflicting_observations_stay_conflicted():
    applied, window = term("Attempt", "a", term("Applied", 10)), constant("Forever")
    unapplied, unstated = term("Attempt", "a", constant("NotApplied")), constant("Unstated")
    prediction = items((term("Prediction", "effect", "privacy"),))
    guessed = items((term("Observation", 0, "effect", "privacy", "confirmed", "model-proposed", term("At", 20), unstated),))
    opposing = items((term("Observation", 1, "effect", "privacy", "confirmed", "measured", term("At", 20), unstated),
                      term("Observation", 2, "effect", "privacy", "contradicted", "deterministic", term("At", 30), unstated)))
    assert policy("gc-relevance-assess", applied, 0, window, prediction, items(()))[1][0][3] == "predicted"
    assert policy("gc-relevance-assess", applied, 0, window, prediction, guessed)[1][0][3] == "predicted"
    assert policy("gc-relevance-assess", applied, 0, window, prediction, opposing)[1][0][3] == "conflicted"
    assert policy("gc-relevance-assess", unapplied, 0, window, prediction, opposing)[1][0][3] == "not-attempted"


# am[verifies a-math-conformance-1016@9e5589] am[verifies a-rel-rr-projection-1018@a05ccf]
def test_unknown_expired_and_conflicting_signals_never_become_positive_facts():
    forever = constant("Forever")
    cases = (
        ((), "unknown"),
        ((term("Reading", "s", "detected", "measured", term("Until", 9), 0),), "unknown"),
        ((term("Reading", "s", "detected", "measured", term("Until", 10), 0),), "detected"),
        ((term("Reading", "s", "refuted", "measured", forever, 0),), "refuted"),
        ((term("Reading", "s", "detected", "measured", forever, 0),
          term("Reading", "s", "refuted", "deterministic", forever, 1)), "conflicted"),
        # A contrary of a lower tier is overruled by the adopted preference, not outvoted.
        ((term("Reading", "s", "detected", "measured", forever, 0),
          term("Reading", "s", "refuted", "model-proposed", forever, 1)), "detected"),
    )
    for readings, expected in cases:
        result = policy("gc-relevance-effective", 10, items(readings), items(("s",)))
        assert str(result[0][0]) == "Effective"
        assert result[0][1:3] == ("s", expected)
        if expected in ("unknown", "conflicted"):
            assert is_nothing(result[0][3])
        else:
            assert str(result[0][3][0]) == "Some"
            assert str(result[0][3][1][0]) == "Fact"
            assert result[0][3][1][1:] == ("s", expected == "detected")


# am[verifies a-math-conformance-1016@9e5589]
def test_one_evidence_identity_does_not_amplify_native_support():
    statement = '(sn p so "is" ((arg s (sn c "checked")) (arg o (sn c "safe"))))'
    with SnarsSession.ephemeral(budget=budget(), reader=incident_reader()) as session:
        first = session.believe(statement, evidence=EvidenceCounts(2, 1, 0.5), source="memory:shared-id")
        digest = session.store.state_digest()
        for _ in range(3):
            again = session.believe(statement, evidence=EvidenceCounts(2, 1, 0.5), source="memory:shared-id")
            assert (again.evidence, again.opinion, again.receipts) == (first.evidence, first.opinion, first.receipts)
            assert session.store.state_digest() == digest
        assert len(session.store.events()) == 1


# am[verifies a-math-conformance-1016@9e5589]
def test_actual_review_keeps_model_authority_advisory_and_external_grants_unresolved():
    domain = task_control()
    path = Path(__file__).resolve().parents[1] / "examples/relevance/chemistry-contention.packet.json"
    result = reviewed(domain, parse_packet(json.loads(path.read_text()))).to_dict()
    assert result["disposition"] == "propose"
    assert result["applies_effects"] is False
    assert result["proposal"]["authorization"] == "unresolved"
    assert result["proposal"]["licensed_authority_ceiling"] == "advisory"


# am[verifies a-math-conformance-1016@9e5589]
def test_model_authority_ceiling_and_appraisals_survive_an_irrelevant_forbidden_candidate():
    domain = task_control()
    action = candidate(domain, "pause_recoverably", effects={"option-value": ("positive", "model-proposed")})
    irrelevant = candidate(domain, "handoff", modes="F")
    alone = rank(derived(domain, [action]), budget())
    joined = rank(derived(domain, [action, irrelevant]), budget())
    assert alone.appraisals[action.id] == joined.appraisals[action.id]
    assert alone.appraisals[action.id].licensed_authority_ceiling == "advisory"


# am[verifies a-math-conformance-1016@9e5589]
def test_ordinal_sums_have_a_concrete_relabeling_counterexample():
    # The order 0 < 2/3 < 1 survives, but the winner of the two sums reverses.
    assert Q(2, 3) + Q(2, 3) > 0 + 1
    relabel = {Q(0): 0, Q(2, 3): Q(1, 10), Q(1): 1}
    assert relabel[Q(2, 3)] + relabel[Q(2, 3)] < relabel[Q(0)] + relabel[Q(1)]


# The record scripts/check-mathematical-contracts.sh has the Lean model check itself against is what
# planning_oracle answers on this revision: recording again gives the committed record byte for byte, so the
# Lean model and the oracle the acceptance tests use cannot drift apart unseen. Rewrite the record with
# `python tests/record_planning_model_conformance.py` when the oracle changes.
# am[verifies a-jk-pf-conformance-1019@8a012a]
def test_the_planning_model_record_is_what_the_oracle_answers_now():
    assert RECORDED.read_text() == planning_model_record()


# Integer coordinates make the reference calculation exact; translation and positive scaling
# exercise the same need expressed in different measurement units.
# am[verifies a-v2-lean-conformance-1020@8abaca]
@st.composite
def regulated_need_cases(draw):
    width = draw(st.integers(1, 24))
    low = draw(st.integers(0, width))
    high = draw(st.integers(low, width))
    level = draw(st.integers(0, width))
    change = draw(st.integers(-width, width))
    power = draw(st.integers(1, 5))
    offset = draw(st.integers(-100, 100))
    unit = draw(st.integers(1, 7))
    return width, low, high, level, change, power, offset, unit


# Distance from a closed interval, divided by the farthest endpoint's distance. This oracle
# uses rational arithmetic and interval projection, independently of the native floating code.
# am[verifies a-v2-lean-conformance-1020@8abaca]
def rational_drive(width, low, high, level, power):
    margin = max(low, width - high)
    nearest = min(max(level, low), high)
    return (Q(abs(level - nearest)) / margin) ** power if margin else Q(0)


# am[verifies a-v2-lean-conformance-1020@8abaca]
def rational_reduction(width, low, high, level, change, power):
    after = min(max(level + change, 0), width)
    return (rational_drive(width, low, high, level, power)
            - rational_drive(width, low, high, after, power))


# Time: four native calls and constant-size rational arithmetic per generated case.
# am[verifies a-v2-lean-conformance-1020@8abaca]
@settings(max_examples=60, deadline=None)
@given(regulated_need_cases())
def test_native_need_drive_and_reduction_match_exact_arithmetic_across_measurement_units(case):
    width, low, high, level, change, power, offset, unit = case
    urgency = rational_drive(width, low, high, level, power)
    reduction = rational_reduction(width, low, high, level, change, power)
    assert 0 <= urgency <= 1 and -1 <= reduction <= 1
    if low <= level <= high:
        assert urgency == 0 and reduction <= 0
    for origin, scale in ((0, 1), (offset, unit)):
        need = term("Need", "need", "goal", float(origin), float(origin + scale * width),
                    float(origin + scale * low), float(origin + scale * high), float(power))
        observed = float(origin + scale * level)
        shifted = float(scale * change)
        assert helper_call("gc-motivation-urgency", need, observed) == pytest.approx(float(urgency), rel=2e-12, abs=2e-12)
        interval = helper_call("gc-motivation-interval", need, term("Known", observed), term("Known", shifted))
        assert str(interval[0]) == "Interval"
        assert interval[1:] == pytest.approx((float(reduction), float(reduction)), rel=2e-12, abs=2e-12)


# Time: three native calls, at most eight exact endpoint values and 25 interior values per case.
# am[verifies a-v2-lean-conformance-1020@8abaca]
@settings(max_examples=60, deadline=None)
@given(regulated_need_cases())
def test_native_need_unknown_intervals_match_the_exact_model_within_numeric_tolerance(case):
    width, low, high, level, change, power, _, _ = case
    need = term("Need", "need", "goal", 0.0, float(width), float(low), float(high), float(power))
    known = term("Known", float(change))
    unknown = constant("Unknown")
    interval = helper_call("gc-motivation-interval", need, unknown, known)
    endpoints = {Q(point) for edge in (0, low, high, width) for point in (edge, edge - change)
                 if 0 <= point <= width}
    values = [rational_reduction(width, low, high, n, change, power) for n in endpoints]
    expected = (min(values), max(values))
    assert str(interval[0]) == "Interval"
    assert interval[1:] == pytest.approx(tuple(map(float, expected)), rel=2e-12, abs=2e-12)
    for index in range(25):
        value = rational_reduction(width, low, high, Q(width * index, 24), change, power)
        assert expected[0] <= value <= expected[1]
    top = 0 if (low, high) == (0, width) else 1
    urgency = rational_drive(width, low, high, level, power)
    level_known = helper_call("gc-motivation-interval", need, term("Known", float(level)), unknown)
    both_unknown = helper_call("gc-motivation-interval", need, unknown, unknown)
    assert str(level_known[0]) == str(both_unknown[0]) == "Interval"
    assert level_known[1:] == pytest.approx((float(urgency - top), float(urgency)), rel=2e-12, abs=2e-12)
    assert both_unknown[1:] == (-top, top)


# The same semantic counterexample for the supported linear and convex urgency: an in-band destination
# eliminates all drive, while moving farther from the band increases it.
# am[verifies a-v2-lean-conformance-1020@8abaca]
@pytest.mark.parametrize("power", [1.0, 1.5, 3.0])
def test_native_need_fractional_powers_preserve_the_direction_of_band_reduction(power):
    need = term("Need", "need", "goal", 0.0, 1.0, 0.4, 0.6, power)
    closer = helper_call("gc-motivation-interval", need, term("Known", 0.9), term("Known", -0.4))
    farther = helper_call("gc-motivation-interval", need, term("Known", 0.9), term("Known", 0.1))
    assert closer[1:] == pytest.approx((0.75 ** power, 0.75 ** power), rel=2e-12, abs=2e-12)
    assert farther[1:] == pytest.approx((0.75 ** power - 1, 0.75 ** power - 1), rel=2e-12, abs=2e-12)
    # For a convex power the extrema are adjacent to the scale's endpoints;
    # symmetry makes the negative bound its twin.
    extent = 1 - 0.75 ** power
    unknown = helper_call("gc-motivation-interval", need, constant("Unknown"), term("Known", 0.1))
    assert unknown[1:] == pytest.approx((-extent, extent), rel=2e-12, abs=2e-12)


DBL_MAX = sys.float_info.max
UNIT = Q(1, 2 ** 53)
LEAST_NORMAL = Q(1, 2 ** 1022)
# The largest relative error a reported magnitude may show here, in units of (1 + |ln u|) 2^-53, u
# the larger of the move's two real urgencies: ln u = K ln(g / S) carries every rounding of g / S
# times K, which an evaluation in doubles cannot avoid; a value may also miss by 4 subnormal steps.
# The most any of 603,005 generated designs needed was 4.7 (c-v2r-magnitude-error-measured-1020);
# 8 is a regression bound with headroom, not a proved one.
MAGNITUDE_TOLERANCE = 8
SUBNORMAL_SLACK = Q(4, 2 ** 1074)
# Enough digits for the real model on binary64 inputs: two gaps differ by at least 2^-1074 on a
# span of at most 2^1023, so an urgency's difference from another needs at most 632 of them.
EXACT = Context(prec=800, Emin=-(10 ** 15), Emax=10 ** 15)


# A binary64 design over the whole domain needs.py accepts: a scale from a subnormal width to 2^1022
# placed anywhere it stays finite, a band drawn inside it, K anywhere in [1, the largest double], a
# level at or within a few ulps of a scale end or band edge or anywhere on the scale, and a change
# aimed at a band edge, a scale end or the level's mirror across the band, a few subnormal steps, or
# any finite double. Every case is a Need the domain loader accepts.
# am[verifies a-v2r-exact-sign-1020] am[verifies a-v2r-stable-magnitude-1020]
@st.composite
def binary64_need_cases(draw):
    width = draw(st.one_of(st.sampled_from([1.0, 0.3, 12.9, 1e-10, 2.0 ** -1000, 5e-324, 1e300, 2.0 ** 1022]),
                           st.floats(min_value=5e-324, max_value=2.0 ** 1022)))
    lo = draw(st.one_of(st.sampled_from([0.0, -1.0, 1e-300, 5e-324, -width / 2, 2.0 ** 1022 - width]),
                        st.floats(min_value=-(2.0 ** 1022), max_value=2.0 ** 1022)))
    hi = max(lo + width, math.nextafter(lo, math.inf))
    bounds = st.floats(min_value=lo, max_value=hi)
    power = draw(st.one_of(st.sampled_from([1.0, math.nextafter(1.0, 2.0), 1.5, 2.0, 3.0, 1e3, 1e16, 1e100, 1e308, DBL_MAX]),
                           st.floats(min_value=1.0, max_value=DBL_MAX)))
    need = Need("need", "goal", (lo, hi), tuple(sorted((draw(bounds), draw(bounds)))), power, "human:designer")
    (lo, hi), (low, high) = need.scale, need.band
    edges = st.sampled_from([lo, low, high, hi])
    near = st.builds(lambda edge, steps: edge + steps * math.ulp(edge), edges, st.integers(-4, 4))
    level = min(hi, max(lo, draw(st.one_of(edges, near, bounds)))) + 0.0
    target = min(hi, max(lo, draw(st.one_of(bounds, st.sampled_from([lo, low, high, hi, 2 * low - level, 2 * high - level])))))
    change = draw(st.one_of(st.just(target - level), st.builds(lambda steps: steps * 5e-324, st.integers(-8, 8)),
                            st.floats(allow_nan=False, allow_infinity=False))) + 0.0
    return lo, hi, low, high, level, change, need.drive


# The real model's span and the exact gaps of a level and of its clamped target, in rationals.
# am[verifies a-v2r-exact-sign-1020] am[verifies a-v2r-stable-magnitude-1020]
def exact_gaps(lo, hi, low, high, level, change):
    lo, hi, low, high, level, change = map(Q, (lo, hi, low, high, level, change))
    gap = lambda value: max(low - value, 0) + max(value - high, 0)  # noqa: E731
    return max(low - lo, hi - high), gap(level), gap(min(hi, max(lo, level + change)))


# The real urgency (g / S)^K at 800 digits, from the exact ratio g / S.
# am[verifies a-v2r-stable-magnitude-1020]
def real_urgency(gap, span, power):
    if gap == 0:
        return Decimal(0)
    ratio = gap / span
    with localcontext(EXACT):
        return (Decimal(power) * (Decimal(ratio.numerator) / Decimal(ratio.denominator)).ln()).exp()


# The real reduction from gap a to gap b with what a magnitude's error is measured against: its value,
# its sign, which is that of a - b whatever K (c-v2r-sign-invariant-1020), and 1 + |ln u| for u the
# larger urgency.
# am[verifies a-v2r-stable-magnitude-1020]
def real_move(a, b, span, power):
    if span == 0:
        return Decimal(0), 0, Decimal(1)
    with localcontext(EXACT):
        start = real_urgency(max(a, b), span, power)
        weight = 1 - start.ln() if start else Decimal("Infinity")
        return real_urgency(a, span, power) - real_urgency(b, span, power), (a > b) - (a < b), weight


# Whether a reported value agrees with the real one: the real sign exactly, 0.0 allowed only where
# the real value is below the least normal double; at most 1 in size; and a relative error within
# MAGNITUDE_TOLERANCE (1 + |ln u|) 2^-53, plus SUBNORMAL_SLACK.
# am[verifies a-v2r-exact-sign-1020] am[verifies a-v2r-stable-magnitude-1020]
def agrees(reported, real):
    value, sign, weight = real
    if not (isinstance(reported, float) and abs(reported) <= 1.0):
        return False
    if reported == 0.0:
        return sign == 0 or abs(value) < Decimal(LEAST_NORMAL.numerator) / Decimal(LEAST_NORMAL.denominator)
    if (reported > 0) - (reported < 0) != sign:
        return False
    with localcontext(EXACT):
        allowed = MAGNITUDE_TOLERANCE * weight * abs(value) / 2 ** 53 + Decimal(SUBNORMAL_SLACK.numerator) / Decimal(SUBNORMAL_SLACK.denominator)
        return abs(Decimal(reported) - value) <= allowed


# Every value the policy reports for a need agrees with the real model's on the same binary64 inputs:
# the level's urgency, the point for a known level and change, both ends of a known level's range
# under an unknown change, [u(n) - 1, u(n)], and both ends of an unknown level's range, whose real
# ends are the least and greatest values at the clipped breakpoints (MotivationIntervals.lean). The
# predicted level is the clamped target rounded to nearest.
# Time: five native calls and at most twelve 800-digit evaluations per case.
# am[verifies a-v2r-exact-sign-1020] am[verifies a-v2r-predicted-level-1020] am[verifies c-v2r-sign-invariant-1020]
# am[verifies a-v2r-stable-magnitude-1020]
@settings(max_examples=150, deadline=None, derandomize=True)
@given(binary64_need_cases())
def test_native_need_values_have_the_real_sign_and_measured_magnitude(case):
    lo, hi, low, high, level, change, power = case
    need = term("Need", "need", "goal", lo, hi, low, high, power)
    span, start, end = exact_gaps(lo, hi, low, high, level, change)
    top = Q(1) if span else Q(0)

    urgency = helper_call("gc-motivation-urgency", need, level)
    assert agrees(urgency, real_move(start, Q(0), span, power)), (case, urgency)
    point = helper_call("gc-motivation-interval", need, term("Known", level), term("Known", change))
    assert point[1] == point[2] and agrees(point[1], real_move(start, end, span, power)), (case, point)
    ranged = helper_call("gc-motivation-interval", need, term("Known", level), constant("Unknown"))
    assert agrees(ranged[1], real_move(start, span * top, span, power)), (case, ranged)
    assert agrees(ranged[2], real_move(start, Q(0), span, power)), (case, ranged)

    moves = [real_move(*exact_gaps(lo, hi, low, high, b, change)[1:], span, power)
             for b in {b for edge in (lo, low, high, hi) for b in (Q(edge), Q(edge) - Q(change)) if Q(lo) <= b <= Q(hi)}]
    weight = max(move[2] for move in moves)
    least = min(moves, key=lambda move: (move[1], move[0]))
    greatest = max(moves, key=lambda move: (move[1], move[0]))
    ranged = helper_call("gc-motivation-interval", need, constant("Unknown"), term("Known", change))
    assert agrees(ranged[1], (least[0], least[1], weight)) and agrees(ranged[2], (greatest[0], greatest[1], weight)), (case, ranged)

    predicted = helper_call("gc-motivation-predicted", need, term("Known", level), term("Known", change))
    clamped = float(min(Q(hi), max(Q(lo), Q(level) + Q(change))))
    assert (predicted[1], predicted[2]) == (clamped, clamped)


# The reductions where the inputs' rounding once decided the magnitude, beside their real values
# rounded from 800 digits: a gap at the span with a change too small to move its rounded value, at K
# from 1 to the largest double (i-v2r-first-order-large-k-1020, where the first-order term gave 0.5 at
# K = 1e16 and 5e291 at K = 1e308); the same step one subnormal wide, whose ratio to the gap is
# subnormal; a step of one ulp at the top of the widest scale needs.py accepts, [-2^1021, 2^1021];
# and a fractional K near the span.
# am[verifies a-v2r-stable-magnitude-1020]
@pytest.mark.parametrize("lo, hi, low, high, level, change, power, expected", [
    (0.0, 1.0, 0.0, 0.0, 1.0, -5e-17, 1.0, 5e-17),
    (0.0, 1.0, 0.0, 0.0, 1.0, -5e-17, 1e16, 0.3934693402873666),
    (0.0, 1.0, 0.0, 0.0, 1.0, -5e-17, 1e100, 1.0),
    (0.0, 1.0, 0.0, 0.0, 1.0, -5e-17, 1e308, 1.0),
    (0.0, 1.0, 0.0, 0.0, 1.0, -5e-17, DBL_MAX, 1.0),
    (0.0, 1.0, 0.0, 0.0, 1.0, -5e-324, 1e308, 4.940656458412465e-16),
    (-(2.0 ** 1021), 2.0 ** 1021, -(2.0 ** 1021), -(2.0 ** 1021), 2.0 ** 1021, -(2.0 ** 969), 1e16, 0.6705145304930524),
    (0.0, 1.0, 0.25, 0.25, 1.0, -1e-16, 1.5, 2e-16),
])
def test_reductions_near_the_span_keep_their_real_magnitude(lo, hi, low, high, level, change, power, expected):
    Need("need", "goal", (lo, hi), (low, high), power, "human:designer")
    need = term("Need", "need", "goal", lo, hi, low, high, power)
    point = helper_call("gc-motivation-interval", need, term("Known", level), term("Known", change))
    span, start, end = exact_gaps(lo, hi, low, high, level, change)
    real = real_move(start, end, span, power)
    assert point[1] == point[2] and agrees(point[1], real), (point, float(real[0]))
    assert point[1] == pytest.approx(expected, rel=1e-13)


# An expansion's value, its components summed from the smallest, is within 4.5 (1 + 2^-53)^m 2^-53 of
# its exact sum relative to it for m components, and its largest component has that sum's sign, on
# terms that cancel to a few ulps of the largest (c-v2r-expansion-value-1020).
# Time: two native calls and one exact sum per case.
# am[verifies a-v2r-stable-magnitude-1020] am[verifies c-v2r-expansion-value-1020]
@settings(max_examples=150, deadline=None, derandomize=True)
@given(st.data())
def test_an_expansion_value_is_within_a_few_units_of_its_exact_sum(data):
    finite = st.floats(min_value=-(2.0 ** 1000), max_value=2.0 ** 1000)
    terms = [data.draw(finite)]
    for _ in range(data.draw(st.integers(1, 5))):
        cancel = st.builds(lambda steps, last=terms[-1]: steps * math.ulp(last) - last, st.integers(-8, 8))
        terms.append(data.draw(st.one_of(finite, cancel, st.builds(lambda steps: steps * 5e-324, st.integers(-8, 8)))) + 0.0)
    expansion = helper_call("gc-motivation-expansion", tuple(terms))
    exact = sum(map(Q, terms), Q(0))
    assert sum(map(Q, expansion), Q(0)) == exact
    value = helper_call("gc-motivation-value", expansion)
    assert abs(Q(value) - exact) <= Q(9, 2) * (1 + UNIT) ** len(expansion) * UNIT * abs(exact), (terms, expansion, value)
    leading = helper_call("gc-motivation-leading", expansion)
    assert (leading > 0) - (leading < 0) == (exact > 0) - (exact < 0)


# The decimal designs whose rounded evaluation once had the wrong sign, one of each kind: a balanced
# overshoot whose exact reduction is 0 read as a gain or a loss, and an exact gain or loss read as 0.
# am[verifies a-v2r-exact-sign-1020]
@pytest.mark.parametrize("low, high, level, change, power, sign", [
    (0.2, 0.4, 0.1, 0.4, 1, 0),
    (0.1, 0.2, 0.05, 0.2, 1, 0),
    (0.1, 0.55, 0.05, 0.55, 1, 0),
    (0.15, 0.55, 0.65, -0.6, 1, 1),
    (0.0, 0.25, 0.05, 0.2, 1, -1),
])
def test_decimal_designs_once_signed_wrongly_take_their_exact_sign(low, high, level, change, power, sign):
    span, start, end = exact_gaps(0.0, 1.0, low, high, level, change)
    assert real_move(start, end, span, power)[1] == sign
    point = helper_call("gc-motivation-interval", term("Need", "need", "goal", 0.0, 1.0, low, high, float(power)),
                        term("Known", level), term("Known", change))
    assert (point[1] > 0) - (point[1] < 0) == sign and point[1] == point[2]
    if sign == 0:
        assert point[1] == 0.0

"""Purpose: check typed signal readings, their observation ids and the one reading term the review and the planner build from them, their decay, the preference between contrary readings of different tiers and the conflict between readings of one at a review's reference time, and the facts they emit."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from functools import cache

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from goal_chainer.domains.loader import vocabulary
from goal_chainer.relevance import signals
from goal_chainer.relevance.errors import RelevanceError
from goal_chainer.relevance.signals import SignalReading, SignalState, effective_readings, reading_term, theory_facts

from relevance_support import helper_call
from request_support import budget as request_budget

AS_OF = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
SIGNALS = ("alpha", "beta")


# am[verifies a-rel-signals-1016@16b33a] am[verifies i-rel-reading-validation-1016@09a38a]
def test_an_unrecognised_state_is_an_error_not_a_silently_dropped_reading() -> None:
    # The copied reader compared states by identity, so the string "present" emitted no fact
    # and no error; a typed reading refuses it.
    with pytest.raises(RelevanceError, match="state must be one of") as raised:
        SignalReading("alpha", "present", "test", "measured")  # type: ignore[arg-type]
    assert raised.value.code == "invalid-packet"


# am[verifies a-rel-signals-1016@16b33a]
def test_a_state_given_as_text_becomes_the_enum_and_emits_its_fact() -> None:
    reading = SignalReading("alpha", "detected", "test", "measured")  # type: ignore[arg-type]

    assert reading.state is SignalState.DETECTED
    effective = effective_readings([reading], SIGNALS, AS_OF, budget=request_budget())
    assert theory_facts(effective) == "(given (signal alpha))"


# am[verifies a-rel-signals-1016@16b33a]
@pytest.mark.parametrize(
    "fields, message",
    [
        ({"state": "detected", "source": "test"}, "needs the estimator"),
        ({"state": "refuted", "source": "test", "estimator": "guessed"}, "estimator must be one of"),
        ({"state": "detected", "source": " ", "estimator": "measured"}, "nonempty source"),
        ({"state": "detected", "source": "t", "estimator": "measured", "observed_at": datetime(2026, 1, 1)}, "timezone-aware"),
        (
            {"state": "detected", "source": "t", "estimator": "measured",
             "observed_at": AS_OF, "valid_until": AS_OF - timedelta(seconds=1)},
            "valid_until precedes observed_at",
        ),
    ],
)
def test_malformed_readings_are_rejected(fields: dict, message: str) -> None:
    with pytest.raises(RelevanceError, match=message):
        SignalReading("alpha", **fields)


# am[verifies a-rel-signals-1016@16b33a]
def test_facts_are_three_valued() -> None:
    effective = effective_readings(
        [
            SignalReading("alpha", "detected", "t", "measured"),  # type: ignore[arg-type]
            SignalReading("beta", "refuted", "t", "deterministic"),  # type: ignore[arg-type]
        ],
        SIGNALS + ("gamma",),
        AS_OF,
        budget=request_budget(),
    )

    assert theory_facts(effective) == "(given (signal alpha))\n(given (not (signal beta)))"
    assert effective["gamma"].state == "unknown"


# am[verifies a-rel-signals-1016@16b33a] am[rests-on c-integrate-agenticmind-support-1016@b60619]
@settings(max_examples=60, deadline=None)
@given(
    state=st.sampled_from(["detected", "refuted"]),
    lived=st.integers(min_value=0, max_value=600),
    late=st.integers(min_value=1, max_value=10_000),
)
def test_an_expired_reading_decays_to_unknown_and_never_to_refuted(state: str, lived: int, late: int) -> None:
    observed = AS_OF - timedelta(minutes=lived + late)
    reading = SignalReading(
        "alpha", state, "telemetry", "measured",  # type: ignore[arg-type]
        observed_at=observed, valid_until=observed + timedelta(minutes=lived),
    )

    effective = effective_readings([reading], SIGNALS, AS_OF, budget=request_budget())["alpha"]

    assert effective.state == "unknown"
    assert effective.decayed == (reading,)
    assert theory_facts({"alpha": effective}) == ""


# am[verifies a-rel-signals-1016@16b33a]
def test_valid_detected_and_refuted_readings_leave_the_signal_conflicted_and_factless() -> None:
    effective = effective_readings(
        [
            SignalReading("alpha", "detected", "sensor-a", "measured"),  # type: ignore[arg-type]
            SignalReading("alpha", "refuted", "sensor-b", "measured"),  # type: ignore[arg-type]
        ],
        SIGNALS,
        AS_OF,
        budget=request_budget(),
    )

    assert effective["alpha"].state == "conflicted"
    assert effective["alpha"].disputed and effective["alpha"].contested == ()
    assert theory_facts(effective) == ""


# The parent's ruling (c-integrate-reading-owner-rule-1018): the preferred polarity is projected,
# and the overruled contrary stays live and in dispute while it is current.
# am[verifies a-rel-rr-p-effective-1018@2a0968] am[verifies a-rel-rr-p-escalation-1018@86a7bb]
def test_a_contrary_of_a_lower_tier_is_overruled_and_left_contested() -> None:
    measured = SignalReading("alpha", "detected", "sensor", "measured")  # type: ignore[arg-type]
    modelled = SignalReading("alpha", "refuted", "model", "model-proposed")  # type: ignore[arg-type]

    effective = effective_readings([modelled, measured], SIGNALS, AS_OF, budget=request_budget())

    alpha = effective["alpha"]
    assert (alpha.state, alpha.fact, alpha.disputed) == ("detected", True, True)
    assert (alpha.support, alpha.contested) == ((measured,), (modelled,))
    assert theory_facts(effective) == "(given (signal alpha))"


# The preference is defeasible: outliving the preferred reading reinstates its contrary, and an
# expired contrary is no live disagreement.
# am[verifies a-rel-rr-p-effective-1018@2a0968]
def test_an_expired_preferred_reading_reinstates_its_contrary_undisputed() -> None:
    lapsed = SignalReading(
        "alpha", "refuted", "sensor", "measured", valid_until=AS_OF - timedelta(minutes=1),  # type: ignore[arg-type]
    )
    modelled = SignalReading("alpha", "detected", "model", "model-proposed")  # type: ignore[arg-type]

    alpha = effective_readings([lapsed, modelled], SIGNALS, AS_OF, budget=request_budget())["alpha"]

    assert (alpha.state, alpha.fact, alpha.disputed) == ("detected", True, False)
    assert (alpha.support, alpha.contested, alpha.decayed) == ((modelled,), (), (lapsed,))


# am[verifies a-rel-signals-1016@16b33a]
@pytest.mark.parametrize(
    "reading, message",
    [
        (SignalReading("delta", "detected", "t", "measured"), "undeclared signal delta"),  # type: ignore[arg-type]
        (
            SignalReading("alpha", "detected", "t", "measured", observed_at=AS_OF + timedelta(seconds=1)),  # type: ignore[arg-type]
            "after the review's as_of",
        ),
    ],
)
def test_a_reading_that_could_never_count_is_an_error(reading: SignalReading, message: str) -> None:
    with pytest.raises(RelevanceError, match=message):
        effective_readings([reading], SIGNALS, AS_OF, budget=request_budget())


# am[verifies a-rel-signals-1016@16b33a]
def test_a_snapshot_is_the_observation_identity_without_the_note() -> None:
    def snapshot(**fields) -> dict:
        reading = SignalReading("alpha", "detected", fields.pop("source", "s"), "measured", **fields)  # type: ignore[arg-type]
        return effective_readings([reading], SIGNALS, AS_OF, budget=request_budget())["alpha"].snapshot()

    base = snapshot()
    assert snapshot(note="commentary") == base
    assert snapshot(source="another-sensor") != base
    assert snapshot(valid_until=AS_OF + timedelta(hours=1)) != base
    assert effective_readings([], SIGNALS, AS_OF, budget=request_budget())["alpha"].snapshot() == {"state": "unknown", "support": []}


# am[verifies a-rel-pj-observation-id-1018@457d2e]
def test_an_observation_id_names_the_signal_and_identity_but_not_the_note() -> None:
    def observation(signal: str = "alpha", **fields) -> SignalReading:
        return SignalReading(signal, fields.pop("state", "detected"), fields.pop("source", "s"), "measured", **fields)  # type: ignore[arg-type]

    base = observation(observed_at=AS_OF)
    payload = json.dumps({"signal": "alpha", **base.identity()}, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)

    assert base.observation_id() == "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert observation(observed_at=AS_OF, note="commentary").observation_id() == base.observation_id()
    assert observation(observed_at=AS_OF.astimezone(timezone(timedelta(hours=11)))).observation_id() == base.observation_id()
    for changed in (observation("beta", observed_at=AS_OF), observation(state="refuted", observed_at=AS_OF),
                    observation(source="another-sensor", observed_at=AS_OF), observation(),
                    observation(observed_at=AS_OF, valid_until=AS_OF + timedelta(hours=1))):
        assert changed.observation_id() != base.observation_id()


# The review names a reading's row by its observation id, as the planner does, and every reading of
# one observation, whatever its note, stands behind the belief it supports, in packet order.
# am[verifies a-rel-reading-term-one-home-1018@522700] am[verifies i-rel-reading-term-two-homes-1018@a67558]
def test_a_reading_term_names_its_observation_and_every_copy_stands_behind_the_belief() -> None:
    from metta import S

    first = SignalReading("alpha", "detected", "probe", "measured", note="first")  # type: ignore[arg-type]
    other = SignalReading("beta", "refuted", "probe", "measured", valid_until=AS_OF)  # type: ignore[arg-type]
    again = SignalReading("alpha", "detected", "probe", "measured", note="second")  # type: ignore[arg-type]
    unread = SignalReading("beta", "unknown", "probe")  # type: ignore[arg-type]

    assert reading_term(first) == S.Reading("alpha", "detected", "measured", S.Forever, first.observation_id())
    assert reading_term(unread) == S.Reading("beta", "unknown", S["None"], S.Forever, unread.observation_id())
    assert reading_term(other).children[4] == S.Until(int(AS_OF.timestamp() * 1_000_000))
    effective = effective_readings([first, other, again, unread], SIGNALS, AS_OF, budget=request_budget())
    assert effective["alpha"].support == (first, again)
    assert effective["beta"].support == (other,) and effective["beta"].unknown == (unread,)


# A belief naming an observation no reading of the packet has is the policy's mistake, never a
# reading silently dropped or invented.
# am[verifies a-rel-reading-term-one-home-1018@522700]
def test_a_belief_naming_an_observation_no_reading_has_is_unreadable(monkeypatch) -> None:
    from metta import S

    reading = SignalReading("alpha", "detected", "probe", "measured")  # type: ignore[arg-type]
    belief = (S.Effective, "alpha", "detected", S["None"], False, ("sha256:" + "0" * 64,), (), (), ())
    monkeypatch.setattr(signals, "evaluate", lambda *_, **__: (belief,))

    with pytest.raises(RelevanceError, match="no reading has") as raised:
        effective_readings([reading], ("alpha",), AS_OF, budget=request_budget())
    assert raised.value.code == "engine-output-invalid"


# A contested reading is current evidence the review was decided from, so the snapshot keeps it:
# its lapsing ends the dispute and must make a stored review stale.
# am[verifies a-rel-rr-p-effective-1018@2a0968]
def test_a_snapshot_lists_a_contested_reading_with_the_support() -> None:
    measured = SignalReading("alpha", "detected", "sensor", "measured")  # type: ignore[arg-type]
    modelled = SignalReading("alpha", "refuted", "model", "model-proposed")  # type: ignore[arg-type]

    disputed = effective_readings([measured, modelled], SIGNALS, AS_OF, budget=request_budget())["alpha"].snapshot()
    alone = effective_readings([measured], SIGNALS, AS_OF, budget=request_budget())["alpha"].snapshot()

    assert disputed["state"] == alone["state"] == "detected"
    assert disputed["support"] == sorted(
        (measured.identity(), modelled.identity()), key=lambda identity: tuple(str(identity[k]) for k in sorted(identity))
    )
    assert disputed != alone


# Each class's tier as the shared vocabulary answers it; the vocabulary's own tests pin the table.
# am[verifies a-rel-rr-projection-1018@a05ccf]
@cache
def _tier(estimator: str) -> int:
    return helper_call("gc-estimator-tier", estimator)


# The projection of policy/evidence.metta stated independently of the kernel, for a differential
# check: of the current definite readings, the polarity whose top tier is higher is accepted and
# every reading of the other is contested; equal top tiers leave the signal conflicted.
# am[verifies a-rel-rr-projection-1018@a05ccf]
def _expected(readings: list[SignalReading], signal: str) -> tuple:
    mine = [r for r in readings if r.signal == signal]
    current = [r for r in mine if r.is_definite and (r.valid_until is None or r.valid_until >= AS_OF)]
    decayed = tuple(r for r in mine if r.is_definite and r.valid_until is not None and r.valid_until < AS_OF)
    unknown = tuple(r for r in mine if not r.is_definite)
    top = {
        state: max((_tier(r.estimator) for r in current if r.state.value == state), default=None)
        for state in ("detected", "refuted")
    }
    if top["detected"] is None and top["refuted"] is None:
        state = "unknown"
    elif top["refuted"] is None or (top["detected"] is not None and top["detected"] > top["refuted"]):
        state = "detected"
    elif top["detected"] is None or top["refuted"] > top["detected"]:
        state = "refuted"
    else:
        state = "conflicted"
    winner = state if state in ("detected", "refuted") else None
    support = tuple(r for r in current if winner is None or r.state.value == winner)
    contested = tuple(r for r in current if winner is not None and r.state.value != winner)
    fact = {"detected": True, "refuted": False}.get(state)
    return state, fact, state == "conflicted" or bool(contested), support, contested, decayed, unknown


# am[verifies a-rel-signals-1016@16b33a] am[verifies a-rel-metta-policy-1016@fdaa20]
# am[verifies a-rel-rr-projection-1018@a05ccf]
@settings(max_examples=80, deadline=None)
@given(
    rows=st.lists(
        st.tuples(
            st.sampled_from(SIGNALS),
            st.sampled_from(["detected", "refuted", "unknown"]),
            st.sampled_from(vocabulary().classes),
            st.one_of(st.none(), st.integers(min_value=-90, max_value=90)),
        ),
        max_size=8,
    )
)
def test_the_evidence_policy_follows_its_rules_on_any_set_of_readings(rows: list[tuple[str, str, str, int | None]]) -> None:
    readings = [
        SignalReading(
            signal, state, f"source-{index}", None if state == "unknown" else estimator,  # type: ignore[arg-type]
            valid_until=None if minutes is None else AS_OF + timedelta(minutes=minutes),
        )
        for index, (signal, state, estimator, minutes) in enumerate(rows)
    ]

    effective = effective_readings(readings, SIGNALS, AS_OF, budget=request_budget())

    for signal in SIGNALS:
        got = effective[signal]
        assert (got.state, got.fact, got.disputed, got.support, got.contested, got.decayed, got.unknown) == _expected(
            readings, signal
        )

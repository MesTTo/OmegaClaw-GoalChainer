"""Purpose: test the projection of a declared Jev reading into the relevance review's signal
readings: the state each declared direction gives, the model-proposed class whatever Jev's
probability, the refusal of a reading made under another declaration, the provenance and grade a
signal reading carries, the review packet's boundary, and what the review's own evidence policy
makes of the projected readings, the replayed reading of a captured request included."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings, strategies as st
from relevance_support import packet

from goal_chainer import semantic_reader as sr
from goal_chainer.errors import InvalidInputError
from goal_chainer.domains.readings import DIRECTIONS, ReadingDeclaration
from goal_chainer.reading_projection import ESTIMATOR, STATES, signal_readings
from goal_chainer.relevance.errors import RelevanceError
from goal_chainer.relevance.packet import parse_packet
from goal_chainer.relevance.signals import SignalState, effective_readings, theory_facts
from request_support import budget
from reading_support import INCIDENT as TABLE

SIGNALS = tuple(p.id for p in TABLE.propositions)
AS_OF = datetime(2026, 10, 18, 4, 0, tzinfo=timezone.utc)


# A reading built by hand: each proposition answered as answers says, unknown otherwise, at
# probability, so the projection is held to exact answers; real answers are replayed below.
# am[verifies a-dr-pj-api-1018@b3c793]
def _reading(answers: dict[str, str], probability: float = 0.9,
             declaration: ReadingDeclaration = TABLE) -> sr.Reading:
    def answer(proposition):
        return answers.get(proposition.id, "unknown")

    return sr.Reading(
        text="synthetic text",
        model=declaration.model,
        revision="synthetic",
        declaration=declaration,
        passages=("the passage",),
        propositions=tuple(
            sr.PropositionReading(
                proposition=p,
                answer=answer(p),
                direction=declaration.direction(answer(p)),
                probability=probability,
                probabilities={a: (probability if a == answer(p) else 0.0) for a in declaration.answers},
                draws=1,
                key=f"synthetic-{p.id}",
                grounding=None if answer(p) not in declaration.decided else sr.Grounding("the passage", 0.9),
            )
            for p in declaration.propositions
        ),
        choices=(),
        bindings=(),
    )


# am[verifies a-dr-pj-api-1018@b3c793]
def _project(reading: sr.Reading, valid_until: datetime | None = None):
    return signal_readings(reading, TABLE, observed_at=AS_OF, valid_until=valid_until)


# The table is total over the declared directions, and every option of the declaration reads as
# the state of its own direction, under each proposition's own id in declaration order.
# am[verifies a-dr-pj-api-1018@b3c793]
def test_every_declared_direction_gives_its_review_state() -> None:
    assert set(STATES) == set(DIRECTIONS) == {option.direction for option in TABLE.options}
    for option in TABLE.options:
        projected = _project(_reading({p: option.name for p in SIGNALS}))

        state = STATES[option.direction]
        assert [r.signal for r in projected] == list(SIGNALS)
        assert {r.state for r in projected} == {state}
        assert {r.estimator for r in projected} == {None if state is SignalState.UNKNOWN else ESTIMATOR}


# A confident answer is still a model's estimate, so no probability lifts its class.
# am[verifies a-dr-pj-api-1018@b3c793] am[verifies c-dr-pj-model-proposed-never-checks-1018@9500c1]
@settings(max_examples=60, deadline=None)
@given(st.floats(min_value=0.0, max_value=1.0), st.sampled_from(sorted(TABLE.answers)))
def test_the_class_stays_model_proposed_whatever_the_probability(probability: float, answer: str) -> None:
    first = _project(_reading({SIGNALS[0]: answer}, probability))[0]

    assert first.estimator == (None if TABLE.direction(answer) == "none" else ESTIMATOR)
    assert first.note.startswith(f"{answer} {probability:.2f}")


# am[verifies a-dr-pj-api-1018@b3c793]
def test_a_reading_made_under_another_declaration_is_refused() -> None:
    other = dataclasses.replace(TABLE, model="another-model")
    assert other.digest != TABLE.digest

    with pytest.raises(InvalidInputError) as raised:
        _project(_reading({"sensitive-data": "supported"}, declaration=other))
    assert raised.value.details["declared"] == TABLE.digest
    assert raised.value.details["read"] == other.digest


# The source names the Jev answer, so it is part of the observation's identity; the grade and the
# grounding passage travel in the note, which is not; the instants are the caller's.
# am[verifies a-dr-pj-api-1018@b3c793]
def test_a_signal_reading_carries_the_answer_s_provenance_and_grade() -> None:
    until = AS_OF + timedelta(hours=1)
    by_signal = {r.signal: r for r in _project(_reading({"sensitive-data": "supported"}, 0.87), until)}

    supported, silent = by_signal["sensitive-data"], by_signal["public-data"]
    assert supported.source == f"jev:{TABLE.model}:synthetic-sensitive-data"
    assert supported.note == "supported 0.87: the passage"
    assert silent.note == "unknown 0.87" and silent.estimator is None
    assert (supported.observed_at, supported.valid_until) == (AS_OF, until)
    assert supported.identity()["source"] == supported.source and "note" not in supported.identity()


# am[verifies a-dr-pj-api-1018@b3c793]
def test_projected_readings_pass_the_review_packet_unchanged() -> None:
    projected = _project(_reading({"sensitive-data": "supported", "public-data": "contradicted"}),
                         AS_OF + timedelta(days=1))

    assert parse_packet(packet(*projected).to_dict()).readings == projected


# The review's evidence policy reads the projection as it reads any reading: a supported answer
# detects its signal, a contradicted one refutes it, an unknown answer and a declared signal no
# proposition reads stay unknown, and a domain declaring fewer signals refuses the rest.
# am[verifies a-dr-pj-api-1018@b3c793] am[verifies c-dr-pj-review-refuses-undeclared-1018@8db2c3]
def test_the_review_reads_what_the_projection_hands_it() -> None:
    projected = _project(_reading({"sensitive-data": "supported", "public-data": "contradicted"}))

    effective = effective_readings(projected, (*SIGNALS, "elsewhere"), AS_OF, budget=budget())
    assert effective["sensitive-data"].state == "detected"
    assert effective["public-data"].state == "refuted"
    assert effective["unverified"].state == "unknown"
    assert effective["elsewhere"].state == "unknown"
    facts = theory_facts(effective)
    assert "(given (signal sensitive-data))" in facts and "(given (not (signal public-data)))" in facts
    assert "unverified" not in facts

    with pytest.raises(RelevanceError, match="undeclared signal"):
        effective_readings(projected, SIGNALS[:1], AS_OF, budget=budget())


# A captured request, read from its replayed Jev answers: every proposition projects under its own
# id, in the direction its answer was read, from the answer the reading names.
# am[verifies a-dr-pj-api-1018@b3c793] am[verifies c-dr-pj-reading-carries-direction-1018@7ca4e4]
def test_a_replayed_reading_projects_each_proposition_from_its_own_answer() -> None:
    reading = sr.default_reader(budget=budget()).read("Do not publish the raw logs that expose customer emails.", budget=budget())

    projected = _project(reading)
    assert [r.signal for r in projected] == list(SIGNALS)
    for signal_reading, read in zip(projected, reading.propositions, strict=True):
        assert signal_reading.state is STATES[read.direction]
        assert signal_reading.source == f"jev:{reading.model}:{read.key}"
    assert any(r.state is SignalState.DETECTED for r in projected)

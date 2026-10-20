"""Purpose: project a declared Jev reading into the relevance review's signal readings and the
planner's entity readings. Each declared proposition becomes one SignalReading under its own id,
its state read off the direction its declaration gives the decided answer, and its estimator class
model-proposed whenever it is definite, whatever Jev's probability, so no reading by a model
establishes what it reads. Each binding whose answer chose an entity, of a proposition read
definitely, becomes one EntityReading: that proposition's reading placed on the chosen entity, so
the entity is the binding's and the evidence the proposition's.

The reading itself stays whole for SNARS, whose gc-reading facts keep every proposition's graded
answer (snars_ingestion.reading_facts). A SignalReading keeps the reading's provenance in its
source, which is part of the observation's identity, and the graded answer in its note, which is
not. Which signals a domain declares is each consumer's check: the review refuses a reading of an
undeclared signal, and the planner places each signal at its domain's anchor; taking entity readings
is the planner's own change (a-bnd-planner-readings-1019). No EntityReading reaches the review.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from .errors import InvalidInputError, safe_repr
from .domains.readings import ReadingDeclaration, is_reading_symbol
from .relevance.canonical import fingerprint_of
from .relevance.policy import constant, term
from .relevance.signals import SignalReading, SignalState, reading_term
from .semantic_reader import PropositionReading, Reading

# The review's state for each declared direction: a `for` answer is evidence that the condition
# holds, an `against` answer evidence that it does not, and `none` no evidence either way, which
# the review reads as unknown and never as refuted.
# am[implements a-dr-pj-api-1018@b3c793]
STATES: dict[str, SignalState] = {
    "for": SignalState.DETECTED,
    "against": SignalState.REFUTED,
    "none": SignalState.UNKNOWN,
}
# A reading is a model's estimate, so its class is the vocabulary's model-proposed, which
# establishes nothing: the justification kernel never labels a claim Checked on it.
# am[implements a-dr-pj-api-1018@b3c793]
ESTIMATOR = "model-proposed"


# A signal reading placed on one declared entity by a binding's answer: the proposition's own
# reading, the entity the binding chose and that choice's source. It is a type of its own, never a
# SignalReading, because the review folds every SignalReading of a signal into the signal's one
# belief, and an entity reading is not evidence about the signal; only the planner takes it. Its
# identity is the reading's and the entity's and the entity source's, and its note is the reading's.
# A refusal quotes the value it refused through errors.safe_repr, so a value repr cannot write, such as
# an integer past the digit limit, is still refused as InvalidInputError (c-integrate-binding-repr-escape-1019).
# am[implements a-bnd-entity-reading-1019@b71e57] am[rests-on c-bnd-relevance-folds-signal-readings-1019@0c12a0]
# am[implements a-integrate-binding-refusal-repair-1019@77b660] am[related a-rt-rr-safe-repr-1018@ec9700]
@dataclass(frozen=True, slots=True)
class EntityReading:
    reading: SignalReading
    entity: str
    entity_source: str

    def __post_init__(self) -> None:
        if not isinstance(self.reading, SignalReading):
            raise InvalidInputError("An entity reading places a signal reading.",
                                    details={"reading": safe_repr(self.reading)[:200]})
        if not is_reading_symbol(self.entity):
            raise InvalidInputError("An entity reading names an entity symbol.",
                                    details={"entity": safe_repr(self.entity)[:200]})
        if not isinstance(self.entity_source, str) or not self.entity_source.strip():
            raise InvalidInputError("An entity reading needs a nonempty entity source.",
                                    details={"entity_source": safe_repr(self.entity_source)[:200]})

    def identity(self) -> dict[str, object]:
        """The decision-relevant identity: the reading's, with the entity and the entity source."""

        return {**self.reading.identity(), "entity": self.entity, "entity_source": self.entity_source}

    def observation_id(self) -> str:
        """The SHA-256 of the signal and the identity, which names the planner's row for this
        reading and never equals the signal reading's own id."""

        return fingerprint_of({"signal": self.reading.signal, **self.identity()})


# (EntityReading SIGNAL ENTITY STATE ESTIMATOR VALIDITY ID) as a pymetta atom: the signal reading's
# fields as the review's reading_term encodes them, so the two terms read one encoding, the entity a
# symbol as the planner's anchors write entities, and ID the entity reading's observation_id(). The
# planner's own rule is to map it to the row gc-reading-row gives its reading, with the claim
# (On (Signal S) E), once the planner takes entity readings (a-bnd-planner-row-1019, evidence's).
# am[implements a-bnd-entity-reading-1019@b71e57] am[related a-bnd-planner-row-1019@c65aa2]
def entity_term(reading: EntityReading) -> Any:
    _, signal, state, estimator, validity, _ = list(reading_term(reading.reading))
    return term("EntityReading", signal, constant(reading.entity), state, estimator, validity, reading.observation_id())


# am[implements a-dr-pj-api-1018@b3c793] am[implements a-bnd-entity-reading-1019@b71e57]
def _check_declaration(reading: Reading, declaration: ReadingDeclaration) -> None:
    if reading.declaration.digest != declaration.digest:
        raise InvalidInputError(
            "The reading was made under another reading declaration than the domain declares.",
            details={
                "domain": declaration.name,
                "declared": declaration.digest,
                "read": reading.declaration.digest,
                "read_domain": reading.declaration.name,
            },
        )


# A reading made under another declaration than the domain's is refused, since its answers mean
# what that other declaration says. observed_at and valid_until are the caller's: a reading of a
# request's text holds for that request, so its instant and validity come with the request.
# Time: one SignalReading per declared proposition.
# am[implements a-dr-pj-api-1018@b3c793]
def signal_readings(
    reading: Reading,
    declaration: ReadingDeclaration,
    *,
    observed_at: datetime | None,
    valid_until: datetime | None,
) -> tuple[SignalReading, ...]:
    """Each proposition of reading as the review's SignalReading, in declaration order."""

    _check_declaration(reading, declaration)
    return tuple(
        _signal_reading(reading, read, observed_at=observed_at, valid_until=valid_until)
        for read in reading.propositions
    )


# A binding's answer supports exactly the chosen entity's literal, with its proposition's evidence:
# a detected proposition places (On (Signal S) E) and a refuted one its negation, so another entity
# the binding offers is left unknown, never refuted. No match, or a proposition the text leaves
# unknown, places nothing. Every entity reading's class is model-proposed whatever either answer's
# probability, since it is the proposition's reading placed.
# Time: one EntityReading at most per binding.
# am[implements a-bnd-entity-reading-1019@b71e57]
def entity_readings(
    reading: Reading,
    declaration: ReadingDeclaration,
    *,
    observed_at: datetime | None,
    valid_until: datetime | None,
) -> tuple[EntityReading, ...]:
    """Each binding of reading that chose an entity for a definite proposition, as the planner's
    EntityReading, in declaration order."""

    _check_declaration(reading, declaration)
    propositions = {read.proposition.id: read for read in reading.propositions}
    placed = []
    for bound in reading.bindings:
        read = propositions[bound.binding.signal]
        if bound.entity is None or STATES[read.direction] is SignalState.UNKNOWN:
            continue
        signal = _signal_reading(reading, read, observed_at=observed_at, valid_until=valid_until)
        placed.append(EntityReading(
            reading=replace(signal, note=f"{signal.note}; on {bound.entity} {bound.probability:.2f}"),
            entity=bound.entity,
            entity_source=f"jev:{reading.model}:{bound.key}",
        ))
    return tuple(placed)


# am[implements a-dr-pj-api-1018@b3c793]
def _signal_reading(
    reading: Reading,
    read: PropositionReading,
    *,
    observed_at: datetime | None,
    valid_until: datetime | None,
) -> SignalReading:
    state = STATES[read.direction]
    grounding = "" if read.grounding is None else f": {read.grounding.passage}"
    return SignalReading(
        signal=read.proposition.id,
        state=state,
        # The answer key digests the model, the text and the question, so two readings with one
        # source are one Jev answer.
        source=f"jev:{reading.model}:{read.key}",
        estimator=None if state is SignalState.UNKNOWN else ESTIMATOR,
        note=f"{read.answer} {read.probability:.2f}{grounding}",
        observed_at=observed_at,
        valid_until=valid_until,
    )


__all__ = ["ESTIMATOR", "STATES", "EntityReading", "entity_readings", "entity_term", "signal_readings"]

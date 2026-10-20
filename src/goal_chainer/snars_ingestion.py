"""Purpose: define the gc-reading fact SNARS ingests for one proposition of a semantic reading,
with its one grammar, an emitter and the parser that inverts it, and project a semantic reader's
reading into one such fact per proposition."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .domains.readings import is_reading_symbol
from .errors import InvalidInputError, safe_repr

# SNARS's policy is what reads these facts, so their grammar lives on SNARS's side: its batches, its
# store and the projection import it here, and the reading the projection takes is named only in an
# annotation, so importing SNARS imports no semantic reader.
# am[implements a-sib-home-snars-ingestion-1018@5727d2] am[rests-on c-sib-fact-is-snars-input-1018@4e5065]
if TYPE_CHECKING:
    from .semantic_reader import Reading


# The one grammar of gc-reading facts, emitter and parser together:
# (gc-reading SOURCE TRUST ID ANSWER P (provenance MODEL ANSWER-KEY PASSAGE)). Whatever admits a
# stored fact parses it here, so a store boundary and the emitter cannot disagree. A ReadingFact
# that parse would refuse cannot be built, so parse(emit(f)) == f for every fact there is. Its
# shape is all it checks: whether its proposition and answer are declared is the declaration's to
# say (ReadingDeclaration.admit), since facts from any domain share this grammar.
# Its trust and probability are compared with 0 and 1 as given, which is exact for an int or a
# float and false for NaN, so no value is converted before it is checked; the refusal quotes the
# reading id through errors.safe_repr, so it stays InvalidInputError whatever the values are.
# am[implements a-jev-fact-grammar-one-1018@0f04e2]
# am[implements a-jev-fact-total-1016@c8ddbd]
# am[implements a-dr-explicit-table-1018@bba9ce]
# am[implements a-integrate-reader-numeric-refusal-closure-1018@54efbb] am[rests-on c-rn-exact-range-before-float-1018@81d212]
# am[related a-rt-rr-safe-repr-1018@ec9700]
@dataclass(frozen=True, slots=True)
class ReadingFact:
    """One proposition's reading as a fact."""

    source: str
    trust: float
    reading_id: str
    answer: str
    probability: float
    model: str
    key: str
    passage: str

    def __post_init__(self) -> None:
        problems = [
            f"its {what} is not a number from 0 to 1"
            for what, value in (("trust", self.trust), ("probability", self.probability))
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1
        ]
        problems += [
            f"its {what} is not a reading symbol"
            for what, value in (("reading id", self.reading_id), ("answer", self.answer))
            if not is_reading_symbol(value)
        ]
        if not all(isinstance(part, str) for part in (self.source, self.model, self.key, self.passage)):
            problems.append("its source, model, key and passage are not all text")
        if problems:
            raise InvalidInputError(
                f"A gc-reading fact is not well formed: {problems[0]}.",
                details={"reading": safe_repr(self.reading_id)[:100], "problems": problems},
            )

    def emit(self, codec: Any) -> str:
        return codec.emit(
            [
                codec.symbol("gc-reading"),
                codec.string(self.source),
                float(self.trust),
                codec.symbol(self.reading_id),
                codec.symbol(self.answer),
                float(self.probability),
                [codec.symbol("provenance"), codec.string(self.model), codec.string(self.key),
                 codec.string(self.passage)],
            ]
        )

    @classmethod
    def parse(cls, text: str, codec: Any) -> ReadingFact:
        """The fact text as a ReadingFact, or InvalidInputError for anything else: another
        head, a wrong arity, a part of the wrong kind, or a value a ReadingFact cannot hold."""

        def malformed(problem: str) -> InvalidInputError:
            return InvalidInputError(
                f"An ingestion fact is not a well-formed gc-reading: {problem}.",
                details={"fact": text[:500]},
            )

        def number(atom: Any) -> float:
            # Mettabase's codec reads a number as a symbol; anything else is not a number.
            try:
                return float(atom.text) if isinstance(atom, codec.Symbol) else math.nan
            except ValueError:
                return math.nan

        atom = codec.parse(text)
        if not (isinstance(atom, list) and len(atom) == 7 and isinstance(atom[0], codec.Symbol)
                and atom[0].text == "gc-reading"):
            raise malformed("it is not a seven-part (gc-reading ...) expression")
        _, source, trust, reading_id, answer, probability, provenance = atom
        if not isinstance(source, codec.StringLiteral):
            raise malformed("its source is not a string")
        if not (isinstance(reading_id, codec.Symbol) and isinstance(answer, codec.Symbol)):
            raise malformed("its reading id and answer are not symbols")
        if not (isinstance(provenance, list) and len(provenance) == 4
                and isinstance(provenance[0], codec.Symbol) and provenance[0].text == "provenance"
                and all(isinstance(part, codec.StringLiteral) for part in provenance[1:])):
            raise malformed("its provenance is not (provenance MODEL KEY PASSAGE)")
        try:
            return cls(source.value, number(trust), reading_id.text, answer.text, number(probability),
                       provenance[1].value, provenance[2].value, provenance[3].value)
        except InvalidInputError as error:
            raise malformed(error.details["problems"][0]) from error


# The caller's trust reaches ReadingFact as given, so a trust that is not a number from 0 to 1 is
# the grammar's refusal before emit writes an accepted one as its float. Each probability is the
# reader's, which checked_answer admitted as a float from 0 to 1.
# am[implements a-jev-snars-ingest-1016@2517b8] am[implements a-integrate-reader-numeric-refusal-closure-1018@54efbb]
def reading_facts(reading: Reading, *, source: str, trust: float, codec: Any) -> tuple[str, ...]:
    """A reading's `gc-reading` facts: one per proposition, carrying the source and trust it was
    read under, the decided answer and its probability, and the provenance."""

    return tuple(
        ReadingFact(
            source=source,
            trust=trust,
            reading_id=r.proposition.id,
            answer=r.answer,
            probability=float(r.probability),
            model=reading.model,
            key=r.key,
            passage="" if r.grounding is None else r.grounding.passage,
        ).emit(codec)
        for r in reading.propositions
    )


__all__ = ["ReadingFact", "reading_facts"]

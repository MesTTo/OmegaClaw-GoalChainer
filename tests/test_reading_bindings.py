"""Purpose: verify the reading section's bindings, the reader half of a-dr-brs-readings-1018: a binding
reads, writes back without its entities and offers its control's declared entities with their
descriptions once the domain loader has checked the domain; its rows refuse a binding of what is not
declared, a repeated binding and an undescribed entity it offers, and nothing about an entity no
binding offers; the declaration's identity and the binding's question cover each offered entity and
description while the domain digest does not, and a declaration with no binding keeps the identity it
had; a reading answers each binding with an entity or no match; the projection places a definite
proposition's reading on the chosen entity alone, model-proposed at every probability, leaving every
other entity unknown and placing nothing for no match or an unknown proposition; and the evaluation
scores a labelled binding. Every Jev answer here is synthetic and served offline."""

from __future__ import annotations

import json
import sys
from dataclasses import fields, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import assume, given, settings, strategies as st

import goal_chainer.semantic_reader as sr
from goal_chainer.domains.loader import _packaged_directory, read_domain
from goal_chainer.domains.model import DomainError
from goal_chainer.domains.readings import NO_MATCH, Binding, is_reading_symbol, with_entities
from goal_chainer.errors import InvalidInputError
from goal_chainer.reading_projection import EntityReading, entity_readings, entity_term, signal_readings
from goal_chainer.relevance.signals import SignalReading, SignalState
from goal_chainer.semantic_evaluation import CORPUS_PATH, evaluate, load_corpus, markdown, score
from jev_support import answering, client
from reading_support import INCIDENT, SYMBOLS, TEXTS, declarations, section, section_text
from request_support import budget

TASK = (_packaged_directory() / "task_control.metta").read_text(encoding="utf-8")
INSTRUCTIONS = "Which seat does the text say the data left? Statement: "
NO_SEAT = "The text names no seat."
BINDING = f'(gc-reading-binding leaked Seat "{INSTRUCTIONS}" "{NO_SEAT}")'
READING = [
    "(gc-reading-domain probe)",
    '(gc-reading-model "jev-1.13.0")',
    '(gc-reading-language "en")',
    '(gc-reading-instructions "Does the text support the proposition? Proposition: ")',
    '(gc-reading-option yes for "the text says it")',
    '(gc-reading-option no against "the text denies it")',
    '(gc-reading-option unclear none "the text leaves it open")',
    '(gc-reading-proposition leaked "Customer data left a seat." "Did customer data leave a seat?")',
    BINDING,
    '(gc-ranking-instruction "Rank the passages.")',
]
SEATS = (("seat", "the seat that owns the focal task"), ("receiving_seat", "the seat the work belongs with"))
AS_OF = datetime(2026, 10, 19, tzinfo=timezone.utc)


# The packaged task-control domain, whose bigraph section declares two described seats under Seat,
# with a reading section binding one proposition over Seat.
# am[verifies a-bnd-candidates-1019@61b2d4]
def _domain(task: str = TASK, reading: tuple[str, ...] | list[str] = READING, source: str = "binding-probe"):
    return read_domain(task + "\n" + "\n".join(reading), source, budget=budget())


DOMAIN = _domain()
DECLARATION = DOMAIN.readings


# The domain loader's faults for a domain, each line after the count the loader writes.
# am[verifies a-bnd-faults-1019@b5dc70]
def _faults(task: str = TASK, reading: tuple[str, ...] | list[str] = READING) -> str:
    with pytest.raises(DomainError) as refused:
        _domain(task, reading)
    return str(refused.value)


# am[verifies a-bnd-candidates-1019@61b2d4] am[verifies a-bnd-form-1019@787476]
def test_a_binding_offers_its_control_s_described_entities_in_declaration_order() -> None:
    (binding,) = DECLARATION.bindings
    assert binding == Binding("leaked", "Seat", INSTRUCTIONS, NO_SEAT, SEATS)
    assert binding.options == ("seat", "receiving_seat", NO_MATCH)
    assert binding.question_id == "leaked Seat" and not is_reading_symbol(binding.question_id)


# The section's own forms carry the binding without its entities, which the bigraph section declares;
# given them again, the declaration read back is the declaration, digest included.
# am[verifies a-bnd-form-1019@787476] am[verifies a-bnd-candidates-1019@61b2d4]
def test_a_binding_writes_back_without_its_entities_and_reads_back_whole_once_given_them() -> None:
    again = section(section_text(DECLARATION))
    assert again.bindings == (replace(DECLARATION.bindings[0], entities=()),)
    assert again.digest != DECLARATION.digest
    entities = [(entity.id, entity.control, entity.description) for entity in DOMAIN.bigraph.entities]
    restored = with_entities(again, entities)
    assert restored.bindings == DECLARATION.bindings and restored.digest == DECLARATION.digest


# Any declaration given bindings over generated controls, each offering generated entities with any
# descriptions, writes back as forms that read as it without the entities and as it once given them.
# am[verifies a-bnd-form-1019@787476] am[verifies a-bnd-candidates-1019@61b2d4]
@st.composite
def _bound(draw):
    declaration = draw(declarations())
    assume(declaration.propositions)
    count = draw(st.integers(1, 3))
    names = draw(st.lists(SYMBOLS, min_size=2 * count, max_size=2 * count, unique=True))
    controls, entities = names[:count], names[count:]
    triples = [(entity, control, draw(TEXTS)) for entity, control in zip(entities, controls)]
    bindings = tuple(
        Binding(draw(st.sampled_from([p.id for p in declaration.propositions])), control, draw(TEXTS), draw(TEXTS))
        for control in controls
    )
    return with_entities(replace(declaration, bindings=bindings), triples), triples


# am[verifies a-bnd-form-1019@787476] am[verifies a-bnd-candidates-1019@61b2d4]
@settings(max_examples=60, deadline=None)
@given(bound=_bound())
def test_any_bound_declaration_writes_back_as_forms_that_read_back_as_it(bound) -> None:
    declaration, triples = bound
    again = section(section_text(declaration), declaration.module)
    assert again.bindings == tuple(replace(b, entities=()) for b in declaration.bindings)
    assert with_entities(again, triples) == declaration


# A binding's question, so the Jev cache key it is asked and replayed under, and the declaration's
# digest move with any entity or description the binding offers and with nothing it does not, and the
# domain digest, the review's alone, moves with neither.
# am[verifies a-bnd-candidates-1019@61b2d4] am[verifies a-bnd-question-1019@b2f0b9] am[verifies a-bnd-proof-1019@85b4cd]
@pytest.mark.parametrize(("old", "new", "moves"), [
    ("the seat the work belongs with", "the seat the work moves to", True),
    ("(gc-brs-in review (Root 0))",
     '(gc-brs-in review (Root 0))\n(gc-brs-entity spare_seat Seat "a spare seat")\n(gc-brs-in spare_seat (Root 0))', True),
    ("the review in progress", "the review under way", False),
])
def test_the_declaration_s_identity_covers_what_a_binding_offers_and_the_domain_digest_does_not(old, new, moves) -> None:
    assert old in TASK
    changed = _domain(TASK.replace(old, new))
    question, changed_question = DECLARATION.questions()["leaked Seat"], changed.readings.questions()["leaked Seat"]
    key, asked = sr.AnswerCache(Path("unused")).key, {"text": "The seat leaked."}
    assert (changed.readings.digest != DECLARATION.digest) is moves
    assert (changed_question != question) is moves
    assert (key(changed.readings.model, asked, changed_question) != key(DECLARATION.model, asked, question)) is moves
    assert changed.digest == DOMAIN.digest


# A declaration with no binding has no bindings key, so the incident declaration keeps the digest the
# committed corpus report recorded before bindings existed.
# am[verifies a-bnd-candidates-1019@61b2d4]
def test_a_declaration_with_no_binding_keeps_the_identity_it_had() -> None:
    report = json.loads((CORPUS_PATH.parent / "report.json").read_text(encoding="utf-8"))
    assert "bindings" not in INCIDENT.content()
    assert INCIDENT.digest == report["declaration"]["digest"] == "d43bc0fe604e5a378418958701c0a63db12d8d86b9b6d328628fd22d51f65bd0"


# Refusing malformed values at every place leaves each accepted declaration's identity as it was: the
# bound declaration's digest is the one it had at 9dc53cca, before the repair.
# am[verifies a-integrate-binding-declaration-refusal-repair-1019@59efc5]
def test_a_bound_declaration_keeps_the_identity_it_had() -> None:
    assert DECLARATION.digest == "5709387681418da75866f1d9cb770b51d43a42eaa4ce8612f8d1210559d7d510"


# Values a refusal could fail to format: an integer past the digit limit, of either sign, which str and
# repr refuse; an object whose every rendering raises; and a str and a tuple whose own methods raise,
# which only a check of their exact type keeps from being read as a name, a text or a pair.
# am[verifies a-integrate-binding-declaration-refusal-repair-1019@59efc5]
class _Unwritable:
    def __repr__(self) -> str:
        raise RuntimeError("unwritable")

    def __str__(self) -> str:
        raise RuntimeError("unwritable")

    def __format__(self, spec: str) -> str:
        raise RuntimeError("unwritable")


# am[verifies a-integrate-binding-declaration-refusal-repair-1019@59efc5]
class _HostileText(str):
    def _raise(self, *args, **kwargs):
        raise RuntimeError("hostile")

    __repr__ = __str__ = __format__ = __eq__ = __float__ = startswith = strip = _raise
    __hash__ = str.__hash__


# am[verifies a-integrate-binding-declaration-refusal-repair-1019@59efc5]
class _HostileTuple(tuple):
    def _raise(self, *args, **kwargs):
        raise RuntimeError("hostile")

    __repr__ = __len__ = __iter__ = __getitem__ = _raise


UNWRITABLE = (10**5000, -(10**5000), _Unwritable(), _HostileText("seat"), _HostileTuple(("seat", "a seat")))


# Each place a declaration holds a value, as (place, the replace() changes putting `value` there): its
# texts, names and module, each tuple of records, each record and each of its fields, and each choice
# option or binding entity pair and each side of it, so a test reaches every place without listing them.
# Time: one entry per place, linear in the declaration's size.
# am[verifies a-integrate-binding-declaration-refusal-repair-1019@59efc5]
def _places(declaration, value):
    def swap(items, index, new):
        return (*items[:index], new, *items[index + 1:])

    places = [(name, {name: value})
              for name in ("name", "model", "language", "instructions", "ranking_instruction", "module")]
    for field in ("options", "propositions", "choices", "bindings"):
        records = getattr(declaration, field)
        places.append((field, {field: value}))
        for i, record in enumerate(records):
            variants = [(f"[{i}]", value)]
            for part in fields(record):
                held = getattr(record, part.name)
                variants.append((f"[{i}].{part.name}", replace(record, **{part.name: value})))
                if part.name in ("options", "entities"):
                    for j, pair in enumerate(held):
                        for side, new in (("", value), ("[0]", (value, pair[1])), ("[1]", (pair[0], value))):
                            variants.append((f"[{i}].{part.name}[{j}]{side}",
                                             replace(record, **{part.name: swap(held, j, new)})))
            places += [(f"{field}{where}", {field: swap(records, i, new)}) for where, new in variants]
    return places


# Any declaration refuses a value that is not well formed at any place it holds one, a value no
# refusal can format by str or repr included, with the declaration's typed refusal, never another
# exception, and its JSON form (to_dict) serializes with every problem listed.
# am[verifies a-integrate-binding-declaration-refusal-repair-1019@59efc5] am[rests-on c-bnd-declaration-escape-surface-1019@ac7ef9]
@settings(max_examples=25, deadline=None)
@given(bound=_bound(), value=st.sampled_from(UNWRITABLE))
def test_a_malformed_value_anywhere_in_a_declaration_is_refused_whatever_it_quotes(bound, value) -> None:
    declaration, _ = bound
    for place, change in _places(declaration, value):
        with pytest.raises(InvalidInputError, match="^A reading declaration is not well formed: ") as refused:
            replace(declaration, **change)
        assert json.loads(json.dumps(refused.value.to_dict()))["details"]["problems"], place


# A refused binding name is quoted as repr writes it, and one repr cannot write is named, an integer
# past the digit limit by its sign and the limit, so the problem reads whole either way.
# am[verifies a-integrate-binding-declaration-refusal-repair-1019@59efc5] am[rests-on c-integrate-binding-declaration-repr-escape-1019@dc6c4d]
@pytest.mark.parametrize(("change", "problem"), [
    ({"signal": "two words"}, "'two words' in its binding signals is not a reading symbol"),
    ({"signal": _HostileText("leaked")},
     "a value of type _HostileText whose repr raised RuntimeError in its binding signals is not a reading symbol"),
    ({"signal": 10**5000}, "an integer of more than {limit} digits in its binding signals is not a reading symbol"),
    ({"control": 10**5000}, "an integer of more than {limit} digits in its binding controls is not a reading symbol"),
    ({"entities": ((-(10**5000), "the seat"),)},
     "a negative integer of more than {limit} digits in its binding leaked Seat entities is not a reading symbol"),
], ids=("ordinary", "subclass", "signal", "control", "entity"))
def test_a_refused_binding_name_is_quoted_or_named(change, problem) -> None:
    problem = problem.format(limit=sys.get_int_max_str_digits())
    with pytest.raises(InvalidInputError) as refused:
        replace(DECLARATION, bindings=(replace(DECLARATION.bindings[0], **change),))
    assert str(refused.value) == f"A reading declaration is not well formed: {problem}."
    assert refused.value.details["problems"] == [problem]


# Each entry is checked itself, so an entry named as another is cannot hide an empty text: the
# section's tables refuse the repeat when the domain loader reads a domain, and a declaration built
# without the loader still refuses the empty text.
# am[verifies a-integrate-binding-declaration-refusal-repair-1019@59efc5] am[rests-on c-bnd-declaration-escape-surface-1019@ac7ef9]
@pytest.mark.parametrize(("declaration", "change"), [
    (DECLARATION, lambda d: {"propositions": (replace(d.propositions[0], statement=" "), *d.propositions)}),
    (INCIDENT, lambda d: {"choices": (replace(d.choices[0], instructions=" "), *d.choices)}),
    (DECLARATION, lambda d: {"bindings": (replace(d.bindings[0], no_match=" "), *d.bindings)}),
    (DECLARATION, lambda d: {"bindings": (replace(d.bindings[0], entities=(
        (d.bindings[0].entities[0][0], " "), *d.bindings[0].entities)),)}),
], ids=("proposition", "choice", "binding", "entity"))
def test_an_empty_text_is_refused_beside_an_entry_of_the_same_name(declaration, change) -> None:
    with pytest.raises(InvalidInputError, match="is not nonempty text"):
        replace(declaration, **change(declaration))


# Each row's fault, through the domain loader, as the one fault of its domain: a binding over an
# undeclared control is reported for the control alone, not again for offering no entity.
# am[verifies a-bnd-faults-1019@b5dc70]
@pytest.mark.parametrize(("task", "reading", "fault"), [
    (TASK, [line.replace("leaked Seat", "leaked Nothing") for line in READING],
     '(Binding "leaked" "Nothing") names a control no gc-brs-control declares'),
    (TASK + "\n(gc-brs-control Spare (Ports) passive)", [line.replace("leaked Seat", "leaked Spare") for line in READING],
     '(Binding "leaked" "Spare") names a control no gc-brs-entity is declared under, so it offers only no match'),
    (TASK, [line.replace("leaked Seat", "ghost Seat") for line in READING],
     '(Binding "ghost" "Seat") binds no gc-reading-proposition of its id, so it has no statement to place'),
    (TASK, [*READING, BINDING], '(Binding "leaked" "Seat") is not the only gc-reading-binding of its signal and control'),
    (TASK.replace('(gc-brs-entity receiving_seat Seat "the seat the work belongs with")', "(gc-brs-entity receiving_seat Seat)"),
     READING, '(Entity "receiving_seat" "Seat") is offered by a gc-reading-binding but has no description for Jev to choose it by'),
])
def test_each_binding_row_reports_its_own_fault(task, reading, fault) -> None:
    assert _faults(task, reading) == f"binding-probe: {fault}"


# An entity no binding offers needs no description, so an undescribed review reads as before.
# am[verifies a-bnd-faults-1019@b5dc70]
def test_an_entity_no_binding_offers_needs_no_description() -> None:
    task = TASK.replace('(gc-brs-entity review Review "the review in progress")', "(gc-brs-entity review Review)")
    assert _domain(task).readings.bindings == DECLARATION.bindings


# Every binding fault of a domain is reported at once, among its other checks.
# am[verifies a-bnd-faults-1019@b5dc70]
def test_every_binding_fault_is_reported_at_once() -> None:
    task = TASK.replace('(gc-brs-entity receiving_seat Seat "the seat the work belongs with")', "(gc-brs-entity receiving_seat Seat)")
    reading = [*READING, '(gc-reading-binding ghost Nothing "Which? " "None.")']
    message = _faults(task, reading)
    assert message.splitlines()[0].endswith("3 faults:")
    for fault in ('(Binding "ghost" "Nothing") names a control no gc-brs-control declares',
                  '(Binding "ghost" "Nothing") binds no gc-reading-proposition of its id',
                  '(Entity "receiving_seat" "Seat") is offered by a gc-reading-binding'):
        assert fault in message


# The binding's question: its instructions then its proposition's statement, each offered entity by its
# description and no match by the binding's own text, keyed apart from every reading id.
# am[verifies a-bnd-question-1019@b2f0b9]
def test_a_binding_s_question_offers_each_entity_by_its_description_and_no_match() -> None:
    questions = DECLARATION.questions()
    assert list(questions) == ["leaked", "leaked Seat"]
    assert questions["leaked Seat"] == {
        "type": "choice",
        "instructions": INSTRUCTIONS + "Customer data left a seat.",
        "criteria": {"seat": "the seat that owns the focal task", "receiving_seat": "the seat the work belongs with",
                     NO_MATCH: NO_SEAT},
    }
    assert not is_reading_symbol(NO_MATCH)


# A declaration read without the domain loader has bindings offering no entity, so it asks nothing
# rather than asking a Choice of no match alone.
# am[verifies a-bnd-question-1019@b2f0b9]
def test_a_binding_offering_no_entity_is_refused_rather_than_asked() -> None:
    with pytest.raises(InvalidInputError, match="offers no entity"):
        section(section_text(DECLARATION)).questions()


# A reader of the bound declaration answers the binding with the entity Jev chose, or None for no
# match, beside its proposition; a stand-in ranker grounds the decided proposition.
# am[verifies a-bnd-reading-1019@105c81]
@pytest.mark.parametrize(("chosen", "entity"), [("receiving_seat", "receiving_seat"), (NO_MATCH, None)])
def test_a_reading_answers_a_binding_with_an_entity_or_no_match(tmp_path, chosen, entity) -> None:
    def answer_for(question, state):
        del state
        if question == "leaked":
            return {"yes": 0.9, "no": 0.05, "unclear": 0.05}
        return {option: (0.8 if option == chosen else 0.1) for option in DECLARATION.bindings[0].options}

    jev = sr.JevClient(sr.AnswerCache(tmp_path / "answers"), DECLARATION.model, client_factory=client(answering(answer_for)))
    reader = sr.SemanticReader(declaration=DECLARATION, jev=jev, serve=lambda: sr.ServedRanker("base", tmp_path),
                               load=lambda ranker: SimpleNamespace(scores=lambda pairs: tuple(0.5 for _ in pairs)))
    reading = reader.read("The receiving seat leaked the customer data.", budget=budget())
    (bound,) = reading.bindings
    assert (bound.answer, bound.entity, bound.probability) == (chosen, entity, pytest.approx(0.8))
    assert reading.to_dict()["bindings"][0]["entity"] == entity
    assert reading.proposition("leaked").answer == "yes"


# A reading built by hand: the proposition answered as given and the binding choosing as given.
# am[verifies a-bnd-entity-reading-1019@b71e57]
def _reading(answer: str, chosen: str, probability: float = 0.9, chosen_probability: float = 0.8,
             declaration=DECLARATION) -> sr.Reading:
    (proposition,) = declaration.propositions
    (binding,) = declaration.bindings
    return sr.Reading(
        text="synthetic text",
        model=declaration.model,
        revision="synthetic",
        declaration=declaration,
        passages=("the passage",),
        propositions=(sr.PropositionReading(
            proposition=proposition, answer=answer, direction=declaration.direction(answer), probability=probability,
            probabilities={a: (probability if a == answer else 0.0) for a in declaration.answers}, draws=1,
            key="synthetic-leaked", grounding=None),),
        choices=(),
        bindings=(sr.BindingReading(
            binding=binding, answer=chosen, probability=chosen_probability,
            probabilities={o: (chosen_probability if o == chosen else 0.0) for o in binding.options}, draws=1,
            key="synthetic-leaked-seat"),),
    )


# am[verifies a-bnd-entity-reading-1019@b71e57]
def _placed(reading: sr.Reading) -> tuple[EntityReading, ...]:
    return entity_readings(reading, DECLARATION, observed_at=AS_OF, valid_until=None)


# A detected proposition with an entity chosen is placed on that entity alone, with the proposition's
# own observation and an id apart from it; the other seat gets nothing, and the review's readings are
# the proposition's alone.
# am[verifies a-bnd-entity-reading-1019@b71e57] am[verifies a-bnd-proof-1019@85b4cd]
def test_a_definite_proposition_is_placed_on_the_chosen_entity_alone() -> None:
    reading = _reading("yes", "receiving_seat")
    (placed,) = _placed(reading)
    (bare,) = signal_readings(reading, DECLARATION, observed_at=AS_OF, valid_until=None)
    assert (placed.entity, placed.reading.signal, placed.reading.state) == ("receiving_seat", "leaked", SignalState.DETECTED)
    assert placed.reading.identity() == bare.identity() and placed.observation_id() != bare.observation_id()
    assert placed.entity_source == f"jev:{DECLARATION.model}:synthetic-leaked-seat"
    assert all(other.entity != "seat" for other in _placed(reading))


# A refuted proposition places its negation's evidence on the chosen entity: the state is refuted.
# am[verifies a-bnd-entity-reading-1019@b71e57] am[verifies a-bnd-proof-1019@85b4cd]
def test_a_refuted_proposition_is_placed_refuted() -> None:
    (placed,) = _placed(_reading("no", "seat"))
    assert (placed.entity, placed.reading.state) == ("seat", SignalState.REFUTED)


# No match, or a proposition the text leaves unknown, places nothing.
# am[verifies a-bnd-entity-reading-1019@b71e57] am[verifies a-bnd-proof-1019@85b4cd]
@pytest.mark.parametrize(("answer", "chosen"), [("unclear", "seat"), ("yes", NO_MATCH), ("unclear", NO_MATCH)])
def test_no_match_or_an_unknown_proposition_places_nothing(answer, chosen) -> None:
    assert _placed(_reading(answer, chosen)) == ()


# Whatever either answer's probability, an entity reading is model-proposed.
# am[verifies a-bnd-entity-reading-1019@b71e57] am[verifies a-bnd-proof-1019@85b4cd]
@settings(max_examples=60, deadline=None)
@given(probability=st.floats(0, 1), chosen_probability=st.floats(0, 1), answer=st.sampled_from(["yes", "no"]))
def test_an_entity_reading_is_model_proposed_at_every_probability(probability, chosen_probability, answer) -> None:
    (placed,) = _placed(_reading(answer, "seat", probability, chosen_probability))
    assert placed.reading.estimator == "model-proposed"


# A reading made under another declaration is refused, as signal_readings refuses it.
# am[verifies a-bnd-entity-reading-1019@b71e57]
def test_an_entity_reading_of_another_declaration_is_refused() -> None:
    other = replace(DECLARATION, instructions="Another instruction: ")
    with pytest.raises(InvalidInputError, match="another reading declaration"):
        _placed(_reading("yes", "seat", declaration=other))


# The planner's term carries the reading's fields as the review's encoding writes them, the entity as
# a symbol and the entity reading's own id.
# am[verifies a-bnd-entity-reading-1019@b71e57]
def test_an_entity_term_carries_the_entity_as_a_symbol_and_its_own_id() -> None:
    from metta import S  # noqa: PLC0415 (pymetta, the pinned engine)

    (placed,) = _placed(_reading("yes", "receiving_seat"))
    assert entity_term(placed) == S.EntityReading("leaked", S["receiving_seat"], "detected", "model-proposed", S.Forever,
                                                  placed.observation_id())


# An entity reading places a SignalReading on an entity symbol from a named source.
# am[verifies a-bnd-entity-reading-1019@b71e57]
@pytest.mark.parametrize(("reading", "entity", "source"), [
    ("not a reading", "seat", "jev:m:k"),
    (SignalReading(signal="leaked", state="detected", source="jev:m:k", estimator="model-proposed"), "two words", "jev:m:k"),
    (SignalReading(signal="leaked", state="detected", source="jev:m:k", estimator="model-proposed"), "seat", " "),
])
def test_an_entity_reading_refuses_what_it_cannot_place(reading, entity, source) -> None:
    with pytest.raises(InvalidInputError):
        EntityReading(reading, entity, source)


# A refusal stays the typed InvalidInputError whatever value it quotes, an integer repr cannot write
# included, and its details stay short.
# am[verifies a-integrate-binding-refusal-repair-1019@77b660] am[rests-on c-integrate-binding-repr-escape-1019@8d3ede]
@pytest.mark.parametrize("field", ["reading", "entity", "entity_source"])
def test_an_entity_reading_refusal_stays_typed_whatever_value_it_quotes(field) -> None:
    valid = {"reading": SignalReading(signal="leaked", state="detected", source="jev:m:k", estimator="model-proposed"),
             "entity": "seat", "entity_source": "jev:m:k"}
    with pytest.raises(InvalidInputError) as refused:
        EntityReading(**{**valid, field: 10**5000})
    assert [len(str(value)) <= 200 for value in refused.value.details.values()] == [True]


# A corpus for a bound declaration labels each binding by signal and control with an offered entity,
# no match or abstain, and the evaluation scores it as a choice over those options.
# am[verifies a-bnd-evaluation-1019@f82299]
def _corpus(tmp_path: Path, texts: list[dict]) -> Path:
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps({"version": 1, "labelled_by": "test", "texts": texts}), encoding="utf-8")
    return path


TEXTS_LABELLED = [
    {"id": "a", "text": "The receiving seat leaked the customer data.", "labels": {"leaked": ["yes", "it says so"]},
     "bindings": {"leaked": {"Seat": ["receiving_seat", "it names the receiving seat"]}}},
    {"id": "b", "text": "Nothing left any seat.", "labels": {"leaked": ["no", "it denies it"]},
     "bindings": {"leaked": {"Seat": [NO_MATCH, "it names no seat"]}}},
]


# am[verifies a-bnd-evaluation-1019@f82299]
def test_the_evaluation_scores_a_labelled_binding(tmp_path) -> None:
    corpus = load_corpus(DECLARATION, _corpus(tmp_path, TEXTS_LABELLED))
    assert [text.bindings["leaked Seat"].answer for text in corpus.texts] == ["receiving_seat", NO_MATCH]

    def answer_for(question, state):
        names = "receiving seat" in state["text"]
        if question == "leaked":
            return {"yes": 0.9 if names else 0.05, "no": 0.05 if names else 0.9, "unclear": 0.05}
        return {option: (0.8 if option == ("receiving_seat" if names else NO_MATCH) else 0.1)
                for option in DECLARATION.bindings[0].options}

    jev = sr.JevClient(sr.AnswerCache(tmp_path / "answers"), DECLARATION.model, client_factory=client(answering(answer_for)))
    target = evaluate(corpus, DECLARATION, jev, budget=budget())["targets"]["leaked Seat"]
    assert (target["n"], target["accuracy"], target["abstained"]) == (2, 1.0, 0)
    assert set(target["confusion"]) == {"seat", "receiving_seat", NO_MATCH}


# A corpus text must label every binding with one of its options, and nothing else.
# am[verifies a-bnd-evaluation-1019@f82299]
@pytest.mark.parametrize(("bindings", "match"), [
    (None, "label every binding"),
    ({"leaked": {"Seat": ["seat", "why"], "Review": ["review", "why"]}}, "label every binding"),
    ({"leaked": {"Seat": ["review", "why"]}}, "names no option"),
    ({"leaked": ["seat", "why"]}, "map each signal"),
])
def test_a_corpus_must_label_every_binding_with_one_of_its_options(tmp_path, bindings, match) -> None:
    text = dict(TEXTS_LABELLED[0])
    if bindings is None:
        del text["bindings"]
    else:
        text["bindings"] = bindings
    with pytest.raises(InvalidInputError, match=match):
        load_corpus(DECLARATION, _corpus(tmp_path, [text]))


# An entity named abstain is an answer like any other: its label is kept and scored, and only null
# abstains (c-integrate-binding-abstain-collision-1019).
# am[verifies a-integrate-binding-abstain-repair-1019@bf5ccd] am[rests-on c-integrate-binding-abstain-collision-1019@8304fc]
def test_an_entity_named_abstain_is_labelled_and_only_null_abstains(tmp_path) -> None:
    declaration = with_entities(section(section_text(DECLARATION), DECLARATION.module),
                                [("abstain", "Seat", "the seat spelled abstain"), ("seat", "Seat", "the owning seat")])
    named = dict(TEXTS_LABELLED[0], bindings={"leaked": {"Seat": ["abstain", "it names that seat"]}})
    silent = dict(TEXTS_LABELLED[1], bindings={"leaked": {"Seat": [None, "a careful reader could say either"]}})
    corpus = load_corpus(declaration, _corpus(tmp_path, [named, silent]))
    assert [text.bindings["leaked Seat"].answer for text in corpus.texts] == ["abstain", None]


# The decoder every target shares reads a proposition answer and a choice option named abstain as that
# option, abstains only on null, and refuses the word abstain where no option has that name.
# am[verifies a-integrate-binding-abstain-repair-1019@bf5ccd]
def test_every_target_reads_the_word_abstain_only_as_an_option_it_offers(tmp_path) -> None:
    declaration = section("\n".join([
        "(gc-reading-domain plain)", '(gc-reading-model "jev-1.13.0")', '(gc-reading-language "en")',
        '(gc-reading-instructions "Read: ")', '(gc-reading-option abstain for "the text says so")',
        '(gc-reading-option open none "the text leaves it open")',
        '(gc-reading-proposition said "It was said." "Was it said?")',
        '(gc-reading-choice tone "Which tone?" ((abstain "it holds back") (warm "it is warm")))',
        '(gc-ranking-instruction "Rank.")',
    ]))
    texts = [{"id": "a", "text": "x", "labels": {"said": ["abstain", "it says so"]}, "tone": ["abstain", "held back"]},
             {"id": "b", "text": "y", "labels": {"said": [None, "either way"]}, "tone": [None, "either way"]}]
    corpus = load_corpus(declaration, _corpus(tmp_path, texts))
    assert [(t.labels["said"].answer, t.choices["tone"].answer) for t in corpus.texts] == [("abstain", "abstain"), (None, None)]
    worded = dict(TEXTS_LABELLED[0], labels={"leaked": ["abstain", "the old word for abstaining"]})
    with pytest.raises(InvalidInputError, match="names no option"):
        load_corpus(DECLARATION, _corpus(tmp_path, [worded]))


# A target whose every label abstained has no scored metric, which the report writes as n/a, while a
# scored target's row reads as before.
# am[verifies a-integrate-binding-empty-score-render-1019@aa4d95]
def test_a_target_with_no_scored_label_renders_its_absent_metrics() -> None:
    options = list(DECLARATION.bindings[0].options)
    right = [("seat", "seat", {"seat": 0.9, "receiving_seat": 0.05, NO_MATCH: 0.05})] * 3
    report = {"corpus": {"version": 2, "texts": 3, "sha256": "0" * 64}, "model": [DECLARATION.model],
              "declaration": {"domain": DECLARATION.name, "digest": DECLARATION.digest},
              "targets": {"leaked Seat": {**score([], options), "abstained": 3},
                          "scored": {**score(right, options), "abstained": 0}}}
    rows = {line.split(" | ")[0]: line for line in markdown(report).splitlines() if line.startswith("| leaked") or line.startswith("| scored")}
    assert rows["| leaked Seat"] == "| leaked Seat | 0 | n/a (n/a) |  | n/a (n/a) | n/a (n/a) |"
    assert rows["| scored"].startswith("| scored | 3 | 1.00 (") and "seat 1.00 of 3" in rows["| scored"]

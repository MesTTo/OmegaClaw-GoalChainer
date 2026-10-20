"""Purpose: verify the planner's half of reading bindings. A procedure literal may place a signal on one
declared entity, (On (Signal S) E), read, written back and negated as one literal; the bigraph section
term anchors it at each entity a binding of S offers and nowhere else, the bare signal's anchor staying as
the section declares it, and a section cannot anchor one itself; a library may name it only where a
binding offers its entity. An entity reading informs exactly its entity's qualified literal, unchecked
as model-proposed and checked as a deterministic reading would be, while another entity's literal and
the bare signal's reading stay apart; plan and admit refuse an entity reading no binding offers and a
value that is no reading; and in every state an entity reading's row is the shared ordinary reading row
with only its claim placed on the entity, an unknown reading having none."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, strategies as st

from goal_chainer.domains.loader import _packaged_directory, read_domain
from goal_chainer.domains.model import DomainError
from goal_chainer.errors import InvalidInputError
from goal_chainer.planning.procedures import (
    NegatedLiteral,
    ProcedureError,
    QualifiedLiteral,
    SignalLiteral,
    literal_term,
    literal_text,
    negate,
    read_literal,
    read_procedures,
    section_term,
)
from goal_chainer.planning.projection import Admitted, Blocked, NoPlan, Plan, Unsolved, admit, plan
from goal_chainer.reading_projection import EntityReading
from goal_chainer.relevance.signals import SignalReading
from request_support import budget

TASK = (_packaged_directory() / "task_control.metta").read_text(encoding="utf-8")
OWNER_MISMATCH = '(gc-signal owner_mismatch "the work belongs with a different owner or seat")\n'
# A reading section over the packaged task-control domain declaring owner_mismatch as its one proposition,
# in place of the domain's own gc-signal form, since a proposition and a signal share one namespace of ids;
# the section still anchors it bare on the task, and it is bound over Seat, whose two described entities it
# offers.
READING = (
    "(gc-reading-domain task-control-bindings)",
    '(gc-reading-model "jev-1.13.0")',
    '(gc-reading-language "en")',
    '(gc-reading-instructions "Does the text support the proposition? Proposition: ")',
    '(gc-reading-option yes for "the text says it")',
    '(gc-reading-option no against "the text denies it")',
    '(gc-reading-option unclear none "the text leaves it open")',
    '(gc-reading-proposition owner_mismatch "The task is held by a seat that does not own it."'
    ' "Is the task held by a seat that does not own it?")',
    '(gc-reading-binding owner_mismatch Seat "Which seat does the text say holds the task? Statement: "'
    ' "The text names no seat.")',
    '(gc-ranking-instruction "Rank the passages.")',
)
assert OWNER_MISMATCH in TASK
BOUND = TASK.replace(OWNER_MISMATCH, "") + "\n" + "\n".join(READING)
DOMAIN = read_domain(BOUND, "planning-bindings", budget=budget())
SEAT = QualifiedLiteral(SignalLiteral("owner_mismatch"), "seat")
NAMES = st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True)
AT = datetime(2026, 10, 19, 6, 0, tzinfo=timezone.utc)
GOAL = SignalLiteral("receiving_owner_accepts")
# The goal read refuted, so a plan must bring it about.
REFUTED_GOAL = SignalReading("receiving_owner_accepts", "refuted", "test", "deterministic",
                             observed_at=AT - timedelta(minutes=1))


# The section's anchors as (subject, entity, via) texts.
# am[verifies a-ev-bnd-qualified-anchors-1019@4da23d]
def _anchors(term) -> set[tuple[str, str, str]]:
    return {(str(row.children[1]), str(row.children[2]), str(row.children[3]))
            for row in term.children[1:] if str(row.children[0]) == "gc-brs-literal"}


# A one-procedure library escalating to the receiving owner while `when` holds.
# am[verifies a-ev-bnd-qualified-acceptance-1019@47bdad]
def _library(when: str) -> str:
    return f"""(gc-procedures task-control-v1)
(gc-procedure reassign (Achieves (Signal receiving_owner_accepts)) (When {when})
  (Steps (Step ask act escalate (After))))"""


LIBRARY = read_procedures(_library("(On (Signal owner_mismatch) seat)"), "bindings-procedures.metta", DOMAIN,
                          budget=budget())


# owner_mismatch read `state` by `estimator`, placed on `entity` as a binding's answer places it.
# am[verifies a-ev-bnd-readings-evidence-1019@a88ded]
def _placed(entity: str, *, signal: str = "owner_mismatch", state: str = "detected",
            estimator: str = "model-proposed") -> EntityReading:
    reading = SignalReading(signal, state, "jev:test", estimator, observed_at=AT - timedelta(minutes=1))
    return EntityReading(reading=reading, entity=entity, entity_source="jev:test:key")


# The plan for the goal under LIBRARY, waiting on owner_mismatch on the seat, and the admission of its
# start step, planned from a checked entity reading on the seat, against `readings`.
# am[verifies a-ev-bnd-readings-evidence-1019@a88ded]
def _plan(readings: list):
    return plan((GOAL,), domain=DOMAIN, library=LIBRARY, readings=readings, journal=(), rows=(), receipts={},
                at=AT, budget=budget())


# am[verifies a-ev-bnd-readings-evidence-1019@a88ded]
def _admitted(readings: list):
    start = _plan([REFUTED_GOAL, _placed("seat", estimator="deterministic")]).steps[0]
    return admit(start, instance_id=None, domain=DOMAIN, library=LIBRARY, readings=readings, journal=(), rows=(),
                 at=AT, budget=budget())


# am[verifies a-ev-bnd-qualified-literal-1019@8d05ed]
@given(NAMES, NAMES)
def test_a_qualified_literal_reads_back_as_written_and_negates_as_any_literal(signal: str, entity: str) -> None:
    literal = QualifiedLiteral(SignalLiteral(signal), entity)
    text = literal_text(literal)
    assert text == f"(On (Signal {signal}) {entity})"
    assert read_literal(text, "binding test", budget=None) == literal
    assert read_literal(f"(Not {text})", "binding test", budget=None) == negate(literal) == NegatedLiteral(literal)
    assert negate(negate(literal)) == literal
    assert str(literal_term(literal)) == f'(On (Signal "{signal}") {entity})'


# Only a signal goes on an entity, and the entity is a symbol: a statement, a negation, a missing entity
# or a quoted one is no qualified literal.
# am[verifies a-ev-bnd-qualified-literal-1019@8d05ed]
@pytest.mark.parametrize("text", [
    '(On (Statement (sn c "x")) seat)',
    "(On (Not (Signal owner_mismatch)) seat)",
    "(On (Signal owner_mismatch))",
    '(On (Signal owner_mismatch) "seat")',
    "(On (Signal owner_mismatch) seat extra)",
])
def test_a_qualified_literal_places_a_signal_on_an_entity_symbol(text: str) -> None:
    with pytest.raises(ProcedureError):
        read_literal(text, "binding test", budget=None)


# Each entity the binding offers, seat and receiving_seat, anchors owner_mismatch's qualified literal with no
# Via; the task, which no binding offers, anchors none, and the bare signal keeps its declared anchor.
# am[verifies a-ev-bnd-qualified-anchors-1019@4da23d] am[verifies c-bnd-literal-first-anchor-1019@1ad5bb]
def test_each_binding_anchors_its_signal_on_every_entity_it_offers_and_the_bare_anchor_stays() -> None:
    anchors = _anchors(section_term(DOMAIN))
    qualified = {anchor for anchor in anchors if anchor[0].startswith("(On ")}
    assert qualified == {
        ('(On (Signal "owner_mismatch") seat)', "(On seat)", "(Via)"),
        ('(On (Signal "owner_mismatch") receiving_seat)', "(On receiving_seat)", "(Via)"),
    }
    assert ('(Signal "owner_mismatch")', "(On task)", "(Via)") in anchors
    plain = read_domain(TASK, "planning-bindings", budget=budget())
    assert anchors - qualified == _anchors(section_term(plain))


# The section's own checks read an anchor of anything but a signal or a statement as (Literal TEXT) and
# refuse it, so a qualified literal's anchors come from bindings alone.
# am[verifies a-ev-bnd-qualified-anchors-1019@4da23d]
def test_a_section_cannot_anchor_a_qualified_literal_itself() -> None:
    with pytest.raises(DomainError):
        read_domain(BOUND + "\n(gc-brs-literal (On (Signal owner_mismatch) seat) (On seat))", "planning-bindings",
                    budget=budget())


# A library may name owner_mismatch on an entity the binding offers, either way round; on the task, which no
# binding offers, or for a signal no binding binds, the literal is unanchored; and a signal the domain does
# not declare is undeclared, as for a bare signal.
# am[verifies a-ev-bnd-qualified-acceptance-1019@47bdad]
@pytest.mark.parametrize("when, problem", [
    ("(On (Signal owner_mismatch) seat)", None),
    ("(Not (On (Signal owner_mismatch) receiving_seat))", None),
    ("(On (Signal owner_mismatch) task)", "unanchored-literal"),
    ("(On (Signal review_open) seat)", "unanchored-literal"),
    ("(On (Signal no_such_signal) seat)", "undeclared-signal"),
])
def test_a_library_names_a_signal_on_an_entity_only_where_a_binding_offers_it(when: str, problem: str | None) -> None:
    if problem is None:
        library = read_procedures(_library(when), "bindings-procedures.metta", DOMAIN, budget=budget())
        assert library.procedures[0].when == (read_literal(when, "binding test", budget=None),)
    else:
        with pytest.raises(ProcedureError, match=problem):
            read_procedures(_library(when), "bindings-procedures.metta", DOMAIN, budget=budget())


# A binding's answer is the model's, so an entity reading on the seat leaves the seat's qualified literal an
# assumption the plan names and never acts on; read as a deterministic source would, it is checked and the
# plan acts. Placed on the receiving seat, or read bare on the task even deterministically, it says nothing
# of the seat, whose literal stays unknown and so is not even an assumption: the goal is blocked with no
# alternative (c-bnd-bare-instance-breaks-separation-1019).
# am[verifies a-bnd-planner-row-1019@c65aa2] am[verifies a-ev-bnd-readings-tests-1019@345608]
# am[verifies c-bnd-bare-instance-breaks-separation-1019@435e9e]
@pytest.mark.parametrize("evidence, answer", [
    ([_placed("seat")], "assumed"),
    ([_placed("seat", estimator="deterministic")], "planned"),
    ([_placed("receiving_seat")], "unknowable"),
    ([SignalReading("owner_mismatch", "detected", "test", "deterministic", observed_at=AT - timedelta(minutes=1))],
     "unknowable"),
], ids=["seat-model-proposed", "seat-deterministic", "receiving-seat", "bare-signal"])
def test_an_entity_reading_informs_its_entity_s_literal_alone(evidence: list, answer: str) -> None:
    found = _plan([REFUTED_GOAL, *evidence])
    steps = [("start", "reassign", None), ("act", "reassign", "ask"), ("finish", "reassign", None)]
    if answer == "planned":
        assert isinstance(found, Plan) and found.assumptions == ()
        assert [(s.kind, s.procedure, s.step) for s in found.steps] == steps
    elif answer == "assumed":
        assert isinstance(found, NoPlan) and found.unsolved == (Unsolved(GOAL, "blocked", ()),)
        assert found.alternative.assumptions == (SEAT,)
        assert [(s.kind, s.procedure, s.step) for s in found.alternative.steps] == steps
    else:
        assert found == NoPlan((Unsolved(GOAL, "blocked", ()),), None)


# Admission asks the same claim of the seat's literal: a checked entity reading on the seat admits the plan's
# start, and one on the receiving seat leaves it blocked on the seat's literal.
# am[verifies a-bnd-planner-literals-1019@57d268] am[verifies a-ev-bnd-readings-tests-1019@345608]
def test_admission_reads_the_qualified_literal_the_entity_reading_claims() -> None:
    assert isinstance(_admitted([REFUTED_GOAL, _placed("seat", estimator="deterministic")]), Admitted)
    assert _admitted([REFUTED_GOAL, _placed("receiving_seat", estimator="deterministic")]) == Blocked((SEAT,))


# The planner refuses evidence it cannot place: an entity reading of a signal no binding binds, one on an
# entity its binding does not offer, and a value that is no reading, by plan and admit alike.
# am[verifies a-ev-bnd-readings-evidence-1019@a88ded] am[verifies a-ev-bnd-readings-tests-1019@345608]
@pytest.mark.parametrize("reading, message", [
    (_placed("seat", signal="review_open"), "no reading binding"),
    (_placed("task"), "no reading binding"),
    ("owner_mismatch detected on seat", "is a SignalReading or an EntityReading"),
], ids=["unbound-signal", "unoffered-entity", "not-a-reading"])
def test_evidence_no_binding_places_is_refused(reading, message: str) -> None:
    with pytest.raises(InvalidInputError, match=message):
        _plan([REFUTED_GOAL, reading])
    with pytest.raises(InvalidInputError, match=message):
        _admitted([REFUTED_GOAL, reading])


# The row mapping's cases: each state, each estimator a definite reading may carry (an unknown reading has
# none), each validity (forever, current at AT, or expired before it) and each entity the binding offers,
# few enough to take every one.
# am[verifies a-bnd-row-equivalence-1019@8c9dc6]
_ROW_CASES = [
    (state, estimator, until, entity)
    for state in ("detected", "refuted", "unknown")
    for estimator in (("model-proposed", "deterministic", "measured") if state != "unknown" else (None,))
    for until in (None, timedelta(minutes=1), -timedelta(minutes=1))
    for entity in ("seat", "receiving_seat")
]


# An entity reading's row is the shared vocabulary's ordinary reading row with only its claim placed on the
# entity: gc-pk-entity-rows over (EntityReading S E STATE EST VAL ID) is gc-reading-rows over
# ((Reading S STATE EST VAL ID)), ID the entity reading's own observation id, each (From (Signal S) SRC)
# becoming (From (On (Signal S) E) SRC) and each (From (Not (Signal S)) SRC) becoming
# (From (Not (On (Signal S) E)) SRC), SRC unchanged. The shared rule keeps a definite reading whatever its
# estimator or validity, an expired one included, which justification withdraws at its instant, and drops an
# unknown one, so a detected or refuted entity reading has one row and an unknown one none.
# am[verifies a-bnd-planner-row-1019@c65aa2] am[verifies a-bnd-row-equivalence-1019@8c9dc6]
@pytest.mark.parametrize(("state", "estimator", "until", "entity"), _ROW_CASES)
def test_an_entity_row_is_the_shared_reading_row_with_its_claim_on_the_entity(state, estimator, until,
                                                                              entity) -> None:
    from metta import Expression, Symbol

    from goal_chainer.planning import group
    from goal_chainer.reading_projection import entity_term
    from goal_chainer.relevance.policy import term
    from policy_support import group_answers

    reading = SignalReading("owner_mismatch", state, "jev:test", estimator, observed_at=AT - timedelta(minutes=2),
                            valid_until=None if until is None else AT + until)
    placed = entity_term(EntityReading(reading=reading, entity=entity, entity_source="jev:test:key"))
    _, signal, _, read_state, read_estimator, validity, identity = list(placed)
    [rows] = group_answers(group.PLANNING, "(gc-pk-entity-rows {readings})", readings=Expression((placed,)))
    [shared] = group_answers(group.PLANNING, "(gc-reading-rows {readings})", readings=Expression(
        (term("Reading", signal, read_state, read_estimator, validity, identity),)))
    on, negation, at_entity = Symbol("On"), Symbol("Not"), Symbol(entity)

    def on_entity(row):
        head, claim, source = row
        return (head, (negation, (on, claim[1], at_entity)) if claim[0] == negation else (on, claim, at_entity),
                source)

    assert rows == tuple(on_entity(row) for row in shared)
    assert len(rows) == (0 if state == "unknown" else 1)

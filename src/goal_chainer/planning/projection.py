"""Purpose: plan over a domain's bigraph state and admit each plan step against the current evidence,
through the planner's MeTTa module group (planning/group.py) under the caller's RunBudget.

    plan(goal, *, domain, library, readings, journal, rows, receipts, at, budget) -> Plan | Inquiry | NoPlan
    admit(step, *, instance_id, domain, library, readings, journal, rows, at, budget)
        -> Admitted | Blocked | Ambiguous | Stale

The domain's bigraph section declares the world; the library's procedures compile to reaction rules
over it; and the state is that world plus what justification establishes from the evidence: the
readings, through the shared vocabulary's row rule, the entity readings a reading binding places,
through the same rule with the claim placed on the entity, the executor's journal, and any other
justification rows the caller holds. Signal evidence has one owner, the readings, which the relevance
review justifies through the same row rule, so an extra row argues about statements alone and reaches
the planner's own evidence only through claims: it claims a statement or its negation, or withdraws
such a row, and cites no Reading, Journal or Receipt observation and no row but a statement row, or it
is refused. The planner builds those observations' rows itself, and a reference to one would read it by
its identity, which outlives its standing. The review and the plan then never read different signal
evidence from one snapshot, and no statement is checked by a reading or receipt nobody holds, nor
withdrawn by a reading that has expired. A plan is a scheduling answer, never an authorization (proposal
3, sections 5 and 6): review, norms, licensing, freshness and receipts still gate each step. Each step
carries a Witness, so admission answers Stale rather than execute a transition the current library,
section or planner would compile differently, Ambiguous rather than choose between different
transitions, and Blocked naming what the evidence does not yet establish. A budget the evaluation
exhausts raises InferenceBudgetExceeded or ReviewTimeout, never NoPlan.

What a Plan promises: it holds in every world the snapshot admits, a world being any settling to rest
that agrees with every checked reading, since the readings observe the world at rest and a reading still
valid holds at the plan's time. That the readings are current is the caller's precondition, and nothing
here checks it: a reading taken before an act ran observes the world before that act, and the refusal of
a reading observed after the plan's time, like the decay of one past its valid_until, says nothing of the
acts in between. So once a receipt reports an act applied, the caller refreshes or leaves out each
reading of what the act may have changed, what its procedure's Finish writes and the Derives write in
turn included, before planning or admitting again. A snapshot that admits no world is refused, by plan
and admit alike, as PlanningRefused naming Contradicted and what the snapshot knows of the literals
Derives and the done journal instances' Finishes touch; deciding it enumerates those literals' values,
under the budget. The refusal checks that the snapshot is consistent and detects no stale reading: a
reading an act made stale that some world still agrees with is taken as current, and a plan may rest on
it. Within an inquiry, a branch whose answer would admit no world is a NoPlan whose goal literals are all
contradicted. A world, not the plan, orders the Finishes and Derives enabled together, so a plan never
passes a state whose Finishes and Derives can rest two ways, and declaration order only ranks orders that
rest alike; a library whose Derives can undo one another forever is refused when it is read. A journal
instance whose steps all have receipts may have finished before the readings. One every admitted world
finished did: what it achieved that every such world holds is known, and its plan step is a Finish that
writes nothing. One no admitted world finished is still open, and a plan may finish it. One some worlds
finished and others did not is uncertain, so a plan takes neither its finish nor what that finish writes
for granted.

A plan's cost reads each procedure's track, its record of bringing its Achieves literals about, and the
tracks come only from receipts, never from the caller: planning/feedback.metta reads the journal and the
receipt-v2 documents the caller holds for its Receipt events, relevance's assess_attempt grades each
applied attempt against each Achieves literal, and a track is counted only under the library's declared
(gc-track-promotion (Trials N) (Threshold THETA)), with the procedure's record complete and N attributed
trials, its holding SNARS's track-record cut at THETA. A library declaring no promotion promotes nothing.
The caller's journal and receipts are the snapshot at the plan's time, so a receipt issued after it is
refused, as a reading observed or an attempt dispatched after it is, and no track rests on the future.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from ..domains.model import Domain
from ..errors import InvalidInputError, ProtocolError, safe_repr
from ..reading_projection import EntityReading, entity_term
from ..relevance.errors import RelevanceError
from ..relevance.instants import microseconds
from ..relevance.receipt import Receipt as ReceiptDocument
from ..relevance.receipt import assess_attempt, check_receipt
from ..relevance.signals import SignalReading, reading_term
from ..runtime.budget import RunBudget
from ..runtime.engine import shared_evaluation
from ..runtime.evaluator import evaluate, prepare
from .group import PLANNING, refused
from .procedures import (
    ActStep,
    NegatedLiteral,
    ProcedureLibrary,
    ProcedureLiteral,
    QualifiedLiteral,
    SignalLiteral,
    StatementLiteral,
    library_term,
    literal_term,
    literal_text,
    names_term,
    section_term,
    statement_claim,
)

StepKind = Literal["start", "act", "investigate", "finish", "derive"]
# The kind of a step whose rule names a symbol part rather than one of the procedure's step ids.
# am[implements a-ev-pk-python-api-1018@db9b94]
_KIND_OF_PART: dict[str, StepKind] = {"Start": "start", "Finish": "finish", "Derive": "derive"}


# --- the executor's journal ----------------------------------------------------------------------
# The events an executor journals; the planner derives from them the instances still open and the
# justification rows of each step's progress (c-ev-pk-typed-rows-1018), so a caller never passes an
# agenda and rows that disagree.


# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class Started:
    """The executor started an instance of a procedure; `journal` names the journal entry."""

    instance_id: str
    procedure: str
    journal: str


# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class Dispatched:
    """An attempt at an instance's step is in flight, so the step's progress is unknown until its receipt.

    `decision` is the dispatched step's witness digest, which the attempt's receipt names as its
    review_fingerprint, and `at` when the executor dispatched it, after the admission that admitted it, so
    no reading that admission rested on was observed later (c-ev-fb-dispatch-after-admission-1018)."""

    instance_id: str
    step: str
    attempt: str
    decision: str
    at: datetime


# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class Receipt:
    """A receipt for an attempt: `applied` says the host applied the step."""

    receipt: str
    instance_id: str
    step: str
    attempt: str
    applied: bool


# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class Superseded:
    """A later receipt for the same attempt replaces an earlier one."""

    receipt: str
    latest: str


# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class Finished:
    """The executor finished an instance, which then leaves the agenda."""

    instance_id: str


JournalEvent = Started | Dispatched | Receipt | Superseded | Finished


# A procedure's record of bringing a literal about, which the cost reads: an application whose
# procedure's record does not hold for every Achieves literal counts as unestablished.
# am[implements a-ev-pk-commitment-cost-1018@c9673e]
@dataclass(frozen=True, slots=True)
class Track:
    procedure: str
    literal: ProcedureLiteral
    holds: bool


# --- answers ---------------------------------------------------------------------------------------


# What a step must still match when admitted: its compiled rules' name, the digest of the planning
# group's identity and every compiled rule bearing that name, and the image of each redex node that is
# a declared entity or the agenda, all as MeTTa text so the journal can record it.
# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class Witness:
    rule: str
    digest: str
    images: tuple[tuple[str, str], ...]


# `application` numbers the plan's procedure applications from 0 in plan order; `instance_id` is the
# executor's id when the journal started the application before this plan. `step` is the act's or
# investigation's id, None for start, finish and derive. `binding` maps each redex node bound to a
# declared entity to that entity.
# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class PlanStep:
    procedure: str
    step: str | None
    kind: StepKind
    application: int
    instance_id: str | None
    binding: tuple[tuple[str, str], ...]
    witness: Witness


# A model-valid plan when `assumptions` is empty; NoPlan's explanatory alternative names what it
# assumes, and is never a plan to act on.
# am[implements a-ev-pk-python-api-1018@db9b94] am[implements a-ev-pk-search-1018@f96ce8]
@dataclass(frozen=True, slots=True)
class Plan:
    steps: tuple[PlanStep, ...]
    established: bool
    assumptions: tuple[ProcedureLiteral, ...] = ()


# Learning `literal`, which `investigator` observes, opens a plan in at least one branch.
# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class Inquiry:
    literal: ProcedureLiteral
    investigator: str
    if_true: Answer
    if_false: Answer


# A goal literal the state does not establish: no rule writes it (no-way), every rule writing it reads
# a literal no investigator covers (unknowable, naming those literals), the inquiry branch's answer it
# belongs to admits no world (contradicted), or otherwise blocked.
# am[implements a-ev-pk-python-api-1018@db9b94] am[implements a-ev-pc-c1-admission-1019@92a093]
@dataclass(frozen=True, slots=True)
class Unsolved:
    literal: ProcedureLiteral
    reason: Literal["no-way", "blocked", "unknowable", "contradicted"]
    unknowable: tuple[ProcedureLiteral, ...] = ()


# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class NoPlan:
    unsolved: tuple[Unsolved, ...]
    alternative: Plan | None


Answer = Plan | Inquiry | NoPlan


# One executed step's progress the state does not establish: the instance's `step` done, or not done.
# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class Progress:
    instance_id: str
    step: str
    done: bool


# `occurrence` is the kernel's occurrence term as MeTTa text: which entities the step acts on.
# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class Admitted:
    occurrence: str


# What the evidence does not establish for the step: each literal it reads without the value it reads, and
# each executor Progress it waits on. Empty, the step has no transition though every literal it reads holds,
# as for a Derive whose writes the evidence already holds: the world has applied it, so nothing remains to
# admit (i-ev-pc-admit-unnamed-block-1019).
# am[implements a-ev-pk-python-api-1018@db9b94] am[implements a-ev-pc-admit-derive-reads-1019@450a34]
@dataclass(frozen=True, slots=True)
class Blocked:
    waiting_on: tuple[ProcedureLiteral | Progress, ...]


# The matching occurrences fall in `classes` > 1 successor classes; the executor must not choose.
# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class Ambiguous:
    classes: int


# The step's rules or the planner changed since the plan: `expected` and `found` are the digests.
# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class Stale:
    expected: str
    found: str


Verdict = Admitted | Blocked | Ambiguous | Stale


# A section, library, journal or snapshot the planner refuses, with every problem it names.
# am[implements a-ev-pk-python-api-1018@db9b94]
class PlanningRefused(InvalidInputError):
    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__(f"The planner refused its input: {'; '.join(problems)}.", details={"problems": problems})
        self.problems = problems


# --- entries ---------------------------------------------------------------------------------------


# Time: one evaluation of gc-pk-run-plan, charged to `budget`, plus a digest per compiled rule name.
# am[implements a-ev-pk-python-api-1018@db9b94] am[implements a-ev-pk-projection-1018@e5d57e]
# am[rests-on c-integrate-c1-currentness-boundary-1019@4ebdc2] am[implements a-ev-pc-currentness-boundary-1019@3cd29d]
def plan(goal: Sequence[ProcedureLiteral], *, domain: Domain, library: ProcedureLibrary,
         readings: Sequence[SignalReading | EntityReading], journal: Sequence[JournalEvent], rows: Sequence[Any],
         receipts: Mapping[str, ReceiptDocument], at: datetime, budget: RunBudget) -> Answer:
    """The least plan for every literal of `goal` from the state the evidence establishes, else the
    cheapest inquiry, else NoPlan. `readings` holds SignalReadings and EntityReadings, each placing its
    reading on an entity a reading binding of its signal offers. `rows` are further justification rows
    as pymetta atoms, each claiming (Statement S) or its negation, S a SNARS statement as a library
    writes it or literal_term's text, or withdrawing such a row, and citing no reading's, journal's or
    receipt's observation; a statement may rest on a signal's claim, (Claim (Signal S)).
    `receipts` maps each journal Receipt id whose receipt-v2 document the caller holds to that document,
    parsed by relevance.receipt.parse_receipt and issued by `at`; the procedures' tracks come from them
    alone."""

    evidence = _evidence(readings, journal, _planner_rows(rows, budget), at, domain)
    tracks = _tracks(library, journal, receipts, evidence.children[1], at, budget)
    answer = evaluate(PLANNING, "gc-pk-run-plan", _model(domain, library),
                      _term().Goal(*(literal_term(literal) for literal in goal)),
                      evidence, _list(_track(track) for track in tracks), budget=budget)
    parts = _parts(answer, "Planned", 2)
    digests = _digests(parts[1].children, prepare(PLANNING, budget=budget))
    return _answer(parts[0], _Reading(library, digests, _entities(domain)))


# Time: one evaluation of gc-pk-run-admit, charged to `budget`, plus one digest.
# am[implements a-ev-pk-python-api-1018@db9b94] am[implements a-ev-pk-projection-1018@e5d57e]
# am[implements a-integrate-planner-step-consistency-1018@fc6d64] am[implements a-integrate-planner-input-failures-1018@b84418]
# am[rests-on c-integrate-c1-currentness-boundary-1019@4ebdc2] am[implements a-ev-pc-currentness-boundary-1019@3cd29d]
def admit(step: PlanStep, *, instance_id: str | None, domain: Domain, library: ProcedureLibrary,
          readings: Sequence[SignalReading | EntityReading], journal: Sequence[JournalEvent], rows: Sequence[Any],
          at: datetime, budget: RunBudget) -> Verdict:
    """Whether `step` may run now on the executor's instance `instance_id`, which a start or derive
    step has none of and every other step must name."""

    if (step.kind in ("start", "derive")) != (instance_id is None):
        raise InvalidInputError(
            f"A {step.kind} step is admitted {'without' if step.kind in ('start', 'derive') else 'with'} "
            "the executor's instance id.",
            details={"kind": step.kind, "instance_id": instance_id},
        )
    from metta import Symbol  # noqa: PLC0415 (pymetta is imported only once an engine exists)

    S = _term()

    # pymetta's parse runs on the engine, so the witness is read as shared engine work: beside running
    # evaluations, once no load holds the engine alone, and raising its refusals here.
    # am[implements a-integrate-admit-concurrency-1018@b0a4e3]
    def witness(engine: Any) -> tuple[Any, Any]:
        rule = _witness_rule(step)
        images = _list(S.Bound(_witness_term(node, f"image {index} node"), _witness_term(image, f"image {index}"))
                       for index, (node, image) in enumerate(_witness_images(step.witness.images)))
        return rule, images

    rule, images = shared_evaluation(witness, budget=budget)
    answer = evaluate(PLANNING, "gc-pk-run-admit", _model(domain, library), rule,
                      Symbol("None") if instance_id is None else S.Inst(instance_id), images,
                      _evidence(readings, journal, _planner_rows(rows, budget), at, domain), budget=budget)
    verdict, rules = _parts(answer, "Admission", 2)
    problems = refused(verdict)
    if problems is not None:
        raise PlanningRefused(problems)
    found = _digest(prepare(PLANNING, budget=budget), [str(r) for r in rules.children])
    if found != step.witness.digest:
        return Stale(step.witness.digest, found)
    # The step's own fields are what its unchanged witness determines, derived as the plan derived them:
    # its kind is its declared step's, and its binding is the witness's images of declared entities. A
    # witness whose rules are gone answered Stale above, so only a live step is refused here. Its
    # application number is report-only and identifies nothing the planner executes, so it is not read.
    declared = _kind(step.procedure, step.step, str(rule.children[3]), library)
    if declared is not None and declared != step.kind:
        raise InvalidInputError(f"The step's kind {step.kind} is not its declared step's, {declared}.",
                                details={"procedure": step.procedure, "step": step.step, "kind": step.kind,
                                         "declared": declared})
    binding = tuple(tuple(pair) for pair in step.binding)
    if binding != _binding(step.witness.images, _entities(domain)):
        raise InvalidInputError("The step's binding is not the declared entities its witness's images name.",
                                details={"binding": repr(step.binding)[:200]})
    kind = _head(verdict)
    if kind == "Admitted" and len(verdict.children) == 2:
        return Admitted(str(verdict.children[1]))
    if kind == "Blocked":
        return Blocked(tuple(_unmet(unmet) for unmet in verdict.children[1:]))
    if kind == "Ambiguous" and len(verdict.children) == 2:
        return Ambiguous(verdict.children[1].value)
    raise ProtocolError("The planner answered an admission out of contract.", details={"answer": str(answer)})


# A witness is the planner's own answer handed back by the caller, so each of its texts must read as
# exactly one ground MeTTa term. pymetta's parse consumes the whole text and refuses two terms, trailing
# text, an unbalanced parenthesis or nothing (measured, ai-tmp/evidence/probes/probe_parse_whole.py),
# but reads $x as a variable, which matching would bind to anything, so a term holding one is refused as
# no data. Anything else is the caller's malformed input, refused naming the field, never an engine
# fault (c-integrate-request-input-leaks-762662a-1018); only the parse is guarded, so evaluation's own
# failures keep their types. Call it on a thread holding the engine, shared or alone.
# am[implements a-integrate-planner-input-failures-1018@b84418] am[rests-on c-integrate-request-input-leaks-762662a-1018@380521]
def _witness_term(text: object, field: str) -> Any:
    from metta import MettaError, parse  # noqa: PLC0415

    if not isinstance(text, str):
        raise InvalidInputError(f"The step's witness {field} must be text, not {type(text).__name__}.",
                                details={"field": field})
    try:
        term = parse(text)
    except MettaError as error:
        raise InvalidInputError(f"The step's witness {field} is not one MeTTa term: {text!r}",
                                details={"field": field, "text": text}) from error
    if not _ground(term):
        raise InvalidInputError(f"The step's witness {field} is not ground data: {text!r}",
                                details={"field": field, "text": text})
    return term


# Whether a term holds no variable. Time: one visit per subterm.
# am[implements a-integrate-planner-input-failures-1018@b84418]
def _ground(term: Any) -> bool:
    from metta import Expression, Variable  # noqa: PLC0415

    if isinstance(term, Variable):
        return False
    return all(_ground(child) for child in term.children) if isinstance(term, Expression) else True


# The witness's rule names the compiled rule the step was planned through, (Step INDEX "PROCEDURE"
# PART), PART the step's id or Start, Finish or Derive for a step with none, and it must name the very
# step it comes with, so a step and a witness from different plans never pass for one admission. The
# planner selects rules by equality with this term, so any other shape would match none and answer
# nothing. Call it on a thread holding the engine, shared or alone.
# am[implements a-integrate-planner-input-failures-1018@b84418]
def _witness_rule(step: PlanStep) -> Any:
    from metta import Expression, Grounded, Symbol  # noqa: PLC0415

    rule = _witness_term(step.witness.rule, "rule")
    parts = rule.children if isinstance(rule, Expression) else []
    index = parts[1].value if len(parts) == 4 and isinstance(parts[1], Grounded) else None
    if not (len(parts) == 4 and str(parts[0]) == "Step" and type(index) is int and index >= 0 and _is_string(parts[2])
            and (_is_string(parts[3]) or (isinstance(parts[3], Symbol) and str(parts[3]) in _KIND_OF_PART))):
        raise InvalidInputError('The step\'s witness rule must be (Step INDEX "PROCEDURE" PART).',
                                details={"rule": step.witness.rule})
    procedure, part = parts[2].value, parts[3]
    same = (procedure == step.procedure
            and (part.value == step.step if _is_string(part) else step.step is None and _KIND_OF_PART[str(part)] == step.kind))
    if not same:
        raise InvalidInputError("The step's witness rule names another step than the one it comes with.",
                                details={"rule": step.witness.rule, "procedure": step.procedure, "step": step.step,
                                         "kind": step.kind})
    return rule


# The witness's images as (node, image) pairs, or a refusal for any other shape.
# am[implements a-integrate-planner-input-failures-1018@b84418]
def _witness_images(images: object) -> list[tuple[object, object]]:
    if not isinstance(images, (tuple, list)) or not all(isinstance(pair, (tuple, list)) and len(pair) == 2
                                                         for pair in images):
        raise InvalidInputError("The step's witness images must be (node, image) pairs.",
                                details={"images": repr(images)[:200]})
    return [(node, image) for node, image in images]


# --- terms ---------------------------------------------------------------------------------------


# am[implements a-ev-pk-python-api-1018@db9b94]
def _term() -> Any:
    from metta import S  # noqa: PLC0415

    return S


# am[implements a-ev-pk-python-api-1018@db9b94]
def _list(values: Any) -> Any:
    from metta import Expression  # noqa: PLC0415

    return Expression(tuple(values))


# am[implements a-ev-pk-python-api-1018@db9b94] am[implements a-ev-bnd-qualified-anchors-1019@4da23d]
def _model(domain: Domain, library: ProcedureLibrary) -> Any:
    return _term().Model(section_term(domain), names_term(domain), library_term(library))


# A reading observed or an attempt dispatched after `at` would let the plan rest on the future, so it is
# refused, as the relevance review refuses such a reading, and _tracks refuses a receipt issued after it; the
# row rule itself is the shared vocabulary's gc-reading-rows. An entity reading is refused unless a reading
# binding of its signal offers its entity, since only those entities anchor its qualified literal, and its
# term is reading_projection's entity_term, which the planner's own module turns into rows; any other value
# is no reading.
# am[implements a-ev-pk-python-api-1018@db9b94] am[related a-rel-pj-reading-row-1018@03ad71]
# am[implements a-rel-reading-term-one-home-1018@522700] am[implements a-ev-fb-request-receipts-1018@4c8f23]
# am[implements a-ev-bnd-readings-evidence-1019@a88ded] am[rests-on c-ev-bnd-readings-one-sequence-1019@0927b4]
def _evidence(readings: Sequence[SignalReading | EntityReading], journal: Sequence[JournalEvent], rows: Sequence[Any],
              at: datetime, domain: Domain) -> Any:
    S = _term()
    bindings = domain.readings.bindings if domain.readings is not None else ()
    for reading in readings:
        placed = reading.reading if isinstance(reading, EntityReading) else reading
        if not isinstance(placed, SignalReading):
            raise InvalidInputError("A reading is a SignalReading or an EntityReading.",
                                    details={"reading": safe_repr(reading)[:200]})
        if placed.observed_at is not None and placed.observed_at > at:
            raise InvalidInputError(f"A reading of {placed.signal} was observed after the plan's time.",
                                    details={"signal": placed.signal, "observed_at": placed.observed_at.isoformat(),
                                             "at": at.isoformat()})
        if isinstance(reading, EntityReading) and not any(
                binding.signal == placed.signal and reading.entity in (entity for entity, _ in binding.entities)
                for binding in bindings):
            raise InvalidInputError(
                f"An entity reading places {placed.signal} on {reading.entity}, which no reading binding of it offers.",
                details={"signal": placed.signal, "entity": reading.entity})
    for event in journal:
        if isinstance(event, Dispatched):
            if not isinstance(event.at, datetime) or event.at.utcoffset() is None:
                raise InvalidInputError("A Dispatched event's at must be a datetime with a timezone offset.",
                                        details={"attempt": repr(event.attempt)[:200]})
            if event.at > at:
                raise InvalidInputError(f"Attempt {event.attempt} was dispatched after the plan's time.",
                                        details={"attempt": event.attempt, "dispatched_at": event.at.isoformat(),
                                                 "at": at.isoformat()})
    return S.Evidence(
        _list(_event(event) for event in journal),
        _list(entity_term(reading) if isinstance(reading, EntityReading) else reading_term(reading)
              for reading in readings),
        _list(rows),
        microseconds(at),
    )


# The planner reads a caller's row in its own positions only (c-ev-pk-planner-row-positions-1018): the claim of
# (From CLAIM SOURCE), the row of (Withdrawn ROW REASON) and of a (Row ROW) reason, and the claim of a
# (Claim CLAIM) source or reason. Each statement claim there takes literal_term's spelling through
# procedures.statement_claim, so a row may name a statement as a library does (i-dd-statement-row-spelling-1018).
# Every other term stays as written, since justification's generic Statement arguments are arbitrary terms
# (a-integrate-statement-row-literals-1018), and the planner's row grammar refuses a row fitting no position.
# Nothing is evaluated: SNARS's codec reads each statement.
# Time: per row, one walk of its planner positions and statement_claim's parse per statement there.
# am[implements a-ev-pk-row-statement-positions-1018@9c3a50] am[rests-on c-ev-pk-planner-row-positions-1018@7d3b22]
def _planner_rows(rows: Sequence[Any], budget: RunBudget) -> list[Any]:
    S = _term()

    def claim(atom: Any, where: str) -> Any:
        read = statement_claim(atom, where, budget=budget)
        return atom if read is None else read

    def reference(atom: Any, where: str) -> Any:
        if _head(atom) == "Row" and len(atom.children) == 2:
            return S.Row(row(atom.children[1], where))
        if _head(atom) == "Claim" and len(atom.children) == 2:
            return S.Claim(claim(atom.children[1], where))
        return atom

    def row(atom: Any, where: str) -> Any:
        if _head(atom) == "From" and len(atom.children) == 3:
            return S.From(claim(atom.children[1], where), reference(atom.children[2], where))
        if _head(atom) == "Withdrawn" and len(atom.children) == 3:
            return S.Withdrawn(row(atom.children[1], where), reference(atom.children[2], where))
        return atom

    planner = []
    for index, atom in enumerate(rows):
        budget.remaining()
        planner.append(row(atom, f"rows[{index}]"))
    return planner


# am[implements a-ev-pk-python-api-1018@db9b94]
def _event(event: JournalEvent) -> Any:
    S = _term()
    if isinstance(event, Started):
        return S.Started(event.instance_id, event.procedure, event.journal)
    if isinstance(event, Dispatched):
        return S.Dispatched(event.instance_id, event.step, event.attempt, event.decision, microseconds(event.at))
    if isinstance(event, Receipt):
        return S.Receipt(event.receipt, event.instance_id, event.step, event.attempt, event.applied)
    if isinstance(event, Superseded):
        return S.Superseded(event.receipt, event.latest)
    if isinstance(event, Finished):
        return S.Finished(event.instance_id)
    raise InvalidInputError("A journal holds Started, Dispatched, Receipt, Superseded and Finished events.",
                            details={"event": repr(event)})


# am[implements a-ev-pk-commitment-cost-1018@c9673e]
def _track(track: Track) -> Any:
    return _term().Track(track.procedure, literal_term(track.literal), track.holds)


# The tracks the receipts establish (c-ev-fb-complete-record-1018, c-ev-fb-refusals-1018): feedback.metta
# picks each applied attempt's grades from the journal's events and the documents, assess_attempt grades
# each against one Achieves literal as the host wrote it, decided when its attempt was dispatched and closed
# at the next application on the literal's subject, and feedback.metta counts the attributed grades, which
# SNARS's track-record cut at the declared threshold turns into a track. Every call is charged to `budget`.
# Every document is first read through relevance's check_receipt, the one receipt check parse_receipt and the
# assessments use: it refuses a time that is no timezone-aware instant, then runs the receipt and observation
# fault tables, so nothing below compares or converts a time a receipt built in code could hold
# (a-ev-fb-check-before-cut-1018). A receipt issued after `at` is then refused before anything is graded: the
# journal holding its Receipt event is no snapshot at `at`, and since relevance refuses an application or
# observation after a receipt's issue, refusing by the issue instant leaves every application, observation,
# supersession and window the plan grades at or before `at` (c-ev-fb-issue-bounds-receipt-1018). Its Receipt,
# Superseded and Finished events carry no instant of their own, so excluding the receipt instead would leave
# them in the plan's state while its tracks described an earlier one (i-ev-fb-exclusion-splits-snapshot-1018).
# Time: per document, check_receipt's 1 + 4o fault rows for o observations; one feedback evaluation for the
# attempts; per grade, assess_attempt's receipt check and assessment; one evaluation for the counts; per count,
# one SNARS batch.
# am[implements a-ev-fb-request-receipts-1018@4c8f23] am[implements a-ev-fb-trials-1018@775554] am[implements a-ev-fb-promotion-1018@2ae86c]
# am[rests-on c-ev-fb-relevance-error-outside-request-1018@cfed5e] am[implements a-ev-fb-snapshot-refused-1018@f8ac61]
# am[rests-on c-ev-fb-issue-bounds-receipt-1018@4ca120] am[addresses i-ev-fb-future-receipts-count-1018@0846b9]
# am[implements a-ev-fb-check-before-cut-1018@059c44] am[implements a-integrate-feedback-validates-before-cut-1018@914488]
def _tracks(library: ProcedureLibrary, journal: Sequence[JournalEvent], receipts: Mapping[str, ReceiptDocument],
            events: Any, at: datetime, budget: RunBudget) -> tuple[Track, ...]:
    if not isinstance(receipts, Mapping) or not all(
            isinstance(key, str) and key and isinstance(value, ReceiptDocument) for key, value in receipts.items()):
        raise InvalidInputError("receipts must map each journal Receipt id to its parsed receipt-v2 document.")
    for rid, document in receipts.items():
        with _receipt_refused(rid, "is refused"):
            check_receipt(document, budget=budget)
        if document.issued_at > at:
            raise InvalidInputError(f"The receipt {rid} was issued after the plan's time.",
                                    details={"receipt": rid, "issued_at": document.issued_at.isoformat(),
                                             "at": at.isoformat()})
    if not receipts:
        return ()
    S = _term()
    documents = _list(
        S.Document(rid, document.attempt, document.action, document.review_fingerprint,
                   S.NotApplied if document.applied_at is None else S.At(microseconds(document.applied_at)),
                   microseconds(document.issued_at))
        for rid, document in receipts.items())
    answer = evaluate(PLANNING, "gc-pk-run-feedback-attempts", library_term(library), events, documents, budget=budget)
    assessed, complete = _parts(answer, "Attempts", 2)
    by_id = {event.receipt: event for event in journal if isinstance(event, Receipt)}
    decided = {(event.instance_id, event.step, event.attempt): event.at for event in journal if isinstance(event, Dispatched)}
    achieves = {procedure.name: procedure.achieves for procedure in library.procedures}
    trials = []
    for item in assessed.children:
        rid, name, k, until = item.children[1].value, item.children[2].value, item.children[3].value, item.children[4]
        receipt = by_id[rid]
        closes = None if _head(until) is None else receipts[until.children[1].value].applied_at
        with _receipt_refused(rid, "cannot grade its attempt"):
            graded = assess_attempt((("achieves", literal_text(achieves[name][k])),), receipts[rid],
                                    decided_at=decided[(receipt.instance_id, receipt.step, receipt.attempt)],
                                    budget=budget, next_attempt_at=closes)
        [prediction] = graded["predictions"]
        trials.append(S.Trial(name, k, prediction["status"], prediction["attribution"]))
    promotion = library.promotion
    counts = _parts(evaluate(PLANNING, "gc-pk-run-feedback-counts",
                             S.NoPromotion if promotion is None else S.Promotion(promotion.trials),
                             complete, _list(trials), budget=budget), "Counts", 1)[0]
    if not counts.children:
        return ()
    from ..snars_reasoner import track  # noqa: PLC0415 (SNARS is loaded only when a promotion counts)

    return tuple(
        Track(name, achieves[name][k], track(successes, failures, budget=budget, threshold=promotion.threshold).status == "Holds")
        for name, k, successes, failures in ((c.children[1].value, c.children[2].value, c.children[3].value, c.children[4].value)
                                             for c in counts.children))


# relevance's refusal of a receipt, check_receipt's or assess_attempt's, is relevance's error, which no request
# command reports, so it becomes an InvalidInputError naming the receipt and carrying relevance's own record
# (c-ev-fb-relevance-error-outside-request-1018): "The receipt R is refused: receipt.issued_at must be ...".
# am[implements a-ev-fb-check-before-cut-1018@059c44] am[rests-on c-ev-fb-relevance-error-outside-request-1018@cfed5e]
@contextmanager
def _receipt_refused(rid: str, what: str) -> Iterator[None]:
    try:
        yield
    except RelevanceError as error:
        raise InvalidInputError(f"The receipt {rid} {what}: {error.message}",
                                details={"receipt": rid, "relevance": error.to_dict()}) from error


# --- reading answers -------------------------------------------------------------------------------


# The parts of an answer headed HEAD with ARITY parts; a refusal raises PlanningRefused.
# am[implements a-ev-pk-python-api-1018@db9b94]
def _parts(answer: Any, head: str, arity: int) -> tuple[Any, ...]:
    problems = refused(answer)
    if problems is not None:
        raise PlanningRefused(problems)
    if _head(answer) != head or len(answer.children) != arity + 1:
        raise ProtocolError(f"The planner answered out of contract where {head} was due.", details={"answer": str(answer)})
    return tuple(answer.children[1:])


# am[implements a-ev-pk-python-api-1018@db9b94]
def _head(atom: Any) -> str | None:
    from metta import Expression  # noqa: PLC0415

    return str(atom.children[0]) if isinstance(atom, Expression) and atom.children else None


# A step's witness digest: SHA-256 over the planning group's identity, which covers every module's
# bytes, and the text of each compiled rule bearing the step's name in compile order, so any edit to
# the library, the section or the planner that changes what the step does changes the digest.
# am[implements a-ev-pk-python-api-1018@db9b94]
def _digest(identity: str, rules: list[str]) -> str:
    return "sha256:" + hashlib.sha256("\n".join([identity, *rules]).encode("utf-8")).hexdigest()


# am[implements a-ev-pk-python-api-1018@db9b94]
def _digests(rules: Sequence[Any], identity: str) -> dict[str, str]:
    named: dict[str, list[str]] = {}
    for rule in rules:
        named.setdefault(str(rule.children[1]), []).append(str(rule))
    return {name: _digest(identity, texts) for name, texts in named.items()}


# What reading one plan answer needs: the library for each step's kind, the digests by rule name, and
# the declared entities a binding may name.
# am[implements a-ev-pk-python-api-1018@db9b94]
@dataclass(frozen=True, slots=True)
class _Reading:
    library: ProcedureLibrary
    digests: dict[str, str]
    entities: frozenset[str]


# am[implements a-ev-pk-python-api-1018@db9b94]
def _answer(atom: Any, reading: _Reading) -> Answer:
    head = _head(atom)
    if head == "Plan" and len(atom.children) == 4:
        steps, cls, assumed = atom.children[1:]
        return Plan(_steps(steps.children, reading), str(cls.children[1]) == "established",
                    tuple(_literal(a.children[1], a.children[2].value) for a in assumed.children))
    if head == "Inquire" and len(atom.children) == 5:
        literal, investigator, yes, no = atom.children[1:]
        return Inquiry(_literal(literal, True), investigator.value,
                       _answer(yes.children[1], reading), _answer(no.children[1], reading))
    if head == "NoPlan" and len(atom.children) == 3:
        unsolved, alternative = atom.children[1:]
        return NoPlan(tuple(_unsolved(u) for u in unsolved.children),
                      _answer(alternative.children[1], reading) if _head(alternative) == "Alternative" else None)
    raise ProtocolError("The planner answered a plan out of contract.", details={"answer": str(atom)})


# Applications are numbered in plan order. A Start opens its procedure's application, and every later
# step of a planned instance belongs to the one its procedure has open, since Start is barred while an
# instance of the same procedure is open (c-ev-pk-open-instance-bar-1018); a step of an instance the
# journal started belongs to that instance's application, numbered when the plan first touches it.
# am[implements a-ev-pk-python-api-1018@db9b94] am[rests-on c-ev-pk-open-instance-bar-1018@6f0c91]
def _steps(took: Sequence[Any], reading: _Reading) -> tuple[PlanStep, ...]:
    steps: list[PlanStep] = []
    open_by_procedure: dict[str, int] = {}
    started: dict[str, int] = {}
    count = 0
    for item in took:
        name, instance, images = item.children[1:]
        procedure, part = name.children[2].value, name.children[3]
        step_id = part.value if _is_string(part) else None
        kind = _kind(procedure, step_id, str(part), reading.library)
        if kind is None:
            raise ProtocolError("The planner answered a step its library does not declare.", details={"step": str(item)})
        instance_id = instance.children[1].value if _head(instance) == "Inst" else None
        if kind in ("start", "derive"):
            application, count = count, count + 1
            if kind == "start":
                open_by_procedure[procedure] = application
        elif instance_id is not None:
            if instance_id not in started:
                started[instance_id], count = count, count + 1
            application = started[instance_id]
        elif procedure in open_by_procedure:
            application = open_by_procedure[procedure]
            if kind == "finish":
                del open_by_procedure[procedure]
        else:
            raise ProtocolError("The planner answered a step of an instance no Start opened.", details={"step": str(item)})
        pairs = tuple((str(bound.children[1]), str(bound.children[2])) for bound in images.children)
        steps.append(PlanStep(
            procedure=procedure, step=step_id, kind=kind, application=application, instance_id=instance_id,
            binding=_binding(pairs, reading.entities),
            witness=Witness(str(name), reading.digests[str(name)], pairs),
        ))
    return tuple(steps)


# am[implements a-ev-pk-python-api-1018@db9b94]
def _kind(procedure: str, step_id: str | None, part: str, library: ProcedureLibrary) -> StepKind | None:
    if step_id is None:
        return _KIND_OF_PART[part]
    declared = [s for p in library.procedures if p.name == procedure for s in p.steps if s.id == step_id]
    if not declared:
        return None
    return "act" if isinstance(declared[0], ActStep) else "investigate"


# The entities a binding may name: the domain section's declared entities.
# am[implements a-integrate-planner-step-consistency-1018@fc6d64]
def _entities(domain: Domain) -> frozenset[str]:
    return frozenset(entity.id for entity in domain.bigraph.entities) if domain.bigraph else frozenset()


# A step's binding: the witness's images that name a declared entity, in the witness's order.
# am[implements a-integrate-planner-step-consistency-1018@fc6d64]
def _binding(pairs: Sequence[Sequence[str]], entities: frozenset[str]) -> tuple[tuple[str, str], ...]:
    return tuple((node, image) for node, image in pairs if image in entities)


# am[implements a-ev-pk-python-api-1018@db9b94]
def _is_string(atom: Any) -> bool:
    from metta import Grounded  # noqa: PLC0415

    return isinstance(atom, Grounded) and isinstance(atom.value, str)


# A literal instance (Lit SUBJECT ENTITY VIA) with a value, as the procedure literal it judges; SUBJECT is
# in literal_term's spelling, (Signal "S"), (Statement "T") or (On (Signal "S") E).
# am[implements a-ev-pk-python-api-1018@db9b94] am[implements a-ev-bnd-qualified-literal-1019@8d05ed]
def _literal(lit: Any, value: bool) -> ProcedureLiteral:
    positive = _subject(lit.children[1])
    return positive if value else NegatedLiteral(positive)


# am[implements a-ev-pk-python-api-1018@db9b94] am[implements a-ev-bnd-qualified-literal-1019@8d05ed]
def _subject(subject: Any) -> SignalLiteral | StatementLiteral | QualifiedLiteral:
    kind = _head(subject)
    if kind == "On":
        return QualifiedLiteral(_subject(subject.children[1]), str(subject.children[2]))
    name = subject.children[1].value
    return SignalLiteral(name) if kind == "Signal" else StatementLiteral(name)


# One unmet read: a knowledge literal, or an executed step's progress on the executor's instance.
# am[implements a-ev-pk-python-api-1018@db9b94]
def _unmet(unmet: Any) -> ProcedureLiteral | Progress:
    lit, value = unmet.children[1], unmet.children[2].value
    if _head(lit.children[1]) == "Done":
        return Progress(lit.children[2].children[1].value, lit.children[1].children[1].value, value)
    return _literal(lit, value)


# am[implements a-ev-pk-python-api-1018@db9b94] am[implements a-ev-pc-c1-admission-1019@92a093]
def _unsolved(unsolved: Any) -> Unsolved:
    lit, value, reason = unsolved.children[1:]
    literal = _literal(lit, value.value)
    if _head(reason) == "Unknowable":
        return Unsolved(literal, "unknowable", tuple(_literal(unknown, True) for unknown in reason.children[1].children))
    return Unsolved(literal, {"NoWay": "no-way", "Contradicted": "contradicted"}.get(str(reason), "blocked"))


__all__ = [
    "Admitted",
    "Ambiguous",
    "Answer",
    "Blocked",
    "Dispatched",
    "Finished",
    "Inquiry",
    "JournalEvent",
    "NoPlan",
    "Plan",
    "PlanStep",
    "PlanningRefused",
    "Progress",
    "Receipt",
    "Stale",
    "Started",
    "Superseded",
    "Unsolved",
    "Verdict",
    "Witness",
    "admit",
    "plan",
]

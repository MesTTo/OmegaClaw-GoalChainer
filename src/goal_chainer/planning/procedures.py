"""Purpose: read a domain's procedures into typed literals, procedures and investigators, refused
unless the procedure policy accepts them against the domain's declared actions and signals and the
literals its bigraph section anchors, and write a library, a domain's names and its bigraph section
as the terms the planner reads.

A procedure is a way to bring about the literals it `Achieves`: it applies while its `When`
literals hold, and its steps act, investigate or achieve a literal in their `After` order. Its file
is the planner's, `planning/library/` with the domain's file stem, never in `domains/`, which lists
every file in it as a packaged domain (c-rel-domains-dir-lists-every-metta-1017). The file is data,
so a `!` in it is refused before pymetta reads it, and pymetta reads the rest into atoms without
evaluating anything. The procedure policy, `policy/goalchainer_procedure.metta`, decides which
library is acceptable, evaluated in the planner's module group under the caller's RunBudget; this
module validates shapes and transports values. An act step may end with `(Bind (RID ENTITY) ...)`:
which declared entity each redex node of its action's declared reaction must be, so the planner's
merged rule acts on the focal entity and never on another of its control. A literal of the domain's
bigraph section is read by this module's literal grammar too, so a section and a library spelling
one statement differently still name one literal.

A literal may also place a signal on one declared entity, `(On (Signal NAME) ENTITY)`: what a reading
binding's entity reading informs. Its anchors are never written by hand: the bigraph section term
anchors it at each entity a binding of NAME offers, and nowhere else.

A library may declare at most one `(gc-track-promotion (Trials N) (Threshold THETA))`: the rule under
which a procedure's record of bringing a literal about holds, read from receipts by
planning.feedback. With none, no record holds.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from ..domains.bigraph import Edge, Root
from ..domains.forms import FormsUnreadable, file_text, parsed_forms
from ..domains.model import Domain
from ..errors import InvalidInputError, ProtocolError
from ..runtime.budget import RunBudget
from ..runtime.evaluator import evaluate
from ..sexpr.codec import SexprCodec
from ..snars_program import parse_statement
from .group import PLANNING, refused

LIBRARY_DIRECTORY = "library"


# A machine-readable failure like every other layer's (goal_chainer.errors), keeping invalid_input's code.
# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
class ProcedureError(InvalidInputError):
    """A procedures file that cannot be read as its domain's procedures, or a planning input that
    does not fit them; the message names the file or the literal."""


# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
@dataclass(frozen=True, slots=True)
class SignalLiteral:
    """A signal the domain declares, judged from the review's effective reading of it."""

    name: str


# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
@dataclass(frozen=True, slots=True)
class StatementLiteral:
    """A SNARS statement, kept as the text SNARS's own codec emits for it, so two spellings of one
    tree are one literal."""

    text: str


# A signal placed on one declared entity, (On (Signal NAME) ENTITY), as a reading binding's entity
# reading informs it. It is its own anchored literal at ENTITY (c-bnd-literal-first-anchor-1019), never an
# instance of the bare signal at that entity, since the bare proposition's reading would then support it
# whatever entity the binding chose (c-bnd-bare-instance-breaks-separation-1019).
# am[implements a-ev-bnd-qualified-literal-1019@8d05ed] am[rests-on c-bnd-literal-first-anchor-1019@1ad5bb]
# am[rests-on c-bnd-bare-instance-breaks-separation-1019@435e9e]
@dataclass(frozen=True, slots=True)
class QualifiedLiteral:
    """A signal of the domain on one entity its bigraph section declares."""

    signal: SignalLiteral
    entity: str

    # The check is of types alone, as NegatedLiteral's is, since a signal's name is any string too: the
    # literal grammar and EntityReading admit only symbols, and planning.transport decodes a record
    # through this constructor from its field annotations.
    def __post_init__(self) -> None:
        if not isinstance(self.signal, SignalLiteral) or not isinstance(self.entity, str):
            raise TypeError("a qualified literal places a signal literal on an entity")


# Negation never nests: reading (Not (Not L)) folds it to L, and the constructor refuses to wrap a
# negation, so one literal has one representation.
# am[implements a-ev-pl-ag-representation-1017@ca0cfc] am[implements a-ev-bnd-qualified-literal-1019@8d05ed]
@dataclass(frozen=True, slots=True)
class NegatedLiteral:
    """The negation of a signal, statement or qualified literal."""

    literal: SignalLiteral | StatementLiteral | QualifiedLiteral

    def __post_init__(self) -> None:
        if not isinstance(self.literal, (SignalLiteral, StatementLiteral, QualifiedLiteral)):
            raise TypeError("a negation wraps a signal, statement or qualified literal, never another negation")


ProcedureLiteral = SignalLiteral | StatementLiteral | QualifiedLiteral | NegatedLiteral


# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
def negate(literal: ProcedureLiteral) -> ProcedureLiteral:
    """The literal's negation, folding a double negation away."""

    return literal.literal if isinstance(literal, NegatedLiteral) else NegatedLiteral(literal)


# A caller such as the CLI reads a goal literal written as a procedures file writes it, through the
# same reader and grammar the library and the domain's bigraph section are read by, so no second
# literal parser exists. Time: one scan and one pymetta parse of the text, plus one SNARS parse for a
# statement; under a request, the parse waits for the engine only until its budget's deadline, and
# None, outside any request, waits as long as it takes.
# am[implements a-ev-pk-python-api-1018@db9b94] am[implements a-ev-pl-ag-representation-1017@ca0cfc]
# am[rests-on c-rel-agrees-dr-pymetta-atoms-1018@552f9f]
# am[implements a-integrate-runtime-wait-deadline-1018@a74406]
# am[implements a-rt-parse-budget-required-1018@f73dbd]
def read_literal(text: str, source: str, *, budget: RunBudget | None) -> ProcedureLiteral:
    """The one literal `text` writes, (Signal NAME), (Statement SNARS-STATEMENT), (On (Signal NAME)
    ENTITY) or (Not L); `source` names it in every error."""

    try:
        parsed = parsed_forms(text, budget=budget)
    except FormsUnreadable as error:
        raise ProcedureError(f"{source}: {error.problem}") from error
    if len(parsed) != 1:
        raise ProcedureError(f"{source}: a literal is one form, (Signal NAME), (Statement SNARS-STATEMENT), "
                             f"(On (Signal NAME) ENTITY) or (Not L)")
    return _Reader(source, SexprCodec()).literal(_plain(parsed[0][1]))


# The inverse of read_literal: a signal by its name as a symbol, a statement by the SNARS text it
# keeps, which SNARS's codec emitted, a qualified literal's entity as a symbol, so
# read_literal(literal_text(L)) == L for every literal read_literal or a library read, whose signal names
# and entities are symbols.
# am[implements a-ev-pk-python-api-1018@db9b94] am[implements a-ev-bnd-qualified-literal-1019@8d05ed]
def literal_text(literal: ProcedureLiteral) -> str:
    """The literal as a procedures file writes it."""

    if isinstance(literal, SignalLiteral):
        return f"(Signal {literal.name})"
    if isinstance(literal, StatementLiteral):
        return f"(Statement {literal.text})"
    if isinstance(literal, QualifiedLiteral):
        return f"(On {literal_text(literal.signal)} {literal.entity})"
    return f"(Not {literal_text(literal.literal)})"


# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
@dataclass(frozen=True, slots=True)
class ActStep:
    """Apply one of the domain's actions; `binds` pairs each bound redex node of the action's
    declared reaction with the declared entity it must be."""

    id: str
    action: str
    after: tuple[str, ...]
    binds: tuple[tuple[str, str], ...] = ()


# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
@dataclass(frozen=True, slots=True)
class InvestigateStep:
    """Gather evidence about a literal; completing it makes nothing true."""

    id: str
    literal: ProcedureLiteral
    after: tuple[str, ...]


# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
@dataclass(frozen=True, slots=True)
class AchieveStep:
    """Bring a literal about: nothing to do if it holds, otherwise a way that makes it hold."""

    id: str
    literal: ProcedureLiteral
    after: tuple[str, ...]


ProcedureStep = ActStep | InvestigateStep | AchieveStep


# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
@dataclass(frozen=True, slots=True)
class Procedure:
    """A way to bring about `achieves`, applicable while `when` holds, done by `steps`."""

    name: str
    achieves: tuple[ProcedureLiteral, ...]
    when: tuple[ProcedureLiteral, ...]
    steps: tuple[ProcedureStep, ...]


# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
@dataclass(frozen=True, slots=True)
class Investigator:
    """A host capability that can observe each literal it lists."""

    name: str
    observes: tuple[ProcedureLiteral, ...]


# A library's predeclared promotion rule (grg-v3 section 16.7: predeclared thresholds in a versioned
# policy, the library's gc-procedures version): a procedure's record of bringing a literal about holds
# once at least `trials` of its trials are attributed, with SNARS's track-record condition holding at
# `threshold`. Trials counts receipts, so 5.0 or True is no count, and a threshold is a probability.
# am[implements a-ev-fb-promotion-1018@2ae86c] am[rests-on c-ev-fb-promotion-in-library-1018@943bd4]
@dataclass(frozen=True, slots=True)
class Promotion:
    """At least `trials` attributed trials, and SNARS's condition at `threshold`, in (0, 1]."""

    trials: int
    threshold: float

    def __post_init__(self) -> None:
        if type(self.trials) is not int or self.trials < 1:
            raise ValueError(f"Trials must be a positive integer, not {self.trials!r}")
        if type(self.threshold) not in (int, float) or not math.isfinite(self.threshold) or not 0 < self.threshold <= 1:
            raise ValueError(f"Threshold must be a finite number in (0, 1], not {self.threshold!r}")


# am[implements a-ev-pl-ag-representation-1017@ca0cfc] am[implements a-ev-fb-promotion-1018@2ae86c]
@dataclass(frozen=True, slots=True)
class ProcedureLibrary:
    """One domain's procedures and investigators, in the order the file declares them."""

    policy_version: str
    source: str
    digest: str
    procedures: tuple[Procedure, ...]
    investigators: tuple[Investigator, ...]
    promotion: Promotion | None = None

    def achieving(self, literal: ProcedureLiteral) -> tuple[Procedure, ...]:
        """The procedures that predict `literal`, in declared order."""

        return tuple(procedure for procedure in self.procedures if literal in procedure.achieves)

    def investigators_of(self, literal: ProcedureLiteral) -> tuple[Investigator, ...]:
        """The investigators that can observe `literal`, in declared order."""

        return tuple(investigator for investigator in self.investigators if literal in investigator.observes)


# am[implements a-ev-pl-ag-procedures-file-1017@70f843] am[rests-on c-rel-domains-dir-lists-every-metta-1017@1863f6]
def packaged_procedures(domain: Domain, *, budget: RunBudget) -> ProcedureLibrary:
    """The procedures shipped for a packaged domain, from planning/library/<its file stem>.metta."""

    stem = Path(domain.source).stem
    entry = resources.files("goal_chainer.planning") / LIBRARY_DIRECTORY / f"{stem}.metta"
    if not entry.is_file():
        raise ProcedureError(f"no procedures are packaged for the domain {stem}")
    return read_procedures(
        entry.read_text(encoding="utf-8"), f"goal_chainer/planning/{LIBRARY_DIRECTORY}/{stem}.metta", domain,
        budget=budget,
    )


# A caller's file is read like every declaration file, by domains.forms.file_text, which resolves the
# path itself, so a path that is unusable, missing, a directory, unreadable or not UTF-8 is refused as
# a ProcedureError naming it and the cause, in the domain loader's wording, never a path, decoding or
# OS error (c-integrate-request-input-leaks-762662a-1018, c-integrate-path-normalization-leaks-1018).
# am[implements a-ev-pl-ag-representation-1017@ca0cfc] am[implements a-integrate-planner-input-failures-1018@b84418]
# am[related a-rel-file-text-one-home-1018@f5dd20]
def load_procedures(path: str | Path, domain: Domain, *, budget: RunBudget) -> ProcedureLibrary:
    """Read a procedures file for `domain`, or raise ProcedureError saying what is wrong with it."""

    source, text = file_text(path, ProcedureError)
    return read_procedures(text, str(source), domain, budget=budget)


# A procedures file is data, read like every declaration file by domains.forms.parsed_forms, which
# refuses a directive or any text outside a form before pymetta parses each form without evaluating
# it, since pymetta alone would read !(f) back as a plain (f) (c-ev-pl-pymetta-parses-1017). Shapes
# are this module's; acceptability is the policy's.
# Time: one scan of the text + one pymetta parse per form + one policy call over the library, charged
# to `budget`.
# am[implements a-ev-pl-ag-representation-1017@ca0cfc] am[rests-on c-ev-pl-pymetta-parses-1017@02664c]
# am[rests-on c-rel-agrees-dr-pymetta-atoms-1018@552f9f]
def read_procedures(text: str, source: str, domain: Domain, *, budget: RunBudget) -> ProcedureLibrary:
    """Parse and validate procedures text for `domain`; `source` names it in every error."""

    try:
        atoms = [atom for _, atom in parsed_forms(text, budget=budget)]
    except FormsUnreadable as error:
        line = text.count("\n", 0, error.index) + 1
        raise ProcedureError(f"{source}:{line}: {error.problem}") from error

    reader = _Reader(source, SexprCodec())
    versions: list[str] = []
    procedures: list[Procedure] = []
    investigators: list[Investigator] = []
    promotions: list[Promotion] = []
    for atom in atoms:
        form = _plain(atom)
        head = form[0] if isinstance(form, tuple) and form else None
        if head == "gc-procedures":
            versions.append(reader.name(form, 1, "(gc-procedures POLICY-VERSION)", length=2))
        elif head == "gc-procedure":
            procedures.append(reader.procedure(form))
        elif head == "gc-investigator":
            investigators.append(reader.investigator(form))
        elif head == "gc-track-promotion":
            promotions.append(reader.promotion(form))
        else:
            raise ProcedureError(
                f"{source}: {reader.render(form)} is not gc-procedures, gc-procedure, gc-investigator or gc-track-promotion"
            )
    if len(versions) != 1:
        raise ProcedureError(f"{source}: name the policy version once, as (gc-procedures VERSION); found {len(versions)}")
    if len(promotions) > 1:
        raise ProcedureError(f"{source}: declare the track promotion at most once, as "
                             f"(gc-track-promotion (Trials N) (Threshold THETA)); found {len(promotions)}")
    if versions[0] != domain.policy_version:
        raise ProcedureError(
            f"{source}: written for policy version {versions[0]}, but the domain is {domain.policy_version}"
        )
    library = ProcedureLibrary(
        policy_version=versions[0],
        source=source,
        digest="sha256:" + hashlib.sha256(
            "\n".join(reader.render(_plain(atom)) for atom in atoms).encode("utf-8")
        ).hexdigest(),
        procedures=tuple(procedures),
        investigators=tuple(investigators),
        promotion=promotions[0] if promotions else None,
    )
    _accept(library, domain, budget=budget)
    return library


# The policy finds every problem at once, so one refusal names them all. A domain without a bigraph
# section anchors nothing, so every literal of its library is refused: the planner could judge none.
# am[implements a-ev-pl-ag-representation-1017@ca0cfc] am[implements a-ev-pk-acceptance-anchors-1018@cb1e61]
def _accept(library: ProcedureLibrary, domain: Domain, *, budget: RunBudget) -> None:
    answer = evaluate(PLANNING, "gc-procedures-run-check", library_term(library), names_term(domain),
                      section_term(domain), budget=budget)
    problems = refused(answer)
    if problems is not None:
        raise ProcedureError(f"{library.source}: {'; '.join(problems)}", details={"problems": problems})
    if str(answer) != "Accepted":
        raise ProtocolError("The procedure policy answered out of contract.", details={"answer": str(answer)})


# --- typed records as policy terms ---------------------------------------------------------------


# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
def _S() -> Any:
    from metta import S  # noqa: PLC0415

    return S


# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
def _list(values: Iterable[Any]) -> Any:
    from metta import Expression  # noqa: PLC0415

    return Expression(tuple(values))


# A caller's statement claim as the planner reads it: (Statement TREE), as a library writes it, or (Statement
# "TEXT"), as literal_term writes it, either negated, read by this module's grammar into literal_term's
# spelling, so it names the literal a library's statement does, as section_term reads a section's anchors
# (c-ev-pk-section-anchors-read-by-grammar-1018). Any other atom answers None; a statement SNARS cannot parse
# is a ProcedureError naming `source`.
# Time: one SNARS parse, and for TEXT one pymetta parse under `budget`.
# am[implements a-ev-pk-row-statement-positions-1018@9c3a50] am[rests-on c-ev-pk-section-anchors-read-by-grammar-1018@8764d2]
def statement_claim(atom: Any, source: str, *, budget: RunBudget) -> Any | None:
    """The planner's spelling of the statement claim `atom` states, or None when it states none."""

    form = _plain(atom)
    negated = isinstance(form, tuple) and len(form) == 2 and form[0] == "Not"
    claim = form[1] if negated else form
    if not (isinstance(claim, tuple) and len(claim) == 2 and claim[0] == "Statement"):
        return None
    if isinstance(claim[1], list):
        literal = read_literal(f"(Statement {claim[1][0]})", source, budget=budget)
    else:
        literal = _Reader(source, SexprCodec()).literal(claim)
    return literal_term(negate(literal) if negated else literal)


# A qualified literal is (On (Signal "NAME") ENTITY), its entity a symbol, as the bigraph section term writes
# an anchor's entity and reading_projection.entity_term an entity reading's, so the claim an entity reading's
# row makes is the subject its derived anchor names.
# am[implements a-ev-pl-ag-representation-1017@ca0cfc] am[implements a-ev-bnd-qualified-literal-1019@8d05ed]
# am[rests-on c-bnd-reader-interface-cecce9b-1019@a60c62]
def literal_term(literal: ProcedureLiteral) -> Any:
    """A literal as the policy reads it: names stay strings, so none is ever evaluated."""

    from metta import Symbol  # noqa: PLC0415

    S = _S()
    if isinstance(literal, SignalLiteral):
        return S.Signal(literal.name)
    if isinstance(literal, StatementLiteral):
        return S.Statement(literal.text)
    if isinstance(literal, QualifiedLiteral):
        return S.On(literal_term(literal.signal), Symbol(literal.entity))
    return S.Not(literal_term(literal.literal))


# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
def _step_term(step: ProcedureStep) -> Any:
    S = _S()
    after = _list(step.after)
    if isinstance(step, ActStep):
        from metta import Symbol  # noqa: PLC0415

        return S.Act(step.id, step.action, after,
                     S.Binds(*(S.Bound(Symbol(rid), Symbol(entity)) for rid, entity in step.binds)))
    if isinstance(step, InvestigateStep):
        return S.Investigate(step.id, literal_term(step.literal), after)
    return S.Achieve(step.id, literal_term(step.literal), after)


# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
def library_term(library: ProcedureLibrary) -> Any:
    """The library as (Library (PROCEDURE ...) (INVESTIGATOR ...)), the policy's reading."""

    S = _S()
    return S.Library(
        _list(
            S.Procedure(
                procedure.name,
                _list(literal_term(literal) for literal in procedure.achieves),
                _list(literal_term(literal) for literal in procedure.when),
                _list(_step_term(step) for step in procedure.steps),
            )
            for procedure in library.procedures
        ),
        _list(
            S.Investigator(investigator.name, _list(literal_term(literal) for literal in investigator.observes))
            for investigator in library.investigators
        ),
    )


# am[implements a-ev-pk-acceptance-anchors-1018@cb1e61]
def names_term(domain: Domain) -> Any:
    """The domain's declared names as the policy reads them, (Names (Actions (A ...)) (Signals (S ...)))."""

    S = _S()
    return S.Names(S.Actions(_list(domain.action_ids)), S.Signals(_list(domain.signal_ids)))


# Names stay symbols as the file wrote them, since the kernel and its rules name nodes and links by
# symbol; an action is a string like the library's acts, which compile.metta matches by equality; and a
# literal takes the library's spelling through this module's grammar, so the two compare by equality.
# A reaction's terms reach the kernel as written but for a node whose control is a literal: the planner
# reads that control too, written either way a section writes one, so a reaction reads or writes the
# very term its anchor declares, and refuses a literal no anchor declares, which it could never read.
# Each binding of the domain's reading declaration anchors (On (Signal S) E) at each entity E it offers,
# with no Via, so a procedure may name the signal on that entity and nowhere else
# (c-bnd-literal-first-anchor-1019); the section's own checks refuse an anchor of any literal but a signal
# or a statement, as (Literal TEXT), so these anchors have no second home. None, a domain declaring no
# section and so no binding, is the empty section.
# Time: linear in the section's forms and in its reactions' atoms, plus one SNARS parse per statement and
# one anchor per entity each binding offers.
# am[implements a-ev-pk-python-api-1018@db9b94] am[implements a-rel-brs-section-1018@b63f59]
# am[implements a-ev-pk-reaction-literals-read-1018@23bd20] am[addresses i-ev-pk-reaction-literal-spelling-1018@7cbbbf]
# am[implements a-ev-pk-reaction-literals-anchored-1018@d38431] am[addresses i-ev-brs-reaction-literal-unanchored-1018@2da49c]
# am[implements a-ev-bnd-qualified-anchors-1019@4da23d] am[rests-on c-bnd-literal-first-anchor-1019@1ad5bb]
def section_term(domain: Domain) -> Any:
    """The domain's bigraph section as the planner reads it, (Section FORM ...), with an anchor for
    each entity each reading binding offers."""

    from metta import Symbol  # noqa: PLC0415

    S = _S()
    section, source = domain.bigraph, domain.source
    if section is None:
        return S.Section()

    def form(head: str, *parts: Any) -> Any:
        return getattr(S, head)(*parts)

    reader = _Reader(source, SexprCodec())
    rows: list[Any] = []
    anchored: set[ProcedureLiteral] = set()
    rows.extend(form("gc-brs-control", Symbol(control.name), S.Ports(*map(Symbol, control.ports)), Symbol(control.kind))
                for control in section.controls)
    rows.extend(form("gc-brs-entity", Symbol(entity.id), Symbol(entity.control)) for entity in section.entities)
    rows.extend(form("gc-brs-in", Symbol(placement.entity),
                     S.Root(placement.parent.index) if isinstance(placement.parent, Root) else Symbol(placement.parent))
                for placement in section.placements)
    rows.extend(form("gc-brs-link", Symbol(link.entity), Symbol(link.port),
                     (S.Edge if isinstance(link.link, Edge) else S.Name)(Symbol(link.link.name)))
                for link in section.links)
    for anchor in section.anchors:
        literal = reader.literal(_plain(anchor.literal))
        if isinstance(literal, NegatedLiteral):
            raise ProcedureError(f"{source}: a bigraph section anchors a signal or a statement, not the negation "
                                 f"{reader.render(_plain(anchor.literal))}")
        anchored.add(literal)
        rows.append(form("gc-brs-literal", literal_term(literal), S.On(Symbol(anchor.entity)), S.Via(*map(Symbol, anchor.via))))
    for binding in domain.readings.bindings if domain.readings is not None else ():
        for entity, _ in binding.entities:
            qualified = QualifiedLiteral(SignalLiteral(binding.signal), entity)
            anchored.add(qualified)
            rows.append(form("gc-brs-literal", literal_term(qualified), S.On(Symbol(entity)), S.Via()))
    for reaction in section.reactions:
        def read(term: Any, action: str = reaction.action) -> Any:
            return _read_terms(term, reader, action, frozenset(anchored))

        rows.append(form("gc-brs-reaction", reaction.action, S.Redex(read(reaction.redex)), S.Reactum(read(reaction.reactum)),
                         reaction.eta, read(reaction.conditions)))
    return S.Section(*rows)


# The heads of a literal as this module's grammar reads it.
# am[implements a-ev-pk-reaction-literals-read-1018@23bd20] am[implements a-ev-bnd-qualified-literal-1019@8d05ed]
_LITERAL_HEADS = frozenset({"Signal", "Statement", "On", "Not"})


# A term with each (N ID CONTROL) row of every Nodes section, at any depth, holding a literal control
# (Signal NAME), (Statement TREE) or (Not L) read by _Reader.control into literal_term's spelling, which
# must be an anchored literal or its witness; every other atom is kept. A condition's pattern is a
# (Bigraph ...) term too, so it is read the same way.
# am[implements a-ev-pk-reaction-literals-read-1018@23bd20] am[addresses i-ev-pk-reaction-literal-spelling-1018@7cbbbf]
# am[implements a-ev-pk-reaction-literals-anchored-1018@d38431] am[addresses i-ev-brs-reaction-literal-unanchored-1018@2da49c]
def _read_terms(atom: Any, reader: _Reader, action: str, anchored: frozenset[ProcedureLiteral]) -> Any:
    from metta import Expression  # noqa: PLC0415

    if not isinstance(atom, Expression) or not atom.children:
        return atom
    head, *rest = atom.children
    if str(head) != "Nodes":
        return Expression((head, *(_read_terms(child, reader, action, anchored) for child in rest)))
    rows = []
    for row in rest:
        parts = row.children if isinstance(row, Expression) else ()
        control = parts[2] if len(parts) == 3 else None
        if not (isinstance(control, Expression) and control.children and str(control.children[0]) in _LITERAL_HEADS):
            rows.append(row)
            continue
        literal = reader.control(_plain(control))
        if (literal.literal if isinstance(literal, NegatedLiteral) else literal) not in anchored:
            raise ProcedureError(f"{reader.source}: the reaction of {action} has a node of {reader.render(_plain(control))}, "
                                 "a literal no gc-brs-literal anchors, so the planner could never read it")
        rows.append(Expression((*parts[:2], literal_term(literal))))
    return Expression((head, *rows))


# --- reading forms -------------------------------------------------------------------------------


# am[implements a-ev-pl-ag-representation-1017@ca0cfc]
def _plain(atom: Any) -> Any:
    """A pymetta atom as nested tuples: a symbol as its name, a string as a one-element list."""

    from metta import Expression, Grounded  # noqa: PLC0415

    if isinstance(atom, Expression):
        return tuple(_plain(child) for child in atom.children)
    if isinstance(atom, Grounded):
        value = atom.value
        return [value] if isinstance(value, str) else value
    return str(atom)


@dataclass(frozen=True, slots=True)
class _Reader:
    source: str
    codec: SexprCodec

    # am[implements a-ev-pl-ag-representation-1017@ca0cfc]
    def render(self, form: Any) -> str:
        if isinstance(form, tuple):
            return "(" + " ".join(self.render(item) for item in form) + ")"
        if isinstance(form, list):
            return '"' + str(form[0]).replace("\\", "\\\\").replace('"', '\\"') + '"'
        return str(form)

    # am[implements a-ev-pl-ag-representation-1017@ca0cfc]
    def fail(self, form: Any, expected: str) -> ProcedureError:
        return ProcedureError(f"{self.source}: {self.render(form)} should be {expected}")

    # am[implements a-ev-pl-ag-representation-1017@ca0cfc]
    def name(self, form: Any, index: int, expected: str, *, length: int | None = None) -> str:
        if not isinstance(form, tuple) or (length is not None and len(form) != length) or len(form) <= index:
            raise self.fail(form, expected)
        value = form[index]
        if not isinstance(value, str):
            raise self.fail(form, expected)
        return value

    # am[implements a-ev-pl-ag-representation-1017@ca0cfc]
    def section(self, form: Any, head: str, expected: str) -> tuple[Any, ...]:
        if not (isinstance(form, tuple) and form and form[0] == head):
            raise self.fail(form, expected)
        return form[1:]

    # am[implements a-ev-pl-ag-representation-1017@ca0cfc]
    def procedure(self, form: Any) -> Procedure:
        shape = "(gc-procedure NAME (Achieves L ...) (When L ...) (Steps STEP ...))"
        if not (isinstance(form, tuple) and len(form) == 5):
            raise self.fail(form, shape)
        name = self.name(form, 1, shape)
        return Procedure(
            name=name,
            achieves=tuple(self.literal(item) for item in self.section(form[2], "Achieves", shape)),
            when=tuple(self.literal(item) for item in self.section(form[3], "When", shape)),
            steps=tuple(self.step(item) for item in self.section(form[4], "Steps", shape)),
        )

    # am[implements a-ev-pl-ag-representation-1017@ca0cfc]
    def step(self, form: Any) -> ProcedureStep:
        shape = ("(Step ID act ACTION (After ID ...) [(Bind (RID ENTITY) ...)]), (Step ID investigate L (After ...))"
                 " or (Step ID achieve L (After ...))")
        if not (isinstance(form, tuple) and len(form) in (5, 6) and form[0] == "Step"):
            raise self.fail(form, shape)
        step_id = self.name(form, 1, shape)
        after_form = form[4]
        after = self.section(after_form, "After", shape)
        if not all(isinstance(item, str) for item in after):
            raise self.fail(after_form, "(After ID ...)")
        kind, target = form[2], form[3]
        if len(form) == 6 and kind != "act":
            raise self.fail(form, shape)
        if kind == "act":
            if not isinstance(target, str):
                raise self.fail(form, shape)
            binds = self.section(form[5], "Bind", shape) if len(form) == 6 else ()
            if not all(isinstance(b, tuple) and len(b) == 2 and all(isinstance(x, str) for x in b) for b in binds):
                raise self.fail(form[5], "(Bind (RID ENTITY) ...)")
            return ActStep(step_id, target, tuple(after), tuple((rid, entity) for rid, entity in binds))
        if kind == "investigate":
            return InvestigateStep(step_id, self.literal(target), tuple(after))
        if kind == "achieve":
            return AchieveStep(step_id, self.literal(target), tuple(after))
        raise self.fail(form, shape)

    # am[implements a-ev-pl-ag-representation-1017@ca0cfc]
    def investigator(self, form: Any) -> Investigator:
        shape = "(gc-investigator NAME L ...)"
        if not (isinstance(form, tuple) and len(form) >= 2):
            raise self.fail(form, shape)
        return Investigator(self.name(form, 1, shape), tuple(self.literal(item) for item in form[2:]))

    # (gc-track-promotion (Trials N) (Threshold THETA)), its numbers as pymetta read them, so 5.0 stays a
    # float and is refused as a count.
    # am[implements a-ev-fb-promotion-1018@2ae86c] am[rests-on c-ev-fb-promotion-in-library-1018@943bd4]
    def promotion(self, form: Any) -> Promotion:
        shape = "(gc-track-promotion (Trials N) (Threshold THETA))"
        if not (isinstance(form, tuple) and len(form) == 3
                and all(isinstance(part, tuple) and len(part) == 2 for part in form[1:])
                and (form[1][0], form[2][0]) == ("Trials", "Threshold")):
            raise self.fail(form, shape)
        try:
            return Promotion(form[1][1], form[2][1])
        except ValueError as error:
            raise ProcedureError(f"{self.source}: {self.render(form)}: {error}") from error

    # The literal grammar a library and a section's anchors are written in.
    # am[implements a-ev-pl-ag-representation-1017@ca0cfc] am[implements a-ev-bnd-qualified-literal-1019@8d05ed]
    def literal(self, form: Any) -> ProcedureLiteral:
        shape = "(Signal NAME), (Statement SNARS-STATEMENT), (On (Signal NAME) ENTITY) or (Not L)"
        if isinstance(form, tuple) and len(form) == 3 and form[0] == "On":
            signal = self.literal(form[1])
            if not (isinstance(signal, SignalLiteral) and isinstance(form[2], str)):
                raise self.fail(form, "(On (Signal NAME) ENTITY)")
            return QualifiedLiteral(signal, form[2])
        if not (isinstance(form, tuple) and len(form) == 2):
            raise self.fail(form, shape)
        head, value = form
        if head == "Signal" and isinstance(value, str):
            return SignalLiteral(value)
        if head == "Statement" and isinstance(value, tuple):
            # SNARS's own codec validates the tree and emits its one spelling of it.
            try:
                atom = parse_statement(self.render(value))
            except InvalidInputError as error:
                raise ProcedureError(f"{self.source}: {self.render(form)} is not a SNARS statement: {error}") from error
            return StatementLiteral(self.codec.emit(atom))
        if head == "Not":
            return negate(self.literal(value))
        raise self.fail(form, shape)

    # A literal in a reaction's terms, which a section writes either in this grammar or in literal_term's
    # own spelling, its signal name or statement text a string, a qualified literal's entity a symbol in
    # both; both read to one literal.
    # am[implements a-ev-pk-reaction-literals-read-1018@23bd20] am[implements a-ev-bnd-qualified-literal-1019@8d05ed]
    def control(self, form: Any) -> ProcedureLiteral:
        if isinstance(form, tuple) and len(form) == 3 and form[0] == "On":
            signal = self.control(form[1])
            if not (isinstance(signal, SignalLiteral) and isinstance(form[2], str)):
                raise self.fail(form, "(On (Signal NAME) ENTITY)")
            return QualifiedLiteral(signal, form[2])
        if isinstance(form, tuple) and len(form) == 2:
            head, value = form
            if head == "Not":
                return negate(self.control(value))
            text = value[0] if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str) else None
            if head == "Signal" and text is not None:
                return SignalLiteral(text)
            if head == "Statement" and text is not None:
                try:
                    atom = parse_statement(text)
                except InvalidInputError as error:
                    raise ProcedureError(f"{self.source}: {self.render(form)} is not a SNARS statement: {error}") from error
                return StatementLiteral(self.codec.emit(atom))
        return self.literal(form)


__all__ = [
    "AchieveStep",
    "ActStep",
    "InvestigateStep",
    "Investigator",
    "NegatedLiteral",
    "Procedure",
    "ProcedureError",
    "ProcedureLibrary",
    "ProcedureLiteral",
    "Promotion",
    "ProcedureStep",
    "QualifiedLiteral",
    "SignalLiteral",
    "StatementLiteral",
    "library_term",
    "literal_text",
    "literal_term",
    "load_procedures",
    "names_term",
    "negate",
    "packaged_procedures",
    "read_literal",
    "read_procedures",
    "section_term",
]

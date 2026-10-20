"""Purpose: read a domain's reading section into one validated, data-only ReadingDeclaration, and
write a declaration back as that section's forms: the propositions Jev judges in a text, the answer
options and the evidence direction each gives, the choices, the bindings, and the model, language
and instructions every question is asked under. A declaration is identified by the SHA-256 of its
content, the entities and descriptions its bindings offer included, and admits a reading fact only
when the fact's proposition and answer are ones it declares; answer the section's facts, which the
domain loader's validation runner checks against the section's fault tables in readings.metta; and
give each binding the entities the domain's bigraph section declares under its control.

The section is these forms, whose heads are HEADS. The domain loader hands read_section the forms of
a domain file with these heads, and forms() writes a declaration as them, which read_section reads
back as the same declaration, its bindings without the entities they offer:

    (gc-reading-domain NAME)                              once: the domain the readings belong to
    (gc-reading-model "jev-1.13.0")                       once: the pinned Jev model
    (gc-reading-language "en")                            once: the language the statements use
    (gc-reading-instructions "...")                       once: put before every statement
    (gc-reading-option NAME DIRECTION "description")      one or more, one at least for or against;
                                                          DIRECTION is for, against or none
    (gc-reading-proposition ID "statement" "question")    any number, with the choices one at least
    (gc-reading-choice ID "instructions" ((OPTION "description") ...))    any number, one option or more
    (gc-reading-binding SIGNAL CONTROL "instructions" "no-match description")    any number: which
                                                          entity declared under the bigraph control
                                                          CONTROL the proposition SIGNAL is about
    (gc-ranking-instruction "...")                        once: the cross-encoder's instruction

Nothing here names a domain's propositions, answers or choices. What a decided answer means comes
from its option's direction alone: `for` is evidence for the proposition, `against` evidence against
it, and `none`, the text leaving it unsettled, is no evidence either way.

A binding is one Jev Choice over every entity the domain's bigraph section declares under its
control, each offered by its description, and one more option, NO_MATCH, for a text that places the
proposition on none of them. The domain loader gives a binding its entities, with with_entities,
once the domain's checks pass, so a declaration the loader answers has every binding's entities and
the digest covers each entity and its description; read_section alone answers a binding with none.

read_section reads each form's shape and each singleton's count, and a ReadingDeclaration refuses any
value that is not well formed. What the values must satisfy together, such as distinct answer names
or at least one answer giving evidence, is checked by the section's fault tables (CHECKS, through the
typed entry ENTRY) over the facts FACTS answers, which the domain loader runs with every other check
of the domain, so a domain file's faults are reported at once.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path, PosixPath, PurePosixPath, PureWindowsPath, WindowsPath
from typing import Any, Protocol, TypeGuard, TypeVar

from ..errors import InvalidInputError, safe_repr
from ..sexpr.codec import SexprCodec
from ..sexpr.forms import TopLevelForm

DIRECTIONS = ("for", "against", "none")

# How a domain theory reads a decided answer, by its direction: (supported ID) for `for` and
# (contradicted ID) for `against`. A `none` answer asserts nothing, because silence is not
# refutation (c-orch-three-way-semantics-1016).
# am[implements a-dr-direction-words-1018@1b6ec6]
JUDGEMENTS = {"for": "supported", "against": "contradicted"}

# The option a binding offers beside its entities: the text places the proposition on none of them.
# Entity linking answers a mention with no matching entity as its own NIL outcome, not as a low score
# on some entity, so the Choice can say so; the name holds a space, so no entity symbol equals it.
# am[implements a-bnd-question-1019@b2f0b9] am[rests-on c-bnd-nil-is-its-own-outcome-1019@babf3c]
NO_MATCH = "no match"

# A reading id or answer name is written into gc-reading facts as a bare symbol, so it must read back
# as that symbol in every reader of those facts: no space, parenthesis, quote or comment character,
# not a MeTTa variable, and not a number, which a reader would parse as one. It is a plain str, never
# a subclass, whose own methods could read or write it otherwise.
# am[implements a-dr-one-name-1018@beba5e] am[implements a-integrate-binding-declaration-refusal-repair-1019@59efc5]
_SYMBOL = re.compile(r'[^\s()";]+')

_SINGLE = {
    "gc-reading-domain": "symbol",
    "gc-reading-model": "string",
    "gc-reading-language": "string",
    "gc-reading-instructions": "string",
    "gc-ranking-instruction": "string",
}
_REPEATED = ("gc-reading-option", "gc-reading-proposition", "gc-reading-choice", "gc-reading-binding")
# The heads of the reading section's forms, which the domain loader hands read_section.
# am[implements a-dr-readings-move-1018@8f7d09]
HEADS = frozenset((*_SINGLE, *_REPEATED))
# The section's fault tables, their typed entry and their warm-up, which the domain loader's
# validation runner loads into its domain-checks module group: it warms the tables once per process
# and calls the entry with the domain's facts.
# am[implements a-dr-dt-module-1018@8da5f7] am[implements a-rel-nd-section-warm-ups-1018@df1a66]
CHECKS = Path(__file__).resolve().with_name("readings.metta")
ENTRY = "gc-rd-run-faults"
WARM_UP = "gc-rd-checks-warm-up"


# am[implements a-dr-one-name-1018@beba5e] am[implements a-integrate-binding-declaration-refusal-repair-1019@59efc5]
def is_reading_symbol(text: object) -> TypeGuard[str]:
    """Whether text can stand as a proposition id or an answer in a gc-reading fact."""

    if type(text) is not str or not _SYMBOL.fullmatch(text) or text.startswith("$"):
        return False
    try:
        float(text)
    except ValueError:
        return True
    return False


# A refusal's text for a value it names: the value itself where it is a reading symbol, as every name
# of a well-formed declaration is, and errors.safe_repr's text for anything else, so writing a refusal
# never formats a value no check has passed; an integer past the digit limit is named by its sign and
# that limit, never converted (c-integrate-binding-declaration-repr-escape-1019).
# am[implements a-integrate-binding-declaration-refusal-repair-1019@59efc5]
# am[rests-on c-bnd-declaration-escape-surface-1019@ac7ef9] am[related a-rt-rr-safe-repr-1018@ec9700]
def _label(value: object) -> str:
    return value if is_reading_symbol(value) else safe_repr(value)


# The problems with a field that must be a tuple of members `fits` accepts: the field itself when it is
# no plain tuple, else each member that does not fit, quoted through errors.safe_repr.
# Time: one call of fits per member.
# am[implements a-integrate-binding-declaration-refusal-repair-1019@59efc5]
def _members(what: str, members: object, fits: Callable[[object], bool], noun: str) -> list[str]:
    if type(members) is not tuple:
        return [f"its {what} are {safe_repr(members)}, not a tuple"]
    return [f"its {what} hold {safe_repr(member)}, which is not {noun}" for member in members if not fits(member)]


# am[implements a-integrate-binding-declaration-refusal-repair-1019@59efc5]
def _pair(value: object) -> bool:
    return type(value) is tuple and len(value) == 2


# What a declaration's module may be: its text, or a path as pathlib makes one. Exact types, as for
# every value a declaration holds, so no subclass changes how a refusal writes it.
# am[implements a-integrate-binding-declaration-refusal-repair-1019@59efc5]
_MODULES = (str, PurePosixPath, PureWindowsPath, PosixPath, WindowsPath)


# am[implements a-dr-reader-core-1018@84955f]
def _digest(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# One answer a proposition can get, and the evidence direction it gives.
# am[implements a-dr-direction-words-1018@1b6ec6]
@dataclass(frozen=True, slots=True)
class AnswerOption:
    name: str
    direction: str
    description: str


# A statement Jev judges against a text, and the question the cross-encoder ranks passages by.
# am[implements a-dr-one-name-1018@beba5e]
@dataclass(frozen=True, slots=True)
class Proposition:
    id: str
    statement: str
    question: str


# A reading whose answer is one of its own options rather than a proposition's truth.
# am[implements a-dr-reader-core-1018@84955f]
@dataclass(frozen=True, slots=True)
class Choice:
    id: str
    instructions: str
    options: tuple[tuple[str, str], ...]


# Which declared entity a proposition is about: a Choice over the entities the bigraph section
# declares under `control`, each (id, description) in declaration order, and NO_MATCH, described by
# `no_match`. read_section answers a binding with no entities; the domain loader gives it its
# control's (with_entities). Its question is keyed "SIGNAL CONTROL", which no reading id can be,
# since an id holds no space; that key names the question to Jev's client and the corpus report and
# is never a signal's name.
# am[implements a-bnd-form-1019@787476] am[implements a-bnd-candidates-1019@61b2d4]
@dataclass(frozen=True, slots=True)
class Binding:
    signal: str
    control: str
    instructions: str
    no_match: str
    entities: tuple[tuple[str, str], ...] = ()

    @property
    def question_id(self) -> str:
        return f"{self.signal} {self.control}"

    @property
    def options(self) -> tuple[str, ...]:
        """The answers the binding's Choice may give: each offered entity, then NO_MATCH."""

        return (*(entity for entity, _ in self.entities), NO_MATCH)


# What admit() needs of a reading fact: the proposition it reads and the answer it records.
# am[implements a-dr-explicit-table-1018@bba9ce]
class _Fact(Protocol):
    @property
    def reading_id(self) -> str: ...

    @property
    def answer(self) -> str: ...


F = TypeVar("F", bound=_Fact)


# A binding's name in a refusal: its question id, each half through _label.
# am[implements a-integrate-binding-declaration-refusal-repair-1019@59efc5]
def _named(binding: Binding) -> str:
    return f"{_label(binding.signal)} {_label(binding.control)}"


# A ReadingDeclaration's every value is well formed however it is built: each text is nonempty, each
# name a reading symbol, each option's direction one of DIRECTIONS and the module a path. It holds
# plain values of exact types, str, tuple, its own records and pathlib's paths, so no subclass changes
# how a value reads or renders. Its construction checks shapes before values, each record field a tuple
# of its records and each choice option and binding entity a pair, so no check meets a value it cannot
# take apart; it checks each value as its own (place, value) entry, so an entry named as another
# cannot hide it; and its refusals format a value only once it is a reading symbol, quoting anything
# else through errors.safe_repr, so a malformed value at any place is refused as InvalidInputError,
# never another exception (c-bnd-declaration-escape-surface-1019). What the values must satisfy
# together, distinct names, propositions and choices sharing one namespace of ids, an option and one
# giving evidence, a reading, and a binding of a declared proposition over a declared control's
# described entities, is checked by the section's tables over FACTS when the domain loader reads the
# section, so each rule has one home.
# am[implements a-dr-reader-core-1018@84955f] am[implements a-dr-identity-1018@df82ab] am[implements a-dr-explicit-table-1018@bba9ce]
# am[implements a-dr-dt-module-1018@8da5f7] am[rests-on c-dr-dt-value-checks-every-path-1018@f5c5ad]
# am[implements a-bnd-form-1019@787476] am[implements a-bnd-candidates-1019@61b2d4]
# am[implements a-integrate-binding-declaration-refusal-repair-1019@59efc5] am[rests-on c-bnd-declaration-escape-surface-1019@ac7ef9]
@dataclass(frozen=True, slots=True)
class ReadingDeclaration:
    """One domain's reading declaration, identified by `digest`, read from the file `module`."""

    name: str
    model: str
    language: str
    instructions: str
    options: tuple[AnswerOption, ...]
    propositions: tuple[Proposition, ...]
    choices: tuple[Choice, ...]
    ranking_instruction: str
    module: Path
    bindings: tuple[Binding, ...] = ()
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        self._refuse([
            *([] if type(self.module) in _MODULES else [f"its module is {safe_repr(self.module)}, not a path"]),
            *_members("options", self.options, lambda o: type(o) is AnswerOption, "an answer option"),
            *_members("propositions", self.propositions, lambda p: type(p) is Proposition, "a proposition"),
            *_members("choices", self.choices, lambda c: type(c) is Choice, "a choice"),
            *_members("bindings", self.bindings, lambda b: type(b) is Binding, "a binding"),
        ])
        self._refuse([
            *(problem for c in self.choices
              for problem in _members(f"{_label(c.id)} options", c.options, _pair, "an (option, description) pair")),
            *(problem for b in self.bindings
              for problem in _members(f"binding {_named(b)} entities", b.entities, _pair, "an (id, description) pair")),
        ])
        texts = [
            ("model", self.model),
            ("language", self.language),
            ("instructions", self.instructions),
            ("ranking instruction", self.ranking_instruction),
            *((f"{_label(p.id)} statement", p.statement) for p in self.propositions),
            *((f"{_label(p.id)} question", p.question) for p in self.propositions),
            *((f"{_label(c.id)} instructions", c.instructions) for c in self.choices),
            *((f"{_label(c.id)} option {_label(option)}", text) for c in self.choices for option, text in c.options),
            *((f"option {_label(o.name)}", o.description) for o in self.options),
            *((f"binding {_named(b)} instructions", b.instructions) for b in self.bindings),
            *((f"binding {_named(b)} no-match description", b.no_match) for b in self.bindings),
            *((f"binding {_named(b)} entity {_label(entity)}", text) for b in self.bindings for entity, text in b.entities),
        ]
        names = [
            ("domain name", self.name),
            *(("answer names", o.name) for o in self.options),
            *(("reading ids", p.id) for p in self.propositions),
            *(("reading ids", c.id) for c in self.choices),
            *((f"{_label(c.id)} options", option) for c in self.choices for option, _ in c.options),
            *(("binding signals", b.signal) for b in self.bindings),
            *(("binding controls", b.control) for b in self.bindings),
            *((f"binding {_named(b)} entities", entity) for b in self.bindings for entity, _ in b.entities),
        ]
        self._refuse([
            *(f"its {what} is not nonempty text" for what, text in texts if type(text) is not str or not text.strip()),
            *(f"{safe_repr(value)} in its {what} is not a reading symbol"
              for what, value in names if not is_reading_symbol(value)),
            *(f"option {_label(o.name)} has the direction {safe_repr(o.direction)}, not one of {DIRECTIONS}"
              for o in self.options if type(o.direction) is not str or o.direction not in DIRECTIONS),
        ])
        object.__setattr__(self, "digest", _digest(self.content()))

    # The declaration's one refusal, naming its first problem and listing them all; the module is
    # written as its path, or quoted through errors.safe_repr when it is none.
    # am[implements a-integrate-binding-declaration-refusal-repair-1019@59efc5]
    def _refuse(self, problems: list[str]) -> None:
        if problems:
            module = str(self.module) if type(self.module) in _MODULES else safe_repr(self.module)
            raise InvalidInputError(f"A reading declaration is not well formed: {problems[0]}.",
                                    details={"module": module, "problems": problems})

    def content(self) -> dict[str, Any]:
        """Everything the readings depend on, which `digest` hashes; the file's place is not part
        of it, so the same declaration anywhere is the same identity. A binding's entities and their
        descriptions are part of it, and a declaration with no binding has no bindings key, so it
        keeps the identity it had before bindings existed."""

        content: dict[str, Any] = {
            "domain": self.name,
            "model": self.model,
            "language": self.language,
            "instructions": self.instructions,
            "options": [[o.name, o.direction, o.description] for o in self.options],
            "propositions": [[p.id, p.statement, p.question] for p in self.propositions],
            "choices": [[c.id, c.instructions, [list(o) for o in c.options]] for c in self.choices],
            "ranking_instruction": self.ranking_instruction,
        }
        if self.bindings:
            content["bindings"] = [[b.signal, b.control, b.instructions, b.no_match, [list(e) for e in b.entities]]
                                   for b in self.bindings]
        return content

    @property
    def answers(self) -> tuple[str, ...]:
        return tuple(option.name for option in self.options)

    # The answers that give evidence, which are the ones worth grounding in a passage.
    @property
    def decided(self) -> frozenset[str]:
        return frozenset(o.name for o in self.options if o.direction in JUDGEMENTS)

    def direction(self, answer: str) -> str:
        for option in self.options:
            if option.name == answer:
                return option.direction
        raise InvalidInputError(
            "The answer is not one this reading declaration declares.",
            details={"domain": self.name, "answer": repr(answer)[:100], "answers": list(self.answers)},
        )

    def proposition(self, reading_id: str) -> Proposition:
        for proposition in self.propositions:
            if proposition.id == reading_id:
                return proposition
        raise InvalidInputError(
            "The proposition is not one this reading declaration declares.",
            details={"domain": self.name, "reading": repr(reading_id)[:100]},
        )

    # The question text and its criteria are all a cached Jev answer's key digests, besides the
    # model and the state, so ids and the file's place never move a key
    # (c-dr-cache-key-content-1018); a binding's key moves with any entity or description it offers.
    # A binding asks its instructions followed by its proposition's statement, as a proposition asks
    # the section's, and offers each entity by its description, since its description is all Jev
    # identifies an entity by (c-bnd-linking-by-descriptions-1019); one offering no entity has no
    # question to ask, so it is refused rather than asked with no match alone.
    # am[rests-on c-dr-cache-key-content-1018@420689] am[implements a-bnd-question-1019@b2f0b9]
    # am[rests-on c-bnd-linking-by-descriptions-1019@e01edd]
    def questions(self) -> dict[str, dict[str, Any]]:
        """Jev Choice questions keyed by reading id: one per proposition, then one per choice, then
        one per binding under its question_id."""

        criteria = {option.name: option.description for option in self.options}
        asked: dict[str, dict[str, Any]] = {
            p.id: {"type": "choice", "instructions": self.instructions + p.statement, "criteria": criteria}
            for p in self.propositions
        }
        asked.update(
            {c.id: {"type": "choice", "instructions": c.instructions, "criteria": dict(c.options)}
             for c in self.choices}
        )
        for binding in self.bindings:
            if not binding.entities:
                raise InvalidInputError(
                    "A binding offers no entity, so its declaration was not read through the domain loader.",
                    details={"domain": self.name, "binding": binding.question_id},
                )
            asked[binding.question_id] = {
                "type": "choice",
                "instructions": binding.instructions + self.proposition(binding.signal).statement,
                "criteria": {**dict(binding.entities), NO_MATCH: binding.no_match},
            }
        return asked

    def admit(self, fact: F) -> F:
        """The fact itself when its proposition and answer are declared here; otherwise
        InvalidInputError, since another domain's reading means something this one never
        asked."""

        problems = []
        if fact.reading_id not in {p.id for p in self.propositions}:
            problems.append("its proposition is not declared")
        if fact.answer not in self.answers:
            problems.append("its answer is not declared")
        if problems:
            raise InvalidInputError(
                f"A reading is not one the {self.name} reading declaration asks: {problems[0]}.",
                details={"domain": self.name, "digest": self.digest,
                         "reading": repr(fact.reading_id)[:100], "answer": repr(fact.answer)[:100],
                         "problems": problems},
            )
        return fact


# am[implements a-dr-reader-core-1018@84955f]
def _invalid(module: Path, problem: str, form: str = "") -> InvalidInputError:
    return InvalidInputError(
        f"A reading declaration is not well formed: {problem}.",
        details={"path": str(module), "form": form[:300]},
    )


# Each form is checked against its head's shape, and a form with any other head is refused, so the
# domain loader hands this the forms whose heads are HEADS; the domain file's pymetta parse gives
# each string what MeTTa reads it as, escapes included.
# Time: one shape check per form.
# am[implements a-dr-reader-core-1018@84955f] am[implements a-dr-readings-move-1018@8f7d09]
# am[implements a-bnd-form-1019@787476]
def read_section(forms: Iterable[tuple[TopLevelForm, Any]], module: Path) -> ReadingDeclaration:
    """The reading declaration the forms declare, each a (TopLevelForm, atom) pair from
    goal_chainer.domains.forms.parsed_forms; module names the file they were read from."""

    def invalid(problem: str, form: str = "") -> InvalidInputError:
        return _invalid(module, problem, form)

    from metta import Expression, Grounded, Symbol  # noqa: PLC0415 (pymetta, the pinned engine)

    def symbol(atom: Any, what: str, form: str) -> str:
        if not isinstance(atom, Symbol):
            raise invalid(f"its {what} is not a symbol", form)
        return atom.name

    def string(atom: Any, what: str, form: str) -> str:
        if not (isinstance(atom, Grounded) and isinstance(atom.value, str)):
            raise invalid(f"its {what} is not a string", form)
        return atom.value

    singles: dict[str, list[str]] = {head: [] for head in _SINGLE}
    options: list[AnswerOption] = []
    propositions: list[Proposition] = []
    choices: list[Choice] = []
    bindings: list[Binding] = []
    for form, atom in forms:
        parts = list(atom) if isinstance(atom, Expression) else []
        head = parts[0].name if parts and isinstance(parts[0], Symbol) else None
        if head in _SINGLE:
            if len(parts) != 2:
                raise invalid(f"({head} VALUE) takes one argument", form.text)
            value = (symbol if _SINGLE[head] == "symbol" else string)(parts[1], head, form.text)
            singles[head].append(value)
        elif head == "gc-reading-option":
            if len(parts) != 4:
                raise invalid("(gc-reading-option NAME DIRECTION DESCRIPTION) takes three arguments", form.text)
            options.append(AnswerOption(symbol(parts[1], "name", form.text),
                                        symbol(parts[2], "direction", form.text),
                                        string(parts[3], "description", form.text)))
        elif head == "gc-reading-proposition":
            if len(parts) != 4:
                raise invalid("(gc-reading-proposition ID STATEMENT QUESTION) takes three arguments", form.text)
            propositions.append(Proposition(symbol(parts[1], "id", form.text),
                                            string(parts[2], "statement", form.text),
                                            string(parts[3], "question", form.text)))
        elif head == "gc-reading-choice":
            if len(parts) != 4 or not isinstance(parts[3], Expression):
                raise invalid("(gc-reading-choice ID INSTRUCTIONS ((OPTION DESCRIPTION) ...)) takes three arguments", form.text)
            pairs = []
            for pair in parts[3]:
                items = list(pair) if isinstance(pair, Expression) else []
                if len(items) != 2:
                    raise invalid("a choice option is not (OPTION DESCRIPTION)", form.text)
                pairs.append((symbol(items[0], "option", form.text), string(items[1], "option description", form.text)))
            choices.append(Choice(symbol(parts[1], "id", form.text),
                                  string(parts[2], "instructions", form.text), tuple(pairs)))
        elif head == "gc-reading-binding":
            if len(parts) != 5:
                raise invalid("(gc-reading-binding SIGNAL CONTROL INSTRUCTIONS NO-MATCH) takes four arguments", form.text)
            bindings.append(Binding(symbol(parts[1], "signal", form.text), symbol(parts[2], "control", form.text),
                                    string(parts[3], "instructions", form.text),
                                    string(parts[4], "no-match description", form.text)))
        else:
            raise invalid("it is not a reading declaration form", form.text)
    for head, values in singles.items():
        if len(values) != 1:
            raise invalid(f"it must declare ({head} ...) exactly once, not {len(values)} times")
    return ReadingDeclaration(
        name=singles["gc-reading-domain"][0],
        model=singles["gc-reading-model"][0],
        language=singles["gc-reading-language"][0],
        instructions=singles["gc-reading-instructions"][0],
        options=tuple(options),
        propositions=tuple(propositions),
        choices=tuple(choices),
        ranking_instruction=singles["gc-ranking-instruction"][0],
        module=module,
        bindings=tuple(bindings),
    )


# A declaration written back as its section's forms, one top-level form's text each, in the order
# read_section's grammar lists them, through the codec every MeTTa text GoalChainer writes goes
# through; read_section reads them as a declaration with the same digest once each binding is given
# its entities again, which the bigraph section, not the reading section, declares. A SNARS batch
# carries its declaration as these forms, so the policy reads the rows the batch's facts were
# admitted against; it reads no binding row (c-bnd-snars-policy-ignores-binding-rows-1019).
# Time: one emit per form.
# am[implements a-dr-sr-snars-batch-declaration-1018@5c965d] am[implements a-bnd-form-1019@787476]
def forms(declaration: ReadingDeclaration) -> tuple[str, ...]:
    codec = SexprCodec()
    symbol, string, row = codec.symbol, codec.string, codec.expression
    return tuple(codec.emit(form) for form in (
        row("gc-reading-domain", symbol(declaration.name)),
        row("gc-reading-model", string(declaration.model)),
        row("gc-reading-language", string(declaration.language)),
        row("gc-reading-instructions", string(declaration.instructions)),
        *(row("gc-reading-option", symbol(o.name), symbol(o.direction), string(o.description))
          for o in declaration.options),
        *(row("gc-reading-proposition", symbol(p.id), string(p.statement), string(p.question))
          for p in declaration.propositions),
        *(row("gc-reading-choice", symbol(c.id), string(c.instructions),
              [[symbol(option), string(text)] for option, text in c.options])
          for c in declaration.choices),
        *(row("gc-reading-binding", symbol(b.signal), symbol(b.control), string(b.instructions), string(b.no_match))
          for b in declaration.bindings),
        row("gc-ranking-instruction", string(declaration.ranking_instruction)),
    ))


# The declaration's facts for the domain validation runner, every name a string as the shared
# vocabulary's are: the section itself; each proposition declared as a signal, so it shares the core's
# one id table with gc-signal, and again as a proposition, which the choice rows tell from a gc-signal;
# each choice declared in that table and again with its own options, so two choices sharing an id
# never make either's options look repeated; each answer option with its direction; and each option
# the declaration counts as decided, the evidence rule staying JUDGEMENTS'; and each binding's signal
# and control, which the binding rows read beside the bigraph section's controls and entities.
# readings.metta's tables read them.
# Time: one fact per section and binding, two per proposition and choice, at most two per answer option.
# am[implements a-dr-readings-facts-1018@64445a] am[implements a-dr-dt-facts-1018@2ca5b0]
# am[rests-on c-dr-dt-core-same-kind-duplicates-1018@3c4ed3] am[rests-on c-dr-dt-choice-copies-cascade-1018@8dfe84]
# am[implements a-bnd-faults-1019@b5dc70]
def FACTS(declaration: ReadingDeclaration) -> tuple[tuple[Any, ...], ...]:  # noqa: N802 (the runner's section interface)
    return (
        ("Readings", declaration.name),
        *(("Declared", "signal", p.id) for p in declaration.propositions),
        *(("Declared", "choice", c.id) for c in declaration.choices),
        *(("Proposition", p.id) for p in declaration.propositions),
        *(("Option", o.name, o.direction) for o in declaration.options),
        *(("Decided", o.name) for o in declaration.options if o.direction in JUDGEMENTS),
        *(("Choice", c.id, ("Options", *(option for option, _ in c.options))) for c in declaration.choices),
        *(("Binding", b.signal, b.control) for b in declaration.bindings),
    )


# The declaration with each binding offering every entity declared under its control, in declaration
# order with its description: entities are (id, control, description) as the bigraph section reads
# them, the one place they are declared. The domain loader calls this once the domain's checks pass,
# so every binding's control is declared and has an entity, each of them described.
# Time: one pass over the entities and one over the bindings.
# am[implements a-bnd-candidates-1019@61b2d4]
def with_entities(declaration: ReadingDeclaration, entities: Iterable[tuple[str, str, str]]) -> ReadingDeclaration:
    offered: dict[str, list[tuple[str, str]]] = {}
    for entity, control, description in entities:
        offered.setdefault(control, []).append((entity, description))
    return replace(declaration, bindings=tuple(replace(b, entities=tuple(offered.get(b.control, ())))
                                               for b in declaration.bindings))


__all__ = [
    "CHECKS",
    "DIRECTIONS",
    "ENTRY",
    "FACTS",
    "HEADS",
    "JUDGEMENTS",
    "NO_MATCH",
    "WARM_UP",
    "AnswerOption",
    "Binding",
    "Choice",
    "Proposition",
    "ReadingDeclaration",
    "forms",
    "is_reading_symbol",
    "read_section",
    "with_entities",
]

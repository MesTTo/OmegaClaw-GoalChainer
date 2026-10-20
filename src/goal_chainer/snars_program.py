"""Purpose: build GoalChainer's SNARS batches as validated values, hold the one table of modules a
batch's world loads after the packaged SNARS library, carry in each batch the reading declaration
its facts were admitted against, parse and build SNARS statements, and turn the semantic
reader's readings of a text into the facts SNARS ingestion stores."""

from __future__ import annotations

from importlib.resources import files
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from .runtime.modules import MettaLibrary
from .runtime.budget import RunBudget
from .domains.readings import ReadingDeclaration, forms as declaration_forms
from .snars_ingestion import ReadingFact, reading_facts
from .sexpr.codec import SexprCodec
from .errors import InvalidInputError, safe_repr

# A session's reader is its caller's to choose and is named here only in an annotation, so the
# SNARS core imports no semantic reader.
# am[implements a-sib-home-snars-ingestion-1018@5727d2]
if TYPE_CHECKING:
    from .semantic_reader import SemanticReader

# GoalChainer's SNARS modules ship in the package, so an installed wheel loads every module a world
# holds.
# am[implements a-core-package-resources-1016@be483a] am[implements a-rt-snars-modules-in-package-1016@7d0afe]
# am[implements a-ie-s2b-scalar-modules-1018@df30d8]
PROTOCOL_PATH = Path(str(files("goal_chainer").joinpath("policy", "goalchainer_protocol.metta")))
POLICY_PATH = Path(str(files("goal_chainer").joinpath("policy", "goalchainer_policy.metta")))

# SNARS ships in this package, in snars_library/, whose PROVENANCE.md names the Mettabase commit it
# was taken from; the engine resolves `(library snars X)` under that directory.
# am[implements a-rt-snars-adopt-library-1017@1231db]
SNARS_DIRECTORY = Path(__file__).resolve().parent / "snars_library"
SNARS_LIBRARY = MettaLibrary("snars", "snars")

# The modules a batch's world loads after the SNARS library, in load order, each with the optional feature that includes it, or None where every world loads it.
# No world loads a reading declaration: a batch carries its own (SnarsBatch.rows).
# am[implements a-rt-snars-batch-value-1017@0e8147] am[implements a-integrate-ecan-forward-query-interface-1017]
# am[related a-dr-sr-snars-batch-declaration-1018@5c965d] am[implements a-ie-s2b-scalar-modules-1018@df30d8]
WORLD_MODULES: tuple[tuple[str | None, Path], ...] = (
    ("policy", POLICY_PATH),
    (None, PROTOCOL_PATH),
    ("guard", SNARS_DIRECTORY / "snars-guard.metta"),
    ("attention", PROTOCOL_PATH.with_name("goalchainer_attention.metta")),
    ("attention", PROTOCOL_PATH.with_name("goalchainer_attention_graph.metta")),
    ("attention", PROTOCOL_PATH.with_name("goalchainer_attention_control.metta")),
    ("attention", PROTOCOL_PATH.with_name("goalchainer_attention_query.metta")),
)
# The optional features a batch may include, in WORLD_MODULES order.
FEATURES: tuple[str, ...] = tuple(dict.fromkeys(f for f, _ in WORLD_MODULES if f is not None))
# What a feature adds to a batch's directive ahead of its operation: the policy believes the
# request's readings and runs two SNARS cycles over them, which derive what SNARS's own syllogistic
# rules conclude; the policy registers no rule of its own.
# am[implements a-rt-snars-batch-value-1017@0e8147] am[implements a-ie-s7-metta-1018@0ca8fe]
# am[rests-on c-ie-cycles-generic-1018@d7387c]
FEATURE_EFFECTS: Mapping[str, tuple[str, ...]] = {
    "policy": ("(gc assert-request-context!)", "(sn cycles 2)"),
}
# The feature whose module reads a batch's reading declaration: goalchainer_policy.metta matches its
# option and proposition rows when a batch runs and at no other time, so a batch that includes the
# policy carries its declaration's rows, when it has one, and no other batch's world sees them, as
# worlds without the policy never loaded a declaration (c-dr-policy-rows-call-time-1018). The policy
# reads those rows only while it believes readings, so a policy batch carrying none needs no
# declaration and still runs the policy's cycles (c-dr-snars-facts-need-declaration-1018).
# am[implements a-dr-sr-snars-batch-declaration-1018@5c965d] am[implements a-jev-reading-belief-1016]
# am[rests-on c-dr-policy-rows-call-time-1018@257f9a] am[rests-on c-dr-snars-facts-need-declaration-1018@22456d]
DECLARATION_FEATURE = "policy"


# am[implements a-rt-snars-batch-value-1017@0e8147]
def feature_set(includes: Iterable[str]) -> frozenset[str]:
    """The optional features named, as a frozenset, refusing any name FEATURES does not hold."""

    included = frozenset(includes)
    unknown = sorted(map(repr, included - set(FEATURES)))
    if unknown:
        raise InvalidInputError(
            "A SNARS world includes only the optional features its modules define.",
            details={"unknown": unknown, "features": list(FEATURES)},
        )
    return included


# am[implements a-rt-snars-batch-value-1017@0e8147]
def world_modules(includes: frozenset[str]) -> tuple[Path, ...]:
    """The modules a world with these optional features loads after the SNARS library, in order."""

    return tuple(path for feature, path in WORLD_MODULES if feature is None or feature in includes)

_FORBIDDEN_HEADS = frozenset(
    {
        "!",
        "=",
        "add-atom",
        "bind!",
        "import!",
        "py-call",
        "remove-atom",
        "transfer!",
    }
)


@dataclass(frozen=True, slots=True)
class ProgramFragments:
    """Plain facts and effect expressions generated for one operation."""

    facts: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()


# am[implements a-jev-snars-ingest-1016]
@dataclass(frozen=True, slots=True)
class TextIngestion:
    """One text's reading as program facts, with the reader revision that produced them."""

    revision: str
    fragments: ProgramFragments


_CODEC = SexprCodec()


# A SNARS statement from its source: a nonempty sn or sh expression with no executable form and, unless
# it is a pattern, no variable. The codec is SNARS-neutral, so the statement grammar lives here.
# am[implements a-rt-rb-codec-1018@e3e552] am[implements a-rt-sexpr-codec-packaged-1017@608f80]
def parse_statement(source: str, *, pattern: bool = False) -> Any:
    atom = _CODEC.parse(source)
    _validate_statement_atom(atom, _CODEC, pattern=pattern)
    return atom


# Time and space: O(n), n = the number of nodes in the source expression.
# am[implements a-integrate-guard-metta-build-1019@e688cb]
def parse_guard(source: str) -> list[Any]:
    """Read one guard expression without executing its operators or variables."""

    if not isinstance(source, str):
        raise InvalidInputError("A guard clause or goal must be MeTTa source text.")
    forms = _CODEC.parse(f"({source})")
    if not (isinstance(forms, list) and len(forms) == 1
            and isinstance(forms[0], list) and forms[0]):
        raise InvalidInputError("A guard clause or goal must be exactly one nonempty expression.")
    for node in _walk(forms[0]):
        if isinstance(node, list) and (
            not node or not isinstance(node[0], _CODEC.Symbol) or node[0].text.startswith("$")
        ):
            raise InvalidInputError("A guard expression needs a fixed symbol as its head.")
    return forms[0]


# The SNARS statement relating a subject concept to an object concept, both named by text.
# am[implements a-rt-rb-codec-1018@e3e552]
def binary_statement(relation: str, subject: str, object_: str) -> list[Any]:
    def concept(name: str) -> list[Any]:
        return _CODEC.expression("sn", _CODEC.symbol("c"), _CODEC.string(name))

    return _CODEC.expression(
        "sn",
        _CODEC.symbol("p"),
        _CODEC.symbol("so"),
        _CODEC.string(relation),
        [
            [_CODEC.symbol("arg"), _CODEC.symbol("s"), concept(subject)],
            [_CODEC.symbol("arg"), _CODEC.symbol("o"), concept(object_)],
        ],
    )


# A batch is checked once, where it is made, so neither engine runs anything but readings and one
# expression: a stored event cannot carry other MeTTa into a world. The directive is parsed inside
# one more pair of parentheses because the codec answers several top-level forms as the list of
# them, which a single expression of lists would otherwise look like. A source's readings carry
# one trust, because the reading policy believes them once, as the mean of their units, under that
# trust, and the mean of trusted evidence is the trusted mean only when one trust scales it all.
# Every fact is admitted by the batch's own declaration, the one its rows give the policy, so a
# reading of a proposition or an answer that declaration does not ask is refused here rather than
# dropped by the policy, and a session reading another domain runs in the same compiled worlds.
# am[implements a-rt-snars-batch-value-1017@0e8147] am[implements a-jev-fact-grammar-one-1018@0f04e2]
# am[implements a-ev-wt-context-mean-1017@46162f] am[rests-on c-ev-rt-agrees-batch-trust-1017@18bf73]
# am[implements a-dr-explicit-table-1018@bba9ce] am[implements a-dr-sr-snars-batch-declaration-1018@5c965d]
# am[related a-rt-snars-declaration-boundary-1018@c03022] am[implements a-ie-sr-readerless-session-1018@9ffb9b]
# am[implements a-rt-rr-safe-repr-1018@ec9700]
@dataclass(frozen=True, slots=True)
class SnarsBatch:
    """One SNARS batch as MeTTa text: the gc-reading facts it adds to its world, the optional
    features whose modules that world loads, the one expression it evaluates as `!DIRECTIVE`, and
    the reading declaration its facts were admitted against, which a batch with no facts, such as
    track's or any of a session opened without a reader, does without.

    Making one raises InvalidInputError unless `includes` names only FEATURES, a batch with facts
    has a ReadingDeclaration, every fact is a reading ReadingFact accepts and the declaration
    admits, every reading of one source carries one trust, and the directive is exactly one
    expression.
    """

    facts: tuple[str, ...]
    includes: frozenset[str]
    directive: str
    declaration: ReadingDeclaration | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.facts, tuple) or not all(isinstance(fact, str) for fact in self.facts):
            raise InvalidInputError("A SNARS batch's facts must be a tuple of text.")
        if not isinstance(self.includes, frozenset):
            raise InvalidInputError("A SNARS batch's included features must be a frozenset.")
        feature_set(self.includes)
        if self.declaration is None:
            if self.facts:
                raise InvalidInputError(
                    "A SNARS batch that carries readings needs the reading declaration they are read against.",
                    details={"facts": len(self.facts)},
                )
        elif not isinstance(self.declaration, ReadingDeclaration):
            raise InvalidInputError("A SNARS batch's declaration must be a ReadingDeclaration.",
                                    details={"declaration": safe_repr(self.declaration)[:200]})
        trusts: dict[str, set[float]] = {}
        for fact in self.facts:
            reading = self.declaration.admit(ReadingFact.parse(fact, _CODEC))
            trusts.setdefault(reading.source, set()).add(reading.trust)
        for source, values in sorted(trusts.items()):
            if len(values) > 1:
                raise InvalidInputError(
                    "A SNARS batch's readings of one source must carry one trust.",
                    details={"source": source, "trusts": sorted(values)},
                )
        if not isinstance(self.directive, str):
            raise InvalidInputError("A SNARS batch's directive must be text.")
        forms = _CODEC.parse(f"({self.directive})")
        if not (isinstance(forms, list) and len(forms) == 1 and isinstance(forms[0], list) and forms[0]):
            raise InvalidInputError(
                "A SNARS batch's directive must be exactly one expression.",
                details={"directive": self.directive[:200]},
            )

    @property
    def modules(self) -> tuple[Path, ...]:
        """The modules this batch's world loads after the SNARS library, in load order."""

        return world_modules(self.includes)

    # Time: one emit per declaration form, about 17 for the incident domain.
    @property
    def rows(self) -> tuple[str, ...]:
        """The declaration's section forms when the batch includes DECLARATION_FEATURE, else
        nothing; both engines add them to the world beside the facts."""

        if self.declaration is None or DECLARATION_FEATURE not in self.includes:
            return ()
        return declaration_forms(self.declaration)


class SnarsProgramBuilder:
    """Build one batch whose only machine record is the requested operation."""

    # A builder reads with the reader its session was given and gives every batch that reader's
    # declaration, so a session's readings and its batches' admission agree on one declaration by
    # construction. Each reader owns its cross-encoder, so the caller chooses which one a session
    # shares; making a reader loads neither Jev's table nor the cross-encoder, which its first read
    # loads, so programs that ingest no text load neither. A builder without a reader builds only
    # batches that carry no reading, with the policy or without it, as track and a session opened
    # without a reader do, so a statement computation reads no domain.
    # am[implements a-jev-snars-ingest-1016] am[implements a-dr-sr-snars-batch-declaration-1018@5c965d]
    # am[implements a-ie-sr-readerless-session-1018@9ffb9b]
    def __init__(self, reader: SemanticReader | None = None) -> None:
        self.codec = _CODEC
        self.reader = reader

    # am[implements a-ev-br-builder-1017@fa66f9]
    def belief_effect(
        self,
        statement: Any,
        *,
        positive: float,
        negative: float,
        base_rate: float | None,
        source: str,
        trust: float,
        occurrence: float | None = None,
    ) -> str:
        return self.codec.emit(
            self.codec.expression(
                "believe!",
                statement,
                self.evidence_options(
                    positive=positive,
                    negative=negative,
                    base_rate=base_rate,
                    source=source,
                    trust=trust,
                    occurrence=occurrence,
                ),
            )
        )

    # One unit of evidence as the options believe! and what-if! read. Both read a missing
    # (rate R) as (sn config default-rate), so a rate the caller did not give is not written.
    # am[implements a-ev-br-builder-1017@fa66f9] am[rests-on c-ev-snars-default-applies-1017@1fc3d2]
    def evidence_options(
        self,
        *,
        positive: float,
        negative: float,
        base_rate: float | None,
        source: str,
        trust: float,
        occurrence: float | None = None,
    ) -> list[Any]:
        options: list[Any] = [[self.codec.symbol("evidence"), positive, negative]]
        if base_rate is not None:
            options.append([self.codec.symbol("rate"), base_rate])
        options += [
            [self.codec.symbol("source"), self.codec.string(source)],
            [self.codec.symbol("trust"), trust],
        ]
        if occurrence is not None:
            options.append([self.codec.symbol("occ"), occurrence])
        return options

    # A rate SNARS takes as an argument, as outcome! and marginal! do: the caller's, or else the
    # library's configured default, called as SNARS's own ingest and temporal modules call it.
    # am[implements a-ev-br-builder-1017@fa66f9] am[rests-on c-ev-snars-default-applies-1017@1fc3d2]
    def rate(self, base_rate: float | None) -> Any:
        if base_rate is None:
            return self.codec.expression("sn", self.codec.symbol("config"), self.codec.symbol("default-rate"))
        return base_rate

    def goal_effect(self, statement: Any, desire: float) -> str:
        return self.codec.emit(
            self.codec.expression(
                "goal!",
                statement,
                [[self.codec.symbol("desire"), desire]],
            )
        )

    # am[implements a-jev-snars-ingest-1016]
    # am[implements a-dr-reader-budget-required-1018@0b0cce]
    def text_ingestion(self, text: str, *, source: str, trust: float, budget: RunBudget) -> TextIngestion:
        """Read text with the semantic reader and keep one `gc-reading` fact per proposition.

        The facts carry no effect: goalchainer_policy.metta's (gc assert-request-context!)
        believes them when a policy batch runs, under this ingestion's source and trust. The
        reading is charged to `budget`, the request's.
        """

        if not isinstance(text, str) or not text.strip():
            raise InvalidInputError("Text ingestion requires nonempty text.")
        if self.reader is None:
            raise InvalidInputError("Text ingestion needs the reader its session was opened with.")
        reading = self.reader.read(text, budget=budget)
        return TextIngestion(
            revision=reading.revision,
            fragments=ProgramFragments(
                facts=reading_facts(reading, source=source, trust=trust, codec=self.codec)
            ),
        )

    # Every fact a batch carries, the stored events of a persistent session included, is checked
    # where the SnarsBatch is made; the grammar is snars_ingestion.ReadingFact's, the inverse of
    # the emitter that wrote the fact.
    # am[implements a-jev-snars-ingest-1016@2517b8] am[implements a-rt-snars-batch-value-1017@0e8147]
    def batch(
        self,
        operation: Any,
        *,
        facts: Sequence[str] = (),
        effects: Sequence[str] = (),
        includes: Iterable[str] = (),
    ) -> SnarsBatch:
        included = feature_set(includes)
        body_effects = [
            *effects,
            *(effect for feature in FEATURES if feature in included for effect in FEATURE_EFFECTS.get(feature, ())),
        ]
        operation_source = self.codec.emit(operation)
        if body_effects:
            bindings = " ".join(
                f"($gc-effect-{index} {effect})"
                for index, effect in enumerate(body_effects, start=1)
            )
            directive = f"(let* ({bindings}) {operation_source})"
        else:
            directive = operation_source
        return SnarsBatch(tuple(facts), included, directive, None if self.reader is None else self.reader.declaration)


def _validate_statement_atom(atom: Any, codec: SexprCodec, *, pattern: bool) -> None:
    if not isinstance(atom, list) or not atom:
        raise InvalidInputError("SNARS statement must be a nonempty expression.")
    head = _symbol_text(atom[0], codec)
    if head in _FORBIDDEN_HEADS or head not in {"sn", "sh", "sh-atom", "sh-conn"}:
        raise InvalidInputError(
            "SNARS statement uses a disallowed constructor.",
            details={"head": head},
        )
    for node in _walk(atom):
        if isinstance(node, codec.Symbol):
            if node.text in _FORBIDDEN_HEADS:
                raise InvalidInputError(
                    "SNARS statement contains an executable form.",
                    details={"symbol": node.text},
                )
            if not pattern and node.text.startswith("$"):
                raise InvalidInputError(
                    "Ground SNARS statements cannot contain variables.",
                    details={"symbol": node.text},
                )


def _walk(atom: Any) -> Iterable[Any]:
    yield atom
    if isinstance(atom, list):
        for item in atom:
            yield from _walk(item)


def _symbol_text(atom: Any, codec: SexprCodec) -> str:
    if not isinstance(atom, codec.Symbol):
        raise InvalidInputError("Expression head must be a MeTTa symbol.")
    return atom.text


__all__ = [
    "DECLARATION_FEATURE",
    "FEATURES",
    "FEATURE_EFFECTS",
    "POLICY_PATH",
    "PROTOCOL_PATH",
    "SNARS_DIRECTORY",
    "SNARS_LIBRARY",
    "WORLD_MODULES",
    "ProgramFragments",
    "SnarsBatch",
    "SnarsProgramBuilder",
    "TextIngestion",
    "binary_statement",
    "feature_set",
    "parse_statement",
    "parse_guard",
    "world_modules",
]

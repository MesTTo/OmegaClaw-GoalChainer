"""Purpose: run lib_deontic theories as bounded reviews on the process's pymetta engine, answering
typed conclusions, dilemmas, selected support trees, their cost and the engine's identity.

A theory is defeasible-deontic MeTTa: facts (`given`), defeasible rules (`normally`) and the
deontic operators must, may and forbidden. `run_deontic_theory` loads it through lib_deontic, from
the deontic library this package ships in deontic_library/, and answers a `DeonticRun`: every
tagged conclusion lib_deontic draws, the dilemmas it cannot resolve, the inferences the review
spent and the engine it ran on. The caller bounds a review with a `RunBudget`, by inferences and
by a deadline that every stage of the caller's run shares; the review runs under what is left of
it, is charged what it spent, and either bound stops it with a `BudgetExhausted`.

A review runs on a worker of the engine's pool, inside the engine's speculate() scope, so what it
writes to lib_deontic's theory spaces and what it compiles are discarded when it returns: no review
sees another's theory, a review its budget stopped leaves nothing behind, and every review starts
from the state lib_deontic's preparation left. Each review therefore pays its own first-call
compilation and support extraction. A process's first review would also do
work that speculation keeps: it links library predicates lib_deontic autoloads and adds their files
to SWI-Prolog's file search cache, whose insert sweeps the cache once 5 s have passed since its last
sweep. Preparation therefore reviews WARM_UP_THEORY once, inside speculation and charged to no
review, and a charged review's thread resets lib_deontic once before its first review, since the
reset makes SWI global variables each thread holds its own of; so the first review a caller is
charged costs what a later review of its theory costs, and no review's count follows the clock.
"""

from __future__ import annotations

import tempfile
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Literal, cast

from .runtime.budget import (
    BudgetExhausted,
    InferenceBudgetExceeded,
    ReviewTimeout,
    RunBudget,
    run_bounded,
)
from .runtime.modules import (
    MettaLibrary,
    initialize_once,
    load_metta_module,
    register_metta_library,
)
from .runtime.engine import pymetta_identity, shared_evaluation
from .sexpr.protocol import symbol_text
from .errors import DependencyUnavailableError, InvalidInputError, MettaEngineError, ProtocolError
from .sexpr.codec import SexprCodec

# lib_deontic ships in this package, in deontic_library/, whose PROVENANCE.md names the
# omegaclaw-deontic commit it was taken from. The engine resolves `(library deontic X)` under that
# directory, where register_metta_library binds it.
# am[implements a-rt-incorporate-deontic-1016@6ea255] am[rests-on c-rt-deontic-closure-1016@029061]
DEONTIC_DIRECTORY = Path(__file__).resolve().parent / "deontic_library"
DEONTIC_LIBRARY = MettaLibrary("deontic", "lib_deontic")
DEONTIC_SETUP = "deontic"

# The whole review is one MeTTa expression, because pymetta cannot call a compiled MeTTa function
# from a Prolog helper; the ingested rule count is read with match on &theory.
# am[implements a-rt-pymetta-deontic-1016@61a4b6] am[rests-on c-rt-pymetta-functions-not-prolog-1016@a9761a]
# am[implements a-integrate-deontic-support-trees-1019@508ecf]
REVIEW_SOURCE = (
    "!(let* (($cs (dl-run-deontic {path})) ($ds (dilemmas-in $cs))"
    " ($rules (size-atom (collapse (match &theory (rule $n $b $h $k) $n))))"
    " ($lits (unique-atom (union-atom (map-atom $cs $c (let ($tag $lit) $c $lit)) $ds)))"
    " ($support (map-atom $lits $lit (dl-explain $lit))))"
    " ($cs $ds $rules $support))"
)

# The theory preparation reviews once, so the work a process's first review does and speculation
# keeps is fixed startup work, charged to no review: without it the first review was charged about
# 7,700 inferences more than a later one, and 80 more again when it started 5 s or more after the
# file search cache's last sweep. One review of a small theory pays all of it that was measured:
# after a warm-up of the tests' SAMPLE alone, the first review of each packaged domain's theory spent
# what its second did. This one still uses every form and connective a GoalChainer domain theory may
# (domains.loader's THEORY_FORMS and connectives), a rule over a variable, a dilemma, and number and
# string arguments, so a path no measured theory took has run once too.
# am[implements a-rt-det-warmup-1018@c86a73] am[rests-on c-rt-det-first-review-pays-init-1018@ca7755]
# am[rests-on c-rt-det-warmup-not-plain-1018@af1fbe] am[rests-on c-rt-det-only-deontic-clock-1018@07d57f]
# am[rests-on c-rt-det-warmup-prototype-1018@ed9a5c] am[rests-on c-rt-det-warmup-measured-0008-1019@100af6]
WARM_UP_THEORY = """(given (candidate act_a))
(given (candidate act_b))
(given (signal urgent))
(given (not (signal approved)))
(given (rated act_a 0.5 3 "label"))
(always rUrgent (signal urgent) (must (do act_b)))
(normally rPermit (candidate ?a) (may (do ?a)))
(normally rForbid (and (candidate ?a) (not (signal approved))) (forbidden (do ?a)))
(prefer rForbid rPermit)
(except rRated (rated act_a 0.5 3 "label") (not (forbidden (do act_a))))
(normally rClashMust (signal urgent) (must (do act_c)))
(normally rClashForbid (signal urgent) (forbidden (do act_c)))
(normally rRepair (signal urgent) (otherwise (must (do act_a)) (must (do act_d))))
"""

# lib_deontic's spelling of a literal's deontic mode slot: F forbidden, O obligated, P permitted;
# "none" marks a literal that is not deontic.
OBLIGED = "O"
DEONTIC_MODES = ("F", OBLIGED, "P")
# Every status policy/goalchainer_deontic.metta answers; tests/test_deontic_status.py checks the
# rule answers exactly these over its whole input space.
DEONTIC_STATUSES = ("forbidden", "obligated", "permitted", "conflict", "unregulated")

# What prepare_deontic_engine loaded into this process's engine, set once its setup succeeds.
_IDENTITY: DeonticEngine | None = None
_SWIPL_FLAG = 0
# Whether this thread has reset lib_deontic, which a thread does before its first charged review.
# am[implements a-rt-det-deontic-thread-reset-1019@3c05d5]
_RESET = threading.local()

__all__ = [
    "BudgetExhausted",
    "DEONTIC_MODES",
    "DEONTIC_STATUSES",
    "DeonticConclusion",
    "DeonticEngine",
    "DeonticLiteral",
    "DeonticOutputError",
    "DeonticRun",
    "DeonticSupport",
    "InferenceBudgetExceeded",
    "OBLIGED",
    "ReviewTimeout",
    "RunBudget",
    "prepare_deontic_engine",
    "run_deontic_theory",
]


# am[implements a-rt-typed-deontic-api-1016@871afb]
class DeonticOutputError(ProtocolError):
    """lib_deontic answered something that is not a well-formed review."""

    code = "deontic_output_error"


# am[implements a-rt-typed-deontic-api-1016@871afb]
@dataclass(frozen=True, order=True, slots=True)
class DeonticLiteral:
    """A literal `(lit SIGN MODE TEMPORAL FUNCTOR (ARGS...))`.

    SIGN is pos or neg, MODE is F, O, P or none, TEMPORAL is none or a time term, and each
    argument is kept as its MeTTa text, so `(lit pos none none risky (publish_raw_log))` has
    args `("publish_raw_log",)`.
    """

    sign: str
    mode: str
    temporal: str
    functor: str
    args: tuple[str, ...]

    def render(self) -> str:
        return (
            f"(lit {self.sign} {self.mode} {self.temporal} {self.functor} "
            f"({' '.join(self.args)}))"
        )


# am[implements a-rt-typed-deontic-api-1016@871afb]
@dataclass(frozen=True, order=True, slots=True)
class DeonticConclusion:
    """One tagged conclusion: pD or nD proves or refutes definitely, pd or nd defeasibly."""

    tag: str
    literal: DeonticLiteral

    @property
    def is_provable(self) -> bool:
        """A defeasibly provable positive literal, the set DL(d) says the theory supports."""

        return self.tag == "pd" and self.literal.sign == "pos"

    def render(self) -> str:
        return f"({self.tag} {self.literal.render()})"


# am[implements a-rel-deontic-run-1016@be58d5]
@dataclass(frozen=True, slots=True)
class DeonticEngine:
    """What a review ran on, so a review fingerprint changes whenever the engine does.

    `runtime` is "pymetta <version>" and `runtime_digest` is SHA-256 over the installed
    distribution's RECORD, which lists every file of it with its own hash. `plugin_digest` is
    SHA-256 over the package's deontic library directory by relative path and content, and
    `swipl_version` is the SWI-Prolog bundled inside pymetta, which the review ran on.
    """

    runtime: str
    runtime_digest: str
    plugin_digest: str
    swipl_version: str


# am[implements a-integrate-deontic-support-trees-1019@508ecf]
@dataclass(frozen=True, slots=True)
class DeonticSupport:
    """Selected support attribution from dl-explain, not an exhaustive defeat proof.

    A fact or rule names its library label. A rule holds ordered premises. A cycle
    stops recursion; no-proof means no positive support, not a proof of negation.
    """

    literal: DeonticLiteral
    kind: Literal["fact", "rule", "cycle", "no-proof"]
    label: str | None = None
    premises: tuple[DeonticSupport, ...] = ()

    # Time and space: linear in the number of nodes in this support tree.
    # am[implements a-integrate-deontic-support-trees-1019@508ecf]
    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"kind": self.kind, "literal": self.literal.render()}
        if self.label is not None:
            result["label"] = self.label
        if self.kind == "rule":
            result["premises"] = [premise.to_dict() for premise in self.premises]
        return result


# am[implements a-rel-deontic-run-1016@be58d5] am[implements a-integrate-deontic-support-trees-1019@508ecf]
@dataclass(frozen=True, slots=True)
class DeonticRun:
    """One review: conclusions and dilemmas deduplicated and sorted, so equal theories on an
    equal engine answer equal conclusions, dilemmas and rules. `inferences` is what this review
    alone spent, charged to the caller's RunBudget beside its other stages."""

    conclusions: tuple[DeonticConclusion, ...]
    dilemmas: tuple[DeonticLiteral, ...]
    rules: int
    inferences: int
    engine: DeonticEngine
    support: tuple[DeonticSupport, ...]

    def rendered_conclusions(self) -> str:
        return f"({' '.join(conclusion.render() for conclusion in self.conclusions)})"


# Time: one bounded theory run plus support extraction and a parse linear in its output size,
# after the process's one preparation. Extraction is charged with the theory run.
# am[implements a-rt-pymetta-deontic-1016@61a4b6] am[implements a-rel-deontic-run-1016@be58d5]
# am[implements a-rt-run-budget-1016@e046b0] am[rests-on c-rt-speculate-discards-review-writes-1016@5c4db0]
# am[rests-on c-rt-atomic-conflicts-deontic-1016@dcc74b] am[rests-on c-rt-inprocess-review-expression-1016@8ee6dd]
# am[implements a-rt-rbr-read-before-engine-1018@b0a647] am[rests-on c-rt-boot-inside-deadline-1018@e9a118]
# am[implements a-rt-det-warmup-1018@c86a73]
def run_deontic_theory(theory: str, *, budget: RunBudget) -> DeonticRun:
    """Review one theory on the process's engine under what is left of `budget`, charging the
    review's inferences to it.

    Raises InferenceBudgetExceeded or ReviewTimeout, naming the whole bound and the total spend,
    when a bound stops the review or was used up before it; DeonticOutputError when the engine's
    answer is not a review of this theory, including one that ingested no rules, or ingested rules
    and concluded nothing; MettaEngineError when lib_deontic fails on it; and
    DependencyUnavailableError when pymetta or the package's deontic library is missing.
    """

    if not isinstance(theory, str):
        raise InvalidInputError("A deontic theory must be text.")
    # Read before taking the engine, whose first boot nothing can interrupt, so a request whose
    # bounds are used up never boots it; every wait for the engine ends at the budget's deadline.
    budget.remaining()
    with _theory_file(theory) as path:
        # The first review of a process loads lib_deontic inside its own deadline, holding the engine
        # alone; a later review takes no hold before its share (c-rt-kernel-per-call-exclusive-1018).
        initialize_once(DEONTIC_SETUP, partial(_load_deontic, budget=budget), budget=budget)
        identity = cast(DeonticEngine, _IDENTITY)
        # lib_deontic loads holding the engine alone; a review writes its theory spaces only inside
        # its own speculation, so it shares the engine with other reviews and evaluations on its own
        # pool worker (a-rt-cc-rw-pool-1018).
        answers, used = shared_evaluation(
            partial(_review, path=path, budget=budget, identity=identity, subject="the theory"), budget=budget
        )
    return _read_answers(answers, used, _SWIPL_FLAG, identity)


# am[implements a-rt-pymetta-deontic-1016@61a4b6] am[implements a-rt-bounded-preparation-1016@e7eb12]
# am[implements a-rt-det-warmup-1018@c86a73]
def prepare_deontic_engine(*, budget: RunBudget | None = None) -> DeonticEngine:
    """Register the package's deontic library as library `deontic` and import lib_deontic into
    the process's engine, then review WARM_UP_THEORY once inside speculation, once per process,
    and answer the identity of what was loaded. Neither is charged to any review.

    Inside a request, pass the request's budget: the load and the warm-up then run inside its
    deadline, and a deadline that stops either raises ReviewTimeout and leaves the preparation to
    the next call, which runs the warm-up again from the start. Without one it is the host's
    startup load, outside any request and bounded by nothing. run_deontic_theory calls it with the
    review's own budget, and a call after the first preparation does nothing. Raises
    MettaEngineError or DeonticOutputError when lib_deontic fails on the warm-up or answers it
    other than with a review, leaving the process unprepared.
    """

    initialize_once(DEONTIC_SETUP, partial(_load_deontic, budget=budget), budget=budget)
    return cast(DeonticEngine, _IDENTITY)


# The identity is taken from what is imported, at import: the plugin digest is the loader's, read
# on each side of lib_deontic's import, and the SWI version is the bundled engine's own flag.
# The identity is published only once the warm-up review read back as a review, so a preparation
# the warm-up stopped or refused is attempted again whole, its import answering the recorded digest.
# Time: two passes over the plugin, about 1 MB each, one import of lib_deontic, one read of RECORD
# and one review of WARM_UP_THEORY.
# am[implements a-rt-pymetta-deontic-1016@61a4b6] am[rests-on c-rt-pymetta-bundled-swi-1016@5fbd5c]
# am[implements a-rt-bounded-preparation-1016@e7eb12] am[rests-on c-rt-stopped-import-retry-safe-1016@cba696]
# am[implements a-rt-loaded-identity-1016@e4ffa3] am[implements a-rt-det-warmup-1018@c86a73]
def _load_deontic(engine: Any, *, budget: RunBudget | None) -> None:
    global _IDENTITY, _SWIPL_FLAG
    engine_identity = pymetta_identity(engine)
    register_metta_library(DEONTIC_LIBRARY.name, _deontic_library(), budget=budget)
    plugin_digest = load_metta_module(engine, DEONTIC_LIBRARY, budget=budget)
    flag = int(engine.runtime.once("current_prolog_flag(version, Version)")["Version"])
    identity = DeonticEngine(
        runtime=engine_identity.runtime,
        runtime_digest=engine_identity.runtime_digest,
        plugin_digest=plugin_digest,
        swipl_version=engine_identity.swipl_version,
    )
    # A request's deadline bounds the warm-up and none of its inferences are charged
    # (c-rel-one-deadline-1016), as with the import above.
    warm_up_budget = None if budget is None else budget.deadline_only()
    with _theory_file(WARM_UP_THEORY) as path:
        answers, used = _review(engine, path=path, budget=warm_up_budget, identity=identity, subject="its warm-up theory")
    _read_answers(answers, used, flag, identity)
    _SWIPL_FLAG, _IDENTITY = flag, identity


# Speculation discards a review's writes and compilation, so reviews are isolated by
# construction; engine.atomic() cannot be used, since its commit refuses lib_deontic's retirement.
# A review is bounded by `budget` and charged to it; the host's startup warm-up has no budget and
# runs bounded by nothing, its inferences only counted.
# lib_deontic's reset sets SWI global variables (deontic_library/src/deontic/platform/reason.pl),
# which each thread holds its own of, and a thread's first reset spent about 14 inferences more than
# a later one, the first under a time bound in a process 1 more; so a thread resets lib_deontic once
# before its first charged review, under that review's deadline and charged to no review.
# am[implements a-rt-pymetta-deontic-1016@61a4b6] am[rests-on c-rt-speculate-discards-review-writes-1016@5c4db0]
# am[rests-on c-rt-atomic-conflicts-deontic-1016@dcc74b] am[implements a-rt-det-warmup-1018@c86a73]
# am[implements a-rt-det-deontic-thread-reset-1019@3c05d5] am[rests-on c-rt-det-cheap-per-thread-exact-1019@dd8218]
# am[implements a-integrate-pymetta-public-errors-1019@05202a]
def _review(
    engine: Any, *, path: Path, budget: RunBudget | None, identity: DeonticEngine, subject: str
) -> tuple[list[list[Any]], int]:
    from metta.errors import MettaError  # noqa: PLC0415 (pymetta is imported only once an engine exists)

    try:
        with engine.speculate():
            if budget is None:
                with engine.stats() as spent:
                    answers = engine.run(REVIEW_SOURCE, path=str(path))
                return answers, spent.inferences
            if not getattr(_RESET, "done", False):
                run_bounded(engine, "!(dl-reset)", budget=budget.deadline_only())
                _RESET.done = True
            return run_bounded(engine, REVIEW_SOURCE, budget=budget, path=str(path))
    except MettaError as error:
        raise MettaEngineError(
            f"lib_deontic failed on {subject}: {error}",
            details={"engine": identity.runtime, "error": type(error).__name__},
        ) from error


# A review's answer, `(Conclusions Dilemmas Rules Support)` once, read as the payload read_review_payload
# checks, with the inferences the review spent and the SWI-Prolog version flag it ran on.
# am[implements a-rel-deontic-run-1016@be58d5] am[implements a-rt-det-warmup-1018@c86a73]
# am[implements a-integrate-deontic-support-trees-1019@508ecf]
def _read_answers(answers: list[list[Any]], used: int, flag: int, identity: DeonticEngine) -> DeonticRun:
    from metta import Expression  # noqa: PLC0415 (metta_engine has already imported it)

    if len(answers) != 1 or len(answers[0]) != 1:
        raise DeonticOutputError(
            "The review answered other than one result.",
            details={"answers": [[str(atom) for atom in group] for group in answers]},
        )
    [[review]] = answers
    if not isinstance(review, Expression) or len(review.children) != 4:
        raise DeonticOutputError(
            "The review is not (Conclusions Dilemmas Rules Support).",
            details={"answer": str(review)},
        )
    conclusions, dilemmas, rules, support = (str(part) for part in review.children)
    codec = SexprCodec()
    payload = codec.parse(f"(complete {used} {flag} {rules} {conclusions} {dilemmas} {support})")
    return read_review_payload(payload, codec, identity)


# The theory file a review reads, removed when the review is done with it, however it ends.
# am[implements a-rt-pymetta-deontic-1016@61a4b6]
@contextmanager
def _theory_file(theory: str) -> Iterator[Path]:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".metta", prefix=".goalchainer-deontic-", encoding="utf-8", delete=False
    ) as handle:
        handle.write(theory)
        path = Path(handle.name)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


# am[implements a-rel-deontic-run-1016@be58d5] am[implements a-integrate-deontic-support-trees-1019@508ecf]
def read_review_payload(payload: Any, codec: Any, engine: DeonticEngine) -> DeonticRun:
    """Read `(complete Used Version Rules Conclusions Dilemmas Support)` into a run, failing closed on any
    other shape.

    The SWI-Prolog version the review reported must be the one `engine` names, so a run never
    carries the identity of an engine it did not run on.
    """

    if not isinstance(payload, list) or not payload:
        raise DeonticOutputError("The deontic review payload is not an expression.")
    head = symbol_text(payload[0], codec, DeonticOutputError)
    if head != "complete" or len(payload) != 7:
        raise DeonticOutputError(
            "The deontic review payload has the wrong shape.",
            details={"payload": codec.emit(payload)},
        )
    used, version, rules = (_integer(item, codec) for item in payload[1:4])
    reported = _version_text(version)
    if reported != engine.swipl_version:
        raise DeonticOutputError(
            "The deontic review ran on a different SWI-Prolog than the engine identity names.",
            details={"reported": reported, "identity": engine.swipl_version},
        )
    conclusions = tuple(sorted({_conclusion(item, codec) for item in _items(payload[4])}))
    dilemmas = tuple(sorted({_literal(item, codec) for item in _items(payload[5])}))
    # A theory the engine cannot see answers no rules and no conclusions, which reads exactly like
    # a theory with nothing to say; both are refused rather than returned as an empty review.
    if rules == 0:
        raise DeonticOutputError("lib_deontic ingested no rules from the theory.")
    if not conclusions:
        raise DeonticOutputError(
            f"lib_deontic ingested {rules} rules and drew no conclusion.",
            details={"rules": rules},
        )
    support = tuple(sorted((_support(item, codec) for item in _items(payload[6])), key=lambda s: s.literal))
    expected = {c.literal for c in conclusions} | set(dilemmas)
    if len(support) != len(expected) or {s.literal for s in support} != expected:
        raise DeonticOutputError("Support must name every conclusion or dilemma literal exactly once.")
    return DeonticRun(
        conclusions=conclusions,
        dilemmas=dilemmas,
        rules=rules,
        inferences=used,
        engine=engine,
        support=support,
    )


# Time and space: linear in the number of nodes in the library's support tree.
# am[implements a-integrate-deontic-support-trees-1019@508ecf]
def _support(atom: Any, codec: Any) -> DeonticSupport:
    if isinstance(atom, list) and len(atom) in (2, 3):
        tag = symbol_text(atom[0], codec, DeonticOutputError)
        literal = _literal(atom[1], codec)
        if len(atom) == 2 and tag in ("cycle", "no-proof"):
            return DeonticSupport(literal, cast(Literal["cycle", "no-proof"], tag))
        if tag == "proof" and len(atom) == 3 and isinstance(atom[2], list):
            evidence = atom[2]
            if len(evidence) in (2, 3):
                kind = symbol_text(evidence[0], codec, DeonticOutputError)
                label = _term(evidence[1], codec)
                if kind == "fact" and len(evidence) == 2:
                    return DeonticSupport(literal, "fact", label)
                if kind == "rule" and len(evidence) == 3:
                    return DeonticSupport(literal, "rule", label,
                                          tuple(_support(child, codec) for child in _items(evidence[2])))
    raise DeonticOutputError(f"Not a deontic support tree: {codec.emit(atom)}")


# am[implements a-rt-typed-deontic-api-1016@871afb]
def _items(atom: Any) -> Sequence[Any]:
    if not isinstance(atom, list):
        raise DeonticOutputError("A deontic review collection is not an expression.")
    return atom


# am[implements a-rt-typed-deontic-api-1016@871afb]
def _integer(atom: Any, codec: Any) -> int:
    text = symbol_text(atom, codec, DeonticOutputError)
    if not text.lstrip("-").isdigit():
        raise DeonticOutputError(f"Expected an integer in the deontic review, found {text}.")
    return int(text)


# am[implements a-rt-typed-deontic-api-1016@871afb]
def _conclusion(atom: Any, codec: Any) -> DeonticConclusion:
    if not isinstance(atom, list) or len(atom) != 2:
        raise DeonticOutputError(f"A conclusion is not (tag literal): {codec.emit(atom)}")
    return DeonticConclusion(
        tag=symbol_text(atom[0], codec, DeonticOutputError),
        literal=_literal(atom[1], codec),
    )


# am[implements a-rt-typed-deontic-api-1016@871afb]
def _literal(atom: Any, codec: Any) -> DeonticLiteral:
    if (
        not isinstance(atom, list)
        or len(atom) != 6
        or not isinstance(atom[0], codec.Symbol)
        or atom[0].text != "lit"
        or not isinstance(atom[5], list)
    ):
        raise DeonticOutputError(f"Not a six-slot literal: {codec.emit(atom)}")
    sign, mode, temporal, functor = (_term(item, codec) for item in atom[1:5])
    return DeonticLiteral(
        sign=sign,
        mode=mode,
        temporal=temporal,
        functor=functor,
        args=tuple(_term(item, codec) for item in atom[5]),
    )


# A slot or argument as MeTTa text: a symbol by its name, a string or expression as emitted, so
# the symbol x and the string "x" stay distinct.
# am[implements a-rt-typed-deontic-api-1016@871afb]
def _term(atom: Any, codec: Any) -> str:
    if isinstance(atom, codec.Symbol):
        return atom.text
    return codec.emit(atom)


# am[implements a-rt-typed-deontic-api-1016@871afb] am[implements a-rt-incorporate-deontic-1016@6ea255]
def _deontic_library() -> Path:
    if not (DEONTIC_DIRECTORY / "lib_deontic.metta").is_file():
        raise DependencyUnavailableError(
            f"GoalChainer's deontic library is missing from its package at {DEONTIC_DIRECTORY}; "
            "reinstall GoalChainer.",
            details={"dependency": "deontic library", "path": str(DEONTIC_DIRECTORY)},
        )
    return DEONTIC_DIRECTORY


# SWI's version flag is MAJOR * 10000 + MINOR * 100 + PATCH, so 100114 is 10.1.14.
# am[implements a-rel-deontic-run-1016@be58d5]
def _version_text(flag: int) -> str:
    return f"{flag // 10000}.{flag // 100 % 100}.{flag % 100}"

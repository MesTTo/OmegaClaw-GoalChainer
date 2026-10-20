"""Purpose: read a MeTTa domain file into the records of `domains.model`, its optional reading and bigraph sections through their own modules, validated as a decision problem for the relevance review.

A domain declares what exists: the candidate actions, the goals they can serve, the signals a
review packet reports on, the dimensions actions are graded on, and the authority rungs that cap
them. It then writes its norms as a plain defeasible deontic theory that `lib_deontic`
interprets unchanged.

Nothing about a particular review is decided here. The compiler turns each reading into a
`(given (signal X))` or `(given (not (signal X)))` fact, appends the theory verbatim, and runs it
once. That single run derives, together:

    (pd (lit pos F none do (ACTION)))                       the deontic status
    (pd (lit pos none none candidate (ACTION)))             whether its preconditions hold
    (pd (lit pos none none contributes (ACTION GOAL BAND))) what it does for each goal
    (pd (lit pos none none effect (ACTION DIM BAND EST)))   the typed predicted effects
    (pd (lit pos none none required (GOAL)))                which goals this review must serve

so the conditional part of a domain lives in the defeasible logic, where superiority,
contrary-to-duty chains and defeaters act on it, rather than in Python branching.
`ai-notes/deontic-theory-grammar.md` records the grammar as verified against the engine: a
literal takes any functor and arity, and a deontic target must be structured, so the theory
says `(may (do ?a))` and one schematic rule covers every declared action.

    (gc-domain "Task control")
    (gc-policy-version task-control-v1)
    (gc-authority advisory 1 "A recommendation delivered to a human or the scheduler.")
    (gc-action pause_recoverably "Pause recoverably" "..." (authority preauthorized))
    (gc-goal restore_service ops-team collective 0.9 "..." (priority-source human:owner))
    (gc-signal safe_point_reachable "a checkpoint-and-release point is reachable")
    (gc-dimension reversibility benefit "Difficulty and cost of returning to the prior state.")
    (gc-estimator-ceiling model-proposed advisory)

    (normally rPauseCand (signal safe_point_reachable) (candidate pause_recoverably))
    (normally rPausePermit (candidate ?a) (may (do ?a)))

The theory may use `given`, `always`, `normally`, `except` and `prefer`. The review computes
which readings each conclusion can depend on from these rules, so a form it cannot analyse, such
as an event-calculus or trust declaration, is rejected rather than silently left out of that
dependency closure.

Estimator classes and ordinal bands are fixed by the specification (section 8.2 of the goal
relevance governor paper), not by the domain; their one home is the shared vocabulary beside this
module, `domains/vocabulary.metta`, which this module reads on first use. What a domain
chooses is the highest authority rung each action may be applied at and the highest rung each
estimator class can license, which is why both are declarations and the file carries a policy
version.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import dataclass, replace
from functools import cache
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, Iterator

from ..errors import InvalidInputError, ProtocolError
from ..models import Goal
from ..runtime.budget import RunBudget
from ..runtime.evaluator import ModuleGroup, evaluate, plain_value
from ..sexpr.forms import TopLevelForm, top_level_forms
from ..sexpr.syntax import StringLiteral, Symbol, parse
from . import bigraph, needs, readings
from .forms import FormsUnreadable, file_text, parsed_forms
from .model import AuthorityTier, Dimension, Domain, DomainAction, DomainError, Pattern, Rule, Signal

DIMENSION_POLARITIES = frozenset({"benefit", "cost"})
GOAL_KINDS = frozenset({"individual", "collective"})

DECLARATIONS = frozenset(
    {
        "gc-domain",
        "gc-policy-version",
        "gc-authority",
        "gc-action",
        "gc-goal",
        "gc-signal",
        "gc-dimension",
        "gc-estimator-ceiling",
    }
)
# The optional sections' heads. Each section's own module reads the forms its heads declare, and
# imports forms.py and model.py, never this loader (c-rel-pj-loader-imports-section-readers-1018).
# am[implements a-rel-nd-sections-1018@c1f2c6] am[related a-rel-brs-section-1018@b63f59]
# am[rests-on c-rel-pj-loader-imports-section-readers-1018@4e1a4e]
SECTION_HEADS = readings.HEADS | bigraph.HEADS | needs.HEADS

RULE_KINDS = frozenset({"always", "normally", "except"})
THEORY_FORMS = RULE_KINDS | {"given", "prefer"}

# Wrappers that change a literal's sign, mode or role without changing what it is about.
# `(otherwise D1 D2 ...)` is a contrary-to-duty chain whose disjuncts are each a literal.
_CONNECTIVES = frozenset({"and", "not", "must", "may", "forbidden", "otherwise"})
_DEONTIC_WRAPPERS = frozenset({"must", "may", "forbidden"})

# The packaged domain files, inside the package and named by their path in it.
# am[implements a-rel-neutral-domain-1018@535314]
PACKAGED_DOMAIN_DIRECTORY = "domains/data"
# The shared vocabulary the relevance policy loads and this module reads as literal tables.
# am[implements a-rel-nd-vocabulary-down-1018@6e6c8d]
VOCABULARY_FILE = Path(__file__).resolve().with_name("vocabulary.metta")

# One module group checks every domain: the shared vocabulary, the shared fault-table reader, the
# core's tables and each section module's CHECKS, a section without its own tables contributing
# only facts (c-rel-dr-agrees-validation-runner-1018). A section with tables names their CHECKS
# module, the ENTRY the loader evaluates and the WARM_UP that compiles them, and the group runs the
# core's warm-up and each such section's once per process, outside any request's inferences.
# am[implements a-rel-nd-validation-runner-1018@f3f0b6] am[rests-on c-rel-dr-agrees-validation-runner-1018@d65e39]
# am[rests-on c-rel-ev-agrees-validation-runner-1018@898991] am[implements a-rel-nd-section-warm-ups-1018@df1a66]
CHECKS_FILE = Path(__file__).resolve().with_name("checks.metta")
FAULT_TABLES = Path(__file__).resolve().parents[1] / "policy" / "goalchainer_fault_tables.metta"
_SECTION_MODULES = (readings, bigraph, needs)
_TABLED_SECTIONS = tuple(module for module in _SECTION_MODULES if hasattr(module, "CHECKS"))
CHECKS_GROUP = ModuleGroup(
    "domain-checks",
    (VOCABULARY_FILE, FAULT_TABLES, CHECKS_FILE, *(module.CHECKS for module in _TABLED_SECTIONS)),
    warm_ups=("gc-domain-checks-warm-up", *(module.WARM_UP for module in _TABLED_SECTIONS)),
)


# A caller's path is resolved and its file read once through forms.file_text, so every way either
# can fail is a DomainError naming the path, worded as the procedure library's loader words it;
# what reading the text raises, a budget or engine error included, passes through unchanged.
# am[implements a-rel-domain-1016@6f8fc8] am[implements a-integrate-domain-file-failures-1018@359226]
# am[implements a-rel-file-text-normalizes-1018@2afe58]
def load_domain(path: str | Path, *, budget: RunBudget) -> Domain:
    """Read a domain file under the caller's budget, or raise `DomainError` saying what is wrong
    with it, whether its path cannot be resolved or the file is missing, a directory, unreadable
    or not UTF-8 text."""

    source, text = file_text(path, DomainError)
    return read_domain(text, str(source), budget=budget)


# am[implements a-rel-domain-1016@6f8fc8] am[implements a-rel-package-1016@bc5962]
# am[implements a-rel-neutral-domain-1018@535314]
def packaged_domain_names() -> tuple[str, ...]:
    """The domains shipped inside the package, the files of `domains/data/`, named as
    `packaged_domain` takes them."""

    return tuple(
        sorted(
            entry.name.removesuffix(".metta").replace("_", "-")
            for entry in _packaged_directory().iterdir()
            if entry.name.endswith(".metta")
        )
    )


# am[implements a-rel-neutral-domain-1018@535314]
def _packaged_directory() -> Traversable:
    return resources.files("goal_chainer").joinpath(*PACKAGED_DOMAIN_DIRECTORY.split("/"))


# am[implements a-rel-domain-1016@6f8fc8] am[implements a-rel-package-1016@bc5962]
def packaged_domain(name: str, *, budget: RunBudget) -> Domain:
    """A domain shipped inside the package, such as `task-control`, read under the caller's
    budget."""

    if name not in packaged_domain_names():
        raise DomainError(
            f"no packaged domain named {name}; packaged: {', '.join(packaged_domain_names())}"
        )
    filename = name.replace("-", "_") + ".metta"
    return read_domain(
        (_packaged_directory() / filename).read_text(encoding="utf-8"),
        f"goal_chainer/{PACKAGED_DOMAIN_DIRECTORY}/{filename}",
        budget=budget,
    )


# The domain a caller selects, by a file path or a packaged name and never both: the one selection
# the domain request, the relevance CLI and the SNARS command and dispatch make, each wording a
# DomainError as its own error.
# am[implements a-ie-sr-select-domain-1018@577734] am[rests-on c-rel-agrees-selected-domain-1018@976dbd]
def selected_domain(*, path: str | Path | None = None, packaged: str | None = None, budget: RunBudget) -> Domain:
    """The domain read from the file at `path` or shipped as `packaged`, exactly one of them, under
    the caller's budget; `DomainError` for a selection naming neither or both, or for a domain
    that cannot be read."""

    if (path is None) == (packaged is None):
        raise DomainError("select a domain by exactly one of a file path or a packaged name")
    return load_domain(path, budget=budget) if path is not None else packaged_domain(packaged, budget=budget)


# am[implements a-rel-domain-1016@6f8fc8] am[addresses i-rel-deadsignal-1016@c0cf3b]
# am[implements a-rel-nd-reading-section-1018@98f298] am[implements a-rel-nd-sections-1018@c1f2c6]
# am[implements a-rel-nd-unread-signals-1018@f57790] am[implements a-rel-nd-review-digest-scope-1018@96d474]
def read_domain(text: str, source: str, *, budget: RunBudget) -> Domain:
    """Parse and validate domain text under the caller's budget; `source` names it in every
    error, and every fault the relational checks find is listed in one DomainError. A declared
    signal no rule body reads is no fault: the domain lists it in unread_signals. The digest
    covers what the review reads: the core's forms, the signals the sections declare and every
    form of the needs section."""

    title = ""
    policy_version = ""
    actions: list[DomainAction] = []
    goals: list[Goal] = []
    signals: list[Signal] = []
    dimensions: list[Dimension] = []
    authorities: list[AuthorityTier] = []
    ceilings: list[tuple[str, str]] = []
    theory: list[str] = []
    theory_forms: list[Any] = []
    rendered: list[str] = []
    reading_forms: list[tuple[TopLevelForm, Any]] = []
    bigraph_forms: list[tuple[TopLevelForm, Any]] = []
    need_forms: list[tuple[TopLevelForm, Any]] = []
    need_values: list[Any] = []

    for form, atom, value in _forms(text, source, budget=budget):
        head = (_name(value[0]) if value else None) or ""
        if head in readings.HEADS:
            reading_forms.append((form, atom))
            continue
        if head in bigraph.HEADS:
            bigraph_forms.append((form, atom))
            continue
        if head in needs.HEADS:
            need_forms.append((form, atom))
            need_values.append(value)
            continue
        rendered.append(_render(value))
        if head not in DECLARATIONS:
            # A mistyped declaration must not slide silently into the theory,
            # where it would parse as an unrelated fact and never fire.
            if head.startswith("gc-"):
                raise DomainError(
                    f"{source}: unknown declaration {head}; "
                    f"expected one of {', '.join(sorted(DECLARATIONS | SECTION_HEADS))}"
                )
            theory.append(form.text)
            theory_forms.append(value)
            continue
        if head == "gc-domain":
            title = _one_string(value, "gc-domain", source)
        elif head == "gc-policy-version":
            policy_version = _one_atom(value, "gc-policy-version", source)
        elif head == "gc-authority":
            authorities.append(_authority(value, source))
        elif head == "gc-action":
            actions.append(_action(value, source))
        elif head == "gc-goal":
            goals.append(_goal(value, source))
        elif head == "gc-signal":
            signals.append(_signal(value, source))
        elif head == "gc-dimension":
            dimensions.append(_dimension(value, source))
        else:
            ceilings.append(_estimator_ceiling(value, source))

    # Each reading proposition declares one of the domain's signals, after the gc-signal ones, so a
    # domain names a proposition once, and the two share one id namespace: the reading section's
    # facts declare its propositions, the core's facts the gc-signal ones.
    declaration = _reading_section(reading_forms, source) if reading_forms else None
    section = bigraph.read_section(bigraph_forms, source) if bigraph_forms else None
    motivation = needs.read_section(need_forms, source) if need_forms else None
    rules, facts, preferences = _read_theory(theory_forms, source)
    core_facts = _core_facts(actions, goals, signals, dimensions, authorities, ceilings, theory_forms, rules, preferences)
    if declaration is not None:
        signals.extend(Signal(id=proposition.id, description=proposition.statement)
                       for proposition in declaration.propositions)
        rendered.extend(f"(gc-section-signal {_render(proposition.id)} {_render(proposition.statement)})"
                        for proposition in declaration.propositions)

    theory_text = "\n".join(theory).strip() + "\n"
    # The review reads every need and expectation it ranks by, so each one's form is digested whole,
    # in its canonical rendering, after the core's forms (a-v2m-need-forms-1019).
    # am[implements a-v2m-need-forms-1019@6ee59c] am[related a-rel-nd-review-digest-scope-1018@96d474]
    rendered.extend(_render(value) for value in need_values)
    # The review is the one reader of the digest (c-rel-domain-digest-review-only-1018), so it hashes
    # the core's forms and each signal a section declares, whole as a core signal is, its id and its
    # description, and no other section text: editing a bigraph form or a reading question leaves
    # stored reviews fresh.
    # am[implements a-rel-nd-review-digest-scope-1018@96d474] am[addresses i-rel-digest-covers-unread-sections-1018@975b71]
    domain = Domain(
        title=title or Path(source).stem,
        policy_version=policy_version,
        source=source,
        digest="sha256:" + hashlib.sha256("\n".join(rendered).encode("utf-8")).hexdigest(),
        actions=tuple(actions),
        goals=tuple(goals),
        signals=tuple(signals),
        dimensions=tuple(dimensions),
        authorities=tuple(authorities),
        estimator_ceilings=tuple(ceilings),
        theory=theory_text,
        rules=rules,
        facts=facts,
        unestimated_dimensions=_unestimated_dimensions(dimensions, rules, facts),
        readings=declaration,
        bigraph=section,
        motivation=motivation,
    )
    _validate(domain)
    section_facts = tuple(
        fact
        for module, record in ((readings, declaration), (bigraph, section), (needs, motivation))
        if record is not None and hasattr(module, "FACTS")
        for fact in module.FACTS(record)
    )
    checked = (*core_facts, *section_facts)
    _refuse_faults(checked, source, budget)
    # With the checks passed, every binding names a declared control with entities, each described, so
    # each binding is given its control's entities; the domain digest, the review's alone, stays as it was
    # (c-bnd-domain-digest-review-only-1019).
    # am[implements a-bnd-candidates-1019@61b2d4] am[rests-on c-bnd-domain-digest-review-only-1019@b93cf2]
    if declaration is not None and declaration.bindings:
        entities = section.entities if section is not None else ()
        domain = replace(domain, readings=readings.with_entities(
            declaration, ((entity.id, entity.control, entity.description) for entity in entities)))
    return replace(domain, unread_signals=_unread_signals(checked, source, budget))


# The reading section's reader refuses with its own InvalidInputError, as a standalone declaration
# file does; inside a domain file every fault is a DomainError naming the file.
# am[implements a-rel-nd-reading-section-1018@98f298] am[rests-on c-rel-agrees-dr-pj-api-1018@3ef2d8]
def _reading_section(forms: list[tuple[TopLevelForm, Any]], source: str) -> readings.ReadingDeclaration:
    try:
        return readings.read_section(forms, Path(source))
    except InvalidInputError as error:
        raise DomainError(f"{source}: {error}") from error


# am[implements a-rel-domain-1016@6f8fc8] am[implements a-rel-finite-number-1017@924176]
def _authority(form: tuple, source: str) -> AuthorityTier:
    _arity(form, 4, '(gc-authority ID rank "description")', source)
    rank = _number(form[2], f"rank of authority {_render(form[1])}", source)
    if rank != int(rank):
        raise DomainError(f"{source}: authority rank must be a whole number: {_render(form[1])}")
    return AuthorityTier(_atom(form[1], "authority id", source), int(rank), _text(form[3]))


# am[implements a-rel-domain-1016@6f8fc8]
def _action(form: tuple, source: str) -> DomainAction:
    _arity(form, 5, '(gc-action ID "label" "description" (authority TIER))', source)
    authority = form[4]
    if not isinstance(authority, tuple) or len(authority) != 2 or _name(authority[0]) != "authority":
        raise DomainError(
            f"{source}: gc-action {_render(form[1])} needs an (authority TIER) clause, got {_render(authority)}"
        )
    return DomainAction(
        id=_atom(form[1], "action id", source),
        label=_text(form[2]),
        description=_text(form[3]),
        authority=_atom(authority[1], "authority tier", source),
    )


# am[implements a-rel-domain-1016@6f8fc8]
# am[implements a-rel-finite-priority-1017@262e4d]
def _goal(form: tuple, source: str) -> Goal:
    """A goal's vocabulary.

    Whether a review requires the goal is derived, not declared: the theory says
    `(required G)`, unconditionally or under a signal, so requiredness has the same single
    source as everything else conditional.

    The priority source is mandatory because a priority is human- or policy-declared
    importance, and a derived score that loses who declared it is the priority-laundering
    failure the paper names. A priority that is not a finite non-negative number is refused
    here, as Goal refuses it.
    """

    _arity(
        form,
        7,
        '(gc-goal ID owner individual|collective priority "statement" (priority-source SRC))',
        source,
    )
    _, goal_id, owner, kind, priority, statement, provenance = form
    if _name(kind) not in GOAL_KINDS:
        raise DomainError(f"{source}: goal kind must be individual or collective: {_render(goal_id)}")
    if (
        not isinstance(provenance, tuple)
        or len(provenance) != 2
        or _name(provenance[0]) != "priority-source"
    ):
        raise DomainError(
            f"{source}: gc-goal {_render(goal_id)} needs a (priority-source SRC) clause, "
            f"got {_render(provenance)}"
        )
    try:
        return Goal(
            id=_atom(goal_id, "goal id", source),
            owner=_atom(owner, "goal owner", source),
            statement=_text(statement),
            weight=_number(priority, f"priority of goal {_render(goal_id)}", source),
            kind=_name(kind),  # type: ignore[arg-type]
            priority_source=_atom(provenance[1], "priority source", source),
        )
    except DomainError:
        raise
    except ValueError as error:
        raise DomainError(f"{source}: {error}") from error


# am[implements a-rel-domain-1016@6f8fc8]
def _signal(form: tuple, source: str) -> Signal:
    _arity(form, 3, '(gc-signal ID "description")', source)
    return Signal(id=_atom(form[1], "signal id", source), description=_text(form[2]))


# am[implements a-rel-domain-1016@6f8fc8]
def _dimension(form: tuple, source: str) -> Dimension:
    _arity(form, 4, '(gc-dimension ID benefit|cost "description")', source)
    polarity = _name(form[2])
    if polarity not in DIMENSION_POLARITIES:
        raise DomainError(
            f"{source}: dimension polarity must be benefit or cost: {_render(form[1])} has {_render(form[2])}"
        )
    return Dimension(
        _atom(form[1], "dimension id", source),
        polarity,  # type: ignore[arg-type]
        _text(form[3]),
    )


# am[implements a-rel-domain-1016@6f8fc8]
def _estimator_ceiling(form: tuple, source: str) -> tuple[str, str]:
    _arity(form, 3, "(gc-estimator-ceiling ESTIMATOR AUTHORITY)", source)
    # Whether the class is one of the vocabulary's is a row of the core's tables.
    return _atom(form[1], "estimator class", source), _atom(form[2], "authority tier", source)


# am[implements a-rel-domain-1016@6f8fc8] am[rests-on c-rel-cone-sound-1016@092cec]
def _read_theory(
    forms: list[Any], source: str
) -> tuple[tuple[Rule, ...], tuple[Pattern, ...], tuple[tuple[str, ...], ...]]:
    """Every rule and fact of the theory, as the patterns it reads and concludes, and the labels
    each prefer form names.

    A rule is `(KIND [Label] Body Head)`; the engine detects the optional label by arity, and
    so does this. Whether the labels are unique and the preferences name them is a relational
    check, a row of the core's tables.
    """

    rules: list[Rule] = []
    facts: list[Pattern] = []
    preferences: list[tuple[str, ...]] = []
    for form in forms:
        head = (_name(form[0]) if form else None) or ""
        if head not in THEORY_FORMS:
            raise DomainError(
                f"{source}: the theory may use {', '.join(sorted(THEORY_FORMS))}; "
                f"{_render(form)[:120]} is not a form the review can trace dependencies through"
            )
        if head == "given":
            _arity(form, 2, "(given LITERAL)", source)
            facts.extend(_literals(form[1]))
        elif head == "prefer":
            preferences.append(tuple(_render(label) for label in form[1:]))
        elif len(form) == 4:
            rules.append(Rule(_atom(form[1], "rule label", source), head, *_body_and_heads(form[2], form[3])))
        elif len(form) == 3:
            rules.append(Rule(None, head, *_body_and_heads(form[1], form[2])))
        else:
            raise DomainError(f"{source}: ({head} [Label] Body Head) got {_render(form)[:120]}")

    return tuple(rules), tuple(facts), tuple(preferences)


# am[implements a-rel-domain-1016@6f8fc8]
def _body_and_heads(body, head) -> tuple[tuple[Pattern, ...], tuple[Pattern, ...], tuple[Pattern, ...]]:
    return tuple(_literals(body)), tuple(_literals(head)), tuple(_norms(head))


# am[implements a-rel-domain-1016@6f8fc8]
def _norms(term, deontic: bool = False) -> Iterator[Pattern]:
    """The literals of a head that sit under must, may or forbidden, at any depth."""

    head = _name(term[0]) if isinstance(term, tuple) and term else None
    if head is None:
        if deontic:
            yield from _literals(term)
        return
    if head in _DEONTIC_WRAPPERS:
        for item in term[1:]:
            yield from _norms(item, True)
    elif head in _CONNECTIVES:
        for item in term[1:]:
            yield from _norms(item, deontic)
    elif deontic:
        yield from _literals(term)


# am[implements a-rel-domain-1016@6f8fc8]
def _literals(term) -> Iterator[Pattern]:
    """The literals inside a body or head, with connectives and deontic wrappers removed."""

    if not isinstance(term, tuple):
        yield Pattern(_render(term), ())
        return
    if not term:
        return
    head = term[0]
    if _name(head) in _CONNECTIVES:
        for item in term[1:]:
            yield from _literals(item)
        return
    yield Pattern(_render(head), tuple(_render(arg) for arg in term[1:]))


# am[implements a-rel-domain-1016@6f8fc8] am[addresses i-rel-unknown-neutral-1016@7e3679]
def _unestimated_dimensions(
    dimensions: list[Dimension], rules: tuple[Rule, ...], facts: tuple[Pattern, ...]
) -> tuple[str, ...]:
    """The declared dimensions no rule or fact can ever give an effect on.

    They are known unknowns: a review reports them as missing information for every candidate
    instead of letting them read as neutral.
    """

    concluded = [pattern for rule in rules for pattern in rule.heads] + list(facts)
    estimated = {
        pattern.args[1]
        for pattern in concluded
        if pattern.functor == "effect" and len(pattern.args) == 4
    }
    if any(name.startswith("?") for name in estimated):
        return ()
    return tuple(dimension.id for dimension in dimensions if dimension.id not in estimated)


# am[implements a-rel-domain-1016@6f8fc8]
def _arity(form: tuple, expected: int, shape: str, source: str) -> None:
    if len(form) != expected:
        raise DomainError(
            f"{source}: {shape} takes {expected - 1} arguments, got {len(form) - 1}: {_render(form)}"
        )


# am[implements a-rel-domain-1016@6f8fc8]
def _one_string(form: tuple, head: str, source: str) -> str:
    _arity(form, 2, f'({head} "text")', source)
    return _text(form[1])


# am[implements a-rel-domain-1016@6f8fc8]
def _one_atom(form: tuple, head: str, source: str) -> str:
    _arity(form, 2, f"({head} ID)", source)
    return _atom(form[1], head, source)


# A plain name is a symbol, never a string or a number.
# am[implements a-rel-domain-1016@6f8fc8] am[implements a-rel-nd-pymetta-atoms-1018@f047df]
def _atom(token, what: str, source: str) -> str:
    name = _name(token)
    if name is None:
        if isinstance(token, str):
            raise DomainError(f"{source}: {what} must be a plain name, not a string: {_render(token)}")
        raise DomainError(f"{source}: {what} must be a plain name, got {_render(token)}")
    return name


# A domain's numbers are finite. pymetta reads nan, inf and -inf as symbols, and Python's float
# reads them as numbers that are not finite, so a symbol spelling a number is read as float reads it:
# neither is a rank or a priority, and int() of one raises outside DomainError. float() raises
# OverflowError for an integer beyond its range, which has no finite float either and is named
# rather than written out (c-rel-num-loader-overflow-1018).
# am[implements a-rel-domain-1016@6f8fc8] am[implements a-rel-finite-number-1017@924176]
# am[addresses i-rel-nonfinite-number-1017@9d89c8] am[rests-on c-rel-nd-parse-boots-runtime-1018@bce664]
# am[implements a-integrate-relevance-numeric-boundaries-1018@4c2a7d]
def _number(token, what: str, source: str) -> float:
    if isinstance(token, (int, float)) and not isinstance(token, bool):
        try:
            value = float(token)
        except OverflowError:
            raise DomainError(f"{source}: {what} is not a finite number: an integer beyond the float range") from None
    else:
        name = _name(token)
        try:
            value = float(name) if name is not None else math.nan
        except ValueError:
            name = None
        if name is None:
            raise DomainError(f"{source}: {what} is not a number: {_render(token)}")
    if not math.isfinite(value):
        raise DomainError(f"{source}: {what} is not a finite number: {_render(token)}")
    return value


# A description or title: a string as pymetta read it, or any other value as written.
# am[implements a-rel-domain-1016@6f8fc8] am[implements a-rel-nd-pymetta-atoms-1018@f047df]
def _text(token) -> str:
    return token if isinstance(token, str) else _render(token)


# A symbol's name, None for any other value.
# am[implements a-rel-nd-pymetta-atoms-1018@f047df]
def _name(value: Any) -> str | None:
    from metta import Symbol  # noqa: PLC0415 (pymetta is imported once a form is parsed)

    return str(value) if isinstance(value, Symbol) else None


# A value written back as MeTTa reads it, one canonical spelling per value, so the digest and a
# literal's arguments do not depend on how a number or a string was spelled.
# am[implements a-rel-domain-1016@6f8fc8] am[implements a-rel-nd-pymetta-atoms-1018@f047df]
def _render(value: Any) -> str:
    if isinstance(value, tuple):
        return "(" + " ".join(_render(item) for item in value) + ")"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, float):
        return repr(value)
    return str(value)


# am[implements a-rel-domain-1016@6f8fc8]
def _validate(domain: Domain) -> None:
    source = domain.source
    if not domain.actions:
        raise DomainError(f"{source}: a domain needs at least one gc-action")
    if not domain.goals:
        raise DomainError(f"{source}: a domain needs at least one gc-goal")
    if not domain.policy_version:
        raise DomainError(
            f"{source}: a domain needs a (gc-policy-version ID); every verdict records "
            f"the policy version it was decided under"
        )
    if not domain.authorities:
        raise DomainError(f"{source}: a domain needs at least one gc-authority tier")

    declared_ceilings = [estimator for estimator, _ in domain.estimator_ceilings]
    missing_ceilings = [e for e in vocabulary().classes if e not in declared_ceilings]
    if missing_ceilings:
        raise DomainError(
            f"{source}: every estimator class needs a gc-estimator-ceiling, because the "
            f"policy gate conditions authority on the class; missing: "
            f"{', '.join(missing_ceilings)}"
        )


# The core's facts, every name a string, in declaration order: what each declaration declares, the
# tier each action names, each tier's rank, each ceiling, every term of the theory with its
# arguments, each rule label and preference, and the signals the rule bodies read. A gc-signal's
# declaration is the core's; a reading proposition's is its section's (c-rel-dr-agrees-validation-runner-1018).
# Time: one pass over the declarations and one walk of each theory form's terms.
# am[implements a-rel-nd-validation-runner-1018@f3f0b6] am[rests-on c-rel-nd-ids-symbols-classes-strings-1018@fef3a2]
def _core_facts(
    actions: list[DomainAction],
    goals: list[Goal],
    signals: list[Signal],
    dimensions: list[Dimension],
    authorities: list[AuthorityTier],
    ceilings: list[tuple[str, str]],
    theory_forms: list[Any],
    rules: tuple[Rule, ...],
    preferences: tuple[tuple[str, ...], ...],
) -> tuple[tuple, ...]:
    def argument(token: Any) -> str | tuple:
        if isinstance(token, tuple):
            return ("Term",)
        name = _name(token)
        if name is not None and name.startswith("?"):
            return ("Schematic", name[1:])
        return name if name is not None else _render(token)

    return (
        *(fact for action in actions for fact in (("Declared", "action", action.id), ("Tier", action.id, action.authority))),
        *(("Declared", "goal", goal.id) for goal in goals),
        *(("Declared", "signal", signal.id) for signal in signals),
        *(("Declared", "dimension", dimension.id) for dimension in dimensions),
        *(fact for tier in authorities for fact in (("Declared", "authority", tier.id), ("Rank", tier.id, _render(tier.rank)))),
        *(("Ceiling", estimator, tier) for estimator, tier in ceilings),
        *(("Literal", _name(term[0]), ("Args", *(argument(token) for token in term[1:])))
          for form in theory_forms for term in _terms(form) if term and _name(term[0]) is not None),
        *(("Label", rule.label) for rule in rules if rule.label is not None),
        *(("Prefer", ("Labels", *labels)) for labels in preferences),
        *(("ReadsSchematic",) if pattern.args[0].startswith("?") else ("Reads", pattern.args[0])
          for rule in rules for pattern in rule.body if pattern.functor == "signal" and len(pattern.args) == 1),
    )


# A fact as the MeTTa term the checks read: its head a symbol, each argument a string or a fact.
# am[implements a-rel-nd-validation-runner-1018@f3f0b6] am[related a-dr-readings-facts-1018@64445a]
def _fact_atom(fact: tuple) -> Any:
    from metta import S  # noqa: PLC0415 (pymetta, the pinned engine)

    return S[fact[0]](*(_fact_atom(argument) if isinstance(argument, tuple) else argument for argument in fact[1:]))


# A fault as one line: the fact that failed, then what the row says of it. A fact of a head the
# core reads is written in its own words, and any other fact, a section's or one of a shape the
# core does not read, as the term it is.
# am[implements a-rel-nd-validation-runner-1018@f3f0b6]
_FAULT_WORDS = {
    ("Declared", 2): "{0} {1}",
    ("Tier", 2): "action {0}'s authority {1}",
    ("Rank", 2): "authority {0}'s rank {1}",
    ("Ceiling", 2): "(gc-estimator-ceiling {0} {1})",
    ("Literal", 2): "the theory's ({0} {1})",
    ("Label", 1): "rule label {0}",
    ("Prefer", 1): "(prefer {0})",
}


# am[implements a-rel-nd-validation-runner-1018@f3f0b6]
def _fault_line(fact: Any, message: str) -> str:
    def word(part: Any) -> str:
        if isinstance(part, tuple):
            return " ".join(word(item) for item in part[1:])
        return part if isinstance(part, str) else (_name(part) or _render(part))

    parts = fact if isinstance(fact, tuple) else (fact,)
    head = parts[0] if isinstance(parts[0], str) else _name(parts[0])
    template = _FAULT_WORDS.get((head or "", len(parts) - 1))
    return f"{template.format(*(word(part) for part in parts[1:])) if template else _render(fact)} {message}"


# Every section's relational checks over the domain's facts, in one module group under the
# caller's budget: the core's table, then each section module's CHECKS behind its ENTRY. A Fault is
# a line of the one DomainError listing them all; a Defect is a mistake in the checks themselves.
# am[implements a-rel-nd-validation-runner-1018@f3f0b6] am[rests-on c-rel-nd-validation-needs-budget-1018@1989e6]
# am[rests-on c-rel-nd-checks-as-constraints-1018@704895]
def _refuse_faults(facts: tuple[tuple, ...], source: str, budget: RunBudget) -> None:
    entries = ("gc-domain-core-faults", *(module.ENTRY for module in _TABLED_SECTIONS))
    term = _fact_atom(("Domain", *facts))
    answers = [plain_value(evaluate(CHECKS_GROUP, entry, term, budget=budget)) for entry in entries]
    lines = []
    for answer in answers:
        for fault in answer:
            kind = _name(fault[0])
            if kind != "Fault":
                raise ProtocolError(
                    f"the domain checks answered {_render(fault)} for {source}, which is a mistake in the checks, "
                    f"not in the domain",
                    details={"source": source, "answer": _render(fault)},
                )
            lines.append(_fault_line(fault[2], str(fault[3])))
    if lines:
        listed = lines[0] if len(lines) == 1 else f"{len(lines)} faults:\n  " + "\n  ".join(lines)
        raise DomainError(f"{source}: {listed}", faults=lines)


# The signal table's failing subjects are the declared signals no rule body reads, each a
# (Declared "signal" ID) fact; any other answer is a mistake in the checks, as it is for a fault.
# am[implements a-rel-nd-unread-signals-1018@f57790]
def _unread_signals(facts: tuple[tuple, ...], source: str, budget: RunBudget) -> tuple[str, ...]:
    answer = plain_value(evaluate(CHECKS_GROUP, "gc-domain-unread-signals", _fact_atom(("Domain", *facts)), budget=budget))
    unread = []
    for fault in answer:
        if _name(fault[0]) != "Fault" or not isinstance(fault[2], tuple) or len(fault[2]) != 3:
            raise ProtocolError(
                f"the domain checks answered {_render(fault)} for {source}'s unread signals, which is a "
                f"mistake in the checks, not in the domain",
                details={"source": source, "answer": _render(fault)},
            )
        unread.append(str(fault[2][2]))
    return tuple(sorted(unread))


# am[implements a-rel-domain-1016@6f8fc8]
def _terms(form) -> Iterator[tuple]:
    """Every expression inside a form's value, the form itself included."""

    stack = [form]
    while stack:
        current = stack.pop()
        if not isinstance(current, tuple):
            continue
        yield current
        stack.extend(item for item in current if isinstance(item, tuple))


# A domain's forms, each with its parsed atom and that atom as plain values, or a DomainError at
# the line where the text stops being data, writes an integer too long to write or writes the symbol
# Error; a request's read waits for the engine only until its budget's deadline.
# am[implements a-rel-nd-pymetta-atoms-1018@f047df]
# am[implements a-integrate-runtime-wait-deadline-1018@a74406] am[implements a-ev-pk-error-name-refused-1018@ce3a7f]
# am[implements a-integrate-relevance-numeric-boundaries-1018@4c2a7d]
def _forms(text: str, source: str, *, budget: RunBudget | None) -> Iterator[tuple[TopLevelForm, Any, Any]]:
    try:
        parsed = parsed_forms(text, budget=budget)
    except FormsUnreadable as error:
        line = text.count("\n", 0, error.index) + 1
        raise DomainError(f"{source}:{line}: {error.problem}") from error
    for form, atom in parsed:
        value = plain_value(atom)
        line = text.count("\n", 0, form.index) + 1
        _refuse_unwritable_integer(value, source, line)
        _refuse_error_symbol(value, source, line)
        yield form, atom, value


# pymetta reads an integer literal of any length as an int, and the interpreter writes one of more
# digits than sys.get_int_max_str_digits() only by raising ValueError, so no digest, rendering or
# refusal could write a form holding one (c-rel-num-loader-unwritable-1018). Such a form is refused
# at its line, named by its head, before anything renders it, the Error check included.
# Time: one visit per expression and element of the form, and one str() per integer.
# am[implements a-integrate-relevance-numeric-boundaries-1018@4c2a7d] am[rests-on c-sn-overflow-and-digit-limits-1018@0e7f7d]
def _refuse_unwritable_integer(value: Any, source: str, line: int) -> None:
    for item in (value, *(item for term in _terms(value) for item in term)):
        if not isinstance(item, int):
            continue
        try:
            str(item)
        except ValueError:
            head = _name(value[0]) if isinstance(value, tuple) and value else None
            raise DomainError(
                f"{source}:{line}: {f'({head} ...)' if head else 'a form'} writes an integer of more than "
                f"{sys.get_int_max_str_digits()} digits, which the interpreter cannot write as text"
            ) from None


# Error is MeTTa's error constructor: a list whose first element is Error is an error value, which
# pymetta's list operations hand back unchanged, so the kernel's list of a world's nodes headed by
# an entity named Error answers that error, and plan refuses the world for faults that name nothing
# wrong. No form may write the symbol, as no plain name may be True or False, which pymetta reads
# as booleans; the string "Error" stays data and a longer symbol stays a name.
# Time: one visit per expression and element of the form.
# am[implements a-ev-pk-error-name-refused-1018@ce3a7f] am[rests-on c-ev-pk-error-symbol-poisons-lists-1018@8f8f6b]
# am[rests-on f2175393-f8b4-5334-be83-0667fb61c446@a18867]
def _refuse_error_symbol(value: Any, source: str, line: int) -> None:
    for term in _terms(value):
        if any(_name(item) == "Error" for item in term):
            raise DomainError(
                f"{source}:{line}: {_render(term)} writes the symbol Error, MeTTa's error constructor, which is no plain name"
            )


# The vocabulary every domain consumer shares, section 8.2: the estimator classes, each the name in
# one (Class NAME TIER) entry of the class table, and the ordinal bands worst to best. It is read on
# first use, never at import, without starting or waiting for the engine.
# am[implements a-rel-nd-vocabulary-down-1018@6e6c8d] am[implements a-integrate-vocab-pure-read-1019@745f98]
@dataclass(frozen=True)
class Vocabulary:
    classes: tuple[str, ...]
    bands: tuple[str, ...]


# am[implements a-rel-nd-vocabulary-down-1018@6e6c8d] am[implements a-integrate-derivability-review-1016@5a4239]
# Read literal data only; policy equations remain the engine's responsibility.
# Time: scan(N) + tokenize(N) + visit(A) + project(K), N source characters, A atoms, K table entries.
# Space: O(N + A + K) on the first call; cached calls take O(1) time and space.
# am[implements a-integrate-vocab-pure-read-1019@745f98] am[rests-on c-integrate-vocab-cost-1019@57bcb9]
@cache
def vocabulary() -> Vocabulary:
    """The shared vocabulary's literal tables, read once per process without pymetta."""

    source = f"goal_chainer/domains/{VOCABULARY_FILE.name}"
    tables = {}
    try:
        for form in top_level_forms(VOCABULARY_FILE.read_text(encoding="utf-8")):
            if form.directive:
                raise DomainError(f"{source}: the vocabulary must only declare forms")
            match parse(form.text):
                case [Symbol("="), [Symbol(name)], list() as values]:
                    tables[name] = values
    except ValueError as error:
        raise DomainError(f"{source}: cannot read the vocabulary: {error}") from error
    missing = [name for name in ("gc-estimator-class-table", "gc-bands") if name not in tables]
    if missing:
        raise DomainError(f"{source} defines no ({missing[0]})")
    classes, bands = tables["gc-estimator-class-table"], tables["gc-bands"]
    if any(not isinstance(entry, list) or len(entry) != 3 or entry[0] != Symbol("Class")
           or not isinstance(entry[1], StringLiteral) for entry in classes):
        raise DomainError(f'{source}: gc-estimator-class-table must contain (Class "NAME" TIER) entries')
    if any(not isinstance(band, StringLiteral) for band in bands):
        raise DomainError(f"{source}: gc-bands must contain string literals")
    return Vocabulary(
        classes=tuple(entry[1].value for entry in classes),
        bands=tuple(band.value for band in bands),
    )

"""Purpose: developer diagnostics of one MeTTa expression in a ModuleGroup's space, each run on the
process's engine held alone, inside the space's speculative scope, bounded by and charged to its
caller's RunBudget, and each answering a JSON-ready report: `profile` runs the expression under
pymetta's statistical profiler, `explain` answers the engine's plan for a match form, or its
declarations for an operation call, without running it, and `match` says which stage of a
conjunctive match leaves it without answers. pymetta's own Space.why and explain(analyze=True)
are not offered, because part of their engine work escapes both of the budget's bounds."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict
from typing import Any

from ..errors import InvalidInputError, MettaEngineError, safe_repr
from ..sexpr import syntax
from ..sexpr.forms import MettaTextError, top_level_forms
from .budget import RunBudget, bounded_call, caller_budget, run_bounded
from .engine import metta_engine, pymetta_identity
from .evaluator import ModuleGroup, plain_value, prepare

# What a match diagnostic finds, by the first stage that answers: the whole query, the patterns
# joined without the guard, then each pattern alone; the order and the wording follow pymetta's own
# explanation of an empty query (metta/_observe/diagnostics.py, explain_empty_query).
MATCHES = "matches"
GUARD_REJECTS = "guard-rejects-every-row"
PATTERNS_MATCH_NOTHING = "patterns-match-nothing"
NO_JOINT_BINDING = "no-joint-binding"


# A diagnostic takes MeTTa text from a developer, so each piece is checked to be exactly one
# parenthesized form, no directive, before it is spliced into the program the engine runs, and is
# read into its tree, all without the engine: the scanner sexpr.forms splits the text, string
# literals and comments included, and the reader sexpr.syntax refuses what it cannot read with
# ValueError and nesting past the interpreter's stack with RecursionError, each a typed refusal
# here before any engine work. The tree is what explain reads a form's head from.
# Time: two passes over the text and one recursive descent over the form's tree.
# am[implements a-dg-module-1019@7c4558]
def _form(text: object, role: str) -> tuple[str, syntax.Atom]:
    if not isinstance(text, str):
        raise InvalidInputError(f"A diagnostic's {role} must be MeTTa text.", details={role: safe_repr(text)})
    try:
        forms = list(top_level_forms(text))
    except MettaTextError as error:
        raise InvalidInputError(f"A diagnostic's {role} is not one MeTTa form: {error}.",
                                details={role: text}) from error
    if len(forms) != 1 or forms[0].directive:
        raise InvalidInputError(
            f"A diagnostic's {role} must be one parenthesized MeTTa form without !, not {len(forms)} "
            f"form{'' if len(forms) == 1 else 's'}{' with !' if forms and forms[0].directive else ''}.",
            details={role: text},
        )
    try:
        tree = syntax.parse(forms[0].text)
    except (ValueError, RecursionError) as error:
        raise InvalidInputError(f"A diagnostic's {role} cannot be read as a MeTTa form: "
                                f"{type(error).__name__}: {error}.", details={role: text}) from error
    return forms[0].text, tree


# Every diagnostic prepares its group as an evaluation does, then holds the engine alone: SWI's
# profiler belongs to one thread per process (c-dg-profiler-thread-owned-1019), and no evaluation
# then runs beside the diagnostic. The work runs inside the group space's speculative scope, which
# discards its engine writes and not a Python effect a py-call made, and an engine refusal is a
# MettaEngineError naming the diagnostic. A budget already used up is stopped by prepare before any
# engine work.
# Time: one prepare, the work, and one read of the engine's identity.
# am[implements a-dg-module-1019@7c4558] am[rests-on c-dg-profiler-thread-owned-1019@3efd60]
# am[rests-on c-integrate-pymetta-diagnostic-boundary-1019@480fde]
def _diagnose(diagnostic: str, group: ModuleGroup, budget: RunBudget,
              work: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:
    from metta.errors import MettaError  # noqa: PLC0415 (pymetta is imported only once an engine exists)

    budget = caller_budget(budget, f"The {diagnostic} diagnostic")
    if not isinstance(group, ModuleGroup):
        raise InvalidInputError(f"The {diagnostic} diagnostic runs in a ModuleGroup's space.",
                                details={"group": safe_repr(group)})
    identity = prepare(group, budget=budget)
    with metta_engine(budget) as engine:
        space = engine.space(group.space)
        try:
            with space.speculative():
                report = work(space)
        except MettaError as error:
            raise MettaEngineError(
                f"The engine refused the {diagnostic} diagnostic in module group {group.name}: {error}",
                details={"diagnostic": diagnostic, "group": group.name, "error": str(error)},
            ) from error
        engine_identity = pymetta_identity(engine)
    return {
        "diagnostic": diagnostic,
        "group": {"name": group.name, "space": group.space, "identity": identity},
        "engine": asdict(engine_identity),
        **report,
        "budget": {"inference_budget": budget.inference_budget, "timeout_seconds": budget.timeout_seconds,
                   "spent": budget.spent},
    }


# am[implements a-dg-module-1019@7c4558]
def _texts(groups: list[list[Any]]) -> list[list[str]]:
    return [[str(atom) for atom in group] for group in groups]


# A profile row's value as JSON reads it: the sampler's numbers and names stay themselves, and
# anything else is written as its text.
# am[implements a-dg-module-1019@7c4558]
def _plain(value: Any) -> Any:
    return value if value is None or isinstance(value, (int, float, str)) else str(value)


# The rows name their columns from the profile's own COLUMNS, so a column pymetta adds is reported
# without a change here.
# Time: one bounded run of the expression under the sampler, plus the top rows' copy.
# am[implements a-dg-module-1019@7c4558] am[rests-on c-dg-profile-bounded-1019@fc2967]
def profile(group: ModuleGroup, expression: str, *, top: int = 20, budget: RunBudget) -> dict[str, Any]:
    """Run `(EXPRESSION)` once in the group's space under pymetta's statistical profiler and answer
    its answers, the inferences it was charged, the sampler's counters and the `top` predicate rows
    the samples landed in most, each row keyed by the profile's column names.

    The expression runs, so whatever it does happens: its engine writes are discarded with the
    speculation and a Python effect is not. The sampler is statistical, so a short run reports few
    or no samples, while each row's calls and redos are counted exactly. Raises InvalidInputError
    for text that is not one form or a `top` that is not a count; InferenceBudgetExceeded or
    ReviewTimeout when a bound stops the run or was used up first; MettaEngineError when the
    engine refuses it; and whatever prepare raises."""

    form, _ = _form(expression, "expression")
    if isinstance(top, bool) or not isinstance(top, int) or top < 0:
        raise InvalidInputError("A profile's top must be a count of rows, 0 or more.", details={"top": safe_repr(top)})

    def work(space: Any) -> dict[str, Any]:
        (groups, sampled), inferences = bounded_call(
            space, lambda limit, seconds: space.profile(f"!{form}", inferences=limit, timeout=seconds), budget=budget)
        return {
            "expression": form,
            "answers": _texts(groups),
            "inferences": inferences,
            "profile": {
                "samples": sampled.samples,
                "ticks": sampled.ticks,
                "seconds": sampled.seconds,
                "predicates": len(sampled.nodes),
                "top": [dict(zip(sampled.COLUMNS, map(_plain, row), strict=True)) for row in sampled.top(top)],
            },
        }

    return _diagnose("profile", group, budget, work)


# The engine's longhand for Space.explain is `!(explain QUERY)`, one ordinary run, so run_bounded
# bounds and charges it whole (c-dg-explain-one-run-1019). It reflects the query and runs none of
# it. A match form the engine does not take for one, as in a space the engine does not recognize
# (c-dg-unrecognized-space-defects-1019), answers the match operation's declarations with no plan,
# which is refused rather than reported as a plan; whether the form is a match form is read from
# the engine-free tree _form read, so nothing crosses into the engine outside that one run.
# Time: one bounded run of the engine's explain.
# am[implements a-dg-module-1019@7c4558] am[implements a-dg-explain-refusal-1019@b7099d]
# am[rests-on c-dg-explain-one-run-1019@8212b8] am[rests-on c-dg-unrecognized-space-defects-1019@e59ed6]
def explain(group: ModuleGroup, expression: str, *, budget: RunBudget) -> dict[str, Any]:
    """Answer what the engine would do with `EXPRESSION` in the group's space, without running it:
    for `(match SPACE PATTERN TEMPLATE)` the route, writes, error mode and the plan, the join the
    conjunctive matcher runs; for an operation call its effect, inverse, cache decision and origin.
    `items` are the engine's items in its order and `plan` the plan item, None for an operation.

    Raises InvalidInputError for text that is not one form; MettaEngineError when the engine
    refuses the form or answers a match form without a plan; InferenceBudgetExceeded or
    ReviewTimeout when a bound stops it or was used up first; and whatever prepare raises."""

    form, tree = _form(expression, "expression")
    match_form = isinstance(tree, list) and bool(tree) and tree[0] == syntax.Symbol("match")

    def work(space: Any) -> dict[str, Any]:
        from metta import Expression  # noqa: PLC0415 (pymetta is imported only once an engine exists)

        answers, inferences = run_bounded(space, f"!(explain {form})", budget=budget)
        if len(answers) != 1 or len(answers[0]) != 1 or not isinstance(answers[0][0], Expression):
            raise MettaEngineError(
                f"The engine's explain answered {_texts(answers)} for {form}, not one list of items.",
                details={"diagnostic": "explain", "group": group.name, "expression": form, "answers": _texts(answers)},
            )
        items = answers[0][0].children
        plans = [item for item in items if isinstance(item, Expression) and item.children
                 and str(item.children[0]) == "plan"]
        if match_form and not plans:
            raise MettaEngineError(
                f"The engine explained {form} without a plan: it took the form for a call of the match "
                f"operation, which happens when the form is not (match SPACE PATTERN TEMPLATE) or the "
                f"engine does not recognize its space, which it recognizes by an &-prefixed name or as "
                f"a registered operand.",
                details={"diagnostic": "explain", "group": group.name, "expression": form,
                         "items": [str(item) for item in items]},
            )
        return {"expression": form, "items": [str(item) for item in items],
                "plan": str(plans[0]) if plans else None, "inferences": inferences}

    return _diagnose("explain", group, budget, work)


# Each stage is one bounded `once` over a match in the group's space, so it stops at its first
# answer and is charged whole, where Space.match's cursor engine would not be
# (c-dg-match-cursor-uncounted-1019), and Space.why's atom scan escapes the bounds altogether
# (c-dg-why-outside-limits-1019). The stages are pymetta's explanation of an empty query: the
# whole query, the patterns joined without the guard, then each pattern alone; a later stage runs
# only when the earlier ones found nothing, and one pattern alone is the query itself.
# Time: at most 2 + n bounded runs, n = len(patterns), each stopping at its first answer.
# am[implements a-dg-module-1019@7c4558] am[rests-on c-dg-match-cursor-uncounted-1019@458a46]
# am[rests-on c-dg-why-outside-limits-1019@d1933e]
def match(group: ModuleGroup, patterns: Sequence[str], *, where: str | None = None,
          budget: RunBudget) -> dict[str, Any]:
    """Say why the conjunction of `patterns`, kept by the guard `where` when one is given, has
    answers in the group's space or none: `verdict` is "matches", "guard-rejects-every-row" when
    the patterns join but the guard keeps no row, "patterns-match-nothing" with the 1-based
    `unmatched` patterns that match nothing alone, or "no-joint-binding" when each pattern
    matches alone but no binding satisfies them together. `stages` lists each query run, whether
    it found an answer and its inferences.

    A guard is evaluated as the match evaluates it, once per joined row. Raises InvalidInputError
    for no pattern or text that is not one form; MettaEngineError when a stage answers anything
    but True or nothing, as an Error atom from the guard; InferenceBudgetExceeded or ReviewTimeout
    when a bound stops a stage or was used up first; and whatever prepare raises."""

    if isinstance(patterns, str) or not isinstance(patterns, Sequence) or not patterns:
        raise InvalidInputError("A match diagnostic takes one or more patterns.", details={"patterns": safe_repr(patterns)})
    forms = [_form(pattern, "pattern")[0] for pattern in patterns]
    guard = None if where is None else _form(where, "guard")[0]
    conjunction = forms[0] if len(forms) == 1 else "(, " + " ".join(forms) + ")"

    def work(space: Any) -> dict[str, Any]:
        stages: list[dict[str, Any]] = []

        def found(query: str, kept_by: str | None) -> bool:
            template = "True" if kept_by is None else f"(if {kept_by} True (empty))"
            source = f"(once (match &self {query} {template}))"
            answers, inferences = run_bounded(space, f"!{source}", budget=budget)
            nothing = answers == [[]]
            true = len(answers) == 1 and len(answers[0]) == 1 and plain_value(answers[0][0]) is True
            if not (nothing or true):
                raise MettaEngineError(
                    f"The match diagnostic's stage {source} answered {_texts(answers)}, not True or nothing.",
                    details={"diagnostic": "match", "group": group.name, "stage": source, "answers": _texts(answers)},
                )
            stages.append({"query": source, "found": true, "inferences": inferences})
            return true

        unmatched: list[int] = []
        if found(conjunction, guard):
            verdict = MATCHES
        elif guard is not None and found(conjunction, None):
            verdict = GUARD_REJECTS
        else:
            unmatched = [1] if len(forms) == 1 else [
                index for index, form in enumerate(forms, start=1) if not found(form, None)]
            verdict = PATTERNS_MATCH_NOTHING if unmatched else NO_JOINT_BINDING
        return {"patterns": forms, "where": guard, "verdict": verdict, "unmatched": unmatched, "stages": stages,
                "inferences": sum(stage["inferences"] for stage in stages)}

    return _diagnose("match", group, budget, work)

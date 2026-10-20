"""Purpose: verify goal_chainer.runtime.evaluator on the real engine: a typed entry answers its one
atom with hole data left inert; entries without a typed arrow, other arities and other answer
counts are refused, and a refused name, entry or module named where repr cannot write it; a call
leaves nothing in its group's space while the same call outside
speculation does; a group's space carries the & prefix the engine needs to take it for a space,
so an empty conjunctive match there answers nothing and explain answers a match form's plan; the
caller's budget is charged and stops a runaway entry; a group's identity
follows its name and modules; one name stands for one group, a Python module for one group, and a
group's warm-ups each answer True, run in order outside speculation, and run again from the first
after one fails."""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pytest
from metta import Expression, S, Variable

from goal_chainer.errors import InvalidInputError, MettaEngineError, ProtocolError
from goal_chainer.runtime.budget import InferenceBudgetExceeded, RunBudget, run_bounded
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.evaluator import ModuleGroup, evaluate, plain_value, prepare

# Entries declare Atom for parameters so hole data stays inert, and their result's own type, since
# an entry returning Atom answers its body unevaluated (c-rt-atom-return-unevaluated-1018).
ENTRIES = """
(: gc-eval-echo (-> Atom Atom))
(= (gc-eval-echo $x) $x)
(: gc-eval-double (-> Number Number))
(= (gc-eval-double $n) (* $n 2))
(: gc-eval-pair (-> Atom Atom Expression))
(= (gc-eval-pair $a $b) ($a $b))
(: gc-eval-loose (-> %Undefined% Expression))
(= (gc-eval-loose $x) ($x))
(= (gc-eval-untyped $x) $x)
(: gc-eval-two (-> Atom Number))
(= (gc-eval-two $x) 1)
(= (gc-eval-two $x) 2)
(: gc-eval-none (-> Atom Expression))
(= (gc-eval-none $x) (empty))
(: gc-eval-store (-> Atom Symbol))
(= (gc-eval-store $x) (let $_ (add-atom &self (gc-eval-stored $x)) done))
(: gc-eval-spin (-> Number Number))
(= (gc-eval-spin $n) (gc-eval-spin (+ $n 1)))
"""
_NUMBERS = itertools.count()


# am[verifies a-rt-rb-evaluator-api-1018@9374f4]
def _budget(inferences: int | None = None) -> RunBudget:
    return RunBudget(inference_budget=inferences, timeout_seconds=120.0)


# A one-module group named for this test alone, since a process prepares each name once.
# am[verifies a-rt-rb-evaluator-api-1018@9374f4]
def _group(tmp_path: Path, source: str = ENTRIES, *, warm_ups: tuple[str, ...] = ()) -> ModuleGroup:
    number = next(_NUMBERS)
    module = tmp_path / f"group_{number}.metta"
    module.write_text(source, encoding="utf-8")
    return ModuleGroup(f"test-evaluator-{number}", (module,), warm_ups)


# A Number hole is evaluated as a number, and an expression whose head names a defined function
# stays the expression behind an Atom parameter.
# am[verifies a-rt-rb-evaluator-api-1018@9374f4] am[verifies a-rt-rb-evaluate-answers-atom-1018@0aeca3]
# am[verifies c-jk-atom-entry-inert-1018@63e37f]
def test_a_typed_entry_answers_its_one_atom_and_keeps_hole_data_inert(tmp_path):
    group = _group(tmp_path)

    assert evaluate(group, "gc-eval-echo", S["gc-eval-double"](2), budget=_budget()) == S["gc-eval-double"](2)
    assert plain_value(evaluate(group, "gc-eval-double", 21, budget=_budget())) == 42
    assert plain_value(evaluate(group, "gc-eval-pair", S.a, "b", budget=_budget())) == (S.a, "b")


# am[verifies a-rt-rb-evaluator-api-1018@9374f4] am[verifies c-jk-atom-entry-inert-1018@63e37f]
@pytest.mark.parametrize(("function", "arguments", "refusal"), [
    ("gc-eval-untyped", (1,), "must declare an arrow type"),
    ("gc-eval-loose", (1,), "must declare an arrow type"),
    ("gc-eval-missing", (1,), "must declare an arrow type"),
    ("gc-eval-pair", (1,), "takes 2 arguments, not 1"),
    ("(gc-eval-pair 1 2)", (), "must be a MeTTa symbol"),
])
def test_an_entry_without_a_typed_arrow_or_its_arity_is_refused(tmp_path, function, arguments, refusal):
    group = _group(tmp_path)

    with pytest.raises(InvalidInputError, match=refusal):
        evaluate(group, function, *arguments, budget=_budget())


# am[verifies a-rt-rb-evaluator-api-1018@9374f4]
def test_a_call_answering_other_than_once_is_a_protocol_error(tmp_path):
    group = _group(tmp_path)

    with pytest.raises(ProtocolError) as two:
        evaluate(group, "gc-eval-two", 0, budget=_budget())
    with pytest.raises(ProtocolError, match="answered 0 results"):
        evaluate(group, "gc-eval-none", 0, budget=_budget())
    assert two.value.details["group"] == group.name
    assert two.value.details["function"] == "gc-eval-two"
    assert sorted(two.value.details["answers"][0]) == ["1", "2"]


# The same call outside speculation stores its atom, so the first read could have found one.
# am[verifies a-rt-rb-evaluator-api-1018@9374f4] am[verifies a-rt-rb-evaluate-answers-atom-1018@0aeca3]
def test_a_call_leaves_nothing_in_its_groups_space(tmp_path):
    group = _group(tmp_path)

    def stored():
        with metta_engine(None) as engine:
            answers = engine.space(group.space).run("!(collapse (match &self (gc-eval-stored $y) $y))")
        return [[plain_value(answer) for answer in answered] for answered in answers]

    assert evaluate(group, "gc-eval-store", S.inside, budget=_budget()) == S.done
    assert stored() == [[()]]
    with metta_engine(None) as engine:
        run_bounded(engine.space(group.space), "!(gc-eval-store outside)", budget=_budget())
    assert stored() == [[(S.outside,)]]


# An atom's text with its variables named in order of first appearance, so an answer holding the
# engine's fresh $_N variables compares by its shape alone.
# am[verifies a-dg-amp-group-spaces-1019@9b4cf8]
def _canonical(atom: object, names: dict[str, str] | None = None) -> str:
    names = {} if names is None else names
    if isinstance(atom, Variable):
        return names.setdefault(atom.name, f"$v{len(names) + 1}")
    if isinstance(atom, Expression):
        return "(" + " ".join(_canonical(child, names) for child in atom.children) + ")"
    return str(atom)


# Without the & prefix the engine answered the empty conjunction with an Error atom saying match
# expects a space, and explained the match form as the match operation with no plan item
# (c-dg-unrecognized-space-defects-1019); the plan is pinned whole.
# am[verifies a-dg-amp-group-spaces-1019@9b4cf8] am[rests-on c-dg-unrecognized-space-defects-1019@e59ed6]
def test_a_groups_space_answers_an_empty_conjunction_with_nothing_and_explains_its_plan(tmp_path):
    group = _group(tmp_path, "(gc-eval-edge a b) (gc-eval-edge b c) (gc-eval-node a)\n")
    prepare(group, budget=_budget())
    join = "(, (gc-eval-edge $x $y) (gc-eval-edge $y $z))"

    with metta_engine(None) as engine:
        space = engine.space(group.space)
        empty, _ = run_bounded(space, "!(collapse (match &self (, (gc-eval-edge a $y) (gc-eval-node $y)) $y))",
                               budget=_budget())
        joined, _ = run_bounded(space, f"!(collapse (match &self {join} ($x $z)))", budget=_budget())
        explained, _ = run_bounded(space, f"!(explain (match &self {join} ($x $z)))", budget=_budget())

    assert [[plain_value(answer) for answer in answered] for answered in empty] == [[()]]
    assert [[plain_value(answer) for answer in answered] for answered in joined] == [[((S.a, S.c),)]]
    [[items]] = explained
    plans = [_canonical(item) for item in items.children if str(item.children[0]) == "plan"]
    assert plans == ["(plan nested-loop (order (gc-eval-edge $v1 $v2) (gc-eval-edge $v2 $v3)))"]
    assert group.space == f"&gc-group-{group.name}"


# am[verifies a-rt-rb-one-budget-1018@550ffd]
def test_the_callers_budget_is_charged_and_stops_a_runaway_entry(tmp_path):
    group = _group(tmp_path)
    budget = _budget(inferences=200_000)

    evaluate(group, "gc-eval-double", 1, budget=budget)
    spent = budget.spent
    with pytest.raises(InferenceBudgetExceeded):
        evaluate(group, "gc-eval-spin", 0, budget=budget)

    assert 0 < spent < budget.spent


# A prepared group still stops a request whose budget is used up, before any engine work.
# am[verifies a-rt-rb-one-budget-1018@550ffd]
def test_an_exhausted_budget_is_stopped_in_a_prepared_group(tmp_path):
    group = _group(tmp_path)
    prepare(group, budget=_budget())
    budget = _budget(inferences=10)
    budget.charge(10)

    with pytest.raises(InferenceBudgetExceeded):
        evaluate(group, "gc-eval-double", 1, budget=budget)


# No call runs unbounded: a missing budget is refused before the group loads.
# am[verifies a-rt-rb-one-budget-1018@550ffd]
def test_a_call_without_a_budget_is_refused(tmp_path):
    group = _group(tmp_path)

    with pytest.raises(InvalidInputError, match="never unbounded"):
        evaluate(group, "gc-eval-double", 1, budget=None)


# am[verifies a-rt-rb-evaluator-api-1018@9374f4]
def test_a_groups_identity_follows_its_name_and_modules(tmp_path):
    group = _group(tmp_path)
    renamed = _group(tmp_path)
    edited = _group(tmp_path, ENTRIES + "(= (gc-eval-extra) 1)\n")

    identity = prepare(group, budget=_budget())

    assert identity.startswith("sha256:")
    assert prepare(group, budget=_budget()) == identity
    assert prepare(renamed, budget=_budget()) != identity
    assert prepare(edited, budget=_budget()) not in {identity, prepare(renamed, budget=_budget())}


# am[verifies a-rt-rb-evaluator-api-1018@9374f4]
def test_one_name_stands_for_one_group(tmp_path):
    group = _group(tmp_path)
    prepare(group, budget=_budget())
    other = tmp_path / "other.metta"
    other.write_text(ENTRIES, encoding="utf-8")

    with pytest.raises(InvalidInputError, match="already prepared with other modules"):
        prepare(ModuleGroup(group.name, (other,)), budget=_budget())


# am[verifies a-rt-rb-py-module-one-group-1018@64026b]
def test_a_python_module_belongs_to_one_group(tmp_path):
    helper = tmp_path / "gc_eval_helper.py"
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    first = ModuleGroup(f"test-evaluator-{next(_NUMBERS)}", (helper,))
    second = ModuleGroup(f"test-evaluator-{next(_NUMBERS)}", (helper,))
    prepare(first, budget=_budget())

    with pytest.raises(InvalidInputError, match="already belongs to module group") as refused:
        prepare(second, budget=_budget())
    assert refused.value.details["owner"] == first.name


# A warm-up answering False leaves the group unprepared, so the next call tries it again whole.
# am[verifies a-rt-rb-evaluator-api-1018@9374f4]
def test_a_warm_up_must_answer_true(tmp_path):
    ready = _group(tmp_path, ENTRIES + "(: gc-eval-ready (-> Bool))\n(= (gc-eval-ready) True)\n",
                   warm_ups=("gc-eval-ready",))
    unready = _group(tmp_path, ENTRIES + "(: gc-eval-ready (-> Bool))\n(= (gc-eval-ready) False)\n",
                     warm_ups=("gc-eval-ready",))

    assert prepare(ready, budget=_budget()).startswith("sha256:")
    for _attempt in range(2):
        with pytest.raises(ProtocolError, match="warm-up gc-eval-ready must answer True"):
            prepare(unready, budget=_budget())


# Warm-ups that record themselves in their group's space: the second answers True only after the
# first has run, and the refusing one never does.
WARM_UPS = ENTRIES + """
(: gc-eval-first (-> Bool))
(= (gc-eval-first) (let $added (add-atom &self (gc-eval-ran first)) True))
(: gc-eval-second (-> Bool))
(= (gc-eval-second)
   (if (== (collapse (match &self (gc-eval-ran first) seen)) (seen))
       (let $added (add-atom &self (gc-eval-ran second)) True)
       False))
(: gc-eval-refuse (-> Bool))
(= (gc-eval-refuse) False)
"""


# am[verifies a-rel-nd-section-warm-ups-1018@df1a66]
def _ran(group: ModuleGroup) -> list[str]:
    with metta_engine(None) as engine:
        return sorted(str(atom) for atom in engine.space(group.space).atoms() if str(atom).startswith("(gc-eval-ran "))


# A composed group runs each owner's warm-up once, in the order it names them, outside speculation,
# so what each writes stays in the space; a group with none prepares without one.
# am[verifies a-rel-nd-section-warm-ups-1018@df1a66]
def test_a_groups_warm_ups_each_run_once_in_order(tmp_path):
    ordered = _group(tmp_path, WARM_UPS, warm_ups=("gc-eval-first", "gc-eval-second"))
    reversed_ = _group(tmp_path, WARM_UPS, warm_ups=("gc-eval-second", "gc-eval-first"))
    bare = _group(tmp_path, WARM_UPS)

    prepare(ordered, budget=_budget())
    prepare(ordered, budget=_budget())
    assert _ran(ordered) == ["(gc-eval-ran first)", "(gc-eval-ran second)"]
    with pytest.raises(ProtocolError, match="warm-up gc-eval-second must answer True"):
        prepare(reversed_, budget=_budget())
    assert bare.warm_ups == ()
    assert prepare(bare, budget=_budget()).startswith("sha256:")
    assert _ran(bare) == []


# A failing warm-up leaves the group unprepared, so the next call runs every warm-up again from the
# first.
# am[verifies a-rel-nd-section-warm-ups-1018@df1a66]
def test_a_failing_warm_up_leaves_the_group_unprepared_and_a_retry_runs_them_all(tmp_path):
    group = _group(tmp_path, WARM_UPS, warm_ups=("gc-eval-first", "gc-eval-refuse"))

    for _attempt in range(2):
        with pytest.raises(ProtocolError, match="warm-up gc-eval-refuse must answer True") as refused:
            prepare(group, budget=_budget())
        assert refused.value.details["warm_up"] == "gc-eval-refuse"
    assert _ran(group) == ["(gc-eval-ran first)", "(gc-eval-ran first)"]


# A module with one closing parenthesis too many would import nothing, so its group is refused,
# naming the module, every time it is prepared: no identity stands for code its space never got
# (i-ev-prepare-silent-on-unparsed-module-1018).
# am[verifies a-rt-loader-refuses-unparsed-1018@d138df]
def test_a_group_whose_module_does_not_parse_is_refused(tmp_path):
    group = _group(tmp_path, "(: probe-ok (-> Number))\n(= (probe-ok) 1))\n")

    for _attempt in range(2):
        with pytest.raises(MettaEngineError, match="does not parse") as refused:
            prepare(group, budget=_budget())
        assert refused.value.details["path"] == str(group.modules[0].resolve())


# am[verifies a-rt-rb-evaluator-api-1018@9374f4]
# am[verifies a-rel-nd-section-warm-ups-1018@df1a66]
@pytest.mark.parametrize(("name", "modules", "warm_ups", "refusal"), [
    ("two words", (Path("a.metta"),), (), "name must be a MeTTa symbol"),
    ("test-evaluator-shape", (), (), "nonempty tuple"),
    ("test-evaluator-shape", [Path("a.metta")], (), "nonempty tuple"),
    ("test-evaluator-shape", ("a.metta",), (), "nonempty tuple"),
    ("test-evaluator-shape", (Path("a.metta"),), ("(ready)",), "warm-up must name an entry"),
    ("test-evaluator-shape", (Path("a.metta"),), "ready", "must be a tuple of entry names"),
    ("test-evaluator-shape", (Path("a.metta"),), ("ready", "set", "ready"), "names each warm-up once"),
])
def test_a_group_is_declared_with_symbols_and_a_tuple_of_modules(name, modules, warm_ups, refusal):
    with pytest.raises(InvalidInputError, match=refusal):
        ModuleGroup(name, modules, warm_ups)


# A group or entry refused for a value repr cannot write names it in the refusal's details, so the
# refusal is still the InvalidInputError where building it raised ValueError.
# am[verifies a-rt-rr-safe-repr-1018@ec9700]
def test_a_refused_group_or_entry_names_what_repr_cannot_write(tmp_path):
    huge = f"an integer of more than {sys.get_int_max_str_digits()} digits"
    module = (Path("a.metta"),)

    with pytest.raises(InvalidInputError, match="name must be a MeTTa symbol") as name:
        ModuleGroup(10**5000, module)
    with pytest.raises(InvalidInputError, match="warm-up must name an entry") as warm_up:
        ModuleGroup("test-evaluator-shape", module, (10**5000,))
    with pytest.raises(InvalidInputError, match="nonempty tuple") as modules:
        ModuleGroup("test-evaluator-shape", (10**5000,))
    with pytest.raises(InvalidInputError, match="entry must be a MeTTa symbol") as entry:
        evaluate(_group(tmp_path), 10**5000, budget=_budget())

    assert name.value.details["name"] == huge
    assert warm_up.value.details["warm_up"] == huge
    assert modules.value.details["modules"] == "a value of type tuple whose repr raised ValueError"
    assert entry.value.details["function"] == huge

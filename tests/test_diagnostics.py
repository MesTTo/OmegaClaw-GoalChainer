"""Purpose: verify goal_chainer.runtime.diagnostics and `goalchainer diagnose` on the real pinned
engine: a profile answers its run, the sampler's counters and rows named by the profile's columns,
discards its engine writes, and is stopped and charged by either bound while the next profile still
runs; explain answers a match form's whole plan without running the query and an operation's
declarations, refuses a match form with no plan and what the engine cannot explain, and reads a
form's head without metta.parse; match names the stage that leaves a query without answers, and a
stage answering an Error atom is an engine error; every diagnostic stops a used-up budget before
any engine work, refuses text that is not one readable form and runs on the process's one engine;
the command prints the report or a typed JSON error, refuses a used-up budget before importing a
group's module, requires both limits and refuses a path that is no UTF-8 text."""

from __future__ import annotations

import itertools
import json
import re
import sys
import time
from pathlib import Path

import metta
import pytest
from metta import S
from metta.errors import InferenceLimitError, TimeLimitError
from request_support import CLI_LIMITS

from goal_chainer import cli
from goal_chainer.errors import InvalidInputError, MettaEngineError
from goal_chainer.runtime import diagnostics, evaluator
from goal_chainer.runtime import engine as runtime_engine
from goal_chainer.runtime.budget import InferenceBudgetExceeded, ReviewTimeout, RunBudget, run_bounded
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.evaluator import ModuleGroup, plain_value, prepare

MODULE = """(gc-diag-edge a b) (gc-diag-edge b c) (gc-diag-node a)
(: gc-diag-spin (-> Number Number))
(= (gc-diag-spin $n) (gc-diag-spin (+ $n 1)))
(: gc-diag-hop (-> Atom Symbol))
(= (gc-diag-hop $x) (match &self (gc-diag-edge $x $y) $y))
(: gc-diag-mark (-> Atom Symbol))
(= (gc-diag-mark $x) (let $_ (add-atom &self (gc-diag-marked $x)) done))
"""
# The line gc-diag-hop's equation is on, which the engine's origin item names.
HOP_LINE = MODULE.splitlines().index("(= (gc-diag-hop $x) (match &self (gc-diag-edge $x $y) $y))") + 1
# The columns of a profile row, pymetta's EngineProfile.COLUMNS, which the report keys each row by.
COLUMNS = {"predicate", "calls", "redos", "ticks_self", "ticks_siblings", "file", "line", "seconds_self",
           "seconds_total", "name", "arity", "recursive_calls"}
# The two-edge join, its plan as the engine answers it with the fresh variables renamed in order.
JOIN = "(, (gc-diag-edge $x $y) (gc-diag-edge $y $z))"
JOIN_PLAN = "(plan nested-loop (order (gc-diag-edge $v1 $v2) (gc-diag-edge $v2 $v3)))"
_NUMBERS = itertools.count()


# am[verifies a-dg-module-1019@7c4558]
def _budget(inferences: int | None = 50_000_000, seconds: float = 120.0) -> RunBudget:
    return RunBudget(inference_budget=inferences, timeout_seconds=seconds)


# A module file of its own for each test, and a group named for it, since a process prepares each
# group name once.
# am[verifies a-dg-module-1019@7c4558]
def _module(tmp_path: Path) -> Path:
    module = tmp_path / f"diagnostics_{next(_NUMBERS)}.metta"
    module.write_text(MODULE, encoding="utf-8")
    return module


# am[verifies a-dg-module-1019@7c4558]
def _group(tmp_path: Path) -> ModuleGroup:
    module = _module(tmp_path)
    return ModuleGroup(f"test-{module.stem.replace('_', '-')}", (module,))


# The engine names a fresh variable $_N from a count it keeps for the whole process, so an item's
# text is compared with its variables renamed in order of first appearance.
# am[verifies a-dg-module-1019@7c4558]
def _canonical(text: str) -> str:
    names: dict[str, str] = {}
    return re.sub(r"\$_\d+", lambda found: names.setdefault(found.group(0), f"$v{len(names) + 1}"), text)


# Preparation charges no inferences, so the run's are the budget's; with every row reported, the
# entry's own row counts its one call exactly whatever the sampler caught.
# am[verifies a-dg-module-1019@7c4558] am[verifies a-dg-bounded-call-1019@a8caca]
def test_a_profile_answers_its_run_the_samplers_counters_and_named_rows(tmp_path):
    group = _group(tmp_path)
    budget = _budget()

    report = diagnostics.profile(group, "(gc-diag-hop a)", top=10_000, budget=budget)

    assert set(report) == {"diagnostic", "group", "engine", "expression", "answers", "inferences",
                           "profile", "budget"}
    assert (report["diagnostic"], report["expression"], report["answers"]) == ("profile", "(gc-diag-hop a)", [["b"]])
    assert report["group"] == {"name": group.name, "space": group.space, "identity": prepare(group, budget=_budget())}
    assert set(report["engine"]) == {"runtime", "runtime_digest", "swipl_version"}
    assert 0 < report["inferences"] == budget.spent
    assert report["budget"] == {"inference_budget": 50_000_000, "timeout_seconds": 120.0, "spent": budget.spent}
    sampled = report["profile"]
    assert set(sampled) == {"samples", "ticks", "seconds", "predicates", "top"}
    assert 0 < len(sampled["top"]) == sampled["predicates"]
    assert all(set(row) == COLUMNS for row in sampled["top"])
    [hop] = [row for row in sampled["top"] if row["name"] == "gc-diag-hop"]
    assert (hop["arity"], hop["calls"], hop["file"]) == (2, 1, str(group.modules[0]))
    assert json.loads(json.dumps(report)) == report


# The same call outside the diagnostic's speculation stores its atom, so the first read could
# have found one.
# am[verifies a-dg-module-1019@7c4558]
def test_a_profile_discards_its_engine_writes(tmp_path):
    group = _group(tmp_path)

    def marked() -> list[list[object]]:
        with metta_engine(None) as engine:
            answers, _ = run_bounded(engine.space(group.space), "!(collapse (match &self (gc-diag-marked $x) $x))",
                                     budget=_budget())
        return [[plain_value(answer) for answer in answered] for answered in answers]

    assert diagnostics.profile(group, "(gc-diag-mark inside)", budget=_budget())["answers"] == [["done"]]
    assert marked() == [[()]]
    with metta_engine(None) as engine:
        run_bounded(engine.space(group.space), "!(gc-diag-mark outside)", budget=_budget())
    assert marked() == [[(S.outside,)]]


# gc-diag-spin never repeats an argument, so neither the cache nor anything else ends it before a
# bound does; the group is prepared first, so the deadline stops the profiled run itself, which ran
# until then. The sampler is released, so the next profile runs.
# am[verifies a-dg-bounded-call-1019@a8caca] am[verifies a-dg-module-1019@7c4558]
@pytest.mark.parametrize(("inferences", "seconds", "raised", "cause"), [
    (200_000, 120.0, InferenceBudgetExceeded, InferenceLimitError),
    (None, 1.0, ReviewTimeout, TimeLimitError),
], ids=["inferences", "deadline"])
def test_a_profile_stopped_by_either_bound_is_charged_and_the_next_one_runs(tmp_path, inferences, seconds,
                                                                            raised, cause):
    group = _group(tmp_path)
    prepare(group, budget=_budget())
    budget = _budget(inferences, seconds)
    started = time.monotonic()

    with pytest.raises(raised) as stopped:
        diagnostics.profile(group, "(gc-diag-spin 0)", budget=budget)

    assert isinstance(stopped.value.__cause__, cause)
    assert budget.spent >= (inferences or 1)
    assert time.monotonic() - started >= (0 if inferences else seconds)
    assert diagnostics.profile(group, "(gc-diag-hop a)", budget=_budget())["answers"] == [["b"]]


# A used-up budget is refused where the diagnostic is entered: no group is loaded and the engine is
# never held.
# am[verifies a-dg-module-1019@7c4558]
@pytest.mark.parametrize("run", [
    lambda group, budget: diagnostics.profile(group, "(gc-diag-hop a)", budget=budget),
    lambda group, budget: diagnostics.explain(group, "(gc-diag-hop a)", budget=budget),
    lambda group, budget: diagnostics.match(group, ["(gc-diag-edge $x $y)"], budget=budget),
], ids=["profile", "explain", "match"])
@pytest.mark.parametrize("used_up", ["inferences", "deadline"])
def test_a_used_up_budget_stops_a_diagnostic_before_any_engine_work(tmp_path, monkeypatch, run, used_up):
    def refuse(*_arguments: object, **_keywords: object) -> None:
        raise AssertionError("engine work began")

    group = _group(tmp_path)
    monkeypatch.setattr(evaluator, "initialize_once", refuse)
    monkeypatch.setattr(diagnostics, "metta_engine", refuse)
    if used_up == "inferences":
        budget, raised = _budget(inferences=10), InferenceBudgetExceeded
        budget.charge(10)
    else:
        budget, raised = _budget(seconds=0.001), ReviewTimeout
        time.sleep(0.01)

    with pytest.raises(raised):
        run(group, budget)


# The template would spin past the budget if explain ran the query; every item is pinned, the plan
# whole.
# am[verifies a-dg-module-1019@7c4558]
def test_explain_answers_a_match_forms_whole_plan_without_running_it(tmp_path):
    budget = _budget(inferences=1_000_000)

    report = diagnostics.explain(_group(tmp_path), f"(match &self {JOIN} (gc-diag-spin 0))", budget=budget)

    assert [_canonical(item) for item in report["items"]] == [
        "(handles none)", "(pushes False)", "(source repeated)", "(context undeclared)", "(annotations bool)",
        "(emits none)", "(events per-write-exactly ordered)", "(writes undeclared)", "(on-error abort)",
        "(merge depth)", JOIN_PLAN, "(materialized False)"]
    assert _canonical(report["plan"]) == JOIN_PLAN
    assert 0 < report["inferences"] == budget.spent < 1_000_000


# am[verifies a-dg-module-1019@7c4558]
def test_explain_answers_an_operations_declarations(tmp_path):
    group = _group(tmp_path)

    report = diagnostics.explain(group, "(gc-diag-hop a)", budget=_budget())

    assert report["plan"] is None
    assert report["items"] == ["(effect none)", "(inverse False)", "(annotations bool)", "(on-error abort)",
                               "(cache declined not-recursive)", "(visibility public)",
                               f'(origin {group.space} "{group.modules[0]}" {HOP_LINE})']


# A match form without its template is a call of the match operation to the engine, so it answers
# no plan; a form whose head is a number is no operation call either.
# am[verifies a-dg-explain-refusal-1019@b7099d]
@pytest.mark.parametrize(("expression", "refusal"), [
    ("(match &self (gc-diag-edge $x $y))", "without a plan"),
    ("(1 2)", "refused the explain diagnostic"),
])
def test_explain_refuses_a_match_form_without_a_plan_and_what_the_engine_cannot_explain(tmp_path, expression,
                                                                                         refusal):
    with pytest.raises(MettaEngineError, match=refusal):
        diagnostics.explain(_group(tmp_path), expression, budget=_budget())


# A form's head is read by the engine-free reader, so no engine call happens outside the one
# bounded run.
# am[verifies a-dg-module-1019@7c4558] am[verifies a-dg-explain-refusal-1019@b7099d]
def test_explain_reads_a_forms_head_without_metta_parse(tmp_path, monkeypatch):
    def refuse(*_arguments: object, **_keywords: object) -> None:
        raise AssertionError("metta.parse was called")

    group = _group(tmp_path)
    prepare(group, budget=_budget())
    monkeypatch.setattr(metta, "parse", refuse)

    assert _canonical(diagnostics.explain(group, f"(match &self {JOIN} True)", budget=_budget())["plan"]) == JOIN_PLAN
    with pytest.raises(MettaEngineError, match="without a plan"):
        diagnostics.explain(group, "(match &self (gc-diag-edge $x $y))", budget=_budget())


# Each later stage runs only when the earlier ones found nothing, and one pattern alone is the
# query itself; the stages' inferences are what the budget was charged.
# am[verifies a-dg-module-1019@7c4558]
@pytest.mark.parametrize(("patterns", "where", "verdict", "unmatched", "stages"), [
    (["(gc-diag-edge $x $y)", "(gc-diag-edge $y $z)"], None, "matches", [], 1),
    (["(gc-diag-edge $x $y)"], "(== $x a)", "matches", [], 1),
    (["(gc-diag-edge $x $y)"], "(== $x q)", "guard-rejects-every-row", [], 2),
    (["(gc-diag-edge a $y)", "(gc-diag-node $y)"], None, "no-joint-binding", [], 3),
    (["(gc-diag-edge z $y)", "(gc-diag-node $y)", "(gc-diag-missing $y)"], None, "patterns-match-nothing", [1, 3], 4),
    (["(gc-diag-edge z $y)"], None, "patterns-match-nothing", [1], 1),
    (["(gc-diag-edge z $y)"], "(== $y a)", "patterns-match-nothing", [1], 2),
])
def test_match_names_the_stage_that_leaves_a_query_without_answers(tmp_path, patterns, where, verdict, unmatched,
                                                                  stages):
    budget = _budget()

    report = diagnostics.match(_group(tmp_path), patterns, where=where, budget=budget)

    assert (report["verdict"], report["unmatched"], len(report["stages"])) == (verdict, unmatched, stages)
    assert (report["patterns"], report["where"]) == (patterns, where)
    assert [stage["found"] for stage in report["stages"]][:1] == [verdict == "matches"]
    assert report["inferences"] == sum(stage["inferences"] for stage in report["stages"]) == budget.spent


# A guard the engine answers with an Error atom leaves its stage with neither True nor nothing.
# am[verifies a-dg-module-1019@7c4558]
def test_a_match_stage_answering_an_error_is_an_engine_error(tmp_path):
    with pytest.raises(MettaEngineError, match="not True or nothing"):
        diagnostics.match(_group(tmp_path), ["(gc-diag-edge $x $y)"], where='(+ 1 "a")', budget=_budget())


# Text is refused before any engine work: more or fewer than one form, a directive, an unclosed
# form, a bare atom, no text at all, and a form nested past the reader's recursion.
# am[verifies a-dg-module-1019@7c4558]
@pytest.mark.parametrize("text", ["(a) (b)", "!(a)", "(a", "a", "", "  ", 5, "(" * 5000 + ")" * 5000],
                         ids=["two", "directive", "unclosed", "bare", "empty", "blank", "number", "deep"])
def test_a_diagnostic_refuses_text_that_is_not_one_readable_form(tmp_path, monkeypatch, text):
    def refuse(*_arguments: object, **_keywords: object) -> None:
        raise AssertionError("engine work began")

    group = _group(tmp_path)
    monkeypatch.setattr(diagnostics, "metta_engine", refuse)
    for run in (lambda: diagnostics.profile(group, text, budget=_budget()),
                lambda: diagnostics.explain(group, text, budget=_budget()),
                lambda: diagnostics.match(group, [text], budget=_budget()),
                lambda: diagnostics.match(group, ["(gc-diag-edge $x $y)"], where=text, budget=_budget())):
        with pytest.raises(InvalidInputError):
            run()


# am[verifies a-dg-module-1019@7c4558]
def test_a_diagnostic_refuses_a_missing_budget_a_non_group_no_patterns_and_a_bad_row_count(tmp_path):
    group = _group(tmp_path)

    with pytest.raises(InvalidInputError, match="never unbounded"):
        diagnostics.explain(group, "(gc-diag-hop a)", budget=None)
    with pytest.raises(InvalidInputError, match="ModuleGroup"):
        diagnostics.explain("not a group", "(gc-diag-hop a)", budget=_budget())
    for patterns in ([], "(gc-diag-edge $x $y)", None):
        with pytest.raises(InvalidInputError, match="one or more patterns"):
            diagnostics.match(group, patterns, budget=_budget())
    for top in (-1, True, 1.5):
        with pytest.raises(InvalidInputError, match="count of rows"):
            diagnostics.profile(group, "(gc-diag-hop a)", top=top, budget=_budget())


# The engine a diagnostic runs on is the one the process booted: constructing another would fail
# here, and no evaluation pool is started for it.
# am[verifies a-dg-module-1019@7c4558]
def test_diagnostics_run_on_the_processs_one_engine(tmp_path, monkeypatch):
    def refuse(*_arguments: object, **_keywords: object) -> None:
        raise AssertionError("another MeTTa instance was constructed")

    group = _group(tmp_path)
    with metta_engine(None) as before:
        pass
    pool = runtime_engine._POOL
    monkeypatch.setattr(metta, "MeTTa", refuse)

    diagnostics.profile(group, "(gc-diag-hop a)", budget=_budget())
    diagnostics.explain(group, "(gc-diag-hop a)", budget=_budget())
    diagnostics.match(group, ["(gc-diag-edge $x $y)"], budget=_budget())

    with metta_engine(None) as after:
        pass
    assert after is before
    assert runtime_engine._POOL is pool


# am[verifies a-dg-cli-1019@996a1b]
def test_the_command_prints_the_report_for_module_files_and_for_a_packaged_group(tmp_path, capsys):
    module = _module(tmp_path)

    assert cli.main(["diagnose", "match", "--module", str(module), *CLI_LIMITS,
                     "(gc-diag-edge a $y)", "(gc-diag-node $y)"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["verdict"] == "no-joint-binding"
    assert report["group"]["name"].startswith("diagnose-")
    assert cli.main(["diagnose", "profile", "--group", "goal_chainer.bigraph.kernel:GROUP", *CLI_LIMITS,
                     "--top", "3", "(bg-warm-up)"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (report["answers"], report["group"]["space"]) == ([["True"]], "&gc-group-bigraph")
    assert len(report["profile"]["top"]) == 3


# A refusal is the typed error as JSON with a nonzero status: a group that names no importable
# object, an object that is no ModuleGroup, a module path holding a surrogate for bytes that are no
# UTF-8, text that is not one form, and a deadline already past.
# am[verifies a-dg-cli-1019@996a1b]
@pytest.mark.parametrize(("arguments", "code"), [
    (["--group", "goal_chainer.no_such_module:GROUP", *CLI_LIMITS, "(x)"], "invalid_input"),
    (["--group", "goal_chainer.runtime.evaluator:ModuleGroup", *CLI_LIMITS, "(x)"], "invalid_input"),
    (["--group", "goal_chainer.bigraph.kernel", *CLI_LIMITS, "(x)"], "invalid_input"),
    (["--module", "\udcffgroup.metta", *CLI_LIMITS, "(x)"], "invalid_input"),
    (["--module", "MODULE", *CLI_LIMITS, "(a) (b)"], "invalid_input"),
    (["--module", "MODULE", "--inference-budget", "1000", "--timeout-seconds", "1e-9", "(x)"], "review_timeout"),
], ids=["no-module", "not-a-group", "a-module", "surrogate-path", "two-forms", "deadline-past"])
def test_the_command_reports_a_refusal_as_typed_json(tmp_path, capsys, arguments, code):
    module = str(_module(tmp_path))
    arguments = [module if argument == "MODULE" else argument for argument in arguments]

    assert cli.main(["diagnose", "explain", *arguments]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert (payload["ok"], payload["error"]["code"]) == (False, code)


# Resolving --group imports its module, so a used-up budget is refused first and nothing is
# imported.
# am[verifies a-dg-cli-1019@996a1b]
def test_the_command_refuses_a_used_up_budget_before_importing_a_groups_module(tmp_path, monkeypatch, capsys):
    (tmp_path / "gc_diagnostics_probe_group.py").write_text("IMPORTED = True\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    assert cli.main(["diagnose", "profile", "--group", "gc_diagnostics_probe_group:GROUP",
                     "--inference-budget", "1000", "--timeout-seconds", "1e-9", "(x)"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "review_timeout"
    assert "gc_diagnostics_probe_group" not in sys.modules


# No diagnostic runs without both limits: argparse refuses the command before anything runs.
# am[verifies a-dg-cli-1019@996a1b]
@pytest.mark.parametrize("limits", [[], ["--inference-budget", "1000"], ["--timeout-seconds", "10"]])
def test_the_command_requires_both_limits(tmp_path, limits):
    with pytest.raises(SystemExit) as refused:
        cli.main(["diagnose", "explain", "--module", str(_module(tmp_path)), *limits, "(x)"])

    assert refused.value.code == 2

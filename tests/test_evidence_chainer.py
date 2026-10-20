"""Purpose: test where the PeTTaChainer grader is found, that evidence_chainer.grade answers every
PLN statement set recorded in data/pettachainer_petta_beliefs.json as PeTTaChainer answered it on
PeTTa, with or without the backward premise prefilter, that it refuses a malformed statement, a
reused name or a pattern target before anything runs, that an unproved target has no answer while a
false statement is one, that each grading runs under its caller's RunBudget and leaves nothing
behind on any path, that a grading computes each proof's liveness once, and that the group's
warm-up leaves only compilation behind."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
# am[verifies a-integrate-grading-timeout-fixture-1019@e72071]
from types import SimpleNamespace
from typing import Any

import pytest
from metta import parse
# am[verifies a-integrate-grading-timeout-fixture-1019@e72071]
# am[related a-integrate-pymetta-public-errors-1019@05202a]
from metta.errors import InferenceLimitError, TimeLimitError

from goal_chainer import evidence_chainer
from goal_chainer.errors import DependencyUnavailableError, InvalidInputError, ProtocolError
from goal_chainer.evidence_chainer import (
    ENTRY,
    Belief,
    Grading,
    chainer_metta_dir,
    grade,
    grading_arguments,
    grading_group,
    most_confident,
    statement,
)
# am[verifies a-integrate-grading-timeout-fixture-1019@e72071]
from goal_chainer.runtime import budget as runtime_budget
from goal_chainer.runtime.budget import InferenceBudgetExceeded, ReviewTimeout, RunBudget, run_bounded
from goal_chainer.runtime.engine import metta_engine
from record_pettachainer_petta_beliefs import RECORDED
from request_support import budget


# The statement sets, their targets and what PeTTaChainer answered on PeTTa, by label, written by
# record_pettachainer_petta_beliefs.py, since the package does not run PeTTa.
# am[verifies a-hh-gp-tests-1018]
RECORD = json.loads(RECORDED.read_text(encoding="utf-8"))
CASES = {case["label"]: case for case in RECORD["cases"]}


def test_chainer_metta_dir_prefers_vendored_checkout(monkeypatch):
    monkeypatch.delenv("GOALCHAINER_PETTACHAINER_DIR", raising=False)

    root = Path(__file__).resolve().parents[1]

    assert chainer_metta_dir() == root / "external/PeTTaChainer/pettachainer/metta"


def test_chainer_metta_dir_honors_explicit_checkout(tmp_path, monkeypatch):
    metta_dir = tmp_path / "pettachainer/metta"
    metta_dir.mkdir(parents=True)
    (metta_dir / "petta_chainer.metta").write_text("", encoding="utf-8")
    monkeypatch.setenv("GOALCHAINER_PETTACHAINER_DIR", str(tmp_path))

    assert chainer_metta_dir() == metta_dir


# am[verifies a-rt-vendored-defaults-1016@182749]
def test_chainer_metta_dir_rejects_invalid_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GOALCHAINER_PETTACHAINER_DIR", str(tmp_path))

    with pytest.raises(DependencyUnavailableError) as caught:
        chainer_metta_dir()
    assert str(tmp_path) in str(caught.value)


# ---------------------------------------------------------------------------
# What PeTTaChainer answered on PeTTa is what the in-process grading must answer
# ---------------------------------------------------------------------------


# A recorded set's statements and targets as the atoms PeTTa was given, parsed from their text,
# which they print back exactly.
# am[verifies a-hh-gp-tests-1018]
def _inputs(label: str) -> tuple[list[Any], list[Any]]:
    case = CASES[label]
    return [parse(text) for text in case["statements"]], [parse(text) for text in case["targets"]]


# A grading's answers for each target in the record's form, [strength, confidence, answer].
# am[verifies a-hh-gp-tests-1018]
def _answers(grading: Grading) -> list[list[list[Any]]]:
    return [[[belief.strength, belief.confidence, belief.proof] for belief in answers] for answers in grading.answers]


# The recorded answers hold only for what PeTTa was asked, under this step bound and prefilter.
# am[verifies a-hh-gp-tests-1018]
def test_the_record_is_for_this_step_bound_and_prefilter():
    assert (RECORD["query_steps"], RECORD["prefilter"]) == (
        evidence_chainer.QUERY_STEPS, evidence_chainer.BACKWARD_PREMISE_PREFILTER)


# The in-process grading must give every answer PeTTa gave about each target, in order, and none
# where PeTTa proved nothing: the 48 statement sets the incident appraisal made for each policy
# outcome and shape of memory, and sets of other shapes, two-premise rules, chains, revision with a
# false statement, no statements and claims with expression arguments.
@pytest.mark.parametrize("label", sorted(CASES))
# am[verifies a-hh-pc-port-1018] am[verifies a-hh-pc-library-portable-1018] am[verifies a-hh-gp-callable-1018]
# am[verifies a-hh-gp-tests-1018]
def test_grading_answers_as_pettachainer_on_petta(label):
    grading = grade(*_inputs(label), budget=budget())

    assert _answers(grading) == CASES[label]["answers"]
    assert grading.call.startswith(f"!({ENTRY} ")
    assert grading.call.endswith(f" {evidence_chainer.QUERY_STEPS} True)")


# The backward premise prefilter only prunes premises that cannot contribute, so without it every
# set answers the same.
@pytest.mark.parametrize("label", sorted(CASES))
# am[related a-ev-jev-a-one-reader@a39fcd] am[verifies a-hh-pc-port-1018] am[verifies a-hh-gp-tests-1018]
def test_the_backward_premise_prefilter_changes_no_answer(label, monkeypatch):
    monkeypatch.setattr(evidence_chainer, "BACKWARD_PREMISE_PREFILTER", False)

    grading = grade(*_inputs(label), budget=budget())

    assert grading.call.endswith(f" {evidence_chainer.QUERY_STEPS} False)")
    assert _answers(grading) == CASES[label]["answers"]


# ---------------------------------------------------------------------------
# The boundary: unknown is not false, and what crosses it is checked first
# ---------------------------------------------------------------------------


# am[verifies a-hh-gp-callable-1018]
def test_most_confident_takes_the_highest_confidence_and_the_first_of_equals():
    low, high, tied = Belief(0.9, 0.5, "low"), Belief(0.2, 0.8, "high"), Belief(0.7, 0.8, "tied")

    assert most_confident((low, high, tied)) is high
    assert most_confident(()) is None


# A target the chainer proves nothing about has no answer: unknown, not false. A statement of
# strength 0 is an answer, a false belief.
# am[verifies a-hh-gp-callable-1018] am[verifies a-hh-pc-port-1018]
def test_an_unproved_target_has_no_answer_and_a_false_statement_is_one():
    door, window = parse("(Open door)"), parse("(Open window)")

    grading = grade([statement("closed_report", door, 0.0, 0.9)], [door, window], budget=budget())

    assert grading.answers == ((Belief(0.0, 0.9, "(: closed_report (Open door) (STV 0.0 0.9))"),), ())


# What crosses the boundary is checked before the engine runs, so a refused grading charges nothing.
@pytest.mark.parametrize(
    ("statements", "targets", "refusal"),
    (
        ([parse("(Open door)")], [], "is not"),
        ([parse("(= a (Open door) (STV 1.0 0.9))")], [], "is not"),
        ([parse("(: a (Open door))")], [], "is not"),
        ([parse("(: (a) (Open door) (STV 1.0 0.9))")], [], "is not"),
        ([parse("(: a (Open door) (TV 1.0 0.9))")], [], "is not"),
        ([parse("(: a (Open door) (STV 1.5 0.9))")], [], "is not"),
        ([parse("(: a (Open door) (STV 0.5 -0.1))")], [], "is not"),
        ([parse("(: a (Open door) (STV high 0.9))")], [], "is not"),
        ([parse("(: a (Open door) (STV 1" + "0" * 400 + " 0.9))")], [], "is not"),
        ([parse("(: a (Open door) (STV 0.5 -1" + "0" * 400 + "))")], [], "is not"),
        ([statement("a", parse("(Open door)"), float("nan"), 0.9)], [], "is not"),
        ([statement("a", parse("(Open door)"), 1.0, 0.9), statement("a", parse("(Open gate)"), 1.0, 0.9)], [],
         "reuses the name a"),
        ([statement("a", parse("(Open door)"), 1.0, 0.9)], [parse("(Open $what)")], "holds a variable"),
    ),
)
# am[verifies a-hh-gp-callable-1018@f10634] am[verifies a-hh-gp-tests-1018@33d25e] am[verifies a-ev-nr-finite-float-1018@6fcba4]
def test_a_malformed_grading_is_refused_before_anything_runs(statements, targets, refusal):
    allowance = budget()

    with pytest.raises(InvalidInputError, match=refusal):
        grade(statements, targets, budget=allowance)
    assert allowance.spent == 0


# The engine's answer is read as a grammar: (Graded ROWS), ROWS one (TARGET ANSWERS) per target in
# order, ANSWERS beliefs about that target, each collection an expression. An answer malformed
# anywhere, injected here in place of the engine's, is a protocol error, so only an empty
# collection reads as a target the chainer proved nothing about.
@pytest.mark.parametrize(
    ("answer", "targets"),
    (
        ("Broken", []),
        ("(Graded)", []),
        ("(Graded Broken)", []),
        ('(Graded "")', []),
        ("(Graded ())", ["(Open door)"]),
        ("(Graded (((Open gate) ())))", ["(Open door)"]),
        ("(Graded (((Open door) Broken)))", ["(Open door)"]),
        ('(Graded (((Open door) "")))', ["(Open door)"]),
        ("(Graded (((Open door) (Broken))))", ["(Open door)"]),
        ("(Graded (((Open door) ((: p (Open gate) (STV 1.0 0.9))))))", ["(Open door)"]),
        ("(Graded (((Open door) ((: p (Open door) (STV 1.5 0.9))))))", ["(Open door)"]),
    ),
)
# am[verifies a-integrate-pln-result-refusal-1018] am[verifies a-hh-gp-callable-1018]
def test_a_malformed_grading_answer_is_a_protocol_error(answer, targets, monkeypatch):
    monkeypatch.setattr(evidence_chainer.evaluator, "evaluate", lambda *_arguments, **_options: parse(answer))

    with pytest.raises(ProtocolError):
        grade([], [parse(target) for target in targets], budget=budget())


@pytest.mark.parametrize(
    ("answer", "targets", "answers"),
    (
        ("(Graded ())", [], ()),
        ("(Graded (((Open door) ())))", ["(Open door)"], ((),)),
    ),
)
# am[verifies a-integrate-pln-result-refusal-1018] am[verifies a-hh-gp-callable-1018]
def test_only_an_empty_collection_reads_as_unknown(answer, targets, answers, monkeypatch):
    monkeypatch.setattr(evidence_chainer.evaluator, "evaluate", lambda *_arguments, **_options: parse(answer))

    assert grade([], [parse(target) for target in targets], budget=budget()).answers == answers


# ---------------------------------------------------------------------------
# Isolation, budgets and the discard of every write
# ---------------------------------------------------------------------------


# Every space the engine stores natively, by its own storage table, with its atom count, and every
# state cell, read from the engine's self space. A space absent counts as empty.
# am[verifies a-hh-pc-isolation-1018]
def _stores() -> dict[str, int]:
    with metta_engine(None) as engine:
        names = engine.runtime.once("findall(_S, spaces:native_storage_module_cache(_S, _), L)")["L"]
        counts = {str(name): len(engine.run(f"!(collapse (get-atoms {name}))")[0][0].children) for name in names}
        cells = engine.runtime.once(
            "aggregate_all(count, (current_module(_M), predicate_property(_M:metta_state_value(_, _), dynamic), "
            "\\+ predicate_property(_M:metta_state_value(_, _), imported_from(_)), _M:metta_state_value(_, _)), N)")
    counts["state cells"] = int(cells["N"])
    return {name: count for name, count in counts.items() if count}


# A recorded set, the same set with a memory statement about its first target, and a set of another
# shape.
WITHOUT = "incident privacy=True ready=False categories=3 memory=none"
WITH = "incident privacy=True ready=False categories=3 memory=support"
OTHER = "generic: two rules chain backward through an intermediate claim"


# am[verifies a-hh-pc-isolation-1018]
def _baseline() -> tuple[Grading, dict[str, int]]:
    return grade(*_inputs(WITHOUT), budget=budget()), _stores()


# am[verifies a-hh-pc-isolation-1018] am[verifies a-hh-pc-tests-1018] am[verifies a-hh-gp-tests-1018]
def test_a_grading_leaves_no_statement_for_the_next():
    baseline, stores = _baseline()

    with_memory = grade(*_inputs(WITH), budget=budget())
    grade(*_inputs(OTHER), budget=budget())
    again = grade(*_inputs(WITHOUT), budget=budget())

    assert with_memory.answers[0] != baseline.answers[0]
    assert "mem_" in with_memory.answers[0][0].proof
    assert again == baseline
    assert _stores() == stores


# Hold the warmed engine before starting the budget and freeze only the Python deadline clock.
# Native inference and time limits still run, so preparation cannot stand in for an interrupted
# grading. Expiry before grading has its own test below.
@pytest.mark.parametrize(
    ("bound", "error", "native_error"),
    (
        ({"inference_budget": 100_000, "timeout_seconds": 600}, InferenceBudgetExceeded, InferenceLimitError),
        ({"inference_budget": None, "timeout_seconds": 0.01}, ReviewTimeout, TimeLimitError),
    ),
    ids=("inferences", "wall"),
)
# am[verifies a-hh-pc-isolation-1018] am[verifies a-hh-pc-tests-1018] am[verifies a-ev-rb-pipeline-budget-1018@988a39]
# am[verifies a-hh-gp-tests-1018] am[implements a-hh-gp-stopped-budget-at-run-1018]
# am[rests-on c-hh-gp-budget-deadline-at-make-1018]
# am[verifies a-integrate-grading-timeout-fixture-1019@e72071]
def test_a_stopped_grading_is_charged_and_leaves_nothing(bound, error, native_error, monkeypatch):
    baseline, stores = _baseline()

    with metta_engine(None), monkeypatch.context() as patch:
        patch.setattr(runtime_budget, "time", SimpleNamespace(monotonic=lambda: 0.0))
        stopped = RunBudget(**bound)
        with pytest.raises(error) as caught:
            grade(*_inputs(WITH), budget=stopped)

    assert isinstance(caught.value.__cause__, native_error)
    assert stopped.spent > 0
    assert _stores() == stores
    assert grade(*_inputs(WITHOUT), budget=budget()) == baseline


# A request already out of time has no grading work to charge and leaves the same stores intact.
# am[verifies a-integrate-grading-timeout-fixture-1019@e72071]
# am[verifies a-hh-pc-isolation-1018]
def test_a_grading_expired_before_work_is_uncharged_and_leaves_nothing(monkeypatch):
    baseline, stores = _baseline()
    clock = SimpleNamespace(now=0.0)
    clock.monotonic = lambda: clock.now
    with monkeypatch.context() as patch:
        patch.setattr(runtime_budget, "time", clock)
        stopped = RunBudget(inference_budget=None, timeout_seconds=10.0)
        clock.now = 11.0
        with pytest.raises(ReviewTimeout) as caught:
            grade(*_inputs(WITH), budget=stopped)

    assert caught.value.__cause__ is None
    assert stopped.spent == 0
    assert _stores() == stores
    assert grade(*_inputs(WITHOUT), budget=budget()) == baseline


# The engine refuses a state-cell write inside speculation, so a grading followed by one raises
# after the grading wrote its knowledge base, proof store and cells; the scope evaluate uses
# discards them all the same.
# am[verifies a-hh-pc-isolation-1018] am[verifies a-hh-pc-tests-1018] am[verifies a-hh-gp-tests-1018]
def test_a_raised_grading_leaves_nothing():
    baseline, stores = _baseline()
    arguments = grading_arguments(*_inputs(WITH))
    holes = {f"a{index}": argument for index, argument in enumerate(arguments)}
    source = "!(let* (($graded (" + ENTRY + " {a0} {a1} {a2} {a3})) ($refused (change-state! gc_chainer_probe 1))) $graded)"

    with metta_engine(None) as engine:
        space = engine.space(grading_group(budget=None).space)
        with pytest.raises(Exception, match="cannot be written during speculative"):
            with space.speculative():
                run_bounded(space, source, budget=budget(), **holes)

    assert _stores() == stores
    assert grade(*_inputs(WITHOUT), budget=budget()) == baseline


# ---------------------------------------------------------------------------
# A grading computes each proof's liveness once
# ---------------------------------------------------------------------------


# Inside a grading's own call, once the entry has answered: how many rows PeTTaChainer's liveness
# cache holds, how many distinct ones, and whether the chainer's own lookup finds each row's value.
# gc_liveness_rows is a symbol nothing defines, so the answer stays the tuple of the three.
# am[verifies a-hh-gc-live-cache-pure-memo-1018@3505b9]
LIVENESS_PROBE = (
    "!(let* (($graded (" + ENTRY + " {a0} {a1} {a2} {a3}))"
    " ($rows (collapse (get-atoms &proof_live_cache))))"
    " (gc_liveness_rows (size-atom $rows) (size-atom (unique-atom $rows))"
    " (unique-atom (collapse (let ($epoch $pid $alive) (superpose $rows)"
    " (== (collapse (cached-proof-live? $pid)) ($alive)))))))"
)


# Each proof's liveness is computed once and then found. Until PeTTaChainer f6717a4 the cache's
# lookups never matched its rows, so every check recomputed liveness over the proof DAG and stored
# one more row: a single grading of a recorded set left (0 0 true) fourteen times, and overlapping
# gradings stalled in that recomputation.
@pytest.mark.parametrize("label", (WITH, OTHER))
# am[verifies a-hh-gc-live-cache-pure-memo-1018@3505b9]
def test_a_grading_computes_each_proofs_liveness_once(label):
    grade(*_inputs(label), budget=budget())
    arguments = grading_arguments(*_inputs(label))
    holes = {f"a{index}": argument for index, argument in enumerate(arguments)}

    with metta_engine(None) as engine:
        space = engine.space(grading_group(budget=None).space)
        with space.speculative():
            answers, _ = run_bounded(space, LIVENESS_PROBE, budget=budget(), **holes)

    _, rows, distinct, found = answers[0][0].children
    assert int(str(rows)) > 0
    assert str(distinct) == str(rows)
    assert str(found) == "(True)"


# ---------------------------------------------------------------------------
# The warm-up leaves only compilation and declared preparation behind
# ---------------------------------------------------------------------------


# Run in a fresh process, since this process's group is already prepared: load the group's modules
# as prepare does, stop one round of warm-ups by its deadline, run every warm-up to its end, and
# report the state before and after: every space's atoms, the group space's atoms themselves, every
# dynamic predicate's clause count and lib_memo's automatic selections and entries.
WARM_UP_PROBE = r"""
import json, re
from collections import Counter
from goal_chainer import evidence_chainer as chainer
from goal_chainer.runtime.budget import ReviewTimeout, RunBudget, run_bounded
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.modules import load_metta_module

def canonical(text):
    names = {}
    return re.sub(r"\$[A-Za-z0-9_#'-]+", lambda m: names.setdefault(m.group(0), f"$v{len(names)}"), text)

def state(engine, space):
    names = engine.runtime.once("findall(_S, spaces:native_storage_module_cache(_S, _), L)")["L"]
    stores = {str(n): len(engine.run(f"!(collapse (get-atoms {n}))")[0][0].children) for n in names}
    clauses = {}
    for row in engine.runtime.once(
            "findall(_S, (current_module(_M), current_predicate(_M:_P/_A), functor(_H, _P, _A), "
            "predicate_property(_M:_H, dynamic), \\+ predicate_property(_M:_H, imported_from(_)), "
            "predicate_property(_M:_H, number_of_clauses(_N)), format(atom(_S), '~q:~q/~q=~d', [_M, _P, _A, _N])), L)")["L"]:
        key, _, count = str(row).rpartition("=")
        clauses[key] = int(count)
    own = Counter(canonical(str(a)) for a in space.run("!(collapse (get-atoms &self))")[0][0].children)
    automatic = sorted(str(f) for f in engine.runtime.once("findall(_F, lib_memo:memo_automatic_enabled(_F, _), L)")["L"])
    entries = sorted({str(f) for f in engine.runtime.once("findall(_F, lib_memo:metta_memo_entry(_F, _, _, _, _, _), L)")["L"]})
    return {"stores": stores, "clauses": clauses, "own": own, "automatic": automatic, "entries": entries}

group = chainer.grading_group(budget=None)
with metta_engine(None) as engine:
    space = engine.space(group.space)
    for module in group.modules:
        load_metta_module(engine, module, space=space)
    before = state(engine, space)
    try:
        for warm_up in group.warm_ups:
            run_bounded(space, f"!({warm_up})", budget=RunBudget(inference_budget=None, timeout_seconds=0.5))
        stopped = False
    except ReviewTimeout:
        stopped = True
    answers = [str(a) for warm_up in group.warm_ups
               for g in run_bounded(space, f"!({warm_up})", budget=RunBudget(inference_budget=None, timeout_seconds=600))[0]
               for a in g]
    after = state(engine, space)
print("RESULT " + json.dumps({
    "stopped": stopped, "answers": answers, "warm_ups": len(group.warm_ups),
    "stores": [before["stores"], after["stores"]],
    "clauses": [before["clauses"], after["clauses"]],
    "added": sorted((after["own"] - before["own"]).elements()),
    "removed": sorted((before["own"] - after["own"]).elements()),
    "automatic": after["automatic"], "entries": after["entries"],
}))
"""

# Compilation's own records: translated forms and their supports, function registrations,
# higher-order specializations, dispatch caches, the storage table naming the chainer's spaces, the
# automatic memo tables lib_memo keeps for pure functions, and the engine's hook and call caches.
COMPILATION_MODULES = ("filereader", "translator", "specializer", "support_graph", "metta_engine", "seam",
                       "spaces", "lib_memo", "prolog", "janus")


# am[verifies a-hh-pc-warm-up-proof-1018] am[rests-on c-hh-pc-warm-up-leftovers-1018]
def test_the_warm_up_leaves_only_compilation_behind():
    result = subprocess.run([sys.executable, "-c", WARM_UP_PROBE], capture_output=True, text=True,
                            env=os.environ.copy(), check=True)
    report = json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
    before_stores, after_stores = report["stores"]
    before_clauses, after_clauses = report["clauses"]
    group_space = grading_group(budget=None).space

    assert report["stopped"] and report["answers"] == ["True"] * report["warm_ups"] and report["warm_ups"] >= 1
    # No space holds an atom it did not hold after loading, apart from the group's own space.
    changed = {name: (before_stores.get(name, 0), count) for name, count in after_stores.items()
               if count != before_stores.get(name, 0)}
    assert set(changed) <= {group_space, "&self"}
    # The group's own space gained only the engine's specializations of higher-order functions.
    assert report["added"] and not report["removed"]
    assert all(re.match(r"\(= \([^ ()]*_Spec_", atom) for atom in report["added"])
    # Every other change is a compilation record; no space's storage module and no state cell moved.
    moved = {key for key in before_clauses.keys() | after_clauses.keys()
             if before_clauses.get(key, 0) != after_clauses.get(key, 0)}
    assert all(key.startswith(COMPILATION_MODULES) for key in moved), sorted(moved)
    # What lib_memo cached belongs to functions it selected itself, which it does only for pure ones.
    assert set(report["entries"]) <= set(report["automatic"])

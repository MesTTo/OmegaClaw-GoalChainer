"""Purpose: verify goal_chainer.runtime, the in-process pymetta engine host, on the real engine:
setup groups retried until they succeed whole, modules imported once and only after they load, each
load answering the digest of what it imported and refusing bytes changed since or during the import,
failed imports restoring pre-existing equations, a module imported once into each named space,
library bindings, run budgets shared by every stage of a run, refusals naming a bound repr cannot
write, no stage charged a thread's or the process's first use, each thread's warm-up bound by its
caller's deadline and made again after a
stop, holes that carry text as one atom, and concurrent callers."""

# am[implements a-integrate-warmup-compose-gate-1019@8b4d00]

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import time
from concurrent import futures
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import metta
import pytest
from metta import S, V

from goal_chainer.runtime.budget import (
    InferenceBudgetExceeded,
    ReviewTimeout,
    RunBudget,
    caller_budget,
    run_bounded,
)
from goal_chainer.runtime import budget as runtime_budget
from goal_chainer.runtime import engine as runtime_engine
from goal_chainer.runtime.modules import (
    MettaLibrary,
    initialize_once,
    load_metta_module,
    register_metta_library,
    tree_digest,
)
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.evaluator import plain_value
from goal_chainer.errors import MettaEngineError, ModuleChanged
from goal_chainer.errors import DependencyUnavailableError, InvalidInputError

# Counts down from N, one engine step per level, so its cost grows with N.
SPIN = "(= (gc-host-spin $n) (if (== $n 0) done (gc-host-spin (- $n 1))))"


# The engine is one per process, so every head and key a test defines is prefixed and unique.
# am[verifies a-rt-pymetta-engine-1016@296784]
@pytest.fixture(scope="module")
def spin_defined() -> None:
    with metta_engine(None) as engine:
        engine.run(SPIN)


# am[verifies a-rt-pymetta-engine-1016@296784]
def _quoted(path: Path) -> str:
    return '"' + str(path) + '"'


# am[verifies a-rt-initialize-once-1016@0767f5]
def test_a_setup_that_raises_runs_again_whole_until_it_succeeds(tmp_path):
    calls: list[str] = []

    def setup(engine):
        calls.append("setup")
        if len(calls) == 1:
            raise RuntimeError("first attempt fails after starting")
        engine.run("(= (gc-host-ready) yes)")

    with metta_engine(None) as engine:
        with pytest.raises(RuntimeError):
            initialize_once(f"gc-host-group-{tmp_path.name}", setup, budget=None)
        initialize_once(f"gc-host-group-{tmp_path.name}", setup, budget=None)
        initialize_once(f"gc-host-group-{tmp_path.name}", setup, budget=None)
        answer = engine.run("!(gc-host-ready)")

    assert calls == ["setup", "setup"]
    assert [[str(atom) for atom in group] for group in answer] == [["yes"]]


# pymetta defines nothing from a file whose load raised, so the module is imported again, whole,
# once its missing dependency exists.
# am[verifies a-rt-pymetta-engine-1016@296784]
def test_a_module_is_recorded_only_after_its_import_succeeds(tmp_path):
    dependency = tmp_path / "gc_host_dependency.metta"
    module = tmp_path / "gc_host_module.metta"
    module.write_text(
        f"(= (gc-host-before) defined)\n!(import! &self {_quoted(dependency)})\n"
        "(= (gc-host-after) (gc-host-dependency))\n"
    )

    with metta_engine(None) as engine:
        with pytest.raises(Exception, match="does not exist"):
            load_metta_module(engine, module)
        assert [str(a) for g in engine.run("!(gc-host-before)") for a in g] == ["(gc-host-before)"]
        dependency.write_text("(= (gc-host-dependency) here)\n")
        load_metta_module(engine, module)
        load_metta_module(engine, module)
        answers = engine.run("!(gc-host-before)\n!(gc-host-after)")

    assert [[str(atom) for atom in group] for group in answers] == [["defined"], ["here"]]


# am[verifies a-rt-loaded-identity-1016@e4ffa3]
def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# am[verifies a-rt-loaded-identity-1016@e4ffa3]
def _answers(engine, source: str) -> list[list[str]]:
    return [[str(atom) for atom in group] for group in engine.run(source)]


# A file is keyed by its resolved path, so a second spelling of it, through `..` or a symlink, is
# answered from the same record.
# am[verifies a-rt-loaded-identity-1016@e4ffa3]
def test_a_file_load_answers_the_digest_of_its_bytes_under_any_spelling(tmp_path):
    text = "(= (gc-host-digest) one)\n"
    module = tmp_path / "gc_host_digest.metta"
    module.write_text(text)
    (tmp_path / "sub").mkdir()
    (tmp_path / "link").symlink_to(tmp_path, target_is_directory=True)

    with metta_engine(None) as engine:
        answers = [
            load_metta_module(engine, spelling)
            for spelling in (module, tmp_path / "sub" / ".." / module.name, tmp_path / "link" / module.name)
        ]
        called = _answers(engine, "!(gc-host-digest)")

    assert answers == [_sha256(text)] * 3
    assert called == [["one"]]


# The engine keeps what it imported, so new bytes are refused under every spelling, never loaded
# over the old ones or reported under a digest the engine does not run.
# am[verifies a-rt-loaded-identity-1016@e4ffa3]
def test_a_module_changed_after_its_load_is_refused_and_the_engine_keeps_it(tmp_path):
    before, after = "(= (gc-host-changed) before)\n", "(= (gc-host-changed) after)\n"
    module = tmp_path / "gc_host_changed.metta"
    module.write_text(before)
    (tmp_path / "sub").mkdir()

    with metta_engine(None) as engine:
        load_metta_module(engine, module)
        module.write_text(after)
        with pytest.raises(ModuleChanged) as caught:
            load_metta_module(engine, tmp_path / "sub" / ".." / module.name)
        with pytest.raises(ModuleChanged):
            load_metta_module(engine, module)
        called = _answers(engine, "!(gc-host-changed)")

    assert caught.value.code == "module_changed"
    assert dict(caught.value.details) == {
        "path": str(module.resolve()), "loaded": _sha256(before), "current": _sha256(after),
    }
    assert "fresh process" in caught.value.message
    assert called == [["before"]]


# The engine whose import a concurrent writer races: the bytes change between the two digests.
# am[verifies a-rt-loaded-identity-1016@e4ffa3]
class _RacedEngine:
    def __init__(self, engine, path, text: str) -> None:
        self.engine, self.path, self.text = engine, path, text

    def run(self, source, **options):
        answer = self.engine.run(source, **options)
        self.path.write_text(self.text)
        return answer

    # am[verifies a-integrate-import-transaction-1017]
    def transaction(self, target):
        return self.engine.transaction(target)


# Bytes that change while the import runs leave the module unrecorded, and the next load imports
# the bytes that are there then.
# am[verifies a-rt-loaded-identity-1016@e4ffa3] am[rests-on c-rt-reimport-replaces-1016@4a932b]
# am[verifies a-integrate-import-transaction-1017]
def test_a_module_changed_during_its_import_is_not_recorded(tmp_path):
    first, second = "(= (gc-host-raced) first)\n", "(= (gc-host-raced) second)\n"
    module = tmp_path / "gc_host_raced.metta"
    module.write_text(first)

    with metta_engine(None) as engine:
        with pytest.raises(ModuleChanged) as caught:
            load_metta_module(_RacedEngine(engine, module, second), module)
        assert _answers(engine, "!(gc-host-raced)") == [["(gc-host-raced)"]]
        answer = load_metta_module(engine, module)
        called = _answers(engine, "!(gc-host-raced)")

    assert "while it was being imported" in caught.value.message
    assert (caught.value.loaded, caught.value.current) == (_sha256(first), _sha256(second))
    assert answer == _sha256(second)
    assert called == [["second"]]


# am[verifies a-rt-loaded-identity-1016@e4ffa3]
def test_a_library_load_answers_the_digest_of_its_bound_directory(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    (library / "gc_host_digest_library.metta").write_text("(= (gc-host-digest-library) bound)\n")
    name = f"gc_host_digest_{tmp_path.name.replace('-', '_')}"

    with metta_engine(None) as engine:
        with pytest.raises(DependencyUnavailableError, match="not registered"):
            load_metta_module(engine, MettaLibrary(name, "gc_host_digest_library"))
        register_metta_library(name, library, budget=None)
        answer = load_metta_module(engine, MettaLibrary(name, "gc_host_digest_library"))
        called = _answers(engine, "!(gc-host-digest-library)")

    assert answer == tree_digest(library.resolve())
    assert called == [["bound"]]


# am[verifies a-rt-loaded-identity-1016@e4ffa3]
def test_a_missing_file_and_a_text_spec_are_refused(tmp_path):
    with metta_engine(None) as engine:
        with pytest.raises(DependencyUnavailableError, match="No MeTTa module"):
            load_metta_module(engine, tmp_path / "absent.metta")
        with pytest.raises(TypeError, match="Path or a MettaLibrary"):
            load_metta_module(engine, _quoted(tmp_path / "absent.metta"))


# pymetta would import the outer module and answer True while the inner file's forms never arrive,
# so the inner file is read first and the import refused naming it, before either defines anything.
# am[verifies a-rt-loader-refuses-unparsed-1018@d138df]
def test_a_module_importing_one_that_does_not_parse_is_refused_before_either_loads(tmp_path):
    inner = tmp_path / "gc_host_unparsed_inner.metta"
    inner.write_text("(= (gc-host-unparsed-inner) 1))\n")
    outer = tmp_path / "gc_host_unparsed_outer.metta"
    outer.write_text(f"!(import! &self {_quoted(inner)})\n(= (gc-host-unparsed-outer) 2)\n")

    with metta_engine(None) as engine:
        for _attempt in range(2):
            with pytest.raises(MettaEngineError, match="does not parse") as refused:
                load_metta_module(engine, outer)
            assert refused.value.details["path"] == str(inner.resolve())
        assert _answers(engine, "!(gc-host-unparsed-outer)") == [["(gc-host-unparsed-outer)"]]
        inner.write_text("(= (gc-host-unparsed-inner) 1)\n")
        load_metta_module(engine, outer)
        assert _answers(engine, "!(gc-host-unparsed-outer)\n!(gc-host-unparsed-inner)") == [["2"], ["1"]]


# A library's modules import one another by relative name, so a file anywhere in its directory that
# does not parse refuses the library's import, naming that file.
# am[verifies a-rt-loader-refuses-unparsed-1018@d138df]
def test_a_library_holding_a_file_that_does_not_parse_is_refused(tmp_path):
    library = tmp_path / "library"
    (library / "parts").mkdir(parents=True)
    (library / "gc_host_unparsed_library.metta").write_text(
        "!(import! &self parts/broken)\n(= (gc-host-unparsed-library) 1)\n"
    )
    (library / "parts" / "broken.metta").write_text("(= (gc-host-unparsed-broken) 1))\n")
    name = f"gc_host_unparsed_{tmp_path.name.replace('-', '_')}"

    with metta_engine(None) as engine:
        register_metta_library(name, library, budget=None)
        with pytest.raises(MettaEngineError, match="does not parse") as refused:
            load_metta_module(engine, MettaLibrary(name, "gc_host_unparsed_library"))
        assert _answers(engine, "!(gc-host-unparsed-library)") == [["(gc-host-unparsed-library)"]]

    assert refused.value.details["path"] == str((library / "parts" / "broken.metta").resolve())


# A space whose import answers nothing, as pymetta's does for a file its reader cannot read, is
# refused even for a file that parses, and nothing is recorded, so the next call tries again.
# am[verifies a-rt-loader-refuses-unparsed-1018@d138df]
def test_an_import_answering_other_than_true_once_is_refused_and_not_recorded(tmp_path):
    module = tmp_path / "gc_host_unanswered.metta"
    module.write_text("(= (gc-host-unanswered) 1)\n")
    runs = []

    # am[verifies a-rt-loader-refuses-unparsed-1018@d138df]
    class Silent:
        name = "gc-host-silent"

        def run(self, source, **holes):
            runs.append(source)
            return [[]]

        def transaction(self, body):
            body()

    with metta_engine(None) as engine:
        for _attempt in range(2):
            with pytest.raises(MettaEngineError, match="not True once"):
                load_metta_module(engine, module, space=Silent())

    assert len(runs) == 2


# A Python module is no MeTTa source: pymetta imports it through Python's loader, so the MeTTa
# reader never reads it, and a MeTTa module importing one still loads.
# am[verifies a-rt-loader-refuses-unparsed-1018@d138df]
def test_a_python_module_is_imported_without_the_metta_reader(tmp_path):
    helper = tmp_path / "gc_host_python_helper.py"
    helper.write_text('"""A docstring the MeTTa reader would refuse."""\nVALUE = 1\n')
    module = tmp_path / "gc_host_python_importer.metta"
    module.write_text(f"!(import! &self {_quoted(helper)})\n(= (gc-host-python-importer) loaded)\n")

    with metta_engine(None) as engine:
        assert load_metta_module(engine, helper) == _sha256(helper.read_text())
        load_metta_module(engine, module)
        assert _answers(engine, "!(gc-host-python-importer)") == [["loaded"]]


# A module the digest cannot read is a dependency failure like a missing one, never a bare OSError.
# am[verifies a-rt-loaded-identity-1016@e4ffa3]
def test_an_unreadable_module_is_a_dependency_failure(tmp_path):
    module = tmp_path / "gc_host_unreadable.metta"
    module.write_text("(= (gc-host-unreadable) never)\n")
    module.chmod(0)
    try:
        with metta_engine(None) as engine:
            with pytest.raises(DependencyUnavailableError, match="Cannot read") as caught:
                load_metta_module(engine, module)
    finally:
        module.chmod(0o600)

    assert caught.value.details["path"] == str(module.resolve())


# A deadline already spent stops the load before it starts, and nothing is recorded for it.
# am[verifies a-rt-bounded-preparation-1016@e7eb12]
def test_a_load_past_its_deadline_raises_review_timeout_and_records_nothing(tmp_path):
    text = "(= (gc-host-late) loaded)\n"
    module = tmp_path / "gc_host_late.metta"
    module.write_text(text)
    budget = RunBudget(inference_budget=None, timeout_seconds=0.05)
    time.sleep(0.06)

    with metta_engine(None) as engine:
        with pytest.raises(ReviewTimeout):
            load_metta_module(engine, module, budget=budget)
        assert _answers(engine, "!(gc-host-late)") == [["(gc-host-late)"]]
        answer = load_metta_module(engine, module)
        called = _answers(engine, "!(gc-host-late)")

    assert answer == _sha256(text)
    assert called == [["loaded"]]


# A binding takes the engine itself, so a caller holding nothing binds, binds again and is refused a
# second directory, and the module still loads from the first.
# am[verifies a-rt-pymetta-engine-1016@296784] am[verifies a-rt-cc-rw-pool-1018]
def test_a_library_name_stays_bound_to_its_first_directory(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "gc_host_library.metta").write_text("(= (gc-host-library-origin) first)\n")
    name = f"gc_host_library_{tmp_path.name.replace('-', '_')}"

    register_metta_library(name, first, budget=None)
    register_metta_library(name, first, budget=None)
    with pytest.raises(DependencyUnavailableError, match="already bound"):
        register_metta_library(name, second, budget=None)
    with metta_engine(None) as engine:
        load_metta_module(engine, MettaLibrary(name, "gc_host_library"))
        answer = engine.run("!(gc-host-library-origin)")

    assert [str(atom) for group in answer for atom in group] == ["first"]


# am[verifies a-rt-run-budget-1016@e046b0]
def test_a_run_is_charged_what_it_spent(spin_defined):
    budget = RunBudget(inference_budget=10_000_000, timeout_seconds=60.0)
    with metta_engine(None) as engine:
        answers, used = run_bounded(engine, "!(gc-host-spin 2000)", budget=budget)

    assert [str(atom) for group in answers for atom in group] == ["done"]
    assert used > 2000
    assert budget.spent == used


# A count that fell was read on two engines; crediting it would raise what the run may still spend,
# so it is refused and the budget keeps its spend.
# am[verifies a-rt-run-budget-1016@e046b0] am[verifies a-rt-cc-rw-pool-1018]
def test_a_falling_inference_count_is_refused_not_credited():
    budget = RunBudget(inference_budget=1_000, timeout_seconds=60.0)
    budget.charge(400)

    with pytest.raises(MettaEngineError, match="count fell"):
        budget.charge(-5)

    assert budget.spent == 400
    assert budget.remaining()[0] == 600


# A later stage gets only what earlier stages left, and its stop names the whole bound and the
# whole spend, never a share.
# am[verifies a-rt-run-budget-1016@e046b0]
def test_a_later_stage_cannot_get_a_reset_inference_bound(spin_defined):
    with metta_engine(None) as engine:
        _, one_run = run_bounded(
            engine,
            "!(gc-host-spin 2000)",
            budget=RunBudget(inference_budget=10_000_000, timeout_seconds=60.0),
        )
        budget = RunBudget(inference_budget=one_run + one_run // 2, timeout_seconds=60.0)
        run_bounded(engine, "!(gc-host-spin 2000)", budget=budget)
        with pytest.raises(InferenceBudgetExceeded) as caught:
            run_bounded(engine, "!(gc-host-spin 2000)", budget=budget)

    assert caught.value.budget == one_run + one_run // 2
    assert caught.value.used == budget.spent
    assert caught.value.used >= caught.value.budget
    assert caught.value.code == "inference_budget_exceeded"


# am[verifies a-rt-run-budget-1016@e046b0]
def test_an_exhausted_budget_starts_no_further_stage(spin_defined):
    budget = RunBudget(inference_budget=1_000, timeout_seconds=60.0)
    with metta_engine(None) as engine:
        with pytest.raises(InferenceBudgetExceeded):
            run_bounded(engine, "!(gc-host-spin 100000)", budget=budget)
        spent = budget.spent
        with pytest.raises(InferenceBudgetExceeded) as caught:
            run_bounded(engine, "!(gc-host-spin 1)", budget=budget)

    assert budget.spent == spent
    assert (caught.value.budget, caught.value.used) == (1_000, spent)


# The deadline runs from when the budget was made, so time spent before a stage is gone for it.
# am[verifies a-rt-run-budget-1016@e046b0]
def test_the_deadline_is_shared_by_every_stage(spin_defined):
    budget = RunBudget(inference_budget=None, timeout_seconds=0.2)
    time.sleep(0.25)
    with metta_engine(None) as engine:
        with pytest.raises(ReviewTimeout) as caught:
            run_bounded(engine, "!(gc-host-spin 1)", budget=budget)

    assert caught.value.timeout_seconds == 0.2
    assert budget.spent == 0


# am[verifies a-rt-run-budget-1016@e046b0]
def test_the_wall_bound_stops_a_running_stage_and_charges_it(spin_defined):
    budget = RunBudget(inference_budget=None, timeout_seconds=0.05)
    with metta_engine(None) as engine:
        with pytest.raises(ReviewTimeout):
            run_bounded(
                engine,
                "!(with-pragma! ((max-stack-depth 1000000000)) (gc-host-spin 100000000))",
                budget=budget,
            )

    assert budget.spent > 0


# A fresh interpreter, whose first bounded stage is the process's and whose pool workers run their
# first work in it: a stage spends the same on the booting thread, first or second, and on every
# worker, fresh or used, since each thread pays its own and the process's first use before its first
# work. Twice as many stages as workers put a second stage on some worker whatever the pool's order.
# am[verifies a-rt-det-warm-thread-1019@199c44]
def test_no_stage_is_charged_a_threads_or_the_processs_first_use():
    script = (
        "import json\n"
        "from goal_chainer.runtime.budget import RunBudget, run_bounded\n"
        "from goal_chainer.runtime.engine import POOL_WORKERS, metta_engine, shared_evaluation\n"
        "def stage(engine):\n"
        "    with engine.speculate():\n"
        "        return run_bounded(engine, '!(+ 1 1)', budget=RunBudget(inference_budget=10_000, timeout_seconds=60.0))[1]\n"
        "with metta_engine(None) as engine:\n"
        "    home = [stage(engine), stage(engine)]\n"
        "pooled = [shared_evaluation(stage, budget=None) for _ in range(2 * POOL_WORKERS)]\n"
        "print(json.dumps({'home': home, 'pooled': pooled}))\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    measured = json.loads(result.stdout.splitlines()[-1])

    assert measured["home"][0] == measured["home"][1]
    assert set(measured["pooled"]) == {measured["home"][0]}


# An engine standing in for pymetta's in the warm-up tests. Each run answers nothing and is recorded
# with its source and bounds; the runs given bounds are the warm-ups, since the tests' own work
# passes none, and the warm-ups `stops` names by their order stop as pymetta stops a run at its time
# bound, after `stall` seconds or that bound if it comes sooner.
# am[verifies a-integrate-warm-thread-deadline-1019@add254]
class _ScriptedEngine:
    def __init__(self, stops: frozenset[int], stall: float = 0.0) -> None:
        self.runs: list[tuple[str, dict]] = []
        self.stops = stops
        self.stall = stall

    @contextmanager
    def speculate(self):
        yield

    # am[related a-integrate-pymetta-public-errors-1019@05202a]
    def run(self, source: str, **bounds) -> list:
        from metta.errors import TimeLimitError

        warm_ups = sum(1 for _, given in self.runs if given)
        self.runs.append((source, bounds))
        if bounds and warm_ups in self.stops:
            time.sleep(min(self.stall, bounds["timeout"]))
            raise TimeLimitError("stopped at its time bound")
        return []


# What attaching a thread to the stand-in engine does: nothing. pymetta's own engine_thread would boot
# the real engine beside it.
# am[verifies a-integrate-warm-thread-deadline-1019@add254]
@contextmanager
def _no_attachment():
    yield


# A pool that starts each work on a thread of its own before submit returns, so the caller always
# waits on started work, which cancelling cannot withdraw.
# am[verifies a-integrate-warm-thread-deadline-1019@add254]
class _StartedPool:
    def submit(self, work, *arguments):
        future: futures.Future = futures.Future()
        future.set_running_or_notify_cancel()

        def run() -> None:
            try:
                future.set_result(work(*arguments))
            except BaseException as error:
                future.set_exception(error)

        threading.Thread(target=run).start()
        return future


# A worker warms its thread before its first work, under the caller's deadline. A stopped warm-up
# raises the caller's ReviewTimeout and runs no work; one stopped for a caller outside any request
# lets the work run; either leaves the thread cold, so its next work warms it again, and after one
# finishes the thread's work runs without another. The calls run on one fresh thread, as one worker.
# am[verifies a-integrate-warm-thread-deadline-1019@add254]
def test_a_stopped_warm_up_leaves_its_thread_cold_for_its_next_work(monkeypatch):
    engine = _ScriptedEngine(stops=frozenset({0, 1}))
    monkeypatch.setattr(runtime_engine, "_ENGINE", engine)
    monkeypatch.setattr(runtime_engine, "_WARMED", threading.local())
    outcomes: list[object] = []

    def worker() -> None:
        for budget in (RunBudget(inference_budget=None, timeout_seconds=30.0), None, None,
                       RunBudget(inference_budget=None, timeout_seconds=30.0)):
            try:
                outcomes.append(runtime_engine._shared_work(lambda held: held.run("!(work)") or "worked", budget))
            except ReviewTimeout as stopped:
                outcomes.append(("stopped", stopped.timeout_seconds))

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    warm_ups = [bounds for _, bounds in engine.runs if bounds]

    assert outcomes == [("stopped", 30.0), "worked", "worked", "worked"]
    assert [source for source, bounds in engine.runs if not bounds] == ["!(work)"] * 3
    assert len(warm_ups) == 3
    assert 0 < warm_ups[0]["timeout"] <= 30.0
    assert [bounds["timeout"] for bounds in warm_ups[1:]] == [60.0, 60.0]


# The booting thread warms under its caller's deadline before its block. A stopped warm-up raises the
# caller's ReviewTimeout before the block runs and leaves the engine booted and the thread cold, so the
# thread's next block warms it again, and the one after runs without a warm-up.
# am[verifies a-integrate-warm-thread-deadline-1019@add254]
def test_a_stopped_boot_warm_up_is_made_again_at_the_booting_threads_next_block(monkeypatch):
    engine = _ScriptedEngine(stops=frozenset({0}))
    monkeypatch.setattr(runtime_engine, "_ENGINE", None)
    monkeypatch.setattr(runtime_engine, "_ENGINE_ENVIRONMENT", {})
    monkeypatch.setattr(runtime_engine, "_BOOT_THREAD", None, raising=False)
    monkeypatch.setattr(runtime_engine, "_WARMED", threading.local())
    monkeypatch.setattr(metta, "MeTTa", lambda: engine)
    monkeypatch.setattr(metta.parallel, "engine_thread", _no_attachment)
    outcomes: list[object] = []

    def booting() -> None:
        for _ in range(3):
            try:
                with metta_engine(RunBudget(inference_budget=None, timeout_seconds=30.0)) as held:
                    outcomes.append(held is engine)
            except ReviewTimeout as stopped:
                outcomes.append(("stopped", stopped.timeout_seconds))

    thread = threading.Thread(target=booting)
    thread.start()
    thread.join()

    assert outcomes == [("stopped", 30.0), True, True]
    assert len(engine.runs) == 2
    assert all(0 < bounds["timeout"] <= 30.0 for _, bounds in engine.runs)


# A caller waits for work a worker has started past its own deadline, since that work charges the
# caller's budget, so the work runs under that deadline, its thread's warm-up included: a warm-up the
# engine stops at the caller's deadline ends the wait with the caller's ReviewTimeout, where one
# bounded by a fixed minute kept the caller waiting until the engine stopped it and then ran the work.
# am[verifies a-integrate-warm-thread-deadline-1019@add254]
def test_a_started_works_warm_up_stops_at_the_callers_deadline(monkeypatch):
    engine = _ScriptedEngine(stops=frozenset({0}), stall=2.0)
    monkeypatch.setattr(runtime_engine, "_ENGINE", engine)
    monkeypatch.setattr(runtime_engine, "_WARMED", threading.local())
    monkeypatch.setattr(runtime_engine, "_POOL", _StartedPool())
    worked: list[object] = []

    with pytest.raises(ReviewTimeout) as stopped:
        runtime_engine.shared_evaluation(worked.append, budget=RunBudget(inference_budget=None, timeout_seconds=0.3))

    [(_, bounds)] = engine.runs
    assert stopped.value.timeout_seconds == 0.3
    assert worked == []
    assert 0 < bounds["timeout"] <= 0.3


# am[verifies a-rt-run-budget-1016@e046b0]
def test_a_text_hole_enters_as_one_string_atom():
    text = 'a "quoted" (paren) ; not a comment'
    with metta_engine(None) as engine:
        engine.run("(= (gc-host-echo $x) $x)")
        answers, _ = run_bounded(
            engine,
            "!(gc-host-echo {text})",
            budget=RunBudget(inference_budget=1_000_000, timeout_seconds=60.0),
            text=text,
        )

    [[atom]] = answers
    assert type(atom).__name__ == "Grounded" and atom.value == text


# An engine whose guard interrupt the program caught: the run returns, having spent more than it
# was given. That spend is the only sign, so the run is exhausted, not answered.
# am[verifies a-rt-spend-over-remaining-1016@70b7b8]
class _SwallowingEngine:
    def __init__(self, spend: int) -> None:
        self.spend = spend
        self.bounds: list[tuple[int | None, float]] = []

    @contextmanager
    def stats(self):
        counter = SimpleNamespace(inferences=0)
        yield counter
        counter.inferences = self.spend

    def run(self, source, *, inferences, timeout, **holes):
        self.bounds.append((inferences, timeout))
        return [["answer"]]


# am[verifies a-rt-spend-over-remaining-1016@70b7b8]
def test_a_run_that_spent_more_than_it_had_left_is_exhausted():
    budget = RunBudget(inference_budget=1_000, timeout_seconds=60.0)
    engine = _SwallowingEngine(spend=1_500)
    with pytest.raises(InferenceBudgetExceeded) as caught:
        run_bounded(engine, "!(anything)", budget=budget)

    assert engine.bounds[0][0] == 1_000
    assert (caught.value.budget, caught.value.used) == (1_000, 1_500)
    assert budget.spent == 1_500


# am[verifies a-rt-spend-over-remaining-1016@70b7b8]
def test_a_run_within_what_it_had_left_answers():
    budget = RunBudget(inference_budget=1_000, timeout_seconds=60.0)
    answers, used = run_bounded(_SwallowingEngine(spend=1_000), "!(anything)", budget=budget)

    assert (answers, used, budget.spent) == ([["answer"]], 1_000, 1_000)


# am[verifies a-rt-pymetta-engine-1016@296784]
def test_answers_read_as_plain_values():
    with metta_engine(None) as engine:
        [[atom]] = engine.run('!(quote (f "s" 1 2.5 True $x (g ()) None "None"))')

    value = plain_value(atom)
    assert value == (S.f, "s", 1, 2.5, True, V.x, (S.g, ()), S["None"], "None")
    assert value[7] != value[8]


# Concurrent callers each hold the engine for their whole run, so every answer is its own.
# am[verifies a-rt-pymetta-engine-1016@296784]
def test_concurrent_callers_each_get_their_own_answer():
    with metta_engine(None) as engine:
        engine.run("(= (gc-host-double $n) (* 2 $n))")
    answers: dict[int, list[str]] = {}

    def call(n: int) -> None:
        with metta_engine(None) as engine:
            result, _ = run_bounded(
                engine,
                "!(gc-host-double {n})",
                budget=RunBudget(inference_budget=1_000_000, timeout_seconds=60.0),
                n=n,
            )
        answers[n] = [str(atom) for group in result for atom in group]

    threads = [threading.Thread(target=call, args=(n,)) for n in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert answers == {n: [str(2 * n)] for n in range(16)}


# am[verifies a-rt-run-budget-1016@e046b0]
@pytest.mark.parametrize("inference_budget", [0, -1, True, 1.5, "100"])
def test_an_inference_budget_is_a_positive_integer_or_none(inference_budget):
    with pytest.raises(InvalidInputError):
        RunBudget(inference_budget=inference_budget, timeout_seconds=60.0)


# am[verifies a-rt-run-budget-1016@e046b0]
# am[verifies a-rt-nr-repair-1018@72901e]
@pytest.mark.parametrize("timeout_seconds", [0, -1.0, float("inf"), float("nan"), True, None, 10**400])
def test_a_wall_bound_is_finite_and_positive(timeout_seconds):
    with pytest.raises(InvalidInputError):
        RunBudget(inference_budget=None, timeout_seconds=timeout_seconds)


# A refused bound is written into the refusal's details as repr writes it, and one repr cannot write,
# an integer past the digit limit or a list holding one, is named, so the refusal is still the
# InvalidInputError where building it raised ValueError.
# am[verifies a-rt-rr-safe-repr-1018@ec9700]
@pytest.mark.parametrize(("bounds", "field", "shown"), [
    ({"inference_budget": None, "timeout_seconds": 10**5000}, "timeout_seconds", "an integer of more than {limit} digits"),
    ({"inference_budget": None, "timeout_seconds": -(10**5000)}, "timeout_seconds",
     "a negative integer of more than {limit} digits"),
    ({"inference_budget": -(10**5000), "timeout_seconds": 60.0}, "inference_budget",
     "a negative integer of more than {limit} digits"),
    ({"inference_budget": [10**5000], "timeout_seconds": 60.0}, "inference_budget",
     "a value of type list whose repr raised ValueError"),
    ({"inference_budget": None, "timeout_seconds": -1}, "timeout_seconds", "-1"),
    ({"inference_budget": "100", "timeout_seconds": 60.0}, "inference_budget", "'100'"),
])
def test_a_refused_bound_is_named_where_repr_cannot_write_it(bounds, field, shown):
    with pytest.raises(InvalidInputError) as refusal:
        RunBudget(**bounds)

    assert dict(refusal.value.details) == {field: shown.format(limit=sys.get_int_max_str_digits())}


# am[verifies a-rt-rr-safe-repr-1018@ec9700]
def test_work_refuses_an_integer_repr_cannot_write_as_its_budget_with_the_typed_error():
    with pytest.raises(InvalidInputError, match="runs only under its caller's RunBudget") as refusal:
        caller_budget(10**5000, "work")

    assert dict(refusal.value.details) == {"budget": f"an integer of more than {sys.get_int_max_str_digits()} digits"}


# A positive integer bound beyond SWI-Prolog's int64_t reaches the engine as the largest limit it
# holds, which no run reaches, and the spend is charged against the whole bound.
# am[verifies a-rt-nr-repair-1018@72901e]
def test_an_inference_bound_beyond_the_engines_int64_reaches_it_as_its_largest_limit():
    budget = RunBudget(inference_budget=10**400, timeout_seconds=60.0)
    engine = _SwallowingEngine(spend=5)
    answers, used = run_bounded(engine, "!(anything)", budget=budget)

    assert engine.bounds[0][0] == 2**63 - 1 == runtime_budget.ENGINE_INFERENCE_LIMIT
    assert (answers, used, budget.spent) == ([["answer"]], 5, 5)


# A deadline beyond threading.TIMEOUT_MAX is waited for in slices no longer than it, since one
# Lock.acquire or Condition.wait raises OverflowError beyond it; a passed deadline waits not at all.
# am[verifies a-rt-nr-repair-1018@72901e]
def test_a_wait_toward_a_deadline_beyond_timeout_max_takes_slices_no_longer_than_it():
    budget = RunBudget(inference_budget=None, timeout_seconds=threading.TIMEOUT_MAX * 3)
    given: list[float] = []

    assert budget.wait(lambda seconds: given.append(seconds) or len(given) == 2)
    assert given == [threading.TIMEOUT_MAX, threading.TIMEOUT_MAX]

    passed = RunBudget(inference_budget=None, timeout_seconds=0.001)
    time.sleep(0.01)
    assert not passed.wait(lambda seconds: given.append(seconds) or True)
    assert len(given) == 2


# A preparation keeps its request's absolute deadline and whole timeout. The request starts at 0
# with 10 s, its time left is read at 2 and a scheduling delay could resume the preparation at 5:
# the preparation still stops at 10, permits work at 9.5, and a stop names 10 s, not the 8 left.
# am[verifies a-integrate-runtime-deadline-preservation-1018@d52ba4]
@pytest.mark.parametrize(("observed_at", "stopped"), [(9.5, False), (11.0, True), (14.0, True)])
def test_a_preparation_keeps_its_requests_deadline_and_timeout(monkeypatch, observed_at, stopped):
    readings = iter((0.0, 2.0, 5.0))
    clock = SimpleNamespace(monotonic=lambda: next(readings))
    monkeypatch.setattr(runtime_budget, "time", clock)
    request = RunBudget(inference_budget=100, timeout_seconds=10.0)
    preparation = request.deadline_only()
    clock.monotonic = lambda: observed_at

    assert (preparation.inference_budget, preparation.timeout_seconds) == (None, 10.0)
    if stopped:
        with pytest.raises(ReviewTimeout) as stop:
            preparation.remaining()
        assert stop.value.timeout_seconds == request.timeout_seconds
    else:
        assert preparation.remaining() == (None, pytest.approx(0.5))


# A named space compiles what it imports into a namespace of its own, so a module imported into
# one space defines nothing in another or in the self space; each space keeps its own record, so a
# second load into it answers the recorded digest and imports nothing.
# am[verifies a-rt-load-module-per-space-1017@309625]
def test_a_module_imports_once_into_each_named_space(tmp_path):
    module = tmp_path / "gc_host_per_space.metta"
    module.write_text("(= (gc-host-per-space) here)\n(gc-host-per-space-fact 1)\n")
    with metta_engine(None) as engine:
        first, second = engine.space("&gc-host-space-a"), engine.space("&gc-host-space-b")
        digest = load_metta_module(engine, module, space=first)

        assert [[str(atom) for atom in group] for group in first.run("!(gc-host-per-space)")] == [["here"]]
        assert str(second.run("!(gc-host-per-space)")[0][0]) == "(gc-host-per-space)"
        assert str(engine.run("!(gc-host-per-space)")[0][0]) == "(gc-host-per-space)"

        assert load_metta_module(engine, module, space=second) == digest
        assert [[str(atom) for atom in group] for group in second.run("!(gc-host-per-space)")] == [["here"]]
        assert load_metta_module(engine, module, space=first) == digest
        facts = first.run("!(collapse (match &self (gc-host-per-space-fact $n) $n))")
        assert str(facts[0][0]) == "(1)"
    assert digest == hashlib.sha256(module.read_bytes()).hexdigest()


# Failed imports must undo edits to earlier modules, not only discard their own definitions.
# Retrying the repaired file must commit the replacement once and publish its digest afterwards.
# am[verifies a-integrate-import-transaction-1017]
@pytest.mark.parametrize("named", [False, True], ids=["self", "named"])
@pytest.mark.parametrize("failure", ["missing-import", "python-error"])
def test_a_failed_import_restores_existing_equations_before_retry(tmp_path, named, failure):
    module = tmp_path / "replacement.metta"
    suffix = _sha256(str(module))[:12]
    original, saved = f"gc-host-original-{suffix}", f"gc-host-saved-{suffix}"
    body = (
        f"!(remove-atom &self (= ({original} $x) $x))\n"
        f"!(add-atom &self (= ({saved} $x) $x))\n"
    )
    stop = (f"!(import! &self {_quoted(tmp_path / 'absent.metta')})\n"
            if failure == "missing-import" else "!(py-call (operator.truediv 1 0))\n")
    module.write_text(body + stop)
    with metta_engine(None) as engine:
        space = engine.space(f"&gc-host-atomic-{suffix}") if named else None
        target = engine if space is None else space
        target.run(f"(= ({original} $x) $x)")
        assert _answers(target, f"!({original} before)") == [["before"]]
        for _attempt in range(2):
            with pytest.raises(Exception) as caught:
                load_metta_module(engine, module, space=space)
            if failure == "python-error":
                assert type(caught.value).__name__ == "EngineError"
            assert _answers(target, f"!({original} after)") == [["after"]]
            assert _answers(target, f"!({saved} after)") == [[f"({saved} after)"]]
        module.write_text(body)
        assert load_metta_module(engine, module, space=space) == _sha256(body)
        assert _answers(target, f"!({original} committed)") == [[f"({original} committed)"]]
        assert _answers(target, f"!({saved} committed)") == [["committed"]]
        assert load_metta_module(engine, module, space=space) == _sha256(body)
        assert _answers(target, f"!(collapse (match &self (= ({saved} $x) $body) True))") == [["(True)"]]


# Importing the package and SNARS's py-call helpers loads no pymetta, so a process without it, as
# PeTTa's Python running those helpers was, imports them; pymetta's absence surfaces only where an
# engine is asked for, as metta_engine's DependencyUnavailableError.
# am[verifies a-rt-pymetta-engine-1016@296784] am[verifies a-rt-rb-migrate-score-sleep-1018@064cf4]
def test_the_package_imports_without_pymetta():
    script = "import sys; sys.modules['metta'] = None; import goal_chainer, goalchainer_snars"
    result = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr

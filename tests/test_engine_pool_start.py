"""Purpose: verify that the evaluation pool's start ends each caller's wait at its own deadline: while
the pool's worker has yet to attach, a first caller raises ReviewTimeout at its deadline and its
work never runs, a later caller waits for the same one start and its work runs once the worker
attaches, and a start whose constructor fails, whose thread cannot be launched or whose import of
pymetta's pool fails raises in the caller waiting on it and leaves the next call to start the pool
again; that an interrupt reaching the launching caller after the startup thread began builds
no second pool: a start its thread has claimed serves the retry, and one cancelled before the claim
constructs nothing; and that a start whose third worker's thread cannot start leaves none of its
workers running once its caller sees the error, so the next call starts the pool on workers of its
own."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from request_support import budget as request_budget

from goal_chainer.runtime import engine as runtime_engine
from goal_chainer.runtime.budget import ReviewTimeout, RunBudget
from goal_chainer.runtime.engine import metta_engine, shared_evaluation

# A caller that is to stop waiting has this long; a held worker waits HOLD_SECONDS before it
# attaches anyway, so a caller still waiting then has outlived its deadline.
DEADLINE_SECONDS = 0.5
HOLD_SECONDS = 30.0


# The process's pool set aside for one test, with one worker: the engine is booted, as any caller
# finds it, and the test's own pool, if it started one, is shut down before the process's comes back.
# am[verifies a-integrate-pool-startup-deadline-1018@609749]
@pytest.fixture
def fresh_pool(monkeypatch):
    with metta_engine(None):
        pass
    monkeypatch.setattr(runtime_engine, "_POOL", None)
    monkeypatch.setattr(runtime_engine, "_STARTING", None)
    monkeypatch.setattr(runtime_engine, "POOL_WORKERS", 1)
    yield monkeypatch
    if runtime_engine._POOL is not None:
        runtime_engine._POOL.shutdown(wait=True)


# Each pool constructed during the test, counted, and its workers held before they attach until the
# test opens them, as the parent's probe holds them (ai-pool-startup-deadline-probe.py).
# am[verifies a-integrate-pool-startup-deadline-1018@609749]
def _held_starts(monkeypatch) -> tuple[list[object], threading.Event, threading.Event]:
    from metta.parallel import EnginePool

    constructed: list[object] = []
    reached, opened = threading.Event(), threading.Event()
    native_init, native_worker = EnginePool.__init__, EnginePool._worker

    def counted(pool, *args, **kwargs):
        constructed.append(pool)
        native_init(pool, *args, **kwargs)

    def held(pool):
        reached.set()
        opened.wait(HOLD_SECONDS)
        native_worker(pool)

    monkeypatch.setattr(EnginePool, "__init__", counted)
    monkeypatch.setattr(EnginePool, "_worker", held)
    return constructed, reached, opened


# A stand-in for pymetta's pool constructor, which needs no engine: it counts the constructions
# that begin, and each waits until the test opens them.
# am[verifies a-integrate-consumer-pool-launch-interrupt-1018@307814]
def _stand_in_pool(monkeypatch) -> tuple[list[int], threading.Event, threading.Event]:
    from metta import parallel

    begun: list[int] = []
    entered, opened = threading.Event(), threading.Event()

    class StandIn:
        def shutdown(self, wait: bool = True) -> None:
            pass

    def pool(workers: int) -> StandIn:
        begun.append(workers)
        entered.set()
        opened.wait(HOLD_SECONDS)
        return StandIn()

    monkeypatch.setattr(parallel, "pool", pool)
    return begun, entered, opened


# The first caller gives up at its deadline while the worker is held, charged nothing, and its work
# never runs, not even once the pool is up; a caller after it waits for the same start, which one
# constructor serves, and its work runs once the worker attaches.
# am[verifies a-integrate-pool-startup-deadline-1018@609749]
def test_a_caller_waiting_for_the_pool_to_start_stops_at_its_deadline_and_the_next_shares_the_start(fresh_pool):
    constructed, reached, opened = _held_starts(fresh_pool)
    ran: list[str] = []
    budget = RunBudget(inference_budget=10**9, timeout_seconds=DEADLINE_SECONDS)

    def later_work(engine):
        ran.append("later")
        return True

    with ThreadPoolExecutor(max_workers=1) as threads:
        try:
            started = time.monotonic()
            with pytest.raises(ReviewTimeout):
                shared_evaluation(lambda engine: ran.append("first"), budget=budget)
            waited = time.monotonic() - started
            assert reached.wait(HOLD_SECONDS) and not opened.is_set()
            later = threads.submit(shared_evaluation, later_work, budget=request_budget())
            assert runtime_engine._STARTING is not None and runtime_engine._POOL is None
        finally:
            opened.set()
        assert later.result(timeout=HOLD_SECONDS) is True

    assert waited < HOLD_SECONDS / 2
    assert budget.spent == 0
    assert ran == ["later"]
    assert len(constructed) == 1 and runtime_engine._POOL is constructed[0]
    assert runtime_engine._STARTING is None


# A worker that cannot attach fails the constructor, which closes its workers and raises; the caller
# waiting on that start gets its error, nothing is left started, and the next call starts the pool
# again and runs its work.
# am[verifies a-integrate-pool-startup-deadline-1018@609749]
# am[related a-integrate-pymetta-public-errors-1019@05202a]
def test_a_failed_start_raises_in_its_caller_and_the_next_call_starts_the_pool_again(fresh_pool):
    from metta import parallel
    from metta.errors import MettaError

    native = parallel.engine_thread
    attachments: list[str] = []

    def first_attachment_fails():
        attachments.append("attach")
        if len(attachments) == 1:
            raise RuntimeError("this worker cannot attach its engine")
        return native()

    fresh_pool.setattr(parallel, "engine_thread", first_attachment_fails)

    with pytest.raises(MettaError) as failed:
        shared_evaluation(lambda engine: "first", budget=request_budget())
    assert isinstance(failed.value.__cause__, RuntimeError)
    assert runtime_engine._POOL is None and runtime_engine._STARTING is None

    assert shared_evaluation(lambda engine: "again", budget=request_budget()) == "again"
    assert runtime_engine._POOL is not None and len(attachments) == 2


# A startup thread that cannot be launched raises in the caller that tried, and no start is left
# pending without a producer, so the next call launches one, starts the pool and runs its work.
# am[verifies a-integrate-pool-start-thread-recovery-1018@d0c74d]
def test_a_start_thread_that_cannot_launch_leaves_the_next_call_to_start_the_pool(fresh_pool):
    native_start = threading.Thread.start
    refused: list[str] = []

    def start(thread):
        if thread.name == "goalchainer-pool-start" and not refused:
            refused.append(thread.name)
            raise RuntimeError("can't start new thread")
        native_start(thread)

    fresh_pool.setattr(threading.Thread, "start", start)

    with pytest.raises(RuntimeError, match="can't start new thread"):
        shared_evaluation(lambda engine: "first", budget=request_budget())
    assert runtime_engine._POOL is None and runtime_engine._STARTING is None

    assert shared_evaluation(lambda engine: "again", budget=request_budget()) == "again"
    assert runtime_engine._POOL is not None and refused == ["goalchainer-pool-start"]


# A start whose import of pymetta's pool fails, before any constructor runs, raises that error in
# the caller waiting on it within the caller's own bound, and the next call starts the pool.
# am[verifies a-integrate-pool-start-thread-recovery-1018@d0c74d]
def test_a_start_whose_import_fails_leaves_the_next_call_to_start_the_pool(fresh_pool):
    from metta import parallel

    native_pool = parallel.pool
    fresh_pool.delattr(parallel, "pool")
    bounded = RunBudget(inference_budget=10**9, timeout_seconds=HOLD_SECONDS)

    with pytest.raises(ImportError):
        shared_evaluation(lambda engine: "first", budget=bounded)
    assert runtime_engine._POOL is None and runtime_engine._STARTING is None

    fresh_pool.setattr(parallel, "pool", native_pool, raising=False)
    assert shared_evaluation(lambda engine: "again", budget=request_budget()) == "again"
    assert runtime_engine._POOL is not None


# The startup thread has claimed its start and is constructing when an interrupt reaches the
# caller that launched it, as one arriving while Thread.start() waits for its started event does.
# The start stays published, so a retry waits for it rather than launching a second one, and once
# the construction completes the retry has the one pool.
# am[verifies a-integrate-consumer-pool-launch-interrupt-1018@307814]
def test_a_start_interrupted_after_its_thread_claimed_it_serves_the_retry(fresh_pool):
    begun, entered, opened = _stand_in_pool(fresh_pool)
    native_start = threading.Thread.start
    launched: list[threading.Thread] = []

    def start(thread):
        native_start(thread)
        if thread.name == "goalchainer-pool-start":
            launched.append(thread)
            if len(launched) == 1:
                assert entered.wait(HOLD_SECONDS), "the startup thread never began its construction"
                raise KeyboardInterrupt

    fresh_pool.setattr(threading.Thread, "start", start)
    try:
        with pytest.raises(KeyboardInterrupt):
            runtime_engine._pool(request_budget())
        assert runtime_engine._STARTING is not None, "a claimed start must stay published for the retry"
        with ThreadPoolExecutor(max_workers=1) as threads:
            retry = threads.submit(runtime_engine._pool, request_budget())
            opened.set()
            pool = retry.result(timeout=HOLD_SECONDS)
        assert pool is runtime_engine._POOL
        assert len(launched) == 1 and begun == [1]
    finally:
        opened.set()
        for thread in launched:
            thread.join(HOLD_SECONDS)


# The interrupt reaches the launching caller before the startup thread claims its start. The
# caller cancels the start, so nothing stays pending; the thread, when it runs, finds its start
# cancelled and constructs nothing; and the next call starts a pool of its own.
# am[verifies a-integrate-consumer-pool-launch-interrupt-1018@307814]
def test_a_start_interrupted_before_its_thread_claimed_it_constructs_nothing(fresh_pool):
    begun, _, opened = _stand_in_pool(fresh_pool)
    opened.set()
    native_start, native_start_pool = threading.Thread.start, runtime_engine._start_pool
    held = threading.Event()
    launched: list[threading.Thread] = []

    def start_pool(starting):
        held.wait(HOLD_SECONDS)
        native_start_pool(starting)

    def start(thread):
        native_start(thread)
        if thread.name == "goalchainer-pool-start":
            launched.append(thread)
            if len(launched) == 1:
                raise KeyboardInterrupt

    fresh_pool.setattr(runtime_engine, "_start_pool", start_pool)
    fresh_pool.setattr(threading.Thread, "start", start)
    try:
        with pytest.raises(KeyboardInterrupt):
            runtime_engine._pool(request_budget())
        assert runtime_engine._STARTING is None and runtime_engine._POOL is None
        held.set()
        launched[0].join(HOLD_SECONDS)
        assert begun == [] and runtime_engine._POOL is None, "a cancelled start must construct nothing"
        assert runtime_engine._pool(request_budget()) is runtime_engine._POOL
        assert len(launched) == 2 and begun == [1]
    finally:
        held.set()
        for thread in launched:
            thread.join(HOLD_SECONDS)


# A pool whose third worker's thread cannot start fails that start in its caller, and none of the
# start's workers is still running when the caller sees the error: pymetta's constructor joins every
# worker that attached an engine before it raises (PyMeTTa 01746f1 and 916e3a5), where 0.9.4's left
# them at its barrier for 60 s beside the next start's. The next call starts the pool on three
# workers of its own.
# am[verifies a-integrate-pool-partial-start-cleanup-1018@ffccc8]
def test_a_pool_start_that_fails_partway_leaves_no_worker_running_and_the_next_call_starts_clean(fresh_pool):
    fresh_pool.setattr(runtime_engine, "POOL_WORKERS", 3)
    before = {thread for thread in threading.enumerate() if thread.name.startswith("metta-pool-")}
    native_start = threading.Thread.start
    launched: list[threading.Thread] = []

    def start(thread):
        if thread.name.startswith("metta-pool-") and len(launched) == 2:
            raise RuntimeError("can't start new thread")
        native_start(thread)
        if thread.name.startswith("metta-pool-"):
            launched.append(thread)

    fresh_pool.setattr(threading.Thread, "start", start)

    with pytest.raises(RuntimeError, match="can't start new thread"):
        shared_evaluation(lambda engine: "first", budget=request_budget())
    assert runtime_engine._POOL is None and runtime_engine._STARTING is None
    assert len(launched) == 2
    assert [worker.name for worker in launched if worker.is_alive()] == []

    fresh_pool.setattr(threading.Thread, "start", native_start)
    assert shared_evaluation(lambda engine: "again", budget=request_budget()) == "again"
    started = {thread for thread in threading.enumerate() if thread.name.startswith("metta-pool-")} - before
    assert len(started) == 3


# A caller's timeout beyond threading.TIMEOUT_MAX is a finite positive bound like any other: the
# wait for the pool to start, for the share and for the work runs in slices no longer than it,
# where each wait had raised OverflowError from the platform's time_t.
# am[verifies a-rt-nr-repair-1018@72901e]
def test_a_timeout_beyond_timeout_max_starts_the_pool_and_answers(fresh_pool):
    budget = RunBudget(inference_budget=None, timeout_seconds=threading.TIMEOUT_MAX * 2)

    assert shared_evaluation(lambda engine: "answered", budget=budget) == "answered"
    assert runtime_engine._POOL is not None

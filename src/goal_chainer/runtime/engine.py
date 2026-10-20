"""Purpose: host the process's in-process pymetta engine and its evaluation pool, and give every
child process GoalChainer starts the environment the engine found. pymetta compiles MeTTa functions
process-wide, so every module shares one function namespace and modules prefix their function names.
`metta_engine(budget)` hands out the home engine alone, for work that changes what every engine reads:
boot, library registration, module loading and world preparation, every call of the block on one
Prolog engine whichever thread holds it. `shared_evaluation(work)` runs work that only reads it,
such as one speculative call, on a worker of an EnginePool, whose workers each attach their own
engine over the process's spaces, so evaluations on different workers run at once; evaluations wait
while the engine is held alone, and holding it alone waits for running evaluations, so preparation
takes it alone only the first time (runtime.modules' initialize_once and register_metta_library).
The pool belongs to the process: one startup thread of its own constructs it, inside no pymetta
scope, while every caller waits for that one start. Every such wait, for the engine alone, for a
share of it, for a pool worker or for the pool's start, ends at the deadline of the RunBudget the
waiting caller gives, with that budget's ReviewTimeout, and work still queued then is cancelled and
never runs; a caller outside any request gives None and waits as long as it takes. Booting the
engine sets SWI_HOME_DIR to the SWI-Prolog home bundled in pymetta, a
setting for this process's own engine: `child_environment` puts back whatever the boot set, so
neither a child running another SWI-Prolog nor anything that child starts inherits the bundled
home. The booting thread and each pool worker, the threads that keep an engine of their own, first
make one trivial speculative run under both of pymetta's bounds, its time bound the caller's
deadline, so the work a thread's or the process's first run does once is charged to no stage; a
thread counts as warm only once that run finished, so a stopped one is made again at the thread's
next block or work. `pymetta_identity` names the engine a run used."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import threading
from collections.abc import Callable, Iterator, Mapping
from concurrent import futures
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

from ..errors import DependencyUnavailableError
from .budget import ReviewTimeout, RunBudget

_Result = TypeVar("_Result")


# Shared and exclusive holds on the engine. Many threads share it while evaluations run; one thread
# holds it alone, re-entrantly, to change what every engine reads. A waiting exclusive hold stops
# new shared holds, so a stream of evaluations cannot starve a load. A shared holder cannot then
# hold it alone, since that would wait for its own share to end. A wait given a RunBudget ends at
# its deadline, Condition.wait_for's bounded wait, as a context's deadline ends a Go wait; an
# exclusive waiter that gives up wakes the shared waiters it was holding back.
# Time: O(1) per hold and release, and a wakeup of every waiter on each release.
# am[implements a-rt-cc-rw-pool-1018] am[rests-on c-rt-engine-pool-concurrent-1018]
# am[implements a-integrate-runtime-wait-deadline-1018@a74406]
class _SharedExclusive:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._shared = 0
        self._owner: int | None = None
        self._depth = 0
        self._waiting = 0

    @contextmanager
    def exclusive(self, budget: RunBudget | None = None) -> Iterator[None]:
        me = threading.get_ident()
        with self._condition:
            if self._owner != me:
                if _shared_depth():
                    raise RuntimeError(
                        "A shared engine evaluation asked for the engine alone, which would wait "
                        "for itself; prepare before evaluating."
                    )
                self._waiting += 1
                try:
                    self._wait_until(lambda: self._owner is None and not self._shared, budget)
                except BaseException:
                    self._condition.notify_all()
                    raise
                finally:
                    self._waiting -= 1
                self._owner = me
            self._depth += 1
        try:
            yield
        finally:
            with self._condition:
                self._depth -= 1
                if not self._depth:
                    self._owner = None
                    self._condition.notify_all()

    @contextmanager
    def shared(self, budget: RunBudget | None = None) -> Iterator[None]:
        with self._condition:
            self._wait_until(lambda: self._owner is None and not self._waiting, budget)
            self._shared += 1
        _SHARED_HOLD.depth = _shared_depth() + 1
        try:
            yield
        finally:
            _SHARED_HOLD.depth -= 1
            with self._condition:
                self._shared -= 1
                if not self._shared:
                    self._condition.notify_all()

    def held_alone(self) -> bool:
        return self._owner == threading.get_ident()

    # Waits, holding the condition, until `ready()`; with a budget only until its deadline, raising
    # its ReviewTimeout then, and a budget already used up raises before any wait, so an exhausted
    # request takes no hold. The wait runs in the budget's slices, so a deadline beyond
    # threading.TIMEOUT_MAX is waited for, not raised as OverflowError.
    # am[implements a-integrate-runtime-wait-deadline-1018@a74406] am[implements a-rt-nr-repair-1018@72901e]
    def _wait_until(self, ready: Callable[[], bool], budget: RunBudget | None) -> None:
        if budget is None:
            self._condition.wait_for(ready)
            return
        budget.remaining()
        if not budget.wait(lambda seconds: self._condition.wait_for(ready, seconds)):
            raise ReviewTimeout(budget.timeout_seconds)


# How many shared holds the current thread is inside, so it can be refused the engine alone.
_SHARED_HOLD = threading.local()


# am[implements a-rt-cc-rw-pool-1018]
def _shared_depth() -> int:
    return getattr(_SHARED_HOLD, "depth", 0)


_HOLDS = _SharedExclusive()

_ENGINE: Any = None

# Whether this thread's warm-up run finished, set only then: the booting thread makes it before its
# blocks and a pool worker before its work until one finishes. _BOOT_THREAD is the thread that
# booted the engine, which keeps it as pymetta's home engine.
# am[implements a-rt-det-warm-thread-1019@199c44] am[addresses i-rt-per-worker-first-use-1019@32dc89]
# am[implements a-integrate-warm-thread-deadline-1019@add254]
_WARMED = threading.local()
_BOOT_THREAD: threading.Thread | None = None

# The evaluation pool, started on the first shared evaluation once the engine has booted, with one
# worker per CPU this process may run on. _STARTING is the start in flight: the Future its startup
# thread resolves with the pool, or with what the constructor raised. _POOL_LOCK guards the two
# and is never held across a wait.
_POOL: Any = None
_STARTING: futures.Future[Any] | None = None
_POOL_LOCK = threading.Lock()
POOL_WORKERS = os.process_cpu_count() or 1


# What booting the engine changed in this process's environment: each variable's value before the
# boot and the value the boot left, None for absent. pymetta 0.9.4 sets only SWI_HOME_DIR, after
# refusing any other home already set (metta/_host/__init__.py). A boot that raises still leaves
# what it set, so every attempt is recorded, a variable keeping its value before the first.
# am[implements a-integrate-petta-child-engine-environment-1017@8f59bb] am[rests-on c-rt-pymetta-boot-sets-swi-home-1017@75b69b]
_ENGINE_ENVIRONMENT: dict[str, tuple[str | None, str | None]] = {}


# Held from a boot's first change to the environment until the change is recorded, and while a
# child's environment is copied and undone, so no child copies the environment in between. The
# engine lock would serve too, but every in-process run holds it, and no child launch should wait
# out a review.
# am[implements a-integrate-petta-child-engine-environment-1017@8f59bb] am[addresses i-integrate-child-env-during-boot-1017@5200fa]
_ENVIRONMENT_LOCK = threading.RLock()


# The home engine alone: concurrent reviews on one shared engine answered wrong
# (c-rt-pymetta-threads-1016), so whatever runs on the home engine runs alone. The boot's changes to
# the environment are recorded for child_environment. pymetta answers each call from a thread
# holding no Prolog engine of its own on a temporary engine, so neither a global variable nor the
# inference counts run_bounded charges carry from one call to the next there
# (c-rt-bare-thread-temporary-engines-1018). The holder therefore runs the block on one engine,
# attached by pymetta's engine_thread for the block; the thread that booted the engine and a pool
# worker keep their own.
# am[implements a-rt-pymetta-engine-1016@296784] am[rests-on c-rt-pymetta-threads-1016@302137]
# am[implements a-integrate-petta-child-engine-environment-1017@8f59bb]
# am[implements a-rt-cc-rw-pool-1018]
# am[implements a-rt-engine-budget-required-1018@e013ed]
@contextmanager
def metta_engine(budget: RunBudget | None) -> Iterator[Any]:
    """The process's pymetta engine, booted on first use, held alone for the block: no evaluation
    runs while it is held, and it waits for running evaluations to finish. Every call in the
    block runs on one Prolog engine, whichever thread holds it.

    Every caller names `budget`, as every budget keyword is named: with a RunBudget the wait ends
    at its deadline with its ReviewTimeout, and a budget already used up raises before waiting, as
    the booting thread's warm-up run before its block does once that deadline stops it;
    None says the caller is outside any request, and it waits as long as it takes. With no default,
    a request that forgot its budget fails at the call instead of waiting unbounded. A thread
    already holding the engine alone never waits.

    Raises DependencyUnavailableError when pymetta is not installed; nothing falls back to
    another engine. Raises RuntimeError when called inside a shared evaluation.
    """

    with _HOLDS.exclusive(budget):
        engine = _booted()
        # Only the booting thread keeps its engine from one block to the next; any other holder's
        # block runs on an engine attached for that block alone.
        if threading.current_thread() is _BOOT_THREAD:
            _warm_thread(engine, budget)
        from metta.parallel import engine_thread  # noqa: PLC0415 (pymetta is imported once an engine exists)

        with engine_thread():
            yield engine


# am[implements a-rt-pymetta-engine-1016@296784] am[implements a-integrate-petta-child-engine-environment-1017@8f59bb]
# am[implements a-rt-det-warm-thread-1019@199c44] am[implements a-integrate-warm-thread-deadline-1019@add254]
def _booted() -> Any:
    global _ENGINE, _BOOT_THREAD
    if _ENGINE is None:
        try:
            import metta  # noqa: PLC0415 (a dependency only in-process callers load)
        except ImportError as error:
            raise DependencyUnavailableError(
                "pymetta is not importable; install GoalChainer's locked environment "
                "with `uv sync --frozen`.",
                details={"dependency": "pymetta", "error": str(error)},
            ) from error
        with _ENVIRONMENT_LOCK:
            before = dict(os.environ)
            try:
                _ENGINE = metta.MeTTa()
            finally:
                after = dict(os.environ)
                for key in before.keys() | after.keys():
                    if before.get(key) != after.get(key):
                        first = _ENGINE_ENVIRONMENT[key][0] if key in _ENGINE_ENVIRONMENT else before.get(key)
                        _ENGINE_ENVIRONMENT[key] = (first, after.get(key))
        _BOOT_THREAD = threading.current_thread()
    return _ENGINE


# The bounds a warm-up run takes for a caller outside any request, which sets none: they only take
# pymetta's bounded path, ten times the 1000 inferences the run spends (c-rt-det-warm-run-cost-1019)
# and a minute it never nears; a request's warm-up takes its remaining seconds instead.
# am[implements a-integrate-warm-thread-deadline-1019@add254]
_WARM_UP_INFERENCES = 10_000
_WARM_UP_SECONDS = 60.0


# A thread's first speculative run does about 33 inferences of work no later run on it repeats,
# and the process's first run under pymetta's inference and time bounds about 16 more, and each was
# charged to whichever stage came first. This trivial run pays both, outside every stage's count:
# the booting thread makes it before its first block and each pool worker before its first work.
# Inside a request it runs under the request's deadline, the same one the stages of that work do
# (c-rel-one-deadline-1016), since a caller waits for work a worker has started past that deadline;
# a stop there is the request's ReviewTimeout. A run that did not finish, stopped or failed, leaves
# the thread cold, so its next block or work makes the run again.
# Time: one engine run of about a thousand inferences per thread, once it finishes.
# am[implements a-rt-det-warm-thread-1019@199c44] am[addresses i-rt-bounded-first-use-1019@8177ff]
# am[addresses i-rt-per-worker-first-use-1019@32dc89] am[rests-on c-rt-det-bounded-first-use-1019@722ad7]
# am[rests-on c-rt-det-cheap-per-thread-exact-1019@dd8218]
# am[implements a-integrate-warm-thread-deadline-1019@add254] am[rests-on c-rel-one-deadline-1016@75de2a]
# am[addresses c-integrate-warm-thread-at-52c9e3b5-1019@0a1d30]
# am[implements a-integrate-pymetta-public-errors-1019@05202a]
def _warm_thread(engine: Any, budget: RunBudget | None) -> None:
    if getattr(_WARMED, "done", False):
        return
    from metta.errors import InferenceLimitError, TimeLimitError  # noqa: PLC0415 (pymetta is imported once an engine exists)

    seconds = _WARM_UP_SECONDS if budget is None else budget.deadline_only().remaining()[1]
    try:
        with engine.speculate():
            engine.run("!(+ 1 1)", inferences=_WARM_UP_INFERENCES, timeout=seconds)
    except TimeLimitError as error:
        if budget is not None:
            raise ReviewTimeout(budget.timeout_seconds) from error
        return
    except InferenceLimitError:
        return
    _WARMED.done = True


# Work that only reads the engine runs on an EnginePool worker, whose own attached engine sees the
# process's spaces and compiled code, so evaluations on different workers run at once
# (c-rt-engine-pool-concurrent-1018); the caller waits for its own. The worker holds the share for
# as long as the work runs, so a caller that stops waiting cannot let a load in under it. A thread
# already holding the engine, alone or inside shared work, runs the work itself: waiting for another
# worker there could wait on its own pool. The work must not take the engine alone: prepare first.
# A caller's budget bounds both waits, for a free worker and for the share: pymetta's pool skips a
# Future cancelled while still queued and lets a started one finish (metta/parallel.py, its
# shutdown and _serve), so work still queued at the deadline is cancelled and never runs, and work a
# worker started first takes the share and warms its thread under the same deadline, so it gives up
# or runs bounded by it.
# Time: one queue hand-off and one wakeup, besides the work and the waits the budget bounds.
# am[implements a-rt-cc-rw-pool-1018] am[rests-on c-rt-engine-pool-concurrent-1018]
# am[implements a-integrate-runtime-wait-deadline-1018@a74406]
def shared_evaluation(work: Callable[[Any], _Result], *, budget: RunBudget | None) -> _Result:
    """Run `work(engine)` while sharing the engine with other evaluations, and answer its result.

    `work` receives the engine handle; on a pool worker its calls run on that worker's attached
    engine. An exception `work` raises is raised here, and so is the RuntimeError metta_engine
    raises when `work` asks for the engine alone.

    `budget` is the caller's: waiting for a worker or for the share ends at its deadline with its
    ReviewTimeout, and so does a worker's warm-up run before its first work; work not yet started
    then never runs, and a budget already used up raises before anything is queued. None is for a
    caller outside any request, which waits as long as it takes. A caller already holding the
    engine runs `work` itself and waits for nothing.
    """

    if _HOLDS.held_alone() or _shared_depth():
        return work(_ENGINE)
    # The pool boots the engine alone, so it is started before this share is taken.
    pool = _pool(budget)
    if budget is None:
        return pool.submit(_shared_work, work, None).result()
    # am[implements a-rt-nr-repair-1018@72901e]
    budget.remaining()
    future = pool.submit(_shared_work, work, budget)
    if not budget.wait(lambda seconds: bool(futures.wait((future,), timeout=seconds)[0])) and future.cancel():
        raise ReviewTimeout(budget.timeout_seconds)
    return future.result()


# am[implements a-rt-cc-rw-pool-1018]
# am[implements a-integrate-runtime-wait-deadline-1018@a74406]
# am[implements a-rt-det-warm-thread-1019@199c44] am[implements a-integrate-warm-thread-deadline-1019@add254]
def _shared_work(work: Callable[[Any], _Result], budget: RunBudget | None) -> _Result:
    with _HOLDS.shared(budget):
        _warm_thread(_ENGINE, budget)
        return work(_ENGINE)


# A started pool is read without the lock, as a recorded setup is (runtime.modules'
# initialize_once): under CPython's GIL the read is atomic and the pool is whole before it is
# published. Before it exists, a caller boots the engine on its own thread, so the boot's changes
# to the environment are recorded, waiting for the engine alone only until its deadline. pymetta's
# pool constructor then attaches every worker's engine before it returns, waiting up to 60 s at its
# barrier (c-rt-pool-constructor-waits-at-barrier-1018), a wait no caller's deadline could end, so
# the first caller hands the construction to a startup thread and every caller, that one included,
# waits for the one start's Future only until its own deadline: Java Concurrency in Practice's
# memoizer, one shared computation and a timed wait each (c-rt-single-flight-memoizer-1018). A
# caller whose deadline passes raises ReviewTimeout before it queues anything, so its work never
# runs; the start goes on and serves the callers after it. A start is published before its thread
# is launched, and the thread claims it first thing by moving its Future to running. A launch that
# raises, because Thread.start() could not start the thread or because an interrupt reached this
# caller after the thread began, cancels the start, and the Future settles which happened
# (c-rt-future-claim-is-atomic-1018): a start no thread has claimed is cancelled and withdrawn, and
# its thread, if it ever runs, constructs nothing, so the next call starts again; a start already
# claimed cannot be cancelled and stays published, so every caller after the interrupt waits for
# it and no second pool is built. The thread cannot resolve its start before the launch is done,
# since it takes the lock this caller holds.
# Time: one boot and one start per process, and a lock round and a Future wait per caller before
# the pool exists; none after.
# am[implements a-rt-cc-rw-pool-1018] am[rests-on c-rt-engine-pool-concurrent-1018]
# am[implements a-integrate-runtime-wait-deadline-1018@a74406]
# am[implements a-integrate-pool-startup-deadline-1018@609749] am[rests-on c-rt-pool-constructor-waits-at-barrier-1018]
# am[rests-on c-rt-single-flight-memoizer-1018]
# am[implements a-integrate-pool-start-thread-recovery-1018@d0c74d] am[addresses c-integrate-pool-thread-start-poisons-future-1018@0bc81a]
# am[implements a-integrate-consumer-pool-launch-interrupt-1018@307814] am[rests-on c-rt-future-claim-is-atomic-1018@5786f0]
# am[addresses c-integrate-consumer-start-interrupt-duplicates-pool-1018@6ef65f]
def _pool(budget: RunBudget | None) -> Any:
    global _STARTING
    started = _POOL
    if started is not None:
        return started
    if _ENGINE is None:
        with metta_engine(budget):
            pass
    with _POOL_LOCK:
        if _POOL is not None:
            return _POOL
        starting = _STARTING
        if starting is None:
            starting = futures.Future()
            _STARTING = starting
            try:
                threading.Thread(target=_start_pool, args=(starting,), name="goalchainer-pool-start", daemon=True).start()
            except BaseException:
                if starting.cancel():
                    _STARTING = None
                raise
    if budget is None:
        return starting.result()
    # am[implements a-rt-nr-repair-1018@72901e]
    budget.remaining()
    if not budget.wait(lambda seconds: bool(futures.wait((starting,), timeout=seconds)[0])):
        raise ReviewTimeout(budget.timeout_seconds)
    return starting.result()


# The one start, on its own thread, which runs inside no pymetta scope, so the pool's shutdown is
# enrolled with none and the pool lives as long as the process (c-rt-pool-owned-by-constructing-scope-1018).
# It claims its start before anything else, and a start its launcher cancelled first is left alone.
# The pool is published before its Future resolves, so a caller arriving in between finds it. A
# constructor that raises has closed its workers already (EnginePool._start). Whatever the start
# raises, the import of pymetta's pool included, resolves the Future for every caller waiting on it,
# and clearing _STARTING lets the next call start again, so no start is left without a producer.
# am[implements a-integrate-pool-startup-deadline-1018@609749] am[rests-on c-rt-pool-constructor-waits-at-barrier-1018]
# am[rests-on c-rt-pool-owned-by-constructing-scope-1018]
# am[implements a-integrate-pool-start-thread-recovery-1018@d0c74d]
# am[implements a-integrate-consumer-pool-launch-interrupt-1018@307814] am[rests-on c-rt-future-claim-is-atomic-1018@5786f0]
def _start_pool(starting: futures.Future[Any]) -> None:
    global _POOL, _STARTING
    if not starting.set_running_or_notify_cancel():
        return
    try:
        from metta.parallel import pool  # noqa: PLC0415 (pymetta is imported once an engine exists)

        constructed = pool(POOL_WORKERS)
    except BaseException as error:  # every failure goes to the callers waiting on this start
        with _POOL_LOCK:
            _STARTING = None
        starting.set_exception(error)
        return
    with _POOL_LOCK:
        _POOL = constructed
        _STARTING = None
    starting.set_result(constructed)


# A variable the boot set describes this process's engine, so it crosses no process boundary: a
# child that inherited the bundled home would pass it on, its own pymetta boot then setting nothing
# it could undo. A variable changed again since the boot is the caller's and kept. gcskill's
# child_environment guards the opposite boundary, a PeTTa host's SWI_HOME_DIR reaching pymetta.
# Time: one copy of the environment, e entries, + one lookup per variable the boot changed.
# am[implements a-integrate-petta-child-engine-environment-1017@8f59bb] am[rests-on c-rt-child-env-leak-transitive-1017@bdc403]
# am[addresses i-integrate-child-env-during-boot-1017@5200fa]
def child_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment a child process starts with: `base`, by default this process's, with each
    variable booting the in-process engine changed put back as it was before the boot, unless
    `base` holds another value for it than the boot left. While another thread's boot is between
    changing the environment and recording the change, it waits for the record."""

    with _ENVIRONMENT_LOCK:
        environment = dict(os.environ if base is None else base)
        for key, (before, booted) in _ENGINE_ENVIRONMENT.items():
            if environment.get(key) != booted:
                continue
            if before is None:
                environment.pop(key, None)
            else:
                environment[key] = before
    return environment


# am[implements a-rt-pymetta-deontic-1016@61a4b6] am[implements a-rt-snars-worlds-by-includes-1017@54c05f]
@dataclass(frozen=True, slots=True)
class PymettaIdentity:
    """The in-process engine a run used: `runtime` is "pymetta <version>", `runtime_digest`
    SHA-256 over the installed distribution's RECORD, which lists every file of it with its own
    hash, and `swipl_version` the version of the SWI-Prolog bundled inside it."""

    runtime: str
    runtime_digest: str
    swipl_version: str


# Time: one read of RECORD, about 100 KB, and one Prolog flag query.
# am[implements a-rt-pymetta-deontic-1016@61a4b6] am[implements a-rt-snars-worlds-by-includes-1017@54c05f]
# am[rests-on c-rt-pymetta-bundled-swi-1016@5fbd5c]
def pymetta_identity(engine: Any) -> PymettaIdentity:
    """The identity of the engine metta_engine handed out. Call it holding metta_engine.

    Raises DependencyUnavailableError when the installed pymetta has no RECORD, since its
    engine could then not be told apart from any other build of the same version.
    """

    distribution = importlib.metadata.distribution("pymetta")
    record = distribution.read_text("RECORD")
    if record is None:
        raise DependencyUnavailableError(
            "The installed pymetta has no RECORD, so the engine it runs cannot be identified; "
            "install GoalChainer's locked environment with `uv sync --frozen`.",
            details={"dependency": "pymetta", "version": distribution.version},
        )
    version = engine.runtime.once("current_prolog_flag(version_data, swi(Major, Minor, Patch, _))")
    return PymettaIdentity(
        runtime=f"pymetta {distribution.version}",
        runtime_digest=hashlib.sha256(record.encode("utf-8")).hexdigest(),
        swipl_version=f"{version['Major']}.{version['Minor']}.{version['Patch']}",
    )

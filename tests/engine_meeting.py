"""Purpose: give the engine concurrency tests' MeTTa entries Python to reach through py-call: a barrier
two engine calls meet at, which only calls running at the same time can pass, named holds a test
opens, so a test can see where an engine call stands, and a record of the calls that ran, so a test
can see that one never did; and give any test a load holding the engine alone and a budget whose
deadline ends long before that load lets go, so it can see a call stop waiting at its deadline."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from goal_chainer.runtime.budget import RunBudget
from goal_chainer.runtime.engine import metta_engine

# How long a meeting or a hold waits before it fails the test instead of hanging it.
WAIT_SECONDS = 30.0
# The wall-clock budget of a call that is to stop waiting: long enough to reach its wait, short
# beside WAIT_SECONDS, which a hold that nobody opens lasts.
DEADLINE_SECONDS = 1.0

_lock = threading.Lock()
_barriers: dict[int, threading.Barrier] = {}
HOLDS: dict[str, tuple[threading.Event, threading.Event]] = {}
RECORDED: list[str] = []


# am[verifies a-rt-cc-rw-pool-1018]
def meet(parties: int) -> bool:
    """Wait until `parties` engine calls have arrived here, raising BrokenBarrierError when they do
    not arrive together within WAIT_SECONDS."""

    with _lock:
        barrier = _barriers.get(parties)
        if barrier is None or barrier.broken:
            barrier = _barriers[parties] = threading.Barrier(parties, timeout=WAIT_SECONDS)
    barrier.wait()
    return True


# am[verifies a-rt-cc-rw-pool-1018]
def hold(name: str) -> bool:
    """Signal that a call reached hold `name`, then wait until the test opens it."""

    entered, opened = HOLDS[name]
    entered.set()
    return opened.wait(WAIT_SECONDS)


# am[verifies a-rt-cc-rw-pool-1018]
def new_hold(name: str) -> tuple[threading.Event, threading.Event]:
    """A fresh hold `name`: the event a call sets on reaching it and the event that opens it."""

    HOLDS[name] = (threading.Event(), threading.Event())
    return HOLDS[name]


# am[verifies a-integrate-runtime-wait-deadline-1018@a74406]
def record(name: str) -> bool:
    """Note that a call named `name` ran."""

    with _lock:
        RECORDED.append(name)
    return True


# am[verifies a-integrate-runtime-wait-deadline-1018@a74406] am[verifies a-integrate-benchmark-hold-budget-1018@1bd14c]
def short_budget() -> RunBudget:
    """A budget whose wall clock ends long before a load it waits for lets go."""

    return RunBudget(inference_budget=10**9, timeout_seconds=DEADLINE_SECONDS)


# am[verifies a-integrate-runtime-wait-deadline-1018@a74406] am[verifies a-integrate-benchmark-hold-budget-1018@1bd14c]
def while_held_alone(call: Callable[[], object]) -> bool:
    """Run `call` on this thread while another holds the engine alone until the call returns or
    WAIT_SECONDS pass, and answer whether the call returned while the engine was still held."""

    holding, release = threading.Event(), threading.Event()

    def hold_alone() -> None:
        with metta_engine(None):
            holding.set()
            release.wait(WAIT_SECONDS)

    with ThreadPoolExecutor(max_workers=1) as threads:
        loading = threads.submit(hold_alone)
        try:
            assert holding.wait(WAIT_SECONDS)
            call()
            return not loading.done()
        finally:
            release.set()
            loading.result()

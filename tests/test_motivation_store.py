"""Purpose: test the motivation stream: observations and attempts recorded once under their keys and
read back in one history, in order and across a reopen; batches recorded whole or not at all;
records refused as they are built and appends refused before their transaction when the domain or
the vocabulary does not declare what they name; racing appends and racing batches recorded once; a
failed append rolled back; a file of another stream or store refused untouched; replay refusing an
event of another kind, an invalid record, a non-canonical payload or a wrong key; and records
surviving their JSON round trip by property."""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings, strategies as st

from goal_chainer import event_store
from goal_chainer.domains.loader import read_domain, vocabulary
from goal_chainer.errors import InvalidInputError, PersistenceError
from goal_chainer.event_store import EventStore, StoreSchema
from goal_chainer.motivation import (
    ATTEMPT_KIND,
    OBSERVATION_KIND,
    Attempt,
    MotivationStore,
    NeedObservation,
    parse_attempt,
    parse_observation,
)
from goal_chainer.motivation.store import SCHEMA
from goal_chainer.motivation.store import check_records
from goal_chainer.motivation import store as motivation_store
from goal_chainer.relevance.canonical import canonical_json, fingerprint_of
from goal_chainer.runtime import budget as budget_module
from goal_chainer.runtime.budget import InferenceBudgetExceeded, ReviewTimeout, RunBudget
from goal_chainer.snars_store import SnarsEventStore

DOMAIN_TEXT = """
(gc-domain "Motivation store fixture")
(gc-policy-version motivation-store-fixture-v1)
(gc-authority advisory 1 "A recommendation for the host.")
(gc-authority preauthorized 2 "Applied inside a declared envelope.")
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling receipt-calibrated preauthorized)
(gc-estimator-ceiling measured preauthorized)
(gc-estimator-ceiling deterministic preauthorized)
(gc-estimator-ceiling human-asserted preauthorized)
(gc-action empathize "Empathize" "Reflect the feeling back." (authority preauthorized))
(gc-action guide_breath "Guide breath" "Lead a breathing practice." (authority preauthorized))
(gc-goal nurturing agent individual 0.9 "The student's suffering is eased." (priority-source human:designer))
(gc-goal competence agent individual 0.7 "The guidance is effective." (priority-source human:designer))
(gc-signal session_open "a session is open")
(normally rCand (signal session_open) (candidate ?a))
(normally rPermit (candidate ?a) (may (do ?a)))
(gc-need calm nurturing (scale 0 1) (band 0.6 0.9) (drive 2) (need-source human:designer))
(gc-need skill competence (scale -1 1) (band 0 1) (drive 1.5) (need-source human:designer))
"""
AT = datetime(2026, 10, 20, 9, 0, tzinfo=timezone(timedelta(hours=11)))
STREAM = "incident-host"


# The fixture domain, read and checked by the domain loader once for the module.
# am[verifies a-v2m-stream-1019@931fdc]
@pytest.fixture(scope="module")
def domain():
    return read_domain(DOMAIN_TEXT, "motivation-store-fixture.metta",
                       budget=RunBudget(inference_budget=None, timeout_seconds=300))


# A valid observation of calm, with any field changed.
# am[verifies a-v2m-st-records-1019@cd8ce5]
def _observation(**change) -> NeedObservation:
    fields = {"need": "calm", "level": 0.4, "scale": (0.0, 1.0), "estimator": "measured",
              "source": "sensor:hrv", "observed_at": AT}
    return NeedObservation(**{**fields, **change})


# am[verifies a-v2m-st-records-1019@cd8ce5]
def _attempt(**change) -> Attempt:
    fields = {"attempt": "exec-1", "action": "empathize", "applied_at": AT}
    return Attempt(**{**fields, **change})


# Observations and attempts are each recorded once under their keys, observe and attempt answering
# whether they appended; the history holds each kind in the order recorded, and its digest changes
# exactly when the stream does.
# am[verifies a-v2m-st-store-1019@670a6d] am[verifies a-v2m-stream-1019@931fdc]
def test_records_are_appended_once_and_read_back_in_order(domain) -> None:
    first, second = _observation(), _observation(level=0.7, observed_at=AT + timedelta(minutes=5),
                                                 produced_by="exec-1")
    with MotivationStore.memory(stream=STREAM) as store:
        assert store.observe(domain, first) is True
        before = store.history()
        assert store.observe(domain, first) is False
        assert store.history() == before
        assert store.attempt(domain, _attempt()) is True
        assert store.attempt(domain, _attempt()) is False
        assert store.observe(domain, second) is True
        assert store.attempt(domain, _attempt(attempt="exec-2", applied_at=None)) is True
        history = store.history()

    assert store.stream == STREAM
    assert history.observations == (first, second)
    assert history.attempts == (_attempt(), _attempt(attempt="exec-2", applied_at=None))
    assert history.digest != before.digest


# A file store reads back across a reopen exactly what it recorded, its digest included, and keeps
# its file private.
# am[verifies a-v2m-st-store-1019@670a6d]
def test_a_file_stream_reads_back_alike_after_reopening(domain, tmp_path) -> None:
    path = tmp_path / "motivation.sqlite3"
    with MotivationStore(path, stream=STREAM) as store:
        store.observe(domain, _observation())
        store.attempt(domain, _attempt())
        recorded = store.history()

    with MotivationStore(path, stream=STREAM) as store:
        assert store.history() == recorded
    assert path.stat().st_mode & 0o777 == 0o600


# One attempt id cannot carry two attempts: a different action or time under a recorded id is
# refused and leaves the stream as it was.
# am[verifies a-v2m-st-store-1019@670a6d]
@pytest.mark.parametrize("change", [{"action": "guide_breath"}, {"applied_at": None},
                                    {"review_fingerprint": "sha256:" + "a" * 64}])
def test_a_different_attempt_under_a_recorded_id_is_refused(domain, change) -> None:
    with MotivationStore.memory(stream=STREAM) as store:
        store.attempt(domain, _attempt())
        before = store.history()

        with pytest.raises(PersistenceError, match="different event is already recorded"):
            store.attempt(domain, _attempt(**change))

        assert store.history() == before


# Two stores on one file recording one observation from two threads at once record it once.
# am[verifies a-v2m-st-store-1019@670a6d]
def test_two_streams_racing_on_one_observation_record_it_once(domain, tmp_path) -> None:
    path = tmp_path / "race.sqlite3"
    MotivationStore(path, stream=STREAM).close()
    start = threading.Barrier(2)
    answers = []

    # A thread that fails breaks the barrier, so the other never waits for it.
    # am[verifies a-v2m-st-store-1019@670a6d]
    def observe():
        try:
            with MotivationStore(path, stream=STREAM) as store:
                start.wait()
                answers.append(store.observe(domain, _observation()))
        except BaseException:
            start.abort()
            raise

    threads = [threading.Thread(target=observe) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    with MotivationStore(path, stream=STREAM) as store:
        history = store.history()

    assert sorted(answers) == [False, True]
    assert history.observations == (_observation(),)


# A failure inside an append's transaction, an interrupt included, rolls it back and propagates
# unchanged; the stream holds nothing of it and the next append proceeds.
# am[verifies a-v2m-st-store-1019@670a6d]
@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_a_failed_append_is_rolled_back_and_the_next_proceeds(domain, monkeypatch, failure) -> None:
    def fail(*_):
        raise failure("injected")

    with MotivationStore.memory(stream=STREAM) as store:
        monkeypatch.setattr(StoreSchema, "event_id", fail)
        with pytest.raises(failure, match="injected"):
            store.observe(domain, _observation())
        monkeypatch.undo()

        assert not store._events._connection.in_transaction  # noqa: SLF001
        assert store.history().observations == ()
        assert store.observe(domain, _observation()) is True
        assert store.history().observations == (_observation(),)


# A record holds by construction what holds whatever the domain, so each of these is refused as it
# is built, before any store sees it.
# am[verifies a-v2m-st-records-1019@cd8ce5]
@pytest.mark.parametrize(("record", "change", "refusal"), [
    pytest.param(_observation, {"level": True}, "level must be a number", id="boolean level"),
    pytest.param(_observation, {"level": "0.4"}, "level must be a number", id="text level"),
    pytest.param(_observation, {"level": math.nan}, "level must be a finite number", id="NaN level"),
    pytest.param(_observation, {"level": math.inf}, "level must be a finite number", id="infinite level"),
    pytest.param(_observation, {"level": 10**400}, "level must be a finite number", id="level past a float"),
    pytest.param(_observation, {"level": 1.5}, "level must lie within its scale", id="level off its scale"),
    pytest.param(_observation, {"scale": (1.0, 0.0), "level": 0.5}, "low end below its high end",
                 id="reversed scale"),
    pytest.param(_observation, {"scale": (0.0, 0.0), "level": 0.0}, "low end below its high end",
                 id="empty scale"),
    pytest.param(_observation, {"scale": (False, 1.0)}, r"scale\[0\] must be a number", id="boolean bound"),
    pytest.param(_observation, {"scale": (0.0, 1.0, 2.0)}, "must be a pair of numbers", id="three bounds"),
    pytest.param(_observation, {"scale": "0 1"}, "must be a pair of numbers", id="text scale"),
    pytest.param(_observation, {"need": " "}, "need must be nonempty text", id="blank need"),
    pytest.param(_observation, {"estimator": "\ud800"}, "estimator must be UTF-8 text", id="surrogate estimator"),
    pytest.param(_observation, {"source": ""}, "source must be nonempty text", id="empty source"),
    pytest.param(_observation, {"produced_by": ""}, "produced_by must be nonempty text", id="empty producer"),
    pytest.param(_observation, {"observed_at": datetime(2026, 10, 20, 9, 0)}, "timezone-aware",
                 id="naive time"),
    pytest.param(_observation, {"observed_at": "2026-10-20T09:00:00+11:00"}, "timezone-aware",
                 id="time as text"),
    pytest.param(_observation, {"observed_at": datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=5)))},
                 "instant UTC can write", id="time before year 1 in UTC"),
    pytest.param(_observation, {"valid_until": AT - timedelta(microseconds=1)}, "must not precede observed_at",
                 id="validity ending first"),
    pytest.param(_attempt, {"attempt": ""}, "attempt.attempt must be nonempty text", id="empty attempt id"),
    pytest.param(_attempt, {"action": 7}, "attempt.action must be nonempty text", id="number action"),
    pytest.param(_attempt, {"applied_at": datetime(2026, 10, 20)}, "applied_at must be a timezone-aware",
                 id="naive application"),
    pytest.param(_attempt, {"review_fingerprint": " "}, "review_fingerprint must be nonempty text",
                 id="blank review fingerprint"),
])
def test_a_record_that_cannot_hold_is_refused_as_it_is_built(record, change, refusal) -> None:
    with pytest.raises(InvalidInputError, match=refusal):
        record(**change)


# What the domain or the vocabulary does not declare is refused before the append's transaction
# begins: the stream gains nothing, holds no transaction, and its next append proceeds.
# am[verifies a-v2m-st-store-1019@670a6d] am[verifies a-v2m-stream-1019@931fdc]
@pytest.mark.parametrize(("record", "refusal"), [
    (lambda store, domain: store.observe(domain, _observation(need="hunger")), "names no need the domain declares"),
    (lambda store, domain: store.observe(domain, _observation(scale=(0.0, 2.0))), "scale the domain declares"),
    (lambda store, domain: store.observe(domain, _observation(estimator="vibes")), "estimator must be one of"),
    (lambda store, domain: store.attempt(domain, _attempt(action="shout")), "names no action the domain declares"),
    (lambda store, domain: store.observe(domain, {"need": "calm"}), "must be a NeedObservation"),
    (lambda store, domain: store.attempt(domain, _observation()), "must be an Attempt"),
    (lambda store, domain: store.record(domain, observations=_observation()), "must be sequences of records"),
    (lambda store, domain: store.record(domain, observations=(_observation(),), budget=60), "budget must be a RunBudget"),
], ids=["undeclared need", "another scale", "unknown estimator", "undeclared action", "a mapping",
        "an observation as an attempt", "one observation as a batch", "seconds as a budget"])
def test_what_the_domain_does_not_declare_is_refused_before_the_transaction(domain, record, refusal) -> None:
    with MotivationStore.memory(stream=STREAM) as store:
        changes = store._events._connection.total_changes  # noqa: SLF001
        with pytest.raises(InvalidInputError, match=refusal):
            record(store, domain)

        assert store._events._connection.total_changes == changes  # noqa: SLF001
        assert not store._events._connection.in_transaction  # noqa: SLF001
        assert store.history().observations == () and store.history().attempts == ()
        assert store.observe(domain, _observation()) is True


# The batch the tests below record: two observations and two attempts.
# am[verifies a-v2m-st-batch-1019@a8d5f5]
def _batch() -> dict[str, tuple]:
    return {"observations": (_observation(), _observation(level=0.7)),
            "attempts": (_attempt(), _attempt(attempt="exec-2", applied_at=None))}


# check_records is record's own check, run with no store: it refuses each record the domain or the
# vocabulary does not declare with the very error record raises for it, and answers the records it
# accepts as tuples.
# am[verifies a-v2m-st-check-first-1020@d9378b]
@pytest.mark.parametrize(("observations", "attempts", "refusal"), [
    ((_observation(need="hunger"),), (), "names no need the domain declares"),
    ((_observation(scale=(0.0, 2.0)),), (), "scale the domain declares"),
    ((_observation(estimator="vibes"),), (), "estimator must be one of"),
    ((), (_attempt(action="shout"),), "names no action the domain declares"),
    (({"need": "calm"},), (), "must be a NeedObservation"),
    ((), (_observation(),), "must be an Attempt"),
    (_observation(), (), "must be sequences of records"),
], ids=["undeclared need", "another scale", "unknown estimator", "undeclared action", "a mapping",
        "an observation as an attempt", "one observation as a batch"])
def test_check_records_refuses_as_record_does_with_no_store(domain, observations, attempts, refusal) -> None:
    with pytest.raises(InvalidInputError, match=refusal) as checked:
        check_records(domain, observations, attempts)
    with MotivationStore.memory(stream=STREAM) as store, pytest.raises(InvalidInputError) as recorded:
        store.record(domain, observations, attempts)

    assert recorded.value.to_dict() == checked.value.to_dict()
    assert check_records(domain, iter(_batch()["observations"]), list(_batch()["attempts"])) == (
        _batch()["observations"], _batch()["attempts"])


# One record of a batch that the domain does not declare refuses the whole batch before its
# transaction: the stream gains none of the records around it.
# am[verifies a-v2m-st-batch-1019@a8d5f5]
def test_a_batch_with_one_undeclared_need_writes_nothing(domain) -> None:
    batch = _batch()
    with MotivationStore.memory(stream=STREAM) as store:
        changes = store._events._connection.total_changes  # noqa: SLF001
        with pytest.raises(InvalidInputError, match="names no need the domain declares"):
            store.record(domain, observations=(*batch["observations"], _observation(need="hunger")),
                         attempts=batch["attempts"])

        assert store._events._connection.total_changes == changes  # noqa: SLF001
        assert store.history().observations == () and store.history().attempts == ()


# A batch answers (key, appended) for each observation and then each attempt in order; sent again
# it appends nothing and answers False for each, and a record repeated within one batch is appended
# once, its repeat answering False.
# am[verifies a-v2m-st-batch-1019@a8d5f5] am[verifies c-v2m-st-batch-surface-1019@14cf84]
def test_a_batch_sent_again_appends_nothing_and_answers_false_for_each(domain) -> None:
    batch = _batch()
    keys = [observation.id for observation in batch["observations"]] + [attempt.attempt for attempt in batch["attempts"]]
    with MotivationStore.memory(stream=STREAM) as store:
        first = store.record(domain, **batch)
        recorded = store.history()
        again = store.record(domain, **batch)
        repeated = store.record(domain, observations=(_observation(level=0.1),) * 2)
        history = store.history()

    assert first == tuple((key, True) for key in keys)
    assert again == tuple((key, False) for key in keys)
    assert [appended for _, appended in repeated] == [True, False]
    assert recorded.observations == batch["observations"] and recorded.attempts == batch["attempts"]
    assert history.observations == (*batch["observations"], _observation(level=0.1))


# A different payload under a key the stream already holds, or under a key an earlier record of the
# same batch takes, rolls the whole batch back, the records before it included.
# am[verifies a-v2m-st-batch-1019@a8d5f5]
@pytest.mark.parametrize(("before", "attempts"), [
    ((_attempt(),), (_attempt(action="guide_breath"),)),
    ((), (_attempt(), _attempt(action="guide_breath"))),
], ids=["recorded before", "earlier in the batch"])
def test_a_conflict_anywhere_in_a_batch_rolls_the_whole_batch_back(domain, before, attempts) -> None:
    with MotivationStore.memory(stream=STREAM) as store:
        store.record(domain, attempts=before)
        recorded = store.history()

        with pytest.raises(PersistenceError, match="different event is already recorded"):
            store.record(domain, observations=_batch()["observations"], attempts=attempts)

        assert store.history() == recorded
        assert not store._events._connection.in_transaction  # noqa: SLF001


# Two stores on one file recording one batch from two threads at once append it once: one answers
# True for every record and the other False for every record.
# am[verifies a-v2m-st-batch-1019@a8d5f5]
def test_racing_identical_batches_append_once(domain, tmp_path) -> None:
    path = tmp_path / "race.sqlite3"
    MotivationStore(path, stream=STREAM).close()
    batch = _batch()
    start = threading.Barrier(2)
    answers = []

    # A thread that fails breaks the barrier, so the other never waits for it.
    # am[verifies a-v2m-st-batch-1019@a8d5f5]
    def record():
        try:
            with MotivationStore(path, stream=STREAM) as store:
                start.wait()
                answers.append(store.record(domain, **batch))
        except BaseException:
            start.abort()
            raise

    threads = [threading.Thread(target=record) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    with MotivationStore(path, stream=STREAM) as store:
        history = store.history()

    assert sorted(tuple(appended for _, appended in answer) for answer in answers) == [(False,) * 4, (True,) * 4]
    assert history.observations == batch["observations"] and history.attempts == batch["attempts"]


# The SQL statements a store's connection runs while `act` runs.
# am[verifies a-v2m-st-deadline-1020@64df73]
def _statements(store: MotivationStore, act) -> list[str]:
    statements = []
    store._events._connection.set_trace_callback(statements.append)  # noqa: SLF001
    try:
        act()
    finally:
        store._events._connection.set_trace_callback(None)  # noqa: SLF001
    return statements


# A budget already spent, its inferences or its time, refuses the batch with its own exhaustion
# before any statement runs, so no transaction begins and nothing is written.
# am[verifies a-v2m-st-deadline-1020@64df73]
@pytest.mark.parametrize("spent", ["inferences", "time"])
def test_an_exhausted_budget_writes_nothing_and_begins_no_transaction(domain, monkeypatch, spent) -> None:
    budget = RunBudget(inference_budget=1, timeout_seconds=60)
    if spent == "inferences":
        budget.charge(1)
    else:
        later = time.monotonic() + 120
        monkeypatch.setattr(budget_module.time, "monotonic", lambda: later)
    exhaustion = InferenceBudgetExceeded if spent == "inferences" else ReviewTimeout
    with MotivationStore.memory(stream=STREAM) as store:
        refused = []

        # am[verifies a-v2m-st-deadline-1020@64df73]
        def record():
            with pytest.raises(exhaustion) as raised:
                store.record(domain, **_batch(), budget=budget)
            refused.append(raised.value)

        statements = _statements(store, record)
        monkeypatch.undo()
        history = store.history()

    assert statements == [] and len(refused) == 1
    assert history.observations == () and history.attempts == ()


# A write lock another connection holds past the deadline ends the wait at the deadline, not after
# the store's five seconds: the budget's ReviewTimeout is raised, nothing is written, and the store
# waits its own five seconds again afterwards.
# am[verifies a-v2m-st-deadline-1020@64df73] am[verifies c-v2m-st-busy-wait-measured-1020@466e30]
def test_a_lock_held_past_the_deadline_raises_its_timeout_within_the_budget(domain, tmp_path) -> None:
    path = tmp_path / "locked.sqlite3"
    with MotivationStore(path, stream=STREAM) as store:
        with closing(sqlite3.connect(path, isolation_level=None)) as holder:
            holder.execute("BEGIN IMMEDIATE")
            start = time.monotonic()
            with pytest.raises(ReviewTimeout):
                store.record(domain, **_batch(), budget=RunBudget(inference_budget=None, timeout_seconds=0.5))
            waited = time.monotonic() - start
            holder.execute("ROLLBACK")
        wait_after = store._events._connection.execute("PRAGMA busy_timeout").fetchone()[0]  # noqa: SLF001
        history = store.history()

    assert 0.45 <= waited < 2.0
    assert wait_after == 5000
    assert history.observations == () and history.attempts == ()


# A lock wait that ends while the budget still holds, here at the store's own wait made short, is
# the store's PersistenceError, not the budget's exhaustion.
# am[verifies a-v2m-st-deadline-1020@64df73]
def test_a_lock_wait_ending_before_the_deadline_is_a_persistence_error(domain, tmp_path, monkeypatch) -> None:
    path = tmp_path / "locked.sqlite3"
    monkeypatch.setattr(event_store, "_LOCK_WAIT_SECONDS", 0.2)
    with MotivationStore(path, stream=STREAM) as store:
        with closing(sqlite3.connect(path, isolation_level=None)) as holder:
            holder.execute("BEGIN IMMEDIATE")
            with pytest.raises(PersistenceError, match="Unable to append the motivation event") as refused:
                store.record(domain, **_batch(), budget=RunBudget(inference_budget=None, timeout_seconds=60))
            holder.execute("ROLLBACK")
        history = store.history()

    assert refused.value.details["error"] == "database is locked"
    assert history.observations == ()


# A write request opens its stream and records under one budget, as run_motivation_request does:
# behind another connection's write lock the open of the existing stream does not wait, and the
# whole request ends with the budget's ReviewTimeout after about its 0.5 s, writing nothing
# (c-v2m-st-open-repro-1020).
# am[verifies a-v2m-st-open-deadline-1020@13fed4] am[verifies a-v2m-st-open-repro-1020@075517]
def test_a_request_opening_and_recording_behind_a_writer_ends_by_its_deadline(domain, tmp_path) -> None:
    path = tmp_path / "locked.sqlite3"
    MotivationStore(path, stream=STREAM).close()
    with closing(sqlite3.connect(path, isolation_level=None)) as holder:
        holder.execute("BEGIN IMMEDIATE")
        budget = RunBudget(inference_budget=None, timeout_seconds=0.5)
        start = time.monotonic()
        with pytest.raises(ReviewTimeout):
            with MotivationStore(path, stream=STREAM, budget=budget) as store:
                store.record(domain, **_batch(), budget=budget)
        waited = time.monotonic() - start
        holder.execute("ROLLBACK")
    with MotivationStore(path, stream=STREAM, create=False) as store:
        history = store.history()

    assert 0.45 <= waited < 2.0
    assert history.observations == () and history.attempts == ()


# The open refuses a budget that is no RunBudget, as record does.
# am[verifies a-v2m-st-open-budget-1020@874189]
def test_an_open_refuses_a_budget_that_is_no_run_budget(tmp_path) -> None:
    with pytest.raises(InvalidInputError, match="budget must be a RunBudget"):
        MotivationStore(tmp_path / "motivation.sqlite3", stream=STREAM, budget=60)

    assert list(tmp_path.iterdir()) == []


# A deadline passing while the batch inserts is found before COMMIT: the whole batch rolls back,
# the budget's ReviewTimeout propagates, and no transaction is left open.
# am[verifies a-v2m-st-deadline-1020@64df73]
def test_a_deadline_passing_before_commit_rolls_the_batch_back(domain, monkeypatch) -> None:
    now = [time.monotonic()]
    monkeypatch.setattr(budget_module.time, "monotonic", lambda: now[0])
    budget = RunBudget(inference_budget=None, timeout_seconds=10)
    event_id = StoreSchema.event_id

    # Each event's id is made between its inserts; the clock passes the deadline there.
    # am[verifies a-v2m-st-deadline-1020@64df73]
    def late(schema, *arguments):
        now[0] += 60
        return event_id(schema, *arguments)

    with MotivationStore.memory(stream=STREAM) as store:
        monkeypatch.setattr(StoreSchema, "event_id", late)
        with pytest.raises(ReviewTimeout):
            store.record(domain, **_batch(), budget=budget)
        monkeypatch.undo()

        assert not store._events._connection.in_transaction  # noqa: SLF001
        assert store.history().observations == () and store.history().attempts == ()


# Within its budget a batch commits and answers as it does without one, and a deadline passing as
# COMMIT runs raises nothing once COMMIT has returned.
# am[verifies a-v2m-st-deadline-1020@64df73]
def test_a_batch_committed_within_its_budget_answers_as_without_one(domain, monkeypatch) -> None:
    now = [time.monotonic()]
    monkeypatch.setattr(budget_module.time, "monotonic", lambda: now[0])
    budget = RunBudget(inference_budget=None, timeout_seconds=10)
    with MotivationStore.memory(stream=STREAM) as store, MotivationStore.memory(stream=STREAM) as plain:

        # The clock passes the deadline as COMMIT starts.
        # am[verifies a-v2m-st-deadline-1020@64df73]
        def committing(statement):
            if statement == "COMMIT":
                now[0] += 60

        store._events._connection.set_trace_callback(committing)  # noqa: SLF001
        answers = store.record(domain, **_batch(), budget=budget)
        store._events._connection.set_trace_callback(None)  # noqa: SLF001
        assert answers == plain.record(domain, **_batch())
        assert store.history().observations == plain.history().observations
        assert store._events._connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000  # noqa: SLF001


# A read refuses a path holding no stream and creates nothing there: a missing file, an empty file,
# a file whose metadata table was made but never filled, and no path at all.
# am[verifies a-v2m-st-read-refuses-1020@676ded]
@pytest.mark.parametrize("holding", ["nothing", "an empty file", "an empty metadata table", "no path"])
def test_a_read_refuses_a_path_holding_no_stream_and_creates_nothing(tmp_path, holding) -> None:
    path = None if holding == "no path" else tmp_path / "motivation.sqlite3"
    if holding == "an empty file":
        path.write_bytes(b"")
    elif holding == "an empty metadata table":
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    before = {child.name: child.read_bytes() for child in tmp_path.iterdir()}

    with pytest.raises(PersistenceError, match="^No motivation store is at the database path.$") as refused:
        MotivationStore(path, stream=STREAM, create=False)

    assert dict(refused.value.details) == {"path": ":memory:" if path is None else str(path)}
    assert {child.name: child.read_bytes() for child in tmp_path.iterdir()} == before


# A read opens an existing stream without taking the write lock, so a writer holding it does not
# delay the read, and refuses another stream's file, a SNARS store and another application's
# database as an open that may create does.
# am[verifies a-v2m-st-read-refuses-1020@676ded]
def test_a_read_opens_an_existing_stream_without_the_write_lock_and_keeps_every_refusal(domain, tmp_path) -> None:
    path = tmp_path / "motivation.sqlite3"
    with MotivationStore(path, stream=STREAM) as store:
        store.record(domain, **_batch())
        recorded = store.history()
    with closing(sqlite3.connect(path, isolation_level=None)) as holder:
        holder.execute("BEGIN IMMEDIATE")
        start = time.monotonic()
        with MotivationStore(path, stream=STREAM, create=False) as reader:
            assert reader.history() == recorded
        opened = time.monotonic() - start
        holder.execute("ROLLBACK")
    snars, application = tmp_path / "snars.sqlite3", tmp_path / "application.sqlite3"
    SnarsEventStore(snars, snars_identity="c" * 64).close()
    with closing(sqlite3.connect(application)) as connection, connection:
        connection.execute("CREATE TABLE events (id INTEGER PRIMARY KEY)")

    assert opened < 1.0
    for other, refusal in [(path, "does not match this runtime"), (snars, "does not match this runtime"),
                           (application, "holds tables but no store metadata")]:
        stream = "other" if other == path else STREAM
        with pytest.raises(PersistenceError, match=refusal):
            MotivationStore(other, stream=stream, create=False)


# Equal records share one id however they were spelled: -0.0 is 0.0, an integral level is its
# float, a scale given as a list is the pair, and one instant in any offset is one time.
# am[verifies a-v2m-st-records-1019@cd8ce5] am[verifies c-v2m-st-negative-zero-1019@7e0645]
def test_equal_observations_share_one_id_however_they_were_spelled() -> None:
    plain = _observation(level=0.0, scale=(0.0, 1.0))
    spelled = _observation(level=-0.0, scale=[-0.0, 1], observed_at=AT.astimezone(timezone.utc))

    assert spelled == plain and spelled.id == plain.id
    assert spelled.scale == (0.0, 1.0) and math.copysign(1.0, spelled.level) == 1.0
    assert _observation(level=1, scale=(0, 1)).id == _observation(level=1.0).id
    assert plain.identity()["observed_at"] == "2026-10-19T22:00:00+00:00"


# The JSON shapes: an observation and an attempt parse from their identities, the optional fields
# absent or null; an unknown or missing field, a time without an offset or finer than a
# microsecond, and a value of the wrong type are refused.
# am[verifies a-v2m-st-records-1019@cd8ce5]
def test_the_json_shapes_parse_their_records_and_refuse_every_other() -> None:
    observation = _observation(valid_until=AT + timedelta(hours=1), produced_by="exec-1")
    shape = {"need": "calm", "level": 0.4, "scale": [0, 1], "estimator": "measured", "source": "sensor:hrv",
             "observed_at": "2026-10-20T09:00:00+11:00"}

    assert parse_observation(observation.identity()) == observation
    assert parse_observation(shape) == parse_observation({**shape, "valid_until": None, "produced_by": None})
    assert parse_attempt({"attempt": "exec-1", "action": "empathize", "applied_at": None}).applied_at is None
    assert parse_attempt(_attempt(review_fingerprint="sha256:x").identity()) == _attempt(review_fingerprint="sha256:x")
    for payload, refusal in [
        ({**shape, "note": "x"}, r"unknown \['note'\], missing \[\]"),
        ({key: value for key, value in shape.items() if key != "level"}, r"missing \['level'\]"),
        ([shape], "must be an object"),
        ({**shape, "observed_at": "2026-10-20T09:00:00"}, "observed_at must carry a timezone offset"),
        ({**shape, "observed_at": "2026-10-20T09:00:00.1234567+11:00"}, "finer than a microsecond"),
        ({**shape, "observed_at": 1760911200}, "observed_at must be ISO-8601 text"),
        ({**shape, "valid_until": "soon"}, "valid_until must be an ISO-8601 time"),
        ({**shape, "level": "0.4"}, "level must be a number"),
    ]:
        with pytest.raises(InvalidInputError, match=refusal):
            parse_observation(payload)
    with pytest.raises(InvalidInputError, match=r"missing \['applied_at'\]"):
        parse_attempt({"attempt": "exec-1", "action": "empathize"})


# A motivation stream's file is its own: another stream's, and a SNARS store's, are refused when
# they open with every byte as it was, and a SNARS store refuses a motivation stream's file.
# am[verifies a-v2m-event-store-1019@c43bc2] am[verifies a-v2m-st-store-1019@670a6d]
@pytest.mark.parametrize(("write", "open_", "refusal"), [
    (lambda path: MotivationStore(path, stream="other").close(),
     lambda path: MotivationStore(path, stream=STREAM), "Motivation store metadata does not match"),
    (lambda path: SnarsEventStore(path, snars_identity="c" * 64).close(),
     lambda path: MotivationStore(path, stream=STREAM), "Motivation store metadata does not match"),
    (lambda path: MotivationStore(path, stream=STREAM).close(),
     lambda path: SnarsEventStore(path, snars_identity="c" * 64), "SNARS store metadata does not match"),
], ids=["another stream", "a SNARS store", "a motivation stream as SNARS"])
def test_a_file_of_another_stream_or_store_is_refused_untouched(tmp_path, write, open_, refusal) -> None:
    path = tmp_path / "store.sqlite3"
    write(path)
    before = path.read_bytes()

    with pytest.raises(PersistenceError, match=refusal):
        open_(path)

    assert path.read_bytes() == before


# Events the stream itself never writes, written into its file through its schema: replay refuses
# an event of another kind, a payload no record parses from, a payload that is not its record's
# identity, and an event under any key but the one its record derives, or under none.
# am[verifies a-v2m-st-store-1019@670a6d] am[verifies a-v2m-stream-1019@931fdc]
@pytest.mark.parametrize(("kind", "payload", "key", "refusal"), [
    ("note", {"text": "x"}, None, "kind is unknown"),
    (OBSERVATION_KIND, {**_observation().identity(), "level": 7.0}, "k", "not a valid record"),
    (ATTEMPT_KIND, {**_attempt().identity(), "applied_at": "2026-10-20T09:00:00+11:00"}, "exec-1",
     "not its record's identity"),
    (OBSERVATION_KIND, _observation().identity(), "another", "not recorded under the key its payload derives"),
    (OBSERVATION_KIND, _observation().identity(), None, "not recorded under the key its payload derives"),
    (ATTEMPT_KIND, _attempt().identity(), "exec-2", "not recorded under the key its payload derives"),
], ids=["another kind", "an invalid record", "a non-canonical payload", "another key", "no key",
        "another attempt id"])
def test_replay_refuses_an_event_the_stream_never_writes(tmp_path, kind, payload, key, refusal) -> None:
    path = tmp_path / "motivation.sqlite3"
    with EventStore(path, schema=SCHEMA, identity=STREAM) as events:
        events.append_prepared(kind, payload, key=key)

    with MotivationStore(path, stream=STREAM) as store, pytest.raises(PersistenceError, match=refusal):
        store.history()


# Valid observations, drawn over both needs' scales, every estimator class, any offset and optional
# validity and producer, survive their JSON round trip with one id, and a stream given any sequence
# of them, repeats included, records each once and reads them back in first-recorded order.
text = st.text(st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=6).filter(str.strip)
moments = st.builds(
    lambda moment, minutes: moment.replace(tzinfo=timezone(timedelta(minutes=minutes))),
    st.datetimes(min_value=datetime(2, 1, 1), max_value=datetime(9998, 12, 31)),
    st.integers(-1439, 1439),
)


# am[verifies a-v2m-st-records-1019@cd8ce5]
@st.composite
def observations(draw):
    need, scale = draw(st.sampled_from([("calm", (0.0, 1.0)), ("skill", (-1.0, 1.0))]))
    observed_at = draw(moments)
    return NeedObservation(
        need=need,
        level=draw(st.floats(*scale)),
        scale=scale,
        estimator=draw(st.sampled_from(vocabulary().classes)),
        source=draw(text),
        observed_at=observed_at,
        valid_until=draw(st.none() | st.timedeltas(timedelta(0), timedelta(days=30)).map(observed_at.__add__)),
        produced_by=draw(st.none() | text),
    )


# am[verifies a-v2m-st-records-1019@cd8ce5]
@settings(max_examples=200, deadline=None)
@given(observations())
def test_an_observation_survives_its_json_round_trip_with_one_id(observation) -> None:
    stored = json.loads(canonical_json(observation.identity()))

    assert parse_observation(stored) == observation
    assert parse_observation(stored).identity() == observation.identity() == stored
    assert parse_observation(stored).id == observation.id == fingerprint_of(stored)


# am[verifies a-v2m-st-store-1019@670a6d]
@settings(max_examples=40, deadline=None)
@given(st.lists(observations(), max_size=6).flatmap(
    lambda drawn: st.lists(st.sampled_from(drawn), max_size=10) if drawn else st.just([])))
def test_a_stream_records_each_observation_once_in_first_recorded_order(domain, sequence) -> None:
    with MotivationStore.memory(stream=STREAM) as store:
        answers = [store.observe(domain, observation) for observation in sequence]
        history = store.history()

    first = list(dict.fromkeys(sequence))
    assert history.observations == tuple(first)
    assert answers == [index == sequence.index(observation) for index, observation in enumerate(sequence)]


# A history through an earlier read's event count is that read, its digest included, whatever has
# been appended since, a record backdated before every other among it; zero is the empty prefix,
# with the digest of no events.
# am[verifies a-v2r-history-prefix-1020] am[verifies c-v2r-store-prefix-immutable-1020]
def test_a_history_through_an_earlier_count_is_that_read(domain) -> None:
    with MotivationStore.memory(stream=STREAM) as store:
        store.observe(domain, _observation())
        store.attempt(domain, _attempt())
        earlier = store.history()
        store.observe(domain, _observation(level=0.9, observed_at=AT - timedelta(days=1), source="sensor:late"))
        replayed = store.history(through=len(earlier.observations) + len(earlier.attempts))
        latest, empty = store.history(), store.history(through=0)

    assert replayed == earlier
    assert len(latest.observations) == 2 and latest.digest != earlier.digest
    assert (empty.observations, empty.attempts, empty.digest) == ((), (), event_store.digest(()))


# A count of events must be an integer of at least 0, never a boolean, refused before the store is
# read; a count beyond the events the stream holds is the store's refusal.
# am[verifies a-v2r-history-prefix-1020]
@pytest.mark.parametrize("through, refusal", [
    (True, InvalidInputError), (-1, InvalidInputError), (1.0, InvalidInputError), ("1", InvalidInputError),
    (2, PersistenceError),
])
def test_a_history_through_no_prefix_of_the_stream_is_refused(domain, through, refusal) -> None:
    with MotivationStore.memory(stream=STREAM) as store:
        store.observe(domain, _observation())
        with pytest.raises(refusal):
            store.history(through=through)


# A history through N reads events 1 to N alone: a later event the store would refuse as corrupt
# leaves the prefix readable, while a read of the whole stream refuses it.
# am[verifies a-v2r-history-prefix-1020] am[related a-v2r-prefix-read-1020]
def test_a_history_through_a_count_reads_only_that_prefix(domain) -> None:
    with MotivationStore.memory(stream=STREAM) as store:
        store.observe(domain, _observation())
        store.attempt(domain, _attempt())
        earlier = store.history()
        store.observe(domain, _observation(level=0.9, source="sensor:late"))
        store._events._connection.execute("UPDATE events SET payload_json = '{}' WHERE sequence = 3")  # noqa: SLF001
        with pytest.raises(PersistenceError):
            store.history()
        assert store.history(through=2) == earlier


# A history keeps a caller's deadline while it replays its events: a deadline passing during one
# event's replay raises the budget's ReviewTimeout before the next, or after the last, and never
# answers; within the deadline the history is the one read without a budget.
# am[verifies a-v2r-history-prefix-1020] am[verifies i-v2rs-history-unbudgeted-1020]
@pytest.mark.parametrize("through", [None, 1, 2])
def test_a_history_replay_keeps_the_callers_deadline(domain, monkeypatch, through) -> None:
    now = [time.monotonic()]
    monkeypatch.setattr(budget_module.time, "monotonic", lambda: now[0])
    replayed = motivation_store._replayed  # noqa: SLF001

    # The clock passes the deadline while an event is replayed.
    # am[verifies i-v2rs-history-unbudgeted-1020]
    def late(event):
        now[0] += 60
        return replayed(event)

    with MotivationStore.memory(stream=STREAM) as store:
        store.observe(domain, _observation())
        store.attempt(domain, _attempt())
        assert store.history(through, budget=RunBudget(inference_budget=None, timeout_seconds=10)) == store.history(through)
        monkeypatch.setattr(motivation_store, "_replayed", late)
        with pytest.raises(ReviewTimeout):
            store.history(through, budget=RunBudget(inference_budget=None, timeout_seconds=10))


# The deadline is read again after the history's digest is computed, so a deadline passing while
# the events are hashed raises the budget's ReviewTimeout instead of answering the history.
# am[verifies a-v2r-history-prefix-1020] am[verifies i-v2rs-history-unbudgeted-1020]
def test_a_history_digest_past_the_deadline_never_answers(domain, monkeypatch) -> None:
    now = [time.monotonic()]
    monkeypatch.setattr(budget_module.time, "monotonic", lambda: now[0])
    hashed = motivation_store.digest

    # The clock passes the deadline while the events are hashed.
    # am[verifies i-v2rs-history-unbudgeted-1020]
    def late(events):
        now[0] += 60
        return hashed(events)

    with MotivationStore.memory(stream=STREAM) as store:
        store.observe(domain, _observation())
        monkeypatch.setattr(motivation_store, "digest", late)
        with pytest.raises(ReviewTimeout):
            store.history(budget=RunBudget(inference_budget=None, timeout_seconds=10))

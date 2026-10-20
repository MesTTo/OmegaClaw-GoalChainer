"""Purpose: verify the JSON motivation request end to end on a file domain with needs and a store file:
observe and attempt record a whole batch once per key, status reports the stream's snapshot at its
instant, a review request naming the stream reviews by it, a request refused by its shape, its
domain, a record's JSON or its budget opens no store, a batch the store refuses writes no event,
identical batches racing record each key once, and the snapshot does not depend on the order or
batching in which records arrived."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import goal_chainer.motivation.requests as motivation_requests
import goal_chainer.requests as domain_requests
from goal_chainer.errors import InvalidInputError, PersistenceError
from goal_chainer.motivation import MOTIVATION_REQUEST_PROTOCOL, parse_observation, run_motivation_request
from goal_chainer.runtime import budget as budget_module
from goal_chainer.runtime.budget import InferenceBudgetExceeded, ReviewTimeout, RunBudget
from motivation_support import CORE, NEEDS, at

STREAM = "student-1"


# Malformed transport fields must not consume domain or model work.
# am[verifies a-v2-motivation-input-order-1020@d40cf5]
@pytest.mark.parametrize("entry", ["motivation", "domain"])
@pytest.mark.parametrize("selection", [
    {"store": "store.sqlite3"}, {"store": "", "stream": "s"},
    {"store": "store.sqlite3", "stream": "\ud800"},
    {"store": "\ud800.sqlite3", "stream": "s"},
])
def test_malformed_stream_selection_is_refused_before_domain_work(monkeypatch, entry, selection):
    # am[verifies a-v2-motivation-input-order-1020@d40cf5]
    def forbidden(*args, **kwargs):
        pytest.fail("malformed motivation reached domain work")

    monkeypatch.setattr(domain_requests, "_domain", forbidden)
    request = {"domain": {"packaged": "task-control"}, "motivation": selection}
    with pytest.raises(InvalidInputError):
        if entry == "motivation":
            run_motivation_request({**request, "operation": "status", "as_of": at(1).isoformat()}, budget=_budget())
        else:
            domain_requests.run_request({**request, "operation": "review", "context": {
                "review_id": "r", "subject": "s", "trigger": "t", "authority": "advisory",
                "as_of": at(1).isoformat(), "readings": [],
            }}, budget=_budget())


# A stream that cannot be read must not trigger a hosted semantic-reading request.
# am[verifies a-v2-motivation-input-order-1020@d40cf5]
def test_unreadable_stream_stops_before_hosted_reading(where, monkeypatch):
    # am[verifies a-v2-motivation-input-order-1020@d40cf5]
    def forbidden(*args, **kwargs):
        pytest.fail("unreadable motivation reached hosted reading")

    monkeypatch.setattr(domain_requests, "_read", forbidden)
    request = {"operation": "review", "domain": where.domain, "motivation": where.motivation,
               "reading": {"text": "original words"}, "context": {
                   "review_id": "r", "subject": "s", "trigger": "t", "authority": "advisory",
                   "as_of": at(1).isoformat(), "readings": [],
               }}
    with pytest.raises(PersistenceError):
        domain_requests.run_request(request, budget=_budget())
    assert not where.store.exists()


# am[verifies a-v2m-request-cycle-1019@abb37d]
def _budget() -> RunBudget:
    return RunBudget(inference_budget=1_000_000_000, timeout_seconds=300)


# A companion domain file and a store path beside it; nothing creates the store but a request.
# am[verifies a-v2m-request-cycle-1019@abb37d]
@pytest.fixture
def where(tmp_path: Path) -> SimpleNamespace:
    domain = tmp_path / "companion.metta"
    domain.write_text(CORE + NEEDS, encoding="utf-8")
    store = tmp_path / "motivation.sqlite3"
    return SimpleNamespace(domain={"path": str(domain)}, store=store,
                           motivation={"store": str(store), "stream": STREAM})


# am[verifies a-v2m-request-cycle-1019@abb37d]
def _observation(need: str, level: float, seconds: float, **fields: Any) -> dict[str, Any]:
    return {"need": need, "level": level, "scale": [0, 1], "estimator": "measured", "source": "host:check-in",
            "observed_at": at(seconds).isoformat(), **fields}


# am[verifies a-v2m-request-cycle-1019@abb37d]
def _attempt(attempt: str, action: str, seconds: float | None) -> dict[str, Any]:
    return {"attempt": attempt, "action": action, "applied_at": None if seconds is None else at(seconds).isoformat()}


# am[verifies a-v2m-request-cycle-1019@abb37d]
def _send(where: SimpleNamespace, operation: str, records: Any = None, *, budget: RunBudget | None = None,
          motivation: dict[str, str] | None = None, as_of: float = 1000.0, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"operation": operation, "domain": where.domain,
                               "motivation": motivation or where.motivation, **fields}
    if operation == "status":
        payload["as_of"] = at(as_of).isoformat()
    else:
        payload["observations" if operation == "observe" else "attempts"] = records
    return run_motivation_request(payload, budget=budget or _budget())


# A baseline, an attempt of empathize and the outcome the host attributes to it: one sample.
# am[verifies a-v2m-request-cycle-1019@abb37d]
def _one_cycle(where: SimpleNamespace) -> None:
    _send(where, "observe", [_observation("nurture", 0.3, 10)])
    _send(where, "attempt", [_attempt("a1", "empathize", 20)])
    _send(where, "observe", [_observation("nurture", 0.5, 30, produced_by="a1")])


# A batch is answered key by key in order, and sending it again records nothing new.
# am[verifies a-v2m-request-cycle-1019@abb37d] am[verifies a-v2m-st-batch-1019@a8d5f5]
def test_observe_records_each_key_once_and_a_resend_records_nothing(where) -> None:
    batch = [_observation("nurture", 0.3, 10), _observation("calm", 0.5, 10)]
    keys = [parse_observation(item).id for item in batch]

    first = _send(where, "observe", batch)
    again = _send(where, "observe", batch)

    assert first["protocol"] == MOTIVATION_REQUEST_PROTOCOL and first["stream"] == STREAM
    assert (first["recorded"], first["already_recorded"]) == (keys, [])
    assert (again["recorded"], again["already_recorded"]) == ([], keys)


# status reads the stream at its own instant: the level as observed then, and the change the
# attempt's attributed outcome measured, against the declared one it replaced.
# am[verifies a-v2m-request-cycle-1019@abb37d] am[verifies a-v2m-expectations-1019@b13468] am[verifies a-v2m-levels-1019@387e68]
def test_status_reports_the_streams_learned_change_and_level_at_its_instant(where) -> None:
    _one_cycle(where)

    later = _send(where, "status", as_of=100)["snapshot"]
    earlier = _send(where, "status", as_of=15)["snapshot"]

    level = next(item for item in later["levels"] if item["need"] == "nurture")
    change = next(item for item in later["changes"] if (item["action"], item["need"]) == ("empathize", "nurture"))
    assert (level["state"], level["level"]) == ("observed", 0.5)
    assert (change["state"], change["count"], change["estimator"]) == ("measured", 1, "receipt-calibrated")
    assert change["change"] == pytest.approx(0.2)
    assert later["samples"][0]["expected"] == 0.3 and later["samples"][0]["residual"] == pytest.approx(-0.1)
    assert next(item for item in earlier["levels"] if item["need"] == "nurture")["level"] == 0.3
    assert next(item for item in earlier["changes"]
                if (item["action"], item["need"]) == ("empathize", "nurture"))["state"] == "declared"


# A review request naming the stream reviews by its snapshot at the packet's instant; without the
# field the review reads an empty stream, so the two fingerprints differ.
# am[verifies a-v2m-request-cycle-1019@abb37d] am[verifies a-v2m-snapshot-identity-1019@118a4b]
def test_a_review_request_reviews_by_the_named_stream(where) -> None:
    _one_cycle(where)
    context = {"review_id": "companion-turn", "subject": STREAM, "trigger": "turn", "as_of": at(100).isoformat(),
               "authority": "advisory",
               "readings": [{"signal": "session_open", "state": "detected", "source": "host:session",
                             "estimator": "deterministic", "observed_at": at(100).isoformat()}]}
    request = {"operation": "review", "domain": where.domain, "context": context}

    named = domain_requests.run_request({**request, "motivation": where.motivation}, budget=_budget())
    unnamed = domain_requests.run_request(request, budget=_budget())

    stream = named["review"]["motivation"]
    assert stream["stream"] == STREAM
    assert next(item for item in stream["levels"] if item["need"] == "nurture")["level"] == 0.5
    assert unnamed["review"]["motivation"]["stream"] is None
    assert {item["state"] for item in unnamed["review"]["motivation"]["levels"]} == {"unobserved"}
    assert named["review"]["fingerprint"] != unnamed["review"]["fingerprint"]
    assert (named["authorization"], named["applies_effects"]) == ("unresolved", False)


# One well-formed record the domain does not declare refuses its whole batch before the store is
# opened, so a store path holding nothing still holds nothing.
# am[verifies a-v2m-request-cycle-1019@abb37d] am[verifies a-v2m-st-check-first-1020@d9378b]
@pytest.mark.parametrize("operation, refused", [
    ("observe", _observation("thirst", 0.3, 10)),
    ("observe", _observation("nurture", 0.3, 10, scale=[0, 2])),
    ("observe", _observation("nurture", 0.3, 10, estimator="astrology")),
    ("attempt", _attempt("a9", "dance", 20)),
], ids=["undeclared-need", "another-scale", "undeclared-estimator", "undeclared-action"])
def test_a_record_the_domain_does_not_declare_refuses_its_batch_and_creates_no_store(where, operation, refused) -> None:
    declared = _observation("nurture", 0.3, 10) if operation == "observe" else _attempt("a1", "empathize", 20)

    with pytest.raises(InvalidInputError):
        _send(where, operation, [declared, refused])

    assert not where.store.exists()


# A read names a stream that must already be there: status, or a review's motivation field, naming a
# path that holds no store is refused and creates nothing.
# am[verifies a-v2m-request-cycle-1019@abb37d] am[verifies a-v2m-st-read-refuses-1020@676ded]
def test_a_read_of_a_path_holding_no_store_is_refused_and_creates_nothing(where) -> None:
    context = {"review_id": "companion-turn", "subject": STREAM, "trigger": "turn", "as_of": at(100).isoformat(),
               "authority": "advisory", "readings": []}

    with pytest.raises(PersistenceError):
        _send(where, "status")
    with pytest.raises(PersistenceError):
        domain_requests.run_request({"operation": "review", "domain": where.domain, "context": context,
                                     "motivation": where.motivation}, budget=_budget())

    assert not where.store.exists()


# A different attempt under a recorded attempt id rolls back the whole batch it came in, the new
# attempt beside it included.
# am[verifies a-v2m-request-cycle-1019@abb37d] am[verifies a-v2m-st-batch-1019@a8d5f5]
def test_a_conflicting_attempt_rolls_its_whole_batch_back(where) -> None:
    _send(where, "attempt", [_attempt("a1", "empathize", 20)])

    with pytest.raises(PersistenceError):
        run_motivation_request({"operation": "attempt", "domain": where.domain, "motivation": where.motivation,
                                "attempts": [_attempt("a2", "stay_silent", 30), _attempt("a1", "guide_breath", 20)]},
                               budget=_budget())

    again = _send(where, "attempt", [_attempt("a2", "stay_silent", 30)])
    assert again["recorded"] == ["a2"]


# Identical batches sent at once append each record once between them.
# am[verifies a-v2m-request-cycle-1019@abb37d] am[verifies a-v2m-st-batch-1019@a8d5f5]
def test_identical_batches_racing_record_each_key_once(where) -> None:
    batch = [_observation("nurture", 0.3, 10), _observation("calm", 0.5, 10)]
    answers: list[dict[str, Any]] = []
    errors: list[BaseException] = []
    start = threading.Barrier(2)

    def send() -> None:
        start.wait()
        try:
            answers.append(_send(where, "observe", batch))
        except BaseException as error:  # noqa: BLE001 (the assertion below reports it)
            errors.append(error)

    threads = [threading.Thread(target=send) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    recorded = [key for answer in answers for key in answer["recorded"]]
    already = [key for answer in answers for key in answer["already_recorded"]]
    assert sorted(recorded) == sorted(parse_observation(item).id for item in batch)
    assert sorted(already) == sorted(recorded)


# Each of these is refused before the store is opened, so no store file is left behind; STORE
# stands for the fixture's store path.
# am[verifies a-v2m-request-cycle-1019@abb37d]
@pytest.mark.parametrize("change", [
    {"operation": "forget"},
    {"operation": None},
    {"extra": 1},
    {"observations": {"need": "nurture"}},
    {"observations": [{"need": "nurture"}]},
    {"observations": [_observation("nurture", 0.3, 10, observed_at="2026-10-20T09:00:00")]},
    {"observations": [_observation("nurture", True, 10)]},
    {"motivation": {"store": "", "stream": STREAM}},
    {"motivation": {"store": "STORE"}},
    {"motivation": {"store": "STORE", "stream": STREAM, "extra": 1}},
    {"motivation": [STREAM]},
    {"domain": {"packaged": "incident"}},
    {"domain": {"path": "no-such-domain.metta"}},
], ids=lambda change: next(iter(change)) + ":" + repr(next(iter(change.values())))[:24])
def test_a_request_refused_before_the_store_creates_nothing(where, change) -> None:
    payload = {"operation": "observe", "domain": where.domain, "motivation": where.motivation,
               "observations": [_observation("nurture", 0.3, 10)], **change}
    if isinstance(payload["motivation"], dict) and payload["motivation"].get("store") == "STORE":
        payload["motivation"] = {**payload["motivation"], "store": str(where.store)}

    with pytest.raises(InvalidInputError):
        run_motivation_request(payload, budget=_budget())

    assert not where.store.exists()


# A status request is refused the same way: no instant, or a naive one.
# am[verifies a-v2m-request-cycle-1019@abb37d]
@pytest.mark.parametrize("as_of", [None, "2026-10-20T09:00:00", "yesterday"])
def test_a_status_without_an_instant_is_refused(where, as_of) -> None:
    with pytest.raises(InvalidInputError):
        run_motivation_request({"operation": "status", "domain": where.domain, "motivation": where.motivation,
                                "as_of": as_of}, budget=_budget())
    assert not where.store.exists()


# The deadline passes while the domain loads: the request raises the budget's own error and opens
# no store, so nothing is created or written.
# am[verifies a-v2m-request-cycle-1019@abb37d] am[verifies c-v2m-request-budget-boundary-1020@3fe8e4]
def test_a_deadline_passing_while_the_domain_loads_opens_no_store(where, monkeypatch) -> None:
    loaded = domain_requests.domain_for

    def load_then_expire(value: object, budget: RunBudget):
        domain = loaded(value, budget)
        later = budget_module.time.monotonic() + 3600
        monkeypatch.setattr(budget_module, "time", SimpleNamespace(monotonic=lambda: later))
        return domain

    monkeypatch.setattr(domain_requests, "domain_for", load_then_expire)
    with pytest.raises(ReviewTimeout):
        _send(where, "observe", [_observation("nurture", 0.3, 10)])
    assert not where.store.exists()


# An inference bound the domain load uses up is the same: the request's error, and no store.
# am[verifies a-v2m-request-cycle-1019@abb37d] am[verifies c-v2m-request-budget-boundary-1020@3fe8e4]
def test_an_inference_bound_the_domain_load_spends_opens_no_store(where) -> None:
    with pytest.raises(InferenceBudgetExceeded):
        _send(where, "observe", [_observation("nurture", 0.3, 10)],
              budget=RunBudget(inference_budget=1, timeout_seconds=300))
    assert not where.store.exists()


# A writer holding the stream's lock past the request's deadline: the request's wait for it ends
# at the deadline with the budget's own error, not after the store's 5 s, and nothing is written.
# The budget's clock is moved once the domain has loaded so that half a second is left, and then
# runs in real time.
# am[verifies a-v2m-request-cycle-1019@abb37d] am[verifies c-v2m-request-budget-boundary-1020@3fe8e4]
# am[verifies a-v2m-st-deadline-1020@64df73]
def test_a_lock_held_past_the_deadline_ends_the_write_at_the_deadline(where, monkeypatch) -> None:
    _send(where, "observe", [_observation("nurture", 0.3, 10)])
    loaded, real, marks = domain_requests.domain_for, time.monotonic, {}

    def load_then_leave_half_a_second(value: object, budget: RunBudget):
        domain = loaded(value, budget)
        offset = budget.remaining()[1] - 0.5
        monkeypatch.setattr(budget_module, "time", SimpleNamespace(monotonic=lambda: real() + offset))
        marks["loaded"] = real()
        return domain

    monkeypatch.setattr(domain_requests, "domain_for", load_then_leave_half_a_second)
    holder = sqlite3.connect(where.store, timeout=0, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(ReviewTimeout):
            _send(where, "observe", [_observation("calm", 0.5, 20)])
        waited = real() - marks["loaded"]
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    monkeypatch.undo()

    assert 0.4 < waited < 3.0
    calm = next(item for item in _send(where, "status")["snapshot"]["levels"] if item["need"] == "calm")
    assert calm["state"] == "unobserved"


# An empty list has nothing to write, so it opens no store and answers two empty lists.
# am[verifies a-v2m-request-cycle-1019@abb37d] am[verifies c-v2m-empty-batch-opens-nothing-1020@b9ed0f]
def test_an_empty_list_opens_no_store(where) -> None:
    answer = _send(where, "attempt", [])
    assert (answer["recorded"], answer["already_recorded"]) == ([], [])
    assert not where.store.exists()


# The same records sent in another order and other batches give the same snapshot; only its history
# reference differs, which commits to the order each stream holds its events in, beside their count.
# am[verifies a-v2m-request-cycle-1019@abb37d] am[verifies c-v2m-endpoint-order-free-1019@6a9e43]
# am[verifies a-v2r-record-digest-1020]
def test_the_snapshot_does_not_depend_on_the_order_or_batching_of_records(where, tmp_path) -> None:
    observations = [_observation("nurture", 0.3, 10), _observation("calm", 0.5, 12),
                    _observation("nurture", 0.5, 30, produced_by="a1"), _observation("calm", 0.45, 30, produced_by="a1")]
    attempts = [_attempt("a1", "empathize", 20), _attempt("a0", "stay_silent", None)]
    other = {"store": str(tmp_path / "other.sqlite3"), "stream": STREAM}

    _send(where, "observe", observations)
    _send(where, "attempt", attempts)
    for observation in reversed(observations):
        _send(where, "observe", [observation], motivation=other)
    _send(where, "attempt", list(reversed(attempts)), motivation=other)

    reordered, recorded = _send(where, "status", motivation=other)["snapshot"], _send(where, "status")["snapshot"]
    assert reordered.pop("history")["event_count"] == recorded.pop("history")["event_count"] == 6
    assert reordered == recorded


# status reads a prefix of the stream by its count of events, 0 being the empty prefix; a count that
# is a boolean, not an integer or negative is refused before the domain is read, and one beyond the
# stream is the store's refusal; only status takes a count.
# am[verifies a-v2r-history-prefix-1020]
def test_status_through_a_count_reads_that_prefix_and_refuses_any_other_count(where, monkeypatch) -> None:
    _one_cycle(where)
    whole = _send(where, "status")["snapshot"]
    assert whole["history"]["event_count"] == 3
    assert _send(where, "status", through=3)["snapshot"] == whole
    first = _send(where, "status", through=1)["snapshot"]
    assert first["history"]["event_count"] == 1 and first["samples"] == []
    assert _send(where, "status", through=0)["snapshot"]["history"]["event_count"] == 0
    with pytest.raises(PersistenceError):
        _send(where, "status", through=4)
    monkeypatch.setattr(motivation_requests, "_domain", lambda *_: pytest.fail("the domain was read"))
    for count in (True, -1, 1.5, "3", None):
        with pytest.raises(InvalidInputError, match="through"):
            _send(where, "status", through=count)
    with pytest.raises(InvalidInputError, match="Invalid fields"):
        _send(where, "observe", [], through=0)

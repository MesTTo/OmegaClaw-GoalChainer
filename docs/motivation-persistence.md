<!-- Purpose: explain what a motivation stream stores, how it records, refuses and replays need observations and attempts, and which database file it owns. -->
<!-- am[implements a-v2m-st-docs-1019@5ae7ff] -->
<!-- am[implements a-v2r-guides-1020@0b367f] -->
# Motivation stream persistence

A motivation stream records what a host observed about a domain's needs and
which actions it attempted. It keeps two kinds of event: a need observation,
the level of one declared need read on that need's scale, and an attempt, one
application of a declared action. GoalChainer reads need levels from the
stream, so the stream is the only place they are kept.

## Recording observations and attempts

```python
from datetime import datetime, timedelta, timezone

from goal_chainer.motivation import Attempt, MotivationStore, NeedObservation

at = datetime(2026, 10, 20, 9, 0, tzinfo=timezone(timedelta(hours=11)))
observation = NeedObservation(
    need="calm", level=0.4, scale=(0.0, 1.0), estimator="measured",
    source="sensor:hrv", observed_at=at, valid_until=at + timedelta(hours=1),
)
with MotivationStore("motivation.sqlite3", stream="incident-host") as store:
    store.observe(domain, observation)                            # True: recorded
    store.observe(domain, observation)                            # False: already recorded
    store.attempt(domain, Attempt("exec-276", "empathize", applied_at=at))
    history = store.history()
print(history.observations, history.attempts, history.digest)
```

Here `domain` is a loaded domain that declares the need `calm` on the scale
`[0, 1]` and the action `empathize`. `observe` and `attempt` return `True` when
they recorded the event and `False` when the same event was already recorded.
`MotivationStore.memory(stream="incident-host")` keeps a stream in memory, which
is discarded when the store closes.

An observation may name the attempt that `produced_by` it. That attempt need not
be recorded yet, since feedback can arrive before the attempt's own record.

## Recording a batch

`record` writes several records together or not at all, as a host's list of
readings should be:

```python
answers = store.record(domain, observations=(first, second), attempts=(attempt,))
# ((first.id, True), (second.id, True), ("exec-276", False))
```

It checks every record against the domain and the vocabulary first, so one
record the domain does not declare refuses the whole batch before anything is
written. It then appends them all in one SQLite write transaction and answers
`(key, appended)` for each observation in order and then each attempt in order.
A record its key already holds, including one earlier in the same batch,
answers `False`; a batch sent again therefore appends nothing. A different
record under a key the stream already holds, or under a key an earlier record of
the batch takes, rolls the whole batch back with a `persistence_error`.
`observe` and `attempt` are the batches of one record.

## Checking records before opening a store

`check_records(domain, observations, attempts)` runs the checks `record` runs
first, with no store involved: it answers the records as tuples, or raises the
`invalid_input` error `record` would raise for the first record the domain or
the vocabulary does not declare. A host that checks its records before it opens a
store therefore creates no store file for a refused request:

```python
from goal_chainer.motivation.store import check_records

observations, attempts = check_records(domain, observations, attempts)
with MotivationStore("motivation.sqlite3", stream="incident-host", budget=budget) as store:
    store.record(domain, observations, attempts, budget=budget)
```

## Recording within a deadline

`MotivationStore`, `record` and `history` take the caller's `RunBudget` as
`budget`, the bound a request runs under. An already initialized stream needs
no metadata write lock. Its ordinary WAL reads can proceed beside a writer;
SQLite recovery or an exclusive database lock can still delay a read. A new
stream takes a write lock to initialize its metadata.

A budgeted open checks the budget before touching the file, so an exhausted
budget creates nothing. SQLite lock waits use the smaller of 5 seconds and the
remaining time, rounded up to the millisecond SQLite accepts. A wait that the
deadline ends raises `review_timeout`. A batch commits only while the budget
holds:

- an exhausted budget, its time or its inferences, raises its own
  `review_timeout` or `inference_budget_exceeded` before any statement runs,
  so nothing is written and no transaction begins
- the store waits for SQLite's write lock no longer than the budget's seconds
  left, and never longer than its own 5 seconds; a wait that the deadline ends
  raises `review_timeout`, and one that ends while the budget holds is a
  `persistence_error`
- the budget is read again after the inserts and before `COMMIT`, so a deadline
  that passes while the batch is written rolls the whole batch back and raises
  `review_timeout`

Once `COMMIT` has returned, `record` answers and raises no exhaustion. The caller
can still lose the answer or report a later timeout; retry the same keys to find
which records committed. Without a budget, SQLite lock waits last up to
5 seconds.

## JSON shapes

`parse_observation` and `parse_attempt` read the shapes a host sends, and the
stream stores each event in the same shape:

```json
{"need": "calm", "level": 0.4, "scale": [0.0, 1.0], "estimator": "measured",
 "source": "sensor:hrv", "observed_at": "2026-10-19T22:00:00+00:00",
 "valid_until": "2026-10-19T23:00:00+00:00", "produced_by": null}

{"attempt": "exec-276", "action": "empathize",
 "applied_at": "2026-10-19T22:00:00+00:00", "review_fingerprint": null}
```

Every time is ISO-8601 with an offset, exact to the microsecond, and is stored in
UTC. `valid_until`, `produced_by` and `review_fingerprint` may be left out or be
null. `applied_at` must be present, and is null when the host did not apply the
action. A field the shape does not list is refused, so a misspelt optional field
is never silently dropped.

## Keys and repeats

An observation's id is the SHA-256 fingerprint of its fields, written
`sha256:...`, and the stream keys the observation by it. Two observations are the
same observation when every field is the same. Times compare as instants, so
`09:00+11:00` and `22:00Z` the day before are one time, and a level of `-0.0` is
the level `0.0`. Recording an observation again changes nothing.

An attempt is keyed by its attempt id. Recording the same attempt again changes
nothing. A different action, time or review fingerprint under a recorded attempt
id is refused with a `persistence_error`, because one attempt id cannot name two
applications. When two processes record the same event at once, the stream
records it once: the key check and the write share one SQLite write transaction.

## What is refused

A record is refused with an `invalid_input` error when it is built, before any
store sees it, if it holds:

- an empty text, or a text holding a lone surrogate that UTF-8 cannot carry
- a level that is a boolean, is not a finite number, or lies outside its scale
- a scale that is not two finite numbers with the low end below the high end
- a time without a timezone, or one before year 1 or after year 9999 in UTC
- a validity that ends before the observation was made

`observe` and `attempt` also refuse with an `invalid_input` error, before any
transaction begins, a need the domain does not declare, a scale other than the
one the domain declares for the need, an estimator class outside the shared
vocabulary, and an action the domain does not declare. A refused event writes
nothing, and the next one is recorded as usual.

## Reading the stream

`history()` reads the events in one SQLite statement. It returns observations
and attempts in their respective recording orders, and a SHA-256 digest
committing to the ordered events it read. Event keys are checked against that
same prefix. Appends cannot change the prefix because an event and its key are
written together and never rewritten.

`history(through=N, budget=budget)` reads only events 1 through `N`. Zero means
the empty prefix. A boolean, a negative number or a value that is not an
integer raises `invalid_input`; a count beyond the stream raises
`persistence_error`. Leaving `through` out reads the latest history. The budget
is checked before the read, while rows are stepped and records are validated,
and after the history and its digest are built. These checks do not preempt an
individual Python operation halfway through it.

Replay checks each event's sequence, schema version, stream and content hash, as
the SNARS store does. It also refuses with a `persistence_error` an event of
another kind, a payload that is not a valid record, a payload not written in its
record's own form, and an event recorded under any key but the one its record
gives. A history therefore never holds two observations, or two attempts, with
one id. Replay does not check the domain or the vocabulary again, so an
observation stays readable after its domain changes; the policy that reads it
decides what it still means.

## Audit an earlier review

A review keeps the need levels, expected changes and reductions used in its
decision. It summarizes evidence with these fields:

| Location | Evidence retained in the review |
| --- | --- |
| Each level | `support_count`, `support_digest` and `support_estimators`. |
| Each expected change | `count` and `samples_digest`. |
| `motivation.history` | `event_count` and `digest` of the history read. |

The support and sample digests commit to their sorted evidence. They
participate in the decision identity; `history` does not. An unrelated append
therefore does not by itself make a review stale. A full `status` snapshot
includes the individual support observations, sample keys, `samples`,
`not_sampled` and `excluded` lists.

To recover those details for an earlier review, send a `status` request using
the same stream, domain and policy revision. Set `as_of` to the review's
`motivation.as_of`, and `through` to its `motivation.history.event_count`.
Compare the returned `snapshot.history.digest` with the review's recorded
digest. For example, a review made from the first three events is audited with
`"through": 3`, even if the stream now holds a thousand events. A later append
with an earlier observation timestamp is still outside that prefix.

The JSON `through` field accepts an integer count, including zero; omit it for
the latest stream. Null, booleans and non-integers are refused. Only `status`
accepts it. Reviews and freshness checks use the latest stream at their
declared `as_of`, so an audit cannot hide later evidence from a new decision.

SHA-256 is a content commitment, not a signature authenticating the host.
Replay also depends on retaining the database and the matching domain and
policy code. A hand-built `MotivationHistory` carries whatever digest its
builder supplied and names no replayable store prefix. A history read from
`MotivationStore.memory()` names a real prefix only while that store survives.
With no stream, a review's history reference is `null`.

## The stream's file

A stream's database belongs to that stream. Its metadata names schema version 1
and the stream, and every event carries both. A store opens only a database that
is new or that its own kind and identity wrote. It refuses with a
`persistence_error`, without writing to the database, a stream recorded under
another stream name, a SNARS store, and any SQLite database holding tables but no
store metadata, such as another application's. A SNARS store refuses a motivation
stream's database the same way. Use one database per stream.

`MotivationStore(path, stream=..., create=False)` opens only a stream already at
the path, for a read such as a status request. It refuses a path holding no
stream with a `persistence_error` saying no motivation store is at the database
path: a missing file, an empty one, and a database whose store metadata was never
written. It creates no database file, writes none of the database's bytes and
takes no metadata write lock. The same database refusals apply as for an open
that may create a store.

<!-- am[implements a-v2rs-opath-open-1020@5f6c09] -->
The database's protections are the SNARS store's: see
[file controls](snars-persistence.md#file-controls). Among them, the store changes
an existing file's mode only once it has found its own store's metadata there, so
a database or any other file it refuses keeps its mode.

## Privacy, retention and deletion

Sources and attempt ids can name people, devices or tickets. Choose a database
path with the same care as an incident log. The event table is append-only:
close the store, then delete the database with its `-wal` and `-shm` files
together to delete a stream.

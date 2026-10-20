"""Purpose: keep GoalChainer's append-only event streams, each in a private SQLite database file the
store makes and checks before SQLite opens it and under a schema naming its format version and
identity: a file another store or another identity wrote is refused when it opens, a keyed event is
appended at most once, events appended together commit together, every append and every read keeps
a caller's deadline when it gives one, a malformed event is refused before its transaction, and
replay checks each event's order, version, identity and hash."""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import sqlite3
import stat
import urllib.parse
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import closing, contextmanager, nullcontext, suppress
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, ClassVar, Self, TypeVar

from .errors import PersistenceError, safe_repr
from .runtime.budget import BudgetExhausted, RunBudget

# How long a store waits for SQLite's write lock before it refuses, SQLite's busy timeout; a caller's
# RunBudget shortens one transaction's wait to the seconds the budget has left.
_LOCK_WAIT_SECONDS = 5.0


# What tells one store's files and messages from another's. The version and the identity are written
# to the file's metadata, under schema_version and identity_key, and into every row, whose identity
# column identity_key names, and every event hash covers both. label, identity_name and identifies
# are the words the store's messages use: SNARS's schema (snars_store.SCHEMA) says "The SNARS
# identity must be nonempty text." and "SNARS event was recorded against a different SNARS library."
# am[implements a-v2m-es-extract-1019@b610bc]
@dataclass(frozen=True)
class StoreSchema:
    label: str
    version: int
    identity_key: str
    identity_name: str
    identifies: str

    # The identity key is written into the store's SQL as a column name, so it must be a plain ASCII
    # identifier, and it shares the metadata table with schema_version.
    def __post_init__(self) -> None:
        key = self.identity_key
        if not (key.isascii() and key.isidentifier()) or key == "schema_version":
            raise ValueError(f"an event store's identity key must be an identifier other than schema_version, not {key!r}")

    @property
    def title(self) -> str:
        """The label as it starts a sentence: SNARS stays SNARS and motivation becomes Motivation."""

        return self.label[:1].upper() + self.label[1:]

    # One event's id: the SHA-256 of the schema version, the identity, the sequence, the kind and the
    # canonical payload, each separated by NUL, so a changed byte in any of them changes the id.
    # am[implements a-rt-snars-store-identity-1017@deb59d] am[implements a-v2m-es-extract-1019@b610bc]
    def event_id(self, sequence: int, kind: str, canonical_payload: str, identity: str) -> str:
        content = f"{self.version}\0{identity}\0{sequence}\0{kind}\0{canonical_payload}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


# One stored event: its row's values in column order.
# am[implements a-v2m-es-extract-1019@b610bc]
@dataclass(frozen=True, slots=True)
class Event:
    sequence: int
    event_id: str
    kind: str
    payload: Mapping[str, Any]
    identity: str
    schema_version: int


_Answer = TypeVar("_Answer")


# A read that gives back its answer only while the caller's budget holds: the budget is read once
# more after the read's last unit of work, whether that is its statement's last step, which may scan
# rows it keeps none of, or the checking, hashing or comparing after it, so no read answers once its
# deadline has passed, an empty key lookup included. A refusal the read raises stays its own, and a
# read given no budget is as it was. _read and events() read the budget before the statement and
# before each unit of work, so a long read also stops near its deadline.
# am[implements a-v2rs-kr-store-1020@a28d14] am[addresses i-v2rs-key-reads-unbudgeted-1020@48553e]
def _within_budget(read: Callable[..., _Answer]) -> Callable[..., _Answer]:
    # am[implements a-v2rs-kr-store-1020@a28d14]
    @wraps(read)
    def answered(store: EventStore, *arguments: Any, budget: RunBudget | None = None, **options: Any) -> _Answer:
        answer = read(store, *arguments, budget=budget, **options)
        if budget is not None:
            budget.remaining()
        return answer

    return answered


class EventStore:
    """A private append-only event stream under one schema, with deterministic read order."""

    # The record each event is read into, built from its row's six values in column order; a store
    # whose callers know its events by another record names that record here.
    event_type: ClassVar[type] = Event

    # The identity and the path are checked before any file is touched, so a refused name makes
    # nothing. Every failure once a connection exists closes it, an OSError or SQLite error
    # becoming PersistenceError and any other exception, an interrupt included, propagating
    # unchanged, so a refused open holds no file or lock. With create=False the store opens only a
    # file that already holds a store of its schema and identity: it creates no database file and
    # writes none of its bytes, and SQLite's -wal and -shm files come and go with its connections as
    # they do for any open. A file the store refuses keeps its bytes and its mode; _private_database
    # says when the store makes the file it opens private.
    # With a caller's budget the open keeps its deadline as append_batch does: the budget is read
    # once the names are checked and before the file is touched, so an exhausted one creates nothing;
    # every lock wait while opening lasts at most min(5 s, its seconds left), a wait the deadline
    # ended raising its exhaustion; and the store's own 5 s wait is put back once the store is open.
    # am[implements a-rt-snars-store-identity-1017@deb59d] am[implements a-integrate-store-boundaries-fix-1019@ebf493]
    # am[implements a-v2m-es-extract-1019@b610bc] am[implements a-v2m-st-read-refuses-1020@676ded]
    # am[implements a-v2m-st-open-budget-1020@874189] am[rests-on c-v2m-st-busy-wait-measured-1020@466e30]
    # am[implements a-v2rs-opath-open-1020@5f6c09] am[addresses i-v2rs-refused-open-chmod-1020@bc323a]
    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        schema: StoreSchema,
        identity: str,
        create: bool = True,
        budget: RunBudget | None = None,
    ) -> None:
        self.schema = schema
        self.identity = _text(identity, f"The {schema.identity_name}")
        self.path = None if path is None else _safe_database_path(path, schema)
        wait = _LOCK_WAIT_SECONDS if budget is None else min(_LOCK_WAIT_SECONDS, budget.remaining()[1])
        opening = nullcontext(_IN_MEMORY) if self.path is None else _private_database(self.path, schema, create)
        connection = None
        try:
            with opening as database:
                connection = sqlite3.connect(database.uri, timeout=wait, isolation_level=None, uri=True)
                database.unmoved()
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute(f"PRAGMA busy_timeout = {_milliseconds(wait)}")
                connection.execute("PRAGMA secure_delete = ON")
                self._connection = connection
                self._initialize(create)
                database.verified()
            if wait != _LOCK_WAIT_SECONDS:
                connection.execute(f"PRAGMA busy_timeout = {_milliseconds(_LOCK_WAIT_SECONDS)}")
        except BaseException as exc:
            if connection is not None:
                connection.close()
            _raise_if_deadline_ended(budget, exc)
            if isinstance(exc, (OSError, sqlite3.Error)):
                raise PersistenceError(
                    f"Unable to open the {schema.label} event store.",
                    details={"path": ":memory:" if self.path is None else str(self.path), "error": str(exc)},
                ) from exc
            raise

    # am[implements a-v2m-es-extract-1019@b610bc]
    @property
    def persistent(self) -> bool:
        return self.path is not None

    # The batch of one: append_batch keeps a single event's statements, refusals and deadline.
    # am[implements a-ev-outcome-evidence@69a360] am[implements a-integrate-store-boundaries-fix-1019@ebf493]
    # am[addresses i-ev-outcome-reinflation@b31afa] am[implements a-v2m-es-extract-1019@b610bc]
    # am[implements a-v2rs-snars-budget-1020@5469ea]
    def append_prepared(
        self,
        kind: str,
        payload: Mapping[str, Any],
        *,
        key: str | None = None,
        budget: RunBudget | None = None,
    ) -> Any | None:
        """Append one event; with a key, append it at most once per (kind, key).

        The key lookup and the insert share one BEGIN IMMEDIATE transaction, so
        two sessions racing on one database cannot both append a keyed event.
        An identical payload under a recorded key returns None and writes
        nothing; a different payload under it raises, since one identity cannot
        carry two pieces of evidence. A malformed event is refused before the
        transaction begins and any failure inside it rolls it back, so a
        refused append writes nothing and the next append proceeds. With a
        budget the event commits only within its deadline, as append_batch's do.
        """

        return self.append_batch([(kind, payload, key)], budget=budget)[0]

    # Events appended together or not at all, in one BEGIN IMMEDIATE transaction, each at most once
    # per (kind, key) as append_prepared appends one. Every event is checked and encoded before the
    # transaction begins. A payload its key already holds, earlier in the same batch included,
    # answers None and writes nothing, and a different payload under a recorded key raises inside
    # the transaction, so the whole batch rolls back; any other failure inside it rolls it back too.
    # With a caller's budget the batch commits only while the budget holds: it is read before any
    # statement runs, the write lock is waited for no longer than the seconds it has left, at most
    # the store's own wait, a wait the deadline ended raises the budget's exhaustion where any other
    # failed wait is a PersistenceError, and it is read again after the inserts, before COMMIT, so
    # an exhausted budget rolls the batch back; once COMMIT returns, nothing raises exhaustion.
    # Time: per event one key lookup, one MAX(sequence) read on the primary key and up to two
    # inserts, n events, under one write lock waited for at most min(5 s, the budget's seconds left).
    # am[implements a-v2m-st-batch-1019@a8d5f5] am[implements a-ev-outcome-evidence@69a360]
    # am[implements a-integrate-store-boundaries-fix-1019@ebf493] am[implements a-v2m-es-extract-1019@b610bc]
    # am[implements a-v2m-st-deadline-1020@64df73] am[rests-on c-v2m-st-busy-wait-measured-1020@466e30]
    def append_batch(
        self,
        events: Iterable[tuple[str, Mapping[str, Any], str | None]],
        *,
        budget: RunBudget | None = None,
    ) -> tuple[Any | None, ...]:
        """Append (kind, payload, key) events as one transaction, answering each appended event, or
        None for a payload its key already held, in order; with a budget, within its deadline."""

        prepared = [(kind, key, _prepared(kind, payload, key)) for kind, payload, key in events]
        wait = None
        if budget is not None:
            _, seconds = budget.remaining()
            wait = min(_LOCK_WAIT_SECONDS, seconds)
        if not prepared:
            return ()
        appended: list[tuple[int, str, str, str] | None] = []
        kind = prepared[0][0]
        try:
            with _lock_wait(self._connection, wait), _immediate(self._connection):
                for kind, key, canonical in prepared:
                    recorded = None
                    if key is not None:
                        recorded = self._connection.execute(_RECORDED_UNDER_KEY, (kind, key)).fetchone()
                    if recorded is not None:
                        _same_as_recorded(recorded, canonical, kind, key)
                        appended.append(None)
                        continue
                    row = self._connection.execute(
                        "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM events"
                    ).fetchone()
                    sequence = int(row["next_sequence"])
                    event_id = self.schema.event_id(sequence, kind, canonical, self.identity)
                    self._connection.execute(
                        f"""
                        INSERT INTO events (
                            sequence, event_id, kind, payload_json,
                            {self.schema.identity_key}, schema_version
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (sequence, event_id, kind, canonical, self.identity, self.schema.version),
                    )
                    if key is not None:
                        self._connection.execute(
                            "INSERT INTO event_keys (kind, key, sequence) VALUES (?, ?, ?)",
                            (kind, key, sequence),
                        )
                    appended.append((sequence, event_id, kind, canonical))
                if budget is not None:
                    budget.remaining()
        except sqlite3.Error as exc:
            _raise_if_deadline_ended(budget, exc)
            raise PersistenceError(
                f"Unable to append the {self.schema.label} event.",
                details={"kind": kind, "error": str(exc)},
            ) from exc
        return tuple(
            None if event is None
            else self.event_type(event[0], event[1], event[2], json.loads(event[3]), self.identity, self.schema.version)
            for event in appended
        )

    # A keyed event checked against what its key holds, by the rule append_prepared applies, without
    # a transaction or a write: False when nothing is recorded under the key, True when this payload
    # is, and append_prepared's refusal when a different one is. A caller learns before costly work
    # whether its append would repeat or conflict; a key is never removed, so a recorded answer
    # stays true, while an unrecorded one is settled atomically by the append itself. A caller's
    # budget bounds the lookup and its comparison as _read and _within_budget say.
    # am[implements a-v2-outcome-sequential-conflict-1020@10212e] am[implements a-v2m-es-extract-1019@b610bc]
    # am[implements a-v2rs-kr-store-1020@a28d14] am[addresses i-v2rs-key-reads-unbudgeted-1020@48553e]
    @_within_budget
    def recorded(self, kind: str, payload: Mapping[str, Any], *, key: str,
                 budget: RunBudget | None = None) -> bool:
        """Whether this payload is recorded under the key, refusing a different one recorded there."""

        canonical = _prepared(kind, payload, key)
        rows = self._read(_RECORDED_UNDER_KEY, (kind, key), budget=budget, what="event keys")
        if not rows:
            return False
        _same_as_recorded(rows[0], canonical, kind, key)
        return True

    # A caller's budget bounds the read as _read and _within_budget say.
    # am[implements a-ev-outcome-evidence@69a360] am[implements a-integrate-store-boundaries-fix-1019@ebf493]
    # am[implements a-v2m-es-extract-1019@b610bc] am[implements a-v2rs-kr-store-1020@a28d14]
    # am[addresses i-v2rs-key-reads-unbudgeted-1020@48553e]
    @_within_budget
    def has_key(self, kind: str, key: str, *, budget: RunBudget | None = None) -> bool:
        """Whether an event of this kind is recorded under this key."""

        _text(kind, "Event kind")
        _text(key, "Event key")
        rows = self._read("SELECT 1 FROM event_keys WHERE kind = ? AND key = ?", (kind, key),
                          budget=budget, what="event keys")
        return bool(rows)

    # Every key row is written in the transaction that appends its event and none is ever removed, so
    # a read after events() holds the key of every event that read returned; `through` keeps the keys
    # of events 1 to N, as events() reads them, and a caller's budget bounds the read as _read and
    # _within_budget say.
    # Time: one scan of the key table, k keyed events, and one budget read each.
    # am[implements a-v2m-es-extract-1019@b610bc] am[related a-v2m-st-store-1019@670a6d]
    # am[implements a-v2rs-events-budget-1020@a8933d] am[implements a-v2rs-kr-store-1020@a28d14]
    @_within_budget
    def event_keys(self, *, through: int | None = None,
                   budget: RunBudget | None = None) -> dict[int, tuple[str, str]]:
        """The kind and key each keyed event is recorded under, by the event's sequence."""

        rows = self._read("SELECT sequence, kind, key FROM event_keys WHERE sequence <= ?",
                          (_bound(through),), budget=budget, what="event keys")
        return {int(row["sequence"]): (str(row["kind"]), str(row["key"])) for row in rows}

    # A stored event's JSON is the caller's file once its hash is recomputed, so json.loads's
    # ValueError for an integer past the interpreter's digit limit and its RecursionError for nesting
    # past its parser are the store's corrupt event, as a JSONDecodeError is
    # (c-rt-rr-store-json-digits-1018). `through` reads events 1 to N alone, by the primary key, so an
    # audit of an old prefix costs that prefix. With a caller's budget the read keeps its deadline:
    # _read bounds the statement, and the budget is read again before each event is verified and once
    # after the last, as _within_budget reads it for every read, so a long stream raises the budget's
    # own exhaustion within one event's work of the deadline, about 0.1 µs a read against about 19 µs
    # an event (c-v2rs-budget-check-cost-1020), and an overrun in the last event's work cannot answer
    # success; without one the read is as it was.
    # Time: one read of the n events read, one hash, one JSON parse and two budget reads each.
    # am[implements a-rt-snars-store-identity-1017@deb59d] am[implements a-rt-rr-json-read-1018@305497]
    # am[rests-on c-rt-rr-store-json-digits-1018@e19f9b] am[implements a-v2m-es-extract-1019@b610bc]
    # am[implements a-v2rs-events-budget-1020@a8933d] am[addresses i-v2rs-history-unbudgeted-1020@5dcb6e]
    # am[rests-on c-v2rs-budget-check-cost-1020@89fd57] am[implements a-v2rs-kr-store-1020@a28d14]
    @_within_budget
    def events(self, *, through: int | None = None, budget: RunBudget | None = None) -> tuple[Any, ...]:
        rows = self._read(
            f"""
            SELECT sequence, event_id, kind, payload_json,
                   {self.schema.identity_key} AS identity, schema_version
            FROM events
            WHERE sequence <= ?
            ORDER BY sequence ASC
            """,
            (_bound(through),),
            budget=budget,
            what="events",
        )
        events: list[Any] = []
        for expected_sequence, row in enumerate(rows, start=1):
            if budget is not None:
                budget.remaining()
            events.append(self._checked(row, expected_sequence))
        return tuple(events)

    # One read statement's rows, bound to `parameters`, under a caller's budget: the budget is read
    # before the statement and again as each row is stepped, before the row is kept, and any wait for
    # a lock while stepping lasts no longer than min(5 s, the seconds left). A WAL reader waits only
    # while the database is recovered or another connection holds it exclusively, and a
    # rollback-journal one while a writer commits. A wait the deadline ended raises the budget's own
    # exhaustion, any other SQLite failure the store's PersistenceError naming what was read, as
    # append_batch types its failures. Every read the store answers goes through here, and reads the
    # budget once more before it answers, as _within_budget says.
    # Time: one statement stepped over r rows, and one budget read each.
    # am[implements a-v2rs-events-budget-1020@a8933d] am[rests-on c-v2m-st-busy-wait-measured-1020@466e30]
    # am[implements a-v2rs-kr-store-1020@a28d14]
    def _read(self, sql: str, parameters: tuple[object, ...], *, budget: RunBudget | None,
              what: str) -> list[sqlite3.Row]:
        wait = None if budget is None else min(_LOCK_WAIT_SECONDS, budget.remaining()[1])
        rows: list[sqlite3.Row] = []
        try:
            with _lock_wait(self._connection, wait), closing(self._connection.execute(sql, parameters)) as cursor:
                for row in cursor:
                    if budget is not None:
                        budget.remaining()
                    rows.append(row)
        except sqlite3.Error as exc:
            _raise_if_deadline_ended(budget, exc)
            raise PersistenceError(
                f"Unable to read {self.schema.label} {what}.",
                details={"error": str(exc)},
            ) from exc
        return rows

    # One stored row checked as the event at `expected_sequence`: its sequence, version, identity,
    # hash and JSON, any fault the store's corrupt event.
    # am[implements a-v2m-es-extract-1019@b610bc] am[implements a-v2rs-events-budget-1020@a8933d]
    def _checked(self, row: sqlite3.Row, expected_sequence: int) -> Any:
        title = self.schema.title
        sequence = int(row["sequence"])
        if sequence != expected_sequence:
            raise PersistenceError(
                f"{title} event sequence is corrupt.",
                details={"expected": expected_sequence, "received": sequence},
            )
        schema_version = int(row["schema_version"])
        if schema_version != self.schema.version:
            raise PersistenceError(
                f"{title} event schema version is unsupported.",
                details={
                    "expected": self.schema.version,
                    "received": schema_version,
                    "sequence": sequence,
                },
            )
        identity = str(row["identity"])
        if identity != self.identity:
            raise PersistenceError(
                f"{title} event was recorded against a different {self.schema.identifies}.",
                details={
                    "expected": self.identity,
                    "received": identity,
                    "sequence": sequence,
                },
            )
        canonical = str(row["payload_json"])
        expected_id = self.schema.event_id(sequence, str(row["kind"]), canonical, identity)
        if expected_id != row["event_id"]:
            raise PersistenceError(
                f"{title} event content hash is invalid.",
                details={"sequence": sequence},
            )
        try:
            payload = json.loads(canonical)
        except (ValueError, RecursionError) as exc:
            raise PersistenceError(
                f"{title} event JSON is corrupt.",
                details={"sequence": sequence, "error": str(exc)},
            ) from exc
        if not isinstance(payload, dict):
            raise PersistenceError(
                f"{title} event payload must decode to an object.",
                details={"sequence": sequence},
            )
        return self.event_type(sequence, str(row["event_id"]), str(row["kind"]), payload, identity, schema_version)

    # The digest of every event, read and verified as events() reads them; with a caller's budget the
    # hashing is the read's last step, after which _within_budget reads the budget once more.
    # am[implements a-v2m-es-extract-1019@b610bc] am[implements a-v2rs-kr-store-1020@a28d14]
    # am[addresses i-v2rs-key-reads-unbudgeted-1020@48553e]
    @_within_budget
    def state_digest(self, *, budget: RunBudget | None = None) -> str:
        return digest(self.events(budget=budget))

    # am[implements a-v2m-es-extract-1019@b610bc]
    def close(self) -> None:
        try:
            self._connection.close()
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Unable to close the {self.schema.label} event store.",
                details={"error": str(exc)},
            ) from exc

    # am[implements a-v2m-es-extract-1019@b610bc]
    def __enter__(self) -> Self:
        return self

    # am[implements a-v2m-es-extract-1019@b610bc]
    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    # The file is read and judged before the store writes a byte to it, the WAL switch included, so
    # a refused file is left as it was: a file holding tables but no store metadata is another
    # application's, and metadata that is not this store's is refused by _refuse_foreign_metadata.
    # A new file is written in the order it always was, WAL first. The metadata is checked again
    # under the write lock that fills it, since another store may have opened the file meanwhile;
    # a process writing the file between the first read and the WAL switch is no more guarded
    # against than one replacing the file, as docs/snars-persistence.md's file controls say.
    # An open that may not create stops after the read, taking no write lock: a file holding no
    # store metadata, or a store missing its event tables, is no store, and nothing is written.
    # Metadata never changes once written, so only an open that found it empty takes the write lock
    # to fill it: an open of an initialized store takes no write lock, so on a WAL database it reads
    # beside a writer (c-v2m-st-open-repro-1020). A read SQLite does make wait, during recovery,
    # behind a connection holding the database exclusively or behind a writer on a rollback journal,
    # waits no longer than the open's own lock wait (c-v2rs-kr-repro-1020).
    # am[implements a-ev-outcome-evidence@69a360] am[implements a-rt-snars-store-identity-1017@deb59d]
    # am[implements a-integrate-store-boundaries-fix-1019@ebf493] am[implements a-v2m-es-extract-1019@b610bc]
    # am[implements a-v2m-es-keyset-1019@b2f86c] am[implements a-v2m-es-check-before-write-1019@4edc67]
    # am[addresses i-v2m-es-refused-open-writes-1019@697b7d] am[implements a-v2m-st-read-refuses-1020@676ded]
    # am[implements a-v2m-st-open-nolock-1020@e6eca3] am[addresses i-v2m-st-open-waits-past-deadline-1020@3fadd8]
    # am[rests-on c-v2m-st-open-repro-1020@9485d2] am[rests-on c-v2rs-kr-repro-1020@6150df]
    def _initialize(self, create: bool) -> None:
        values = {
            "schema_version": str(self.schema.version),
            self.schema.identity_key: self.identity,
        }
        tables = {
            str(row["name"])
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite!_%' ESCAPE '!'"
            ).fetchall()
        }
        recorded = self._metadata() if "metadata" in tables else {}
        if not recorded and not tables <= {"metadata"}:
            raise PersistenceError(
                f"{self.schema.title} database holds tables but no store metadata.",
                details={"tables": sorted(tables)},
            )
        _refuse_foreign_metadata(self.schema, values, recorded)
        if not create:
            if not recorded or not {"events", "event_keys"} <= tables:
                raise _no_store(self.schema, self.path)
            return
        if self.path is not None:
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        if not recorded:
            with _immediate(self._connection):
                recorded = self._metadata()
                _refuse_foreign_metadata(self.schema, values, recorded)
                if not recorded:
                    self._connection.executemany(
                        "INSERT INTO metadata (key, value) VALUES (?, ?)",
                        values.items(),
                    )
        # event_keys is additive: a store written before it opens unchanged, and
        # its events keep their schema version.
        self._connection.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                {self.schema.identity_key} TEXT NOT NULL,
                schema_version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS event_keys (
                kind TEXT NOT NULL,
                key TEXT NOT NULL,
                sequence INTEGER NOT NULL UNIQUE REFERENCES events(sequence),
                PRIMARY KEY (kind, key)
            );
            """
        )

    # am[implements a-v2m-es-keyset-1019@b2f86c]
    def _metadata(self) -> dict[str, str]:
        return {
            str(row["key"]): str(row["value"])
            for row in self._connection.execute("SELECT key, value FROM metadata").fetchall()
        }


# Metadata this store did not write is refused, its values first, so a store an older version wrote
# is refused by the version it records rather than by a column it lacks; then its keys must be
# exactly this schema's, since two formats can share a version number: a SNARS version-1 store
# records schema_version 1 beside mettabase_commit where a version-1 motivation stream records it
# beside stream (c-v2m-es-version-collision-1019). Empty metadata is a store not yet given its own.
# am[implements a-v2m-es-keyset-1019@b2f86c] am[rests-on c-v2m-es-version-collision-1019@39a7e3]
# am[implements a-rt-snars-store-identity-1017@deb59d]
def _refuse_foreign_metadata(schema: StoreSchema, values: Mapping[str, str], recorded: Mapping[str, str]) -> None:
    for key, value in values.items():
        if key in recorded and recorded[key] != value:
            raise PersistenceError(
                f"{schema.title} store metadata does not match this runtime.",
                details={
                    "key": key,
                    "expected": value,
                    "received": recorded[key],
                },
            )
    if recorded and recorded.keys() != values.keys():
        raise PersistenceError(
            f"{schema.title} store metadata does not hold exactly this store's keys.",
            details={"expected": sorted(values), "received": sorted(recorded)},
        )


# The refusal of an open that may not create, where the path holds no store of this schema.
# am[implements a-v2m-st-read-refuses-1020@676ded]
def _no_store(schema: StoreSchema, path: Path | None) -> PersistenceError:
    return PersistenceError(
        f"No {schema.label} store is at the database path.",
        details={"path": ":memory:" if path is None else str(path)},
    )


# A whole number of milliseconds no shorter than `seconds`, as SQLite's busy timeout takes them.
# am[implements a-v2m-st-deadline-1020@64df73]
def _milliseconds(seconds: float) -> int:
    return math.ceil(seconds * 1000)


# SQLite's largest INTEGER, the last sequence a read of every event takes.
_EVERY_SEQUENCE = 2**63 - 1


# The last sequence a read takes: a nonnegative integer, a larger one reading every event as SQLite
# can bind no integer past its own, or None for every event; anything else, a bool included, is
# refused before the read as a store refuses its own arguments.
# am[implements a-v2rs-events-budget-1020@a8933d]
def _bound(through: object) -> int:
    if through is None:
        return _EVERY_SEQUENCE
    if isinstance(through, bool) or not isinstance(through, int) or through < 0:
        raise PersistenceError(
            "A read's last event sequence must be a nonnegative integer or None.",
            details={"through": safe_repr(through)},
        )
    return min(through, _EVERY_SEQUENCE)


# A failed wait for SQLite's lock, SQLITE_BUSY, is the deadline's when the caller's budget has run
# out by then: its own exhaustion is raised, from the SQLite error. Any other failure, and a wait
# that ended while the budget still holds, is left to the caller's PersistenceError.
# am[implements a-v2m-st-deadline-1020@64df73] am[implements a-v2m-st-open-budget-1020@874189]
# am[rests-on c-v2m-st-busy-wait-measured-1020@466e30]
def _raise_if_deadline_ended(budget: RunBudget | None, error: BaseException) -> None:
    if budget is not None and getattr(error, "sqlite_errorcode", 0) & 0xFF == sqlite3.SQLITE_BUSY:
        try:
            budget.remaining()
        except BudgetExhausted as exhausted:
            raise exhausted from error


# One transaction's wait for the write lock, no longer than `seconds`: SQLite's busy timeout is set
# before it begins and put back to the store's own after it ends. Rounded up to whole milliseconds,
# a wait that runs out has lasted the seconds read from a deadline, so the deadline has passed
# (c-v2m-st-busy-wait-measured-1020). None leaves the store's own wait.
# am[implements a-v2m-st-deadline-1020@64df73] am[rests-on c-v2m-st-busy-wait-measured-1020@466e30]
@contextmanager
def _lock_wait(connection: sqlite3.Connection, seconds: float | None) -> Iterator[None]:
    if seconds is None:
        yield
        return
    connection.execute(f"PRAGMA busy_timeout = {_milliseconds(seconds)}")
    try:
        yield
    finally:
        connection.execute(f"PRAGMA busy_timeout = {_milliseconds(_LOCK_WAIT_SECONDS)}")


# The digest of a stream's state: the SHA-256 of each event's sequence and id, one line each, so two
# reads digest alike exactly when they hold the same events in the same order.
# Time: one hash update per event.
# am[implements a-v2m-es-extract-1019@b610bc]
def digest(events: Iterable[Any]) -> str:
    state = hashlib.sha256()
    for event in events:
        state.update(f"{event.sequence}:{event.event_id}\n".encode())
    return state.hexdigest()


# The event a key holds, with the payload its comparison reads.
# am[implements a-v2m-es-extract-1019@b610bc]
_RECORDED_UNDER_KEY = """
    SELECT events.sequence AS sequence, events.payload_json AS payload_json
    FROM event_keys JOIN events ON events.sequence = event_keys.sequence
    WHERE event_keys.kind = ? AND event_keys.key = ?
"""


# An event's kind, payload and key checked, and its payload's canonical text, in the order every
# keyed write and check refuses them, all before any transaction begins.
# am[implements a-integrate-store-boundaries-fix-1019@ebf493] am[implements a-v2m-es-extract-1019@b610bc]
def _prepared(kind: str, payload: Mapping[str, Any], key: str | None) -> str:
    _text(kind, "Event kind")
    if not isinstance(payload, Mapping):
        raise PersistenceError("Event payload must be a mapping.")
    if key is not None:
        _text(key, "Event key")
    try:
        return _canonical_json(payload)
    except (TypeError, ValueError, RecursionError) as exc:
        raise PersistenceError(
            "Prepared event JSON encoding failed.",
            details={"kind": kind, "error": str(exc)},
        ) from exc


# The one rule for a key already taken: the event it holds must be this payload, byte for byte in
# canonical JSON, since one identity cannot carry two pieces of evidence.
# am[implements a-ev-outcome-evidence@69a360] am[implements a-v2-outcome-sequential-conflict-1020@10212e]
# am[implements a-v2m-es-extract-1019@b610bc]
def _same_as_recorded(recorded: sqlite3.Row, canonical: str, kind: str, key: str) -> None:
    if recorded["payload_json"] != canonical:
        raise PersistenceError(
            "A different event is already recorded under this key.",
            details={
                "kind": kind,
                "key": key,
                "sequence": int(recorded["sequence"]),
            },
        )


# The database is named by a path with no symbolic link in it, as SQLITE_OPEN_NOFOLLOW requires of
# a database name: a linked directory would carry the store into whatever directory the link
# reaches, onto a store already there (c-linked-dir-redirects-store-1019). Each directory is checked
# by lstat from the root down, twice: as the written path names it, as far as that path exists, so a
# link before a .. is refused, and as the normalized path the store opens names it, where every one
# must exist, so no link hides behind the .. of a missing directory; the final name is checked as the
# store opens it. A name the operating system cannot take, holding NUL or a surrogate os.fsencode
# cannot encode, is refused here rather than raising ValueError at the first system call, and a path
# these checks cannot read, under a home directory expanduser cannot find or a directory the process
# may not search, is refused with the reason the operating system gave, the same on every Python the
# package supports, where Path.is_symlink raised PermissionError before 3.14 and answers False from it.
# A directory every user can write without the sticky bit lets any of them replace the store's files.
# Time: at most two lstats per directory above the database.
# am[implements a-integrate-store-boundaries-fix-1019@ebf493] am[rests-on c-linked-dir-redirects-store-1019@458a31]
# am[related c-sqlite-resolves-every-link-1019@c02e10] am[implements a-v2m-es-extract-1019@b610bc]
# am[implements a-v2rs-typed-path-checks-1020@15ef87] am[addresses i-v2rs-path-check-untyped-1020@7a17eb]
# am[addresses i-v2rs-link-behind-missing-dir-1020@386010]
def _safe_database_path(path: str | os.PathLike[str], schema: StoreSchema) -> Path:
    try:
        absolute = Path(path).expanduser().absolute()
        nameable = b"\0" not in os.fsencode(absolute)
    except ValueError:
        absolute, nameable = Path(path), False
    except (OSError, RuntimeError) as exc:
        raise _unreadable(schema, Path(path), exc) from exc
    if not nameable:
        raise PersistenceError(
            f"{schema.title} database path cannot name a file.",
            details={"path": str(absolute)},
        )
    for directory in reversed(absolute.parents):
        if _directory_mode(directory, absolute, schema) is None:
            break
    # With no link above it, the path's .. components mean what they say lexically.
    database = Path(os.path.normpath(absolute))
    parent = database.parent
    for directory in (*reversed(parent.parents), parent):
        mode = _directory_mode(directory, absolute, schema)
        if mode is None or not stat.S_ISDIR(mode):
            raise PersistenceError(
                f"{schema.title} database parent directory does not exist.",
                details={"path": str(parent)},
            )
    world_writable = bool(mode & stat.S_IWOTH)
    sticky = bool(mode & stat.S_ISVTX)
    if world_writable and not sticky:
        raise PersistenceError(
            f"{schema.title} database parent directory is world-writable without a sticky bit.",
            details={"path": str(parent)},
        )
    return database


# A directory's mode as lstat reads it, None for a name that does not exist, a link refused as a link
# in `path`, and any other failure the operating system reports refused as a path these checks
# cannot read.
# am[implements a-v2rs-typed-path-checks-1020@15ef87]
def _directory_mode(directory: Path, path: Path, schema: StoreSchema) -> int | None:
    try:
        mode = os.lstat(directory).st_mode
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        raise _unreadable(schema, path, exc) from exc
    if stat.S_ISLNK(mode):
        raise PersistenceError(
            f"{schema.title} database path must not pass through a symbolic link.",
            details={"path": str(path), "link": str(directory)},
        )
    return mode


# The refusal of a database path the store's checks cannot read, naming why.
# am[implements a-v2rs-typed-path-checks-1020@15ef87]
def _unreadable(schema: StoreSchema, path: Path, error: BaseException) -> PersistenceError:
    return PersistenceError(
        f"{schema.title} database path cannot be checked.",
        details={"path": str(path), "error": str(error)},
    )


# Read and write access to a file, as 0600 gives its owner.
_PRIVATE = stat.S_IRUSR | stat.S_IWUSR


# The store makes or opens its database itself and SQLite then opens it by name, through a mode=rw
# URI, which never creates a file (c-sqlite-uri-rw-never-creates-1019). The store makes a missing
# file with mknod, which creates a regular file at 0600 without opening it and refuses any name
# already taken, a link included, and holds the file it opens by an O_PATH O_NOFOLLOW descriptor,
# which names a link at the name rather than what it reaches, so a link there, dangling or not, is
# refused, and so is a FIFO or a device, before anything is changed. The descriptor reads no byte and
# holds no lock, so closing it drops no POSIX lock of this process, where closing a descriptor opened
# to read or write the file drops every one, the SHARED lock a WAL connection keeps included
# (c-close-releases-sqlite-locks-1019): a store opened on a file another store of this process held
# open left that store unlocked, and on SQLite before 3.51 another process could then checkpoint and
# unlink its WAL and lose committed events (c-v2rs-lost-commit-sqlite346-1020). Only SQLite can defer
# closing a descriptor of its own while its connections hold locks (os_unix.c's pUnused list).
# The descriptor stays open while SQLite opens the name and reads the file, so its inode is not
# reused and unmoved() shows whether the name still holds the file checked, before SQLite's first
# statement. SQLite opens read-only a database the process may not write, so a file the process may
# not read and write is refused, as the read-write open the store made before refused it.
# A missing or empty file, whose first bytes a creating open writes, is made 0600 before SQLite opens
# it, so the WAL and shared-memory files SQLite gives its mode are 0600 too
# (c-sqlite-side-files-take-db-mode-1019), as CPython's mkstemp and dbm.sqlite3 make their files
# first (c-cpython-private-create-1019). Any other file is changed only once _initialize has read it
# and found this store's metadata, and a file the store refuses keeps its mode
# (c-v2rs-mode-contract-1020). Every open that finds its store sets the database to 0600 and its WAL
# and shared-memory files too, whatever made them, before any event is written: SQLite's read of a
# database found at another mode makes them at that mode, and a live connection keeps the side files
# an earlier version made at 0644 long after the database itself was made private.
# The mode is set through /proc/self/fd, which reaches the held file and no link at its name.
# A directory others can write can still swap the name and swap it back between these checks.
# am[implements a-integrate-store-boundaries-fix-1019@ebf493] am[rests-on c-sqlite-side-files-take-db-mode-1019@0579b9]
# am[rests-on c-sqlite-uri-rw-never-creates-1019@d86508] am[rests-on c-close-releases-sqlite-locks-1019@2b868b]
# am[related c-cpython-private-create-1019@4764c5] am[implements a-v2m-es-extract-1019@b610bc]
# am[implements a-v2rs-opath-open-1020@5f6c09] am[rests-on c-v2rs-opath-keeps-locks-1020@517b86]
# am[addresses i-v2rs-raw-close-drops-locks-1020@b99034] am[addresses i-v2rs-refused-open-chmod-1020@bc323a]
# am[related c-v2rs-sqlite-351-defence-1020@84ddc5]
@contextmanager
def _private_database(path: Path, schema: StoreSchema, create: bool) -> Iterator[_DatabaseFile]:
    if create:
        _make(path)
    try:
        descriptor = os.open(path, os.O_PATH | os.O_NOFOLLOW)
    except FileNotFoundError as exc:
        raise (_moved(schema, path) if create else _no_store(schema, path)) from exc
    try:
        checked = os.fstat(descriptor)
        if stat.S_ISLNK(checked.st_mode):
            raise PersistenceError(
                f"{schema.title} database path must not be a symbolic link.",
                details={"path": str(path)},
            )
        if not stat.S_ISREG(checked.st_mode):
            raise PersistenceError(
                f"{schema.title} database path is not a regular file.",
                details={"path": str(path)},
            )
        fresh = create and checked.st_size == 0
        if fresh:
            _make_private(descriptor, checked.st_mode)
        if not os.access(_held(descriptor), os.R_OK | os.W_OK, effective_ids=True):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(path))
        yield _DatabaseFile(path, schema, descriptor, checked, fresh)
    finally:
        os.close(descriptor)


# A store's database file while it opens, held by the O_PATH descriptor _private_database took:
# `checked` is what that descriptor's fstat found, and `fresh` whether the file was made private
# before SQLite opened it.
# am[implements a-v2rs-opath-open-1020@5f6c09]
@dataclass(frozen=True, slots=True)
class _DatabaseFile:
    path: Path
    schema: StoreSchema
    descriptor: int
    checked: os.stat_result
    fresh: bool

    @property
    def uri(self) -> str:
        return f"file://{urllib.parse.quote(os.fsencode(self.path))}?mode=rw"

    # Whether the name SQLite opened still holds the file checked, refused when it does not.
    def unmoved(self) -> None:
        if not os.path.samestat(self.checked, os.stat(self.path, follow_symlinks=False)):
            raise _moved(self.schema, self.path)

    # The file _initialize found to be this store, and its WAL and shared-memory files, set to 0600.
    # Time: two O_PATH opens and at most three chmods, none when all three are already private.
    def verified(self) -> None:
        if not self.fresh:
            _make_private(self.descriptor, self.checked.st_mode)
        for suffix in ("-wal", "-shm"):
            _make_side_private(Path(f"{self.path}{suffix}"))


# The in-memory database as the store opens it: nothing on disk to check or make private.
# am[implements a-v2rs-opath-open-1020@5f6c09]
class _InMemory:
    uri = ":memory:"

    def unmoved(self) -> None:
        pass

    def verified(self) -> None:
        pass


_IN_MEMORY = _InMemory()


# A missing database file made as a regular file at 0600, less the process's umask, that nothing
# holds open; a name already taken, a link included, is left for the open to check.
# am[implements a-v2rs-opath-open-1020@5f6c09]
def _make(path: Path) -> None:
    with suppress(FileExistsError):
        os.mknod(path, stat.S_IFREG | _PRIVATE)


# The name of the file an O_PATH descriptor holds, which chmod and access reach without following
# any link at the file's own name.
# am[implements a-v2rs-opath-open-1020@5f6c09]
def _held(descriptor: int) -> str:
    return f"/proc/self/fd/{descriptor}"


# am[implements a-v2rs-opath-open-1020@5f6c09]
def _make_private(descriptor: int, mode: int) -> None:
    if stat.S_IMODE(mode) != _PRIVATE:
        os.chmod(_held(descriptor), _PRIVATE)


# A WAL or shared-memory file beside a verified store set to 0600 when it is a regular file; one that
# is missing or anything else is left alone, as SQLite opens it.
# am[implements a-v2rs-opath-open-1020@5f6c09]
def _make_side_private(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_PATH | os.O_NOFOLLOW)
    except FileNotFoundError:
        return
    try:
        side = os.fstat(descriptor)
        if stat.S_ISREG(side.st_mode):
            _make_private(descriptor, side.st_mode)
    finally:
        os.close(descriptor)


# The refusal of an open whose name stopped holding the file it checked.
# am[implements a-integrate-store-boundaries-fix-1019@ebf493]
def _moved(schema: StoreSchema, path: Path) -> PersistenceError:
    return PersistenceError(
        f"{schema.title} database path changed while the store opened it.",
        details={"path": str(path)},
    )


# Text the store keeps reaches SQLite and the event hash as UTF-8, so a str holding a lone
# surrogate, which Python allows and UTF-8 cannot carry, is refused before any transaction begins
# (c-json-passes-lone-surrogates-1019). A store refuses its own arguments with PersistenceError; a
# record whose fields a store will keep refuses them as input, with the error its caller names.
# am[implements a-integrate-store-boundaries-fix-1019@ebf493] am[rests-on c-json-passes-lone-surrogates-1019@3cee42]
# am[implements a-v2m-es-extract-1019@b610bc]
def _text(value: object, name: str, error: type[Exception] = PersistenceError) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error(f"{name} must be nonempty text.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise error(
            f"{name} must be UTF-8 text.",
            details={"error": str(exc)},
        ) from exc
    return value


# One write transaction: BEGIN IMMEDIATE takes the write lock before the reads it guards, and the
# transaction commits when its block completes or rolls back on any exception, which then
# propagates unchanged, an interrupt included, as sqlite3.Connection.__exit__ rolls back.
# BEGIN runs inside the try, since CPython can deliver an interrupt as BEGIN's execute call
# returns, with the transaction already begun; a ROLLBACK when none began fails and is ignored.
# am[implements a-integrate-store-boundaries-fix-1019@ebf493]
@contextmanager
def _immediate(connection: sqlite3.Connection) -> Iterator[None]:
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield
        connection.execute("COMMIT")
    except BaseException:
        _rollback_quietly(connection)
        raise


# json.dumps passes a lone surrogate through as text no UTF-8 can carry, so the canonical text is
# encoded once here and such a payload raises UnicodeEncodeError, a ValueError, before it is kept.
# The bytes are otherwise the accepted canonical form (c-store-golden-rows-1019).
# am[implements a-integrate-store-boundaries-fix-1019@ebf493] am[rests-on c-json-passes-lone-surrogates-1019@3cee42]
# am[related c-store-golden-rows-1019@010412]
def _canonical_json(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    canonical.encode("utf-8")
    return canonical


# am[implements a-integrate-store-boundaries-fix-1019@ebf493] am[implements a-v2m-es-extract-1019@b610bc]
def _rollback_quietly(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("ROLLBACK")
    except sqlite3.Error:
        pass


__all__ = [
    "Event",
    "EventStore",
    "StoreSchema",
    "digest",
]

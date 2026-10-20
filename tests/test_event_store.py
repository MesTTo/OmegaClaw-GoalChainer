"""Purpose: test the event store machinery every GoalChainer stream shares, under a schema other than
SNARS's: each store's identity column, metadata and messages follow its schema; a file another
schema or identity wrote is refused when it opens, with every byte and its mode left as it was, also
when two formats share a version number, and so is a file that is no database; a store the open
makes is private under any umask and a store the process may not write is refused; another store
opened on a file a store of the process holds open leaves that store's lock; an existing store opens
without waiting for the write lock, and an open given a budget waits for a lock no longer than its
deadline; a link the normalized path reaches behind a missing directory is refused and a path the
checks cannot read is refused as the store's own error; a keyed payload is checked against its key
without a write; the key table and the digest answer what the events hold; and every read given a
budget, of the events, their keys, a keyed payload, a key or the digest, refuses a spent one before
reading, stops at its deadline, answers nothing once its last step ends past it, and waits for a lock
no longer than it."""

from __future__ import annotations

import os
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from contextlib import closing

import pytest

from goal_chainer import event_store
from goal_chainer.errors import PersistenceError
from goal_chainer.event_store import Event, EventStore, StoreSchema, digest
from goal_chainer.runtime import budget as budget_module
from goal_chainer.runtime.budget import InferenceBudgetExceeded, ReviewTimeout, RunBudget
from goal_chainer.snars_store import SnarsEventStore

LEDGER = StoreSchema(label="ledger", version=3, identity_key="ledger", identity_name="ledger name",
                     identifies="ledger")
EARLY = StoreSchema(label="early", version=1, identity_key="stream", identity_name="early stream",
                    identifies="early stream")
SNARS_IDENTITY = "c" * 64


# am[verifies a-v2m-es-extract-1019@b610bc]
def _tables(path) -> dict[str, list]:
    with closing(sqlite3.connect(path)) as connection:
        return {
            "metadata": connection.execute("SELECT * FROM metadata ORDER BY key").fetchall(),
            "columns": [row[1] for row in connection.execute("PRAGMA table_info(events)")],
            "events": connection.execute("SELECT * FROM events ORDER BY sequence").fetchall(),
            "keys": connection.execute("SELECT * FROM event_keys ORDER BY sequence").fetchall(),
        }


# A store keeps its identity in the column its schema names, records its own metadata, hashes each
# event with its own version, and names itself in its messages, its label starting a sentence
# capitalised.
# am[verifies a-v2m-es-extract-1019@b610bc]
def test_a_store_keeps_its_schema_identity_column_metadata_and_messages(tmp_path) -> None:
    path = tmp_path / "ledger.sqlite3"
    with EventStore(path, schema=LEDGER, identity="books") as store:
        first = store.append_prepared("entry", {"amount": 3})
        keyed = store.append_prepared("entry", {"amount": 4}, key="e-2")
        store._connection.execute("UPDATE events SET ledger = 'other' WHERE sequence = 2")  # noqa: SLF001

        with pytest.raises(PersistenceError, match="^Ledger event was recorded against a different ledger.$"):
            store.events()
        store._connection.execute("UPDATE events SET ledger = 'books' WHERE sequence = 2")  # noqa: SLF001
        events = store.events()

    tables = _tables(path)
    assert events == (first, keyed)
    assert type(first) is Event and first.identity == "books" and first.schema_version == 3
    assert first.event_id == LEDGER.event_id(1, "entry", '{"amount":3}', "books")
    assert tables["metadata"] == [("ledger", "books"), ("schema_version", "3")]
    assert tables["columns"] == ["sequence", "event_id", "kind", "payload_json", "ledger", "schema_version"]
    assert tables["keys"] == [("entry", "e-2", 2)]
    with pytest.raises(PersistenceError, match="^The ledger name must be nonempty text.$"):
        EventStore(path, schema=LEDGER, identity=" ")
    assert LEDGER.title == "Ledger" and SnarsEventStore.memory(snars_identity=SNARS_IDENTITY).schema.title == "SNARS"


# am[verifies a-v2m-es-extract-1019@b610bc]
def _snars_store(path) -> None:
    with SnarsEventStore(path, snars_identity=SNARS_IDENTITY) as store:
        store.append("belief", {"positive": 1})


# am[verifies a-v2m-es-extract-1019@b610bc]
def _early_store(path) -> None:
    with EventStore(path, schema=EARLY, identity="s") as store:
        store.append_prepared("entry", {"amount": 1}, key="e-1")


# A SNARS version-1 store as that version wrote its metadata: schema_version 1 beside the
# Mettabase commit it named.
# am[verifies a-v2m-es-keyset-1019@b2f86c]
def _snars_version_one_store(path) -> None:
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany("INSERT INTO metadata VALUES (?, ?)",
                               [("schema_version", "1"), ("mettabase_commit", "c" * 40)])


# A store written under schema_version alone, as no store writes it.
# am[verifies a-v2m-es-keyset-1019@b2f86c]
def _version_only_store(path) -> None:
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO metadata VALUES ('schema_version', '3')")


# Another application's database, with a table named as a store's own is and no store metadata.
# am[verifies a-v2m-es-check-before-write-1019@4edc67]
def _application_database(path) -> None:
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, title TEXT)")
        connection.execute("INSERT INTO events (title) VALUES ('standup')")


# am[verifies a-v2m-es-keyset-1019@b2f86c]
def _open_ledger(path) -> None:
    EventStore(path, schema=LEDGER, identity="books")


# am[verifies a-v2m-es-keyset-1019@b2f86c]
def _open_early(path) -> None:
    EventStore(path, schema=EARLY, identity="s")


# am[verifies a-v2m-es-keyset-1019@b2f86c]
def _open_snars(path) -> None:
    SnarsEventStore(path, snars_identity=SNARS_IDENTITY)


# A store opens only a file its own schema and identity wrote, and refuses any other before it
# writes a byte or changes its mode, here 0644: by the version the file records where the versions
# differ, with the message every store gives a version mismatch, and by its metadata keys where two
# formats share a version, as a SNARS version-3 store and a version-3 ledger do, and as a SNARS
# version-1 store and a version-1 early stream do (c-v2m-es-version-collision-1019). A file holding
# schema_version alone is no store's and is refused too, never given the opener's identity, and so
# is another application's database, whose tables no store metadata names. The refused files
# written without WAL stay so.
# am[verifies a-v2m-es-keyset-1019@b2f86c] am[verifies a-v2m-es-extract-1019@b610bc]
# am[verifies a-v2m-es-check-before-write-1019@4edc67] am[verifies a-v2rs-opath-open-1020@5f6c09]
@pytest.mark.parametrize(("written", "opened", "refusal", "details"), [
    (_snars_store, _open_early, "^Early store metadata does not match this runtime.$",
     {"key": "schema_version", "expected": "1", "received": "3"}),
    (_early_store, _open_snars, "^SNARS store metadata does not match this runtime.$",
     {"key": "schema_version", "expected": "3", "received": "1"}),
    (_snars_store, _open_ledger, "^Ledger store metadata does not hold exactly this store's keys.$",
     {"expected": ["ledger", "schema_version"], "received": ["schema_version", "snars_identity"]}),
    (_early_store, _open_ledger, "^Ledger store metadata does not match this runtime.$",
     {"key": "schema_version", "expected": "3", "received": "1"}),
    (_snars_version_one_store, _open_early, "^Early store metadata does not hold exactly this store's keys.$",
     {"expected": ["schema_version", "stream"], "received": ["mettabase_commit", "schema_version"]}),
    (_version_only_store, _open_snars, "^SNARS store metadata does not hold exactly this store's keys.$",
     {"expected": ["schema_version", "snars_identity"], "received": ["schema_version"]}),
    (_application_database, _open_early, "^Early database holds tables but no store metadata.$",
     {"tables": ["events"]}),
], ids=["SNARS file as early", "early file as SNARS", "SNARS file as ledger at one version",
        "early file as ledger", "SNARS version-1 file as early at one version", "version alone as SNARS",
        "another application's database"])
def test_a_file_another_store_wrote_is_refused_and_left_as_it_was(tmp_path, written, opened, refusal,
                                                                   details) -> None:
    path = tmp_path / "store.sqlite3"
    written(path)
    path.chmod(0o644)
    before = path.read_bytes()

    with pytest.raises(PersistenceError, match=refusal) as refused:
        opened(path)

    assert dict(refused.value.details) == details
    assert path.read_bytes() == before
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


# A file that is no database, such as a script, is refused whether the open may create or not, and
# keeps its bytes and its mode: the store changes an existing file only once it has read the file
# and found its own metadata there.
# am[verifies a-v2rs-opath-open-1020@5f6c09]
@pytest.mark.parametrize("create", [False, True], ids=["read", "create"])
def test_a_file_that_is_no_database_is_refused_with_its_bytes_and_mode(tmp_path, create) -> None:
    script = tmp_path / "deploy.sh"
    script.write_text("#!/bin/sh\necho deployed\n")
    script.chmod(0o755)

    with pytest.raises(PersistenceError, match="^Unable to open the early event store.$"):
        EventStore(script, schema=EARLY, identity="s", create=create)

    assert script.read_text() == "#!/bin/sh\necho deployed\n"
    assert stat.S_IMODE(script.stat().st_mode) == 0o755


# An empty file holds no store, so an open that may not create refuses it and leaves its mode, while
# an open that may create writes its first bytes, so it makes it 0600 before SQLite opens it, and its
# WAL and shared-memory files with it.
# am[verifies a-v2rs-opath-open-1020@5f6c09] am[verifies a-v2m-st-read-refuses-1020@676ded]
def test_an_empty_file_is_refused_by_a_read_and_made_a_private_store_by_a_create(tmp_path) -> None:
    path = tmp_path / "early.sqlite3"
    path.touch()
    path.chmod(0o644)

    with pytest.raises(PersistenceError, match="^No early store is at the database path.$"):
        EventStore(path, schema=EARLY, identity="s", create=False)
    unchanged = stat.S_IMODE(path.stat().st_mode)
    with EventStore(path, schema=EARLY, identity="s") as store:
        store.append_prepared("entry", {"amount": 1})
        modes = _modes(path)

    assert unchanged == 0o644
    assert modes == [0o600, 0o600, 0o600]


# The modes of a store's database, WAL and shared-memory files.
# am[verifies a-v2rs-opath-open-1020@5f6c09]
def _modes(path) -> list[int]:
    return [stat.S_IMODE(os.stat(f"{path}{suffix}").st_mode) for suffix in ("", "-wal", "-shm")]


# A store at 0600 whose WAL and shared-memory files an older version left at 0644, kept by a live
# connection, has them made 0600 by the next open that finds its own metadata, a read included; an
# open another identity makes is refused and leaves all three files as they were.
# am[verifies a-v2rs-opath-open-1020@5f6c09]
def test_every_verified_open_makes_the_side_files_private_and_a_refused_one_leaves_them(tmp_path) -> None:
    path = tmp_path / "early.sqlite3"
    with EventStore(path, schema=EARLY, identity="s") as holder:
        holder.append_prepared("entry", {"amount": 1})
        for suffix in ("-wal", "-shm"):
            os.chmod(f"{path}{suffix}", 0o644)
        left = _modes(path)
        with pytest.raises(PersistenceError, match="does not match this runtime"):
            EventStore(path, schema=EARLY, identity="t", create=False)
        refused = _modes(path)
        with EventStore(path, schema=EARLY, identity="s", create=False) as reader:
            events = reader.events()
        verified = _modes(path)

    assert left == refused == [0o600, 0o644, 0o644]
    assert verified == [0o600, 0o600, 0o600]
    assert [event.payload for event in events] == [{"amount": 1}]


# A store the open makes is 0600 under any umask, with its WAL and shared-memory files, so a umask
# that takes away the owner's write bit still leaves a store the process can append to.
# am[verifies a-v2rs-opath-open-1020@5f6c09]
@pytest.mark.parametrize("umask", [0o022, 0o077, 0o277])
def test_a_store_the_open_makes_is_private_under_any_umask(tmp_path, umask) -> None:
    path = tmp_path / "early.sqlite3"
    previous = os.umask(umask)
    try:
        with EventStore(path, schema=EARLY, identity="s") as store:
            store.append_prepared("entry", {"amount": 1})
            modes = _modes(path)
    finally:
        os.umask(previous)

    assert modes == [0o600, 0o600, 0o600]


# A store file the process may not both read and write is refused when it opens, since SQLite would
# open it read-only and refuse only the first append: a store left at 0400 is refused exactly when
# this process lacks that access, which a privileged process has whatever the mode, and keeps its mode.
# am[verifies a-v2rs-opath-open-1020@5f6c09]
def test_a_store_the_process_may_not_write_is_refused(tmp_path) -> None:
    path = tmp_path / "early.sqlite3"
    _early_store(path)
    path.chmod(0o400)
    try:
        if os.access(path, os.R_OK | os.W_OK):
            EventStore(path, schema=EARLY, identity="s").close()
        else:
            with pytest.raises(PersistenceError, match="^Unable to open the early event store.$") as refused:
                EventStore(path, schema=EARLY, identity="s")
            assert "Permission denied" in refused.value.details["error"]
            assert stat.S_IMODE(path.stat().st_mode) == 0o400
    finally:
        path.chmod(0o600)


# Whether another process can take the write lock on SQLite's shared byte range of the database, as a
# connection taking an EXCLUSIVE lock does (os_unix.c: SHARED_FIRST is PENDING_BYTE + 2, 0x40000002,
# and SHARED_SIZE 510), which SQLite takes before it checkpoints and deletes the WAL of a database no
# other connection holds open.
# am[verifies a-v2rs-opath-open-1020@5f6c09]
def _exclusive_lock_free(path) -> bool:
    probe = (
        "import fcntl, os, sys\n"
        "descriptor = os.open(sys.argv[1], os.O_RDWR)\n"
        "try:\n"
        "    fcntl.lockf(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB, 510, 0x40000002, os.SEEK_SET)\n"
        "except OSError:\n"
        "    print('held')\n"
        "else:\n"
        "    print('free')\n"
    )
    answer = subprocess.run([sys.executable, "-I", "-c", probe, str(path)], capture_output=True, text=True, check=True)
    return answer.stdout.strip() == "free"


# A store keeps the SHARED lock a WAL connection holds on its database while another store of this
# process opens and closes the same file, by a read or a create, so another process still cannot take
# the database's EXCLUSIVE lock and delete the WAL under it, which on SQLite before 3.51 lost
# committed events (c-v2rs-lost-commit-sqlite346-1020).
# am[verifies a-v2rs-opath-open-1020@5f6c09]
@pytest.mark.parametrize("create", [False, True], ids=["read", "create"])
def test_another_store_on_an_open_file_leaves_its_lock(tmp_path, create) -> None:
    path = tmp_path / "early.sqlite3"
    with EventStore(path, schema=EARLY, identity="s") as store:
        store.append_prepared("entry", {"amount": 1})
        held_before = not _exclusive_lock_free(path)
        EventStore(path, schema=EARLY, identity="s", create=create).close()
        held_after = not _exclusive_lock_free(path)
        store.append_prepared("entry", {"amount": 2})
        events = store.events()

    assert held_before and held_after
    assert [event.payload for event in events] == [{"amount": 1}, {"amount": 2}]


# A path that names a missing directory and then .. reaches whatever directory its normalized form
# names, so a link there is refused like any link in the path, and nothing is made where it leads.
# am[verifies a-v2rs-typed-path-checks-1020@15ef87]
def test_a_link_behind_a_missing_directory_is_refused(tmp_path) -> None:
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "link").symlink_to(tmp_path / "elsewhere")

    with pytest.raises(PersistenceError, match="^Early database path must not pass through a symbolic link.$") as refused:
        EventStore(tmp_path / "missing" / ".." / "real" / "link" / "early.sqlite3", schema=EARLY, identity="s")

    assert refused.value.details["link"] == str(tmp_path / "real" / "link")
    assert list((tmp_path / "elsewhere").iterdir()) == []


# A path the checks cannot read is the store's own refusal, naming the operating system's reason, on
# every Python the package supports: the home directory of a user the system does not know, and a
# directory the process may not search, which a privileged process may.
# am[verifies a-v2rs-typed-path-checks-1020@15ef87]
def test_a_path_the_checks_cannot_read_is_refused_with_its_reason(tmp_path) -> None:
    with pytest.raises(PersistenceError, match="^Early database path cannot be checked.$") as unknown:
        EventStore("~goalchainer-no-such-user-1020/early.sqlite3", schema=EARLY, identity="s")
    locked = tmp_path / "locked"
    (locked / "inner").mkdir(parents=True)
    locked.chmod(0o000)
    try:
        if os.access(locked, os.X_OK):
            EventStore(locked / "inner" / "early.sqlite3", schema=EARLY, identity="s").close()
        else:
            with pytest.raises(PersistenceError, match="^Early database path cannot be checked.$") as refused:
                EventStore(locked / "inner" / "early.sqlite3", schema=EARLY, identity="s")
            assert "Permission denied" in refused.value.details["error"]
    finally:
        locked.chmod(0o700)

    assert "home directory" in unknown.value.details["error"]


# A file whose metadata table was made by an open that stopped before filling it holds no other
# table, so the next open gives it this store's metadata and opens it as new.
# am[verifies a-v2m-es-check-before-write-1019@4edc67]
def test_a_file_with_an_empty_metadata_table_opens_as_a_new_store(tmp_path) -> None:
    path = tmp_path / "early.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    with EventStore(path, schema=EARLY, identity="s") as store:
        store.append_prepared("entry", {"amount": 1})

    assert _tables(path)["metadata"] == [("schema_version", "1"), ("stream", "s")]


# A store reopened under its own schema and identity reads back what it wrote, and the same file
# under another identity of its schema is refused by that identity.
# am[verifies a-v2m-es-extract-1019@b610bc]
def test_a_store_reopens_under_its_identity_and_refuses_another(tmp_path) -> None:
    path = tmp_path / "early.sqlite3"
    _early_store(path)

    with EventStore(path, schema=EARLY, identity="s") as store:
        assert [event.payload for event in store.events()] == [{"amount": 1}]
    with pytest.raises(PersistenceError, match="does not match this runtime") as refused:
        EventStore(path, schema=EARLY, identity="t")
    assert dict(refused.value.details) == {"key": "stream", "expected": "t", "received": "s"}


# recorded answers whether a payload is the one its key holds by the rule append_prepared applies:
# False before anything is recorded, True for the recorded payload, whatever order its fields were
# given in, and append_prepared's refusal for any other; it writes nothing and leaves no
# transaction open, and refuses what append_prepared refuses before reading anything.
# am[verifies a-v2-outcome-sequential-conflict-1020@10212e] am[verifies a-v2m-es-extract-1019@b610bc]
def test_recorded_checks_a_keyed_payload_by_the_append_rule_without_writing() -> None:
    with EventStore(None, schema=LEDGER, identity="books") as store:
        assert store.recorded("entry", {"amount": 1, "memo": "a"}, key="e-1") is False
        store.append_prepared("entry", {"amount": 1, "memo": "a"}, key="e-1")
        changes = store._connection.total_changes  # noqa: SLF001

        assert store.recorded("entry", {"memo": "a", "amount": 1}, key="e-1") is True
        assert store.recorded("entry", {"amount": 1, "memo": "a"}, key="e-2") is False
        assert store.recorded("other", {"amount": 1, "memo": "a"}, key="e-1") is False
        with pytest.raises(PersistenceError, match="^A different event is already recorded under this key.$") as refused:
            store.recorded("entry", {"amount": 2, "memo": "a"}, key="e-1")
        for kind, payload, key in [("entry", {"amount": 1}, "\udfff"), (" ", {"amount": 1}, "e-1"),
                                   ("entry", [1], "e-1"), ("entry", {"amount": float("nan")}, "e-1")]:
            with pytest.raises(PersistenceError):
                store.recorded(kind, payload, key=key)

        assert dict(refused.value.details) == {"kind": "entry", "key": "e-1", "sequence": 1}
        assert store._connection.total_changes == changes  # noqa: SLF001
        assert not store._connection.in_transaction  # noqa: SLF001
        assert len(store.events()) == 1


# The key table answers each keyed event's kind and key by its sequence and holds nothing for an
# unkeyed one, and the digest of a read is the store's state digest.
# am[verifies a-v2m-es-extract-1019@b610bc]
def test_event_keys_and_the_digest_answer_what_the_events_hold() -> None:
    with EventStore(None, schema=LEDGER, identity="books") as store:
        store.append_prepared("entry", {"amount": 1})
        store.append_prepared("entry", {"amount": 2}, key="e-2")
        store.append_prepared("note", {"text": "x"}, key="n-3")
        events = store.events()

        assert store.event_keys() == {2: ("entry", "e-2"), 3: ("note", "n-3")}
        assert digest(events) == store.state_digest() == digest(store.events())
        assert digest(events[:2]) != store.state_digest()


# A read through N takes events 1 to N and the keys of those events alone, 0 taking none and a bound
# past the last event, however large, taking them all; a bound that is no nonnegative integer, a bool
# included, is refused before the read.
# am[verifies a-v2rs-events-budget-1020@a8933d]
def test_a_read_through_n_takes_the_first_n_events_and_their_keys() -> None:
    with EventStore(None, schema=LEDGER, identity="books") as store:
        store.append_batch([("entry", {"n": n}, f"e-{n}" if n % 2 else None) for n in range(1, 6)])
        every = store.events()

        assert store.events(through=3) == every[:3] and store.event_keys(through=3) == {1: ("entry", "e-1"), 3: ("entry", "e-3")}
        assert store.events(through=0) == () and store.event_keys(through=0) == {}
        assert store.events(through=10**30) == every and digest(store.events(through=5)) == store.state_digest()
        for through in (True, -1, 1.5, "3"):
            with pytest.raises(PersistenceError, match="last event sequence"):
                store.events(through=through)
            with pytest.raises(PersistenceError, match="last event sequence"):
                store.event_keys(through=through)


# Every read a store answers, given a caller's budget, over a store holding one entry under key e-1:
# the key lookups also ask after e-2, which holds nothing.
# am[verifies a-v2rs-events-budget-1020@a8933d] am[verifies a-v2rs-kr-store-1020@a28d14]
READS = {
    "events": lambda store, budget: store.events(budget=budget),
    "event_keys": lambda store, budget: store.event_keys(budget=budget),
    "recorded": lambda store, budget: store.recorded("entry", {"amount": 1}, key="e-1", budget=budget),
    "recorded, none": lambda store, budget: store.recorded("entry", {"amount": 1}, key="e-2", budget=budget),
    "has_key": lambda store, budget: store.has_key("entry", "e-1", budget=budget),
    "has_key, none": lambda store, budget: store.has_key("entry", "e-2", budget=budget),
    "state_digest": lambda store, budget: store.state_digest(budget=budget),
}


# Each read refuses a budget already spent with its exhaustion before any statement runs, and under a
# budget that holds it answers what it answers without one. The key, payload and digest reads once
# took no budget, so they read past a spent one (i-v2rs-key-reads-unbudgeted-1020).
# am[verifies a-v2rs-events-budget-1020@a8933d] am[verifies a-v2rs-kr-store-1020@a28d14]
@pytest.mark.parametrize("read", READS, ids=list(READS))
def test_each_read_refuses_a_spent_budget_and_answers_as_before_under_one_that_holds(read) -> None:
    with EventStore(None, schema=LEDGER, identity="books") as store:
        store.append_prepared("entry", {"amount": 1}, key="e-1")
        spent = RunBudget(inference_budget=1, timeout_seconds=60)
        spent.charge(1)
        statements = []
        store._connection.set_trace_callback(statements.append)  # noqa: SLF001
        with pytest.raises(InferenceBudgetExceeded):
            READS[read](store, spent)
        store._connection.set_trace_callback(None)  # noqa: SLF001
        answers = [READS[read](store, budget) for budget in (RunBudget(inference_budget=None, timeout_seconds=60), None)]

    assert statements == []
    assert answers[0] == answers[1]


# A read under a budget reads it before it verifies each event, so a deadline passing while a stream
# is read stops it at that event with the budget's own error; here the clock moves a second at every
# reading of it, so the deadline 4.5 s after the budget is made passes at the fourth event.
# am[verifies a-v2rs-events-budget-1020@a8933d]
def test_a_read_under_a_budget_stops_at_its_deadline(monkeypatch) -> None:
    with EventStore(None, schema=LEDGER, identity="books") as store:
        store.append_batch([("entry", {"n": n}, None) for n in range(10)])
        clock = iter(range(1000))
        monkeypatch.setattr(budget_module.time, "monotonic", lambda: float(next(clock)))
        budget = RunBudget(inference_budget=None, timeout_seconds=4.5)
        with pytest.raises(ReviewTimeout):
            store.events(budget=budget)
        readings = next(clock)
        monkeypatch.undo()
        events = store.events()

    assert readings == 6
    assert len(events) == 10


# A connection whose read statements end late: the last step of each SELECT's cursor, the one that
# finds no further row, moves the clock 100 s on, as a statement scanning rows it keeps none of would.
# am[verifies a-v2rs-kr-store-1020@a28d14]
class _LateEnd:
    def __init__(self, connection, now) -> None:
        self._connection = connection
        self._now = now

    def execute(self, sql, parameters=()):
        cursor = self._connection.execute(sql, parameters)
        return _LateCursor(cursor, self._now) if sql.lstrip().startswith("SELECT") else cursor

    def __getattr__(self, name):
        return getattr(self._connection, name)


# A cursor whose last step takes 100 s by the clock.
# am[verifies a-v2rs-kr-store-1020@a28d14]
class _LateCursor:
    def __init__(self, cursor, now) -> None:
        self._cursor = cursor
        self._now = now

    def __iter__(self):
        yield from self._cursor
        self._now[0] += 100.0

    def close(self) -> None:
        self._cursor.close()


# A statement that ends past the deadline answers nothing: every read, a key lookup that finds no row
# included, raises the budget's ReviewTimeout, since it reads the budget once more after its last
# step. The key and payload lookups once answered True or False past the deadline.
# am[verifies a-v2rs-kr-store-1020@a28d14]
@pytest.mark.parametrize("read", READS, ids=list(READS))
def test_a_read_whose_statement_ends_past_its_deadline_answers_nothing(monkeypatch, read) -> None:
    with EventStore(None, schema=LEDGER, identity="books") as store:
        store.append_prepared("entry", {"amount": 1}, key="e-1")
        now = [0.0]
        monkeypatch.setattr(budget_module.time, "monotonic", lambda: now[0])
        budget = RunBudget(inference_budget=None, timeout_seconds=10)
        monkeypatch.setattr(store, "_connection", _LateEnd(store._connection, now))  # noqa: SLF001
        with pytest.raises(ReviewTimeout):
            READS[read](store, budget)


# Each read's last step after its statement, which a test makes take 100 s by the clock: the check of
# the last event read, the comparison with the payload a key holds, and the digest's hashing.
# am[verifies a-v2rs-events-budget-1020@a8933d] am[verifies a-v2rs-kr-store-1020@a28d14]
LAST_STEPS = {
    "events": ("_checked", READS["events"]),
    "recorded": ("_same_as_recorded", READS["recorded"]),
    "state_digest": ("digest", READS["state_digest"]),
}


# The deadline passing in a read's last step, after its statement and before it answers, raises the
# budget's ReviewTimeout, since the read checks the budget once more after that step: the last
# event's check, here the only event's, the payload comparison and the digest's hashing alike.
# am[verifies a-v2rs-events-budget-1020@a8933d] am[verifies a-v2rs-kr-store-1020@a28d14]
@pytest.mark.parametrize("read", LAST_STEPS, ids=list(LAST_STEPS))
def test_an_overrun_in_a_reads_last_step_raises_its_timeout(monkeypatch, read) -> None:
    step, run = LAST_STEPS[read]
    with EventStore(None, schema=LEDGER, identity="books") as store:
        store.append_prepared("entry", {"amount": 1}, key="e-1")
        now = [0.0]
        monkeypatch.setattr(budget_module.time, "monotonic", lambda: now[0])
        budget = RunBudget(inference_budget=None, timeout_seconds=10)
        owner = store if step == "_checked" else event_store
        original = getattr(owner, step)

        # The step takes 100 s by the clock, then does its work.
        # am[verifies a-v2rs-kr-store-1020@a28d14]
        def slow(*arguments):
            now[0] += 100.0
            return original(*arguments)

        monkeypatch.setattr(owner, step, slow)
        with pytest.raises(ReviewTimeout):
            run(store, budget)


# A read waits for a lock SQLite makes a reader wait for no longer than its budget's deadline: on a
# store whose database another tool switched to a rollback journal, another connection holding it
# exclusively keeps each read waiting about the budget's 0.5 s, each then raising the budget's
# ReviewTimeout rather than waiting the store's own 5 s and failing as PersistenceError.
# am[verifies a-v2rs-events-budget-1020@a8933d] am[verifies a-v2rs-kr-store-1020@a28d14]
def test_a_read_waiting_for_a_lock_ends_by_its_budget(tmp_path) -> None:
    path = tmp_path / "ledger.sqlite3"
    with EventStore(path, schema=LEDGER, identity="books") as store:
        store.append_prepared("entry", {"amount": 1}, key="e-1")
    with closing(sqlite3.connect(path, isolation_level=None)) as switch:
        switch.execute("PRAGMA journal_mode = DELETE")
    waits = []
    with EventStore(path, schema=LEDGER, identity="books", create=False) as store, \
            closing(sqlite3.connect(path, isolation_level=None)) as holder:
        holder.execute("BEGIN EXCLUSIVE")
        for read in READS.values():
            start = time.monotonic()
            with pytest.raises(ReviewTimeout):
                read(store, RunBudget(inference_budget=None, timeout_seconds=0.5))
            waits.append(time.monotonic() - start)
        holder.execute("ROLLBACK")
        events = store.events()

    assert all(0.45 <= waited < 2.0 for waited in waits)
    assert [event.payload for event in events] == [{"amount": 1}]


# A batch appends in one transaction: a failure at its second event, here SQLite refusing the
# insert, rolls its first event back too and names the kind it failed at, and an empty batch
# appends nothing.
# am[verifies a-v2m-st-batch-1019@a8d5f5]
def test_a_batch_failing_inside_its_transaction_writes_none_of_its_events() -> None:
    with EventStore(None, schema=LEDGER, identity="books") as store:
        store.append_prepared("entry", {"amount": 0})
        store._connection.execute(  # noqa: SLF001
            "CREATE TRIGGER third BEFORE INSERT ON events WHEN NEW.sequence = 3 BEGIN SELECT RAISE(ABORT, 'blocked'); END"
        )

        with pytest.raises(PersistenceError, match="^Unable to append the ledger event.$") as refused:
            store.append_batch([("entry", {"amount": 1}, "e-1"), ("note", {"text": "x"}, None)])

        assert refused.value.details["kind"] == "note"
        assert [event.payload for event in store.events()] == [{"amount": 0}]
        assert store.event_keys() == {}
        assert store.append_batch([]) == ()
        assert not store._connection.in_transaction  # noqa: SLF001


# An open of a store whose metadata is already written takes no write lock, so on its WAL database a
# writer holding the lock on another connection does not delay it: a ledger and a SNARS store, each
# opened with no budget, open at once and read what they hold (c-v2m-st-open-repro-1020).
# am[verifies a-v2m-st-open-nolock-1020@e6eca3] am[verifies a-v2m-st-open-repro-1020@075517]
@pytest.mark.parametrize("opens", [
    lambda path: EventStore(path, schema=LEDGER, identity="books"),
    lambda path: SnarsEventStore(path, snars_identity=SNARS_IDENTITY),
], ids=["ledger", "SNARS"])
def test_an_existing_store_opens_at_once_while_another_connection_holds_the_write_lock(tmp_path, opens) -> None:
    path = tmp_path / "store.sqlite3"
    with opens(path) as store:
        store.append_prepared("entry", {"amount": 1}, key="e-1")
        recorded = store.events()
    with closing(sqlite3.connect(path, isolation_level=None)) as holder:
        holder.execute("BEGIN IMMEDIATE")
        start = time.monotonic()
        with opens(path) as store:
            events = store.events()
        opened = time.monotonic() - start
        holder.execute("ROLLBACK")

    assert opened < 1.0
    assert events == recorded


# An open given a budget reads it before the file is touched, so an exhausted budget raises its own
# exhaustion and creates nothing.
# am[verifies a-v2m-st-open-budget-1020@874189]
def test_an_open_with_an_exhausted_budget_creates_nothing(tmp_path) -> None:
    budget = RunBudget(inference_budget=1, timeout_seconds=60)
    budget.charge(1)

    with pytest.raises(InferenceBudgetExceeded):
        EventStore(tmp_path / "new.sqlite3", schema=LEDGER, identity="books", budget=budget)

    assert list(tmp_path.iterdir()) == []


# A store whose metadata table was made but never filled takes the write lock to fill it. Another
# connection holding that lock keeps an open with a budget waiting until the deadline, which raises
# the budget's ReviewTimeout after about its 0.5 s, not after the store's 5 s; a short store wait
# ending while the budget holds is the store's PersistenceError.
# am[verifies a-v2m-st-open-budget-1020@874189]
@pytest.mark.parametrize(("store_wait", "seconds", "refusal"), [
    (None, 0.5, ReviewTimeout),
    (0.2, 60, PersistenceError),
], ids=["deadline", "store wait"])
def test_an_open_waiting_for_the_write_lock_ends_by_its_budget(tmp_path, monkeypatch, store_wait, seconds, refusal) -> None:
    path = tmp_path / "ledger.sqlite3"
    with closing(sqlite3.connect(path, isolation_level=None)) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    if store_wait is not None:
        monkeypatch.setattr(event_store, "_LOCK_WAIT_SECONDS", store_wait)
    with closing(sqlite3.connect(path, isolation_level=None)) as holder:
        holder.execute("BEGIN IMMEDIATE")
        start = time.monotonic()
        with pytest.raises(refusal) as refused:
            EventStore(path, schema=LEDGER, identity="books",
                       budget=RunBudget(inference_budget=None, timeout_seconds=seconds))
        waited = time.monotonic() - start
        holder.execute("ROLLBACK")

    assert waited < 2.0
    if refusal is PersistenceError:
        assert refused.value.message == "Unable to open the ledger event store."
    else:
        assert waited >= 0.45


# An open with a budget of 2 s waits at most 2 s for a lock, and once it completes the store waits its
# own 5 s for the write lock again.
# am[verifies a-v2m-st-open-budget-1020@874189]
def test_an_open_with_a_budget_leaves_the_store_its_own_lock_wait(tmp_path) -> None:
    with EventStore(tmp_path / "ledger.sqlite3", schema=LEDGER, identity="books",
                    budget=RunBudget(inference_budget=None, timeout_seconds=2)) as store:
        assert store._connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000  # noqa: SLF001


# Two stores on one file appending one keyed event from two threads at once append it once: the
# key lookup and the insert share one write transaction. Each thread opens its own store, since a
# SQLite connection serves the thread that made it.
# am[verifies a-v2m-es-extract-1019@b610bc]
def test_two_stores_racing_on_one_key_append_it_once(tmp_path) -> None:
    path = tmp_path / "race.sqlite3"
    EventStore(path, schema=LEDGER, identity="books").close()
    start = threading.Barrier(2)
    answers = []

    # A thread that fails breaks the barrier, so the other never waits for it.
    # am[verifies a-v2m-es-extract-1019@b610bc]
    def append():
        try:
            with EventStore(path, schema=LEDGER, identity="books") as store:
                start.wait()
                answers.append(store.append_prepared("entry", {"amount": 1}, key="e-1"))
        except BaseException:
            start.abort()
            raise

    threads = [threading.Thread(target=append) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    with EventStore(path, schema=LEDGER, identity="books") as store:
        events = store.events()

    assert len(answers) == 2 and sorted(answer is None for answer in answers) == [False, True]
    assert [event.payload for event in events] == [{"amount": 1}]


# An identity key names a column in the store's SQL, so only an ASCII identifier other than
# schema_version names one.
# am[verifies a-v2m-es-extract-1019@b610bc]
@pytest.mark.parametrize("key", ["two words", "x; DROP TABLE events", "schema_version", "naïve", ""])
def test_a_schema_refuses_an_identity_key_no_column_can_carry(key) -> None:
    with pytest.raises(ValueError, match="identity key"):
        StoreSchema(label="bad", version=1, identity_key=key, identity_name="bad", identifies="bad")

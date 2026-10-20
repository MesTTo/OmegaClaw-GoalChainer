"""Purpose: test the SNARS event store: deterministic append and replay, redaction before
persistence, including the passage redactor for reading facts, and the integrity, schema and
keyed-append checks, an older version's store refused when it opens, the database and its side
files private and reached through no link from their creation, and refused opens and appends
leaving no connection or transaction open and every accepted byte as it was."""

from __future__ import annotations

import os
import sqlite3
import stat
from contextlib import closing

import pytest

from goal_chainer.errors import PersistenceError
from goal_chainer.event_store import StoreSchema
from goal_chainer.snars_ingestion import ReadingFact
from goal_chainer.sexpr.codec import SexprCodec
from goal_chainer.snars_store import SCHEMA_VERSION, SnarsEventStore, text_redactor
from reading_support import INCIDENT

IDENTITY = "c" * 64


# Records each connection the store makes, calling before() as the store asks SQLite to open and
# passing options, such as a factory, on to sqlite3.connect.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def _spy_connect(monkeypatch, before=lambda: None, **options) -> list[sqlite3.Connection]:
    made = []
    connect = sqlite3.connect

    # am[verifies a-integrate-store-boundaries-gate-1019@cded65]
    def spy(*args, **kwargs):
        before()
        made.append(connect(*args, **kwargs, **options))
        return made[-1]

    monkeypatch.setattr(sqlite3, "connect", spy)
    return made


# total_changes reads no file, so it answers on an open connection to any file and refuses only
# a closed one.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def _closed(connection: sqlite3.Connection) -> bool:
    try:
        connection.total_changes
    except sqlite3.ProgrammingError:
        return True
    return False


# am[related a-rt-snars-store-identity-1017@deb59d]
def test_memory_store_appends_in_deterministic_order() -> None:
    with SnarsEventStore.memory(snars_identity=IDENTITY) as store:
        first = store.append("belief", {"source": "a", "positive": 1})
        second = store.append("goal", {"desire": 0.9})

        events = store.events()

        assert [event.sequence for event in events] == [1, 2]
        assert events == (first, second)
        assert store.state_digest() == store.state_digest()
        assert not store.persistent


# am[related a-rt-snars-store-identity-1017@deb59d]
def test_file_store_replays_identically_after_restart(tmp_path) -> None:
    path = tmp_path / "snars.sqlite3"
    with SnarsEventStore(path, snars_identity=IDENTITY) as store:
        store.append("belief", {"text": "évidence", "source": "user"})
        expected = store.events()
        expected_digest = store.state_digest()

    with SnarsEventStore(path, snars_identity=IDENTITY) as reopened:
        assert reopened.events() == expected
        assert reopened.state_digest() == expected_digest
        assert reopened.persistent

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


# am[related a-rt-snars-store-identity-1017@deb59d]
def test_redactor_runs_before_persistence() -> None:
    def redact(kind, payload):
        assert kind == "ingest_text"
        return {**payload, "text": "[redacted]"}

    with SnarsEventStore.memory(
        snars_identity=IDENTITY,
        redactor=redact,
    ) as store:
        store.append("ingest_text", {"text": "customer@example.test"})

        assert store.events()[0].payload["text"] == "[redacted]"



# Each decided reading quotes the request in its passage, so the passage redactor blanks the text
# and every passage while every fact stays one ReadingFact.parse reads back, with its reading,
# answer and probability unchanged; an unknown reading's empty passage stays empty, and other
# events pass untouched.
# am[verifies a-ev-jev-c-store@16b3f6]
def test_the_text_redactor_blanks_the_text_and_every_passage_and_keeps_the_facts() -> None:
    codec = SexprCodec()
    facts = [
        ReadingFact("goalchainer:request", 1.0, p.id, answer, 0.8, INCIDENT.model, f"key-{p.id}", passage).emit(codec)
        for p, answer, passage in (
            (INCIDENT.propositions[0], "supported", "customer@example.test is in the log"),
            (INCIDENT.propositions[1], "unknown", ""),
        )
    ]
    redact = text_redactor(codec)

    redacted = redact("ingest_text", {"text": "customer@example.test", "facts": facts, "effects": []})

    assert redacted["text"] == "[redacted]"
    assert "customer@example.test" not in repr(redacted)
    kept = [ReadingFact.parse(fact, codec) for fact in redacted["facts"]]
    original = [ReadingFact.parse(fact, codec) for fact in facts]
    assert [fact.passage for fact in kept] == ["[redacted]", ""]
    assert [(f.reading_id, f.answer, f.probability, f.source) for f in kept] == [
        (f.reading_id, f.answer, f.probability, f.source) for f in original
    ]
    belief = {"statement": "(has-property request sensitive-data)", "source": "user"}
    assert redact("belief", belief) is belief


# A version-1 store's ingest events hold HyperBase facts nothing replays, and a version-2 store's
# events name a Mettabase commit where version 3 names the SNARS identity, so opening either is
# refused by its recorded schema version, never by SQLite failing on the column version 3 renamed.
# Each store is written with the schema its version's code created.
# am[verifies a-ev-jev-c-store@16b3f6] am[verifies a-rt-snars-store-identity-1017@deb59d]
@pytest.mark.parametrize("version", [1, 2])
def test_an_older_version_store_is_refused_when_it_opens(tmp_path, version) -> None:
    path = tmp_path / "snars.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE events (
                sequence INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                mettabase_commit TEXT NOT NULL,
                schema_version INTEGER NOT NULL
            );
            CREATE TABLE event_keys (
                kind TEXT NOT NULL,
                key TEXT NOT NULL,
                sequence INTEGER NOT NULL UNIQUE REFERENCES events(sequence),
                PRIMARY KEY (kind, key)
            );
            """
        )
        connection.executemany(
            "INSERT INTO metadata (key, value) VALUES (?, ?)",
            [("schema_version", str(version)), ("mettabase_commit", "c" * 40)],
        )
        connection.execute(
            "INSERT INTO events VALUES (1, 'e1', 'ingest_text', '{}', ?, ?)", ("c" * 40, version)
        )

    with pytest.raises(PersistenceError, match="metadata") as refused:
        SnarsEventStore(path, snars_identity=IDENTITY)
    assert refused.value.details["received"] == str(version)

# am[related a-rt-snars-store-identity-1017@deb59d]
def test_prepared_payload_is_redacted_once_and_replayed_verbatim() -> None:
    calls = []

    def redact(kind, payload):
        calls.append((kind, dict(payload)))
        return {**payload, "text": "[redacted]"}

    with SnarsEventStore.memory(
        snars_identity=IDENTITY,
        redactor=redact,
    ) as store:
        prepared = store.prepare_payload(
            "ingest_text",
            {"text": "customer@example.test", "facts": [], "effects": []},
        )
        event = store.append_prepared("ingest_text", prepared)

        assert len(calls) == 1
        assert event.payload == prepared
        assert store.events()[0].payload["text"] == "[redacted]"


# am[related a-rt-snars-store-identity-1017@deb59d]
def test_prepared_payload_is_detached_from_mutable_input() -> None:
    payload = {"values": ["original"]}
    with SnarsEventStore.memory(snars_identity=IDENTITY) as store:
        prepared = store.prepare_payload("belief", payload)
        payload["values"].append("changed")
        store.append_prepared("belief", prepared)

        assert store.events()[0].payload == {"values": ["original"]}


# am[verifies a-rt-snars-store-identity-1017@deb59d]
def test_store_rejects_a_different_snars_identity_after_restart(tmp_path) -> None:
    path = tmp_path / "snars.sqlite3"
    with SnarsEventStore(path, snars_identity=IDENTITY):
        pass

    with pytest.raises(PersistenceError, match="metadata"):
        SnarsEventStore(path, snars_identity="d" * 64)


# am[related a-rt-snars-store-identity-1017@deb59d]
def test_store_detects_corrupt_event_hash() -> None:
    with SnarsEventStore.memory(snars_identity=IDENTITY) as store:
        store.append("belief", {"positive": 1})
        store._connection.execute(  # noqa: SLF001
            "UPDATE events SET payload_json = ? WHERE sequence = 1",
            ('{"positive":2}',),
        )

        with pytest.raises(PersistenceError, match="content hash"):
            store.events()


# A stored event whose hash is recomputed passes the store's own checks, so JSON json.loads cannot
# read, an integer past the digit limit or nesting past its parser, is a corrupt event on replay.
# am[verifies a-rt-rr-json-read-1018@305497] am[related a-v2m-es-extract-1019@b610bc]
@pytest.mark.parametrize("payload", [
    '{"positive":1' + "0" * 5000 + "}",
    '{"positive":' + "[" * 100_000 + "]" * 100_000 + "}",
], ids=["integer of 5001 digits", "nested 100000 deep"])
def test_store_refuses_event_json_it_cannot_read_as_corrupt(payload) -> None:
    with SnarsEventStore.memory(snars_identity=IDENTITY) as store:
        event = store.append("belief", {"positive": 1})
        store._connection.execute(  # noqa: SLF001
            "UPDATE events SET payload_json = ?, event_id = ? WHERE sequence = ?",
            (payload, store.schema.event_id(event.sequence, event.kind, payload, IDENTITY), event.sequence),
        )

        with pytest.raises(PersistenceError, match="SNARS event JSON is corrupt"):
            store.events()


# am[related a-rt-snars-store-identity-1017@deb59d]
def test_store_detects_unsupported_schema_version() -> None:
    with SnarsEventStore.memory(snars_identity=IDENTITY) as store:
        store.append("belief", {"positive": 1})
        store._connection.execute(  # noqa: SLF001
            "UPDATE events SET schema_version = ? WHERE sequence = 1",
            (SCHEMA_VERSION + 1,),
        )

        with pytest.raises(PersistenceError, match="unsupported"):
            store.events()


# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def _final_link(tmp_path, target):
    link = tmp_path / "link.sqlite3"
    link.symlink_to(target)
    return link


# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def _linked_directory(tmp_path, target):
    (tmp_path / "via").symlink_to(target.parent)
    return tmp_path / "via" / target.name


# A link anywhere in the database's path is refused before anything is opened or made: a dangling
# final link, whose target is never created, a link to a store, and a linked directory, which
# would carry the store onto the store already in the directory it reaches.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
@pytest.mark.parametrize(("stored", "through"), [
    (False, _final_link),
    (True, _final_link),
    (True, _linked_directory),
], ids=["dangling final link", "final link to a store", "linked directory holding a store"])
def test_a_link_in_the_database_path_is_refused_and_its_target_left_as_it_was(tmp_path, stored, through) -> None:
    (tmp_path / "real").mkdir()
    target = tmp_path / "real" / "snars.sqlite3"
    if stored:
        with SnarsEventStore(target, snars_identity=IDENTITY) as store:
            store.append("belief", {"incident": "a"})
    before = target.read_bytes() if stored else None
    path = through(tmp_path, target)

    with pytest.raises(PersistenceError, match="symbolic link"):
        SnarsEventStore(path, snars_identity=IDENTITY)

    assert (target.read_bytes() if target.exists() else None) == before


# am[related a-rt-snars-store-identity-1017@deb59d]
def test_failed_insert_rolls_back_transaction() -> None:
    with SnarsEventStore.memory(snars_identity=IDENTITY) as store:
        store._connection.execute(  # noqa: SLF001
            """
            CREATE TRIGGER reject_events
            BEFORE INSERT ON events
            BEGIN
                SELECT RAISE(ABORT, 'blocked');
            END
            """
        )

        with pytest.raises(PersistenceError, match="Unable to append"):
            store.append("belief", {"positive": 1})

        assert store.events() == ()


# SQLite gives the WAL and shared-memory files it creates the database's mode. A store the open makes
# is 0600 when the store asks SQLite to open it; a store found at 0644 is read at that mode, since the
# store changes an existing file only once it has found its own metadata there, and then it and its
# WAL and shared-memory files are 0600 before any event is written. Under umask 022 all three files
# are 0600 from the open on.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65] am[verifies a-v2rs-opath-open-1020@5f6c09]
@pytest.mark.parametrize(("existing", "connected_at"), [(False, 0o600), (True, 0o644)],
                         ids=["new store", "existing store at 0644"])
def test_a_store_and_its_side_files_are_private_before_any_event_is_written(
    tmp_path, monkeypatch, existing, connected_at
) -> None:
    path = tmp_path / "snars.sqlite3"
    if existing:
        SnarsEventStore(path, snars_identity=IDENTITY).close()
        path.chmod(0o644)
    at_connect = []
    _spy_connect(monkeypatch, lambda: at_connect.append(
        stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    ))
    previous = os.umask(0o022)
    try:
        with SnarsEventStore(path, snars_identity=IDENTITY) as store:
            opened = [stat.S_IMODE(os.stat(f"{path}{suffix}").st_mode) for suffix in ("", "-wal", "-shm")]
            store.append("belief", {"text": "private"})
            appended = [stat.S_IMODE(os.stat(f"{path}{suffix}").st_mode) for suffix in ("", "-wal", "-shm")]
    finally:
        os.umask(previous)

    assert at_connect == [connected_at]
    assert opened == appended == [0o600, 0o600, 0o600]


# The store sets 0600 only on a regular file: a FIFO at the path is refused with its mode as it was.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def test_a_path_naming_no_regular_file_is_refused_with_its_mode_unchanged(tmp_path) -> None:
    fifo = tmp_path / "snars.sqlite3"
    os.mkfifo(fifo)
    fifo.chmod(0o644)

    with pytest.raises(PersistenceError, match="regular file"):
        SnarsEventStore(fifo, snars_identity=IDENTITY)

    assert stat.S_IMODE(fifo.stat().st_mode) == 0o644


# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def _relinked(path, other):
    path.unlink(missing_ok=True)
    path.symlink_to(other)
    return other


# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def _replaced(path, other):
    os.replace(other, path)
    return path


# Between the store's own open and SQLite's open by name, whoever can write the directory can swap
# the name: for a link to another store, or for another store moved over it. The store then
# refuses what SQLite opened, closes that connection, and leaves the other store as it was.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
@pytest.mark.parametrize("swap", [_relinked, _replaced], ids=["relinked", "replaced"])
def test_a_name_swapped_while_sqlite_opens_it_is_refused(tmp_path, monkeypatch, swap) -> None:
    path = tmp_path / "snars.sqlite3"
    other = tmp_path / "other.sqlite3"
    with SnarsEventStore(other, snars_identity=IDENTITY) as store:
        store.append("belief", {"incident": "other"})
    before = other.read_bytes()
    swapped = []
    made = _spy_connect(monkeypatch, lambda: swapped.append(swap(path, other)))

    with pytest.raises(PersistenceError, match="changed"):
        SnarsEventStore(path, snars_identity=IDENTITY)

    assert len(made) == 1 and _closed(made[0])
    assert swapped[0].read_bytes() == before


# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def _other_identity(path):
    SnarsEventStore(path, snars_identity="d" * 64).close()


# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def _not_a_database(path):
    path.write_bytes(b"not a database " * 64)


# A refused open closes the connection it made: a store recorded against another SNARS identity,
# refused by its metadata, and a file that is no SQLite database, refused by SQLite.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
@pytest.mark.parametrize(("existing", "refusal"), [
    (_other_identity, "metadata"),
    (_not_a_database, "Unable to open"),
], ids=["another identity", "not a database"])
def test_a_refused_open_closes_its_connection(tmp_path, monkeypatch, existing, refusal) -> None:
    path = tmp_path / "snars.sqlite3"
    existing(path)
    made = _spy_connect(monkeypatch)

    with pytest.raises(PersistenceError, match=refusal):
        SnarsEventStore(path, snars_identity=IDENTITY)

    assert len(made) == 1 and _closed(made[0])


# An identity the store could not record, or a name no file can have, is refused before the store
# makes anything, so the directory stays empty.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
@pytest.mark.parametrize(("identity", "name", "refusal"), [
    (" ", "snars.sqlite3", "SNARS identity"),
    ("\ud800", "snars.sqlite3", "SNARS identity"),
    (IDENTITY, "snars\0.sqlite3", "cannot name a file"),
    (IDENTITY, "\ud800.sqlite3", "cannot name a file"),
], ids=["blank identity", "identity holding a lone surrogate", "name holding NUL", "name holding a lone surrogate"])
def test_a_store_that_cannot_be_named_is_refused_before_anything_is_made(tmp_path, identity, name, refusal) -> None:
    with pytest.raises(PersistenceError, match=refusal):
        SnarsEventStore(tmp_path / name, snars_identity=identity)

    assert list(tmp_path.iterdir()) == []


# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def _nested(depth):
    value = {}
    for _ in range(depth):
        value = {"v": value}
    return value


# Text SQLite and the event hash cannot carry as UTF-8, and a payload JSON cannot encode, are refused
# before the append's transaction begins, so the refusal writes nothing and the next append is the
# stream's first event; preparing such a payload is refused the same way, before any batch runs it,
# and so is asking for such a key, and an event appended once by its content is refused alike before
# any key is made of it.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65] am[verifies a-v2rs-snars-keyed-dedup-1020@85653f]
@pytest.mark.parametrize("refused", [
    pytest.param(lambda store: store.append_prepared("belief", {"text": "\ud800"}), id="lone surrogate in a text"),
    pytest.param(lambda store: store.append_prepared("belief", {"\udc80": 1}), id="lone surrogate in a field name"),
    pytest.param(lambda store: store.append_prepared("\ud800", {"value": 1}), id="lone surrogate in a kind"),
    pytest.param(lambda store: store.append_prepared("outcome", {"value": 1}, key="\udfff"), id="lone surrogate in a key"),
    pytest.param(lambda store: store.append_prepared("belief", {"value": float("nan")}), id="a number JSON cannot hold"),
    pytest.param(lambda store: store.append_prepared("belief", {"value": object()}), id="a value JSON cannot hold"),
    pytest.param(lambda store: store.append_prepared("belief", _nested(100_000)), id="nested 100000 deep"),
    pytest.param(lambda store: store.prepare_payload("belief", {"text": "\ud800"}), id="lone surrogate prepared"),
    pytest.param(lambda store: store.has_key("outcome", "\udfff"), id="lone surrogate asked as a key"),
    pytest.param(lambda store: store.append_once("belief", {"text": "\ud800"}), id="lone surrogate appended once"),
    pytest.param(lambda store: store.append_once("\ud800", {"value": 1}), id="lone surrogate in a kind appended once"),
    pytest.param(lambda store: store.append_once("belief", {"value": float("nan")}), id="a number JSON cannot hold appended once"),
    pytest.param(lambda store: store.append_once("belief", [1]), id="no mapping appended once"),
])
def test_a_malformed_event_is_refused_before_its_transaction_and_the_next_append_proceeds(refused) -> None:
    with SnarsEventStore.memory(snars_identity=IDENTITY) as store:
        with pytest.raises(PersistenceError):
            refused(store)

        assert not store._connection.in_transaction  # noqa: SLF001
        event = store.append("belief", {"positive": 1})
        assert event.sequence == 1
        assert store.events() == (event,)


# A failure inside the append's transaction that is not SQLite's, an interrupt included, rolls the
# transaction back and propagates unchanged, and the store's next append proceeds.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65] am[related a-v2m-es-extract-1019@b610bc]
@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_a_failure_inside_the_append_transaction_rolls_it_back_and_propagates(monkeypatch, failure) -> None:
    def fail(*_):
        raise failure("injected")

    with SnarsEventStore.memory(snars_identity=IDENTITY) as store:
        monkeypatch.setattr(StoreSchema, "event_id", fail)
        with pytest.raises(failure, match="injected"):
            store.append("belief", {"positive": 1})
        monkeypatch.undo()

        assert not store._connection.in_transaction  # noqa: SLF001
        assert store.append("belief", {"positive": 1}).sequence == 1


# Once armed, its next BEGIN IMMEDIATE begins the transaction and then raises, as an interrupt
# CPython delivers when that execute call returns would.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
class _InterruptedBegin(sqlite3.Connection):
    armed = False

    # am[verifies a-integrate-store-boundaries-gate-1019@cded65]
    def execute(self, sql, *parameters):
        cursor = super().execute(sql, *parameters)
        if self.armed and sql == "BEGIN IMMEDIATE":
            self.armed = False
            raise KeyboardInterrupt("after BEGIN")
        return cursor


# An interrupt that arrives once BEGIN IMMEDIATE has begun the transaction, before the block that
# would use it, still rolls it back and propagates unchanged, and the next append proceeds.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def test_an_interrupt_as_begin_returns_rolls_the_transaction_back_and_propagates(monkeypatch) -> None:
    made = _spy_connect(monkeypatch, factory=_InterruptedBegin)
    with SnarsEventStore.memory(snars_identity=IDENTITY) as store:
        made[0].armed = True
        with pytest.raises(KeyboardInterrupt, match="after BEGIN"):
            store.append("belief", {"positive": 1})

        assert not made[0].in_transaction
        assert store.append("belief", {"positive": 1}).sequence == 1


# A keyed event is appended once: the same payload under its key again writes nothing and answers
# None, a different payload under it is refused, and neither leaves a transaction open.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def test_a_keyed_event_is_appended_once_and_a_repeat_leaves_no_transaction() -> None:
    with SnarsEventStore.memory(snars_identity=IDENTITY) as store:
        first = store.append_prepared("outcome", {"success": True}, key="o-1")

        assert store.append_prepared("outcome", {"success": True}, key="o-1") is None
        with pytest.raises(PersistenceError, match="different event"):
            store.append_prepared("outcome", {"success": False}, key="o-1")

        assert not store._connection.in_transaction  # noqa: SLF001
        assert store.has_key("outcome", "o-1")
        assert store.events() == (first,)


# The rows two fixed events are stored as, one of them keyed, are byte for byte the rows and event
# ids d4fbc9e4 stored (c-store-golden-rows-1019), so the repair changed no accepted event.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def test_stored_events_keep_the_bytes_and_ids_the_store_accepted(tmp_path) -> None:
    path = tmp_path / "snars.sqlite3"
    with SnarsEventStore(path, snars_identity=IDENTITY) as store:
        store.append("belief", {"text": "évidence", "source": "user", "positive": 1})
        store.append_prepared("outcome", {"observation": "o-1", "success": True}, key="o-1")

    with closing(sqlite3.connect(path)) as connection:
        events = connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        keys = connection.execute("SELECT * FROM event_keys").fetchall()
        metadata = connection.execute("SELECT * FROM metadata ORDER BY key").fetchall()

    assert events == [
        (1, "75dcb002cbb746d3d5faba1fb54a708c2a1b6bb63f186b73a3c9025cd024965b", "belief",
         '{"positive":1,"source":"user","text":"évidence"}', IDENTITY, 3),
        (2, "f456f89c9b7505f0592304263c30649b4a88a44aaf93d14ac454adaff85bc067", "outcome",
         '{"observation":"o-1","success":true}', IDENTITY, 3),
    ]
    assert keys == [("outcome", "o-1", 2)]
    assert metadata == [("schema_version", "3"), ("snars_identity", IDENTITY)]


# A directory every user can write lets any of them replace the store's files, unless its sticky
# bit keeps each user's entries to their owner.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
@pytest.mark.parametrize(("mode", "refused"), [(0o777, True), (0o1777, False)], ids=["world-writable", "sticky"])
def test_a_directory_every_user_can_write_is_refused_without_its_sticky_bit(tmp_path, mode, refused) -> None:
    directory = tmp_path / "shared"
    directory.mkdir()
    directory.chmod(mode)

    if refused:
        with pytest.raises(PersistenceError, match="world-writable"):
            SnarsEventStore(directory / "snars.sqlite3", snars_identity=IDENTITY)
        assert list(directory.iterdir()) == []
    else:
        SnarsEventStore(directory / "snars.sqlite3", snars_identity=IDENTITY).close()


# A relative name opens in the working directory, which the operating system names without links.
# am[verifies a-integrate-store-boundaries-gate-1019@cded65]
def test_a_relative_name_opens_in_the_working_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    with SnarsEventStore("snars.sqlite3", snars_identity=IDENTITY) as store:
        assert store.path == tmp_path / "snars.sqlite3"

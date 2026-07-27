from __future__ import annotations

import stat

import pytest

from goal_chainer.snars_models import SnarsPersistenceError
from goal_chainer.snars_store import SCHEMA_VERSION, SnarsEventStore

COMMIT = "c" * 40


def test_memory_store_appends_in_deterministic_order() -> None:
    with SnarsEventStore.memory(mettabase_commit=COMMIT) as store:
        first = store.append("belief", {"source": "a", "positive": 1})
        second = store.append("goal", {"desire": 0.9})

        events = store.events()

        assert [event.sequence for event in events] == [1, 2]
        assert events == (first, second)
        assert store.state_digest() == store.state_digest()
        assert not store.persistent


def test_file_store_replays_identically_after_restart(tmp_path) -> None:
    path = tmp_path / "snars.sqlite3"
    with SnarsEventStore(path, mettabase_commit=COMMIT) as store:
        store.append("belief", {"text": "évidence", "source": "user"})
        expected = store.events()
        expected_digest = store.state_digest()

    with SnarsEventStore(path, mettabase_commit=COMMIT) as reopened:
        assert reopened.events() == expected
        assert reopened.state_digest() == expected_digest
        assert reopened.persistent

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_redactor_runs_before_persistence() -> None:
    def redact(kind, payload):
        assert kind == "ingest_text"
        return {**payload, "text": "[redacted]"}

    with SnarsEventStore.memory(
        mettabase_commit=COMMIT,
        redactor=redact,
    ) as store:
        store.append("ingest_text", {"text": "customer@example.test"})

        assert store.events()[0].payload["text"] == "[redacted]"


def test_store_rejects_commit_mismatch_after_restart(tmp_path) -> None:
    path = tmp_path / "snars.sqlite3"
    with SnarsEventStore(path, mettabase_commit=COMMIT):
        pass

    with pytest.raises(SnarsPersistenceError, match="metadata"):
        SnarsEventStore(path, mettabase_commit="d" * 40)


def test_store_detects_corrupt_event_hash() -> None:
    with SnarsEventStore.memory(mettabase_commit=COMMIT) as store:
        store.append("belief", {"positive": 1})
        store._connection.execute(  # noqa: SLF001
            "UPDATE events SET payload_json = ? WHERE sequence = 1",
            ('{"positive":2}',),
        )

        with pytest.raises(SnarsPersistenceError, match="content hash"):
            store.events()


def test_store_detects_unsupported_schema_version() -> None:
    with SnarsEventStore.memory(mettabase_commit=COMMIT) as store:
        store.append("belief", {"positive": 1})
        store._connection.execute(  # noqa: SLF001
            "UPDATE events SET schema_version = ? WHERE sequence = 1",
            (SCHEMA_VERSION + 1,),
        )

        with pytest.raises(SnarsPersistenceError, match="unsupported"):
            store.events()


def test_store_rejects_symlink_path(tmp_path) -> None:
    target = tmp_path / "target.sqlite3"
    target.touch()
    link = tmp_path / "link.sqlite3"
    link.symlink_to(target)

    with pytest.raises(SnarsPersistenceError, match="symbolic link"):
        SnarsEventStore(link, mettabase_commit=COMMIT)


def test_failed_insert_rolls_back_transaction() -> None:
    with SnarsEventStore.memory(mettabase_commit=COMMIT) as store:
        store._connection.execute(  # noqa: SLF001
            """
            CREATE TRIGGER reject_events
            BEFORE INSERT ON events
            BEGIN
                SELECT RAISE(ABORT, 'blocked');
            END
            """
        )

        with pytest.raises(SnarsPersistenceError, match="Unable to append"):
            store.append("belief", {"positive": 1})

        assert store.events() == ()

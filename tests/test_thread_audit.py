from __future__ import annotations

import json
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from goal_chainer.thread_audit import ThreadAuditStore
from goal_chainer.thread_models import ThreadExecutionError


def fixed_clock() -> datetime:
    return datetime(2026, 7, 28, 1, 2, 3, tzinfo=UTC)


def test_audit_is_private_append_only_and_hash_chained(tmp_path) -> None:
    path = tmp_path / "thread.jsonl"
    store = ThreadAuditStore(path, clock=fixed_clock)

    first = store.append(
        thread_id="incident-42",
        event_type="thread-compiled",
        actor="thread-supervisor",
        payload={"digest": "abc"},
    )
    second = store.append(
        thread_id="incident-42",
        event_type="task-claimed",
        actor="thread-supervisor",
        payload={"task": "collect-evidence"},
    )

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_hash == first.event_hash
    assert store.verify() == (first, second)


def test_audit_rejects_tampering_before_append(tmp_path) -> None:
    path = tmp_path / "tampered.jsonl"
    store = ThreadAuditStore(path, clock=fixed_clock)
    store.append(
        thread_id="incident-42",
        event_type="thread-compiled",
        actor="thread-supervisor",
        payload={"value": 1},
    )
    row = json.loads(path.read_text())
    row["payload"]["value"] = 2
    path.write_text(json.dumps(row, sort_keys=True) + "\n")
    path.chmod(0o600)

    with pytest.raises(ThreadExecutionError, match="event hash"):
        store.append(
            thread_id="incident-42",
            event_type="task-claimed",
            actor="thread-supervisor",
            payload={},
        )


def test_concurrent_appenders_receive_contiguous_sequences(tmp_path) -> None:
    store = ThreadAuditStore(tmp_path / "concurrent.jsonl", clock=fixed_clock)

    def append(index: int) -> int:
        return store.append(
            thread_id="incident-42",
            event_type="usage-recorded",
            actor="thread-supervisor",
            payload={"index": index},
        ).sequence

    with ThreadPoolExecutor(max_workers=4) as executor:
        sequences = list(executor.map(append, range(12)))

    assert sorted(sequences) == list(range(1, 13))
    assert len(store.verify()) == 12


def test_audit_rejects_symlinks_and_permissive_files(tmp_path) -> None:
    target = tmp_path / "target.jsonl"
    target.write_text("")
    target.chmod(0o600)
    link = tmp_path / "link.jsonl"
    link.symlink_to(target)

    with pytest.raises(ThreadExecutionError, match="symbolic link"):
        ThreadAuditStore(link)

    target.chmod(0o644)
    with pytest.raises(ThreadExecutionError, match="permissions"):
        ThreadAuditStore(target).verify()


@given(
    st.dictionaries(
        st.text(min_size=1, max_size=12),
        st.one_of(st.integers(), st.booleans(), st.text(max_size=30)),
        max_size=8,
    )
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_audit_round_trips_json_payloads(tmp_path, payload) -> None:
    path = tmp_path / "property.jsonl"
    path.unlink(missing_ok=True)
    store = ThreadAuditStore(path, clock=fixed_clock)
    event = store.append(
        thread_id="incident-42",
        event_type="usage-recorded",
        actor="thread-supervisor",
        payload=payload,
    )

    assert store.verify()[0].payload == event.payload

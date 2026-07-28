"""Locked, append-only hash chain for thread orchestration events."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, cast

from .thread_models import ThreadAuditEvent, ThreadExecutionError

_ZERO_HASH = "0" * 64
_MAX_AUDIT_BYTES = 16 * 1024 * 1024


class ThreadAuditStore:
    """Verify and extend one private JSONL event chain."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = _audit_path(path)
        self._clock = clock or (lambda: datetime.now(UTC))

    def append(
        self,
        *,
        thread_id: str,
        event_type: str,
        actor: str,
        payload: Mapping[str, Any],
    ) -> ThreadAuditEvent:
        with _locked_audit(self.path, exclusive=True, create=True) as handle:
            events = _read_and_verify(handle, self.path)
            previous = events[-1].event_hash if events else _ZERO_HASH
            body = {
                "sequence": len(events) + 1,
                "timestamp": _timestamp(self._clock()),
                "thread_id": thread_id,
                "event_type": event_type,
                "actor": actor,
                "payload": dict(payload),
                "previous_hash": previous,
            }
            digest = _digest(body)
            event = _event_from_mapping(body, event_hash=digest)
            encoded = _canonical({**body, "event_hash": digest}) + b"\n"
            if handle.seek(0, os.SEEK_END) + len(encoded) > _MAX_AUDIT_BYTES:
                raise ThreadExecutionError(
                    "Thread audit log exceeds its size limit.",
                    details={"path": str(self.path), "limit": _MAX_AUDIT_BYTES},
                )
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            return event

    def verify(self) -> tuple[ThreadAuditEvent, ...]:
        if not self.path.exists():
            return ()
        with _locked_audit(self.path, exclusive=False, create=False) as handle:
            return _read_and_verify(handle, self.path)


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ThreadExecutionError("Thread audit clock must return an aware datetime.")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ThreadExecutionError(
            "Thread audit event is not valid JSON.",
            details={"error": str(exc)},
        ) from exc


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _read_and_verify(
    handle: BinaryIO,
    path: Path,
) -> tuple[ThreadAuditEvent, ...]:
    handle.seek(0, os.SEEK_END)
    size = handle.tell()
    if size > _MAX_AUDIT_BYTES:
        raise ThreadExecutionError(
            "Thread audit log exceeds its size limit.",
            details={"path": str(path), "size": size},
        )
    handle.seek(0)
    events: list[ThreadAuditEvent] = []
    previous = _ZERO_HASH
    for line_number, raw_line in enumerate(handle, start=1):
        if not raw_line.endswith(b"\n"):
            raise _audit_error(path, line_number, "unterminated JSONL record")
        try:
            row = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _audit_error(path, line_number, f"invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise _audit_error(path, line_number, "record is not an object")
        expected_fields = {
            "sequence",
            "timestamp",
            "thread_id",
            "event_type",
            "actor",
            "payload",
            "previous_hash",
            "event_hash",
        }
        if set(row) != expected_fields:
            raise _audit_error(path, line_number, "record fields are malformed")
        event_hash = row.pop("event_hash")
        if row["sequence"] != line_number:
            raise _audit_error(path, line_number, "sequence is discontinuous")
        if row["previous_hash"] != previous:
            raise _audit_error(path, line_number, "previous hash does not match")
        if event_hash != _digest(row):
            raise _audit_error(path, line_number, "event hash does not match")
        try:
            event = _event_from_mapping(row, event_hash=cast(str, event_hash))
        except (TypeError, ValueError) as exc:
            raise _audit_error(path, line_number, str(exc)) from exc
        events.append(event)
        previous = event.event_hash
    return tuple(events)


def _event_from_mapping(
    row: Mapping[str, Any],
    *,
    event_hash: str,
) -> ThreadAuditEvent:
    return ThreadAuditEvent(
        sequence=cast(int, row["sequence"]),
        timestamp=cast(str, row["timestamp"]),
        thread_id=cast(str, row["thread_id"]),
        event_type=cast(str, row["event_type"]),
        actor=cast(str, row["actor"]),
        payload=cast(Mapping[str, Any], row["payload"]),
        previous_hash=cast(str, row["previous_hash"]),
        event_hash=event_hash,
    )


def _audit_error(path: Path, line: int, reason: str) -> ThreadExecutionError:
    return ThreadExecutionError(
        f"Thread audit verification failed at line {line}: {reason}.",
        details={"path": str(path), "line": line, "reason": reason},
    )


def _audit_path(path: str | os.PathLike[str]) -> Path:
    candidate = Path(path).expanduser().absolute()
    if candidate.suffix != ".jsonl":
        raise ThreadExecutionError(
            "Thread audit path must end in .jsonl.",
            details={"path": str(candidate)},
        )
    if not candidate.parent.is_dir():
        raise ThreadExecutionError(
            "Thread audit parent directory does not exist.",
            details={"path": str(candidate.parent)},
        )
    if candidate.is_symlink():
        raise ThreadExecutionError(
            "Thread audit path must not be a symbolic link.",
            details={"path": str(candidate)},
        )
    return candidate


@contextmanager
def _locked_audit(
    path: Path,
    *,
    exclusive: bool,
    create: bool,
) -> Iterator[BinaryIO]:
    flags = os.O_RDWR if exclusive else os.O_RDONLY
    if create:
        flags |= os.O_CREAT | os.O_APPEND
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ThreadExecutionError(
            "Thread audit log could not be opened safely.",
            details={"path": str(path), "error": str(exc)},
        ) from exc
    mode = "a+b" if exclusive else "rb"
    with os.fdopen(descriptor, mode) as handle:
        file_stat = os.fstat(handle.fileno())
        if not stat.S_ISREG(file_stat.st_mode):
            raise ThreadExecutionError("Thread audit log is not a regular file.")
        if file_stat.st_uid != os.getuid():
            raise ThreadExecutionError("Thread audit log is not owned by this user.")
        if stat.S_IMODE(file_stat.st_mode) != 0o600:
            raise ThreadExecutionError(
                "Thread audit log permissions must be 0600.",
                details={
                    "path": str(path),
                    "mode": oct(stat.S_IMODE(file_stat.st_mode)),
                },
            )
        fcntl.flock(
            handle.fileno(),
            fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH,
        )
        yield handle


__all__ = ["ThreadAuditStore"]

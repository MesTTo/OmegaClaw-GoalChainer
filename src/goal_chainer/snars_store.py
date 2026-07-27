"""Append-only SQLite persistence for replaying native SNARS operations."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .snars_models import SnarsPersistenceError

SCHEMA_VERSION = 1
Redactor = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class SnarsEvent:
    sequence: int
    event_id: str
    kind: str
    payload: Mapping[str, Any]
    mettabase_commit: str
    schema_version: int


class SnarsEventStore:
    """A private append-only event stream with deterministic read order."""

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        mettabase_commit: str,
        redactor: Redactor | None = None,
    ) -> None:
        if not mettabase_commit.strip():
            raise SnarsPersistenceError("Mettabase commit must be nonempty.")
        self.mettabase_commit = mettabase_commit
        self.redactor = redactor
        self.path = None if path is None else _safe_database_path(path)
        target = ":memory:" if self.path is None else str(self.path)
        try:
            self._connection = sqlite3.connect(
                target,
                timeout=5.0,
                isolation_level=None,
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 5000")
            self._connection.execute("PRAGMA secure_delete = ON")
            if self.path is not None:
                self._connection.execute("PRAGMA journal_mode = WAL")
            self._initialize()
            if self.path is not None:
                os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        except (OSError, sqlite3.Error) as exc:
            raise SnarsPersistenceError(
                "Unable to open the SNARS event store.",
                details={"path": target, "error": str(exc)},
            ) from exc

    @classmethod
    def memory(
        cls,
        *,
        mettabase_commit: str,
        redactor: Redactor | None = None,
    ) -> SnarsEventStore:
        return cls(
            None,
            mettabase_commit=mettabase_commit,
            redactor=redactor,
        )

    @property
    def persistent(self) -> bool:
        return self.path is not None

    def append(self, kind: str, payload: Mapping[str, Any]) -> SnarsEvent:
        return self.append_prepared(kind, self.prepare_payload(kind, payload))

    def prepare_payload(
        self,
        kind: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if not isinstance(kind, str) or not kind.strip():
            raise SnarsPersistenceError("Event kind must be nonempty.")
        if not isinstance(payload, Mapping):
            raise SnarsPersistenceError("Event payload must be a mapping.")
        try:
            visible = self.redactor(kind, payload) if self.redactor else payload
            canonical = _canonical_json(visible)
        except Exception as exc:
            raise SnarsPersistenceError(
                "Event redaction or JSON encoding failed.",
                details={"kind": kind, "error": str(exc)},
            ) from exc
        prepared = json.loads(canonical)
        if not isinstance(prepared, dict):
            raise SnarsPersistenceError("Prepared event payload must be an object.")
        return prepared

    def append_prepared(
        self,
        kind: str,
        payload: Mapping[str, Any],
    ) -> SnarsEvent:
        if not isinstance(kind, str) or not kind.strip():
            raise SnarsPersistenceError("Event kind must be nonempty.")
        if not isinstance(payload, Mapping):
            raise SnarsPersistenceError("Event payload must be a mapping.")
        try:
            canonical = _canonical_json(payload)
        except (TypeError, ValueError) as exc:
            raise SnarsPersistenceError(
                "Prepared event JSON encoding failed.",
                details={"kind": kind, "error": str(exc)},
            ) from exc
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM events"
            ).fetchone()
            sequence = int(row["next_sequence"])
            event_id = _event_id(
                sequence,
                kind,
                canonical,
                self.mettabase_commit,
            )
            self._connection.execute(
                """
                INSERT INTO events (
                    sequence, event_id, kind, payload_json,
                    mettabase_commit, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    sequence,
                    event_id,
                    kind,
                    canonical,
                    self.mettabase_commit,
                    SCHEMA_VERSION,
                ),
            )
            self._connection.execute("COMMIT")
        except sqlite3.Error as exc:
            _rollback_quietly(self._connection)
            raise SnarsPersistenceError(
                "Unable to append the SNARS event.",
                details={"kind": kind, "error": str(exc)},
            ) from exc
        return SnarsEvent(
            sequence,
            event_id,
            kind,
            json.loads(canonical),
            self.mettabase_commit,
            SCHEMA_VERSION,
        )

    def events(self) -> tuple[SnarsEvent, ...]:
        try:
            rows = self._connection.execute(
                """
                SELECT sequence, event_id, kind, payload_json,
                       mettabase_commit, schema_version
                FROM events
                ORDER BY sequence ASC
                """
            ).fetchall()
        except sqlite3.Error as exc:
            raise SnarsPersistenceError(
                "Unable to read SNARS events.",
                details={"error": str(exc)},
            ) from exc

        events: list[SnarsEvent] = []
        expected_sequence = 1
        for row in rows:
            sequence = int(row["sequence"])
            if sequence != expected_sequence:
                raise SnarsPersistenceError(
                    "SNARS event sequence is corrupt.",
                    details={"expected": expected_sequence, "received": sequence},
                )
            expected_sequence += 1
            schema_version = int(row["schema_version"])
            if schema_version != SCHEMA_VERSION:
                raise SnarsPersistenceError(
                    "SNARS event schema version is unsupported.",
                    details={
                        "expected": SCHEMA_VERSION,
                        "received": schema_version,
                        "sequence": sequence,
                    },
                )
            commit = str(row["mettabase_commit"])
            if commit != self.mettabase_commit:
                raise SnarsPersistenceError(
                    "SNARS event was recorded against a different Mettabase commit.",
                    details={
                        "expected": self.mettabase_commit,
                        "received": commit,
                        "sequence": sequence,
                    },
                )
            canonical = str(row["payload_json"])
            expected_id = _event_id(sequence, str(row["kind"]), canonical, commit)
            if expected_id != row["event_id"]:
                raise SnarsPersistenceError(
                    "SNARS event content hash is invalid.",
                    details={"sequence": sequence},
                )
            try:
                payload = json.loads(canonical)
            except json.JSONDecodeError as exc:
                raise SnarsPersistenceError(
                    "SNARS event JSON is corrupt.",
                    details={"sequence": sequence, "error": str(exc)},
                ) from exc
            if not isinstance(payload, dict):
                raise SnarsPersistenceError(
                    "SNARS event payload must decode to an object.",
                    details={"sequence": sequence},
                )
            events.append(
                SnarsEvent(
                    sequence,
                    str(row["event_id"]),
                    str(row["kind"]),
                    payload,
                    commit,
                    schema_version,
                )
            )
        return tuple(events)

    def state_digest(self) -> str:
        digest = hashlib.sha256()
        for event in self.events():
            digest.update(f"{event.sequence}:{event.event_id}\n".encode())
        return digest.hexdigest()

    def close(self) -> None:
        try:
            self._connection.close()
        except sqlite3.Error as exc:
            raise SnarsPersistenceError(
                "Unable to close the SNARS event store.",
                details={"error": str(exc)},
            ) from exc

    def __enter__(self) -> SnarsEventStore:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                mettabase_commit TEXT NOT NULL,
                schema_version INTEGER NOT NULL
            );
            """
        )
        values = {
            "schema_version": str(SCHEMA_VERSION),
            "mettabase_commit": self.mettabase_commit,
        }
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            for key, value in values.items():
                existing = self._connection.execute(
                    "SELECT value FROM metadata WHERE key = ?",
                    (key,),
                ).fetchone()
                if existing is None:
                    self._connection.execute(
                        "INSERT INTO metadata (key, value) VALUES (?, ?)",
                        (key, value),
                    )
                elif existing["value"] != value:
                    raise SnarsPersistenceError(
                        "SNARS store metadata does not match this runtime.",
                        details={
                            "key": key,
                            "expected": value,
                            "received": existing["value"],
                        },
                    )
            self._connection.execute("COMMIT")
        except Exception:
            _rollback_quietly(self._connection)
            raise


def _safe_database_path(path: str | os.PathLike[str]) -> Path:
    raw = Path(path).expanduser()
    if raw.exists() and raw.is_symlink():
        raise SnarsPersistenceError(
            "SNARS database path must not be a symbolic link.",
            details={"path": str(raw)},
        )
    parent = raw.parent.resolve()
    if not parent.is_dir():
        raise SnarsPersistenceError(
            "SNARS database parent directory does not exist.",
            details={"path": str(parent)},
        )
    if parent.is_symlink():
        raise SnarsPersistenceError(
            "SNARS database parent directory must not be a symbolic link.",
            details={"path": str(parent)},
        )
    mode = parent.stat().st_mode
    world_writable = bool(mode & stat.S_IWOTH)
    sticky = bool(mode & stat.S_ISVTX)
    if world_writable and not sticky:
        raise SnarsPersistenceError(
            "SNARS database parent directory is world-writable without a sticky bit.",
            details={"path": str(parent)},
        )
    return (parent / raw.name).resolve()


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _event_id(
    sequence: int,
    kind: str,
    canonical_payload: str,
    commit: str,
) -> str:
    content = (
        f"{SCHEMA_VERSION}\0{commit}\0{sequence}\0{kind}\0{canonical_payload}"
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _rollback_quietly(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("ROLLBACK")
    except sqlite3.Error:
        pass


__all__ = [
    "Redactor",
    "SCHEMA_VERSION",
    "SnarsEvent",
    "SnarsEventStore",
]

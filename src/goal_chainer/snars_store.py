"""Purpose: persist native SNARS operations as an append-only event stream, event_store's private
SQLite file under the SNARS schema, version 3, whose identity is the SNARS library the events were
recorded against, and redact request text from ingestion events before they are kept."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .event_store import EventStore, StoreSchema, _canonical_json, _prepared, _text
from .snars_ingestion import ReadingFact
from .errors import PersistenceError
from .runtime.budget import RunBudget

# Version 2: an ingest_text event holds the semantic reader's gc-reading facts and its reader
# revision. A version-1 store's ingest events hold HyperBase facts, which nothing replays now, so
# such a store is refused as unsupported instead of replayed into a different state.
# Version 3: every event names the SNARS identity it was recorded against, snars_engine's digest of
# the packaged SNARS library and the Python its py-calls run, where version 2 named the commit of a
# Mettabase checkout. An older store is refused by its metadata when it opens, before any of its
# events is read.
# am[implements a-ev-jev-c-store@16b3f6] am[implements a-rt-snars-store-identity-1017@deb59d]
SCHEMA_VERSION = 3
# The SNARS store's rows, hashes and messages are event_store's under this schema, byte for byte the
# ones the store kept before the machinery moved there (c-store-golden-rows-1019).
# am[implements a-v2m-es-extract-1019@b610bc] am[related c-store-golden-rows-1019@010412]
SCHEMA = StoreSchema(
    label="SNARS",
    version=SCHEMA_VERSION,
    identity_key="snars_identity",
    identity_name="SNARS identity",
    identifies="SNARS library",
)
Redactor = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


# Request text survives an ingest_text event in two places: its text and the grounding passage of
# each reading fact, which quotes the text verbatim. This redactor replaces both and keeps every
# fact well formed, parsing and re-emitting it through ReadingFact, the facts' one grammar, so
# what is kept still replays and still gives the native decision every reading. An unknown
# reading's passage is empty and stays empty. Other events pass unchanged.
# Time: one parse and one emit per reading fact.
# am[implements a-ev-jev-c-store@16b3f6]
def text_redactor(codec: Any, replacement: str = "[redacted]") -> Redactor:
    """A redactor for SnarsSession.persistent that keeps no request text."""

    def redact(kind: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if kind != "ingest_text":
            return payload
        return {
            **payload,
            "text": replacement,
            "facts": [
                dataclasses.replace(fact, passage=replacement if fact.passage else "").emit(codec)
                for fact in (ReadingFact.parse(text, codec) for text in payload["facts"])
            ],
        }

    return redact


# am[implements a-rt-snars-store-identity-1017@deb59d]
@dataclass(frozen=True, slots=True)
class SnarsEvent:
    sequence: int
    event_id: str
    kind: str
    payload: Mapping[str, Any]
    snars_identity: str
    schema_version: int


# am[implements a-v2m-es-extract-1019@b610bc]
class SnarsEventStore(EventStore):
    """A private append-only event stream with deterministic read order."""

    event_type = SnarsEvent

    # The SNARS identity is checked before the path, as event_store checks every store's identity, so
    # a refused name makes nothing; a caller's budget bounds the open as EventStore's does, read
    # before the file is touched, and None leaves the store's own lock wait.
    # am[implements a-rt-snars-store-identity-1017@deb59d] am[implements a-integrate-store-boundaries-fix-1019@ebf493]
    # am[implements a-v2m-es-extract-1019@b610bc] am[implements a-v2rs-snars-budget-1020@5469ea]
    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        snars_identity: str,
        redactor: Redactor | None = None,
        budget: RunBudget | None = None,
    ) -> None:
        self.redactor = redactor
        super().__init__(path, schema=SCHEMA, identity=snars_identity, budget=budget)

    # am[implements a-rt-snars-store-identity-1017@deb59d] am[implements a-v2m-es-extract-1019@b610bc]
    @property
    def snars_identity(self) -> str:
        return self.identity

    # am[implements a-rt-snars-store-identity-1017@deb59d] am[implements a-v2rs-snars-budget-1020@5469ea]
    @classmethod
    def memory(
        cls,
        *,
        snars_identity: str,
        redactor: Redactor | None = None,
        budget: RunBudget | None = None,
    ) -> SnarsEventStore:
        return cls(
            None,
            snars_identity=snars_identity,
            redactor=redactor,
            budget=budget,
        )

    # am[related a-ev-outcome-evidence@69a360] am[implements a-v2rs-snars-budget-1020@5469ea]
    def append(self, kind: str, payload: Mapping[str, Any], *, budget: RunBudget | None = None) -> SnarsEvent:
        return self.append_prepared(kind, self.prepare_payload(kind, payload), budget=budget)

    # An event appended at most once by its content: keyed under its kind by the SHA-256 of its
    # canonical payload, so two sessions appending one event at once append it once, the second
    # answering None as an identical keyed append does, while a payload that differs anywhere has
    # its own key and is its own event. An identical event an earlier version recorded unkeyed holds
    # no key, so a session finds it by its payload before it appends (SnarsSession._has_event).
    # The key is the hash of the canonical text event_store's one guard answers, so an event that
    # guard refuses, a lone surrogate or a value JSON cannot hold, is refused as append_prepared
    # refuses it, before any key is made.
    # Time: one canonical encoding and one hash of the payload, then append_prepared's.
    # am[implements a-v2rs-snars-keyed-dedup-1020@85653f] am[addresses i-v2rs-snars-dedup-race-1020@f2b0b9]
    def append_once(
        self,
        kind: str,
        payload: Mapping[str, Any],
        *,
        budget: RunBudget | None = None,
    ) -> SnarsEvent | None:
        """Append a prepared event unless its identical payload is already recorded under its kind."""

        key = "sha256:" + hashlib.sha256(_prepared(kind, payload, None).encode("utf-8")).hexdigest()
        return self.append_prepared(kind, payload, key=key, budget=budget)

    # am[implements a-integrate-store-boundaries-fix-1019@ebf493]
    def prepare_payload(
        self,
        kind: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        _text(kind, "Event kind")
        if not isinstance(payload, Mapping):
            raise PersistenceError("Event payload must be a mapping.")
        try:
            visible = self.redactor(kind, payload) if self.redactor else payload
            canonical = _canonical_json(visible)
        except Exception as exc:
            raise PersistenceError(
                "Event redaction or JSON encoding failed.",
                details={"kind": kind, "error": str(exc)},
            ) from exc
        prepared = json.loads(canonical)
        if not isinstance(prepared, dict):
            raise PersistenceError("Prepared event payload must be an object.")
        return prepared


__all__ = [
    "Redactor",
    "SCHEMA",
    "SCHEMA_VERSION",
    "SnarsEvent",
    "SnarsEventStore",
    "text_redactor",
]

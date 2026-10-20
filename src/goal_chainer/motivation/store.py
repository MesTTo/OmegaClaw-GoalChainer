"""Purpose: keep a motivation stream, the need observations and host attempts a domain's needs are
read from, as keyed events in an event store of their own, each checked against the domain and the
shared vocabulary before any transaction and recorded once under its key, and read the stream back
in one consistent history whose kinds, keys and records replay verifies."""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self

from ..domains.loader import vocabulary
from ..domains.model import Domain, DomainError
from ..errors import InvalidInputError, PersistenceError, safe_repr
from ..event_store import Event, EventStore, StoreSchema, _text, digest
from ..relevance.canonical import fingerprint_of
from ..relevance.instants import parse_instant, utc_text
from ..runtime.budget import RunBudget

# A motivation stream's file is its own: its metadata names schema version 1 and the stream, so a
# SNARS store and any other stream are refused when it opens, and it refuses theirs
# (c-v2-store-stream-separation-1019).
# am[implements a-v2m-st-store-1019@670a6d] am[rests-on c-v2-store-stream-separation-1019@74fc02]
SCHEMA = StoreSchema(
    label="motivation",
    version=1,
    identity_key="stream",
    identity_name="motivation stream",
    identifies="motivation stream",
)
OBSERVATION_KIND = "need-observation"
ATTEMPT_KIND = "attempt"


# An observed level of one declared need on the scale it was read on, by an estimator class, from a
# source, at an instant, valid until an optional later instant, and produced by an optional attempt,
# which need not be recorded yet since feedback may arrive before its attempt. Its identity is every
# field, its times in UTC text, and its id that identity's fingerprint, the shape relevance's receipt
# observations have (c-v2m-st-receipt-prior-art-1019); the level and the scale are kept as floats
# with -0.0 made 0.0, so equal observations share one id (c-v2m-st-negative-zero-1019).
# am[implements a-v2m-st-records-1019@cd8ce5] am[rests-on c-v2m-st-receipt-prior-art-1019@762ee8]
# am[rests-on c-v2m-st-negative-zero-1019@7e0645]
@dataclass(frozen=True, slots=True)
class NeedObservation:
    """One reading of a need's level.

    It holds by construction what holds whatever the domain: nonempty UTF-8 text, a finite level
    within its own scale, a finite scale with its low end below its high end, timezone-aware times
    UTC can write, and validity that does not end before the observation; anything else is an
    InvalidInputError. Whether the domain declares the need on that scale, and whether the
    vocabulary has the estimator class, MotivationStore.observe checks as it records it.
    """

    need: str
    level: float
    scale: tuple[float, float]
    estimator: str
    source: str
    observed_at: datetime
    valid_until: datetime | None = None
    produced_by: str | None = None

    # am[implements a-v2m-st-records-1019@cd8ce5] am[rests-on c-v2m-st-instant-overflow-1019@16c656]
    def __post_init__(self) -> None:
        where = OBSERVATION_KIND
        _text(self.need, f"{where}.need", InvalidInputError)
        low, high = _scale(self.scale, f"{where}.scale")
        level = _number(self.level, f"{where}.level")
        if not low <= level <= high:
            raise InvalidInputError(
                f"{where}.level must lie within its scale.",
                details={"level": level, "scale": [low, high]},
            )
        _text(self.estimator, f"{where}.estimator", InvalidInputError)
        _text(self.source, f"{where}.source", InvalidInputError)
        _instant(self.observed_at, f"{where}.observed_at")
        if self.valid_until is not None:
            _instant(self.valid_until, f"{where}.valid_until")
            if self.valid_until < self.observed_at:
                raise InvalidInputError(
                    f"{where}.valid_until must not precede observed_at.",
                    details={"observed_at": utc_text(self.observed_at), "valid_until": utc_text(self.valid_until)},
                )
        if self.produced_by is not None:
            _text(self.produced_by, f"{where}.produced_by", InvalidInputError)
        object.__setattr__(self, "scale", (low, high))
        object.__setattr__(self, "level", level)

    # am[implements a-v2m-st-records-1019@cd8ce5]
    def identity(self) -> dict[str, object]:
        """Every field, as the stream stores it: times in UTC text and the scale as [low, high]."""

        return {
            "need": self.need,
            "level": self.level,
            "scale": list(self.scale),
            "estimator": self.estimator,
            "source": self.source,
            "observed_at": utc_text(self.observed_at),
            "valid_until": None if self.valid_until is None else utc_text(self.valid_until),
            "produced_by": self.produced_by,
        }

    # am[implements a-v2m-st-records-1019@cd8ce5]
    @property
    def id(self) -> str:
        """The fingerprint of the identity, which keys the observation in its stream."""

        return fingerprint_of(self.identity())


# One application, or a decided non-application, of a declared action by the host: the attempt id
# names the application, as a receipt's attempt does, applied_at is None when nothing was applied,
# and review_fingerprint optionally names the decision it applied.
# am[implements a-v2m-st-records-1019@cd8ce5] am[rests-on c-v2m-st-receipt-prior-art-1019@762ee8]
@dataclass(frozen=True, slots=True)
class Attempt:
    """One host attempt, keyed in its stream by its attempt id.

    It holds by construction nonempty UTF-8 ids and a timezone-aware applied_at UTC can write when
    there is one; anything else is an InvalidInputError. Whether the domain declares the action,
    MotivationStore.attempt checks as it records it.
    """

    attempt: str
    action: str
    applied_at: datetime | None
    review_fingerprint: str | None = None

    # am[implements a-v2m-st-records-1019@cd8ce5]
    def __post_init__(self) -> None:
        where = ATTEMPT_KIND
        _text(self.attempt, f"{where}.attempt", InvalidInputError)
        _text(self.action, f"{where}.action", InvalidInputError)
        if self.applied_at is not None:
            _instant(self.applied_at, f"{where}.applied_at")
        if self.review_fingerprint is not None:
            _text(self.review_fingerprint, f"{where}.review_fingerprint", InvalidInputError)

    # am[implements a-v2m-st-records-1019@cd8ce5]
    def identity(self) -> dict[str, object]:
        """Every field, as the stream stores it, applied_at in UTC text or None."""

        return {
            "attempt": self.attempt,
            "action": self.action,
            "applied_at": None if self.applied_at is None else utc_text(self.applied_at),
            "review_fingerprint": self.review_fingerprint,
        }


# What one read of a stream holds: its observations and its attempts, each in the order they were
# recorded, and the digest of exactly the events read, so a decision made from them names the state
# it saw (c-v2m-st-split-reads-1019).
# am[implements a-v2m-st-store-1019@670a6d] am[rests-on c-v2m-st-split-reads-1019@b1d1ca]
@dataclass(frozen=True, slots=True)
class MotivationHistory:
    observations: tuple[NeedObservation, ...]
    attempts: tuple[Attempt, ...]
    digest: str


class MotivationStore:
    """A motivation stream in its own private SQLite file, or in memory without a path.

        with MotivationStore("motivation.sqlite3", stream="incident-host") as store:
            store.observe(domain, NeedObservation(...))     # True: recorded
            store.observe(domain, NeedObservation(...))     # False: already recorded
            store.record(domain, observations=(...), attempts=(...), budget=budget)   # all or nothing
            history = store.history()

    record, observe and attempt refuse with InvalidInputError, before any transaction, what the
    domain or the vocabulary does not declare; a different payload under a recorded key is a
    PersistenceError. With create=False the store opens only a stream already at the path,
    refusing with PersistenceError a path holding none and creating nothing, for a read.
    """

    # am[implements a-v2m-st-store-1019@670a6d] am[implements a-v2m-st-read-refuses-1020@676ded]
    # am[implements a-v2m-st-open-budget-1020@874189] am[rests-on c-v2m-st-open-surface-1020@322f6f]
    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        stream: str,
        create: bool = True,
        budget: RunBudget | None = None,
    ) -> None:
        self._events = EventStore(
            path, schema=SCHEMA, identity=stream, create=create, budget=_optional_budget(budget, "The store's budget")
        )

    # am[implements a-v2m-st-store-1019@670a6d]
    @classmethod
    def memory(cls, *, stream: str) -> MotivationStore:
        return cls(None, stream=stream)

    # am[implements a-v2m-st-store-1019@670a6d]
    @property
    def stream(self) -> str:
        return self._events.identity

    # Every record is checked against the domain and the vocabulary before the one transaction that
    # appends them all, so a batch is recorded whole or not at all: a record the domain does not
    # declare refuses the batch before anything is written, and a different payload under any
    # recorded key rolls the whole batch back (c-v2m-st-batch-surface-1019). A caller's budget bounds
    # the batch as append_batch says: an exhausted one writes nothing, the write lock is waited for
    # no longer than its deadline, and one exhausted before COMMIT rolls the batch back.
    # am[implements a-v2m-st-batch-1019@a8d5f5] am[implements a-v2m-st-store-1019@670a6d]
    # am[rests-on c-v2m-st-batch-surface-1019@14cf84] am[rests-on c-v2m-st-replay-context-free-1019@6a4ba4]
    # am[implements a-v2m-st-deadline-1020@64df73] am[rests-on c-v2m-st-deadline-design-1020@97fda9]
    def record(
        self,
        domain: Domain,
        observations: Iterable[NeedObservation] = (),
        attempts: Iterable[Attempt] = (),
        *,
        budget: RunBudget | None = None,
    ) -> tuple[tuple[str, bool], ...]:
        """Record observations, keyed by id, and attempts, keyed by attempt id, as one transaction:
        (key, appended) for each observation in order and then each attempt in order, appended
        False for a record its key already held, an earlier one in the batch included. With a
        budget, the batch commits only within its deadline and raises its exhaustion otherwise."""

        observations, attempts = check_records(domain, observations, attempts)
        budget = _optional_budget(budget, "record's budget")
        events = [
            *((OBSERVATION_KIND, observation.identity(), observation.id) for observation in observations),
            *((ATTEMPT_KIND, attempt.identity(), attempt.attempt) for attempt in attempts),
        ]
        appended = self._events.append_batch(events, budget=budget)
        return tuple((key, event is not None) for (_, _, key), event in zip(events, appended, strict=True))

    # am[implements a-v2m-st-store-1019@670a6d] am[implements a-v2m-st-batch-1019@a8d5f5]
    def observe(self, domain: Domain, observation: NeedObservation) -> bool:
        """Record an observation once under its id: True when it was appended, False when it was
        already recorded."""

        return self.record(domain, observations=(observation,))[0][1]

    # am[implements a-v2m-st-store-1019@670a6d] am[implements a-v2m-st-batch-1019@a8d5f5]
    def attempt(self, domain: Domain, attempt: Attempt) -> bool:
        """Record an attempt once under its attempt id: True when it was appended, False when the
        same attempt was already recorded; a different one under its id is a PersistenceError."""

        return self.record(domain, attempts=(attempt,))[0][1]

    # Every event is read in one statement, and each must be an observation or an attempt whose
    # payload is its record's identity and whose key is the one that record derives, so a history
    # never holds two observations or two attempts under one id. The key table is read after the
    # events, which is sound since a key is written with its event and never removed. Events are
    # only appended, numbered 1..N, so the first N events read today are the N an earlier read
    # returned, whatever was appended since: a history `through` an earlier read's event count is
    # that read's history, and its digest commits to the same events (c-v2r-store-prefix-immutable-1020).
    # Zero is the empty prefix. `through` reads events 1 to N and their keys alone, so an audit of an
    # old prefix costs that prefix however long the stream has grown (a-v2r-prefix-read-1020). A
    # caller's budget bounds both reads as EventStore.events and event_keys say and is read again
    # before each event is replayed and once after the history and its digest are built, so a long
    # history raises the budget's own exhaustion within one event's work of its deadline and an
    # overrun in the last replay or in hashing the events cannot answer success.
    # Time: one read of the n events read, n the stream's length or `through`, and of their k keys,
    # one parse, one fingerprint and one budget read per event.
    # am[implements a-v2m-st-store-1019@670a6d] am[rests-on c-v2m-st-split-reads-1019@b1d1ca]
    # am[rests-on c-v2m-st-replay-context-free-1019@6a4ba4]
    # am[implements a-v2r-history-prefix-1020] am[related a-v2r-prefix-read-1020]
    # am[addresses i-v2rs-history-unbudgeted-1020] am[related a-v2rs-events-budget-1020]
    def history(self, through: int | None = None, *, budget: RunBudget | None = None) -> MotivationHistory:
        """The stream's observations and attempts in the order recorded, and the digest of that read;
        with `through`, those of its first `through` events only. InvalidInputError, before the
        read, for a `through` that is a bool, not an integer or negative; PersistenceError for one
        beyond the events the stream holds; with a budget, its exhaustion once the deadline passes."""

        if through is not None and (isinstance(through, bool) or not isinstance(through, int) or through < 0):
            raise InvalidInputError("history's through must be a nonnegative integer count of events.",
                                    details={"through": safe_repr(through)})
        budget = _optional_budget(budget, "history's budget")
        events = self._events.events(through=through, budget=budget)
        if through is not None and through > len(events):
            raise PersistenceError(
                "Motivation stream holds fewer events than the prefix asked for.",
                details={"through": through, "events": len(events)},
            )
        keys = self._events.event_keys(through=through, budget=budget)
        observations: list[NeedObservation] = []
        attempts: list[Attempt] = []
        for event in events:
            if budget is not None:
                budget.remaining()
            record = _replayed(event)
            key = (event.kind, record.id if isinstance(record, NeedObservation) else record.attempt)
            if keys.get(event.sequence) != key:
                raise PersistenceError(
                    "Motivation event is not recorded under the key its payload derives.",
                    details={
                        "sequence": event.sequence,
                        "expected": list(key),
                        "received": None if event.sequence not in keys else list(keys[event.sequence]),
                    },
                )
            (observations if isinstance(record, NeedObservation) else attempts).append(record)
        history = MotivationHistory(tuple(observations), tuple(attempts), digest(events))
        if budget is not None:
            budget.remaining()
        return history

    # am[implements a-v2m-st-store-1019@670a6d]
    def close(self) -> None:
        self._events.close()

    # am[implements a-v2m-st-store-1019@670a6d]
    def __enter__(self) -> Self:
        return self

    # am[implements a-v2m-st-store-1019@670a6d]
    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


# A caller's budget, or None for none; anything else is refused as input before any store is touched.
# am[implements a-v2m-st-deadline-1020@64df73] am[implements a-v2m-st-open-budget-1020@874189]
def _optional_budget(budget: object, name: str) -> RunBudget | None:
    if budget is not None and not isinstance(budget, RunBudget):
        raise InvalidInputError(f"{name} must be a RunBudget or None.", details={"budget": safe_repr(budget)})
    return budget


# The one home of the checks a batch must pass before a stream is touched: every record is one the
# domain and the vocabulary declare. record runs it first, and a caller may run it before it opens a
# store at all, so a refused record creates no store file (c-v2m-st-check-records-1020).
# Time: one domain lookup per record and one vocabulary scan per observation.
# am[implements a-v2m-st-check-first-1020@d9378b] am[rests-on c-v2m-st-check-records-1020@2be56e]
# am[rests-on c-v2m-st-replay-context-free-1019@6a4ba4]
def check_records(
    domain: Domain,
    observations: Iterable[NeedObservation] = (),
    attempts: Iterable[Attempt] = (),
) -> tuple[tuple[NeedObservation, ...], tuple[Attempt, ...]]:
    """The observations and the attempts as tuples, once every one is a record the domain and the
    vocabulary declare; the InvalidInputError record raises for the first that is not."""

    try:
        observations, attempts = tuple(observations), tuple(attempts)
    except TypeError as error:
        raise InvalidInputError("Observations and attempts must be sequences of records.") from error
    for observation in observations:
        _check_observation(domain, observation)
    for attempt in attempts:
        _check_attempt(domain, attempt)
    return observations, attempts


_OBSERVATION_FIELDS = (frozenset({"need", "level", "scale", "estimator", "source", "observed_at"}),
                       frozenset({"valid_until", "produced_by"}))
_ATTEMPT_FIELDS = (frozenset({"attempt", "action", "applied_at"}), frozenset({"review_fingerprint"}))


# The JSON shape of an observation, as a host sends it and the stream stores it: an object with
# exactly the record's fields, the optional valid_until and produced_by absent or null, and times in
# ISO-8601 with an offset, exact to the microsecond. Any fault is an InvalidInputError.
# am[implements a-v2m-st-records-1019@cd8ce5] am[rests-on c-v2m-st-receipt-prior-art-1019@762ee8]
def parse_observation(payload: Any) -> NeedObservation:
    """The need observation a JSON object states."""

    _fields(payload, OBSERVATION_KIND, *_OBSERVATION_FIELDS)
    where = OBSERVATION_KIND
    return NeedObservation(
        need=payload["need"],
        level=payload["level"],
        scale=payload["scale"],
        estimator=payload["estimator"],
        source=payload["source"],
        observed_at=_time(payload["observed_at"], f"{where}.observed_at"),
        valid_until=None if payload.get("valid_until") is None else _time(payload["valid_until"], f"{where}.valid_until"),
        produced_by=payload.get("produced_by"),
    )


# The JSON shape of an attempt: an object with exactly the record's fields, applied_at present and
# null when nothing was applied, as a receipt's is, and review_fingerprint absent or null when none
# is named. Any fault is an InvalidInputError.
# am[implements a-v2m-st-records-1019@cd8ce5] am[rests-on c-v2m-st-receipt-prior-art-1019@762ee8]
def parse_attempt(payload: Any) -> Attempt:
    """The attempt a JSON object states."""

    _fields(payload, ATTEMPT_KIND, *_ATTEMPT_FIELDS)
    return Attempt(
        attempt=payload["attempt"],
        action=payload["action"],
        applied_at=None if payload["applied_at"] is None else _time(payload["applied_at"], f"{ATTEMPT_KIND}.applied_at"),
        review_fingerprint=payload.get("review_fingerprint"),
    )


_PARSERS: dict[str, Callable[[Any], NeedObservation | Attempt]] = {
    OBSERVATION_KIND: parse_observation,
    ATTEMPT_KIND: parse_attempt,
}


# What check_records checks of each observation, before any store is touched: the need is one the
# domain declares, on the scale it declares, and the estimator is a vocabulary class.
# Replay does not repeat these, so a later domain or vocabulary leaves what was recorded readable
# (c-v2m-st-replay-context-free-1019).
# am[implements a-v2m-st-store-1019@670a6d] am[rests-on c-v2m-st-replay-context-free-1019@6a4ba4]
# am[implements a-v2m-st-check-first-1020@d9378b]
def _check_observation(domain: Domain, observation: NeedObservation) -> None:
    if not isinstance(observation, NeedObservation):
        raise InvalidInputError("An observation must be a NeedObservation.", details={"value": safe_repr(observation)})
    try:
        need = domain.need(observation.need)
    except DomainError as error:
        raise InvalidInputError(
            f"{OBSERVATION_KIND}.need names no need the domain declares.",
            details={"need": observation.need, "declared": list(domain.need_ids)},
        ) from error
    if observation.scale != need.scale:
        raise InvalidInputError(
            f"{OBSERVATION_KIND}.scale must be the scale the domain declares for its need.",
            details={"need": need.id, "declared": list(need.scale), "received": list(observation.scale)},
        )
    classes = vocabulary().classes
    if observation.estimator not in classes:
        raise InvalidInputError(
            f"{OBSERVATION_KIND}.estimator must be one of {', '.join(classes)}.",
            details={"estimator": observation.estimator},
        )


# What check_records checks of each attempt, before any store is touched: the action is one the
# domain declares.
# am[implements a-v2m-st-store-1019@670a6d] am[rests-on c-v2m-st-replay-context-free-1019@6a4ba4]
# am[implements a-v2m-st-check-first-1020@d9378b]
def _check_attempt(domain: Domain, attempt: Attempt) -> None:
    if not isinstance(attempt, Attempt):
        raise InvalidInputError("An attempt must be an Attempt.", details={"value": safe_repr(attempt)})
    if attempt.action not in domain.action_ids:
        raise InvalidInputError(
            f"{ATTEMPT_KIND}.action names no action the domain declares.",
            details={"action": attempt.action, "declared": list(domain.action_ids)},
        )


# A stored event read back as its record: its kind must be one of the stream's and its payload
# exactly the identity of the record it parses to, so the stream holds each record in one form.
# Any fault is the file's, a PersistenceError.
# am[implements a-v2m-st-store-1019@670a6d]
def _replayed(event: Event) -> NeedObservation | Attempt:
    parse = _PARSERS.get(event.kind)
    if parse is None:
        raise PersistenceError(
            "Motivation event kind is unknown.",
            details={"sequence": event.sequence, "kind": event.kind},
        )
    try:
        record = parse(event.payload)
    except InvalidInputError as error:
        raise PersistenceError(
            "Motivation event payload is not a valid record.",
            details={"sequence": event.sequence, "kind": event.kind, "error": error.message},
        ) from error
    if record.identity() != event.payload:
        raise PersistenceError(
            "Motivation event payload is not its record's identity.",
            details={"sequence": event.sequence, "kind": event.kind},
        )
    return record


# An object holding exactly a record's required fields and any of its optional ones.
# am[implements a-v2m-st-records-1019@cd8ce5]
def _fields(payload: Any, where: str, required: frozenset[str], optional: frozenset[str]) -> None:
    if not isinstance(payload, Mapping):
        raise InvalidInputError(f"{where} must be an object.", details={"value": safe_repr(payload)})
    unknown = sorted(str(name) for name in payload if name not in required | optional)
    missing = sorted(required - set(payload))
    if unknown or missing:
        raise InvalidInputError(
            f"{where} fields: unknown {unknown}, missing {missing}.",
            details={"unknown": unknown, "missing": missing},
        )


# A finite number, never a boolean, as a float with -0.0 made 0.0 (c-v2m-st-negative-zero-1019);
# an integer too large for a float is refused as no finite number.
# am[implements a-v2m-st-records-1019@cd8ce5] am[rests-on c-v2m-st-negative-zero-1019@7e0645]
def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidInputError(f"{name} must be a number.", details={"value": safe_repr(value)})
    try:
        number = float(value)
    except OverflowError:
        number = math.inf
    if not math.isfinite(number):
        raise InvalidInputError(f"{name} must be a finite number.", details={"value": safe_repr(value)})
    return number + 0.0


# A scale as a pair of finite numbers, its low end below its high end, as a declared need's is.
# am[implements a-v2m-st-records-1019@cd8ce5]
def _scale(value: object, name: str) -> tuple[float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise InvalidInputError(f"{name} must be a pair of numbers [low, high].", details={"value": safe_repr(value)})
    low, high = (_number(bound, f"{name}[{index}]") for index, bound in enumerate(value))
    if not low < high:
        raise InvalidInputError(f"{name} must have its low end below its high end.", details={"scale": [low, high]})
    return low, high


# A timezone-aware datetime whose instant UTC text can write: one before year 1 in UTC raises
# OverflowError there (c-v2m-st-instant-overflow-1019).
# am[implements a-v2m-st-records-1019@cd8ce5] am[rests-on c-v2m-st-instant-overflow-1019@16c656]
def _instant(value: object, name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise InvalidInputError(f"{name} must be a timezone-aware datetime.", details={"value": safe_repr(value)})
    try:
        utc_text(value)
    except OverflowError as error:
        raise InvalidInputError(f"{name} must be an instant UTC can write.", details={"value": safe_repr(value)}) from error


# A time from JSON text, read as relevance reads every instant.
# am[implements a-v2m-st-records-1019@cd8ce5]
def _time(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise InvalidInputError(f"{name} must be ISO-8601 text with an offset.", details={"value": safe_repr(value)})
    try:
        return parse_instant(value)
    except ValueError as error:
        raise InvalidInputError(f"{name} {error}.", details={"value": safe_repr(value)}) from error


__all__ = [
    "ATTEMPT_KIND",
    "Attempt",
    "MotivationHistory",
    "MotivationStore",
    "NeedObservation",
    "OBSERVATION_KIND",
    "SCHEMA",
    "check_records",
    "parse_attempt",
    "parse_observation",
]

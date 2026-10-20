"""Purpose: answer a JSON motivation request for an explicitly selected domain and motivation stream,
under the caller's one RunBudget: record need observations or host attempts in the stream, or
report the stream's motivation snapshot at an instant; and give a domain request the snapshot it
reviews by.

    {"operation": "observe", "domain": {"path": ...} | {"packaged": ...},
     "motivation": {"store": PATH, "stream": ID},
     "observations": [{"need", "level", "scale", "estimator", "source", "observed_at",
                       "valid_until"?, "produced_by"?}, ...]}
    {"operation": "attempt", ..., "attempts": [{"attempt", "action", "applied_at", "review_fingerprint"?}, ...]}
    {"operation": "status", ..., "as_of": TIME, "through"?: COUNT}

observe and attempt read every record through the store's own JSON readers, check each against the
domain with the store's check_records, and read the budget, all before the store is opened, so a
request refused by its shape, its domain, a record or its budget creates and writes nothing. The
store opens under the same budget, an existing one with no write lock and a new one waiting for
its lock no longer than the deadline, and MotivationStore.record writes the whole list in one
transaction, whose wait for the write lock also ends by the deadline and which reads the budget
again before it commits: a batch is written whole or not at all, and every wait for the store's
lock ends when the request's deadline passes, to the millisecond SQLite's busy timeout counts in.
Once the batch commits, the request answers each record's key as recorded or already_recorded and
raises nothing more: a caller whose envelope
reports exhaustion afterwards, or who never saw the answer, sends the same batch again, and the keys
it then answers already_recorded are the ones that committed. status and a domain request's
motivation field read a stream only where one is: a store path holding none is refused and nothing
is created, so a host reviews before its first record by leaving the field out.

status reads the whole stream, as reviews and freshness checks do; with `through` it reads only the
stream's first COUNT events, the prefix a review's motivation.history names by its event_count, so
it answers that review's full snapshot, its samples included, at the review's as_of however much has
been appended since, backdated observations among it, and the answer's history digest is a SHA-256
commitment to the events it read. The read costs that prefix, not the stream, and runs under the
request's budget event by event. COUNT is a JSON integer of at least 0, 0 being the empty prefix;
one beyond the stream is the store's PersistenceError.

Nothing here applies an action or records one on the host's behalf: an attempt is the host's
statement that it applied, or declined, an action, and an observation its statement of what it then
saw; a review's predicted level changes are never written back as observations.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ..domains.model import Domain
from ..errors import InvalidInputError, safe_repr
from ..relevance.instants import parse_instant
from ..relevance.motivation import MotivationSnapshot, motivation_snapshot
from ..runtime.budget import RunBudget, caller_budget
from .store import MotivationStore, check_records, parse_attempt, parse_observation

MOTIVATION_REQUEST_PROTOCOL = "goalchainer-motivation-request-v1"

# Each operation's required fields, and the optional ones status takes.
# am[implements a-v2m-request-cycle-1019@abb37d] am[implements a-v2r-history-prefix-1020]
_FIELDS = {
    "observe": {"operation", "domain", "motivation", "observations"},
    "attempt": {"operation", "domain", "motivation", "attempts"},
    "status": {"operation", "domain", "motivation", "as_of"},
}
_OPTIONAL = {"observe": set(), "attempt": set(), "status": {"through"}}


# Time: the domain read, one parse per record, and one batch append or, for status, one store read
# and one snapshot policy call, each charged to `budget`.
# am[implements a-v2m-request-cycle-1019@abb37d] am[rests-on c-gc-v2-authority-boundary-1019@5d2caf]
# am[related c-v2m-st-open-surface-1020@322f6f]
# am[implements a-v2-motivation-input-order-1020@d40cf5]
def run_motivation_request(payload: object, *, budget: RunBudget) -> dict[str, Any]:
    """Record observations or attempts in the stream, or report its snapshot, for the selected
    domain; InvalidInputError for a malformed request or a record the domain does not declare,
    BudgetExhausted for a budget spent before the batch commits, PersistenceError for a store
    refusal, a status read of a path holding no store included."""

    budget = caller_budget(budget, "a motivation request")
    budget.remaining()
    before = budget.spent
    request = _object(payload, "request")
    operation = request.get("operation")
    if not isinstance(operation, str) or operation not in _FIELDS:
        raise InvalidInputError("operation must be observe, attempt or status.")
    missing, unknown = _FIELDS[operation] - request.keys(), request.keys() - _FIELDS[operation] - _OPTIONAL[operation]
    if missing or unknown:
        raise InvalidInputError("Invalid fields in request.", details={"missing": sorted(missing), "unknown": sorted(unknown)})
    path, stream = stream_selection(request["motivation"])
    through = _count(request["through"], "through") if "through" in request else None
    domain = _regulating(_domain(request["domain"], budget))
    result: dict[str, Any] = {"protocol": MOTIVATION_REQUEST_PROTOCOL, "operation": operation, "stream": stream}
    if operation == "status":
        as_of = _instant(request["as_of"], "as_of")
        result["snapshot"] = stream_snapshot(request["motivation"], domain, as_of=as_of, budget=budget,
                                             through=through).to_dict()
    else:
        field = "observations" if operation == "observe" else "attempts"
        listed = request[field]
        if not isinstance(listed, list):
            raise InvalidInputError(f"{field} must be a JSON list of records.")
        records = tuple(parse_observation(item) if operation == "observe" else parse_attempt(item) for item in listed)
        # Every record is checked against the domain, and the budget read once the domain load has
        # spent part of it, before the store is opened; an empty list has nothing to write, so it
        # opens no store either and answers two empty lists.
        check_records(domain, **{field: records})
        budget.remaining()
        answered: tuple[tuple[str, bool], ...] = ()
        if records:
            with MotivationStore(path, stream=stream, budget=budget) as store:
                answered = store.record(domain, **{field: records}, budget=budget)
        result["recorded"] = [key for key, appended in answered if appended]
        result["already_recorded"] = [key for key, appended in answered if not appended]
    result["inferences"] = budget.spent - before
    return result


# The snapshot a domain request reviews by: the named stream's history at the packet's instant, read
# under the budget, which bounds the store's open, its read and every event's replay, and only from a
# store already at the path; with `through`, its first events only, as a status audit of an earlier
# review reads them.
# am[implements a-v2m-request-cycle-1019@abb37d] am[implements a-v2m-snapshot-identity-1019@118a4b]
# am[related a-v2m-st-read-refuses-1020@676ded] am[implements a-v2r-history-prefix-1020]
# am[addresses i-v2rs-history-unbudgeted-1020]
def stream_snapshot(value: object, domain: Domain, *, as_of: datetime, budget: RunBudget,
                    through: int | None = None) -> MotivationSnapshot:
    """The snapshot of the stream `value` selects ({"store": PATH, "stream": ID}) at `as_of`, of its
    first `through` events when that is given."""

    path, stream = stream_selection(value)
    _regulating(domain)
    budget.remaining()
    with MotivationStore(path, stream=stream, create=False, budget=budget) as store:
        return motivation_snapshot(domain, store.history(through=through, budget=budget), stream=store.stream,
                                   as_of=as_of, budget=budget)


# A count of events as a request gives it: a JSON integer, never a boolean or null, of at least 0,
# refused before any domain or store work; a request that wants none leaves the field out.
# am[implements a-v2r-history-prefix-1020]
def _count(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidInputError(f"{where} must be an integer of at least 0.", details={where: safe_repr(value)})
    return value


# A motivation stream as a request names it: an object with exactly a store path and a stream id,
# both nonempty UTF-8 text, refused before domain or hosted reading work.
# am[implements a-v2m-request-cycle-1019@abb37d]
# am[implements a-v2-motivation-input-order-1020@d40cf5]
def stream_selection(value: object) -> tuple[str, str]:
    selection = _object(value, "motivation")
    if set(selection) != {"store", "stream"}:
        raise InvalidInputError("motivation must name exactly a store and a stream.",
                                details={"fields": sorted(selection)})
    return _text(selection["store"], "motivation.store"), _text(selection["stream"], "motivation.stream")


# Only a domain that declares needs has a motivation stream: its records name its needs and actions.
# am[implements a-v2m-request-cycle-1019@abb37d]
def _regulating(domain: Domain) -> Domain:
    if not domain.needs:
        raise InvalidInputError(f"{domain.source} declares no needs, so it has no motivation stream.")
    return domain


# The domain request's own selection and loading, so every request reads a domain one way.
# am[implements a-v2m-request-cycle-1019@abb37d] am[related a-ie-sr-select-domain-1018@577734]
def _domain(value: object, budget: RunBudget) -> Domain:
    from ..requests import domain_for  # noqa: PLC0415 (requests.py reads this module for its motivation field)

    return domain_for(value, budget)


# am[implements a-v2m-request-cycle-1019@abb37d]
def _instant(value: object, where: str) -> datetime:
    try:
        return parse_instant(_text(value, where))
    except ValueError as error:
        raise InvalidInputError(f"Invalid {where}: {error}") from error


# am[implements a-v2m-request-cycle-1019@abb37d]
def _object(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise InvalidInputError(f"{where} must be a JSON object with text keys.")
    return value


# am[implements a-v2m-request-cycle-1019@abb37d]
# am[implements a-v2-motivation-input-order-1020@d40cf5]
def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"{where} must be nonempty text.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise InvalidInputError(f"{where} must be UTF-8 text.") from error
    return value

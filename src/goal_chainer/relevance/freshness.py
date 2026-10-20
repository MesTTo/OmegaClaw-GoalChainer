"""Purpose: decide whether an earlier review record still has the support it was decided on, without running the theory again.

A review record carries its readset: every signal whose reading could change its outcome,
including what removed the rivals, with a snapshot of the effective reading and the identity
of the observations behind it. A host checks freshness before acting on a stored proposal
(paper sections 8.5 and 10.5): it compiles the current packet and asks whether anything the
review rested on moved.

    fresh   the domain digest, the review policy's digest, the engine identity, the review's
            authority rung, every readset reading and, for a domain with needs, the motivation
            snapshot's identity at the current packet's as_of are exactly as they were, so the
            same review would reach the same result from the same evidence;
    stale   one of them changed.

This module finds what moved; `policy/outcome.metta` decides what follows, and stale is not
refuted there: the earlier result has lost the grounds it was decided on and needs a new review,
and it says nothing about which alternative is right. A reading that expired, or a definite
reading replaced by an observation from another source or with another validity window,
changes the snapshot even when the state reads the same, because support is the observation and
not its boolean. Notes are not part of a snapshot. The same holds for the motivation snapshot: a
new observation of a need or a new sample of a change stales the review even when the level or
the mean it gives is unchanged, since the support moved (c-v2-motivation-freshness-obligation-1019).
The current readings come from the evidence policy, charged to the packet's own budget, whose
deadline starts when the check is called and covers any preparation the process still needs.

Only a record of the current review protocol is compared; a version-1 record, written before the
motivation snapshot existed, is refused as an invalid-record naming its protocol, never reported
stale, so a host reviews again (c-v2m-v1-refused-1019).

A review that ranked by a named motivation stream is compared only with that stream's snapshot:
checked without one, or with another stream's, it is refused as invalid-motivation rather than
called stale, since nothing it rested on was compared. A review that ranked by no stream is
compared with an empty unnamed stream's snapshot when none is given; checked against a named
stream's snapshot it goes stale, even when that stream holds nothing, since the snapshot's identity
names its stream (i-v2r-freshness-empty-stream-doc-1020).

A review is about one subject, the task or plan under review, so a packet for another subject
cannot make it fresh or stale: the comparison is refused with `subject-mismatch`. The review id
and trigger only label the review and are not compared.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, get_args, get_type_hints

from ..domains.model import Domain
from ..runtime.budget import BudgetExhausted, RunBudget
from .derived import ENGINE_IDENTITY_FIELDS
from .errors import RelevanceError
from .motivation import MotivationSnapshot, motivation_snapshot
from .packet import ReviewPacket
from .policy import evaluate, prepare, stopped, symbol, term, text
from .records import ANY_KEY, OPTIONAL_TEXT, check_record
from .review import REVIEW_PROTOCOL
from .signals import OBSERVATION_IDENTITY, SignalReading, effective_readings

FRESHNESS_PROTOCOL = "goalchainer-relevance-freshness-v1"

# An observation identity as a record carries it: text, or nothing where the reading's own field
# may be absent.
_IDENTITY = {
    name: OPTIONAL_TEXT if type(None) in get_args(get_type_hints(SignalReading)[name]) else str
    for name in OBSERVATION_IDENTITY
}
# Every field of a review record the freshness check reads.
_RECORD_SHAPE = {
    "protocol": str,
    "review_id": str,
    "subject": str,
    "fingerprint": str,
    "review_authority": str,
    "domain": {"digest": str},
    "review_policy": {"digest": str},
    "engine": {name: str for name in ENGINE_IDENTITY_FIELDS},
    "readset": {"snapshot": {ANY_KEY: {"state": str, "support": [_IDENTITY]}}},
    "readings": [{"signal": str, "support": [_IDENTITY]}],
    "candidates": [{"action": str}],
}


# am[implements a-rel-review-contract-1016@d0bea9] am[rests-on c-integrate-agenticmind-support-1016@b60619]
@dataclass(frozen=True)
class FreshnessReport:
    review_id: str
    fingerprint: str
    changes: tuple[dict[str, object], ...]
    ignored_changes: tuple[str, ...]
    policy_changed: bool
    review_policy_changed: bool
    engine_changed: bool
    authority_changed: bool
    status: str
    support: str
    motivation_changed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol": FRESHNESS_PROTOCOL,
            "review_id": self.review_id,
            "fingerprint": self.fingerprint,
            "status": self.status,
            "support": self.support,
            "changes": list(self.changes),
            "ignored_changes": list(self.ignored_changes),
            "policy_changed": self.policy_changed,
            "review_policy_changed": self.review_policy_changed,
            "engine_changed": self.engine_changed,
            "authority_changed": self.authority_changed,
            "motivation_changed": self.motivation_changed,
            "implies_alternative": False,
        }


# Time: s for the s declared signals, plus the evidence policy's s * r comparisons over r readings.
# am[implements a-rel-review-contract-1016@d0bea9] am[rests-on c-integrate-agenticmind-support-1016@b60619]
# am[implements a-integrate-domain-review-budget-1018@a84bf4] am[implements a-v2m-snapshot-identity-1019@118a4b]
def check_freshness(
    prior: Mapping[str, Any],
    domain: Domain,
    packet: ReviewPacket,
    engine: Mapping[str, str | None],
    *,
    budget: RunBudget,
    motivation: MotivationSnapshot | None = None,
) -> FreshnessReport:
    """Compare a stored review record with the current packet, domain and engine identity.

    `ignored_changes` lists signals whose reading moved outside the readset; they are reported
    so a reader can see the check looked, and they leave the review fresh. The check runs under
    the caller's budget, which must have no more left than the packet declares. For a domain
    with needs, `motivation` is the stream's snapshot at the packet's as_of, as a review takes it,
    and an empty stream's when it is None.
    """

    try:
        budget = packet.budget.admit(budget, "a relevance freshness check")
    except BudgetExhausted as error:
        raise stopped(error) from error
    record = check_record(prior, _RECORD_SHAPE, "review record")
    if record["protocol"] != REVIEW_PROTOCOL:
        raise RelevanceError("invalid-record", f"a freshness check needs a {REVIEW_PROTOCOL} record")
    if record["subject"] != packet.subject:
        raise RelevanceError(
            "subject-mismatch",
            f"review {record['review_id']} is about {record['subject']}, the packet about {packet.subject}",
            details={"review": record["subject"], "packet": packet.subject},
        )
    packet.check_against(domain)
    policy_digest = prepare(budget)
    current = effective_readings(packet.readings, domain.signal_ids, packet.as_of, budget=budget)
    snapshot: Mapping[str, Any] = record["readset"]["snapshot"]
    changes = []
    for name in sorted(snapshot):
        now = current[name].snapshot() if name in current else {"state": "undeclared", "support": []}
        if now != snapshot[name]:
            changes.append({"signal": name, "was": snapshot[name], "now": now})
    prior_readings = {item["signal"]: item for item in record["readings"]}
    ignored = tuple(
        name
        for name in sorted(current)
        if name not in snapshot
        and name in prior_readings
        and _definite_identities(prior_readings[name]) != current[name].snapshot()["support"]
    )
    prior_engine = {key: record["engine"][key] for key in ENGINE_IDENTITY_FIELDS}
    policy_changed = record["domain"]["digest"] != domain.digest
    review_policy_changed = record["review_policy"]["digest"] != policy_digest
    engine_changed = prior_engine != {key: engine[key] for key in ENGINE_IDENTITY_FIELDS}
    authority_changed = record["review_authority"] != packet.authority
    motivation_changed = _motivation_moved(record, domain, packet, motivation, budget)
    status, support = _verdict(
        evaluate(
            "gc-relevance-freshness",
            term("Moved", bool(changes), policy_changed, review_policy_changed, engine_changed, authority_changed,
                 motivation_changed),
            budget=budget,
        )
    )
    return FreshnessReport(
        review_id=record["review_id"],
        fingerprint=record["fingerprint"],
        changes=tuple(changes),
        ignored_changes=ignored,
        policy_changed=policy_changed,
        review_policy_changed=review_policy_changed,
        engine_changed=engine_changed,
        authority_changed=authority_changed,
        status=status,
        support=support,
        motivation_changed=motivation_changed,
    )


# Whether the motivation the review rested on moved: the record's snapshot identity against the
# current snapshot's identity for the record's candidates, at the current packet's as_of. A record
# of a domain without needs holds none and its domain has none to compare; a domain that gained or
# lost needs has another digest, which the domain comparison reports. A record that names its
# stream is compared only with that stream, so a caller who leaves the stream out, or names another,
# is refused instead of told the review is stale.
# am[implements a-v2m-snapshot-identity-1019@118a4b] am[rests-on c-v2-motivation-freshness-obligation-1019@ad4628]
# am[implements a-v2m-freshness-stream-explicit-1020@5eabf7]
def _motivation_moved(record: Mapping[str, Any], domain: Domain, packet: ReviewPacket,
                      snapshot: MotivationSnapshot | None, budget: RunBudget) -> bool:
    if "motivation" not in record:
        raise RelevanceError("invalid-record", "review record has no motivation")
    stored = record["motivation"]
    if stored is not None and (not isinstance(stored, Mapping) or not isinstance(stored.get("snapshot"), Mapping)):
        raise RelevanceError("invalid-record", "review record.motivation must be null or carry its snapshot")
    if not domain.needs:
        if snapshot is not None:
            raise RelevanceError("invalid-motivation", f"{domain.source} declares no needs, so its freshness takes no motivation snapshot")
        return stored is not None
    named = None if stored is None else stored["snapshot"].get("stream")
    if named is not None and not isinstance(named, str):
        raise RelevanceError("invalid-record", "review record.motivation.snapshot.stream must be null or text")
    if snapshot is None:
        if named is not None:
            raise RelevanceError("invalid-motivation", f"the review ranked by motivation stream {named!r}, so its "
                                                       "freshness needs that stream's snapshot at the packet's as_of")
        try:
            snapshot = motivation_snapshot(domain, None, stream=None, as_of=packet.as_of, budget=budget)
        except BudgetExhausted as error:
            raise stopped(error) from error
    elif snapshot.domain_digest != domain.digest or snapshot.as_of != packet.as_of:
        raise RelevanceError("invalid-motivation", "the motivation snapshot was computed for another domain or instant than the packet's")
    elif named is not None and snapshot.stream != named:
        raise RelevanceError("invalid-motivation", f"the review ranked by motivation stream {named!r}, not {snapshot.stream!r}")
    if stored is None:
        return True
    return dict(stored["snapshot"]) != snapshot.identity(candidate["action"] for candidate in record["candidates"])


# am[implements a-rel-review-contract-1016@d0bea9]
def _verdict(answer: Any) -> tuple[str, str]:
    try:
        if not isinstance(answer, tuple) or len(answer) != 3 or symbol(answer[0]) != "Freshness":
            raise ValueError(f"expected (Freshness STATUS SUPPORT), got {answer!r}")
        verdict = (text(answer[1]), text(answer[2]))
        if verdict not in {("fresh", "standing"), ("stale", "withdrawn")}:
            raise ValueError(f"unknown freshness verdict {verdict}")
        return verdict
    except ValueError as error:
        raise RelevanceError("engine-output-invalid", f"the freshness policy answered {error}") from error


# am[implements a-rel-review-contract-1016@d0bea9]
# A record's current definite readings, as a snapshot lists them: its support and its contested
# readings. A record written before contested readings existed lists every current reading as
# support, so it has none to add.
# am[implements a-rel-rr-p-effective-1018@2a0968]
def _definite_identities(reading: Mapping[str, Any]) -> list[dict[str, object]]:
    return sorted(
        ({key: item[key] for key in OBSERVATION_IDENTITY} for item in (*reading["support"], *reading.get("contested", ()))),
        key=lambda identity: tuple(str(identity[key]) for key in sorted(identity)),
    )

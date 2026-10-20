"""Purpose: compute a stream's motivation snapshot at one instant for a domain that declares needs:
hand the domain's needs, expected changes and actions and the stream's history of need
observations and host attempts to the motivation policy, relevance/policy/motivation.metta, under
the caller's RunBudget, and read its answer back as typed records the review ranks by, records,
fingerprints and checks for freshness.

    motivation_snapshot(domain, history, *, stream, as_of, budget) -> MotivationSnapshot

The policy owns every rule: which observation is a need's level, which attempt's change counts as
a sample, how expected changes are learned and how far each action can reduce each need's
urgency. This module only validates what it is handed, builds the policy's input from it and
checks the answer's shape. `history` is a goal_chainer.motivation.MotivationHistory, as
MotivationStore.history() reads it in one consistent read, holding only the store's own
NeedObservation and Attempt records, whose constructors are the one home of what any observation
or attempt must satisfy; None is the history of a stream nothing has been recorded in, whose needs
are all unobserved. What only the domain or the vocabulary can say of a record, such as whether
its need, scale and estimator class are declared, the policy decides and lists as an exclusion,
since a stream recorded under an older domain stays readable.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..domains.model import Domain
from ..errors import InvalidInputError
from ..runtime.budget import RunBudget, caller_budget
from .canonical import fingerprint_of
from .errors import RelevanceError
from .instants import microseconds, utc_text
from .policy import constant, evaluate, is_nothing, items, symbol, term, text

# goal_chainer.motivation's records read relevance's instants and canonical identities, so this
# module names them for the type checker and imports them when a snapshot is first computed.
if TYPE_CHECKING:
    from ..motivation.store import Attempt, MotivationHistory, NeedObservation

SNAPSHOT_PROTOCOL = "goalchainer-motivation-snapshot-v1"
LEVEL_STATES = ("observed", "unobserved", "expired", "conflicted")
CHANGE_STATES = ("measured", "declared", "unknown")


# One need's level at the snapshot's instant: STATE observed with its value, band distance and
# urgency, or unobserved, expired or conflicted with none of them, and the observations it rests
# on with their estimator classes. Its identity and its review entry commit to those observations
# by count and by the SHA-256 of their sorted ids, so they stay one size however many sources
# report at the latest instant; the review entry keeps the distinct estimator classes the ranking's
# ceiling read, a set of at most the vocabulary's classes, and only the full snapshot a status read
# answers lists every observation with its class.
# am[implements a-v2m-levels-1019@387e68] am[implements a-v2r-level-support-digest-1020]
# am[addresses i-v2r-level-support-unbounded-1020]
@dataclass(frozen=True, slots=True)
class NeedLevel:
    need: str
    state: str
    value: float | None
    distance: float | None
    urgency: float | None
    support: tuple[tuple[str, str], ...]

    @property
    def known(self) -> bool:
        return self.state == "observed"

    def identity(self) -> dict[str, object]:
        """What a decision resting on this level rests on: its state, its value, and the count of the
        observations behind it with a SHA-256 commitment to their sorted ids."""

        ids = sorted({observation for observation, _ in self.support})
        return {"state": self.state, "level": self.value, "support_count": len(ids),
                "support_digest": fingerprint_of({"support": ids})}

    def to_review_dict(self) -> dict[str, object]:
        return {"need": self.need, **self.identity(), "distance": self.distance, "urgency": self.urgency,
                "support_estimators": sorted({estimator for _, estimator in self.support})}

    def to_dict(self) -> dict[str, object]:
        return {**self.to_review_dict(), "support": [{"observation": observation, "estimator": estimator}
                                                     for observation, estimator in sorted(set(self.support))]}


# A measured sample's identity: its attempt and the observations of its two endpoints.
# am[implements a-v2m-expectations-1019@b13468] am[rests-on c-v2m-endpoint-order-free-1019@6a9e43]
@dataclass(frozen=True, slots=True)
class SampleKey:
    attempt: str
    before: tuple[str, ...]
    after: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"attempt": self.attempt, "before": sorted(self.before), "after": sorted(self.after)}


# One action's expected change of one need: measured, the mean of its samples with the class
# receipt-calibrated; declared, the domain's change and class; or unknown. Its identity commits to
# its samples by count and by the SHA-256 of their sorted keys, so it stays one fixed size however
# long the stream grows; the keys themselves are in the full snapshot a status read answers.
# am[implements a-v2m-expectations-1019@b13468] am[implements a-v2r-record-digest-1020]
@dataclass(frozen=True, slots=True)
class ExpectedChange:
    action: str
    need: str
    state: str
    change: float | None
    samples: int
    estimator: str | None
    keys: tuple[SampleKey, ...]

    @property
    def known(self) -> bool:
        return self.state != "unknown"

    def sample_keys(self) -> list[dict[str, object]]:
        return sorted((key.to_dict() for key in self.keys), key=lambda key: (key["attempt"], key["before"], key["after"]))

    def identity(self) -> dict[str, object]:
        return {
            "state": self.state,
            "change": self.change,
            "estimator": self.estimator,
            "count": self.samples,
            "samples_digest": fingerprint_of({"samples": self.sample_keys()}),
        }

    def to_dict(self) -> dict[str, object]:
        return {"action": self.action, "need": self.need, **self.identity(), "samples": self.sample_keys()}


# The history a snapshot was computed from, as that history states itself: event_count is how many
# records it held, len(observations) + len(attempts), and digest the digest it carried. For a
# store's read these are the read's own events, one record per event since a stream admits only
# those two kinds, and the digest a SHA-256 commitment to their ordered sequences and ids, so a
# status read through that count replays exactly that prefix after any later append. A history a
# caller built in memory names no store prefix: its count is of the records it was given, repeats
# included although the snapshot counts a repeated record once, and its digest is whatever its
# builder chose, which nothing can replay; a MotivationStore.memory() read is a real prefix, gone
# once that store closes.
# am[implements a-v2r-record-digest-1020] am[rests-on c-v2r-store-prefix-immutable-1020]
@dataclass(frozen=True, slots=True)
class HistoryReference:
    event_count: int
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {"event_count": self.event_count, "digest": self.digest}


# The interval an action can reduce a need's urgency by, in [-1, 1], each end with the real one's
# exact sign, or 0.0 where the real end's size is below 2^-1022, and the level the action is
# predicted to leave, a range on the need's scale wherever the level or the change is unknown.
# am[implements a-v2m-drive-paths-1019@65a7d5] am[rests-on c-v2m-reduction-formula-1019@0fcd08]
# am[implements a-v2r-predicted-level-1020] am[rests-on c-v2r-sign-invariant-1020]
@dataclass(frozen=True, slots=True)
class Reduction:
    action: str
    need: str
    low: float
    high: float
    predicted_level: tuple[float, float]

    def to_dict(self) -> dict[str, object]:
        return {"action": self.action, "need": self.need, "low": self.low, "high": self.high,
                "predicted_level": {"low": self.predicted_level[0], "high": self.predicted_level[1]}}


# One measured sample: the change the host attributed to an attempt, the expectation it was
# observed against, and their difference.
# am[implements a-v2m-expectations-1019@b13468] am[rests-on c-v2m-attribution-associational-1019@daf305]
@dataclass(frozen=True, slots=True)
class OutcomeSample:
    key: SampleKey
    action: str
    need: str
    change: float
    prior: float | None
    residual: float | None

    def to_dict(self) -> dict[str, object]:
        return {**self.key.to_dict(), "action": self.action, "need": self.need, "change": self.change,
                "expected": self.prior, "residual": self.residual}


# am[implements a-v2m-snapshot-identity-1019@118a4b] am[implements a-v2m-levels-1019@387e68]
# am[implements a-v2m-expectations-1019@b13468]
@dataclass(frozen=True, slots=True)
class MotivationSnapshot:
    """A stream's motivational state at one instant, as the motivation policy derived it."""

    stream: str | None
    as_of: datetime
    domain_digest: str
    levels: tuple[NeedLevel, ...]
    changes: tuple[ExpectedChange, ...]
    reductions: tuple[Reduction, ...]
    samples: tuple[OutcomeSample, ...]
    not_sampled: tuple[tuple[str, str, str], ...]
    excluded: tuple[tuple[str, str], ...]
    history: HistoryReference | None = None

    def level(self, need: str) -> NeedLevel:
        return next(level for level in self.levels if level.need == need)

    def change(self, action: str, need: str) -> ExpectedChange:
        return next(change for change in self.changes if (change.action, change.need) == (action, need))

    def reduction(self, action: str, need: str) -> Reduction:
        return next(item for item in self.reductions if (item.action, item.need) == (action, need))

    def identity(self, actions: Iterable[str]) -> dict[str, object]:
        """What a review of `actions` rests on: the stream, every need's level and each of those
        actions' expected changes, each with SHA-256 commitments to the observations or samples
        behind it, so a new observation or sample changes the identity even when the value it gives
        is unchanged. The history it was read from is no part of it: an append that changes none of
        these leaves a review fresh."""

        wanted = set(actions)
        return {
            "stream": self.stream,
            "levels": {level.need: level.identity() for level in self.levels},
            "changes": {f"{change.action} {change.need}": change.identity()
                        for change in self.changes if change.action in wanted},
        }

    # The whole snapshot, as a status read answers it, with every level's observations, every
    # sample, every not_sampled entry, one for each applied attempt and need it produced an
    # observation of that gave no sample, naming the rule it failed (c-v2r-not-sampled-rule-1020),
    # and every observation excluded.
    # am[implements a-v2r-record-digest-1020] am[implements a-v2r-level-support-digest-1020]
    def to_dict(self) -> dict[str, object]:
        return {
            "protocol": SNAPSHOT_PROTOCOL,
            **self._fixed(),
            "levels": [level.to_dict() for level in self.levels],
            "changes": [change.to_dict() for change in self.changes],
            "samples": [sample.to_dict() for sample in self.samples],
            "not_sampled": [{"attempt": attempt, "need": need, "reason": reason}
                            for attempt, need, reason in self.not_sampled],
            "excluded": [{"observation": observation, "reason": reason} for observation, reason in self.excluded],
        }

    # The snapshot as a review records it, of one size however long its stream is and however many
    # observations share an instant: each level with its support's count, commitment and estimator
    # classes, each change with its sample count and the commitment to its keys, the reductions, and
    # the history it was read from, through which a status read recovers the levels' observations,
    # the samples, the not_sampled entries and the excluded observations exactly as this snapshot
    # had them.
    # am[implements a-v2r-record-digest-1020] am[implements a-v2r-level-support-digest-1020]
    def to_review_dict(self) -> dict[str, object]:
        return {**self._fixed(), "levels": [level.to_review_dict() for level in self.levels],
                "changes": [{"action": change.action, "need": change.need, **change.identity()}
                            for change in self.changes]}

    def _fixed(self) -> dict[str, object]:
        return {
            "stream": self.stream,
            "as_of": utc_text(self.as_of),
            "domain_digest": self.domain_digest,
            "history": None if self.history is None else self.history.to_dict(),
            "reductions": [reduction.to_dict() for reduction in self.reductions],
        }


# Time: building the input is linear in the declarations and the history; the policy's cost is in
# motivation.metta's entry comment; reading the answer is linear in its size.
# am[implements a-v2m-snapshot-identity-1019@118a4b] am[implements a-v2m-levels-1019@387e68] am[implements a-v2m-expectations-1019@b13468]
def motivation_snapshot(
    domain: Domain, history: MotivationHistory | None, *, stream: str | None, as_of: datetime, budget: RunBudget
) -> MotivationSnapshot:
    """The snapshot of `history` at `as_of` for `domain`'s needs, its policy call charged to
    `budget`; None is an empty stream's history. InvalidInputError, before any engine work, when
    the domain declares no needs, `as_of` has no offset, `stream` is neither None nor nonempty
    text, or `history` is not a MotivationHistory of the store's own NeedObservation and Attempt
    records with a text digest. The snapshot names the history it read by its records' count and
    its digest, and None for None."""

    budget = caller_budget(budget, "a motivation snapshot")
    if not domain.needs:
        raise InvalidInputError(f"{domain.source} declares no needs, so it has no motivation snapshot")
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise InvalidInputError("a motivation snapshot's as_of must be a datetime with a timezone offset")
    if stream is not None and (not isinstance(stream, str) or not stream.strip()):
        raise InvalidInputError("a motivation snapshot's stream must be None or nonempty text")
    observations, attempts = _records(history)
    answer = evaluate("gc-motivation-snapshot", _input(domain, observations, attempts, as_of), budget=budget)
    reference = None if history is None else HistoryReference(len(history.observations) + len(history.attempts), history.digest)
    return _read(answer, domain, stream=stream, as_of=as_of, history=reference)


# The history must be the store's own: a MotivationHistory whose every record a NeedObservation or
# an Attempt constructor accepted, so this module checks only the types and leaves every rule of
# what a record may hold to those constructors. A record held twice counts once, as the store
# records it once, so a history and the same history with a record repeated give one snapshot;
# two different attempts under one attempt id are no stream's history, since the store refuses the
# second, and are refused here too. An observation's id is its identity's fingerprint, so two
# observations under one id are the same observation.
# Time: one pass over the records, hashing each id.
# am[implements a-v2m-snapshot-identity-1019@118a4b] am[rests-on c-v2m-store-surface-1019@49737f]
# am[implements a-v2m-snapshot-sweep-1020@fefbd6]
def _records(history: object) -> tuple[tuple[NeedObservation, ...], tuple[Attempt, ...]]:
    from ..motivation.store import Attempt, MotivationHistory, NeedObservation  # noqa: PLC0415 (import cycle)

    if history is None:
        return (), ()
    if not isinstance(history, MotivationHistory) or not isinstance(history.observations, tuple) \
            or not isinstance(history.attempts, tuple) or not isinstance(history.digest, str):
        raise InvalidInputError("a motivation snapshot reads a MotivationHistory, as MotivationStore.history() gives it")
    for index, record in enumerate(history.observations):
        if not isinstance(record, NeedObservation):
            raise InvalidInputError(f"history.observations[{index}] is not a NeedObservation")
    attempts: dict[str, Attempt] = {}
    for index, record in enumerate(history.attempts):
        if not isinstance(record, Attempt):
            raise InvalidInputError(f"history.attempts[{index}] is not an Attempt")
        if attempts.setdefault(record.attempt, record) != record:
            raise InvalidInputError(f"history.attempts[{index}] states attempt {record.attempt} otherwise than an earlier one")
    return tuple({record.id: record for record in history.observations}.values()), tuple(attempts.values())


# The policy's input, every value a string, a number or one of its constructors.
# am[implements a-v2m-snapshot-identity-1019@118a4b] am[rests-on c-rel-strings-inert-1016@947e27]
def _input(domain: Domain, observations: tuple[NeedObservation, ...], attempts: tuple[Attempt, ...], as_of: datetime) -> Any:
    def at(moment: datetime | None, present: str, absent: str) -> Any:
        return constant(absent) if moment is None else term(present, microseconds(moment))

    stated_observations = items(
        term("Obs", o.id, o.need, o.level, o.scale[0], o.scale[1], o.estimator,
             microseconds(o.observed_at), at(o.valid_until, "Until", "Forever"),
             constant("Unstated") if o.produced_by is None else term("ProducedBy", o.produced_by))
        for o in observations
    )
    stated_attempts = items(term("Attempt", a.attempt, a.action, at(a.applied_at, "Applied", "NotApplied"))
                            for a in attempts)
    return term(
        "MotivationInput",
        term("AsOf", microseconds(as_of)),
        term("Needs", items(term("Need", n.id, n.goal, *n.scale, *n.band, n.drive) for n in domain.needs)),
        term("Declared", items(term("Expectation", e.action, e.need, e.change, e.estimator) for e in domain.need_expectations)),
        term("Actions", items(domain.action_ids)),
        term("Observations", stated_observations),
        term("Attempts", stated_attempts),
    )


# Any answer of another shape is the policy's defect: engine-output-invalid, as every relevance
# policy's unreadable answer is.
# Time: linear in the answer.
# am[implements a-v2m-snapshot-identity-1019@118a4b]
def _read(answer: Any, domain: Domain, *, stream: str | None, as_of: datetime,
          history: HistoryReference | None) -> MotivationSnapshot:
    try:
        head, levels, changes, reductions, samples, unsampled, excluded = answer
        if symbol(head) != "Snapshot":
            raise ValueError(f"expected (Snapshot ...), got {head!r}")
        snapshot = MotivationSnapshot(
            stream=stream,
            as_of=as_of,
            domain_digest=domain.digest,
            levels=tuple(map(_level, _body(levels, "Levels"))),
            changes=tuple(map(_change, _body(changes, "Changes"))),
            reductions=tuple(map(_reduction, _body(reductions, "Reductions"))),
            samples=tuple(map(_sample, _body(samples, "Samples"))),
            not_sampled=tuple(_parts(item, "NotSampled", 3, text) for item in _body(unsampled, "NotSampled")),
            excluded=tuple(_parts(item, "Excluded", 2, text) for item in _body(excluded, "Excluded")),
            history=history,
        )
    except (KeyError, ValueError, TypeError, IndexError) as error:
        raise RelevanceError("engine-output-invalid", f"the motivation policy answered an unreadable snapshot: {error}") from error
    expected = [(action, need.id) for action in domain.action_ids for need in domain.needs]
    if [level.need for level in snapshot.levels] != list(domain.need_ids) or \
            [(c.action, c.need) for c in snapshot.changes] != expected or \
            [(r.action, r.need) for r in snapshot.reductions] != expected:
        raise RelevanceError("engine-output-invalid", "the motivation policy answered for other needs or actions than declared")
    for reduction in snapshot.reductions:
        low, high = domain.need(reduction.need).scale
        if not low <= reduction.predicted_level[0] <= reduction.predicted_level[1] <= high:
            raise RelevanceError("engine-output-invalid", f"the motivation policy predicted {reduction.need} under "
                                 f"{reduction.action} outside its scale: {list(reduction.predicted_level)}")
    return snapshot


# am[implements a-v2m-snapshot-identity-1019@118a4b]
def _body(wrapped: Any, head: str) -> tuple:
    if not isinstance(wrapped, tuple) or len(wrapped) != 2 or symbol(wrapped[0]) != head or not isinstance(wrapped[1], tuple):
        raise ValueError(f"expected ({head} (...)), got {wrapped!r}")
    return wrapped[1]


# am[implements a-v2m-snapshot-identity-1019@118a4b]
def _parts(value: Any, head: str, size: int, read: Any = None) -> tuple:
    if not isinstance(value, tuple) or len(value) != size + 1 or symbol(value[0]) != head:
        raise ValueError(f"expected ({head} with {size} arguments), got {value!r}")
    return tuple(map(read, value[1:])) if read is not None else value[1:]


# A number in an answer; a boolean or None in its place is unreadable.
# am[implements a-v2m-snapshot-identity-1019@118a4b]
def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected a number, got {value!r}")
    return float(value)


# am[implements a-v2m-snapshot-identity-1019@118a4b]
def _optional(value: Any) -> float | None:
    return None if is_nothing(value) else _number(value)


# am[implements a-v2m-levels-1019@387e68]
def _level(item: Any) -> NeedLevel:
    need, state, value, distance, urgency, support = _parts(item, "Level", 6)
    if text(state) not in LEVEL_STATES:
        raise ValueError(f"unknown level state {state!r}")
    (pairs,) = _parts(support, "Support", 1)
    level = NeedLevel(text(need), text(state), _optional(value), _optional(distance), _optional(urgency),
                      tuple(_parts(pair, "Sup", 2, text) for pair in pairs))
    if level.known != (level.value is not None and level.distance is not None and level.urgency is not None):
        raise ValueError(f"level {level.need} is {level.state} with value {level.value!r}")
    return level


# am[implements a-v2m-expectations-1019@b13468]
def _key(item: Any) -> SampleKey:
    attempt, before, after = _parts(item, "Key", 3)
    return SampleKey(text(attempt), tuple(map(text, before)), tuple(map(text, after)))


# am[implements a-v2m-expectations-1019@b13468]
def _change(item: Any) -> ExpectedChange:
    action, need, state, mean, count, estimator, keys = _parts(item, "Change", 7)
    if text(state) not in CHANGE_STATES or isinstance(count, bool) or not isinstance(count, int):
        raise ValueError(f"unknown change {item!r}")
    (listed,) = _parts(keys, "Samples", 1)
    return ExpectedChange(text(action), text(need), text(state), _optional(mean), count,
                          None if is_nothing(estimator) else text(estimator), tuple(map(_key, listed)))


# am[implements a-v2m-drive-paths-1019@65a7d5] am[implements a-v2r-predicted-level-1020]
def _reduction(item: Any) -> Reduction:
    action, need, interval, predicted = _parts(item, "Reduction", 4)
    low, high = map(_number, _parts(interval, "Interval", 2))
    if not -1.0 <= low <= high <= 1.0:
        raise ValueError(f"reduction of {text(need)} by {text(action)} outside [-1, 1]: [{low}, {high}]")
    start, end = map(_number, _parts(predicted, "Interval", 2))
    return Reduction(text(action), text(need), low, high, (start, end))


# am[implements a-v2m-expectations-1019@b13468]
def _sample(item: Any) -> OutcomeSample:
    attempt, action, need, before, after, change, prior, residual = _parts(item, "Sample", 8)
    return OutcomeSample(SampleKey(text(attempt), tuple(map(text, before)), tuple(map(text, after))),
                         text(action), text(need), _number(change), _optional(prior), _optional(residual))

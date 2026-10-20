"""Purpose: typed signal readings, validated at the packet boundary, and the effective readings and theory facts the evidence policy makes of them.

The theory reasons over signals, so what a review packet says about each one is the whole
input to a review. A reading is `detected`, `refuted` or `unknown`, and the three are
genuinely different: "nothing looked" is not "we looked and it is absent".

What a review believes about each signal at its `as_of`, which fact that belief gives the theory,
and whether its readings are in dispute is `policy/evidence.metta`'s decision, read off the
justification kernel's labels: an expired reading decays to unknown, never to refuted; of two
valid contrary readings the one whose estimator class has the higher tier is preferred and the
other is contested, and two of one tier leave the signal conflicted; a detected signal asserts
`(given (signal X))`, a refuted one `(given (not (signal X)))`, and an unknown or conflicted one
nothing, because a rule body `(not (signal X))` needs the negative literal proved
(`ai-notes/deontic-theory-grammar.md` records the experiment). This module validates readings,
hands them to that policy, and renders the facts it answers.

Every definite reading carries the estimator class that produced it, because a proposal's
authority is capped by the weakest estimate underneath it (section 8.2), and the source and
validity window that identify the observation, because a proposal's support is that
observation and not merely its boolean value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, Literal, get_args

from ..domains.loader import vocabulary
from ..runtime.budget import RunBudget
from .canonical import fingerprint_of
from .errors import RelevanceError
from .instants import microseconds, utc_text
from .policy import constant, evaluate, is_nothing, items, symbol, term, text

EffectiveState = Literal["detected", "refuted", "unknown", "conflicted"]
EFFECTIVE_STATES: frozenset[str] = frozenset(get_args(EffectiveState))
# The fields that identify an observation: everything a reading carries except its signal, which
# keys it, and its note, which carries no decision-relevant meaning.
OBSERVATION_IDENTITY = ("state", "estimator", "source", "observed_at", "valid_until")


# am[implements a-rel-signals-1016@16b33a]
class SignalState(str, Enum):
    DETECTED = "detected"
    REFUTED = "refuted"
    UNKNOWN = "unknown"


# am[implements a-rel-signals-1016@16b33a] am[addresses i-rel-reading-validation-1016@09a38a]
@dataclass(frozen=True)
class SignalReading:
    """What one source concluded about one declared signal.

    `note` is free commentary and the only field that carries no decision-relevant meaning:
    the fingerprint and the freshness check leave it out, and everything else is part of the
    observation's identity.
    """

    signal: str
    state: SignalState
    source: str
    estimator: str | None = None
    note: str = ""
    observed_at: datetime | None = None
    valid_until: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.signal, str) or not self.signal:
            raise _invalid(f"a reading needs a signal name, got {self.signal!r}")
        try:
            state = SignalState(self.state)
        except ValueError:
            raise _invalid(
                f"reading for {self.signal}: state must be one of "
                f"{', '.join(state.value for state in SignalState)}, got {self.state!r}"
            ) from None
        object.__setattr__(self, "state", state)
        if not isinstance(self.source, str) or not self.source.strip():
            raise _invalid(f"reading for {self.signal}: a reading needs a nonempty source")
        if self.estimator is None:
            if state is not SignalState.UNKNOWN:
                raise _invalid(
                    f"reading for {self.signal}: a {state.value} reading needs the estimator "
                    f"class that produced it"
                )
        elif self.estimator not in vocabulary().classes:
            raise _invalid(
                f"reading for {self.signal}: estimator must be one of "
                f"{', '.join(vocabulary().classes)}, got {self.estimator!r}"
            )
        if not isinstance(self.note, str):
            raise _invalid(f"reading for {self.signal}: note must be text")
        for name in ("observed_at", "valid_until"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, datetime) or value.tzinfo is None):
                raise _invalid(
                    f"reading for {self.signal}: {name} must be a timezone-aware time, got {value!r}"
                )
        if (
            self.observed_at is not None
            and self.valid_until is not None
            and self.valid_until < self.observed_at
        ):
            raise _invalid(f"reading for {self.signal}: valid_until precedes observed_at")

    @property
    def is_definite(self) -> bool:
        return self.state is not SignalState.UNKNOWN

    def identity(self) -> dict[str, object]:
        """The decision-relevant identity of this observation: everything except the note."""

        return {name: _wire(getattr(self, name)) for name in OBSERVATION_IDENTITY}

    # The planner names a reading's justification row by this id, so one reading has one name on
    # every path that reads it, with no second table mapping ids (a-dr-pj-observation-id-1018).
    # am[implements a-rel-pj-observation-id-1018@457d2e]
    def observation_id(self) -> str:
        """The SHA-256 of the signal and the observation's identity: two readings that differ only
        in their notes are one observation, and any other field names another."""

        return fingerprint_of({"signal": self.signal, **self.identity()})

    def to_dict(self) -> dict[str, object]:
        return {"signal": self.signal, **self.identity(), "note": self.note}


# am[implements a-rel-signals-1016@16b33a] am[rests-on c-integrate-agenticmind-support-1016@b60619]
# am[implements a-rel-rr-p-effective-1018@2a0968] am[implements a-rel-rr-p-escalation-1018@86a7bb]
@dataclass(frozen=True)
class EffectiveReading:
    """What a review actually believes about one signal at its `as_of` time.

    `support` holds the current definite readings the state rests on, and `contested` the current
    ones a preferred contrary overruled. `decayed` holds definite readings that expired before
    `as_of`; they were evidence once and are not now. `fact` is the theory fact the belief
    asserts: True for the signal, False for its negation, None for no fact. `disputed` says the
    disagreement is live, conflicted or contested, which the ranking escalates when the signal
    can affect the review.
    """

    signal: str
    state: EffectiveState
    fact: bool | None = None
    disputed: bool = False
    support: tuple[SignalReading, ...] = ()
    contested: tuple[SignalReading, ...] = ()
    decayed: tuple[SignalReading, ...] = ()
    unknown: tuple[SignalReading, ...] = ()

    def snapshot(self) -> dict[str, object]:
        """The state and the identities of the current readings it was decided from, in a fixed order.

        Two effective readings with equal snapshots support exactly the same conclusions with
        exactly the same evidence, so the snapshot's support lists every current definite
        reading, a contested one too, since one that lapses ends the dispute it caused; an unknown
        signal snapshots as its state alone, since no observation supports it.
        """

        return {
            "state": self.state,
            "support": sorted(
                (reading.identity() for reading in (*self.support, *self.contested)),
                key=lambda identity: tuple(str(identity[key]) for key in sorted(identity)),
            ),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "signal": self.signal,
            "state": self.state,
            "support": [reading.to_dict() for reading in self.support],
            "contested": [reading.to_dict() for reading in self.contested],
            "decayed": [reading.to_dict() for reading in self.decayed],
            "unknown": [reading.to_dict() for reading in self.unknown],
        }


# Time: r checks and r observation ids for the r readings, then one policy call: one kernel run
# over the r rows and s * (2 + r) * a comparisons over its a answer atoms, s = signals.
# am[implements a-rel-signals-1016@16b33a] am[rests-on c-integrate-agenticmind-support-1016@b60619]
# am[implements a-rel-rr-p-rows-1018@14fc36] am[implements a-rel-reading-term-one-home-1018@522700]
# am[implements a-rel-mig-callers-1018@da2f3e]
def effective_readings(
    readings: Iterable[SignalReading],
    signals: Iterable[str],
    as_of: datetime,
    *,
    budget: RunBudget,
) -> dict[str, EffectiveReading]:
    """Every declared signal's effective reading at `as_of`, unknown where nothing was read.

    A reading for an undeclared signal, or one observed after `as_of`, is an error: the first
    could never reach a rule, and the second would let a review rest on the future. The policy
    call is charged to `budget`.
    """

    declared = list(signals)
    listed = list(readings)
    for reading in listed:
        if reading.signal not in declared:
            raise _invalid(
                f"reading for undeclared signal {reading.signal}; this domain declares "
                f"{', '.join(sorted(declared))}"
            )
        if reading.observed_at is not None and reading.observed_at > as_of:
            raise _invalid(
                f"reading for {reading.signal} was observed at {utc_text(reading.observed_at)}, "
                f"after the review's as_of {utc_text(as_of)}"
            )
    answer = evaluate(
        "gc-relevance-effective", microseconds(as_of), items(reading_term(reading) for reading in listed),
        items(declared), budget=budget,
    )
    # A normal answer is a list of (Effective ...) beliefs; only the kernel's refusal opens with a symbol.
    if isinstance(answer, tuple) and answer and not isinstance(answer[0], tuple) and symbol(answer[0]) == "Refused":
        raise RelevanceError("engine-output-invalid", f"the justification kernel refused the readings' rows: {answer!r}")
    named = [(reading.observation_id(), reading) for reading in listed]
    try:
        effective = [_read_effective(item, named) for item in answer]
    except (ValueError, TypeError, IndexError) as error:
        raise RelevanceError("engine-output-invalid", f"the evidence policy answered an unreadable belief: {error}") from error
    if [reading.signal for reading in effective] != declared:
        raise RelevanceError("engine-output-invalid", "the evidence policy did not answer one belief per declared signal")
    return {reading.signal: reading for reading in effective}


# A reading as the shared vocabulary's row rule reads it, named by its observation id. The review's
# evidence policy and the planner both build their rows from this one term, so a reading has one
# name on every path that reads it.
# am[implements a-rel-reading-term-one-home-1018@522700] am[addresses i-rel-reading-term-two-homes-1018@a67558]
# am[implements a-rel-pj-observation-id-1018@457d2e]
def reading_term(reading: SignalReading) -> Any:
    """`(Reading SIGNAL STATE ESTIMATOR VALIDITY ID)` as a pymetta atom, ID the reading's
    observation_id(), ESTIMATOR None for an unknown reading and VALIDITY Forever or
    (Until MICROSECONDS)."""

    return term(
        "Reading",
        reading.signal,
        reading.state.value,
        constant("None") if reading.estimator is None else reading.estimator,
        _validity(reading.valid_until),
        reading.observation_id(),
    )


# am[implements a-rel-signals-1016@16b33a] am[implements a-rel-rr-p-effective-1018@2a0968]
def _read_effective(item: Any, named: list[tuple[str, SignalReading]]) -> EffectiveReading:
    if not isinstance(item, tuple) or len(item) != 9 or symbol(item[0]) != "Effective":
        raise ValueError(f"expected (Effective ...), got {item!r}")
    _, signal, state, fact, disputed, support, contested, decayed, unknown = item
    if text(state) not in EFFECTIVE_STATES:
        raise ValueError(f"unknown effective state {state!r}")
    if not isinstance(disputed, bool):
        raise ValueError(f"a dispute flag must be a boolean, got {disputed!r}")
    return EffectiveReading(
        signal=text(signal),
        state=state,
        fact=_fact(fact, signal),
        disputed=disputed,
        support=_named(support, named),
        contested=_named(contested, named),
        decayed=_named(decayed, named),
        unknown=_named(unknown, named),
    )


# The readings a belief names by observation id, in packet order. Readings that differ only in
# their notes are one observation with one row, so every one of them stands behind it, as each did
# when a reading was named by its position.
# Time: r membership tests in a set of the k ids named, r = readings.
# am[implements a-rel-reading-term-one-home-1018@522700]
def _named(ids: Any, named: list[tuple[str, SignalReading]]) -> tuple[SignalReading, ...]:
    if not isinstance(ids, tuple) or not all(isinstance(identifier, str) for identifier in ids):
        raise ValueError(f"expected a list of observation ids, got {ids!r}")
    wanted = set(ids)
    unknown = wanted - {identifier for identifier, _ in named}
    if unknown:
        raise ValueError(f"the belief names observations no reading has: {sorted(unknown)}")
    return tuple(reading for identifier, reading in named if identifier in wanted)


# am[implements a-rel-signals-1016@16b33a]
def _fact(value: Any, signal: str) -> bool | None:
    if is_nothing(value):
        return None
    if not isinstance(value, tuple) or len(value) != 2 or symbol(value[0]) != "Some":
        raise ValueError(f"expected None or (Some (Fact ...)), got {value!r}")
    fact = value[1]
    if not isinstance(fact, tuple) or len(fact) != 3 or symbol(fact[0]) != "Fact" or fact[1] != signal:
        raise ValueError(f"expected (Fact {signal} BOOL), got {fact!r}")
    if not isinstance(fact[2], bool):
        raise ValueError(f"a fact's polarity must be a boolean, got {fact[2]!r}")
    return fact[2]


# am[implements a-rel-signals-1016@16b33a]
def _validity(valid_until: datetime | None) -> Any:
    return constant("Forever") if valid_until is None else term("Until", microseconds(valid_until))


# am[implements a-rel-signals-1016@16b33a]
def theory_facts(effective: dict[str, EffectiveReading]) -> str:
    """The `given` facts a theory is run against, rendered from the facts the evidence policy decided."""

    lines: list[str] = []
    for name in sorted(effective):
        fact = effective[name].fact
        if fact is True:
            lines.append(f"(given (signal {name}))")
        elif fact is False:
            lines.append(f"(given (not (signal {name})))")
    return "\n".join(lines)


# A time is written as its UTC instant, so one observation re-sent at another offset keeps its
# identity in the fingerprint and the freshness check.
# am[implements a-rel-signals-1016@16b33a] am[implements a-rel-rcpt-v2-reading-instants-1017@034dcc]
# am[addresses i-rel-reading-identity-offset-1017@5e1130]
def _wire(value: object) -> object:
    """A reading field as the review record carries it."""

    if isinstance(value, SignalState):
        return value.value
    if isinstance(value, datetime):
        return utc_text(value)
    return value


# am[implements a-rel-signals-1016@16b33a]
def _invalid(message: str) -> RelevanceError:
    return RelevanceError("invalid-packet", message)

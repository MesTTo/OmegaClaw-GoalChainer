"""Purpose: parse and validate the review packet, the bounded decision-relevant slice a review reads.

The packet is the paper's section 8.5 review packet reduced to what this review consumes: the
focal subject and trigger for the record, the reference time every reading is judged at, the
authority rung the review itself runs at, the caller's explicit budget, and the signal
readings. Nothing here reads a clock, a file or the hive: the same packet always means the
same review.

    {
      "protocol": "goalchainer-relevance-packet-v1",
      "review_id": "rr-42",
      "subject": "chemistry-calibration",
      "trigger": "resource-conflict",
      "as_of": "2026-10-16T09:00:00+00:00",
      "authority": "advisory",
      "budget": {"inferences": 5000000, "timeout_seconds": 60},
      "policy_version": "task-control-v1",
      "readings": [
        {"signal": "review_open", "state": "detected", "estimator": "deterministic",
         "source": "task-board:rr-42", "observed_at": "2026-10-16T08:59:00+00:00"}
      ]
    }

`policy_version` is optional; when present it must equal the domain's, so a packet compiled
for one policy cannot be reviewed under another. The budget has no default, because how much
a caller will spend on one review is the caller's decision (section 10.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from ..domains.model import Domain
from ..errors import InvalidInputError, safe_repr
from ..runtime.budget import RunBudget, caller_budget
from ..runtime.numbers import finite_float
from .errors import RelevanceError
from .instants import parse_instant
from .signals import SignalReading

PACKET_PROTOCOL = "goalchainer-relevance-packet-v1"

_PACKET_KEYS = frozenset(
    {"protocol", "review_id", "subject", "trigger", "as_of", "authority", "budget",
     "policy_version", "readings"}
)
_READING_KEYS = frozenset(
    {"signal", "state", "estimator", "source", "note", "observed_at", "valid_until"}
)


# am[implements a-rel-review-contract-1016@d0bea9]
@dataclass(frozen=True)
class ReviewBudget:
    """The most one review may cost, as the packet declares it: deterministic engine inferences
    and wall-clock seconds. The review runs under its caller's RunBudget, which may be tighter
    than these bounds and never looser."""

    inferences: int
    timeout_seconds: float

    # A caller with no budget of its own, such as the relevance CLI or a test, builds the one
    # budget at its boundary from what the packet declares (c-rel-review-builds-own-budget-1018).
    # am[implements a-integrate-domain-review-budget-1018@a84bf4]
    def run_budget(self) -> RunBudget:
        """A RunBudget of exactly these bounds, its deadline starting now."""

        return RunBudget(inference_budget=self.inferences, timeout_seconds=self.timeout_seconds)

    # The packet declares what the review may cost, so a caller offering more would let it cost
    # more than declared. What the caller has left is compared when the work is entered, and an
    # exhausted budget stops it there with the budget's own error. A bound of any size is kept, so
    # the refusal writes it through errors.safe_repr, which names one too long to write
    # (c-rel-packet-refusals-constructed-1018).
    # am[implements a-integrate-domain-review-budget-1018@a84bf4] am[related a-rt-rb-one-budget-1018@550ffd]
    # am[implements a-rel-packet-refusals-safe-repr-1018@c2f3f7]
    def admit(self, budget: object, work: str) -> RunBudget:
        """`budget` when it is a RunBudget with no more left than these bounds; otherwise
        InvalidInputError, naming `work`. Raises InferenceBudgetExceeded or ReviewTimeout when the
        budget is already used up."""

        budget = caller_budget(budget, work)
        inferences, seconds = budget.remaining()
        if inferences is None or inferences > self.inferences or seconds > self.timeout_seconds:
            raise InvalidInputError(
                f"{work} runs under a budget no looser than its packet's: at most {safe_repr(self.inferences)} "
                f"inferences and {self.timeout_seconds} seconds.",
                details={"packet": {"inferences": self.inferences, "timeout_seconds": self.timeout_seconds},
                         "caller": {"inferences": inferences, "seconds": seconds}},
            )
        return budget


# am[implements a-rel-review-contract-1016@d0bea9]
@dataclass(frozen=True)
class ReviewPacket:
    review_id: str
    subject: str
    trigger: str
    as_of: datetime
    authority: str
    budget: ReviewBudget
    readings: tuple[SignalReading, ...]
    policy_version: str | None = None

    def check_against(self, domain: Domain) -> None:
        """Reject a packet the domain cannot review: wrong policy or undeclared authority."""

        if self.policy_version is not None and self.policy_version != domain.policy_version:
            raise RelevanceError(
                "policy-version-mismatch",
                f"the packet was compiled for policy {self.policy_version}, but {domain.source} "
                f"is policy {domain.policy_version}",
                details={"packet": self.policy_version, "domain": domain.policy_version},
            )
        if self.authority not in domain.authority_ids:
            raise _invalid(
                f"authority {self.authority!r} is not a tier of {domain.source}; "
                f"tiers: {', '.join(domain.authority_ids)}"
            )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "protocol": PACKET_PROTOCOL,
            "review_id": self.review_id,
            "subject": self.subject,
            "trigger": self.trigger,
            "as_of": self.as_of.isoformat(),
            "authority": self.authority,
            "budget": {
                "inferences": self.budget.inferences,
                "timeout_seconds": self.budget.timeout_seconds,
            },
            "readings": [reading.to_dict() for reading in self.readings],
        }
        if self.policy_version is not None:
            payload["policy_version"] = self.policy_version
        return payload


# Every refusal writes the value it rejected through errors.safe_repr, so a Python caller's mapping,
# which can hold what JSON never carries, meets the refusal JSON input would (a-rt-rr-safe-repr-1018).
# am[implements a-rel-review-contract-1016@d0bea9] am[addresses i-rel-reading-validation-1016@09a38a]
# am[implements a-rel-packet-refusals-safe-repr-1018@c2f3f7] am[related a-rt-rr-safe-repr-1018@ec9700]
def parse_packet(payload: Any) -> ReviewPacket:
    """Build a packet from decoded JSON, or raise `RelevanceError` naming the first problem."""

    if not isinstance(payload, Mapping):
        raise _invalid("a review packet must be a JSON object")
    _exact_keys(payload, _PACKET_KEYS, {"policy_version"}, "packet")
    if payload["protocol"] != PACKET_PROTOCOL:
        raise _invalid(f"packet protocol must be {PACKET_PROTOCOL}, got {safe_repr(payload['protocol'])}")
    budget = payload["budget"]
    if not isinstance(budget, Mapping):
        raise _invalid("budget must be an object with inferences and timeout_seconds")
    _exact_keys(budget, frozenset({"inferences", "timeout_seconds"}), set(), "budget")
    readings = payload["readings"]
    if not isinstance(readings, list):
        raise _invalid("readings must be a list")
    policy_version = payload.get("policy_version")
    if policy_version is not None:
        policy_version = _text(policy_version, "policy_version")
    return ReviewPacket(
        review_id=_text(payload["review_id"], "review_id"),
        subject=_text(payload["subject"], "subject"),
        trigger=_text(payload["trigger"], "trigger"),
        as_of=_time(payload["as_of"], "as_of"),
        authority=_text(payload["authority"], "authority"),
        budget=ReviewBudget(
            inferences=_positive_int(budget["inferences"], "budget.inferences"),
            timeout_seconds=_positive_number(budget["timeout_seconds"], "budget.timeout_seconds"),
        ),
        readings=tuple(_reading(item, index) for index, item in enumerate(readings)),
        policy_version=policy_version,
    )


# am[implements a-rel-review-contract-1016@d0bea9]
def _reading(item: Any, index: int) -> SignalReading:
    where = f"readings[{index}]"
    if not isinstance(item, Mapping):
        raise _invalid(f"{where} must be an object")
    _exact_keys(item, _READING_KEYS, {"estimator", "note", "observed_at", "valid_until"}, where)
    estimator = item.get("estimator")
    return SignalReading(
        signal=_text(item["signal"], f"{where}.signal"),
        state=_text(item["state"], f"{where}.state"),  # type: ignore[arg-type]
        source=_text(item["source"], f"{where}.source"),
        estimator=None if estimator is None else _text(estimator, f"{where}.estimator"),
        note=_text(item.get("note", ""), f"{where}.note", allow_empty=True),
        observed_at=_optional_time(item.get("observed_at"), f"{where}.observed_at"),
        valid_until=_optional_time(item.get("valid_until"), f"{where}.valid_until"),
    )


# JSON's object keys are text, but a Python caller's mapping can hold any key, so a key that is no
# string is named through errors.safe_repr, and the names, all text, sort and join.
# am[implements a-rel-review-contract-1016@d0bea9] am[implements a-rel-packet-refusals-safe-repr-1018@c2f3f7]
def _exact_keys(
    payload: Mapping[str, Any], allowed: frozenset[str], optional: set[str], where: str
) -> None:
    unknown = sorted(key if isinstance(key, str) else safe_repr(key) for key in set(payload) - allowed)
    if unknown:
        raise _invalid(f"{where} has unknown fields: {', '.join(unknown)}")
    missing = sorted(allowed - optional - set(payload))
    if missing:
        raise _invalid(f"{where} is missing: {', '.join(missing)}")


# am[implements a-rel-review-contract-1016@d0bea9]
def _text(value: Any, where: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise _invalid(f"{where} must be {'text' if allow_empty else 'nonempty text'}")
    return value


# am[implements a-rel-review-contract-1016@d0bea9] am[implements a-rel-rcpt-v2-instants-1017@3a3b0d]
def _time(value: Any, where: str) -> datetime:
    text = _text(value, where)
    try:
        return parse_instant(text)
    except ValueError as error:
        raise _invalid(f"{where} {error}, got {text!r}") from None


# am[implements a-rel-review-contract-1016@d0bea9]
def _optional_time(value: Any, where: str) -> datetime | None:
    return None if value is None else _time(value, where)


# am[implements a-rel-review-contract-1016@d0bea9] am[implements a-rel-packet-refusals-safe-repr-1018@c2f3f7]
def _positive_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _invalid(f"{where} must be a positive whole number, got {safe_repr(value)}")
    return value


# A timeout is the float the review's budget runs under, so a number is an invalid packet unless
# runtime.numbers.finite_float, which RunBudget reads its timeout with, holds it and it is
# positive. finite_float holds no integer from 2**1024 - 2**970 up (c-rel-num-packet-timeout-edge-1018),
# and such an integer, the one int it refuses, is named rather than written out, since one longer
# than the interpreter's digit limit cannot be written.
# am[implements a-rel-review-contract-1016@d0bea9] am[implements a-integrate-packet-number-refusal-1018@aecbf3]
# am[rests-on c-sn-overflow-and-digit-limits-1018@0e7f7d] am[implements a-rel-packet-shares-finite-float-1018@8346c1]
# am[implements a-rel-packet-refusals-safe-repr-1018@c2f3f7]
def _positive_number(value: Any, where: str) -> float:
    number = finite_float(value)
    if number is None and isinstance(value, int) and not isinstance(value, bool):
        raise _invalid(f"{where} must be a positive finite number, got an integer beyond the float range")
    if number is None or number <= 0:
        raise _invalid(f"{where} must be a positive finite number, got {safe_repr(value)}")
    return number


# am[implements a-rel-review-contract-1016@d0bea9]
def _invalid(message: str) -> RelevanceError:
    return RelevanceError("invalid-packet", message)

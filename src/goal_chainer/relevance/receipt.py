"""Purpose: assess a host's receipt for one attempt against what the decision it applied predicted, a review's proposal or a caller's own predictions, keeping each prediction predicted until an establishing observation inside the attempt's window checks it, and crediting the attempt only where an observation says the attempt produced what it saw.

The receipt is the host's record of one attempt (paper section 8.8): one application of one
decided action, when it was applied, when the host wrote the receipt, and what was observed.
The review fingerprint names a decision, not an application, so the attempt names the
application. This module decodes the receipt and the decision's predictions and links the one to
the other; `policy/outcome.metta` decides whether what the receipt states about its instants and
about production coheres, which observations count, each status and each attribution, by the
rules AgenticMind keeps for finished work (`state.lp` at 6df23ed2: completed, evidenced and
effect_confirmed are separate, and what finished work was for stays predicted until something
checks it):

    applied, nothing counted              every prediction stays predicted
    a counted observation confirms it     confirmed
    a counted observation contradicts it  missed
    counted observations disagree         conflicted
    not applied                           not-attempted; no observation counts

A prediction is an (about, target) pair: an effect on a dimension, a contribution to a goal, or a
literal a procedure's step achieves. `assess_receipt` judges a receipt against the review record
it names, whose proposal predicts effects and contributions and whose decision was made at its
as_of. `assess_attempt` makes the same judgement for any decision: its caller gives the
predictions and `decided_at`, when the decision was made, as a planner gives the Achieves
literals of the step it dispatched and the instant it dispatched it.

An observation counts when its estimator class can establish what happened (measured,
deterministic or human-asserted; section 8.2 makes model-proposed and receipt-calibrated values
estimates), the action was applied, the observation has a time after the application and not
after the same subject's next applied attempt, and the decision predicts what it is about; the
first of these that fails is the reason it is listed uncounted. A confirmed prediction says the
predicted outcome was seen after the attempt, not that the attempt caused it. The attribution is
`asserted` only when a counted observation agreeing with the status names the attempt in
`produced_by`, as W3C PROV states a generation and checks only its ordering. No assessment
reports a goal achieved: that is the host verifier's to establish.

    {
      "protocol": "goalchainer-relevance-receipt-v2",
      "review_fingerprint": "sha256:...",
      "action": "pause_recoverably",
      "attempt": "exec-276",
      "applied_at": "2026-10-16T09:02:00+00:00",
      "issued_at": "2026-10-16T09:10:00+00:00",
      "observations": [
        {"about": "effect", "target": "recoverability", "outcome": "confirmed",
         "estimator": "measured", "source": "checkpoint-store:cp-276",
         "observed_at": "2026-10-16T09:06:00+00:00", "produced_by": "exec-276"}
      ]
    }

`applied_at` is null when the host did not apply the action, and an observation is `about` an
effect, a contribution or what a step achieves. Every time is ISO-8601 with an offset, exact to
the microsecond, and is written back in UTC.

A receipt whose statements do not cohere is an `invalid-record`, its message naming the first
fault the policy's fault tables found and its details listing every one, each with the index of
the observation it is in: an application or an observation after the receipt was issued, a
producer other than the attempt, a producer named by an attempt that applied nothing or by an
observation not made after the application, an application before the decision was made, and a
next attempt not after this application.
A Receipt built in code rather than parsed is checked again by both assessments, its times first:
a time that is not a timezone-aware datetime is an invalid-record naming its field, while
`applied_at` and an observation's `observed_at` may still be None.

Every status, attribution, reason and fault name, and each fault's message, is the policy's: this
module checks the shape of each answer and fills a message's values, and keeps no copy of either.
Both the receipt's fault check and the assessment run under their caller's RunBudget, as every
policy call does; the relevance CLI gives one from its --inference-budget and --timeout-seconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Mapping, get_args

from ..domains.loader import vocabulary
from ..runtime.budget import RunBudget, caller_budget
from .errors import RelevanceError
from .instants import microseconds, parse_instant, utc_text
from .policy import body, constant, evaluate, items, symbol, term, text
from .records import check_record
from .canonical import fingerprint_of
from .review import REVIEW_PROTOCOL

RECEIPT_PROTOCOL = "goalchainer-relevance-receipt-v2"
ASSESSMENT_PROTOCOL = "goalchainer-relevance-assessment-v2"

_OBSERVATION_KEYS = frozenset(
    {"about", "target", "outcome", "estimator", "source", "observed_at", "produced_by", "note"}
)
_OBSERVATION_REQUIRED = frozenset({"about", "target", "outcome", "estimator", "source"})
_RECEIPT_KEYS = frozenset(
    {"protocol", "review_fingerprint", "action", "attempt", "applied_at", "issued_at", "observations"}
)
# Every field of a review record the assessment reads; the proposal is read only once the
# record says something was proposed.
_RECORD_SHAPE = {"protocol": str, "review_id": str, "fingerprint": str, "as_of": str, "disposition": str}
_PROPOSAL_SHAPE = {
    "action": str,
    "predicted_effects": [{"dimension": str, "band": str, "estimator": str}],
    "predicted_contributions": [{"goal": str, "band": str}],
}

# What a prediction or an observation is about: an effect on a dimension, a contribution to a
# goal, or a literal a procedure's step achieves, which no review proposal predicts. A prediction
# names its target as an observation does.
# am[implements a-rel-assess-attempt-1018@20e6ca]
About = Literal["effect", "contribution", "achieves"]
_ABOUT: tuple[str, ...] = get_args(About)
Prediction = tuple[About, str]


# am[implements a-rel-review-contract-1016@d0bea9] am[rests-on c-integrate-agenticmind-effects-1016@7fdbf0]
# am[implements a-rel-rcpt-v2-schema-1017@df2f55] am[implements a-rel-assess-attempt-1018@20e6ca]
@dataclass(frozen=True)
class Observation:
    about: About
    target: str
    outcome: Literal["confirmed", "contradicted"]
    estimator: str
    source: str
    observed_at: datetime | None = None
    produced_by: str | None = None
    note: str = ""

    def identity(self) -> dict[str, object]:
        """What was observed: every field but the note, which carries no decision-relevant meaning."""

        return {
            "about": self.about,
            "target": self.target,
            "outcome": self.outcome,
            "estimator": self.estimator,
            "source": self.source,
            "observed_at": None if self.observed_at is None else utc_text(self.observed_at),
            "produced_by": self.produced_by,
        }

    # One observation has one id in every receipt that carries it, so an outcome store keyed by it
    # counts the observation once (believe! fuses once per statement and source).
    # am[implements a-rel-rcpt-v2-assessment-1017@25ad31] am[addresses i-rel-rcpt-receipt-keyed-evidence-1017@55440a]
    @property
    def id(self) -> str:
        return fingerprint_of(self.identity())

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **self.identity(), "note": self.note}


# am[implements a-rel-review-contract-1016@d0bea9] am[implements a-rel-rcpt-v2-schema-1017@df2f55]
# am[rests-on c-rel-rcpt-fingerprint-not-attempt-1017@ffd849] am[rests-on c-rel-rcpt-nullable-applied-at-1017@a48394]
# am[addresses i-rel-rcpt-no-attempt-1017@92c323]
@dataclass(frozen=True)
class Receipt:
    review_fingerprint: str
    action: str
    attempt: str
    applied_at: datetime | None
    issued_at: datetime
    observations: tuple[Observation, ...]

    # What the receipt says, without notes: a resubmitted receipt has the same fingerprint, and a
    # store keeps per attempt the receipt issued last.
    # am[implements a-rel-rcpt-v2-assessment-1017@25ad31]
    @property
    def fingerprint(self) -> str:
        return fingerprint_of(
            {
                "protocol": RECEIPT_PROTOCOL,
                "review_fingerprint": self.review_fingerprint,
                "action": self.action,
                "attempt": self.attempt,
                "applied_at": None if self.applied_at is None else utc_text(self.applied_at),
                "issued_at": utc_text(self.issued_at),
                "observations": sorted({observation.id for observation in self.observations}),
            }
        )


# Time: o observations decoded, then one policy call of 1 + 4o row checks.
# am[implements a-rel-review-contract-1016@d0bea9] am[implements a-rel-rcpt-v2-schema-1017@df2f55]
# am[implements a-rel-rcpt-v2-metta-rules-1018@c22bf6] am[implements a-rel-mig-receipt-1018@6f384d]
# am[rests-on c-rel-rcpt-budget-required-1018@4eed67]
def parse_receipt(payload: Any, *, budget: RunBudget) -> Receipt:
    """The receipt `payload` states, its fault check charged to `budget`. Raises InvalidInputError
    when `budget` is not a RunBudget and RelevanceError invalid-record for a receipt that is
    malformed or whose statements do not cohere."""

    budget = caller_budget(budget, "a receipt check")
    if not isinstance(payload, Mapping):
        raise _invalid(f"a receipt must be a {RECEIPT_PROTOCOL} object")
    unknown = sorted(set(payload) - _RECEIPT_KEYS)
    missing = sorted(_RECEIPT_KEYS - set(payload))
    if payload.get("protocol") != RECEIPT_PROTOCOL or unknown or missing:
        raise _invalid(
            f"a receipt must be a {RECEIPT_PROTOCOL} object, not {payload.get('protocol')!r} "
            f"with unknown fields {unknown} and missing {missing}"
        )
    if not isinstance(payload["observations"], list):
        raise _invalid("receipt.observations must be a list")
    receipt = Receipt(
        review_fingerprint=_text(payload["review_fingerprint"], "receipt.review_fingerprint"),
        action=_text(payload["action"], "receipt.action"),
        attempt=_text(payload["attempt"], "receipt.attempt"),
        applied_at=None if payload["applied_at"] is None else _instant(payload["applied_at"], "receipt.applied_at"),
        issued_at=_instant(payload["issued_at"], "receipt.issued_at"),
        observations=tuple(_observation(item, index) for index, item in enumerate(payload["observations"])),
    )
    check_receipt(receipt, budget=budget)
    return receipt


# The one recheck of a receipt: parse_receipt and both assessments run it, and a caller that reads a
# receipt's times itself, such as the planner cutting receipts at a plan's time, runs it first. A
# Receipt can be built without parse_receipt, so it checks the times first, a time that is no
# timezone-aware instant being an invalid-record before any time is compared, and then refuses a
# receipt whose statements the policy's receipt and observation fault tables reject.
# Time: one policy call of 1 + 4o row checks, o observations.
# am[implements a-rel-rcpt-v2-metta-rules-1018@c22bf6] am[implements a-rel-mig-receipt-1018@6f384d]
# am[implements a-rel-assess-attempt-1018@20e6ca] am[implements a-integrate-built-receipt-instant-refusal-1018@43fdb6]
# am[implements a-rel-check-receipt-public-1018@ac8018] am[rests-on c-rel-track-cut-before-check-9bd1769-1018]
def check_receipt(receipt: Receipt, *, budget: RunBudget) -> Receipt:
    """`receipt`, once its times and statements are shown to cohere, its fault check charged to
    `budget`. Raises InvalidInputError when `budget` is not a RunBudget and RelevanceError
    invalid-record for a time that is no timezone-aware instant or a statement the fault tables
    refuse."""

    budget = caller_budget(budget, "a receipt check")
    _times(receipt)
    faults = evaluate(
        "gc-relevance-receipt-faults",
        _attempt_term(receipt),
        microseconds(receipt.issued_at),
        items(_observation_term(index, observation) for index, observation in enumerate(receipt.observations)),
        budget=budget,
    )
    _refuse(_faults(faults, len(receipt.observations)), receipt)
    return receipt


# Each time a Receipt carries is a timezone-aware datetime, None only where a receipt allows none:
# applied_at when nothing was applied, and an observation's observed_at when it is untimed. A
# parsed receipt always passes, since parse_instant answers only aware instants; one built in code
# may carry any value, which the policy's terms would turn into a TypeError.
# Time: one check per time, 2 + o, o observations.
# am[implements a-integrate-built-receipt-instant-refusal-1018@43fdb6] am[rests-on c-rel-attempt-inputs-invalid-record-1018@8bbff3]
def _times(receipt: Receipt) -> None:
    if receipt.applied_at is not None:
        _aware(receipt.applied_at, "receipt.applied_at")
    _aware(receipt.issued_at, "receipt.issued_at")
    for index, observation in enumerate(receipt.observations):
        if observation.observed_at is not None:
            _aware(observation.observed_at, f"receipt.observations[{index}].observed_at")


# am[implements a-rel-review-contract-1016@d0bea9] am[implements a-rel-rcpt-v2-schema-1017@df2f55]
# am[implements a-rel-assess-attempt-1018@20e6ca]
def _observation(item: Any, index: int) -> Observation:
    where = f"receipt.observations[{index}]"
    if not isinstance(item, Mapping):
        raise _invalid(f"{where} must be an object")
    unknown = sorted(set(item) - _OBSERVATION_KEYS)
    missing = sorted(_OBSERVATION_REQUIRED - set(item))
    if unknown or missing:
        raise _invalid(f"{where} fields: unknown {unknown}, missing {missing}")
    if item["about"] not in _ABOUT:
        raise _invalid(f"{where}.about must be one of {', '.join(_ABOUT)}")
    if item["outcome"] not in ("confirmed", "contradicted"):
        raise _invalid(f"{where}.outcome must be confirmed or contradicted")
    if item["estimator"] not in vocabulary().classes:
        raise _invalid(f"{where}.estimator must be one of {', '.join(vocabulary().classes)}")
    note = item.get("note", "")
    if not isinstance(note, str):
        raise _invalid(f"{where}.note must be text")
    return Observation(
        about=item["about"],
        target=_text(item["target"], f"{where}.target"),
        outcome=item["outcome"],
        estimator=item["estimator"],
        source=_text(item["source"], f"{where}.source"),
        observed_at=None if item.get("observed_at") is None else _instant(item["observed_at"], f"{where}.observed_at"),
        produced_by=None if item.get("produced_by") is None else _text(item["produced_by"], f"{where}.produced_by"),
        note=note,
    )


# Time: the receipt's 1 + 4o fault checks, o observations deduplicated by id, then the outcome
# policy's 2 assessment-table checks, 6 * o counting-table checks and p * o comparisons for p
# predictions, both calls charged to the caller's budget.
# am[implements a-rel-assess-attempt-1018@20e6ca] am[rests-on c-rel-decided-at-follows-readings-1018@8c479a]
# am[rests-on c-rel-attempt-inputs-invalid-record-1018@8bbff3] am[rests-on c-rel-rcpt-budget-required-1018@4eed67]
# am[rests-on c-integrate-agenticmind-effects-1016@7fdbf0] am[rests-on c-rel-next-attempt-at-final-1017@a3d73f]
def assess_attempt(
    predictions: tuple[Prediction, ...] | list[Prediction], receipt: Receipt, *, decided_at: datetime,
    budget: RunBudget, next_attempt_at: datetime | None = None,
) -> dict[str, object]:
    """The status and attribution of each of `predictions`, in order, given what the receipt observed.

    Each prediction is an (about, target) pair naming its target as the receipt's observations
    name theirs. `decided_at` is when the decision the attempt applied was made, and no reading
    the decision rested on may follow it: an application before it is refused, and an
    observation counts only after the application, so the decision's own evidence never comes
    back as its outcome. A refusal names the decision by the receipt's review_fingerprint.

    `next_attempt_at` is when the same subject's next applied attempt was applied, which closes
    this attempt's window: an observation made after it is of the next attempt's state. None
    means no later applied attempt is known, and the window closes when the receipt was issued:
    a receipt reporting an observation after that is refused. Predictions that are not such
    pairs, or an instant without an offset, are an invalid-record. The receipt's fault check and
    the assessment are charged to `budget`; one that is not a RunBudget is an InvalidInputError.
    """

    budget = caller_budget(budget, "a receipt assessment")
    predicted = _predictions(predictions)
    check_receipt(receipt, budget=budget)
    return _assess(predicted, receipt, decided_at, receipt.review_fingerprint, budget, next_attempt_at)


# The review case of assess_attempt: the proposal's effects and then its contributions are the
# predictions, the review's as_of is when its decision was made and its id names it in a refusal,
# and the record carries the review's names and each prediction's band beside its verdict.
# Time: assess_attempt's, p = the proposal's effects and contributions.
# am[implements a-rel-review-contract-1016@d0bea9] am[rests-on c-integrate-agenticmind-effects-1016@7fdbf0]
# am[rests-on c-rel-establishing-classes-1016@72edbb] am[implements a-rel-rcpt-v2-assessment-1017@25ad31]
# am[rests-on c-rel-next-attempt-at-final-1017@a3d73f] am[addresses i-ev-pl-stale-observation-credits-1017@4583b7]
# am[addresses i-rel-rcpt-unbounded-window-1017@7c2587] am[addresses i-rel-rcpt-confirmation-not-attribution-1017@de2720]
# am[implements a-rel-rcpt-v2-metta-rules-1018@c22bf6] am[implements a-rel-mig-receipt-1018@6f384d]
# am[rests-on c-rel-rcpt-budget-required-1018@4eed67] am[implements a-rel-assess-attempt-1018@20e6ca]
def assess_receipt(
    review_record: Mapping[str, Any], receipt: Receipt, *, budget: RunBudget, next_attempt_at: datetime | None = None
) -> dict[str, object]:
    """The status and attribution of each prediction of the proposal in `review_record`, the
    review the receipt names, given what the receipt observed. `next_attempt_at` and `budget`
    are assess_attempt's; a record that is not that review proposing the receipt's action is an
    invalid-record."""

    budget = caller_budget(budget, "a receipt assessment")
    check_receipt(receipt, budget=budget)
    proposal, as_of = _proposal(review_record, receipt)
    predictions = [("effect", effect["dimension"]) for effect in proposal["predicted_effects"]] + [
        ("contribution", contribution["goal"]) for contribution in proposal["predicted_contributions"]
    ]
    assessed = _assess(predictions, receipt, as_of, review_record["review_id"], budget, next_attempt_at)
    judged = [{key: verdict[key] for key in ("status", "attribution", "observations")}
              for verdict in assessed["predictions"]]
    effects = [
        {**{k: effect[k] for k in ("dimension", "band", "estimator")}, **judged[index]}
        for index, effect in enumerate(proposal["predicted_effects"])
    ]
    offset = len(effects)
    contributions = [
        {"goal": contribution["goal"], "band": contribution["band"], **judged[offset + index]}
        for index, contribution in enumerate(proposal["predicted_contributions"])
    ]
    return {
        "protocol": ASSESSMENT_PROTOCOL,
        "review_id": review_record["review_id"],
        "fingerprint": review_record["fingerprint"],
        "action": receipt.action,
        **{key: assessed[key] for key in ("attempt", "applied", "applied_at", "issued_at", "next_attempt_at",
                                          "receipt_fingerprint")},
        "completion_confirms_effects": False,
        "effects": effects,
        "contributions": contributions,
        "goals": [
            {"goal": contribution["goal"], "achievement": "unverified"}
            for contribution in proposal["predicted_contributions"]
        ],
        "uncounted": assessed["uncounted"],
    }


# The judgement both entries make, the receipt already checked. `decision` names the decision in
# a refusal's message: the review's id, or the receipt's review_fingerprint.
# Time: one policy call of 2 assessment-table checks, 6 * o counting-table checks and p * o
# comparisons, o observations deduplicated by id, p predictions.
# am[implements a-rel-assess-attempt-1018@20e6ca] am[implements a-rel-rcpt-v2-assessment-1017@25ad31]
# am[rests-on c-rel-assessment-table-names-decision-1018@738b65]
def _assess(
    predictions: list[Prediction], receipt: Receipt, decided_at: Any, decision: str, budget: RunBudget,
    next_attempt_at: Any,
) -> dict[str, object]:
    decided_at = _aware(decided_at, "decided_at")
    if next_attempt_at is not None:
        next_attempt_at = _aware(next_attempt_at, "next_attempt_at")
    distinct: dict[str, Observation] = {}
    for observation in receipt.observations:
        distinct.setdefault(observation.id, observation)
    observed = list(distinct.values())
    answer = evaluate(
        "gc-relevance-assess",
        _attempt_term(receipt),
        microseconds(decided_at),
        constant("Forever") if next_attempt_at is None else term("Until", microseconds(next_attempt_at)),
        items(term("Prediction", about, target) for about, target in predictions),
        items(_observation_term(index, observation) for index, observation in enumerate(observed)),
        budget=budget,
    )
    refused = _refusal(answer)
    if refused is not None:
        _refuse(_faults(refused, 0), receipt, decision=decision, decided_at=decided_at,
                next_attempt_at=next_attempt_at)
    statuses, uncounted = _assessment(answer, predictions, len(observed))
    return {
        "attempt": receipt.attempt,
        "applied": receipt.applied_at is not None,
        "applied_at": _written(receipt.applied_at),
        "issued_at": utc_text(receipt.issued_at),
        "next_attempt_at": _written(next_attempt_at),
        "receipt_fingerprint": receipt.fingerprint,
        "predictions": [
            {"about": about, "target": target, "status": status, "attribution": attribution,
             "observations": [observed[i].to_dict() for i in seen]}
            for (about, target), (status, attribution, seen) in zip(predictions, statuses)
        ],
        "uncounted": [{"reason": reason, "observation": observed[index].to_dict()} for index, reason in uncounted],
    }


# The caller's predictions as (about, target) pairs; the first that is not one is an invalid-record.
# am[implements a-rel-assess-attempt-1018@20e6ca] am[rests-on c-rel-attempt-inputs-invalid-record-1018@8bbff3]
def _predictions(predictions: Any) -> list[Prediction]:
    if not isinstance(predictions, (tuple, list)):
        raise _invalid("predictions must be a sequence of (about, target) pairs")
    checked = []
    for index, prediction in enumerate(predictions):
        where = f"predictions[{index}]"
        if not isinstance(prediction, (tuple, list)) or len(prediction) != 2:
            raise _invalid(f"{where} must be an (about, target) pair")
        about, target = prediction
        if about not in _ABOUT:
            raise _invalid(f"{where} must be about one of {', '.join(_ABOUT)}, not {about!r}")
        checked.append((about, _text(target, f"{where}.target")))
    return checked


# am[implements a-rel-assess-attempt-1018@20e6ca] am[rests-on c-rel-attempt-inputs-invalid-record-1018@8bbff3]
def _aware(moment: Any, where: str) -> datetime:
    if not isinstance(moment, datetime) or moment.utcoffset() is None:
        raise _invalid(f"{where} must be a datetime with a timezone offset")
    return moment


# The attempt and each observation as the outcome policy reads them, one representation for its
# fault tables and its counting table.
# am[implements a-rel-rcpt-v2-metta-rules-1018@c22bf6]
def _attempt_term(receipt: Receipt) -> Any:
    application = (
        constant("NotApplied") if receipt.applied_at is None else term("Applied", microseconds(receipt.applied_at))
    )
    return term("Attempt", receipt.attempt, application)


# am[implements a-rel-rcpt-v2-metta-rules-1018@c22bf6]
def _observation_term(index: int, observation: Observation) -> Any:
    return term(
        "Observation", index, observation.about, observation.target, observation.outcome, observation.estimator,
        constant("Untimed") if observation.observed_at is None else term("At", microseconds(observation.observed_at)),
        constant("Unstated") if observation.produced_by is None else term("ProducedBy", observation.produced_by),
    )


# The faults of a (Refused FAULTS) answer, or None for any other answer.
# am[implements a-rel-rcpt-v2-metta-rules-1018@c22bf6]
def _refusal(answer: Any) -> Any:
    try:
        return body(answer, "Refused")
    except ValueError:
        return None


# The policy's ((Fault REASON SUBJECT MESSAGE) ...) as (reason, observation index or None for the
# receipt, message), in the order the policy judged them; an index names one of the `observed`
# observations.
# am[implements a-rel-rcpt-v2-metta-rules-1018@c22bf6]
def _faults(answer: Any, observed: int) -> list[tuple[str, int | None, str]]:
    try:
        if not isinstance(answer, tuple):
            raise ValueError(f"expected a list of faults, got {answer!r}")
        faults = []
        for item in answer:
            if not isinstance(item, tuple) or len(item) != 4 or symbol(item[0]) != "Fault":
                raise ValueError(f"expected (Fault ...), got {item!r}")
            reason, subject, message = text(item[1]), item[2], text(item[3])
            if isinstance(subject, int) and not isinstance(subject, bool):
                if not 0 <= subject < observed:
                    raise ValueError(f"a fault in an observation outside the receipt: {item!r}")
                faults.append((reason, subject, message))
            elif symbol(subject) == "Receipt":
                faults.append((reason, None, message))
            else:
                raise ValueError(f"unknown subject in {item!r}")
        return faults
    except (ValueError, TypeError) as error:
        raise RelevanceError("engine-output-invalid", f"the outcome policy answered {error}") from error


# A refused receipt's invalid-record says what its first fault is, the policy's message filled
# with the receipt's values, and lists every fault.
# am[implements a-rel-rcpt-v2-metta-rules-1018@c22bf6] am[implements a-rel-assess-attempt-1018@20e6ca]
# am[rests-on c-rel-assessment-table-names-decision-1018@738b65]
def _refuse(
    faults: list[tuple[str, int | None, str]], receipt: Receipt, *, decision: str | None = None,
    decided_at: datetime | None = None, next_attempt_at: datetime | None = None,
) -> None:
    if not faults:
        return
    _, index, message = faults[0]
    observation = None if index is None else receipt.observations[index]
    values = {
        "where": "receipt" if index is None else f"receipt.observations[{index}]",
        "attempt": receipt.attempt,
        "applied": _written(receipt.applied_at),
        "issued": _written(receipt.issued_at),
        "observed": None if observation is None else _written(observation.observed_at),
        "producer": None if observation is None else observation.produced_by,
        "decision": decision,
        "decided": _written(decided_at),
        "next": _written(next_attempt_at),
    }
    raise RelevanceError(
        "invalid-record",
        message.format_map(values),
        details={"faults": [{"reason": reason, "observation": at} for reason, at, _ in faults]},
    )


# am[implements a-rel-rcpt-v2-metta-rules-1018@c22bf6]
def _written(moment: datetime | None) -> str | None:
    return None if moment is None else utc_text(moment)


# Every observation is either counted toward the predictions about its target or listed once with
# its reason, never both, which the answer is checked for.
# am[implements a-rel-review-contract-1016@d0bea9] am[implements a-rel-rcpt-v2-assessment-1017@25ad31]
def _assessment(
    answer: Any, predictions: list[tuple[str, str]], observed: int
) -> tuple[list[tuple[str, str, tuple[int, ...]]], list[tuple[int, str]]]:
    """The policy's (Assessment ...) as one (status, attribution, observation indexes) per prediction,
    in order, and the (index, reason) of each observation it did not count."""

    try:
        if not isinstance(answer, tuple) or len(answer) != 3 or symbol(answer[0]) != "Assessment":
            raise ValueError(f"expected (Assessment ...), got {answer!r}")
        _, rows, listed = answer
        if len(rows) != len(predictions):
            raise ValueError(f"{len(rows)} statuses for {len(predictions)} predictions")
        statuses = []
        for row, (kind, target) in zip(rows, predictions):
            if not isinstance(row, tuple) or len(row) != 6 or symbol(row[0]) != "Status":
                raise ValueError(f"expected (Status ...), got {row!r}")
            _, about, named, status, attribution, seen = row
            if (text(about), text(named)) != (kind, target):
                raise ValueError(f"unexpected status {row!r} for {kind} {target}")
            statuses.append((text(status), text(attribution), tuple(seen)))
        uncounted = []
        for item in listed:
            if not isinstance(item, tuple) or len(item) != 3 or symbol(item[0]) != "Uncounted":
                raise ValueError(f"expected (Uncounted ...), got {item!r}")
            uncounted.append((item[1], text(item[2])))
        counted = {i for _, _, seen in statuses for i in seen}
        indexes = [*counted, *(i for i, _ in uncounted)]
        if any(not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < observed for i in indexes):
            raise ValueError("an observation index outside the receipt")
        if len(indexes) != observed or len(set(indexes)) != observed:
            raise ValueError("an observation neither counted nor listed once")
        return statuses, uncounted
    except (ValueError, TypeError) as error:
        raise RelevanceError("engine-output-invalid", f"the outcome policy answered {error}") from error


# The record's proposal and as_of, once the record is shown to be the review the receipt names.
# am[implements a-rel-review-contract-1016@d0bea9] am[implements a-rel-rcpt-v2-schema-1017@df2f55]
def _proposal(review_record: Mapping[str, Any], receipt: Receipt) -> tuple[Mapping[str, Any], datetime]:
    check_record(review_record, _RECORD_SHAPE, "review record")
    if review_record["protocol"] != REVIEW_PROTOCOL:
        raise _invalid(f"a receipt is assessed against a {REVIEW_PROTOCOL} record")
    if review_record["fingerprint"] != receipt.review_fingerprint:
        raise _invalid(
            f"the receipt names review {receipt.review_fingerprint}, "
            f"but the record is {review_record['fingerprint']}"
        )
    as_of = _instant(review_record["as_of"], "review record.as_of")
    if review_record["disposition"] != "propose":
        raise _invalid(
            f"review {review_record['review_id']} proposed nothing "
            f"(disposition {review_record['disposition']}), so no receipt can credit it"
        )
    proposal = check_record(review_record.get("proposal"), _PROPOSAL_SHAPE, "review record.proposal")
    if proposal["action"] != receipt.action:
        raise _invalid(f"the receipt is for {receipt.action}, but the review proposed {proposal['action']}")
    return proposal, as_of


# am[implements a-rel-rcpt-v2-instants-1017@3a3b0d]
def _instant(value: Any, where: str) -> datetime:
    written = _text(value, where)
    try:
        return parse_instant(written)
    except ValueError as error:
        raise _invalid(f"{where} {error}, got {written!r}") from None


# am[implements a-rel-review-contract-1016@d0bea9]
def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"{where} must be nonempty text")
    return value


# am[implements a-rel-review-contract-1016@d0bea9]
def _invalid(message: str) -> RelevanceError:
    return RelevanceError("invalid-record", message)

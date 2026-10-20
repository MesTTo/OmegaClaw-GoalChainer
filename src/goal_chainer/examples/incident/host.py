"""Purpose: be the incident example's host: prepare a reviewed proposal's artifact from the incident record its caller supplies, once the review is still fresh against the current packet and the review of that packet proposes the same action under the same standing, check it for the record's restricted raw-log values, and settle the execution's conditions under the host's own authorization.

The review says *what* it proposes and leaves authorization unresolved; the host decides whether to
take the step. Given the step, this prepares the proposed action's artifact on the caller's raw
incident log (customer emails, order IDs, tokens, ...) and checks the artifact against those values.
Which fields are restricted is the settlement policy's allowlist (settlement.metta); the JSON seal
and the containment scan are the mechanism here. It sends nothing. A host may release an artifact
whose check passed; one whose check failed is withheld, see execution.py.

    stored = relevance.review(packaged_domain("incident", budget=budget), packet, budget=budget).to_dict()
    execution = prepare_proposal(stored, record, authorization, packet=current, budget=current.budget.run_budget())

`current` is the packet for the review's subject as it reads now; the host prepares nothing unless
the stored review is still fresh against it and the review of it, run again under the caller's
budget, proposes the same action under the same deontic standing. That second check is of the
outcome the host consumes, not of the record: the review id and fingerprint the execution's
readset names are taken as the caller gives them, and no other field of the record decides what
is prepared.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from metta import Expression, Grounded, S

from ...deontic_engine import DEONTIC_STATUSES
from ...domains.loader import packaged_domain
from ...errors import GoalChainerError, InvalidInputError
from ...relevance.errors import RelevanceError
from ...relevance.freshness import check_freshness
from ...relevance.packet import ReviewPacket
from ...relevance.policy import stopped
from ...relevance.records import check_record
from ...relevance.review import REVIEW_PROTOCOL, engine_identity, review as relevance_review
from ...runtime.budget import BudgetExhausted, RunBudget
from .execution import Authorization, ExecutionResult, PreparedArtifact, PrivacyCheck, settle

PRIVACY_METHOD = "restricted-raw-log-value-containment"
# The fields of a review record the host reads, in the shapes review records carry them, which
# relevance's own readers check the same way (relevance.receipt reads its fields so): nothing else
# of the record is read, so nothing else is checked.
# am[implements a-integrate-example-host-inputs-1018@f0d0fa]
_READ_REVIEW = {"review_id": str, "fingerprint": str}
# am[implements a-integrate-example-host-inputs-1018@f0d0fa]
_READ_PROPOSAL = {"action": str, "deontic": str}
# Each action the host prepares an artifact for, with that artifact's kind, audience and intended
# effect; its payload is built from the caller's record by _payload.
# am[implements a-ev-execution-contract@7acc73] am[implements a-integrate-example-host-inputs-1018@f0d0fa]
_ARTIFACTS = {
    "publish_redacted_summary": ("redacted-status-update", "external", "the redacted status update was published"),
    "publish_raw_log": ("raw-incident-log", "external", "the raw incident log was shared with the response channel"),
    "hold_external_update": (
        "internal-hold-note", "internal", "external updates stayed held while the facts were checked",
    ),
}


# A stored review whose support moved after it was decided: `details` is the freshness report,
# naming each reading, digest, engine field or authority that moved. The host prepares nothing for
# it, and the refusal says nothing about which outcome is right; only a new review decides that.
# am[implements a-ie-host-freshness-1018@ff618a]
class StaleReview(GoalChainerError):
    code = "stale_review"


# The host's side of one reviewed proposal. The review chose the action and the host decided
# whether to take the step; this does neither. Only an authorized step prepares the artifact, and
# the execution's conditions are settled from the proposal's deontic standing, the host's
# authorization and the artifact's check. What the execution read is the review it acted on.
# Every field it reads is checked before anything is prepared, and an authorized step for a
# proposal the settlement holds inadmissible, which the review's ranking never proposes, is refused
# before its artifact is prepared. Between the two, the stored review is checked against the
# current packet and the review is run again on that packet, so nothing is settled from a review
# whose support moved or from an action or standing the current evidence and norms do not reach.
# am[implements a-ie-s5-incident-host-1018@53176a] am[rests-on c-ie-agents-no-predetermined-1018@4c36f6]
# am[implements a-integrate-example-host-inputs-1018@f0d0fa] am[implements a-ie-host-freshness-1018@ff618a]
# am[implements a-ie-host-recompute-proposal-1018@898c26]
def prepare_proposal(
    review: Mapping[str, Any],
    record: Mapping[str, Any],
    authorization: Authorization,
    *,
    packet: ReviewPacket,
    budget: RunBudget,
) -> ExecutionResult:
    """Prepare and settle the review record's proposal for the caller's incident record.

    `review` is a goalchainer-relevance-review-v2 record, as ReviewResult.to_dict() and a domain
    request's `review` give it, and `packet` the current ReviewPacket for its subject; `budget` is
    no looser than the packet's bounds and pays for the freshness check, the review run again and
    the artifact's policy reads. Raises InvalidInputError for another record, for a review that
    proposes nothing, for an authorization that is not one, for a review id, fingerprint, proposed
    action or deontic standing that is missing or not text, for a standing that is no deontic
    status or an action this host prepares nothing for, for a review record the freshness check
    cannot read, for a packet that is not one or a budget looser than it, for a proposed action
    and standing the review of the current packet does not reach, for an authorized step the
    standing makes inadmissible, and for a record this host cannot prepare from. Raises
    StaleReview, whose details are the freshness report, for a review whose support moved, and
    RelevanceError for a packet about another subject (subject-mismatch) or for the engine or
    budget stopping the check or the review (runtime-unavailable, engine-failed, review-timeout,
    review-budget-exceeded).
    """

    if not isinstance(review, Mapping) or review.get("protocol") != REVIEW_PROTOCOL:
        raise InvalidInputError(
            f"The incident host prepares the proposal of a {REVIEW_PROTOCOL} record.",
            details={"protocol": review.get("protocol") if isinstance(review, Mapping) else None},
        )
    proposal = review.get("proposal")
    if proposal is None:
        raise InvalidInputError(
            "The review proposes no action, so the host has nothing to prepare.",
            details={"review_id": review.get("review_id"), "disposition": review.get("disposition")},
        )
    if not isinstance(authorization, Authorization):
        raise InvalidInputError("The host's decision must be an Authorization.",
                                details={"authorization": repr(authorization)[:200]})
    try:
        check_record(review, _READ_REVIEW, "review record")
        check_record(proposal, _READ_PROPOSAL, "review record.proposal")
    except RelevanceError as error:
        raise InvalidInputError(f"The incident host cannot read the review it acts on: {error.message}.",
                                details={"fault": error.message}) from None
    action, deontic = proposal["action"], proposal["deontic"]
    if deontic not in DEONTIC_STATUSES:
        raise InvalidInputError(f"The proposal's deontic standing {deontic} is no deontic status.",
                                details={"deontic": deontic, "statuses": list(DEONTIC_STATUSES)})
    _artifact_shape(action)
    _check_fresh(review, packet, budget)
    _check_reached(review, packet, budget)
    if authorization.granted and settle("gc-settle-admissible", S[deontic], budget=budget) is not True:
        raise InvalidInputError(f"A {deontic} proposal cannot be authorized, so the host prepares nothing for it.",
                                details={"action": action, "deontic": deontic})
    artifact = prepare_artifact(action, record, budget=budget) if authorization.granted else None
    return ExecutionResult(
        action_id=action,
        norm_status=deontic,
        authorization=authorization,
        artifact=artifact,
        readset={"kind": "relevance-review", "review_id": review["review_id"], "fingerprint": review["fingerprint"]},
        budget=budget,
    )


# Whether the stored review still has the support it was decided on: relevance's freshness check
# of the record against the caller's current packet, under the packaged incident domain and the
# engine this process runs, all charged to the caller's budget once it is admitted as no looser
# than the packet's, as the check itself admits it. A record the check cannot read is refused like
# any field the host reads; a subject mismatch and the engine's and budget's failures keep
# relevance's types, a used-up budget included.
# am[implements a-ie-host-freshness-1018@ff618a]
def _check_fresh(review: Mapping[str, Any], packet: ReviewPacket, budget: RunBudget) -> None:
    if not isinstance(packet, ReviewPacket):
        raise InvalidInputError("The host checks the review against the current ReviewPacket for its subject.",
                                details={"packet": type(packet).__name__})
    try:
        budget = packet.budget.admit(budget, "the incident host's freshness check")
    except BudgetExhausted as error:
        raise stopped(error) from error
    try:
        report = check_freshness(review, packaged_domain("incident", budget=budget), packet,
                                 engine_identity(budget=budget), budget=budget)
    except RelevanceError as error:
        if error.code != "invalid-record":
            raise
        raise InvalidInputError(f"The incident host cannot read the review it acts on: {error.message}.",
                                details={"fault": error.message}) from None
    if report.status != "fresh":
        raise StaleReview(
            f"Review {report.review_id} no longer has the support it was decided on, so the host prepares nothing for it.",
            details=report.to_dict(),
        )


# Whether the review of the current packet reaches what the host consumes of the stored review: its
# proposed action under that action's deontic standing. The review runs again as a domain request
# runs it, under the packaged incident domain and the caller's budget, so the standing the
# execution settles from is one the current evidence and norms derive, and nothing else of the
# stored record, its candidates and readset included, decides what is prepared. A current review
# proposing nothing, or another action or standing, is refused with both outcomes in its details.
# This checks the consumed outcome's consistency, not the record's authenticity, and the engine's
# and budget's failures keep relevance's types.
# Time: one relevance review of `packet` against the incident domain, charged to `budget`.
# am[implements a-ie-host-recompute-proposal-1018@898c26] am[rests-on c-ie-recompute-not-authentication-1018@d54d09]
def _check_reached(review: Mapping[str, Any], packet: ReviewPacket, budget: RunBudget) -> None:
    current = relevance_review(packaged_domain("incident", budget=budget), packet, budget=budget).to_dict()
    consumed = {name: review["proposal"][name] for name in _READ_PROPOSAL}
    proposal = current["proposal"]
    reached = None if proposal is None else {name: proposal[name] for name in _READ_PROPOSAL}
    if reached != consumed:
        now = (f"proposes nothing ({current['disposition']})" if reached is None
               else f"proposes {reached['action']} as {reached['deontic']}")
        raise InvalidInputError(
            f"Review {review['review_id']} proposes {consumed['action']} as {consumed['deontic']}, but the "
            f"review of the current packet {now}, so the host prepares nothing for it.",
            details={"review_id": review["review_id"], "consumed": consumed,
                     "current": {"disposition": current["disposition"], "proposal": reached}},
        )


# The kind, audience and intended effect of the action's artifact, refusing an action this host
# prepares nothing for.
# am[implements a-integrate-example-host-inputs-1018@f0d0fa]
def _artifact_shape(action_id: Any) -> tuple[str, str, str]:
    shape = _ARTIFACTS.get(action_id) if isinstance(action_id, str) else None
    if shape is None:
        raise InvalidInputError(f"The incident host prepares no artifact for the action {action_id}.",
                                details={"action": action_id if isinstance(action_id, str) else repr(action_id)})
    return shape


# am[implements a-ev-mr-privacy-classes@d79884] am[addresses i-ev-privacy-denylist@9fa13e]
# am[implements a-ev-rb-pipeline-budget-1018@988a39]
def field_classes(fields: Iterable[str], *, budget: RunBudget) -> dict[str, str]:
    """Each raw-log field's class, "diagnostic" or "restricted", as the settlement policy assigns it."""

    names = sorted(fields)
    answer = settle("gc-settle-field-classes", Expression(*(Grounded(name) for name in names)), budget=budget)
    return {name: str(kind) for _, name, kind in answer}


# am[implements a-ev-mr-privacy-classes@d79884]
# am[implements a-ev-rb-pipeline-budget-1018@988a39]
def redact(raw_log: Mapping[str, Any], *, budget: RunBudget) -> dict[str, Any]:
    """Keep each diagnostic field's value and redact every other field's."""

    classes = field_classes(raw_log, budget=budget)
    return {
        key: value if classes[key] == "diagnostic" else "[redacted]"
        for key, value in raw_log.items()
    }


# Every value an artifact holds is the caller's record's; the host supplies only each action's
# artifact shape and, for the hold, its internal note.
# am[implements a-ev-execution-contract@7acc73]
# am[addresses i-ev-privacy-fails-open@8ec490]
# am[rests-on c-ev-raw-log-fake-completion@2d8cf2]
# am[implements a-ev-rb-pipeline-budget-1018@988a39] am[implements a-ie-s5-incident-host-1018@53176a]
# am[implements a-integrate-example-host-inputs-1018@f0d0fa]
def prepare_artifact(action_id: str, incident: Mapping[str, Any], *, budget: RunBudget) -> PreparedArtifact:
    """Prepare the artifact for one action from the caller's incident record and check it;
    nothing is sent anywhere.

    The host holds no norm: whether the step may be taken is decided before this is called. A raw
    log is therefore prepared like any other artifact, and its check fails on a record whose log
    holds restricted values, which withholds it. The policy reads it makes are charged to `budget`.
    """

    if not isinstance(incident, Mapping):
        raise InvalidInputError("An incident record must be a mapping.", details={"record": repr(incident)[:200]})
    raw_log = incident.get("raw_log", {})
    if not isinstance(raw_log, Mapping) or not all(isinstance(key, str) for key in raw_log):
        raise InvalidInputError("An incident record's raw_log must be a mapping with text keys.")
    kind, audience, effect = _artifact_shape(action_id)
    if action_id == "publish_redacted_summary":
        payload: dict[str, Any] = {
            "service": incident.get("service"),
            "status": incident.get("status"),
            "summary": incident.get("summary"),
            "diagnostics": redact(raw_log, budget=budget),
            "next_update": incident.get("next_update"),
        }
    elif action_id == "publish_raw_log":
        payload = {"service": incident.get("service"), "raw_log": dict(raw_log)}
    else:
        payload = {
            "internal_note": "Holding external updates until the facts are verified.",
            "internal_detail_available": bool(raw_log),
        }
    return PreparedArtifact.checked(
        action_id=action_id,
        kind=kind,
        audience=audience,
        intended_effect=effect,
        payload=payload,
        privacy=check_privacy(payload, raw_log, budget=budget),
    )


# Time: O(f * |payload|) substring scans for f restricted fields present in raw_log.
# am[implements a-ev-execution-contract@7acc73] am[implements a-ev-mr-privacy-classes@d79884]
# am[implements a-ev-rb-pipeline-budget-1018@988a39]
def check_privacy(payload: Mapping[str, Any], raw_log: Mapping[str, Any], *, budget: RunBudget) -> PrivacyCheck:
    """Search the artifact's canonical JSON for each restricted raw-log value.

    Values are searched in their JSON-escaped form, the form they take inside the
    dumped artifact, so a value holding quotes or backslashes is still found. An
    empty value cannot leak and is not listed as covered. A field the policy does
    not declare diagnostic is restricted, so a field nobody listed is searched for.
    """

    classes = field_classes(raw_log, budget=budget)
    dumped = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    covered: list[str] = []
    leaked: list[str] = []
    for key in sorted(raw_log):
        if classes[key] != "restricted":
            continue
        needle = _needle(raw_log[key])
        if not needle:
            continue
        covered.append(key)
        if needle in dumped:
            leaked.append(key)
    return PrivacyCheck(PRIVACY_METHOD, tuple(covered), tuple(leaked))


# am[implements a-ev-execution-contract@7acc73]
def _needle(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)[1:-1]
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


__all__ = [
    "PRIVACY_METHOD",
    "check_privacy",
    "field_classes",
    "prepare_artifact",
    "prepare_proposal",
    "redact",
]

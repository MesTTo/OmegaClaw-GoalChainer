"""Purpose: test that the incident example's host prepares and checks a reviewed proposal's artifact from the caller's incident record only while the review is fresh against the current packet and the review of that packet proposes the same action under the same standing, that the execution result keeps its facets apart, and that no generic module imports the example."""

import ast
import importlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given, settings, strategies as st

from goal_chainer.domains.loader import packaged_domain
from goal_chainer.errors import DependencyUnavailableError, InvalidInputError
from goal_chainer.examples.incident import (
    CONDITION_NAMES,
    CONTRACT,
    Authorization,
    ExecutionResult,
    PreparedArtifact,
    StaleReview,
    check_privacy,
    field_classes,
    host,
    prepare_artifact,
    prepare_proposal,
    redact,
)
from goal_chainer.examples.incident.execution import settle
from goal_chainer.relevance import ReviewPacket, RelevanceError, check_freshness, engine_identity
from incident_support import incident_record
from relevance_support import packet, reading, reviewed
from request_support import budget

READSET = {"kind": "offline-inputs", "request_digest": "r", "memory_digest": "m"}
# The host's own decisions: GoalChainer neither grants nor refuses a host's step.
HOST = "incident-example-host"
GRANTED = Authorization(True, "HostApproved", HOST, "The host approved the step.")
DENIED = Authorization(False, "HostDeclined", HOST, "The host declined the step.")
DIAGNOSTICS = {"error_code", "failure_mode", "affected_surface"}


# am[verifies a-ev-execution-contract@7acc73]
def _result(artifact, *, authorization=GRANTED, norm="obligated", readset=READSET):
    return ExecutionResult(
        action_id="publish_redacted_summary" if artifact is None else artifact.action_id,
        norm_status=norm,
        authorization=authorization,
        artifact=artifact,
        readset=readset, budget=budget(),
    )


# am[verifies a-ev-execution-contract@7acc73]
def test_redacted_summary_keeps_diagnostics_and_no_restricted_value() -> None:
    incident = incident_record()
    raw = incident["raw_log"]
    artifact = prepare_artifact("publish_redacted_summary", incident, budget=budget())

    dumped = json.dumps(artifact.payload)
    for value in (raw["customer_email"], raw["order_id"], raw["access_token"], raw["stack_trace"]):
        assert value not in dumped
    assert artifact.payload["diagnostics"]["error_code"] == "PAYMENT_TIMEOUT"
    assert artifact.privacy.passed
    assert artifact.privacy.leaked_fields == ()
    assert set(artifact.privacy.covered_fields) == {
        "access_token",
        "customer_email",
        "order_id",
        "request_payload",
        "stack_trace",
    }
    assert artifact.sealed is not None


# am[verifies a-ev-ec-negative-control@80ae2a]
def test_a_leaking_summary_is_withheld_with_no_payload() -> None:
    incident = incident_record()
    incident["summary"] = f"Customer {incident['raw_log']['customer_email']} cannot pay."

    artifact = prepare_artifact("publish_redacted_summary", incident, budget=budget())
    result = _result(artifact)
    conditions = result.conditions

    assert artifact.payload is None
    assert not artifact.privacy.passed
    assert artifact.privacy.leaked_fields == ("customer_email",)
    assert len(artifact.digest) == 64
    assert conditions["PrivacyVerified"].status is False
    assert conditions["ReleaseEligible"].status is False
    assert conditions["ReleaseEligible"].reason == "PrivacyCheckFailed"
    serialized = json.dumps(result.to_dict())
    assert incident["raw_log"]["customer_email"] not in serialized
    assert result.to_dict()["artifact"]["payload"] is None


# am[verifies a-ev-ec-raw-permitted@fb3143]
def test_a_raw_log_is_prepared_like_any_artifact_and_withheld_by_its_check() -> None:
    artifact = prepare_artifact("publish_raw_log", incident_record(), budget=budget())

    assert artifact.kind == "raw-incident-log"
    assert artifact.payload is None
    assert set(artifact.privacy.leaked_fields) == set(artifact.privacy.covered_fields)
    result = _result(artifact, norm="permitted")
    assert result.conditions["ArtifactPrepared"].status is True
    assert result.conditions["ReleaseEligible"].status is False


# am[verifies a-ev-ec-hold-checked@55d1b7]
def test_hold_prepares_an_internal_note_checked_like_any_artifact() -> None:
    artifact = prepare_artifact("hold_external_update", incident_record(), budget=budget())

    assert artifact.audience == "internal"
    assert artifact.payload["internal_detail_available"] is True
    assert artifact.privacy.passed
    assert _result(artifact, norm="obligated").conditions["ReleaseEligible"].status is True


# The counterexample c-ev-unlisted-field-uncovered: a field on neither of the old lists was never
# searched for, so a raw log holding it was releasable.
# am[verifies a-ev-mr-privacy-classes@d79884]
def test_a_field_nobody_listed_is_restricted_redacted_and_searched_for() -> None:
    incident = incident_record()
    incident["raw_log"] = {"customer_phone": "+61 400 000 000", "error_code": "E1"}

    raw = prepare_artifact("publish_raw_log", incident, budget=budget())
    summary = prepare_artifact("publish_redacted_summary", incident, budget=budget())

    assert raw.privacy.covered_fields == ("customer_phone",)
    assert raw.privacy.leaked_fields == ("customer_phone",)
    assert raw.payload is None
    assert summary.payload["diagnostics"] == {"customer_phone": "[redacted]", "error_code": "E1"}
    assert summary.privacy.passed


# am[verifies a-ev-mr-privacy-classes@d79884]
@settings(max_examples=60, deadline=None)
@given(st.lists(st.text(min_size=1, max_size=12), unique=True, max_size=6))
def test_only_declared_diagnostics_keep_their_values(fields) -> None:
    classes = field_classes(fields, budget=budget())
    raw_log = {name: f"value-of-{index}" for index, name in enumerate(fields)}

    assert classes == {
        name: "diagnostic" if name in DIAGNOSTICS else "restricted" for name in fields
    }
    assert redact(raw_log, budget=budget()) == {
        name: value if name in DIAGNOSTICS else "[redacted]" for name, value in raw_log.items()
    }


# The conditions table of docs/execution-contract.md, every norm against every authorization and
# artifact the settlement policy can be given, including combinations ExecutionResult refuses.
# am[verifies a-ev-mr-settle@e40f9f]
@pytest.mark.parametrize("norm", ["obligated", "permitted", "unregulated", "forbidden", "conflict"])
@pytest.mark.parametrize("granted", [True, False])
@pytest.mark.parametrize("verdict", [None, "NoRestrictedValues", "RestrictedValuesFound"])
def test_the_settlement_policy_derives_every_condition(norm, granted, verdict) -> None:
    from metta import S

    answer = settle(
        "gc-settle-conditions",
        S[norm],
        S.Authorization(granted, S.SomeReason),
        S.NoArtifact if verdict is None else S.Artifact(S[verdict]),
        budget=budget(),
    )
    rows = {str(name): (status, reason) for _, name, status, reason in answer[1:]}
    clean = verdict == "NoRestrictedValues"
    unknown = S.Unknown

    assert tuple(rows) == CONDITION_NAMES
    assert rows["Admissible"] == (norm not in {"forbidden", "conflict"}, (S.Norm, S[norm]))
    assert rows["Authorized"] == (granted, S.SomeReason)
    assert rows["ArtifactPrepared"] == (
        (False, S.NotAttempted) if verdict is None else (True, S.Prepared)
    )
    assert rows["PrivacyVerified"] == (
        (unknown, S.NotAttempted) if verdict is None else (clean, S[verdict])
    )
    assert rows["ReleaseEligible"] == (
        (False, S.NotAttempted)
        if verdict is None
        else (True, S.PrivacyVerified) if clean else (False, S.PrivacyCheckFailed)
    )
    assert rows["EffectConfirmed"] == (
        unknown, S.AwaitingHostReceipt if clean else S.NoEffectExpected
    )


# am[verifies a-ev-execution-contract@7acc73]
def test_values_with_json_escapes_are_still_found() -> None:
    raw_log = {"stack_trace": 'Traceback: "worker" \\ path'}
    payload = {"summary": 'Traceback: "worker" \\ path'}

    assert check_privacy(payload, raw_log, budget=budget()).leaked_fields == ("stack_trace",)


# am[verifies a-ev-execution-contract@7acc73]
def test_unknown_actions_and_malformed_records_are_refused() -> None:
    with pytest.raises(InvalidInputError, match="prepares no artifact"):
        prepare_artifact("restart_service", incident_record(), budget=budget())
    with pytest.raises(InvalidInputError, match="must be a mapping"):
        prepare_artifact("publish_raw_log", ["not", "a", "record"], budget=budget())
    with pytest.raises(InvalidInputError, match="raw_log must be a mapping"):
        prepare_artifact("publish_raw_log", {"raw_log": ["line"]}, budget=budget())


# am[verifies a-ev-ec-no-send@b87dac]
@pytest.mark.parametrize(
    "action",
    ["publish_redacted_summary", "publish_raw_log", "hold_external_update"],
)
def test_no_result_claims_a_send_or_a_confirmed_effect(action) -> None:
    result = _result(prepare_artifact(action, incident_record(), budget=budget()), norm="permitted")
    serialized = result.to_dict()

    assert "sent_external" not in json.dumps(serialized)
    assert serialized["conditions"]["EffectConfirmed"]["status"] is None
    assert serialized["contract"] == CONTRACT


# am[verifies a-ev-la-explicit-auth@4c7675]
def test_an_artifact_exists_exactly_when_the_step_was_authorized() -> None:
    artifact = prepare_artifact("publish_redacted_summary", incident_record(), budget=budget())

    with pytest.raises(ValueError, match="exactly when it was authorized"):
        _result(artifact, authorization=DENIED)
    with pytest.raises(ValueError, match="exactly when it was authorized"):
        _result(None, authorization=GRANTED)


# am[verifies a-ev-execution-contract@7acc73]
def test_an_inadmissible_action_cannot_be_authorized() -> None:
    artifact = prepare_artifact("publish_raw_log", incident_record(), budget=budget())

    with pytest.raises(ValueError, match="forbidden action cannot be authorized"):
        _result(artifact, norm="forbidden")


# am[verifies a-ev-ec-negative-control@80ae2a]
def test_a_withheld_artifact_cannot_be_built_with_its_payload() -> None:
    artifact = prepare_artifact("publish_raw_log", incident_record(), budget=budget())
    raw_text = json.dumps({"raw_log": incident_record()["raw_log"]})

    with pytest.raises(ValueError, match="keeps its payload exactly"):
        PreparedArtifact(
            action_id=artifact.action_id,
            kind=artifact.kind,
            audience=artifact.audience,
            intended_effect=artifact.intended_effect,
            digest=artifact.digest,
            privacy=artifact.privacy,
            sealed=raw_text,
        )


# am[verifies a-ev-ec-negative-control@80ae2a]
def test_changing_a_payload_copy_changes_nothing_released() -> None:
    artifact = prepare_artifact("publish_redacted_summary", incident_record(), budget=budget())
    result = _result(artifact)

    copy = artifact.payload
    copy["summary"] = "Customer ava@example.com cannot pay."
    copy["diagnostics"]["customer_email"] = "ava@example.com"

    assert artifact.payload["summary"] == incident_record()["summary"]
    assert artifact.payload["diagnostics"]["customer_email"] == "[redacted]"
    assert "ava@example.com" not in json.dumps(result.to_dict())


# am[verifies a-ev-ec-negative-control@80ae2a]
def test_a_sealed_payload_must_match_its_digest() -> None:
    artifact = prepare_artifact("publish_redacted_summary", incident_record(), budget=budget())

    with pytest.raises(ValueError, match="match the artifact digest"):
        PreparedArtifact(
            action_id=artifact.action_id,
            kind=artifact.kind,
            audience=artifact.audience,
            intended_effect=artifact.intended_effect,
            digest=artifact.digest,
            privacy=artifact.privacy,
            sealed=json.dumps({"summary": "something else"}),
        )


# am[verifies a-ev-execution-contract@7acc73]
def test_a_payload_that_is_not_finite_json_is_refused() -> None:
    incident = incident_record()
    incident["next_update"] = float("nan")

    with pytest.raises(ValueError, match="Out of range float"):
        prepare_artifact("publish_redacted_summary", incident, budget=budget())


# am[verifies a-ev-oe-none-unattempted@916054]
def test_a_refused_step_reports_every_later_facet_as_not_attempted() -> None:
    conditions = _result(None, authorization=DENIED, norm="permitted").conditions

    assert conditions["Admissible"].status is True
    assert conditions["Authorized"].status is False
    assert conditions["Authorized"].reason == "HostDeclined"
    assert conditions["ArtifactPrepared"].status is False
    assert conditions["PrivacyVerified"].status is None
    assert conditions["ReleaseEligible"].status is False
    assert conditions["EffectConfirmed"].reason == "NoEffectExpected"


# am[verifies a-ev-outcome-evidence@69a360]
def test_execution_and_observation_identities() -> None:
    first = prepare_artifact("publish_redacted_summary", incident_record(), budget=budget())
    second = prepare_artifact("publish_redacted_summary", incident_record(), budget=budget())

    assert first.observation_id == second.observation_id
    assert _result(first).execution_id == _result(second).execution_id
    moved = dict(READSET, memory_digest="other")
    assert _result(first).execution_id != _result(first, readset=moved).execution_id


# The review the host acts on, the packaged incident domain reviewed by the generic review over
# attributed readings as a domain request reviews it, with the packet it was decided on, which
# reads the same now unless a case says otherwise.
# am[verifies a-ie-s5-incident-host-1018@53176a] am[verifies a-ie-host-freshness-1018@ff618a]
def _reviewed(*readings) -> tuple[dict, ReviewPacket]:
    current = packet(*readings)
    return reviewed(packaged_domain("incident", budget=budget()), current).to_dict(), current


# The host's step on a stored review against the packet as it reads now, under that packet's budget.
# am[verifies a-ie-host-freshness-1018@ff618a]
def _settle(review: dict, current: ReviewPacket, record, authorization) -> ExecutionResult:
    return prepare_proposal(review, record, authorization, packet=current, budget=current.budget.run_budget())


# Sensitive data with verified facts: the review proposes the obligated redacted summary, forbids the
# raw log and leaves authorization unresolved; the host, having authorized the step, prepares the
# summary from the caller's record, and only a host receipt could confirm its effect.
# am[verifies a-ie-s5-incident-host-1018@53176a] am[rests-on c-ie-incident-review-measured-1018@0cb458]
def test_a_reviewed_proposal_is_prepared_from_the_callers_record() -> None:
    review, current = _reviewed(reading("sensitive-data"), reading("unverified", "refuted"))
    record = incident_record()

    execution = _settle(review, current, record, GRANTED)

    assert review["proposal"]["authorization"] == "unresolved"
    assert {c["action"]: c["deontic"] for c in review["candidates"]}["publish_raw_log"] == "forbidden"
    assert execution.action_id == "publish_redacted_summary"
    assert execution.norm_status == "obligated"
    assert execution.readset == {"kind": "relevance-review", "review_id": review["review_id"],
                                 "fingerprint": review["fingerprint"]}
    conditions = execution.conditions
    assert (conditions["Admissible"].status, conditions["Admissible"].reason) == (True, "Obligated")
    assert (conditions["Authorized"].status, conditions["Authorized"].reason) == (True, "HostApproved")
    assert conditions["ReleaseEligible"].status is True
    assert (conditions["EffectConfirmed"].status, conditions["EffectConfirmed"].reason) == (None, "AwaitingHostReceipt")
    released = json.dumps(execution.to_dict())
    for value in (record["raw_log"][name] for name in ("customer_email", "order_id", "access_token")):
        assert value not in released


# Unverified facts: the review proposes holding, so the host prepares the internal note.
# am[verifies a-ie-s5-incident-host-1018@53176a] am[rests-on c-ie-incident-review-measured-1018@0cb458]
def test_unverified_facts_propose_holding_and_the_host_prepares_an_internal_note() -> None:
    review, current = _reviewed(reading("sensitive-data"), reading("unverified"))

    execution = _settle(review, current, incident_record(), GRANTED)

    assert execution.action_id == "hold_external_update"
    assert execution.artifact.audience == "internal"
    assert execution.conditions["ReleaseEligible"].status is True


# A step the host declined prepares nothing and never reads the record, so even a record the host
# could not prepare from is no error, and every later facet is not attempted.
# am[verifies a-ie-s5-incident-host-1018@53176a] am[verifies a-ev-la-explicit-auth@4c7675]
def test_a_declined_step_prepares_nothing() -> None:
    review, current = _reviewed(reading("sensitive-data"), reading("unverified", "refuted"))

    execution = _settle(review, current, {"raw_log": ["unreadable"]}, DENIED)

    assert execution.artifact is None
    assert execution.conditions["Authorized"].reason == "HostDeclined"
    assert execution.conditions["ArtifactPrepared"].status is False


# The host prepares only a review record's proposal: another record, a review proposing nothing and
# an authorization that is not one are refused before anything is prepared.
# am[verifies a-ie-s5-incident-host-1018@53176a]
def test_the_host_refuses_what_it_cannot_act_on() -> None:
    review, current = _reviewed(reading("sensitive-data"), reading("unverified", "refuted"))

    with pytest.raises(InvalidInputError, match="goalchainer-relevance-review-v2"):
        _settle({**review, "protocol": "goalchainer-relevance-review-v0"}, current, incident_record(), GRANTED)
    with pytest.raises(InvalidInputError, match="proposes no action") as refused:
        _settle({**review, "proposal": None, "disposition": "escalate"}, current, incident_record(), GRANTED)
    assert refused.value.details["disposition"] == "escalate"
    with pytest.raises(InvalidInputError, match="must be an Authorization"):
        _settle(review, current, incident_record(), True)


# The review the next cases change one consumed field of, or the packet it is checked against: it
# proposes the obligated redacted summary.
# am[verifies a-integrate-example-host-inputs-1018@f0d0fa] am[verifies a-ie-host-freshness-1018@ff618a]
@pytest.fixture(scope="module")
def proposed() -> tuple[dict, ReviewPacket]:
    return _reviewed(reading("sensitive-data"), reading("unverified", "refuted"))


# Records the host would have prepared from, so a case can show that nothing was.
# am[verifies a-integrate-example-host-inputs-1018@f0d0fa]
@pytest.fixture
def preparations(monkeypatch) -> list:
    prepared: list = []
    monkeypatch.setattr(host, "prepare_artifact", lambda *args, **kwargs: prepared.append(args))
    return prepared


# A change that removes the field instead of setting it.
# am[verifies a-integrate-example-host-inputs-1018@f0d0fa]
MISSING = object()


# Every field the host reads from a review record is checked, in the representation review records
# carry, before anything is prepared: a proposal that is no object, one without its action or its
# deontic standing, a standing that is no deontic status, an action this host prepares nothing for,
# a review without the id or fingerprint the execution's readset names, and one without the readset
# or subject the freshness check reads. Each is InvalidInputError naming the field, whether the host
# granted the step or declined it.
# am[verifies a-integrate-example-host-inputs-1018@f0d0fa] am[verifies a-ie-host-freshness-1018@ff618a]
@pytest.mark.parametrize("authorization", [GRANTED, DENIED], ids=["granted", "declined"])
@pytest.mark.parametrize("change, named", [
    ({"proposal": {}}, "action"),
    ({"proposal": []}, "proposal"),
    ({"proposal": "publish_redacted_summary"}, "proposal"),
    ({"proposal": 7}, "proposal"),
    ({"proposal": {"deontic": "obligated"}}, "action"),
    ({"proposal": {"action": "publish_redacted_summary"}}, "deontic"),
    ({"proposal": {"action": ["publish_redacted_summary"], "deontic": "obligated"}}, "action"),
    ({"proposal": {"action": "publish_redacted_summary", "deontic": "Obligated"}}, "Obligated"),
    ({"proposal": {"action": "send_everything", "deontic": "obligated"}}, "send_everything"),
    ({"review_id": MISSING}, "review_id"),
    ({"fingerprint": MISSING}, "fingerprint"),
    ({"fingerprint": 7}, "fingerprint"),
    ({"readset": MISSING}, "readset"),
    ({"subject": 7}, "subject"),
])
def test_a_consumed_field_the_host_cannot_read_is_refused_before_anything_is_prepared(
    proposed, preparations, change, named, authorization
) -> None:
    stored, current = proposed
    review = {key: value for key, value in {**stored, **change}.items() if value is not MISSING}

    with pytest.raises(InvalidInputError, match=named):
        _settle(review, current, incident_record(), authorization)
    assert preparations == []


# A granted step for a proposal the host's blocking cut makes inadmissible is refused before its
# artifact is prepared; declined, it settles like any declined step, inadmissible and unprepared.
# The review's ranking never proposes such an action, so the review run again here is one that
# does, as a ranking disagreeing with the host's settlement would.
# am[verifies a-integrate-example-host-inputs-1018@f0d0fa] am[verifies a-ie-s2a-blocking-cut-home-1018@dd66bf]
@pytest.mark.parametrize("norm", ["forbidden", "conflict"])
def test_a_granted_step_for_an_inadmissible_proposal_prepares_nothing(proposed, preparations, monkeypatch, norm) -> None:
    stored, current = proposed
    inadmissible = {**stored, "proposal": {**stored["proposal"], "action": "publish_raw_log", "deontic": norm}}
    monkeypatch.setattr(host, "relevance_review", lambda *_, **__: SimpleNamespace(to_dict=lambda: inadmissible))

    with pytest.raises(InvalidInputError, match=f"A {norm} proposal cannot be authorized"):
        _settle(inadmissible, current, incident_record(), GRANTED)
    declined = _settle(inadmissible, current, incident_record(), DENIED)

    assert preparations == []
    assert declined.artifact is None and declined.conditions["Admissible"].status is False


# A stored review whose proposal names an action or standing the review of the current packet does
# not reach is refused before anything is prepared, granted or declined, with both outcomes in its
# details. The first case is the one measured on the host that took the record's word: the raw log,
# which the review forbids, relabelled permitted.
# am[verifies a-ie-host-recompute-proposal-1018@898c26]
@pytest.mark.parametrize("authorization", [GRANTED, DENIED], ids=["granted", "declined"])
@pytest.mark.parametrize("action, norm", [
    ("publish_raw_log", "permitted"),
    ("publish_raw_log", "forbidden"),
    ("publish_raw_log", "conflict"),
    ("publish_redacted_summary", "permitted"),
    ("hold_external_update", "obligated"),
], ids=["raw-log-relabelled-permitted", "raw-log-forbidden", "raw-log-conflict", "summary-restanded", "hold"])
def test_a_proposal_the_current_review_does_not_reach_prepares_nothing(
    proposed, preparations, action, norm, authorization
) -> None:
    stored, current = proposed
    changed = {**stored, "proposal": {**stored["proposal"], "action": action, "deontic": norm}}

    with pytest.raises(InvalidInputError, match="current packet proposes publish_redacted_summary as obligated") as refused:
        _settle(changed, current, incident_record(), authorization)

    assert {c["action"]: c["deontic"] for c in stored["candidates"]}["publish_raw_log"] == "forbidden"
    assert refused.value.details["consumed"] == {"action": action, "deontic": norm}
    assert refused.value.details["current"] == {
        "disposition": "propose", "proposal": {"action": "publish_redacted_summary", "deontic": "obligated"},
    }
    assert preparations == []


# A readset trimmed so the freshness check no longer compares the unverified facts leaves the stored
# review fresh against a packet where they moved, but cannot keep its summary: the review run again
# on that packet holds the update when the facts read detected, and proposes nothing, escalating,
# when two observations of them disagree. Either is refused before anything is prepared.
# am[verifies a-ie-host-recompute-proposal-1018@898c26]
@pytest.mark.parametrize("readings, disposition, reached", [
    ((reading("sensitive-data"), reading("unverified")), "propose", "hold_external_update"),
    ((reading("sensitive-data"), reading("unverified", "refuted", source="test:first"),
      reading("unverified", source="test:second")), "escalate", None),
], ids=["facts-detected", "facts-conflicted"])
def test_a_trimmed_readset_cannot_keep_a_proposal_the_current_review_does_not_reach(
    proposed, preparations, readings, disposition, reached
) -> None:
    stored, _ = proposed
    moved = packet(*readings)
    trimmed = {**stored, "readset": {
        "signals": [name for name in stored["readset"]["signals"] if name != "unverified"],
        "snapshot": {name: value for name, value in stored["readset"]["snapshot"].items() if name != "unverified"},
    }}

    with pytest.raises(InvalidInputError, match="current packet proposes") as refused:
        _settle(trimmed, moved, incident_record(), GRANTED)

    current = refused.value.details["current"]
    assert current["disposition"] == disposition
    assert (current["proposal"] or {}).get("action") == reached
    assert preparations == []


# Candidates rewritten so every action reads permitted decide nothing: with the proposal relabelled
# to the raw log they are refused like any relabelling, and beside the review's own proposal the
# host prepares what the review of the current packet proposes, from that review's standing.
# am[verifies a-ie-host-recompute-proposal-1018@898c26]
def test_rewritten_candidates_decide_nothing_the_host_prepares(proposed, monkeypatch) -> None:
    stored, current = proposed
    rewritten = {**stored, "candidates": [{**c, "deontic": "permitted"} for c in stored["candidates"]]}
    relabelled = {**rewritten, "proposal": {**stored["proposal"], "action": "publish_raw_log", "deontic": "permitted"}}
    prepared = []
    original = host.prepare_artifact

    def traced(action, *args, **kwargs):
        prepared.append(action)
        return original(action, *args, **kwargs)

    monkeypatch.setattr(host, "prepare_artifact", traced)
    with pytest.raises(InvalidInputError, match="current packet proposes publish_redacted_summary as obligated"):
        _settle(relabelled, current, incident_record(), GRANTED)
    execution = _settle(rewritten, current, incident_record(), GRANTED)

    assert prepared == ["publish_redacted_summary"]
    assert (execution.action_id, execution.norm_status) == ("publish_redacted_summary", "obligated")
    assert execution.conditions["Admissible"].reason == "Obligated"


# The review run again is charged to the caller's budget, the one the freshness check spent from: a
# budget with room for the check and half a review stops inside the review with relevance's own
# review-budget-exceeded, and nothing is prepared.
# am[verifies a-ie-host-recompute-proposal-1018@898c26]
def test_the_review_run_again_is_charged_to_the_callers_budget(proposed, preparations, monkeypatch) -> None:
    stored, current = proposed
    measured = current.budget.run_budget()
    check_freshness(stored, packaged_domain("incident", budget=measured), current,
                    engine_identity(budget=measured), budget=measured)
    review_cost = reviewed(packaged_domain("incident", budget=budget()), current).inferences
    tight = current.budget.run_budget()
    tight.charge(current.budget.inferences - measured.spent - review_cost // 2)
    entered = []
    run_again = host.relevance_review

    def traced(*args, **kwargs):
        entered.append(True)
        return run_again(*args, **kwargs)

    monkeypatch.setattr(host, "relevance_review", traced)
    with pytest.raises(RelevanceError) as stopped:
        prepare_proposal(stored, incident_record(), GRANTED, packet=current, budget=tight)

    assert stopped.value.code == "review-budget-exceeded"
    assert entered == [True]
    assert preparations == []


# A stored review whose support moved, here the unverified facts reading as detected where the
# review read them refuted, is refused as stale whether the host granted the step or declined it:
# its details are the freshness report naming what moved, and nothing is prepared.
# am[verifies a-ie-host-freshness-1018@ff618a]
@pytest.mark.parametrize("authorization", [GRANTED, DENIED], ids=["granted", "declined"])
def test_a_review_whose_support_moved_is_stale_and_prepares_nothing(proposed, preparations, authorization) -> None:
    stored, _ = proposed
    moved = packet(reading("sensitive-data"), reading("unverified"))

    with pytest.raises(StaleReview) as refused:
        _settle(stored, moved, incident_record(), authorization)

    assert refused.value.code == "stale_review"
    assert refused.value.details["status"] == "stale"
    assert refused.value.details["fingerprint"] == stored["fingerprint"]
    assert [change["signal"] for change in refused.value.details["changes"]] == ["unverified"]
    assert preparations == []


# A packet about another subject cannot make the review fresh or stale: relevance refuses the
# comparison as subject-mismatch, a type of its own, and nothing is prepared.
# am[verifies a-ie-host-freshness-1018@ff618a]
def test_a_packet_about_another_subject_is_refused_and_prepares_nothing(proposed, preparations) -> None:
    stored, current = proposed

    with pytest.raises(RelevanceError) as refused:
        _settle(stored, replace(current, subject="another-task"), incident_record(), GRANTED)

    assert refused.value.code == "subject-mismatch"
    assert preparations == []


# The check needs the current ReviewPacket and a budget no looser than the packet's: a packet given
# as its JSON form and the request test budget, which allows more than the packet declares, are each
# InvalidInputError, and an already used-up budget is relevance's own stop, before anything is
# prepared.
# am[verifies a-ie-host-freshness-1018@ff618a]
def test_the_freshness_check_needs_the_packet_and_a_budget_within_it(proposed, preparations) -> None:
    stored, current = proposed
    spent = current.budget.run_budget()
    spent.charge(current.budget.inferences + 1)

    with pytest.raises(InvalidInputError, match="ReviewPacket"):
        prepare_proposal(stored, incident_record(), GRANTED, packet=current.to_dict(),
                         budget=current.budget.run_budget())
    with pytest.raises(InvalidInputError, match="no looser than its packet"):
        prepare_proposal(stored, incident_record(), GRANTED, packet=current, budget=budget())
    with pytest.raises(RelevanceError) as stopped:
        prepare_proposal(stored, incident_record(), GRANTED, packet=current, budget=spent)
    assert stopped.value.code == "review-budget-exceeded"
    assert preparations == []


# An engine the check cannot reach keeps relevance's runtime-unavailable error, and nothing is
# prepared. The package's `review` function shadows the module of that name, so the module is
# patched through the import system.
# am[verifies a-ie-host-freshness-1018@ff618a]
def test_an_engine_the_check_cannot_reach_keeps_its_error_and_prepares_nothing(
    proposed, preparations, monkeypatch
) -> None:
    stored, current = proposed

    def unavailable(**_):
        raise DependencyUnavailableError("pymetta is not importable", details={"module": "metta"})

    monkeypatch.setattr(importlib.import_module("goal_chainer.relevance.review"), "prepare_deontic_engine", unavailable)
    with pytest.raises(RelevanceError) as refused:
        _settle(stored, current, incident_record(), GRANTED)

    assert refused.value.code == "runtime-unavailable"
    assert preparations == []


# The example is selected by importing it: no module of the package outside goal_chainer.examples
# imports it, in any import form.
# Time: one parse of each package module.
# am[verifies a-ie-s5-incident-host-1018@53176a]
def test_no_generic_module_imports_the_example() -> None:
    package = Path(__file__).resolve().parents[1] / "src" / "goal_chainer"
    importers = []
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(package)
        if relative.parts[0] == "examples":
            continue
        current = ["goal_chainer", *relative.with_suffix("").parts]
        if current[-1] == "__init__":
            current.pop()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                package_parts = current if path.name == "__init__.py" else current[:-1]
                base = package_parts[: len(package_parts) - node.level + 1] if node.level else []
                module = ".".join([*base, *([node.module] if node.module else [])])
                targets = [module, *(f"{module}.{alias.name}" for alias in node.names)]
            else:
                continue
            if any(target == "goal_chainer.examples" or target.startswith("goal_chainer.examples.")
                   for target in targets):
                importers.append(f"{relative}:{node.lineno}")
    assert importers == []

"""Purpose: check the review record, its fingerprint, the freshness check, the receipt assessment against a review or against its caller's predictions, and the assess command without a theory run."""

from __future__ import annotations

import functools
import io
import json
import re
import subprocess
import sys
import typing
from dataclasses import fields, replace
from datetime import date, datetime, timedelta, timezone

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from goal_chainer.cli import main
from goal_chainer.domains.loader import vocabulary
from goal_chainer.errors import InvalidInputError
from goal_chainer.relevance.errors import RelevanceError
from goal_chainer.relevance.freshness import check_freshness
from goal_chainer.relevance.packet import parse_packet
from goal_chainer.relevance.policy import constant, evaluate, items, prepare, term
from goal_chainer.relevance.ranking import rank
from goal_chainer.relevance.receipt import Observation, Receipt, assess_attempt, assess_receipt, check_receipt, parse_receipt
from goal_chainer.relevance.review import ReviewResult
from goal_chainer import relevance_cli
from goal_chainer.runtime.budget import RunBudget

from relevance_support import (
    AS_OF, BEYOND_FLOAT, ENGINE, FLOAT_EDGE, candidate, checked_freshness, child_environment, derived, later, packet,
    reading, task_control,
)
from request_support import CLI_LIMITS, budget as request_budget

DOMAIN = task_control()
ENGINE_IDENTITY = ENGINE.identity()
PAUSE_EFFECTS = {
    "recoverability": ("strongly-positive", "deterministic"),
    "option-value": ("strongly-positive", "model-proposed"),
}
READINGS = (
    reading("state_preservation_route", "detected", "deterministic", source="checkpoint-store"),
    reading("safe_point_reachable", "detected", "measured", source="telemetry", valid_until=later(10)),
    reading("resource_contention", "detected", "measured", source="ledger"),
)


# am[related a-rel-review-contract-1016@d0bea9]
def result(readings=READINGS, *, extra=(), authority="advisory", as_of=AS_OF, effects=PAUSE_EFFECTS) -> ReviewResult:
    """The pause review: an obliged pause beside a permitted continue, plus optional candidates."""

    review_packet = packet(*readings, authority=authority, as_of=as_of)
    candidates = [
        candidate(DOMAIN, "pause_recoverably", modes="OP", effects=effects,
                  contributions={"least_commitment": "strongly-positive"}),
        candidate(DOMAIN, "continue_task", modes="P", contributions={"project_outcome": "positive"}),
        *extra,
    ]
    compiled = derived(DOMAIN, candidates, review_packet=review_packet)
    budget = review_packet.budget.run_budget()
    ranking = rank(compiled, budget)
    return ReviewResult(derived=compiled, ranking=ranking, policy_digest=prepare(budget), inferences=budget.spent)


# am[related a-rel-review-contract-1016@d0bea9]
def record(**fields) -> dict:
    return json.loads(json.dumps(result(**fields).to_dict()))


# am[verifies a-rel-review-contract-1016@d0bea9]
def test_the_review_record_is_proposal_only_with_unresolved_authorization() -> None:
    payload = record()

    assert payload["protocol"] == "goalchainer-relevance-review-v2"
    assert payload["applies_effects"] is False
    proposal = payload["proposal"]
    assert payload["disposition"] == "propose" and proposal["action"] == "pause_recoverably"
    assert proposal["authorization"] == "unresolved"
    assert proposal["action_authority_ceiling"] == "preauthorized"
    assert proposal["licensed_authority_ceiling"] == "advisory"
    assert {e["status"] for e in proposal["predicted_effects"]} == {"predicted"}
    assert {c["status"] for c in proposal["predicted_contributions"]} == {"predicted"}
    assert payload["missing_information"]["unestimated_dimensions"] == list(DOMAIN.unestimated_dimensions)


# am[verifies a-rel-review-contract-1016@d0bea9]
def test_the_fingerprint_covers_decision_inputs_and_nothing_else() -> None:
    base = result().fingerprint
    same_inputs = result().derived.packet
    relabelled = replace(same_inputs, review_id="rr-other", trigger="other")
    other_subject = replace(same_inputs, subject="another-task")
    noted = (READINGS[0], replace(READINGS[1], note="commentary"), READINGS[2])

    reviewed = result()
    assert reviewed.fingerprint == base
    assert replace(reviewed, derived=replace(reviewed.derived, packet=relabelled)).fingerprint == base
    # The subject is what the review is about, so one fingerprint never names two subjects.
    assert replace(reviewed, derived=replace(reviewed.derived, packet=other_subject)).fingerprint != base
    # What the review measured is not an input; the policy that decided it is.
    assert replace(reviewed, inferences=reviewed.inferences + 1).fingerprint == base
    assert replace(reviewed, policy_digest="sha256:another-review-policy").fingerprint != base
    assert result(readings=noted).fingerprint == base
    resourced = (READINGS[0], replace(READINGS[1], source="telemetry-2"), READINGS[2])
    assert result(readings=resourced).fingerprint != base
    assert result(authority="shadow").fingerprint != base


# am[verifies a-rel-review-contract-1016@d0bea9] am[rests-on c-integrate-agenticmind-support-1016@b60619]
def test_an_unchanged_packet_is_fresh() -> None:
    report = checked_freshness(record(), DOMAIN, result().derived.packet, ENGINE_IDENTITY).to_dict()

    assert report["status"] == "fresh" and report["support"] == "standing"
    assert report["changes"] == [] and report["implies_alternative"] is False


# One observation keeps its identity whatever offset its time is written in: the same instant at
# +11:00 gives the same fingerprint, and a packet re-spelling it leaves the review fresh.
# am[verifies a-rel-rcpt-v2-reading-instants-1017@034dcc] am[verifies c-rel-reading-identity-offset-1017@198702]
def test_one_instant_written_at_another_offset_is_the_same_observation() -> None:
    utc = later(-1)
    sydney = utc.astimezone(timezone(timedelta(hours=11)))
    written_utc = (replace(READINGS[0], observed_at=utc), *READINGS[1:])
    written_sydney = (replace(READINGS[0], observed_at=sydney), *READINGS[1:])

    assert result(readings=written_utc).fingerprint == result(readings=written_sydney).fingerprint
    report = checked_freshness(record(readings=written_utc), DOMAIN, packet(*written_sydney), ENGINE_IDENTITY).to_dict()
    assert report["status"] == "fresh" and report["changes"] == []
    support = record(readings=written_sydney)["readset"]["snapshot"]["state_preservation_route"]["support"]
    assert support[0]["observed_at"] == "2026-10-16T08:59:00+00:00"


# am[verifies a-rel-review-contract-1016@d0bea9] am[rests-on c-integrate-agenticmind-support-1016@b60619]
def test_the_same_state_from_a_different_observation_withdraws_support() -> None:
    # A checkpoint receipt replaced by another source's must not quietly keep the old support.
    replaced = (replace(READINGS[0], source="checkpoint-store-replica"), *READINGS[1:])

    report = checked_freshness(record(), DOMAIN, packet(*replaced), ENGINE_IDENTITY).to_dict()

    assert report["status"] == "stale" and report["support"] == "withdrawn"
    assert [change["signal"] for change in report["changes"]] == ["state_preservation_route"]
    assert report["changes"][0]["was"]["state"] == report["changes"][0]["now"]["state"] == "detected"
    assert report["implies_alternative"] is False


# am[verifies a-rel-review-contract-1016@d0bea9] am[rests-on c-integrate-agenticmind-support-1016@b60619]
def test_an_expired_reading_withdraws_support_as_unknown_not_refuted() -> None:
    report = checked_freshness(record(), DOMAIN, packet(*READINGS, as_of=later(30)), ENGINE_IDENTITY).to_dict()

    change = next(c for c in report["changes"] if c["signal"] == "safe_point_reachable")
    assert report["status"] == "stale"
    assert change["now"] == {"state": "unknown", "support": []}


# am[verifies a-rel-review-contract-1016@d0bea9]
def test_a_new_observation_that_could_wake_a_rival_withdraws_support() -> None:
    # stale_parent_goal is a candidacy premise of STOP_STALE, which is not a candidate yet.
    woken = (*READINGS, reading("stale_parent_goal", "detected", "deterministic"))

    report = checked_freshness(record(), DOMAIN, packet(*woken), ENGINE_IDENTITY).to_dict()

    assert report["status"] == "stale"
    assert [c["signal"] for c in report["changes"]] == ["stale_parent_goal"]


# am[verifies a-rel-review-contract-1016@d0bea9]
def test_a_change_to_an_elimination_premise_of_a_candidate_rival_withdraws_support() -> None:
    # With STOP_STALE a candidate, the defeater reading low_graph_quality decides whether it is
    # permitted, so it is in the readset even though the winner never reads it.
    stop = candidate(DOMAIN, "stop_stale", modes="P", contributions={"mature_result_efficiency": "positive"})
    graded = (*READINGS, reading("low_graph_quality", "refuted", "measured"))
    prior = record(readings=graded, extra=(stop,))
    withdrawn = (*READINGS, reading("low_graph_quality", "unknown", source="graph-audit"))

    report = checked_freshness(prior, DOMAIN, packet(*withdrawn), ENGINE_IDENTITY).to_dict()

    assert "low_graph_quality" in prior["readset"]["signals"]
    assert [c["signal"] for c in report["changes"]] == ["low_graph_quality"]
    assert report["status"] == "stale"


# An opposing witness arrives while every existing witness is unchanged; the AgenticMind and
# institutional freshness rule is that this too withdraws support.
# am[verifies a-rel-review-contract-1016@d0bea9] am[rests-on c-integrate-agenticmind-support-1016@b60619]
def test_an_opposing_observation_added_beside_unchanged_support_withdraws_it() -> None:
    opposed = (*READINGS, reading("safe_point_reachable", "refuted", "measured", source="second-probe"))

    report = checked_freshness(record(), DOMAIN, packet(*opposed), ENGINE_IDENTITY).to_dict()

    change = next(c for c in report["changes"] if c["signal"] == "safe_point_reachable")
    assert report["status"] == "stale" and report["support"] == "withdrawn"
    assert change["now"]["state"] == "conflicted" and len(change["now"]["support"]) == 2
    assert report["implies_alternative"] is False


# A review stored while an overruled contrary was current escalated on it; once the contrary
# lapses the dispute is over, so the review's support is withdrawn, though the state is unchanged.
# am[verifies a-rel-rr-p-effective-1018@2a0968]
def test_an_overruled_contrary_lapsing_withdraws_support() -> None:
    disputed = (*READINGS, reading("safe_point_reachable", "refuted", "model-proposed", source="model",
                                   valid_until=later(5)))
    prior = record(readings=disputed)

    current = checked_freshness(prior, DOMAIN, packet(*disputed), ENGINE_IDENTITY).to_dict()
    lapsed = checked_freshness(prior, DOMAIN, packet(*disputed, as_of=later(6)), ENGINE_IDENTITY).to_dict()

    assert prior["missing_information"]["contested_signals"] == ["safe_point_reachable"]
    assert prior["disposition"] == "escalate"
    assert current["status"] == "fresh"
    change = next(c for c in lapsed["changes"] if c["signal"] == "safe_point_reachable")
    assert lapsed["status"] == "stale"
    assert change["was"]["state"] == change["now"]["state"] == "detected"
    assert (len(change["was"]["support"]), len(change["now"]["support"])) == (2, 1)


# The declared signals are a finite registry, so the rule can be checked exhaustively: a first
# reading of any signal the review rests on withdraws its support, and one of a signal it does
# not rest on leaves it standing.
# am[verifies a-rel-review-contract-1016@d0bea9] am[verifies c-rel-cone-sound-1016@092cec]
@pytest.mark.parametrize("signal", sorted(set(DOMAIN.signal_ids) - {r.signal for r in READINGS}))
def test_a_first_reading_of_any_signal_withdraws_support_exactly_when_the_review_rests_on_it(signal: str) -> None:
    prior = record()
    added = (*READINGS, reading(signal, "detected", "measured", source="new-witness"))

    report = checked_freshness(prior, DOMAIN, packet(*added), ENGINE_IDENTITY).to_dict()

    if signal in prior["readset"]["signals"]:
        assert report["status"] == "stale" and [c["signal"] for c in report["changes"]] == [signal]
    else:
        assert report["status"] == "fresh" and report["ignored_changes"] == [signal]


# am[verifies a-rel-review-contract-1016@d0bea9]
def test_a_change_outside_the_readset_is_reported_and_leaves_the_review_fresh() -> None:
    prior = record(readings=(*READINGS, reading("receiving_owner_accepts", "refuted", "deterministic")))
    moved = (*READINGS, reading("receiving_owner_accepts", "detected", "deterministic"))

    report = checked_freshness(prior, DOMAIN, packet(*moved), ENGINE_IDENTITY).to_dict()

    assert report["status"] == "fresh"
    assert report["ignored_changes"] == ["receiving_owner_accepts"]


# am[verifies a-rel-review-contract-1016@d0bea9]
@pytest.mark.parametrize("change", ["policy", "review_policy", "engine", "authority"])
def test_a_policy_engine_or_authority_change_makes_the_review_stale(change: str) -> None:
    prior = record()
    engine = dict(ENGINE_IDENTITY)
    current = result().derived.packet
    if change == "policy":
        prior["domain"]["digest"] = "sha256:another-policy"
    elif change == "review_policy":
        prior["review_policy"]["digest"] = "sha256:another-review-policy"
    elif change == "engine":
        engine["plugin_digest"] = "another-plugin"
    else:
        current = replace(current, authority="shadow")

    report = checked_freshness(prior, DOMAIN, current, engine).to_dict()

    assert report["status"] == "stale" and report[f"{change}_changed"] is True


# am[verifies a-integrate-domain-review-budget-1018@a84bf4]
def test_a_freshness_check_runs_only_under_a_callers_budget_no_looser_than_its_packet() -> None:
    current = result().derived.packet
    unbounded = RunBudget(inference_budget=None, timeout_seconds=current.budget.timeout_seconds)

    for budget in (None, unbounded):
        with pytest.raises(InvalidInputError):
            check_freshness(record(), DOMAIN, current, ENGINE_IDENTITY, budget=budget)  # type: ignore[arg-type]
    report = check_freshness(record(), DOMAIN, current, ENGINE_IDENTITY, budget=current.budget.run_budget())
    assert report.to_dict()["status"] == "fresh"


# am[verifies a-rel-review-contract-1016@d0bea9]
def test_a_packet_about_another_subject_is_refused_rather_than_compared() -> None:
    other = replace(result().derived.packet, subject="another-task")

    with pytest.raises(RelevanceError) as raised:
        checked_freshness(record(), DOMAIN, other, ENGINE_IDENTITY)

    assert raised.value.code == "subject-mismatch"


# Paths into a valid record, each set to a value of the wrong type.
MALFORMED_REVIEW_FIELDS = [
    (("subject",), 7),
    (("engine",), "engine"),
    (("engine", "runtime_digest"), None),
    (("review_policy",), None),
    (("review_policy", "digest"), 4),
    (("domain", "digest"), ["digest"]),
    (("readset", "snapshot"), []),
    (("readset", "snapshot", "safe_point_reachable", "support"), {"state": "detected"}),
    (("readset", "snapshot", "safe_point_reachable", "support", 0, "source"), 3),
    (("readings", 0), "reading"),
    (("readings", 0, "support"), None),
    (("readings", "safe_point_reachable", "support", 0, "estimator"), 5),
]


# am[related a-rel-review-contract-1016@d0bea9]
def malformed(path: tuple, value: object) -> dict:
    """A valid record with one field replaced; a text key into a list picks a reading by signal."""

    damaged = record()
    target = damaged
    for key in path[:-1]:
        if isinstance(target, list) and isinstance(key, str):
            target = next(item for item in target if item["signal"] == key)
        else:
            target = target[key]
    target[path[-1]] = value
    return damaged


# am[verifies a-rel-review-contract-1016@d0bea9]
@pytest.mark.parametrize("path, value", MALFORMED_REVIEW_FIELDS)
def test_a_malformed_review_record_is_an_invalid_record_for_the_freshness_check(path: tuple, value: object) -> None:
    with pytest.raises(RelevanceError) as raised:
        checked_freshness(malformed(path, value), DOMAIN, result().derived.packet, ENGINE_IDENTITY)

    assert raised.value.code == "invalid-record"


# am[verifies a-rel-review-contract-1016@d0bea9] am[verifies a-rel-rcpt-v2-schema-1017@df2f55]
@pytest.mark.parametrize(
    "path, value",
    [
        (("proposal",), None),
        (("proposal", "predicted_effects"), {"dimension": "x"}),
        (("proposal", "predicted_effects", 0), "recoverability"),
        (("proposal", "predicted_effects", 0, "band"), 1),
        (("proposal", "predicted_contributions", 0, "goal"), None),
        (("disposition",), None),
        (("as_of",), None),
        (("as_of",), "nine on the sixteenth"),
    ],
)
def test_a_malformed_review_record_is_an_invalid_record_for_the_assessment(path: tuple, value: object) -> None:
    with pytest.raises(RelevanceError) as raised:
        assess_receipt(malformed(path, value), receipt(), budget=request_budget())

    assert raised.value.code == "invalid-record"


APPLIED_AT = later(2)
ISSUED_AT = later(20)
MICROSECOND = timedelta(microseconds=1)
# A literal a procedure's step achieves, as literal_text writes it.
STEP_ACHIEVES = "(Statement task-paused)"
V2_ASSESSMENT_FIELDS = {"protocol", "review_id", "fingerprint", "action", "attempt", "applied", "applied_at",
                        "issued_at", "next_attempt_at", "receipt_fingerprint", "completion_confirms_effects",
                        "effects", "contributions", "goals", "uncounted"}


# am[related a-rel-rcpt-v2-tests-1017@5f9488]
def receipt_payload(
    *observations: dict, applied_at=APPLIED_AT, issued_at=ISSUED_AT, attempt="exec-1",
    fingerprint: str | None = None, action="pause_recoverably",
) -> dict:
    """A v2 receipt for the pause review: applied at 09:02 and issued at 09:20 unless given."""

    return {
        "protocol": "goalchainer-relevance-receipt-v2",
        "review_fingerprint": fingerprint or record()["fingerprint"],
        "action": action,
        "attempt": attempt,
        "applied_at": None if applied_at is None else _written(applied_at),
        "issued_at": _written(issued_at),
        "observations": list(observations),
    }


# am[related a-rel-rcpt-v2-tests-1017@5f9488]
def receipt(*observations: dict, **fields):
    return parse_receipt(receipt_payload(*observations, **fields), budget=request_budget())


# An establishing observation of an effect, made at 09:06 unless given; None leaves it untimed.
# am[related a-rel-rcpt-v2-tests-1017@5f9488]
def seen(target: str, outcome: str = "confirmed", estimator: str = "measured", about: str = "effect",
         observed_at=later(6), **extra) -> dict:
    observation = {"about": about, "target": target, "outcome": outcome, "estimator": estimator, "source": "ledger", **extra}
    if observed_at is not None:
        observation["observed_at"] = _written(observed_at)
    return observation


# am[related a-rel-rcpt-v2-tests-1017@5f9488]
def _written(moment) -> str:
    return moment if isinstance(moment, str) else moment.isoformat()


# am[related a-rel-rcpt-v2-tests-1017@5f9488]
def effect(assessment: dict, dimension: str) -> dict:
    return next(e for e in assessment["effects"] if e["dimension"] == dimension)


# am[related a-rel-rcpt-v2-tests-1017@5f9488]
def reasons(assessment: dict) -> list[str]:
    return [entry["reason"] for entry in assessment["uncounted"]]


# am[verifies a-rel-review-contract-1016@d0bea9] am[rests-on c-integrate-agenticmind-effects-1016@7fdbf0]
# am[verifies a-rel-rcpt-v2-assessment-1017@25ad31] am[verifies a-rel-assess-attempt-1018@20e6ca]
def test_an_applied_action_without_observations_confirms_nothing() -> None:
    assessment = assess_receipt(record(), receipt(), budget=request_budget())

    assert assessment["protocol"] == "goalchainer-relevance-assessment-v2"
    assert set(assessment) == V2_ASSESSMENT_FIELDS
    assert assessment["applied"] is True and assessment["completion_confirms_effects"] is False
    assert (assessment["attempt"], assessment["applied_at"], assessment["issued_at"]) == (
        "exec-1", "2026-10-16T09:02:00+00:00", "2026-10-16T09:20:00+00:00"
    )
    assert {e["status"] for e in assessment["effects"]} == {"predicted"}
    assert {e["attribution"] for e in assessment["effects"]} == {"unestablished"}


# The assess command has no packet to declare its bounds, so its command line gives both, and
# without them it is a usage error; the receipt's check and its assessment run under the one
# budget they make, and an allowance too small to finish stops them with the review's own error.
# am[verifies a-rel-mig-cli-1018@2adefb] am[verifies a-rel-mig-receipt-1018@6f384d]
def test_the_assess_command_runs_under_the_bounds_its_command_line_gives(tmp_path, capsys) -> None:
    review_path, receipt_path = tmp_path / "review.json", tmp_path / "receipt.json"
    review_path.write_text(json.dumps(record()), encoding="utf-8")
    receipt_path.write_text(json.dumps(receipt_payload(seen("recoverability"))), encoding="utf-8")
    command = ["relevance", "assess", "--review", str(review_path), "--receipt", str(receipt_path), "--json"]

    with pytest.raises(SystemExit) as usage:
        main(command)
    assert usage.value.code == 2 and "--inference-budget" in capsys.readouterr().err

    assert main([*command, *CLI_LIMITS]) == 0
    assert effect(json.loads(capsys.readouterr().out), "recoverability")["status"] == "confirmed"

    assert main([*command, "--inference-budget", "1", "--timeout-seconds", "60"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "review-budget-exceeded"


# The review's text is format_review's, the one wording relevance review prints and a command
# that shows a review reuses: one line per fact, no trailing newline, and never an applied effect.
# The command's result is the contract's record, so no review runs.
# am[verifies a-rel-format-review-public-1018@e7baab]
def test_the_review_command_prints_format_review_of_its_record(monkeypatch, capsys) -> None:
    review = record()
    monkeypatch.setattr(relevance_cli, "_result", lambda args: review)

    assert main(["relevance", "review", "--packet", "unread.json"]) == 0

    text = relevance_cli.format_review(review)
    assert capsys.readouterr().out == text + "\n"
    lines = text.splitlines()
    assert lines[0] == (f"relevance review {review['review_id']} of {review['subject']} "
                        f"({review['domain']['policy_version']}, {review['fingerprint']})")
    assert lines[1].startswith("disposition: propose pause_recoverably (")
    assert lines[-1] == "  applies effects: no"


# Two agreeing estimates of one dimension are two predictions about one target. An observation
# of it confirms both and is listed nowhere else: is-member answers once per occurrence of the
# repeated target, and inside the counting table's row it would answer the whole assessment
# twice unless the targets are made unique first, which this test holds in place.
# am[verifies a-rel-review-contract-1016@d0bea9] am[verifies c-rel-member-commit-1017@889086]
# am[verifies c-rel-rcpt-member-needs-unique-1017@222657]
def test_an_observation_confirms_every_prediction_about_its_target_and_is_counted_once() -> None:
    twice = {**PAUSE_EFFECTS,
             "recoverability": [("strongly-positive", "deterministic"), ("strongly-positive", "measured")]}
    review = record(effects=twice)
    assert [e["dimension"] for e in review["proposal"]["predicted_effects"]].count("recoverability") == 2

    assessment = assess_receipt(review, receipt(seen("recoverability"), fingerprint=review["fingerprint"]), budget=request_budget())

    recoverability = [e for e in assessment["effects"] if e["dimension"] == "recoverability"]
    assert [e["status"] for e in recoverability] == ["confirmed", "confirmed"]
    assert all(len(e["observations"]) == 1 for e in recoverability)
    assert assessment["uncounted"] == []
    assert {c["status"] for c in assessment["contributions"]} == {"predicted"}
    assert assessment["goals"] == [{"goal": "least_commitment", "achievement": "unverified"}]


# am[verifies a-rel-review-contract-1016@d0bea9] am[rests-on c-integrate-agenticmind-effects-1016@7fdbf0]
def test_observations_confirm_miss_or_conflict_and_a_duplicate_counts_once() -> None:
    assessment = assess_receipt(
        record(),
        receipt(
            seen("recoverability"),
            seen("recoverability", note="read again"),
            seen("option-value", "contradicted"),
            seen("least_commitment", "confirmed", about="contribution"),
            seen("least_commitment", "contradicted", "deterministic", about="contribution"),
        ), budget=request_budget(),
    )

    status = {e["dimension"]: e["status"] for e in assessment["effects"]}
    assert status == {"option-value": "missed", "recoverability": "confirmed"}
    assert len(effect(assessment, "recoverability")["observations"]) == 1
    assert assessment["contributions"][0]["status"] == "conflicted"
    assert assessment["goals"][0]["achievement"] == "unverified"


# Section 8.2 defines both classes as predictive estimates, so neither can say what happened.
# am[verifies a-rel-review-contract-1016@d0bea9] am[verifies c-rel-establishing-classes-1016@72edbb]
@pytest.mark.parametrize("estimator", ["model-proposed", "receipt-calibrated"])
def test_an_estimated_observation_and_an_unapplied_action_credit_nothing(estimator: str) -> None:
    guessed = assess_receipt(record(), receipt(seen("recoverability", estimator=estimator)), budget=request_budget())
    unapplied = assess_receipt(record(), receipt(seen("recoverability"), applied_at=None), budget=request_budget())

    assert effect(guessed, "recoverability")["status"] == "predicted"
    assert reasons(guessed) == ["cannot-establish"]
    assert unapplied["applied"] is False and unapplied["applied_at"] is None
    assert {e["status"] for e in unapplied["effects"]} == {"not-attempted"}
    assert reasons(unapplied) == ["not-applied"]


# am[verifies a-rel-review-contract-1016@d0bea9]
@pytest.mark.parametrize(
    "kwargs, message",
    [({"fingerprint": "sha256:other"}, "the receipt names review"), ({"action": "continue_task"}, "proposed pause_recoverably")],
)
def test_a_receipt_for_another_review_or_action_is_rejected(kwargs: dict, message: str) -> None:
    with pytest.raises(RelevanceError, match=message) as raised:
        assess_receipt(record(), receipt(**kwargs), budget=request_budget())
    assert raised.value.code == "invalid-record"


# ce1 and the application instant itself: an observation counts only once the action was applied,
# and the instant is compared whatever offset it is written in.
# am[verifies a-rel-rcpt-v2-counting-1017@ae46fe] am[verifies c-rel-rcpt-ce-73fa8ff-1017@e4b726]
@pytest.mark.parametrize(
    "observed_at",
    [AS_OF - timedelta(minutes=30), APPLIED_AT, "2026-10-16T20:02:00+11:00"],
    ids=["before the review", "at the application", "at the application, written at +11:00"],
)
def test_an_observation_at_or_before_the_application_confirms_nothing(observed_at) -> None:
    assessment = assess_receipt(record(), receipt(seen("recoverability", observed_at=observed_at)), budget=request_budget())

    assert effect(assessment, "recoverability")["status"] == "predicted"
    assert reasons(assessment) == ["before-application"]


# ce3: the review's own supporting reading handed back as its outcome, same source and time.
# am[verifies a-rel-rcpt-v2-counting-1017@ae46fe] am[verifies c-rel-rcpt-readings-precede-as-of-1017@54e66d]
def test_the_reviews_own_reading_never_comes_back_as_its_outcome() -> None:
    timed = (
        reading("state_preservation_route", "detected", "deterministic", source="checkpoint-store:cp-275",
                observed_at=AS_OF - timedelta(minutes=2)),
        *READINGS[1:],
    )
    review = record(readings=timed)
    handed_back = seen("recoverability", estimator="deterministic", source="checkpoint-store:cp-275",
                       observed_at=AS_OF - timedelta(minutes=2))

    assessment = assess_receipt(review, receipt(handed_back, fingerprint=review["fingerprint"]), budget=request_budget())

    assert effect(assessment, "recoverability")["status"] == "predicted"
    assert reasons(assessment) == ["before-application"]


# ce2: an observation with no time cannot be shown to follow the application.
# am[verifies a-rel-rcpt-v2-counting-1017@ae46fe] am[verifies c-rel-rcpt-untimed-loophole-1017@cf7c9c]
def test_an_untimed_observation_confirms_nothing() -> None:
    assessment = assess_receipt(record(), receipt(seen("recoverability", observed_at=None)), budget=request_budget())

    assert effect(assessment, "recoverability")["status"] == "predicted"
    assert reasons(assessment) == ["untimed"]


# ce4, the application's own bounds, and every producer a receipt cannot have, including one
# named by a receipt that applied nothing.
# am[verifies a-rel-rcpt-v2-schema-1017@df2f55] am[verifies c-rel-rcpt-produced-needs-application-1017@8afb25]
# am[verifies c-rel-rcpt-exact-instants-1017@c56a05] am[verifies c-rel-fromisoformat-truncates-1017@616584]
# am[verifies a-rel-rcpt-v2-metta-rules-1018@c22bf6]
@pytest.mark.parametrize(
    "payload, message",
    [
        (lambda: receipt_payload(seen("recoverability", observed_at=ISSUED_AT + MICROSECOND)), "after the receipt was issued"),
        (lambda: receipt_payload(applied_at=ISSUED_AT + MICROSECOND), "is after the receipt was issued"),
        (lambda: receipt_payload(applied_at=AS_OF - MICROSECOND), "before decision rr-test was made"),
        (lambda: receipt_payload(seen("recoverability", produced_by="exec-2")), "the receipt is for attempt exec-1"),
        (lambda: receipt_payload(seen("recoverability", produced_by="exec-1", observed_at=None)), "observed after the application"),
        (lambda: receipt_payload(seen("recoverability", produced_by="exec-1", observed_at=APPLIED_AT)), "observed after the application"),
        (lambda: receipt_payload(seen("recoverability", produced_by="exec-1"), applied_at=None), "the receipt applied nothing"),
        (lambda: receipt_payload(seen("recoverability", observed_at="2026-10-16T09:06:00.0000004+00:00")), "finer than a microsecond"),
        (lambda: receipt_payload(seen("recoverability", observed_at="2026-10-16T09:06:00")), "must carry a timezone offset"),
        (lambda: receipt_payload(issued_at="the twentieth"), "must be an ISO-8601 time"),
    ],
    ids=["observed after issue", "applied after issue", "applied before the review", "another attempt's product",
         "an untimed product", "a product at the application", "a product of nothing applied",
         "finer than a microsecond", "no offset", "not a time"],
)
def test_a_receipt_that_contradicts_its_own_times_is_an_invalid_record(payload, message: str) -> None:
    with pytest.raises(RelevanceError, match=message) as raised:
        assess_receipt(record(), parse_receipt(payload(), budget=request_budget()), budget=request_budget())

    assert raised.value.code == "invalid-record"


# am[verifies a-rel-rcpt-v2-schema-1017@df2f55]
def test_a_v1_receipt_is_refused_naming_what_it_lacks() -> None:
    v1 = {"protocol": "goalchainer-relevance-receipt-v1", "review_fingerprint": record()["fingerprint"],
          "action": "pause_recoverably", "applied": True, "observations": []}

    with pytest.raises(RelevanceError, match=r"unknown fields \['applied'\] and missing \['applied_at', 'attempt', 'issued_at'\]") as raised:
        parse_receipt(v1, budget=request_budget())

    assert raised.value.code == "invalid-record"


# A Receipt built without parse_receipt, here one whose observation follows its issue, is refused
# when it is assessed rather than counted.
# am[verifies a-rel-rcpt-v2-metta-rules-1018@c22bf6]
def test_a_receipt_built_without_parsing_is_refused_when_assessed() -> None:
    built = replace(receipt(seen("recoverability", observed_at=later(6))), issued_at=later(5))

    with pytest.raises(RelevanceError, match=r"observations\[0\] was observed at .* after the receipt was issued") as raised:
        assess_receipt(record(), built, budget=request_budget())

    assert raised.value.details["faults"] == [{"reason": "observed-after-issue", "observation": 0}]


# assess_attempt checks a receipt built past parse_receipt again too, so one whose application or
# observation follows its issue is refused rather than graded. Every receipt it grades was applied
# and observed by its issue instant, which a planner that grades only receipts issued by its own
# time rests on.
# am[verifies a-rel-assess-attempt-1018@20e6ca] am[verifies a-rel-rcpt-v2-metta-rules-1018@c22bf6]
# am[related a-ev-fb-snapshot-refused-1018@f8ac61]
@pytest.mark.parametrize(
    "built, fault",
    [
        (lambda: replace(receipt(seen(STEP_ACHIEVES, about="achieves", observed_at=later(6)),
                                 fingerprint="sha256:step-witness"), issued_at=later(5)),
         {"reason": "observed-after-issue", "observation": 0}),
        (lambda: replace(receipt(fingerprint="sha256:step-witness"), issued_at=APPLIED_AT - MICROSECOND),
         {"reason": "applied-after-issue", "observation": None}),
    ],
    ids=["an observation after its issue", "an application after its issue"],
)
def test_an_attempt_refuses_a_receipt_built_past_parsing_whose_times_follow_its_issue(built, fault: dict) -> None:
    with pytest.raises(RelevanceError) as raised:
        assess_attempt((("achieves", STEP_ACHIEVES),), built(), decided_at=AS_OF, budget=request_budget())

    assert raised.value.code == "invalid-record"
    assert raised.value.details["faults"] == [fault]


# An attempt is judged against the predictions its caller gives, in their order, what a step
# achieves among them, by the rules that judge a review's proposal; an observation nothing
# predicts is listed, and the review's names and bands belong to its own record alone.
# am[verifies a-rel-assess-attempt-1018@20e6ca]
def test_an_attempt_is_judged_against_the_predictions_its_caller_gives() -> None:
    predictions = (("achieves", STEP_ACHIEVES), ("effect", "recoverability"),
                   ("achieves", "(Signal safe_point_reachable)"))
    observed = receipt(
        seen(STEP_ACHIEVES, about="achieves", produced_by="exec-1"),
        seen("recoverability", "contradicted", estimator="deterministic"),
        seen("project_outcome", about="contribution"),
        fingerprint="sha256:step-witness",
    )

    assessment = assess_attempt(predictions, observed, decided_at=AS_OF, budget=request_budget())

    assert set(assessment) == {"attempt", "applied", "applied_at", "issued_at", "next_attempt_at",
                               "receipt_fingerprint", "predictions", "uncounted"}
    assert [(p["about"], p["target"], p["status"], p["attribution"]) for p in assessment["predictions"]] == [
        ("achieves", STEP_ACHIEVES, "confirmed", "asserted"),
        ("effect", "recoverability", "missed", "unestablished"),
        ("achieves", "(Signal safe_point_reachable)", "predicted", "unestablished"),
    ]
    assert [o["about"] for o in assessment["predictions"][0]["observations"]] == ["achieves"]
    assert reasons(assessment) == ["unpredicted"]
    assert (assessment["attempt"], assessment["applied_at"], assessment["receipt_fingerprint"]) == (
        "exec-1", "2026-10-16T09:02:00+00:00", observed.fingerprint
    )


# The decision's instant bounds the application to the microsecond, as a review's as_of does, and
# a refusal names the decision by the receipt's review_fingerprint.
# am[verifies a-rel-assess-attempt-1018@20e6ca] am[verifies c-rel-assessment-table-names-decision-1018@738b65]
def test_an_application_before_its_decision_is_refused_naming_the_decision() -> None:
    observed = receipt(fingerprint="sha256:step-witness")

    with pytest.raises(RelevanceError, match=r"applied at 2026-10-16T09:02:00\+00:00, before decision "
                                             r"sha256:step-witness was made at 2026-10-16T09:02:00\.000001\+00:00") as raised:
        assess_attempt((), observed, decided_at=APPLIED_AT + MICROSECOND, budget=request_budget())

    assert raised.value.code == "invalid-record"
    assert raised.value.details["faults"] == [{"reason": "applied-before-decision", "observation": None}]
    assert assess_attempt((), observed, decided_at=APPLIED_AT, budget=request_budget())["predictions"] == []


# am[verifies a-rel-assess-attempt-1018@20e6ca] am[verifies c-rel-attempt-inputs-invalid-record-1018@8bbff3]
@pytest.mark.parametrize(
    "predictions, decided_at, message",
    [
        ("effect", AS_OF, "predictions must be a sequence of"),
        ((("effect",),), AS_OF, r"predictions\[0\] must be an \(about, target\) pair"),
        ((("goal", "least_commitment"),), AS_OF, r"predictions\[0\] must be about one of effect, contribution, achieves"),
        ((("effect", "recoverability"), ("achieves", " ")), AS_OF, r"predictions\[1\]\.target must be nonempty text"),
        ((), AS_OF.replace(tzinfo=None), "decided_at must be a datetime with a timezone offset"),
        ((), "2026-10-16T09:00:00+00:00", "decided_at must be a datetime with a timezone offset"),
    ],
    ids=["not a sequence", "not a pair", "an unknown kind", "a blank target", "no offset", "text"],
)
def test_predictions_that_are_not_pairs_and_a_decision_time_without_an_offset_are_invalid_records(
    predictions, decided_at, message: str
) -> None:
    with pytest.raises(RelevanceError, match=message) as raised:
        assess_attempt(predictions, receipt(fingerprint="sha256:step-witness"), decided_at=decided_at,
                       budget=request_budget())

    assert raised.value.code == "invalid-record"


# Each time a receipt or one of its observations carries, read off the dataclasses, with whether
# its type admits None: an attempt that applied nothing, or an untimed observation.
# am[related a-integrate-built-receipt-instant-refusal-1018@43fdb6]
def receipt_times() -> list[tuple[type, str, bool]]:
    found = []
    for owner in (Receipt, Observation):
        hints = typing.get_type_hints(owner)
        for field in fields(owner):
            kinds = typing.get_args(hints[field.name]) or (hints[field.name],)
            if datetime in kinds:
                found.append((owner, field.name, type(None) in kinds))
    return found


# The pause receipt with one observation, its time `name` on the receipt or the observation set to
# `value` as code past parse_receipt could set it.
# am[related a-integrate-built-receipt-instant-refusal-1018@43fdb6]
def with_time(owner: type, name: str, value: object):
    built = receipt(seen(STEP_ACHIEVES, about="achieves"))
    if owner is Receipt:
        return replace(built, **{name: value})
    return replace(built, observations=(replace(built.observations[0], **{name: value}),))


# Both assessments a built receipt can reach, each value that is no timezone-aware instant, and every
# (time, value) pair a receipt can be given, None included where the time's type does not admit it.
# am[related a-integrate-built-receipt-instant-refusal-1018@43fdb6]
CONSUMERS = {
    "assess_receipt": lambda built: assess_receipt(record(), built, budget=request_budget()),
    "assess_attempt": lambda built: assess_attempt((("achieves", STEP_ACHIEVES),), built, decided_at=AS_OF,
                                                   budget=request_budget()),
}
NOT_INSTANTS = {"naive": datetime(2026, 10, 16, 9, 6), "text": "2026-10-16T09:06:00+00:00", "a date": date(2026, 10, 16)}
BAD_TIMES = [(owner, name, shape, value) for owner, name, optional in receipt_times()
             for shape, value in (*NOT_INSTANTS.items(), *(() if optional else (("none", None),)))]


# Both assessments check a receipt built past parse_receipt again, its times first: each time the
# receipt and its observations carry must be a timezone-aware datetime, None only where its type
# admits it, and any other value is an invalid-record naming the field before any time is
# compared, never a TypeError from the comparison.
# am[verifies a-integrate-built-receipt-instant-refusal-1018@43fdb6]
@pytest.mark.parametrize("consumer", sorted(CONSUMERS))
@pytest.mark.parametrize("owner, name, shape, value", BAD_TIMES, ids=[f"{name} {shape}" for _, name, shape, _ in BAD_TIMES])
def test_a_built_receipt_time_that_is_no_aware_instant_is_an_invalid_record(consumer, owner, name, shape, value) -> None:
    where = f"receipt.{name}" if owner is Receipt else f"receipt.observations[0].{name}"

    with pytest.raises(RelevanceError, match=re.escape(f"{where} must be a datetime with a timezone offset")) as raised:
        CONSUMERS[consumer](with_time(owner, name, value))

    assert raised.value.code == "invalid-record"


# None keeps its meaning where a time's type admits it: a built receipt that applied nothing, or whose
# observation is untimed, is still assessed, its observation listed with that reason.
# am[verifies a-integrate-built-receipt-instant-refusal-1018@43fdb6]
@pytest.mark.parametrize("consumer", sorted(CONSUMERS))
@pytest.mark.parametrize("owner, name", [(owner, name) for owner, name, optional in receipt_times() if optional],
                         ids=[name for _, name, optional in receipt_times() if optional])
def test_a_built_receipt_time_its_type_lets_be_none_is_still_assessed(consumer, owner, name) -> None:
    assessment = CONSUMERS[consumer](with_time(owner, name, None))

    assert reasons(assessment) == ["not-applied" if name == "applied_at" else "untimed"]


# A caller that reads a receipt's times itself, as the planner cutting receipts at a plan's time
# does, runs check_receipt first, the recheck parse_receipt and both assessments run: it hands back
# a coherent receipt unchanged and refuses a bad time or a statement the fault tables reject.
# am[verifies a-rel-check-receipt-public-1018@ac8018]
def test_check_receipt_returns_a_coherent_receipt_and_refuses_a_bad_time_or_a_fault() -> None:
    coherent = receipt(seen("recoverability"))
    assert check_receipt(coherent, budget=request_budget()) is coherent

    with pytest.raises(RelevanceError, match=re.escape("receipt.issued_at must be a datetime with a timezone offset")) as raised:
        check_receipt(with_time(Receipt, "issued_at", datetime(2026, 10, 16, 9, 20)), budget=request_budget())
    assert raised.value.code == "invalid-record"

    late = replace(receipt(seen("recoverability", observed_at=later(6))), issued_at=later(5))
    with pytest.raises(RelevanceError) as raised:
        check_receipt(late, budget=request_budget())
    assert raised.value.details["faults"] == [{"reason": "observed-after-issue", "observation": 0}]


# Each bound of the window is exact: the issue instant and the next attempt's instant are inside
# it, one microsecond later is not, and a seventh fraction digit that is zero names a whole
# microsecond.
# am[verifies a-rel-rcpt-v2-counting-1017@ae46fe] am[verifies c-rel-rcpt-exact-instants-1017@c56a05]
@pytest.mark.parametrize(
    "observed_at, next_attempt_at, counted",
    [
        (ISSUED_AT, None, True),
        ("2026-10-16T09:06:00.1234560+00:00", None, True),
        (later(6), later(6), True),
        (later(6) + MICROSECOND, later(6), False),
        (APPLIED_AT + MICROSECOND, None, True),
    ],
    ids=["at issue", "seven digits ending in zero", "at the next attempt", "just after the next attempt",
         "just after the application"],
)
def test_the_window_is_exact_at_its_bounds(observed_at, next_attempt_at, counted: bool) -> None:
    assessment = assess_receipt(record(), receipt(seen("recoverability", observed_at=observed_at)),
                                next_attempt_at=next_attempt_at, budget=request_budget())

    assert effect(assessment, "recoverability")["status"] == ("confirmed" if counted else "predicted")
    assert reasons(assessment) == ([] if counted else ["after-next-attempt"])


# am[verifies a-rel-rcpt-v2-schema-1017@df2f55] am[verifies c-rel-next-attempt-at-final-1017@a3d73f]
@pytest.mark.parametrize("next_attempt_at", [APPLIED_AT, APPLIED_AT - MICROSECOND])
def test_a_next_attempt_at_or_before_this_application_is_an_invalid_record(next_attempt_at) -> None:
    with pytest.raises(RelevanceError, match="is not after attempt exec-1's application") as raised:
        assess_receipt(record(), receipt(), next_attempt_at=next_attempt_at, budget=request_budget())

    assert raised.value.code == "invalid-record"


# am[verifies a-rel-rcpt-v2-schema-1017@df2f55] am[verifies c-rel-rcpt-readings-precede-as-of-1017@54e66d]
def test_an_application_at_the_reviews_own_instant_is_accepted() -> None:
    assessment = assess_receipt(record(), receipt(seen("recoverability"), applied_at=AS_OF), budget=request_budget())

    assert assessment["applied_at"] == "2026-10-16T09:00:00+00:00"
    assert effect(assessment, "recoverability")["status"] == "confirmed"


# An application at the instant the receipt was issued is inside the receipt that reports it.
# am[verifies a-rel-rcpt-v2-metta-rules-1018@c22bf6]
def test_an_application_at_the_issue_instant_is_accepted() -> None:
    assessment = assess_receipt(record(), receipt(applied_at=ISSUED_AT), budget=request_budget())

    assert assessment["applied_at"] == assessment["issued_at"] == "2026-10-16T09:20:00+00:00"


# ce5: two reviews half an hour apart on unchanged, unexpiring evidence share one fingerprint, so
# the attempt names the application, and each attempt's window holds only its own observations.
# am[verifies a-rel-rcpt-v2-assessment-1017@25ad31] am[verifies c-rel-rcpt-fingerprint-not-attempt-1017@ffd849]
def test_two_attempts_under_one_fingerprint_each_count_only_their_own_window() -> None:
    steady = (READINGS[0], replace(READINGS[1], valid_until=None), READINGS[2])
    first, second = record(readings=steady), record(readings=steady, as_of=later(30))
    assert first["fingerprint"] == second["fingerprint"]
    observation = seen("recoverability", observed_at=later(6))

    earlier = assess_receipt(first, receipt(observation, attempt="exec-1", fingerprint=first["fingerprint"]), budget=request_budget())
    later_one = assess_receipt(
        second,
        receipt(observation, attempt="exec-2", applied_at=later(31), issued_at=later(40), fingerprint=second["fingerprint"]), budget=request_budget(),
    )

    assert effect(earlier, "recoverability")["status"] == "confirmed"
    assert effect(later_one, "recoverability")["status"] == "predicted"
    assert reasons(later_one) == ["before-application"]
    assert earlier["receipt_fingerprint"] != later_one["receipt_fingerprint"]


# ce6: the same time and outcome, once from the checkpoint the pause wrote and named as its product,
# once from a checkpoint older than the pause. Both confirm; only the first is attributed. A
# human-asserted statement keeps its establishing class, and an estimate cannot attribute at all.
# am[verifies a-rel-rcpt-v2-counting-1017@ae46fe] am[verifies c-rel-rcpt-ordering-blind-to-cause-1017@83239a]
# am[verifies c-integrate-human-attribution-existing-policy-1017@f0de63]
@pytest.mark.parametrize(
    "observation, status, attribution, uncounted",
    [
        (seen("recoverability", source="checkpoint-store:cp-276", produced_by="exec-1"), "confirmed", "asserted", []),
        (seen("recoverability", source="checkpoint-store:cp-275"), "confirmed", "unestablished", []),
        (seen("recoverability", "contradicted", produced_by="exec-1"), "missed", "asserted", []),
        (seen("recoverability", estimator="human-asserted", produced_by="exec-1"), "confirmed", "asserted", []),
        (seen("recoverability", estimator="model-proposed", produced_by="exec-1"), "predicted", "unestablished",
         ["cannot-establish"]),
    ],
    ids=["the pause's checkpoint", "an older checkpoint", "a product that contradicts", "a person's statement",
         "an estimate"],
)
def test_only_a_statement_of_production_attributes_an_outcome(observation, status, attribution, uncounted) -> None:
    assessment = assess_receipt(record(), receipt(observation), budget=request_budget())

    assert (effect(assessment, "recoverability")["status"], effect(assessment, "recoverability")["attribution"]) == (
        status, attribution
    )
    assert reasons(assessment) == uncounted


# The policy compares a named producer with the attempt itself, so even a receipt the fault tables
# never read credits no other attempt's product.
# am[verifies a-rel-rcpt-v2-metta-rules-1018@c22bf6] am[verifies a-rel-rcpt-v2-counting-1017@ae46fe]
def test_the_policy_credits_only_a_product_of_this_attempt() -> None:
    attempt = term("Attempt", "exec-1", term("Applied", 10))
    predictions = items((term("Prediction", "effect", "recoverability"),))
    for producer, attribution in (("exec-1", "asserted"), ("exec-2", "unestablished")):
        observed = items((term("Observation", 0, "effect", "recoverability", "confirmed", "measured", term("At", 20),
                               term("ProducedBy", producer)),))

        answer = evaluate("gc-relevance-assess", attempt, 0, constant("Forever"), predictions, observed, budget=request_budget())

        assert answer[1][0][3:5] == ("confirmed", attribution)


# ce7: a confirmation and a contradiction after the action stay conflicted whatever their order,
# and a conflicted prediction is attributed to nothing even when one side names the attempt.
# am[verifies a-rel-rcpt-v2-counting-1017@ae46fe] am[verifies c-rel-rcpt-conflict-kept-1017@808ee5]
@pytest.mark.parametrize("first, second", [(later(6), later(15)), (later(15), later(6))])
def test_disagreeing_observations_stay_conflicted_in_either_order(first, second) -> None:
    assessment = assess_receipt(
        record(),
        receipt(seen("recoverability", observed_at=first, produced_by="exec-1"),
                seen("recoverability", "contradicted", observed_at=second)), budget=request_budget(),
    )

    assert (effect(assessment, "recoverability")["status"], effect(assessment, "recoverability")["attribution"]) == (
        "conflicted", "unestablished"
    )


# ce8: an observation of a goal the proposal makes no prediction about.
# am[verifies a-rel-rcpt-v2-counting-1017@ae46fe]
def test_an_observation_nothing_predicts_is_listed_unpredicted() -> None:
    assessment = assess_receipt(record(), receipt(seen("project_outcome", about="contribution")), budget=request_budget())

    assert reasons(assessment) == ["unpredicted"]
    assert {c["status"] for c in assessment["contributions"]} == {"predicted"}


# ce9: one observation has one id in every receipt that carries it, whatever its note or the
# offset its time is written in, so a store counts it once; the receipt fingerprint leaves notes
# out and changes with the attempt.
# am[verifies a-rel-rcpt-v2-assessment-1017@25ad31] am[verifies c-rel-rcpt-store-double-count-1017@e8bb76]
def test_one_observation_has_one_id_in_every_receipt() -> None:
    first = assess_receipt(record(), receipt(seen("recoverability", note="read at 09:06"), attempt="exec-1"), budget=request_budget())
    second = assess_receipt(record(), receipt(seen("recoverability", observed_at="2026-10-16T20:06:00+11:00"), attempt="exec-2"), budget=request_budget())
    renoted = assess_receipt(record(), receipt(seen("recoverability", note="another note"), attempt="exec-1"), budget=request_budget())

    ids = [effect(a, "recoverability")["observations"][0]["id"] for a in (first, second, renoted)]
    assert len(set(ids)) == 1 and ids[0].startswith("sha256:")
    assert effect(second, "recoverability")["observations"][0]["observed_at"] == "2026-10-16T09:06:00+00:00"
    assert first["receipt_fingerprint"] == renoted["receipt_fingerprint"] != second["receipt_fingerprint"]


# ce10: the pause applied at 09:02 and the same subject's next attempt applied at 09:30; what was
# seen at 09:40 is that attempt's state, and what was seen at 09:30 is still this one's.
# am[verifies a-rel-rcpt-v2-counting-1017@ae46fe] am[verifies c-rel-next-attempt-at-final-1017@a3d73f]
def test_an_observation_after_the_next_attempt_is_not_this_attempts() -> None:
    assessment = assess_receipt(
        record(),
        receipt(seen("recoverability", observed_at=later(40)), seen("option-value", observed_at=later(30)),
                issued_at=later(45)),
        next_attempt_at=later(30), budget=request_budget(),
    )

    assert assessment["next_attempt_at"] == "2026-10-16T09:30:00+00:00"
    assert effect(assessment, "recoverability")["status"] == "predicted"
    assert effect(assessment, "option-value")["status"] == "confirmed"
    assert reasons(assessment) == ["after-next-attempt"]


# A refused receipt is named by its first fault and lists every fault the tables found: the
# receipt's own, then each observation's first, in order.
# am[verifies a-rel-rcpt-v2-metta-rules-1018@c22bf6]
def test_a_refused_receipt_lists_every_fault_in_order() -> None:
    payload = receipt_payload(seen("recoverability", produced_by="exec-2"),
                              seen("option-value", observed_at=ISSUED_AT + MICROSECOND, produced_by="exec-2"),
                              seen("option-value"), applied_at=ISSUED_AT + MICROSECOND)

    with pytest.raises(RelevanceError, match="is after the receipt was issued") as raised:
        parse_receipt(payload, budget=request_budget())

    assert raised.value.code == "invalid-record"
    assert raised.value.details["faults"] == [
        {"reason": "applied-after-issue", "observation": None},
        {"reason": "producer-not-attempt", "observation": 0},
        {"reason": "observed-after-issue", "observation": 1},
    ]


FAULT_MOMENTS = [None, AS_OF - timedelta(minutes=30), APPLIED_AT, APPLIED_AT + MICROSECOND, ISSUED_AT,
                 ISSUED_AT + MICROSECOND]


# The fault tables restated in Python for a receipt as it is read: its own row, then each
# observation's first failing row, the observation given as (observed_at, produced_by).
# am[related a-rel-rcpt-v2-tests-1017@5f9488]
def expected_faults(applied, observations: list[tuple]) -> list[dict]:
    faults = [] if applied is None or applied <= ISSUED_AT else [{"reason": "applied-after-issue", "observation": None}]
    for index, (moment, producer) in enumerate(observations):
        stated = producer is not None
        reason = ("observed-after-issue" if moment is not None and moment > ISSUED_AT
                  else "producer-not-attempt" if stated and producer != "exec-1"
                  else "produced-without-application" if stated and applied is None
                  else "produced-before-application" if stated and (moment is None or not applied < moment)
                  else None)
        if reason is not None:
            faults.append({"reason": reason, "observation": index})
    return faults


# The assessment table restated in Python: the first of its rows a readable receipt fails.
# am[related a-rel-rcpt-v2-tests-1017@5f9488]
def expected_refusal(applied, closes) -> str | None:
    if applied is not None and applied < AS_OF:
        return "applied-before-decision"
    if applied is not None and closes is not None and not applied < closes:
        return "next-attempt-not-after-application"
    return None


# Every generated receipt is refused exactly when the tables say and with exactly their faults,
# as it is read and as it is assessed, and one they accept is assessed.
# am[verifies a-rel-rcpt-v2-metta-rules-1018@c22bf6] am[verifies a-rel-rcpt-v2-tests-1017@5f9488]
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_every_receipt_is_refused_exactly_as_the_fault_tables_say(data) -> None:
    applied = data.draw(st.sampled_from([None, AS_OF - MICROSECOND, AS_OF, APPLIED_AT, ISSUED_AT,
                                         ISSUED_AT + MICROSECOND]), label="applied")
    closes = data.draw(st.sampled_from([None, APPLIED_AT - MICROSECOND, APPLIED_AT, APPLIED_AT + MICROSECOND]),
                       label="closes")
    drawn = data.draw(st.lists(st.tuples(st.sampled_from(FAULT_MOMENTS), st.sampled_from([None, "exec-1", "exec-2"])),
                               max_size=4), label="observations")
    payload = receipt_payload(*(seen("recoverability", observed_at=moment,
                                     **({} if producer is None else {"produced_by": producer}))
                                for moment, producer in drawn), applied_at=applied)

    faults, refusal = expected_faults(applied, drawn), expected_refusal(applied, closes)
    if faults:
        with pytest.raises(RelevanceError) as raised:
            parse_receipt(payload, budget=request_budget())
        assert (raised.value.code, raised.value.details["faults"]) == ("invalid-record", faults)
    elif refusal is not None:
        with pytest.raises(RelevanceError) as raised:
            assess_receipt(record(), parse_receipt(payload, budget=request_budget()), next_attempt_at=closes, budget=request_budget())
        assert (raised.value.code, raised.value.details["faults"]) == (
            "invalid-record", [{"reason": refusal, "observation": None}]
        )
    else:
        assert assess_receipt(record(), parse_receipt(payload, budget=request_budget()), next_attempt_at=closes, budget=request_budget())["attempt"] == "exec-1"


# am[related a-rel-rcpt-v2-tests-1017@5f9488]
@functools.cache
def pause_review(twice: bool) -> dict:
    """The pause review, with recoverability predicted twice when `twice`."""

    if not twice:
        return record()
    return record(effects={**PAUSE_EFFECTS, "recoverability": [("strongly-positive", "deterministic"),
                                                               ("strongly-positive", "measured")]})


MOMENTS = [None, AS_OF - timedelta(minutes=30), APPLIED_AT, APPLIED_AT + MICROSECOND, later(10), later(15),
           later(15) + MICROSECOND, ISSUED_AT]
TARGETS = [("effect", "recoverability"), ("effect", "option-value"), ("contribution", "least_commitment"),
           ("contribution", "project_outcome"), ("achieves", STEP_ACHIEVES)]


# A review record's predictions: its proposal's effects, then its contributions.
# am[related a-rel-rcpt-v2-tests-1017@5f9488]
def review_predictions(review: dict) -> list[tuple[str, str]]:
    return [("effect", e["dimension"]) for e in review["proposal"]["predicted_effects"]] + [
        ("contribution", c["goal"]) for c in review["proposal"]["predicted_contributions"]
    ]


# The counting table and the attribution rule restated in Python: the oracle the policy is held to.
# am[related a-rel-rcpt-v2-tests-1017@5f9488] am[related a-rel-assess-attempt-1018@20e6ca]
def expected_assessment(predictions: list[tuple[str, str]], applied, closes, observations: list[dict]) -> tuple[list, list]:
    predicted = set(predictions)

    def reason(observation: dict) -> str | None:
        moment = observation.get("observed_at")
        if observation["estimator"] not in ("measured", "deterministic", "human-asserted"):
            return "cannot-establish"
        if applied is None:
            return "not-applied"
        if moment is None:
            return "untimed"
        if not applied < moment:
            return "before-application"
        if closes is not None and closes < moment:
            return "after-next-attempt"
        if (observation["about"], observation["target"]) not in predicted:
            return "unpredicted"
        return None

    rows = []
    for kind, target in predictions:
        counted = [o for o in observations if reason(o) is None and (o["about"], o["target"]) == (kind, target)]
        outcomes = {o["outcome"] for o in counted}
        status = ("not-attempted" if applied is None else "predicted" if not outcomes
                  else {"confirmed": "confirmed", "contradicted": "missed"}[outcomes.pop()] if len(outcomes) == 1
                  else "conflicted")
        agreeing = {"confirmed": "confirmed", "missed": "contradicted"}.get(status)
        attributed = any(o.get("produced") and o["outcome"] == agreeing for o in counted)
        rows.append((status, "asserted" if attributed else "unestablished"))
    return rows, [reason(o) for o in observations if reason(o) is not None]


# Every generated receipt is counted, graded and attributed exactly as the table and the rule say,
# with application and window bounds and every estimator class, the duplicated target included,
# against the review's proposal and against predictions its caller gives, repeated ones and what a
# step achieves among them.
# am[verifies a-rel-rcpt-v2-tests-1017@5f9488] am[verifies a-rel-rcpt-v2-counting-1017@ae46fe]
# am[verifies a-rel-assess-attempt-1018@20e6ca]
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_every_receipt_is_counted_graded_and_attributed_as_the_table_says(data) -> None:
    review = pause_review(data.draw(st.booleans(), label="twice"))
    applied = data.draw(st.sampled_from([None, APPLIED_AT]), label="applied")
    closes = data.draw(st.sampled_from([None, later(15)]), label="closes")
    predictions = data.draw(st.lists(st.sampled_from(TARGETS), max_size=4), label="predictions")
    drawn = data.draw(st.lists(st.tuples(st.sampled_from(TARGETS), st.sampled_from(["confirmed", "contradicted"]),
                                         st.sampled_from(sorted(vocabulary().classes)), st.sampled_from(MOMENTS),
                                         st.booleans()), max_size=5), label="observations")
    observations = [
        {"about": about, "target": target, "outcome": outcome, "estimator": estimator, "observed_at": moment,
         "source": f"ledger:{index}",
         # A producer only where one is credible; the invalid cases have their own test.
         "produced": produced and applied is not None and moment is not None and applied < moment}
        for index, ((about, target), outcome, estimator, moment, produced) in enumerate(drawn)
    ]
    wire = [
        {key: value for key, value in (("about", o["about"]), ("target", o["target"]), ("outcome", o["outcome"]),
                                       ("estimator", o["estimator"]), ("source", o["source"]),
                                       ("observed_at", None if o["observed_at"] is None else o["observed_at"].isoformat()),
                                       ("produced_by", "exec-1" if o["produced"] else None)) if value is not None}
        for o in observations
    ]
    parsed = receipt(*wire, applied_at=applied, fingerprint=review["fingerprint"])

    assessment = assess_receipt(review, parsed, next_attempt_at=closes, budget=request_budget())
    attempt = assess_attempt(predictions, parsed, decided_at=AS_OF, next_attempt_at=closes, budget=request_budget())

    rows, uncounted = expected_assessment(review_predictions(review), applied, closes, observations)
    graded = [(item["status"], item["attribution"]) for item in assessment["effects"] + assessment["contributions"]]
    assert graded == rows
    assert reasons(assessment) == uncounted
    assert {g["achievement"] for g in assessment["goals"]} == {"unverified"}
    rows, uncounted = expected_assessment(predictions, applied, closes, observations)
    assert [(p["about"], p["target"]) for p in attempt["predictions"]] == predictions
    assert [(p["status"], p["attribution"]) for p in attempt["predictions"]] == rows
    assert reasons(attempt) == uncounted


# The packet's times go through the same exact parser as the receipt's.
# am[verifies a-rel-rcpt-v2-instants-1017@3a3b0d]
@pytest.mark.parametrize("written, accepted", [("2026-10-16T08:59:00.0000004+00:00", False),
                                               ("2026-10-16T08:59:00.1234560+00:00", True)])
def test_a_packet_time_finer_than_a_microsecond_is_refused(written: str, accepted: bool) -> None:
    payload = json.loads(json.dumps(result().derived.packet.to_dict()))
    payload["readings"][0]["observed_at"] = written

    if accepted:
        assert parse_packet(payload).readings[0].observed_at.microsecond == 123456
    else:
        with pytest.raises(RelevanceError, match="finer than a microsecond") as raised:
            parse_packet(payload)
        assert raised.value.code == "invalid-packet"


# am[verifies a-rel-review-contract-1016@d0bea9]
def test_the_packet_round_trips_through_json() -> None:
    original = result().derived.packet

    assert parse_packet(json.loads(json.dumps(original.to_dict()))) == original
    assert original.as_of == AS_OF and original.readings[1].valid_until == AS_OF + timedelta(minutes=10)


# The edge the timeout tests stand on, checked rather than assumed.
# am[verifies c-rel-num-packet-timeout-edge-1018@c829b4]
def test_the_float_edge_is_the_least_integer_float_cannot_convert() -> None:
    assert float(FLOAT_EDGE - 1) == sys.float_info.max
    with pytest.raises(OverflowError):
        float(FLOAT_EDGE)


# am[related a-integrate-packet-number-refusal-1018@aecbf3]
def packet_payload(timeout: object) -> dict:
    payload = json.loads(json.dumps(packet(*READINGS).to_dict()))
    payload["budget"]["timeout_seconds"] = timeout
    return payload


# A packet's timeout is the float its review's budget runs under, so a number with no positive
# finite float is an invalid packet, an integer float() cannot convert included. The refusal names
# such an integer instead of writing it out.
# am[verifies a-integrate-packet-number-refusal-1018@aecbf3] am[verifies c-rel-num-packet-timeout-edge-1018@c829b4]
@pytest.mark.parametrize(
    ("timeout", "got"),
    [(10**1000, BEYOND_FLOAT), (-10**1000, BEYOND_FLOAT), (10**400, BEYOND_FLOAT), (FLOAT_EDGE, BEYOND_FLOAT),
     (float("inf"), "inf"), (float("nan"), "nan"), (0, "0"), (-1.5, "-1.5"), (True, "True"), ("60", "'60'"),
     (None, "None")],
    ids=["ten-to-the-1000", "minus-ten-to-the-1000", "ten-to-the-400", "float-edge", "inf", "nan", "zero",
         "negative", "true", "text", "null"],
)
def test_a_packet_timeout_with_no_positive_finite_float_is_an_invalid_packet(timeout: object, got: str) -> None:
    with pytest.raises(RelevanceError) as raised:
        parse_packet(packet_payload(timeout))

    assert raised.value.code == "invalid-packet"
    assert str(raised.value) == f"budget.timeout_seconds must be a positive finite number, got {got}"


# Every positive finite float is still a timeout, read as that float, up to the largest float, which
# the largest integer float() converts rounds to.
# am[verifies a-integrate-packet-number-refusal-1018@aecbf3] am[verifies a-rel-review-contract-1016@d0bea9]
@pytest.mark.parametrize("timeout", [7, 0.25, 1e-300, 10**300, FLOAT_EDGE - 1],
                         ids=["seven", "quarter", "tiny", "ten-to-the-300", "below-float-edge"])
def test_a_packet_timeout_with_a_positive_finite_float_is_read_as_that_float(timeout: object) -> None:
    read = parse_packet(packet_payload(timeout)).budget.timeout_seconds

    assert type(read) is float and read == float(timeout)


# One more digit than the interpreter writes as text, an integer JSON never carries but a Python
# caller's mapping can.
# am[related a-rel-packet-refusals-safe-repr-1018@c2f3f7]
UNWRITABLE = 10 ** sys.get_int_max_str_digits()
UNWRITTEN = f"of more than {sys.get_int_max_str_digits()} digits"


# A refusal is the packet's own typed error whatever value it rejected: each refusal that writes the
# value names one repr cannot write through errors.safe_repr, and unknown fields name a key that is
# no string, so a Python caller's mapping meets the same refusals JSON input does
# (c-rt-rr-packet-positive-int-repr-1018, c-rel-packet-refusals-constructed-1018).
# am[verifies a-rel-packet-refusals-safe-repr-1018@c2f3f7] am[verifies c-rel-packet-refusals-constructed-1018@2ab047]
@pytest.mark.parametrize(
    ("change", "message"),
    [(lambda p: p["budget"].__setitem__("inferences", -UNWRITABLE),
      f"budget.inferences must be a positive whole number, got a negative integer {UNWRITTEN}"),
     (lambda p: p["budget"].__setitem__("timeout_seconds", [UNWRITABLE]),
      "budget.timeout_seconds must be a positive finite number, got a value of type list whose repr raised ValueError"),
     (lambda p: p.__setitem__("protocol", [UNWRITABLE]),
      "packet protocol must be goalchainer-relevance-packet-v1, got a value of type list whose repr raised ValueError"),
     (lambda p: p.__setitem__(1, "x"), "packet has unknown fields: 1"),
     (lambda p: (p.__setitem__(1, "x"), p.__setitem__("zz", "y")), "packet has unknown fields: 1, zz")],
    ids=["negative-inferences", "timeout-list", "protocol-list", "int-key", "int-and-text-keys"],
)
def test_a_packet_refusal_is_its_typed_error_whatever_value_it_writes(change, message: str) -> None:
    payload = packet_payload(120.0)
    change(payload)

    with pytest.raises(RelevanceError) as raised:
        parse_packet(payload)
    assert raised.value.code == "invalid-packet" and str(raised.value) == message


# A positive inference count of any size is still a packet's bound, and admitting a looser caller
# budget under one too long to write is refused with the admission's own InvalidInputError, which
# names that bound instead of raising writing it.
# am[verifies a-rel-packet-refusals-safe-repr-1018@c2f3f7] am[verifies c-rel-packet-refusals-constructed-1018@2ab047]
def test_a_packet_bound_too_long_to_write_is_kept_and_its_admission_refusal_still_typed() -> None:
    payload = packet_payload(120.0)
    payload["budget"]["inferences"] = UNWRITABLE
    budget = parse_packet(payload).budget
    assert budget.inferences == UNWRITABLE

    with pytest.raises(InvalidInputError) as raised:
        budget.admit(RunBudget(inference_budget=None, timeout_seconds=60.0), "the review")
    assert f"at most an integer {UNWRITTEN} inferences and 120.0 seconds" in str(raised.value)


# The review command reads its packet as JSON: json.loads refuses an integer literal longer than the
# interpreter's digit limit with a plain ValueError, not a JSONDecodeError, and a shorter one beyond
# the float range reaches the packet's own refusal. Both are invalid packets.
# am[verifies a-integrate-packet-number-refusal-1018@aecbf3] am[verifies c-rel-num-reader-digit-limit-1018@824187]
@pytest.mark.parametrize("digits", [1001, sys.get_int_max_str_digits() + 1], ids=["beyond-float", "beyond-digit-limit"])
def test_the_review_command_refuses_a_timeout_it_cannot_read_as_an_invalid_packet(digits: int, tmp_path, capsys) -> None:
    written = json.dumps(packet_payload(120.0))
    path = tmp_path / "packet.json"
    path.write_text(written.replace('"timeout_seconds": 120.0', '"timeout_seconds": 1' + "0" * (digits - 1)), encoding="utf-8")
    assert path.read_text(encoding="utf-8") != written

    assert main(["relevance", "review", "--packet", str(path), "--json"]) == 1
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "invalid-packet"

    assert main(["relevance", "review", "--packet", str(path)]) == 1
    assert capsys.readouterr().err.startswith("goalchainer relevance error [invalid-packet]: ")


# Whatever stops a JSON input being read is that input's typed error, as a malformed one is: a file
# or standard input that is not UTF-8, and JSON nested deeper than json.loads reaches, for which it
# raises RecursionError. A packet is an invalid packet and a receipt an invalid record.
# am[verifies a-rel-cli-reader-unreadable-1018@cbbab6] am[verifies c-rel-cli-reader-leaks-1018@064e22]
@pytest.mark.parametrize(
    ("written", "said"),
    [(b'{"protocol": "\xff"}', "cannot be read as UTF-8 text: invalid start byte at byte 14"),
     (b"[" * 100_000 + b"]" * 100_000, "cannot be read as JSON: ")],
    ids=["not-utf-8", "nested-too-deep"],
)
def test_a_relevance_input_that_cannot_be_read_is_its_typed_error(written: bytes, said: str, tmp_path, monkeypatch, capsys) -> None:
    unreadable, review_path = tmp_path / "unreadable.json", tmp_path / "review.json"
    unreadable.write_bytes(written)
    review_path.write_text(json.dumps(record()), encoding="utf-8")
    commands = [(["relevance", "review", "--packet", str(unreadable)], "invalid-packet"),
                (["relevance", "assess", "--review", str(review_path), "--receipt", str(unreadable), *CLI_LIMITS],
                 "invalid-record")]

    for command, code in commands:
        assert main([*command, "--json"]) == 1
        error = json.loads(capsys.readouterr().out)["error"]
        assert error["code"] == code and said in error["message"]

    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(written), encoding="utf-8"))
    assert main(["relevance", "review", "--packet", "-", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid-packet"


# A packet whose review_id holds one byte that is no UTF-8, as a file or a pipe would carry it.
# am[related a-rel-cli-stdin-utf8-1018@18df88]
def packet_with_byte(byte: bytes) -> bytes:
    payload = packet_payload(120.0)
    payload["review_id"] = "rr-MARK"
    return json.dumps(payload).encode("utf-8").replace(b"rr-MARK", b"rr-" + byte)


# Standard input is read as bytes and decoded as UTF-8, as a file is, so a byte that is no UTF-8
# inside a packet string is refused in the file form's words, its source aside, whatever encoding
# and error handler the process would decode its standard input with.
# am[verifies a-rel-cli-stdin-utf8-1018@18df88] am[verifies c-rel-stdin-decodes-by-locale-1018@0bfd89]
@pytest.mark.parametrize(("encoding", "errors"), [("utf-8", "strict"), ("utf-8", "surrogateescape"), ("latin-1", "strict")],
                         ids=["utf-8-strict", "utf-8-surrogateescape", "latin-1"])
def test_standard_input_is_decoded_as_utf_8_as_a_file_is(encoding: str, errors: str, tmp_path, monkeypatch, capsys) -> None:
    written = packet_with_byte(b"\xff")
    path = tmp_path / "packet.json"
    path.write_bytes(written)
    cause = f"cannot be read as UTF-8 text: invalid start byte at byte {written.index(b'\xff')}"

    assert main(["relevance", "review", "--packet", str(path), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == {
        "code": "invalid-packet", "message": f"{path.resolve()}: {cause}", "details": {}}

    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(written), encoding=encoding, errors=errors))
    assert main(["relevance", "review", "--packet", "-", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == {
        "code": "invalid-packet", "message": f"standard input: {cause}", "details": {}}


# The review command as a child process, which decodes its standard input by its locale, UTF-8 mode
# or PYTHONIOENCODING: where that decoding would read the byte as a lone surrogate or as latin-1's
# ÿ, the packet is still refused as the file form refuses it. Each environment's decoding is
# checked first, so no case passes for want of its setting.
# am[verifies a-rel-cli-stdin-utf8-1018@18df88] am[verifies c-rel-stdin-decodes-by-locale-1018@0bfd89]
@pytest.mark.parametrize(
    ("setting", "decoding"),
    [({"LC_ALL": "C"}, "utf-8 surrogateescape"), ({"PYTHONUTF8": "1"}, "utf-8 surrogateescape"),
     ({"PYTHONIOENCODING": "utf-8:surrogateescape"}, "utf-8 surrogateescape"),
     ({"PYTHONIOENCODING": "latin-1"}, "iso8859-1 strict")],
    ids=["c-locale", "utf-8-mode", "surrogateescape", "latin-1"],
)
def test_the_review_process_refuses_a_packet_that_is_no_utf_8_on_standard_input(
    setting: dict[str, str], decoding: str, tmp_path
) -> None:
    env = child_environment(**{"LC_ALL": None, "LC_CTYPE": None, "PYTHONUTF8": None, "PYTHONIOENCODING": None, **setting})
    seen = subprocess.run([sys.executable, "-c", "import sys; print(sys.stdin.encoding, sys.stdin.errors)"],
                          input=b"", capture_output=True, env=env, check=True)
    assert seen.stdout.decode().strip() == decoding
    written = packet_with_byte(b"\xff")

    run = subprocess.run([sys.executable, "-c", "import sys; from goal_chainer.cli import main; sys.exit(main())",
                          "relevance", "review", "--packet", "-", "--json"],
                         input=written, capture_output=True, env=env, cwd=tmp_path)
    assert run.returncode == 1, run.stderr.decode("utf-8", "backslashreplace")
    assert json.loads(run.stdout)["error"] == {
        "code": "invalid-packet", "details": {},
        "message": f"standard input: cannot be read as UTF-8 text: invalid start byte at byte {written.index(b'\xff')}"}


# A closed standard input as a process meets it: with file descriptor 0 closed Python leaves
# sys.stdin None, and the review command refuses it as any unreadable standard input, where it once
# raised AttributeError (c-rel-stdin-closed-none-1018). The child checks its stdin is None first.
# am[verifies a-sc-relevance-reads-input-text-1018@0fe1b8] am[verifies c-rel-stdin-closed-none-1018@0ac374]
def test_the_review_process_refuses_a_closed_standard_input(tmp_path) -> None:
    closed = ["sh", "-c", 'exec "$@" <&-', "sh", sys.executable, "-c"]
    env = child_environment()
    seen = subprocess.run([*closed, "import sys; print(sys.stdin is None)"], capture_output=True, env=env, check=True)
    assert seen.stdout.decode().strip() == "True"

    run = subprocess.run([*closed, "import sys; from goal_chainer.cli import main; sys.exit(main())",
                          "relevance", "review", "--packet", "-", "--json"], capture_output=True, env=env, cwd=tmp_path)
    assert run.returncode == 1, run.stderr.decode("utf-8", "backslashreplace")
    assert json.loads(run.stdout)["error"] == {
        "code": "invalid-packet", "details": {}, "message": "standard input: cannot be read as UTF-8 text: it is no byte stream"}


# Every standard input with no byte stream to read is refused in the same words as one that is no
# UTF-8: none at all, text alone with no buffer beneath it, and a buffer already closed, whose read
# raises ValueError rather than OSError.
# am[verifies a-sc-relevance-reads-input-text-1018@0fe1b8] am[verifies a-integrate-input-text-closed-buffer-1018@7d108d]
@pytest.mark.parametrize("kind", ["none", "text-alone", "closed-buffer"])
def test_a_standard_input_with_no_byte_stream_to_read_is_an_invalid_packet(kind: str, monkeypatch, capsys) -> None:
    closed = io.TextIOWrapper(io.BytesIO(b"{}"), encoding="utf-8")
    closed.buffer.close()
    stdin = {"none": None, "text-alone": io.StringIO("{}"), "closed-buffer": closed}[kind]
    monkeypatch.setattr(sys, "stdin", stdin)

    assert main(["relevance", "review", "--packet", "-", "--json"]) == 1
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "invalid-packet"
    assert error["message"].startswith("standard input: cannot be read as UTF-8 text: ")
    if kind != "closed-buffer":
        assert error["message"].endswith(": it is no byte stream")

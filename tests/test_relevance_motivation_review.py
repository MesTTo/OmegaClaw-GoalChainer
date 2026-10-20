"""Purpose: verify that a review of a domain with needs ranks regulated goals by the reduction of their
needs' urgency, after the hard steps: an observed need changes the right choice, a satisfied agent
holds instead of repeating a discretionary action, duties and unregulated goals keep operating, an
unknown need never reads as satisfied, norms and required goals stay hard, the decision's
authority rests on the need evidence whatever value the reduction takes, tied actions are never split
by declaration order, a large finite priority keeps every recorded value finite, and the fingerprint
and freshness follow the snapshot."""

from __future__ import annotations

import math
import re

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from goal_chainer.relevance.errors import RelevanceError
from goal_chainer.relevance.canonical import canonical_json, fingerprint_of
from goal_chainer.relevance.freshness import check_freshness
from goal_chainer.relevance.review import REVIEW_PROTOCOL, engine_identity, review
from motivation_support import CORE, Obs, at, budget, domain, snapshot
from relevance_support import packet, reading

CALM = """
(gc-need calm competence (scale 0 1) (band 0.4 0.6) (drive 1) (need-source human:designer))
(gc-need-expectation empathize calm 0.1 measured (expectation-source pilot))
(gc-need-expectation guide_breath calm -0.4 measured (expectation-source pilot))
(gc-need-expectation stay_silent calm 0.0 measured (expectation-source pilot))
"""
NOW = 1000.0


# am[verifies a-v2m-drive-paths-1019@65a7d5]
def _review(text: str, observations=(), *, needs: bool = True):
    regulated = domain(text)
    current = packet(reading("session_open"), as_of=at(NOW))
    taken = snapshot(regulated, observations, now=NOW) if needs else None
    return review(regulated, current, budget=current.budget.run_budget(), motivation=taken), regulated, current


# The parent's counterexample decides the review: at 0.9 against [0.4, 0.6], guide_breath (-0.4)
# restores the need and empathize (+0.1) worsens it; without the need nothing separates them.
# am[verifies a-v2m-drive-paths-1019@65a7d5] am[verifies a-v2m-hold-1019@be4f47] am[verifies c-v2m-reduction-formula-1019@0fcd08]
def test_an_observed_need_decides_the_action_that_restores_it() -> None:
    result, _, _ = _review(CORE + CALM, [Obs("calm", 0.9, at(10))])
    record = result.to_dict()

    assert record["protocol"] == REVIEW_PROTOCOL == "goalchainer-relevance-review-v2"
    assert record["disposition"] == "propose" and record["proposal"]["action"] == "guide_breath"
    paths = {c["action"]: c["need_paths"][0]["value"] for c in record["candidates"]}
    assert paths["guide_breath"]["low"] == pytest.approx(0.6 * 0.75)
    assert paths["empathize"]["high"] == pytest.approx(0.6 * -0.25)
    assert [step["name"] for step in record["steps"]][2] == "motivational relevance"
    (predicted,) = record["proposal"]["predicted_need_changes"]
    assert predicted["status"] == "predicted" and predicted["expected_change"] == -0.4
    assert (predicted["observed_level"], predicted["level_state"]) == (0.9, "observed")
    assert predicted["predicted_level"] == {"low": 0.5, "high": 0.5} and "level" not in predicted
    plain, _, _ = _review(CORE, needs=False)
    assert plain.to_dict()["disposition"] == "escalate" and plain.to_dict()["motivation"] is None


# Every need inside its band: no discretionary action is proposed, so nothing repeats.
# am[verifies a-v2m-hold-1019@be4f47] am[verifies c-v2-satisfied-single-candidate-case-1019@2461e5]
def test_a_satisfied_agent_holds_and_names_its_satisfied_needs() -> None:
    result, _, _ = _review(CORE + CALM, [Obs("calm", 0.5, at(10))])
    record = result.to_dict()

    assert record["disposition"] == "hold" and record["proposal"] is None
    assert record["hold"] == {"satisfied": ["calm"], "unserved": []}
    removed = {item["action"]: item["reason"] for item in record["steps"][2]["eliminated"]}
    assert set(removed) == {"empathize", "guide_breath", "stay_silent"}


# A duty survives a satisfied agent: lifecycle keeps the obliged action and step 2b never judges it.
# am[verifies a-v2m-hold-1019@be4f47] am[verifies c-v2m-hard-steps-ignore-priority-1019@3a77a5]
def test_a_duty_is_proposed_whatever_the_needs() -> None:
    duty = CORE + CALM + "(normally rDuty (signal session_open) (must (do stay_silent)))\n"
    result, _, _ = _review(duty, [Obs("calm", 0.5, at(10))])

    assert result.to_dict()["disposition"] == "propose" and result.to_dict()["proposal"]["action"] == "stay_silent"


# An unknown need is never satisfied: with every change known to be 0 every interval is [0, 0], yet
# the review escalates for the unknown level instead of holding (c-v2m-unknown-never-holds-1019).
# am[verifies a-v2m-hold-1019@be4f47] am[verifies c-v2m-unknown-never-holds-1019@7b14f5]
def test_an_unknown_need_escalates_instead_of_holding() -> None:
    still = CORE + """
(gc-need calm competence (scale 0 1) (band 0.4 0.6) (drive 1) (need-source human:designer))
(gc-need-expectation empathize calm 0.0 measured (expectation-source pilot))
(gc-need-expectation guide_breath calm 0.0 measured (expectation-source pilot))
(gc-need-expectation stay_silent calm 0.0 measured (expectation-source pilot))
"""
    record = _review(still)[0].to_dict()

    assert record["disposition"] == "escalate" and record["hold"] is None
    assert any("calm" in reason and "observe" in reason for reason in record["escalation"]["reasons"])
    unknown = _review(CORE + CALM)[0].to_dict()
    (reason,) = unknown["escalation"]["reasons"]
    assert unknown["disposition"] == "escalate" and "the unknown levels or expected changes of calm" in reason
    assert "no dimension" not in reason
    assert unknown["missing_information"]["unknown_needs"] == ["calm"]
    assert unknown["missing_information"]["conflicted_needs"] == unknown["missing_information"]["unknown_need_changes"] == []


# A forbidden best reducer is never proposed, and the rest, unable to reduce the need, hold with it
# unserved.
# am[verifies a-v2m-hold-1019@be4f47] am[verifies c-v2m-hard-steps-ignore-priority-1019@3a77a5]
def test_a_forbidden_reducer_stays_forbidden_and_the_need_is_unserved() -> None:
    forbidden = CORE + CALM + "(always rNo (signal session_open) (forbidden (do guide_breath)))\n"
    record = _review(forbidden, [Obs("calm", 0.9, at(10))])[0].to_dict()

    assert record["steps"][0]["eliminated"][0]["action"] == "guide_breath"
    assert record["disposition"] == "hold" and record["hold"] == {"satisfied": [], "unserved": ["calm"]}


# A required goal's harm, declared by the theory, still removes the action in step 2, whatever the
# need's measured reduction says.
# am[verifies a-v2m-hold-1019@be4f47] am[verifies c-v2m-hard-steps-ignore-priority-1019@3a77a5]
def test_harm_to_a_required_goal_still_removes_the_best_reducer() -> None:
    required = CORE + CALM + """
(normally rReq (signal session_open) (required competence))
(normally rHarm (signal session_open) (contributes guide_breath competence negative))
"""
    record = _review(required, [Obs("calm", 0.9, at(10))])[0].to_dict()

    assert {item["action"] for item in record["steps"][1]["eliminated"]} >= {"guide_breath"}
    assert record["proposal"] is None or record["proposal"]["action"] != "guide_breath"


# An unregulated goal keeps operating when every regulated need is satisfied.
# am[verifies a-v2m-hold-1019@be4f47]
def test_an_unregulated_goal_keeps_its_action_motivated() -> None:
    goal = CORE + CALM + "(normally rServe (signal session_open) (contributes empathize nurturing positive))\n"
    record = _review(goal, [Obs("calm", 0.5, at(10))])[0].to_dict()

    assert record["disposition"] == "propose" and record["proposal"]["action"] == "empathize"


# A model-proposed level licenses only the model-proposed ceiling.
# am[verifies a-v2m-need-authority-1019@52deb8]
def test_a_model_proposed_level_lowers_the_licensed_authority() -> None:
    record = _review(CORE + CALM, [Obs("calm", 0.9, at(10), estimator="model-proposed")])[0].to_dict()

    assert record["proposal"]["action"] == "guide_breath"
    assert record["proposal"]["licensed_authority_ceiling"] == "advisory"
    assert {"basis": "need-level:calm", "estimator": "model-proposed", "ceiling": "advisory"} in record["proposal"]["authority_limits"]


# A reduction of exactly 0 still rests on the level and the change it was computed from: at 0.45
# empathize's +0.1 keeps calm inside [0.4, 0.6], where at 0.9 the same change would worsen it, so a
# model-proposed level licenses empathize, carried by an unregulated goal, only at advisory.
# am[verifies a-v2m-need-authority-1019@52deb8] am[verifies c-v2m-zero-reduction-rests-1020@0f4fab]
def test_a_zero_reduction_still_rests_on_the_level_and_change_behind_it() -> None:
    goal = CORE + CALM + "(normally rServe (signal session_open) (contributes empathize nurturing positive))\n"
    record = _review(goal, [Obs("calm", 0.45, at(10), estimator="model-proposed")])[0].to_dict()

    paths = next(item for item in record["candidates"] if item["action"] == "empathize")["need_paths"]
    assert record["disposition"] == "propose" and record["proposal"]["action"] == "empathize"
    assert [path["value"] for path in paths] == [{"low": 0.0, "high": 0.0}]
    assert record["proposal"]["licensed_authority_ceiling"] == "advisory"
    assert {"basis": "need-level:calm", "estimator": "model-proposed", "ceiling": "advisory"} in record["proposal"]["authority_limits"]


# A goal of a large finite priority keeps every value the review records finite: empathize's one
# band path is the point 1e308, whose ends' sum overflowed before the midpoint halved large ends.
# am[verifies a-v2m-drive-paths-1019@65a7d5] am[verifies c-v2m-midpoint-libcxx-1020@5020e4]
def test_a_large_finite_priority_keeps_the_projection_finite() -> None:
    huge = (CORE.replace("individual 0.9", "individual 1e308") + CALM
            + "(normally rServe (signal session_open) (contributes empathize nurturing strongly-positive))\n")
    record = _review(huge, [Obs("calm", 0.5, at(10))])[0].to_dict()

    projections = {item["action"]: item["projection"] for item in record["display_order"]}
    assert all(math.isfinite(value) for value in projections.values())
    assert projections["empathize"] == 1e308 and record["proposal"]["action"] == "empathize"


# A new observation stales the review even when the level it gives is unchanged, since the support
# moved; the same snapshot keeps it fresh; a version-1 record is refused, never called stale.
# am[verifies a-v2m-snapshot-identity-1019@118a4b] am[verifies c-v2-motivation-freshness-obligation-1019@ad4628]
# am[verifies c-v2m-v1-refused-1019@5724e4]
def test_the_fingerprint_and_freshness_follow_the_snapshot() -> None:
    first = [Obs("calm", 0.9, at(10), name="o1")]
    result, regulated, current = _review(CORE + CALM, first)
    record = result.to_dict()
    engine = engine_identity(budget=budget())
    same = snapshot(regulated, first, now=NOW)
    moved = snapshot(regulated, [*first, Obs("calm", 0.9, at(20), name="o2")], now=NOW)

    fresh = check_freshness(record, regulated, current, engine, budget=current.budget.run_budget(), motivation=same)
    stale = check_freshness(record, regulated, current, engine, budget=current.budget.run_budget(), motivation=moved)
    assert (fresh.status, fresh.motivation_changed) == ("fresh", False)
    assert (stale.status, stale.motivation_changed) == ("stale", True)
    again = review(regulated, current, budget=current.budget.run_budget(), motivation=moved)
    assert again.fingerprint != result.fingerprint and again.ranking.disposition == result.ranking.disposition
    with pytest.raises(RelevanceError) as refused:
        check_freshness({**record, "protocol": "goalchainer-relevance-review-v1"}, regulated, current, engine,
                        budget=current.budget.run_budget(), motivation=same)
    assert refused.value.code == "invalid-record"


# A review that ranked by a named stream is compared only with that stream: checked with no
# snapshot, or with another stream's, it is refused rather than called stale. A review that ranked
# by no stream checks fresh without one and goes stale against any named stream's snapshot, one
# holding an observation or one holding nothing, since the snapshot's identity names its stream.
# am[verifies a-v2m-freshness-stream-explicit-1020@5eabf7] am[verifies i-v2r-freshness-empty-stream-doc-1020]
def test_freshness_compares_a_review_only_with_the_stream_it_ranked_by() -> None:
    first = [Obs("calm", 0.9, at(10), name="o1")]
    result, regulated, current = _review(CORE + CALM, first)
    record, engine = result.to_dict(), engine_identity(budget=budget())

    for motivation in (None, snapshot(regulated, first, now=NOW, stream="another")):
        with pytest.raises(RelevanceError) as refused:
            check_freshness(record, regulated, current, engine, budget=current.budget.run_budget(), motivation=motivation)
        assert refused.value.code == "invalid-motivation"
    unnamed = review(regulated, current, budget=current.budget.run_budget()).to_dict()
    alone = check_freshness(unnamed, regulated, current, engine, budget=current.budget.run_budget())
    observed = check_freshness(unnamed, regulated, current, engine, budget=current.budget.run_budget(),
                               motivation=snapshot(regulated, first, now=NOW))
    empty = check_freshness(unnamed, regulated, current, engine, budget=current.budget.run_budget(),
                            motivation=snapshot(regulated, (), now=NOW))
    assert (alone.status, observed.status, observed.motivation_changed) == ("fresh", "stale", True)
    assert (empty.status, empty.motivation_changed) == ("stale", True)


# A snapshot belongs to one domain and one instant.
# am[verifies a-v2m-snapshot-identity-1019@118a4b]
def test_a_snapshot_for_another_review_is_refused() -> None:
    regulated = domain(CORE + CALM)
    current = packet(reading("session_open"), as_of=at(NOW))
    with pytest.raises(RelevanceError) as late:
        review(regulated, current, budget=current.budget.run_budget(), motivation=snapshot(regulated, now=NOW - 1))
    with pytest.raises(RelevanceError) as plain:
        review(domain(CORE), current, budget=current.budget.run_budget(), motivation=snapshot(regulated, now=NOW))
    assert late.value.code == plain.value.code == "invalid-motivation"


# The companion domain with its actions, their candidate rules and their expectations declared in
# `order`: empathize and guide_breath change calm alike, by `change`, and stay_silent leaves it.
# am[verifies a-v2m-drive-paths-1019@65a7d5]
def _declared_in(order: list[str], change: float) -> str:
    lines = CORE.strip().splitlines()
    actions = {a: next(line for line in lines if line.startswith(f"(gc-action {a} ")) for a in order}
    rules = {a: next(line for line in lines if line.endswith(f"(candidate {a}))")) for a in order}
    rest = [line for line in lines if line not in actions.values() and line not in rules.values()]
    expectations = [f"(gc-need-expectation {a} calm {0.0 if a == 'stay_silent' else change} measured (expectation-source pilot))"
                    for a in order]
    need = "(gc-need calm competence (scale 0 1) (band 0.4 0.6) (drive 1) (need-source human:designer))"
    return "\n".join([*rest, *(actions[a] for a in order), *(rules[a] for a in order), need, *expectations]) + "\n"


# Two actions declared alike tie, so the review never proposes either, and declaring the actions,
# their candidate rules and their expectations in another order leaves its decision as it was: the
# disposition, the proposal, the contested candidates, the hold and the reasons, whose prose lists
# candidates in declaration order and so is compared word for word in any order.
# am[verifies a-v2m-drive-paths-1019@65a7d5] am[verifies a-v2m-hold-1019@be4f47] am[verifies c-v2m-lead-conservative-1019@d314ac]
@settings(max_examples=8, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(level=st.one_of(st.none(), st.floats(0.0, 1.0)), change=st.sampled_from([-0.4, -0.1, 0.0, 0.2]),
       order=st.permutations(["empathize", "guide_breath", "stay_silent"]))
def test_tied_actions_are_never_split_and_declaration_order_changes_nothing(level, change, order) -> None:
    observations = [] if level is None else [Obs("calm", level, at(10))]

    def decision(record: dict) -> tuple:
        escalation = record["escalation"] or {"reasons": [], "contested": []}
        reasons = sorted(tuple(sorted(re.findall(r"[\w-]+", reason))) for reason in escalation["reasons"])
        return (record["disposition"], record["proposal"] and record["proposal"]["action"],
                reasons, sorted(escalation["contested"]), record["hold"])

    canonical = decision(_review(_declared_in(["empathize", "guide_breath", "stay_silent"], change), observations)[0].to_dict())
    permuted = decision(_review(_declared_in(list(order), change), observations)[0].to_dict())
    assert permuted == canonical
    assert canonical[1] not in ("empathize", "guide_breath")


# Whatever the needs' levels, steps 1 and 2 remove what they remove without needs: norms and
# duties never move with motivation.
# am[verifies a-v2m-hold-1019@be4f47] am[verifies c-v2m-hard-steps-ignore-priority-1019@3a77a5]
@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(level=st.one_of(st.none(), st.floats(0.0, 1.0)), forbid=st.booleans(), oblige=st.booleans())
def test_steps_one_and_two_ignore_the_needs(level, forbid, oblige) -> None:
    theory = (("(always rNo (signal session_open) (forbidden (do guide_breath)))\n" if forbid else "")
              + ("(normally rDuty (signal session_open) (must (do stay_silent)))\n" if oblige else ""))
    observations = [] if level is None else [Obs("calm", level, at(10))]
    regulated = _review(CORE + CALM + theory, observations)[0].to_dict()
    plain = _review(CORE + theory, needs=False)[0].to_dict()

    assert regulated["steps"][:2] == plain["steps"][:2]
    assert regulated["blockers"] == plain["blockers"]


# A need left at 0.1 below band [0.2, 0.4] that guide_breath's +0.4 leaves 0.1 above it is reduced
# by exactly nothing on these binary64 inputs, as by stay_silent and empathize, so the review holds
# with calm unserved; rounding once read guide_breath's reduction as 5.55e-17 and proposed it.
# am[verifies a-v2r-exact-sign-1020] am[verifies a-v2m-hold-1019@be4f47]
def test_a_balanced_overshoot_reduces_nothing_and_the_review_holds() -> None:
    balanced = CORE + """
(gc-need calm competence (scale 0 1) (band 0.2 0.4) (drive 1) (need-source human:designer))
(gc-need-expectation empathize calm 0.0 measured (expectation-source pilot))
(gc-need-expectation guide_breath calm 0.4 measured (expectation-source pilot))
(gc-need-expectation stay_silent calm 0.0 measured (expectation-source pilot))
"""
    record = _review(balanced, [Obs("calm", 0.1, at(10))])[0].to_dict()

    assert record["disposition"] == "hold" and record["proposal"] is None
    assert record["hold"] == {"satisfied": [], "unserved": ["calm"]}
    reduction = next(item for item in record["motivation"]["reductions"] if item["action"] == "guide_breath")
    assert (reduction["low"], reduction["high"]) == (0.0, 0.0)


# missing_information names every need whose level is unknown or conflicted, and each candidate's
# unknown expected change, so what an observation or a learned change would settle is in the record.
# am[verifies a-v2r-undecided-need-named-1020]
def test_missing_information_names_conflicted_needs_and_unknown_changes() -> None:
    partial = CORE + """
(gc-need calm competence (scale 0 1) (band 0.4 0.6) (drive 1) (need-source human:designer))
(gc-need-expectation guide_breath calm -0.4 measured (expectation-source pilot))
"""
    record = _review(partial, [Obs("calm", 0.9, at(10), name="o1"), Obs("calm", 0.2, at(10), name="o2")])[0].to_dict()

    missing = record["missing_information"]
    assert (missing["unknown_needs"], missing["conflicted_needs"]) == ([], ["calm"])
    assert missing["unknown_need_changes"] == [{"action": "empathize", "need": "calm"}, {"action": "stay_silent", "need": "calm"}]


# A review records its snapshot in one size whatever the stream's length: the history it read by
# count and digest, each change's sample count and the SHA-256 commitment to its keys, and no
# per-sample list, which a status read through the history's count recovers.
# am[verifies a-v2r-record-digest-1020]
def test_a_review_records_its_history_and_commitments_instead_of_its_samples() -> None:
    record = _review(CORE + CALM, [Obs("calm", 0.9, at(10))])[0].to_dict()

    motivation = record["motivation"]
    assert motivation["history"] == {"event_count": 1, "digest": "sha256:fixture"}
    assert not {"samples", "not_sampled", "excluded", "protocol"} & set(motivation)
    change = next(item for item in motivation["changes"] if item["action"] == "guide_breath")
    assert change["count"] == 0 and change["samples_digest"].startswith("sha256:") and "samples" not in change
    assert motivation["snapshot"]["changes"]["guide_breath calm"]["samples_digest"] == change["samples_digest"]


# A level's support is recorded by count, commitment and estimator classes: any number of sources
# reporting one level at the latest instant leave the review's level entry, and the identity a
# freshness check compares, one size, while the full snapshot a status read answers lists every
# source with its class; one source more changes the commitment, so the review goes stale.
# am[verifies a-v2r-level-support-digest-1020]
def test_a_levels_support_is_recorded_by_commitment_however_many_sources_agree() -> None:
    def observed(sources, classes=("measured",)):
        return [Obs("calm", 0.9, at(10), name=f"sensor:{index}", estimator=classes[index % len(classes)])
                for index in range(sources)]

    def entry(observations):
        result, regulated, current = _review(CORE + CALM, observations)
        record = result.to_dict()
        return record, regulated, current, next(item for item in record["motivation"]["levels"] if item["need"] == "calm")

    one, many = entry(observed(1))[3], entry(observed(64))[3]
    assert len(canonical_json(many)) - len(canonical_json(one)) == len("64") - len("1")
    record, regulated, current, level = entry(observed(64, ("measured", "human-asserted")))
    ids = sorted(observation.id for observation in observed(64, ("measured", "human-asserted")))
    assert "support" not in level and level["support_count"] == 64
    assert level["support_digest"] == fingerprint_of({"support": ids})
    assert level["support_estimators"] == ["human-asserted", "measured"]
    assert record["motivation"]["snapshot"]["levels"]["calm"] == {
        "state": "observed", "level": 0.9, "support_count": 64, "support_digest": level["support_digest"]}
    full = snapshot(regulated, observed(64, ("measured", "human-asserted")), now=NOW).to_dict()
    listed = next(item for item in full["levels"] if item["need"] == "calm")["support"]
    assert sorted(item["observation"] for item in listed) == ids

    report = check_freshness(record, regulated, current, engine_identity(budget=budget()), budget=current.budget.run_budget(),
                             motivation=snapshot(regulated, observed(65, ("measured", "human-asserted")), now=NOW))
    assert (report.status, report.motivation_changed) == ("stale", True)

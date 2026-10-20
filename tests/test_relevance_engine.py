"""Purpose: run whole relevance reviews on the native deontic engine and check the worked examples and engine-level properties.

Every test here runs lib_deontic and the MeTTa review policy; a missing runtime fails them with
`runtime-unavailable` rather than skipping, because a review that never ran proves nothing.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from goal_chainer.cli import main
from goal_chainer.domains.loader import load_domain
from goal_chainer.errors import InvalidInputError
from goal_chainer.relevance import parse_packet, review
from goal_chainer.relevance.errors import RelevanceError
from goal_chainer.relevance.packet import ReviewBudget
from goal_chainer.relevance.policy import prepare
from goal_chainer.runtime.budget import RunBudget

from relevance_support import fresh_process, packet, reading, reviewed, task_control
from request_support import budget as request_budget

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = task_control()
CHEMISTRY = ROOT / "examples" / "relevance" / "chemistry-contention.packet.json"


# am[related a-rel-compiler-1016@c69c38]
def chemistry():
    return parse_packet(json.loads(CHEMISTRY.read_text(encoding="utf-8")))


# am[related a-rel-compiler-1016@c69c38]
def stale_worker(*extra):
    """Paper section 14.1: the sole parent goal is achieved and no other path is active."""

    return packet(
        reading("review_open"),
        reading("stale_parent_goal", "detected", "deterministic", source="goal-graph"),
        reading("active_parent_path", "refuted", "deterministic", source="goal-graph"),
        reading("authority_unavailable", "refuted", "deterministic", source="policy"),
        *extra,
    )


# am[verifies a-rel-compiler-1016@c69c38] am[verifies a-rel-ranking-1016@334372]
def test_checkpointed_research_blocking_recovery_proposes_a_recoverable_pause() -> None:
    record = reviewed(DOMAIN, chemistry()).to_dict()

    proposal = record["proposal"]
    assert record["disposition"] == "propose" and record["applies_effects"] is False
    assert (proposal["action"], proposal["deontic"]) == ("pause_recoverably", "obligated")
    assert proposal["decided_at"] == "deterministic lifecycle"
    assert (proposal["action_authority_ceiling"], proposal["licensed_authority_ceiling"]) == ("preauthorized", "advisory")
    assert proposal["authorization"] == "unresolved"
    assert record["required_goals"] == ["project_outcome", "decision_relevant_speed", "epistemic_integrity"]
    assert 0 < record["engine"]["inferences"] < record["engine"]["budget"]["inferences"]
    eliminated = {e["action"]: e["reason"] for e in record["steps"][1]["eliminated"]}
    assert eliminated == {
        "continue_task": "an obligation is in force: pause_recoverably",
        "escalate": "an obligation is in force: pause_recoverably",
    }


# am[verifies a-rel-compiler-1016@c69c38]
def test_a_stale_worker_review_proposes_the_obliged_stop() -> None:
    record = reviewed(DOMAIN, stale_worker(reading("low_graph_quality", "refuted", "measured"))).to_dict()

    assert record["disposition"] == "propose"
    assert (record["proposal"]["action"], record["proposal"]["deontic"]) == ("stop_stale", "obligated")
    assert record["proposal"]["licensed_authority_ceiling"] == "advisory"


# am[verifies a-rel-compiler-1016@c69c38] am[verifies i-rel-unpermitted-admissible-1016@1d4f81]
def test_a_poorly_evidenced_slice_withdraws_the_stop_and_the_review_escalates() -> None:
    record = reviewed(DOMAIN, stale_worker(reading("low_graph_quality", "detected", "measured"))).to_dict()

    stop = next(c for c in record["candidates"] if c["action"] == "stop_stale")
    assert stop["modes"] == ["O"] and stop["eliminated"]["step"] == "deontic admissibility"
    assert record["disposition"] == "escalate" and record["proposal"] is None
    assert any("stop_stale is obliged but has no admissible discharge" in r for r in record["escalation"]["reasons"])


# am[verifies a-rel-compiler-1016@c69c38] am[verifies i-rel-dilemma-silent-1016@8b9179]
def test_an_unresolved_deontic_dilemma_escalates_instead_of_reading_as_permitted() -> None:
    domain = load_domain(ROOT / "tests" / "fixtures" / "relevance" / "dilemma.metta", budget=request_budget())

    record = reviewed(domain, packet(reading("open"), reading("urgent"), reading("risky"))).to_dict()
    single = reviewed(domain, packet(reading("open"), reading("urgent"))).to_dict()

    assert record["dilemmas"] == ["act"] and record["disposition"] == "escalate"
    assert record["escalation"]["contested"] == ["wait"]
    assert single["disposition"] == "propose" and single["proposal"]["action"] == "act"


# am[verifies a-rel-taskcontrol-1016@a7e7e4] am[verifies i-rel-deadsignal-1016@c0cf3b]
def test_a_material_cost_variance_makes_replanning_a_candidate_and_prices_continuing() -> None:
    record = reviewed(DOMAIN, packet(reading("review_open"), reading("cost_variance_material", "detected", "measured"))).to_dict()

    candidates = {c["action"]: c for c in record["candidates"]}
    assert "replan" in candidates
    assert {"dimension": "direct-cost", "band": "negative", "estimator": "measured"} in candidates["continue_task"]["effects"]


# am[verifies a-rel-compiler-1016@c69c38]
def test_the_inference_budget_stops_the_engine_during_the_review() -> None:
    full = reviewed(DOMAIN, chemistry()).to_dict()["engine"]["inferences"]
    tight = replace(chemistry(), budget=ReviewBudget(inferences=1_000, timeout_seconds=120.0))

    with pytest.raises(RelevanceError) as raised:
        reviewed(DOMAIN, tight)

    assert raised.value.code == "review-budget-exceeded"
    assert raised.value.details["budget"] == 1_000
    # Stopped long before the work an unbounded review does; a stopped stage can overshoot its
    # remainder (the engine checks the bound between steps), so the spend is not near 1,000.
    assert raised.value.details["used"] < full


# Two fresh processes, one preparing the service before its first review and one leaving it to
# that review: loading lib_deontic and compiling the policy (about 4.4 million inferences) is
# startup work charged to no review, so both first reviews spend alike; a second review in one
# process is cheaper by the cones it no longer computes. The startup runs under a budget of its
# own, which bounds only its time.
REVIEWS = """
import json, sys
from goal_chainer.domains.loader import packaged_domain
from goal_chainer.relevance import parse_packet, prepare_service, review
from goal_chainer.runtime.budget import RunBudget
packet = parse_packet(json.loads(open(sys.argv[1], encoding="utf-8").read()))
if sys.argv[2] == "prepared":
    prepare_service(RunBudget(inference_budget=None, timeout_seconds=600))
domain = packaged_domain("task-control", budget=packet.budget.run_budget())
print(json.dumps([review(domain, packet, budget=packet.budget.run_budget()).to_dict()["engine"]["inferences"] for _ in range(2)]))
"""


# am[verifies a-rel-request-deadline-1016@b72f03] am[verifies c-rel-one-deadline-1016@75de2a]
def test_startup_is_charged_to_no_review_and_a_warm_review_costs_less() -> None:
    lazy_first, lazy_second = fresh_process(REVIEWS, str(CHEMISTRY), "lazy")
    prepared_first, _ = fresh_process(REVIEWS, str(CHEMISTRY), "prepared")

    assert abs(lazy_first - prepared_first) <= 0.05 * prepared_first
    assert lazy_second < lazy_first


# Each example packet's whole record, without the measured inference count, as one digest per packet.
SEEDED = """
import hashlib, json, sys
from goal_chainer.domains.loader import packaged_domain
from goal_chainer.relevance import parse_packet, review
digests = []
for path in sys.argv[1:]:
    packet = parse_packet(json.loads(open(path, encoding="utf-8").read()))
    domain = packaged_domain("task-control", budget=packet.budget.run_budget())
    record = review(domain, packet, budget=packet.budget.run_budget()).to_dict()
    record["engine"].pop("inferences")
    digests.append(hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest())
print(json.dumps(digests))
"""


# A host checks a stored proposal by running its review again and comparing the records, which two
# processes made, so a record must not depend on the process's string-hash seed, which orders every
# set and frozenset the review holds.
# am[verifies a-rel-review-recompute-docs-1018@d72e34]
def test_a_review_record_is_the_same_under_every_hash_seed(monkeypatch) -> None:
    packets = [str(ROOT / "examples" / "relevance" / name)
               for name in ("chemistry-contention.packet.json", "chemistry-at-apply.packet.json")]
    records = []
    for seed in ("0", "1", "31337"):
        monkeypatch.setenv("PYTHONHASHSEED", seed)
        records.append(fresh_process(SEEDED, *packets))

    assert records[0] == records[1] == records[2]


# A fresh process whose first preparation is already past its deadline: lib_deontic's import is
# stopped there and reported as the review's own timeout, not an engine failure, and a later
# preparation within its deadline loads everything.
DEONTIC_EXPIRED = """
import json
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.relevance import prepare_service
from goal_chainer.relevance.errors import RelevanceError
try:
    prepare_service(RunBudget(inference_budget=None, timeout_seconds=1e-9))
    expired = "prepared"
except RelevanceError as error:
    expired = error.code
print(json.dumps({"expired": expired, "digest": prepare_service(RunBudget(inference_budget=None, timeout_seconds=600))}))
"""


# am[verifies a-rel-digest-from-loads-1016@b6583d] am[verifies c-rel-one-deadline-1016@75de2a]
def test_a_deontic_load_past_its_deadline_is_the_reviews_timeout_and_a_later_one_succeeds() -> None:
    outcome = fresh_process(DEONTIC_EXPIRED)

    assert outcome["expired"] == "review-timeout"
    assert outcome["digest"] == prepare(request_budget())


# am[verifies a-rt-run-budget-1016@e046b0] am[verifies c-rel-one-deadline-1016@75de2a]
def test_a_warm_process_still_stops_a_review_whose_deadline_has_passed() -> None:
    reviewed(DOMAIN, chemistry())
    expired = replace(chemistry(), budget=ReviewBudget(inferences=20_000_000, timeout_seconds=1e-9))

    with pytest.raises(RelevanceError) as raised:
        reviewed(DOMAIN, expired)

    assert raised.value.code == "review-timeout"


# am[verifies a-rel-compiler-1016@c69c38]
def test_the_wall_clock_bound_is_a_typed_failure() -> None:
    tight = replace(chemistry(), budget=ReviewBudget(inferences=20_000_000, timeout_seconds=0.001))

    with pytest.raises(RelevanceError) as raised:
        reviewed(DOMAIN, tight)

    assert raised.value.code == "review-timeout"


# A packet may declare any positive whole number of inferences and any positive finite timeout, and
# the review command runs under those bounds: the runtime hands SWI-Prolog at most the int64 limit
# its inference count keeps and waits toward the deadline in slices of threading.TIMEOUT_MAX, so
# 10**400 inferences and 1e10 seconds, each beyond one of those limits, review as a small budget
# does (c-rel-num-engine-int64-inferences-1018, c-rel-num-wait-timeout-max-1018).
# am[verifies a-rel-num-end-to-end-review-1018@c148b0] am[verifies a-rel-num-runtime-admits-what-it-runs-1018@5093e1]
@pytest.mark.parametrize(("inferences", "seconds"), [(10**400, 120.0), (20_000_000, 1e10), (10**400, 1e10)],
                         ids=["inferences-ten-to-the-400", "timeout-1e10", "both"])
def test_the_review_command_runs_under_any_budget_its_packet_may_declare(inferences: int, seconds: float, tmp_path, capsys) -> None:
    payload = json.loads(CHEMISTRY.read_text(encoding="utf-8"))
    payload["budget"] = {"inferences": inferences, "timeout_seconds": seconds}
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert main(["relevance", "review", "--packet", str(path), "--json"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["disposition"] == "propose" and record["proposal"]["action"] == "pause_recoverably"
    assert record["engine"]["budget"] == {"inferences": inferences, "timeout_seconds": seconds}
    assert 0 < record["engine"]["inferences"]


# am[related a-rel-compiler-1016@c69c38] am[rests-on c-rel-budget-is-bound-not-count-1016@790c1a]
def without_cost(record: dict) -> dict:
    """A review record without its measured inference count, which depends on what the engine
    compiled before the review (c-rel-inference-history-1016) and is never a decision input."""

    return {**record, "engine": {key: value for key, value in record["engine"].items() if key != "inferences"}}


# A review runs only under its caller's RunBudget, never under one with more left than the packet
# declares, so the packet's bounds stay an upper bound on what the review may cost.
# am[verifies a-integrate-domain-review-budget-1018@a84bf4]
def test_a_review_runs_only_under_a_callers_budget_no_looser_than_its_packet() -> None:
    review_packet = chemistry()
    declared = review_packet.budget
    looser = (
        None,
        RunBudget(inference_budget=None, timeout_seconds=declared.timeout_seconds),
        RunBudget(inference_budget=declared.inferences + 1, timeout_seconds=declared.timeout_seconds),
        RunBudget(inference_budget=declared.inferences, timeout_seconds=declared.timeout_seconds + 1),
    )

    for budget in looser:
        with pytest.raises(InvalidInputError):
            review(DOMAIN, review_packet, budget=budget)  # type: ignore[arg-type]
    tighter = RunBudget(inference_budget=declared.inferences, timeout_seconds=declared.timeout_seconds / 2)
    assert review(DOMAIN, review_packet, budget=tighter).to_dict()["disposition"] == reviewed(DOMAIN, review_packet).to_dict()["disposition"]


# One budget runs through a request: the review is charged after whatever an earlier stage spent,
# its record reports only the review's own spend, and the caller's deadline, not the packet's
# longer one, stops it (c-rel-review-builds-own-budget-1018).
# am[verifies a-integrate-domain-review-budget-1018@a84bf4] am[verifies c-rel-one-deadline-1016@75de2a]
def test_a_review_spends_its_callers_budget_and_stops_at_its_callers_deadline() -> None:
    review_packet = chemistry()
    budget = review_packet.budget.run_budget()
    budget.charge(1_000)  # an earlier stage of the same request

    record = review(DOMAIN, review_packet, budget=budget).to_dict()

    assert record["engine"]["inferences"] > 0
    assert budget.spent == 1_000 + record["engine"]["inferences"]
    hurried = RunBudget(inference_budget=review_packet.budget.inferences, timeout_seconds=1e-9)
    with pytest.raises(RelevanceError) as raised:
        review(DOMAIN, review_packet, budget=hurried)
    assert raised.value.code == "review-timeout"


# am[verifies a-rel-compiler-1016@c69c38] am[verifies a-rt-run-budget-1016@e046b0]
def test_a_review_stopped_by_its_budget_leaves_nothing_for_the_next_review() -> None:
    first = without_cost(reviewed(DOMAIN, chemistry()).to_dict())
    with pytest.raises(RelevanceError) as raised:
        reviewed(DOMAIN, replace(stale_worker(), budget=ReviewBudget(inferences=1_000, timeout_seconds=120.0)))
    other = reviewed(DOMAIN, stale_worker()).to_dict()
    again = without_cost(reviewed(DOMAIN, chemistry()).to_dict())

    assert raised.value.code == "review-budget-exceeded"
    assert first == again
    assert other["fingerprint"] != first["fingerprint"]


# Reviews from eight threads at once reach the records the same packets reach one review at a
# time: every policy call shares the engine on its own worker of the engine's pool, and nothing
# one review computes reaches another.
# am[verifies a-rel-mig-group-1018@28c337]
def test_reviews_from_many_threads_answer_as_sequential_reviews() -> None:
    packets = [chemistry(), stale_worker(), stale_worker(reading("low_graph_quality", "detected", "measured")),
               packet(reading("review_open"), reading("cost_variance_material", "detected", "measured"))] * 2
    sequential = [without_cost(reviewed(DOMAIN, each).to_dict()) for each in packets]

    with ThreadPoolExecutor(max_workers=8) as threads:
        concurrent = list(threads.map(lambda each: without_cost(reviewed(DOMAIN, each).to_dict()), packets))

    assert concurrent == sequential


# --- properties over the engine --------------------------------------------------------

SIGNALS = DOMAIN.signal_ids
states = st.sampled_from(["detected", "refuted", "unknown"])
estimators = st.sampled_from(["measured", "deterministic", "model-proposed"])


# am[related a-rel-compiler-1016@c69c38]
@st.composite
def readings_strategy(draw):
    chosen = draw(st.dictionaries(st.sampled_from(SIGNALS), st.tuples(states, estimators), max_size=len(SIGNALS)))
    base = {"review_open": ("detected", "deterministic")} if draw(st.booleans()) else {}
    return {**base, **chosen}


# am[related a-rel-compiler-1016@c69c38]
def as_packet(chosen: dict, moved: frozenset[str] = frozenset()) -> object:
    """Readings for `chosen`; a signal in `moved` comes from another source."""

    return packet(*(reading(name, state, None if state == "unknown" else estimator,
                            source="moved-probe" if name in moved else "probe")
                    for name, (state, estimator) in sorted(chosen.items())))


# am[related a-rel-compiler-1016@c69c38]
def decision(record: dict) -> dict:
    """What a host acts on: the disposition, the proposal, every step and every candidate."""

    return {key: record[key] for key in ("disposition", "proposal", "escalation", "blockers", "steps", "candidates",
                                          "obligations", "dilemmas", "required_goals")}


# am[verifies a-rel-taskcontrol-1016@a7e7e4] am[verifies i-rel-govcost-1016@e950e5]
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(chosen=readings_strategy())
def test_the_task_control_theory_never_derives_two_levels_for_one_effect(chosen: dict) -> None:
    record = reviewed(DOMAIN, as_packet(chosen)).to_dict()

    assert all(not candidate["conflicts"] for candidate in record["candidates"])


# am[verifies a-rel-compiler-1016@c69c38] am[verifies c-rel-cone-sound-1016@092cec]
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(chosen=readings_strategy(), moved=st.data())
def test_changing_readings_outside_the_readset_never_changes_the_decision(chosen: dict, moved) -> None:
    before = reviewed(DOMAIN, as_packet(chosen)).to_dict()
    outside = [name for name in SIGNALS if name not in before["readset"]["signals"]]
    if not outside:
        return
    changes = moved.draw(st.dictionaries(st.sampled_from(outside), st.tuples(states, estimators), min_size=1))
    after = reviewed(DOMAIN, as_packet({**chosen, **changes}, frozenset(changes))).to_dict()

    assert decision(after) == decision(before)

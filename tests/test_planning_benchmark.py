"""Purpose: verify paired planning measurements distinguish simulated goals, missing knowledge,
unreachable goals and budget stops, and fail loudly when their measured protocols fail."""

import pytest

from benchmarks import planning
from goal_chainer.errors import ProtocolError


# am[verifies a-integrate-plan-eval-verify-1019@791c8b]
@pytest.fixture(scope="module")
def prepared():
    result = planning.preparation()
    assert result["historical_blob"] == planning.HISTORICAL_BLOB
    assert all(row["goal_reached_in_model"] for row in result["warmup"])
    return result


# Paired observations change the same conditional graph, not its procedure spelling.
# am[verifies a-integrate-plan-eval-verify-1019@791c8b]
@pytest.mark.parametrize("arm", planning.ARMS)
@pytest.mark.parametrize("variant,reached", [("chain", True), ("missing", False), ("cycle", False),
                                             ("unknown", False), ("true", True), ("false", False)])
def test_goal_outcome_is_checked_by_the_model(prepared, arm, variant, reached):
    row = planning.run(planning.workload(2, variant), arm, 100_000_000, 120)
    assert row["status"] == "answered"
    assert row["goal_reached_in_model"] is reached
    assert row["inferences"] > 0
    assert row["elapsed_seconds"] > 0
    assert row["validation_seconds"] > 0
    if arm == "projection":
        assert row["result"]["@type"] == row["answer"]
    else:
        assert row["result"].startswith("(Composed ")
    if variant == "unknown" and arm == "projection":
        assert row["answer"] == "Inquiry"
    if variant == "false" and arm == "experimental-composer":
        assert row["answer"] == "Unsolved"


# Both plans work in the model, but declared-order composition pays for the longer way.
# am[verifies a-integrate-plan-eval-verify-1019@791c8b]
@pytest.mark.parametrize("prefix", ["w", "renamed"])
def test_a_shorter_alternative_changes_work_without_changing_the_goal(prepared, prefix):
    world = planning.workload(2, "alternative", prefix)
    old = planning.run(world, "experimental-composer", 100_000_000, 120)
    new = planning.run(world, "projection", 100_000_000, 120)
    assert old["goal_reached_in_model"] and new["goal_reached_in_model"]
    assert old["simulated_cost"]["executed"] > new["simulated_cost"]["executed"]
    assert old["workload"] == new["workload"] == planning.digest(world)


# Budget stops yield no invented outcome; an unexpected runtime failure aborts the experiment.
# am[verifies a-integrate-plan-eval-verify-1019@791c8b]
@pytest.mark.parametrize("arm", planning.ARMS)
def test_exhaustion_is_not_reported_as_a_dead_goal(prepared, arm):
    row = planning.run(planning.workload(2, "chain"), arm, 1, 120)
    assert row["status"] == "InferenceBudgetExceeded"
    assert "goal_reached_in_model" not in row
    assert "result" not in row


# am[verifies a-integrate-plan-eval-verify-1019@791c8b]
def test_unexpected_failure_stops_measurement(prepared, monkeypatch):
    # am[verifies a-integrate-plan-eval-verify-1019@791c8b]
    def fail(*args, **kwargs):
        raise ProtocolError("measurement failed")
    monkeypatch.setattr(planning, "plan", fail)
    with pytest.raises(ProtocolError, match="measurement failed"):
        planning.run(planning.workload(1, "chain"), "projection", 100_000_000, 120)


# am[verifies a-integrate-plan-eval-verify-1019@791c8b]
def test_historical_source_change_is_refused_before_use(prepared, monkeypatch):
    monkeypatch.setattr(planning, "HISTORICAL_BLOB", "0" * 40)
    with pytest.raises(ProtocolError, match="historical composer differs"):
        planning.preparation()

"""Purpose: test that caller-written plans and their claim lifecycle run through lib_directive, the MeTTa directive runtime GoalChainer carries, each change made by the agent its caller names."""

import hashlib
import stat

import pytest
from hypothesis import given, strategies as st

from directive_support import AGENT, CHAIN, CHAIN_PLAN, GATED_PLAN, READY_PLAN, task_states
from goal_chainer.directive import (
    DirectiveRuntime,
    DirectiveSession,
    create_plan,
    run_directive_request,
)
from goal_chainer.directive_models import (
    DirectiveInvalidInputError,
    DirectiveLifecycleResult,
    DirectivePlanError,
    DirectiveRun,
    DirectiveSnapshot,
)
from goal_chainer.deontic_engine import run_deontic_theory
from goal_chainer.runtime.budget import InferenceBudgetExceeded, RunBudget
from request_support import budget

LIFECYCLE = ("claim", "unclaim", "complete", "block", "unblock")


# Every directive operation runs under a caller's budget, so each test binds a fresh one.
# am[verifies a-ev-rb-directive-inprocess-1018@7bd2f6]
def _runtime() -> DirectiveRuntime:
    return DirectiveRuntime().bounded(budget())


# am[verifies a-ie-s6-directive-generic-1018@e69fb4]
def _session(tmp_path, name: str, plan: str) -> DirectiveSession:
    return DirectiveSession(create_plan(tmp_path / f"{name}.metta", plan), runtime=_runtime())


# A plan is created private and never replaces a file already there.
# am[verifies a-ie-s6-directive-generic-1018@e69fb4]
def test_a_plan_is_created_private(tmp_path):
    path = create_plan(tmp_path / "private.metta", READY_PLAN)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text() == READY_PLAN


# A review task gates the actions after it: blocking it blocks them upstream, and unblocking it
# returns them to the backlog.
# am[verifies a-ie-s6-directive-generic-1018@e69fb4]
def test_a_review_dependency_gates_and_propagates_a_block(tmp_path):
    session = _session(tmp_path, "gated", GATED_PLAN)

    initial = session.snapshot().value
    assert isinstance(initial, DirectiveSnapshot)
    assert "review_decision" in initial.board.ready
    assert "publish_redacted_summary" in initial.board.backlog
    assert "publish_raw_log" in initial.board.blocked

    blocked = session.block("review_decision", AGENT).value
    assert isinstance(blocked, DirectiveLifecycleResult)
    assert "publish_redacted_summary" in blocked.snapshot.status.upstream_blocked

    unblocked = session.unblock("review_decision", AGENT).value
    assert isinstance(unblocked, DirectiveLifecycleResult)
    assert "review_decision" in unblocked.snapshot.board.ready
    assert "publish_redacted_summary" in unblocked.snapshot.board.backlog


# Each lifecycle change is appended to the plan under the agent the caller named, one the plan
# declares and that is not the retired incident plan's responder.
# am[verifies a-ie-s6-directive-generic-1018@e69fb4] am[verifies a-integrate-directive-explicit-agent-1018@54e84d]
def test_claim_unclaim_and_complete_append_lifecycle_records_under_the_named_agent(tmp_path):
    session = _session(tmp_path, "lifecycle", READY_PLAN)

    claim = session.claim("publish_redacted_summary", AGENT).value
    unclaim = session.unclaim("publish_redacted_summary", AGENT).value
    reclaim = session.claim("publish_redacted_summary", AGENT).value
    complete = session.complete("publish_redacted_summary", AGENT).value

    assert all(isinstance(result, DirectiveLifecycleResult) for result in (claim, unclaim, reclaim, complete))
    assert [claim.version, unclaim.version, reclaim.version] == [1, 2, 3]
    assert complete.version is None
    assert "publish_redacted_summary" in complete.snapshot.board.done
    text = session.path.read_text()
    assert f"(claims agent:{AGENT}" in text
    assert "responder" not in text
    assert "(given completed-publish_redacted_summary)" in text


# A chain of tasks through the public request: blocking the root blocks the rest upstream,
# unblocking clears the cascade, each task becomes ready only once the one before it completes,
# and the plan completes when every task is done. These are what the retired demo operation ran
# on its own fixed plan; here the caller writes the plan and names the agent.
# am[verifies a-ie-s6-directive-generic-1018@e69fb4] am[verifies a-integrate-directive-explicit-agent-1018@54e84d]
def test_a_chain_cascades_blocks_gates_on_dependencies_and_completes(tmp_path):
    path = create_plan(tmp_path / "chain.metta", CHAIN_PLAN)

    def change(operation, task):
        result = run_directive_request(
            {"operation": operation, "plan": str(path), "task": task, "agent": AGENT}, budget=budget()
        )["result"]
        assert result["accepted"] is True, (operation, task, result)
        snapshot = DirectiveSession(path, runtime=_runtime()).snapshot().value
        return task_states(snapshot), snapshot

    first, second, third = CHAIN
    blocked, _ = change("block", first)
    assert blocked == {first: "blocked", second: "upstream-blocked", third: "upstream-blocked"}
    unblocked, _ = change("unblock", first)
    assert unblocked == {first: "ready", second: "backlog", third: "backlog"}
    change("claim", first)
    after_first, _ = change("complete", first)
    assert after_first[second] == "ready" and after_first[third] == "backlog"
    change("claim", second)
    after_second, _ = change("complete", second)
    assert after_second[third] == "ready"
    change("claim", third)
    final, snapshot = change("complete", third)
    assert final == {task: "done" for task in CHAIN}
    assert snapshot.summary.progress_pct == 100
    markdown = run_directive_request({"operation": "markdown", "plan": str(path)}, budget=budget())["result"]
    assert "## Plan and lifecycle log" in markdown and "```metta" in markdown


# am[verifies a-ie-s6-directive-generic-1018@e69fb4] am[verifies a-integrate-directive-explicit-agent-1018@54e84d]
def test_dispatch_reads_and_mutates_a_durable_plan(tmp_path):
    path = create_plan(tmp_path / "dispatch.metta", READY_PLAN)

    claimed = run_directive_request(
        {"operation": "claim", "plan": str(path), "task": "publish_redacted_summary", "agent": "omega"},
        budget=budget(),
    )
    board = run_directive_request({"operation": "board", "plan": str(path)}, budget=budget())

    assert claimed["result"]["accepted"] is True
    assert claimed["digest_before"] != claimed["digest_after"]
    assert board["result"]["in_progress"] == ["publish_redacted_summary"]


# A lifecycle change names its agent: a request leaving it out is refused before the plan is opened,
# so nothing is appended, and a session's lifecycle methods have no default to fall back on.
# am[verifies a-integrate-directive-explicit-agent-1018@54e84d]
@pytest.mark.parametrize("operation", LIFECYCLE)
def test_a_lifecycle_change_without_an_agent_is_refused(tmp_path, operation):
    path = create_plan(tmp_path / f"{operation}.metta", READY_PLAN)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    with pytest.raises(DirectiveInvalidInputError, match="agent") as refused:
        run_directive_request(
            {"operation": operation, "plan": str(path), "task": "publish_redacted_summary"},
            runtime=object(), budget=budget(),
        )

    assert refused.value.details == {"operation": operation, "missing": ["agent"]}
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    session = DirectiveSession(path, runtime=_runtime())
    with pytest.raises(TypeError):
        getattr(session, operation)("publish_redacted_summary")


# The retired demo ran a fixed plan; the request now offers only operations on the caller's plan.
# am[verifies a-ie-s6-directive-generic-1018@e69fb4]
def test_the_demo_operation_is_refused():
    with pytest.raises(DirectiveInvalidInputError, match="Unknown directive dispatch operation") as refused:
        run_directive_request({"operation": "demo"}, runtime=object(), budget=budget())

    assert "demo" not in refused.value.details["available"]


# am[verifies a-ev-rb-directive-inprocess-1018@7bd2f6]
def test_dispatch_rejects_unknown_fields_before_runtime_starts():
    with pytest.raises(DirectiveInvalidInputError, match="unknown fields"):
        run_directive_request(
            {"operation": "snapshot", "plan": "unused.metta", "unexpected": True},
            runtime=object(), budget=budget(),
        )


# am[related a-ie-s6-directive-generic-1018@e69fb4]
def test_plan_creation_refuses_to_replace_an_existing_file(tmp_path):
    path = tmp_path / "existing.metta"
    path.write_text("owner content\n")

    with pytest.raises(DirectivePlanError, match="already exists"):
        create_plan(path, READY_PLAN)

    assert path.read_text() == "owner content\n"


# am[related a-ie-s6-directive-generic-1018@e69fb4]
def test_plan_session_rejects_a_symbolic_link(tmp_path):
    target = create_plan(tmp_path / "target.metta", READY_PLAN)
    link = tmp_path / "linked.metta"
    link.symlink_to(target)

    with pytest.raises(DirectivePlanError, match="symbolic link"):
        DirectiveSession(link, runtime=_runtime())


# am[related a-ie-s6-directive-generic-1018@e69fb4]
def test_plan_session_detects_path_replacement_while_locked(tmp_path):
    path = create_plan(tmp_path / "replace.metta", READY_PLAN)
    moved = tmp_path / "moved.metta"

    class ReplacingRuntime:
        def snapshot(self, _runtime_path):
            path.rename(moved)
            path.write_text("(given task-replacement)\n")
            return DirectiveRun("snapshot", object())

    session = DirectiveSession(path, runtime=ReplacingRuntime())

    with pytest.raises(DirectivePlanError, match="path changed"):
        session.snapshot()


# am[related a-ie-s6-directive-generic-1018@e69fb4]
def test_plan_session_detects_replacement_between_operations(tmp_path):
    path = create_plan(tmp_path / "between.metta", READY_PLAN)
    moved = tmp_path / "between-moved.metta"
    session = DirectiveSession(path, runtime=_runtime())
    path.rename(moved)
    path.write_text("(given task-replacement)\n")

    with pytest.raises(DirectivePlanError, match="session was created"):
        session.snapshot()


# am[verifies a-ev-rb-directive-inprocess-1018@7bd2f6]
@given(st.text().filter(lambda value: value not in {
    "snapshot",
    "status",
    "next",
    "board",
    "summary",
    "info",
    "assignments",
    "markdown",
    "validate",
    "analyze",
    "trace",
    "task-state",
    *LIFECYCLE,
}))
def test_dispatch_rejects_unknown_operations(operation):
    with pytest.raises(DirectiveInvalidInputError):
        run_directive_request({"operation": operation}, budget=budget())


# am[verifies a-ev-rb-directive-inprocess-1018@7bd2f6]
@given(
    st.text(min_size=1).filter(
        lambda value: any(
            character.isspace() or character in '();"\\'
            for character in value
        )
    )
)
def test_dispatch_rejects_unsafe_task_symbols(tmp_path_factory, operation):
    path = tmp_path_factory.getbasetemp() / "symbols.metta"
    path.write_text("(given task-safe)\n")

    with pytest.raises(DirectiveInvalidInputError):
        run_directive_request(
            {
                "operation": "task-state",
                "plan": str(path),
                "task": operation,
            },
            runtime=object(), budget=budget(),
        )


# A directive runtime runs only under a caller's budget: an unbound one refuses before any engine
# work, a bound one charges its inferences to that budget, and an allowance too small for the
# operation stops it with the typed budget error.
# am[verifies a-ev-rb-directive-inprocess-1018@7bd2f6] am[verifies a-ev-rb-pipeline-budget-1018@988a39]
def test_a_directive_runtime_runs_only_under_its_callers_budget(tmp_path):
    path = create_plan(tmp_path / "budget.metta", READY_PLAN)
    with pytest.raises(DirectiveInvalidInputError, match="RunBudget"):
        DirectiveRuntime().snapshot(path)

    request_budget = budget()
    snapshot = DirectiveRuntime().bounded(request_budget).snapshot(path).value

    assert isinstance(snapshot, DirectiveSnapshot) and "publish_redacted_summary" in snapshot.board.ready
    assert request_budget.spent > 0
    with pytest.raises(InferenceBudgetExceeded):
        DirectiveRuntime().bounded(RunBudget(inference_budget=1, timeout_seconds=600)).snapshot(path)


# Each operation runs inside speculation, which rolls back every space write and dynamic fact, so the
# same read twice answers alike, a claim persists only through the plan file it appends to, a claim
# repeated is already-claimed with no second append, and a deontic review answers the same after the
# directive's work as before it.
# am[verifies a-ev-rb-directive-inprocess-1018@7bd2f6]
def test_directive_operations_keep_nothing_but_the_plan_file(tmp_path):
    theory = "(given a)\n(normally r1 a (may hold_external_update))\n"
    before = [conclusion.render() for conclusion in run_deontic_theory(theory, budget=budget()).conclusions]
    path = create_plan(tmp_path / "plan.metta", CHAIN_PLAN)
    session = DirectiveSession(path, runtime=_runtime())

    first, second = session.snapshot(), session.snapshot()
    claimed = session.claim(CHAIN[0], AGENT)
    size = path.stat().st_size
    again = session.claim(CHAIN[0], AGENT)

    assert first.value == second.value and first.value.board.ready == (CHAIN[0],)
    assert claimed.value.accepted and claimed.value.outcome == "claimed"
    assert again.value.accepted and again.value.outcome == "already-claimed"
    assert path.stat().st_size == size
    assert session.snapshot().value.board.in_progress == (CHAIN[0],)
    assert [conclusion.render() for conclusion in run_deontic_theory(theory, budget=budget()).conclusions] == before

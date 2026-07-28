"""GoalChainer plans execute through OmegaClaw's MeTTa directive runtime."""

import stat

import pytest
from hypothesis import given, strategies as st

from goal_chainer.directive import (
    DirectiveSession,
    build_plan,
    classify_task_states,
    create_plan,
    execute_with_directive,
    register_directive,
    run_directive_demo,
    run_directive_request,
)
from goal_chainer.directive_models import (
    DirectiveInvalidInputError,
    DirectiveLifecycleResult,
    DirectivePlanError,
    DirectiveRun,
    DirectiveSnapshot,
)


INCIDENT = {
    "publish_raw_log": "forbidden",
    "publish_redacted_summary": "obligated",
    "hold_external_update": "permitted",
}
TASK_STATES = {
    "publish_raw_log": "blocked",
    "publish_redacted_summary": "ready",
    "hold_external_update": "backlog",
}


def test_metta_relation_maps_deontic_to_task_state():
    states, _ = classify_task_states(INCIDENT)

    assert states["publish_raw_log"] == "blocked"
    assert states["publish_redacted_summary"] == "ready"
    assert states["hold_external_update"] == "backlog"


def test_recommended_action_becomes_a_claimed_task():
    report = register_directive(INCIDENT)

    assert report["status"]["ready"] == ["publish_redacted_summary"]
    assert report["status"]["blocked"] == ["publish_raw_log"]
    assert any(nxt["task"] == "publish_redacted_summary" for nxt in report["next_actions"])
    assert report["claim"]["task"] == "publish_redacted_summary"
    assert report["claim"]["version"] == 1


def test_durable_plan_is_private_and_keeps_the_claim_audit(tmp_path):
    path = tmp_path / "incident.metta"

    report = register_directive(INCIDENT, plan_path=path)

    assert report["plan_path"] == str(path)
    assert path.exists()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "(claims agent:responder" in path.read_text()
    initial = report["audit"]["initial"]
    lifecycle = report["audit"]["lifecycle"]
    assert initial["digest_before"] == lifecycle["digest_before"]
    assert lifecycle["digest_before"] != lifecycle["digest_after"]


def test_review_dependency_gates_and_propagates_a_block(tmp_path):
    path = create_plan(
        tmp_path / "gated.metta",
        build_plan(TASK_STATES, review_complete=False),
    )
    session = DirectiveSession(path)

    initial = session.snapshot().value
    assert isinstance(initial, DirectiveSnapshot)
    assert "review_decision" in initial.board.ready
    assert "publish_redacted_summary" in initial.board.backlog

    blocked = session.block("review_decision").value
    assert isinstance(blocked, DirectiveLifecycleResult)
    assert "publish_redacted_summary" in blocked.snapshot.status.upstream_blocked

    unblocked = session.unblock("review_decision").value
    assert isinstance(unblocked, DirectiveLifecycleResult)
    assert "review_decision" in unblocked.snapshot.board.ready
    assert "publish_redacted_summary" in unblocked.snapshot.board.backlog


def test_claim_unclaim_and_complete_append_lifecycle_records(tmp_path):
    path = create_plan(
        tmp_path / "lifecycle.metta",
        build_plan(TASK_STATES, review_complete=True),
    )
    session = DirectiveSession(path)

    claim = session.claim("publish_redacted_summary").value
    unclaim = session.unclaim("publish_redacted_summary").value
    reclaim = session.claim("publish_redacted_summary").value
    complete = session.complete("publish_redacted_summary").value

    assert isinstance(claim, DirectiveLifecycleResult)
    assert isinstance(unclaim, DirectiveLifecycleResult)
    assert isinstance(reclaim, DirectiveLifecycleResult)
    assert isinstance(complete, DirectiveLifecycleResult)
    assert [claim.version, unclaim.version, reclaim.version] == [1, 2, 3]
    assert complete.version is None
    assert "publish_redacted_summary" in complete.snapshot.board.done
    assert "(given completed-publish_redacted_summary)" in path.read_text()


def test_live_demo_proves_cascade_gating_and_completion(tmp_path):
    path = tmp_path / "demo.metta"

    report = run_directive_demo(plan_path=path)

    assert path.exists()
    assert all(report["verified"].values())
    assert report["stages"][1]["task_states"] == {
        "collect_evidence": "blocked",
        "publish_update": "upstream-blocked",
        "summarize_findings": "upstream-blocked",
    }
    assert report["stages"][-1]["summary"]["progress_pct"] == 100
    assert "## Plan and lifecycle log" in report["markdown"]
    assert "```metta" in report["markdown"]


def test_dispatch_reads_and_mutates_a_durable_plan(tmp_path):
    path = create_plan(
        tmp_path / "dispatch.metta",
        build_plan(TASK_STATES, review_complete=True),
    )

    claimed = run_directive_request(
        {
            "operation": "claim",
            "plan": str(path),
            "task": "publish_redacted_summary",
            "agent": "omega",
        }
    )
    board = run_directive_request(
        {"operation": "board", "plan": str(path)}
    )

    assert claimed["result"]["accepted"] is True
    assert claimed["digest_before"] != claimed["digest_after"]
    assert board["result"]["in_progress"] == ["publish_redacted_summary"]


def test_dispatch_rejects_unknown_fields_before_runtime_starts():
    with pytest.raises(DirectiveInvalidInputError, match="unknown fields"):
        run_directive_request(
            {
                "operation": "demo",
                "unexpected": True,
            }
        )


def test_failed_execution_blocks_the_claimed_task(tmp_path):
    path = tmp_path / "failed-execution.metta"

    def fail(_action):
        raise RuntimeError("executor failed")

    with pytest.raises(RuntimeError, match="executor failed"):
        execute_with_directive(
            "publish_redacted_summary",
            INCIDENT,
            fail,
            plan_path=path,
        )

    snapshot = DirectiveSession(path).snapshot().value
    assert isinstance(snapshot, DirectiveSnapshot)
    assert "publish_redacted_summary" in snapshot.board.blocked


def test_plan_creation_refuses_to_replace_an_existing_file(tmp_path):
    path = tmp_path / "existing.metta"
    path.write_text("owner content\n")

    with pytest.raises(DirectivePlanError, match="already exists"):
        create_plan(path, build_plan(TASK_STATES))

    assert path.read_text() == "owner content\n"


def test_plan_session_rejects_a_symbolic_link(tmp_path):
    target = create_plan(
        tmp_path / "target.metta",
        build_plan(TASK_STATES),
    )
    link = tmp_path / "linked.metta"
    link.symlink_to(target)

    with pytest.raises(DirectivePlanError, match="symbolic link"):
        DirectiveSession(link)


def test_plan_session_detects_path_replacement_while_locked(tmp_path):
    path = create_plan(
        tmp_path / "replace.metta",
        build_plan(TASK_STATES),
    )
    moved = tmp_path / "moved.metta"

    class ReplacingRuntime:
        def snapshot(self, _runtime_path):
            path.rename(moved)
            path.write_text("(given task-replacement)\n")
            return DirectiveRun("snapshot", object())

    session = DirectiveSession(path, runtime=ReplacingRuntime())

    with pytest.raises(DirectivePlanError, match="path changed"):
        session.snapshot()


def test_plan_session_detects_replacement_between_operations(tmp_path):
    path = create_plan(
        tmp_path / "between.metta",
        build_plan(TASK_STATES),
    )
    moved = tmp_path / "between-moved.metta"
    session = DirectiveSession(path)
    path.rename(moved)
    path.write_text("(given task-replacement)\n")

    with pytest.raises(DirectivePlanError, match="session was created"):
        session.snapshot()


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
    "claim",
    "unclaim",
    "complete",
    "block",
    "unblock",
    "demo",
}))
def test_dispatch_rejects_unknown_operations(operation):
    with pytest.raises(DirectiveInvalidInputError):
        run_directive_request({"operation": operation})


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
            runtime=object(),
        )

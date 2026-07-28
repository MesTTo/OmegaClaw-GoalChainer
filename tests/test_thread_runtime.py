from __future__ import annotations

import sys

import pytest
from thread_spec_fixture import VALID_THREAD_SPEC

from goal_chainer.snars_runtime import SnarsRuntime
from goal_chainer.thread_models import (
    ThreadOutcomeDecision,
    ThreadPettaAttempt,
    ThreadReleaseDecision,
    ThreadRouteDecision,
    ThreadSpecification,
    ThreadSpecificationError,
)
from goal_chainer.thread_runtime import ThreadRuntime
from goal_chainer.thread_spec import parse_thread_markdown


@pytest.fixture(scope="module")
def runtime() -> ThreadRuntime:
    return ThreadRuntime(SnarsRuntime(require_text_ingestion=False))


@pytest.fixture(scope="module")
def specification(runtime: ThreadRuntime) -> ThreadSpecification:
    parsed = parse_thread_markdown(VALID_THREAD_SPEC, runtime=runtime.runtime)
    result = runtime.compile(parsed).value
    assert isinstance(result, ThreadSpecification)
    return result


def test_live_mettascript_compiles_metta_markdown_facts(
    specification: ThreadSpecification,
) -> None:
    assert specification.thread_id == "incident-42"
    assert [task.task_id for task in specification.tasks] == [
        "collect-evidence",
        "redact-summary",
    ]
    assert specification.tasks[1].dependencies == ("collect-evidence",)
    assert specification.workflow.workflow_id == "research-agent"
    assert [step.order for step in specification.workflow.steps] == [10, 20, 30]
    assert specification.workflow.steps[0].instruction.startswith(
        "Inspect existing evidence"
    )
    assert specification.mcp_access.profile == "oh-my-goals"
    assert specification.mcp_access.tools == (
        "remember",
        "query",
        "solve",
        "revise",
        "forget",
        "explain",
        "find_papers",
        "ingest_paper",
        "add_claim",
        "citations",
        "review",
        "check_retractions",
    )


def test_live_mettascript_supplies_a_default_guided_workflow(
    runtime: ThreadRuntime,
) -> None:
    source = "\n".join(
        line for line in VALID_THREAD_SPEC.splitlines()
        if "thread-workflow" not in line
    )
    parsed = parse_thread_markdown(source, runtime=runtime.runtime)
    result = runtime.compile(parsed).value

    assert isinstance(result, ThreadSpecification)
    assert result.workflow.workflow_id == "goalchainer-default"
    assert len(result.workflow.steps) == 3


def test_live_mettascript_supplies_default_oh_my_goals_access(
    runtime: ThreadRuntime,
) -> None:
    source = "\n".join(
        line
        for line in VALID_THREAD_SPEC.splitlines()
        if "thread-mcp-profile" not in line
    )
    parsed = parse_thread_markdown(source, runtime=runtime.runtime)
    result = runtime.compile(parsed).value

    assert isinstance(result, ThreadSpecification)
    assert result.mcp_access.profile == "oh-my-goals"
    assert "remember" in result.mcp_access.tools
    assert "find_papers" in result.mcp_access.tools


@pytest.mark.parametrize(
    ("needle", "replacement", "expected_error"),
    [
        (
            '(thread-title incident-42 "Incident response")\n',
            "",
            "missing-title",
        ),
        (
            "```\n",
            (
                "(thread-task incident-42 redact-summary specialist "
                "summary-redacted high)\n```\n"
            ),
            "duplicate-task",
        ),
        (
            "(thread-depends incident-42 redact-summary collect-evidence)",
            "(thread-depends incident-42 redact-summary absent-task)",
            "missing-dependency",
        ),
        (
            "(thread-role incident-42 evaluator result-evaluator)",
            "(thread-role incident-42 evaluator local-worker)",
            "duplicate-role-identity",
        ),
        (
            "(thread-merge-policy incident-42 none none)",
            (
                "(thread-not-before incident-42 absent-task 1785283200)\n"
                "(thread-merge-policy incident-42 none none)"
            ),
            "missing-scheduled-task",
        ),
        (
            "(thread-merge-policy incident-42 none none)",
            (
                "(thread-not-before incident-42 collect-evidence 10)\n"
                "(thread-not-before incident-42 collect-evidence 20)\n"
                "(thread-merge-policy incident-42 none none)"
            ),
            "duplicate-task-schedule",
        ),
        (
            "(thread-merge-policy incident-42 none none)",
            (
                "(thread-not-before incident-42 collect-evidence -1)\n"
                "(thread-merge-policy incident-42 none none)"
            ),
            "invalid-task-schedule",
        ),
        (
            "(thread-workflow incident-42 research-agent)\n",
            "",
            "missing-workflow",
        ),
        (
            "(thread-workflow incident-42 research-agent)",
            (
                "(thread-workflow incident-42 research-agent)\n"
                "(thread-workflow incident-42 second-workflow)"
            ),
            "duplicate-workflow",
        ),
        (
            "research-agent 20",
            "different-workflow 20",
            "invalid-workflow-reference",
        ),
        (
            "research-agent 20",
            "research-agent 10",
            "duplicate-workflow-step-order",
        ),
        (
            'research-agent 20 "Implement only',
            'research-agent 0 "Implement only',
            "invalid-workflow-step",
        ),
        (
            'research-agent 20 "Implement only the released task and verify its acceptance condition."',
            "research-agent 20 unsafe-symbol",
            "invalid-workflow-step",
        ),
        (
            "(thread-mcp-profile incident-42 oh-my-goals)",
            "(thread-mcp-profile incident-42 arbitrary)",
            "invalid-mcp-profile",
        ),
        (
            "(thread-mcp-profile incident-42 oh-my-goals)",
            (
                "(thread-mcp-profile incident-42 oh-my-goals)\n"
                "(thread-mcp-profile incident-42 oh-my-goals)"
            ),
            "duplicate-mcp-profile",
        ),
    ],
)
def test_live_mettascript_rejects_invalid_semantics(
    runtime: ThreadRuntime,
    needle: str,
    replacement: str,
    expected_error: str,
) -> None:
    source = VALID_THREAD_SPEC.replace(needle, replacement, 1)
    parsed = parse_thread_markdown(source, runtime=runtime.runtime)

    with pytest.raises(ThreadSpecificationError, match=expected_error):
        runtime.compile(parsed)


def test_live_mettascript_routes_local_work_without_escalation(
    runtime: ThreadRuntime,
    specification: ThreadSpecification,
) -> None:
    result = runtime.route(
        specification,
        capability="local",
        stakes="normal",
        spent_tokens=specification.budget.ceiling_tokens,
        local_iterations=0,
        hard=True,
    ).value

    assert result == ThreadRouteDecision(
        target="worker",
        allowed=True,
        reason="local task",
        requires_adjudication=False,
    )


def test_live_mettascript_releases_tasks_only_after_not_before(
    runtime: ThreadRuntime,
) -> None:
    future = runtime.release(
        not_before_epoch=200,
        now_epoch=199,
        dependency_ready=True,
    ).value
    due = runtime.release(
        not_before_epoch=200,
        now_epoch=200,
        dependency_ready=True,
    ).value
    blocked = runtime.release(
        not_before_epoch=None,
        now_epoch=200,
        dependency_ready=False,
    ).value

    assert future == ThreadReleaseDecision(
        allowed=False,
        reason="not-before constraint has not elapsed",
    )
    assert due == ThreadReleaseDecision(
        allowed=True,
        reason="not-before constraint elapsed",
    )
    assert blocked == ThreadReleaseDecision(
        allowed=False,
        reason="dependencies not ready",
    )


def test_live_mettascript_projects_scheduled_ui_state(
    runtime: ThreadRuntime,
) -> None:
    result = runtime.ui_projection(
        rows_source=(
            "((ui-task collect local accept normal () ready False "
            "worker 0 none 200) "
            "(ui-task publish local published normal (collect) done False "
            "worker 1 session-7 none))"
        ),
        now_epoch=199,
    ).value

    assert result["summary"] == {
        "total": 2,
        "scheduled": 1,
        "backlog": 0,
        "ready": 0,
        "inProgress": 0,
        "blocked": 0,
        "done": 1,
        "progressPct": 50,
    }
    assert result["tasks"][0]["state"] == "scheduled"
    assert result["tasks"][0]["releaseReason"] == (
        "not-before constraint has not elapsed"
    )


@pytest.mark.parametrize(
    (
        "spent",
        "iterations",
        "hard",
        "expected_target",
        "expected_adjudication",
    ),
    [
        (0, 0, True, "denied", False),
        (0, 1, True, "specialist", True),
        (60000, 1, False, "denied", False),
        (60000, 1, True, "specialist", True),
        (120000, 1, True, "denied", False),
    ],
)
def test_live_mettascript_threadkeeper_budget_boundaries(
    runtime: ThreadRuntime,
    specification: ThreadSpecification,
    spent: int,
    iterations: int,
    hard: bool,
    expected_target: str,
    expected_adjudication: bool,
) -> None:
    result = runtime.route(
        specification,
        capability="specialist",
        stakes="high",
        spent_tokens=spent,
        local_iterations=iterations,
        hard=hard,
    ).value
    assert isinstance(result, ThreadRouteDecision)
    assert result.target == expected_target
    assert result.requires_adjudication is expected_adjudication


@pytest.mark.parametrize(
    (
        "exit_reason",
        "exit_code",
        "evaluator",
        "attempt",
        "adjudication_required",
        "adjudicator",
        "expected",
    ),
    [
        ("process-exited", 0, "accept", 1, False, "not-required", "complete"),
        ("process-exited", 0, "accept", 1, True, "accept", "complete"),
        ("process-exited", 0, "accept", 1, True, "reject", "retry"),
        ("process-exited", 2, "accept", 1, False, "not-required", "retry"),
        ("idle-timeout", 143, "reject", 2, False, "not-required", "retry"),
        (
            "wall-timeout",
            143,
            "reject",
            3,
            False,
            "not-required",
            "permanent-failure",
        ),
    ],
)
def test_live_petta_decides_attempt_outcome(
    runtime: ThreadRuntime,
    specification: ThreadSpecification,
    exit_reason: str,
    exit_code: int,
    evaluator: str,
    attempt: int,
    adjudication_required: bool,
    adjudicator: str,
    expected: str,
) -> None:
    result = runtime.outcome(
        specification,
        exit_reason=exit_reason,
        exit_code=exit_code,
        evaluator_verdict=evaluator,
        attempt=attempt,
        adjudication_required=adjudication_required,
        adjudicator_verdict=adjudicator,
    ).value

    assert isinstance(result, ThreadOutcomeDecision)
    assert result.outcome == expected


def test_live_petta_attempt_uses_host_atoms_for_effects(
    tmp_path,
    runtime: ThreadRuntime,
    specification: ThreadSpecification,
) -> None:
    evaluator = tmp_path / "evaluator.py"
    evaluator.write_text(
        "import json,sys\n"
        "data=json.load(open(sys.argv[1]))\n"
        "ok='evidence-collected' in data['worker']['output']\n"
        "print(json.dumps({'verdict':'accept' if ok else 'reject',"
        "'reason':'checked by external evaluator'}))\n"
    )

    result = runtime.attempt(
        specification,
        specification.tasks[0],
        worker_command=[
            sys.executable,
            "-c",
            "print('evidence-collected')",
        ],
        evaluator_command=[sys.executable, str(evaluator)],
        adjudicator_command=None,
        cwd=tmp_path,
        environment=None,
        use_pty=False,
        attempt=1,
        adjudication_required=False,
    ).value

    assert isinstance(result, ThreadPettaAttempt)
    assert result.observation.exit_code == 0
    assert result.evaluation.verdict == "accept"
    assert result.adjudication.verdict == "not-required"
    assert result.outcome.outcome == "complete"


def test_live_petta_attempt_preserves_host_text_metacharacters(
    tmp_path,
    runtime: ThreadRuntime,
    specification: ThreadSpecification,
) -> None:
    evaluator = tmp_path / "evaluator.py"
    evaluator.write_text(
        "import json\n"
        "print(json.dumps({'verdict':'accept',"
        "'reason':'accepted; detail\\nnext line'}))\n"
    )

    result = runtime.attempt(
        specification,
        specification.tasks[0],
        worker_command=[
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('alpha;beta\\nnext line\\n')",
        ],
        evaluator_command=[sys.executable, str(evaluator)],
        adjudicator_command=None,
        cwd=tmp_path,
        environment={"THREAD_VALUE": "quoted; value\nnext"},
        use_pty=False,
        attempt=1,
        adjudication_required=False,
    ).value

    assert isinstance(result, ThreadPettaAttempt)
    assert result.observation.output == "alpha;beta\nnext line\n"
    assert result.evaluation.reason == "accepted; detail\nnext line"
    assert result.outcome.outcome == "complete"


def test_live_petta_attempt_preserves_empty_failed_output(
    tmp_path,
    runtime: ThreadRuntime,
    specification: ThreadSpecification,
) -> None:
    result = runtime.attempt(
        specification,
        specification.tasks[0],
        worker_command=[sys.executable, "-c", "raise SystemExit(7)"],
        evaluator_command=[sys.executable, "-c", "raise AssertionError"],
        adjudicator_command=None,
        cwd=tmp_path,
        environment=None,
        use_pty=False,
        attempt=1,
        adjudication_required=False,
    ).value

    assert isinstance(result, ThreadPettaAttempt)
    assert result.observation.output == ""
    assert result.evaluation.verdict == "reject"
    assert result.evaluation.reason == "worker did not exit successfully"
    assert result.outcome.outcome == "retry"

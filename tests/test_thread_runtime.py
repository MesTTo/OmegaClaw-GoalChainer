from __future__ import annotations

import shutil
import sys
from typing import cast

import pytest
from thread_spec_fixture import VALID_THREAD_SPEC, VALID_THREAD_SPEC_V2

from goal_chainer import thread_runtime as thread_runtime_module
from goal_chainer.mettascript_runtime import (
    MeTTaScriptRuntime,
    SOURCE_RUNNER_PATH,
)
from goal_chainer.snars_runtime import SnarsRuntime
from goal_chainer.thread_models import (
    ThreadAgentBinding,
    ThreadDispatch,
    ThreadOutcomeDecision,
    ThreadPettaAttempt,
    ThreadReleaseDecision,
    ThreadRouteDecision,
    ThreadSessionAttempt,
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


def test_live_mettascript_compiles_v2_project_agent_contract(
    runtime: ThreadRuntime,
) -> None:
    parsed = parse_thread_markdown(
        VALID_THREAD_SPEC_V2,
        runtime=runtime.runtime,
    )
    result = runtime.compile(parsed).value

    assert isinstance(result, ThreadSpecification)
    assert result.spec_version == "thread-spec-v2"
    assert result.project_id == "project-incident-42"
    assert {agent.agent_key for agent in result.agents} == {
        "local-control",
        "local-worker",
        "thread-supervisor",
        "result-evaluator",
        "security-specialist",
        "security-owner",
    }
    assert result.task_role_policies[0].role == "worker"
    assert result.task_role_policies[1].role == "specialist"
    assert len(result.atomspace_links) == 7


def test_live_mettascript_rejects_non_symbol_v2_agent_key(
    runtime: ThreadRuntime,
) -> None:
    source = VALID_THREAD_SPEC_V2.replace(
        "(thread-agent incident-42 local-worker)",
        '(thread-agent incident-42 "local-worker")',
    )
    parsed = parse_thread_markdown(source, runtime=runtime.runtime)

    with pytest.raises(ThreadSpecificationError, match="invalid-agent"):
        _ = runtime.compile(parsed)


def test_installed_adapter_rejects_non_symbol_v2_agent_key(
    tmp_path,
    monkeypatch,
) -> None:
    installed_root = tmp_path / "installed"
    installed_adapter = installed_root / "goalchainer_threadkeeper.metta"
    installed_runner = installed_root / "runner.mjs"
    installed_root.mkdir()
    shutil.copyfile(thread_runtime_module.SOURCE_ADAPTER_PATH, installed_adapter)
    shutil.copyfile(SOURCE_RUNNER_PATH, installed_runner)
    monkeypatch.setattr(
        thread_runtime_module,
        "SOURCE_ADAPTER_PATH",
        tmp_path / "source-adapter-is-absent.metta",
    )
    monkeypatch.setattr(
        thread_runtime_module,
        "INSTALLED_ADAPTER_PATH",
        installed_adapter,
    )
    installed = ThreadRuntime(
        mettascript_runtime=MeTTaScriptRuntime(
            runner_path=installed_runner,
            module_root=thread_runtime_module.REPO_ROOT,
        )
    )
    source = VALID_THREAD_SPEC_V2.replace(
        "(thread-agent incident-42 local-worker)",
        '(thread-agent incident-42 "local-worker")',
    )
    parsed = parse_thread_markdown(source, runtime=installed.runtime)

    with pytest.raises(ThreadSpecificationError, match="invalid-agent"):
        _ = installed.compile(parsed)


def test_live_mettascript_owns_v2_dispatch_and_session_identity(
    runtime: ThreadRuntime,
) -> None:
    parsed = parse_thread_markdown(
        VALID_THREAD_SPEC_V2,
        runtime=runtime.runtime,
    )
    specification = runtime.compile(parsed).value
    assert isinstance(specification, ThreadSpecification)

    dispatch = runtime.dispatch(
        specification,
        task_id="redact-summary",
        route="specialist",
        attempt=1,
        bindings=(
            ThreadAgentBinding(
                agent_key="security-specialist",
                agent_id="11111111-1111-4111-8111-111111111111",
            ),
        ),
    ).value

    assert isinstance(dispatch, ThreadDispatch)
    assert dispatch.role == "specialist"
    assert dispatch.agent_key == "security-specialist"
    assert dispatch.agent_id == "11111111-1111-4111-8111-111111111111"
    assert {link.link_key for link in dispatch.atomspace_links} == {
        "project-shared",
        "specialist-private",
    }

    session = runtime.bind_session(
        dispatch,
        agent_id="11111111-1111-4111-8111-111111111111",
        agent_attempt=4,
        session_id="session-7",
        status="running",
        activity="active",
        is_terminated=False,
        updated_at="2026-07-29T00:00:00Z",
    ).value

    assert isinstance(session, ThreadSessionAttempt)
    assert session.project_id == "project-incident-42"
    assert session.agent_key == "security-specialist"
    assert session.session_id == "session-7"


def test_live_mettascript_projects_v2_agents_and_attempts(
    runtime: ThreadRuntime,
) -> None:
    result = runtime.ui_projection_v2(
        project_id="project-incident-42",
        agents_source=(
            '((agent local-worker worker "22222222-2222-4222-8222-222222222222")'
            ' (agent security-specialist specialist "11111111-1111-4111-8111-111111111111"))'
        ),
        rows_source=(
            "((ui-task-v2"
            " (task collect local accept normal ())"
            " (execution ready False 200)"
            ' (assignment worker local-worker "22222222-2222-4222-8222-222222222222")'
            " (attempts 0 none ())"
            " (atomspace-links"
            "  ((atomspace-link project-shared shared project)"
            "   (atomspace-link worker-private private local-worker))))"
            " (ui-task-v2"
            " (task publish specialist published high (collect))"
            " (execution done False none)"
            ' (assignment specialist security-specialist "11111111-1111-4111-8111-111111111111")'
            " (attempts 1 session-7"
            '  ((session-attempt 1 "11111111-1111-4111-8111-111111111111" 4 session-7'
            "    complete idle True)))"
            " (atomspace-links"
            "  ((atomspace-link project-shared shared project)"
            "   (atomspace-link specialist-private private security-specialist)))))"
        ),
        now_epoch=199,
    ).value

    assert isinstance(result, dict)
    projection = cast(dict[str, object], result)
    assert projection["projectId"] == "project-incident-42"
    summary = cast(dict[str, int], projection["summary"])
    tasks = cast(tuple[dict[str, object], ...], projection["tasks"])
    assert summary["scheduled"] == 1
    assert tasks[1]["agentKey"] == "security-specialist"
    session_attempts = cast(
        tuple[dict[str, object], ...],
        tasks[1]["sessionAttempts"],
    )
    assert session_attempts[0]["sessionId"] == "session-7"


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

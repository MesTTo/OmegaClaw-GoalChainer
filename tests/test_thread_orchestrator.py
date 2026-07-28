from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from thread_spec_fixture import VALID_THREAD_SPEC

from goal_chainer.thread_models import ThreadExecutionError, ThreadUsage
from goal_chainer.thread_orchestrator import ThreadOrchestrator
from goal_chainer.thread_plan import compile_thread_markdown
from goal_chainer.thread_runtime import ThreadRuntime

HENCE_COMPATIBILITY = (
    Path(__file__).parent / "fixtures" / "threadkeeper" / "hence-compatibility.md"
)


@pytest.fixture(scope="module")
def runtime() -> ThreadRuntime:
    return ThreadRuntime()


def orchestrator(tmp_path, runtime, source=VALID_THREAD_SPEC):
    plan_path = tmp_path / "thread.metta"
    compilation = compile_thread_markdown(
        source,
        plan_path=plan_path,
        thread_runtime=runtime,
    )
    return ThreadOrchestrator(
        compilation.specification,
        plan_path=plan_path,
        audit_path=tmp_path / "thread.jsonl",
        runtime=runtime,
    )


def accept(_task, _observation):
    return "accept", "acceptance condition observed"


def git(repository, *arguments):
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()


def git_repository(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.name", "Test User")
    git(repository, "config", "user.email", "test@example.invalid")
    (repository / "base.txt").write_text("base\n")
    git(repository, "add", "base.txt")
    git(repository, "commit", "-m", "base")
    return repository


def _board_state(snapshot):
    return {
        "backlog": tuple(sorted(snapshot.board.backlog)),
        "ready": tuple(sorted(snapshot.board.ready)),
        "in_progress": tuple(sorted(snapshot.board.in_progress)),
        "blocked": tuple(sorted(snapshot.board.blocked)),
        "done": tuple(sorted(snapshot.board.done)),
    }


def _hence_binary() -> Path | None:
    configured = os.environ.get("HENCE_BIN")
    candidates = (
        Path(configured).expanduser() if configured else None,
        Path(shutil.which("hence")) if shutil.which("hence") else None,
        Path("/home/user/Dev/hence/target/release/hence"),
    )
    return next(
        (
            candidate
            for candidate in candidates
            if candidate is not None
            and candidate.is_file()
            and os.access(candidate, os.X_OK)
        ),
        None,
    )


def _hence_board(binary: Path, plan: Path) -> dict[str, tuple[str, ...]]:
    result = subprocess.run(
        [
            str(binary),
            "--no-color",
            "-q",
            "-f",
            str(plan),
            "plan",
            "board",
            "--json",
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    import json

    payload = json.loads(result.stdout)
    return {
        state: tuple(sorted(row["task"] for row in payload[state]))
        for state in ("backlog", "ready", "in_progress", "blocked", "done")
    }


def _hence_mutate(
    binary: Path,
    plan: Path,
    operation: str,
    task: str,
    *arguments: str,
) -> None:
    subprocess.run(
        [
            str(binary),
            "--no-color",
            "-q",
            "--agent",
            "test-supervisor",
            "-f",
            str(plan),
            "task",
            operation,
            task,
            *arguments,
        ],
        capture_output=True,
        check=True,
        text=True,
    )


def test_success_requires_evaluator_then_completes_omega_task(
    tmp_path,
    runtime,
) -> None:
    thread = orchestrator(tmp_path, runtime)

    result = thread.run_task(
        "collect-evidence",
        [sys.executable, "-c", "print('evidence-collected')"],
        cwd=tmp_path,
        evaluator=accept,
        usage=ThreadUsage(10, 5),
    )

    assert result.outcome == "complete"
    assert result.snapshot.board.done == ("collect-evidence",)
    assert result.snapshot.board.ready == ("redact-summary",)
    assert result.attempts[0].evaluation.verdict == "accept"
    inspection = thread.inspect()
    assert inspection["usage_tokens"] == 15
    event_types = [event.event_type for event in thread.audit.verify()]
    assert event_types.index("evaluation-recorded") < event_types.index(
        "task-completed"
    )


def test_petta_lifecycle_matches_frozen_and_live_hence_corpus(
    tmp_path,
    runtime,
) -> None:
    source = HENCE_COMPATIBILITY.read_text()
    thread = orchestrator(tmp_path, runtime, source)
    expected = [
        {
            "backlog": ("summary",),
            "ready": ("evidence",),
            "in_progress": (),
            "blocked": (),
            "done": (),
        },
        {
            "backlog": ("summary",),
            "ready": (),
            "in_progress": ("evidence",),
            "blocked": (),
            "done": (),
        },
        {
            "backlog": ("summary",),
            "ready": ("evidence",),
            "in_progress": (),
            "blocked": (),
            "done": (),
        },
        {
            "backlog": (),
            "ready": ("summary",),
            "in_progress": (),
            "blocked": (),
            "done": ("evidence",),
        },
        {
            "backlog": (),
            "ready": (),
            "in_progress": (),
            "blocked": ("summary",),
            "done": ("evidence",),
        },
    ]
    observed = [_board_state(thread._snapshot())]
    observed.append(
        _board_state(thread.session.claim("evidence", "test-supervisor").value.snapshot)
    )
    observed.append(
        _board_state(
            thread.session.unclaim("evidence", "test-supervisor").value.snapshot
        )
    )
    observed.append(
        _board_state(
            thread.session.complete("evidence", "test-supervisor").value.snapshot
        )
    )
    observed.append(
        _board_state(thread.session.block("summary", "test-supervisor").value.snapshot)
    )
    assert observed == expected

    hence = _hence_binary()
    if hence is None:
        return
    spl = source.split("```spl\n", 1)[1].split("\n```", 1)[0]
    plan = tmp_path / "hence-compatibility.spl"
    plan.write_text(spl + "\n")
    hence_observed = [_hence_board(hence, plan)]
    _hence_mutate(hence, plan, "claim", "evidence")
    hence_observed.append(_hence_board(hence, plan))
    _hence_mutate(hence, plan, "unclaim", "evidence")
    hence_observed.append(_hence_board(hence, plan))
    _hence_mutate(hence, plan, "complete", "evidence")
    hence_observed.append(_hence_board(hence, plan))
    _hence_mutate(hence, plan, "block", "summary", "test")
    hence_observed.append(_hence_board(hence, plan))
    assert hence_observed == expected


def test_evaluator_rejection_retries_before_completion(tmp_path, runtime) -> None:
    thread = orchestrator(tmp_path, runtime)
    evaluations = 0

    def reject_once(_task, _observation):
        nonlocal evaluations
        evaluations += 1
        return (
            ("reject", "first result incomplete")
            if evaluations == 1
            else ("accept", "second result accepted")
        )

    result = thread.run_task(
        "collect-evidence",
        [sys.executable, "-c", "print('candidate')"],
        cwd=tmp_path,
        evaluator=reject_once,
    )

    assert result.outcome == "complete"
    assert [attempt.evaluation.verdict for attempt in result.attempts] == [
        "reject",
        "accept",
    ]
    assert any(event.event_type == "task-retried" for event in thread.audit.verify())


def test_exhausted_worker_failure_blocks_downstream_work(tmp_path, runtime) -> None:
    thread = orchestrator(tmp_path, runtime)

    result = thread.run_task(
        "collect-evidence",
        [sys.executable, "-c", "raise SystemExit(2)"],
        cwd=tmp_path,
        evaluator=accept,
    )

    assert result.outcome == "permanent-failure"
    assert len(result.attempts) == 3
    assert result.snapshot.status.blocked == ("collect-evidence",)
    assert result.snapshot.status.upstream_blocked == ("redact-summary",)


def test_specialist_budget_denial_does_not_claim_task(tmp_path, runtime) -> None:
    source = VALID_THREAD_SPEC.replace(
        "(thread-depends incident-42 redact-summary collect-evidence)\n",
        "",
    )
    thread = orchestrator(tmp_path, runtime, source)
    thread.record_usage(
        ThreadUsage(120000, 0),
        task_id="redact-summary",
        attempt=0,
    )

    result = thread.run_task(
        "redact-summary",
        [sys.executable, "-c", "print('should not run')"],
        cwd=tmp_path,
        evaluator=accept,
        local_iterations=1,
        hard=True,
    )

    assert result.outcome == "denied"
    assert result.attempts == ()
    assert "redact-summary" in result.snapshot.board.ready
    assert not any(
        event.event_type == "task-claimed" for event in thread.audit.verify()
    )


def test_high_stakes_specialist_requires_adjudicator(tmp_path, runtime) -> None:
    source = VALID_THREAD_SPEC.replace(
        "(thread-depends incident-42 redact-summary collect-evidence)\n",
        "",
    )
    thread = orchestrator(tmp_path, runtime, source)
    adjudications = 0

    def adjudicate(_task, _observation):
        nonlocal adjudications
        adjudications += 1
        return "accept", "security owner approved"

    result = thread.run_task(
        "redact-summary",
        [sys.executable, "-c", "print('summary-redacted')"],
        cwd=tmp_path,
        evaluator=accept,
        adjudicator=adjudicate,
        local_iterations=1,
        hard=True,
    )

    assert result.outcome == "complete"
    assert result.attempts[0].route == "specialist"
    assert result.attempts[0].adjudication.verdict == "accept"
    assert adjudications == 1


def test_external_evaluator_reads_private_context_and_returns_json(
    tmp_path,
    runtime,
) -> None:
    thread = orchestrator(tmp_path, runtime)
    evaluator = tmp_path / "evaluator.py"
    evaluator.write_text(
        "import json,sys\n"
        "data=json.load(open(sys.argv[1]))\n"
        "assert data['task']['acceptance']=='evidence-collected'\n"
        "print(json.dumps({'verdict':'accept','reason':'external check passed'}))\n"
    )

    result = thread.run_task(
        "collect-evidence",
        [sys.executable, "-c", "print('evidence-collected')"],
        cwd=tmp_path,
        evaluator=[sys.executable, str(evaluator)],
    )

    assert result.outcome == "complete"
    assert result.attempts[0].evaluation.reason == "external check passed"
    assert not list(tmp_path.glob(".goalchainer-evaluation-*.json"))


def test_accepted_worktree_updates_only_the_integration_branch(
    tmp_path,
    runtime,
) -> None:
    source = VALID_THREAD_SPEC.replace(
        "(thread-merge-policy incident-42 none none)",
        (
            "(thread-merge-policy incident-42 integration-branch "
            "goalchainer-integration)"
        ),
    )
    thread = orchestrator(tmp_path, runtime, source)
    repository = git_repository(tmp_path)
    caller_head = git(repository, "rev-parse", "HEAD")

    result = thread.run_task_in_worktree(
        "collect-evidence",
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('evidence.txt').write_text('ok\\n')",
        ],
        repository=repository,
        worktree_root=tmp_path / "worktrees",
        evaluator=accept,
    )

    assert result.execution.outcome == "complete"
    assert result.retained is False
    assert git(repository, "symbolic-ref", "--short", "HEAD") == "main"
    assert git(repository, "rev-parse", "HEAD") == caller_head
    assert git(repository, "show", "goalchainer-integration:evidence.txt") == "ok"


def test_integration_conflict_blocks_task_before_completion(
    tmp_path,
    runtime,
) -> None:
    source = VALID_THREAD_SPEC.replace(
        "(thread-merge-policy incident-42 none none)",
        (
            "(thread-merge-policy incident-42 integration-branch "
            "goalchainer-integration)"
        ),
    )
    thread = orchestrator(tmp_path, runtime, source)
    repository = git_repository(tmp_path)
    git(repository, "branch", "goalchainer-integration")
    git(repository, "switch", "goalchainer-integration")
    (repository / "base.txt").write_text("integration\n")
    git(repository, "commit", "-am", "integration side")
    git(repository, "switch", "main")

    with pytest.raises(ThreadExecutionError, match="merge has conflicts"):
        thread.run_task_in_worktree(
            "collect-evidence",
            [
                sys.executable,
                "-c",
                ("from pathlib import Path; Path('base.txt').write_text('worker\\n')"),
            ],
            repository=repository,
            worktree_root=tmp_path / "worktrees",
            evaluator=accept,
        )

    inspection = thread.inspect()
    snapshot = inspection["snapshot"]
    assert "collect-evidence" in snapshot["status"]["blocked"]
    assert "collect-evidence" not in snapshot["board"]["done"]
    worktree = tmp_path / "worktrees" / "incident-42-collect-evidence-attempt-1"
    assert worktree.is_dir()
    assert any(
        event.event_type == "worktree-retained" for event in thread.audit.verify()
    )


def test_orchestration_lock_symlink_fails_as_thread_error(
    tmp_path,
    runtime,
) -> None:
    plan_path = tmp_path / "thread.metta"
    compilation = compile_thread_markdown(
        VALID_THREAD_SPEC,
        plan_path=plan_path,
        thread_runtime=runtime,
    )
    lock_path = plan_path.with_suffix(".metta.thread.lock")
    lock_path.symlink_to(tmp_path / "outside.lock")

    with pytest.raises(ThreadExecutionError, match="opened safely"):
        ThreadOrchestrator(
            compilation.specification,
            plan_path=plan_path,
            audit_path=tmp_path / "thread.jsonl",
            runtime=runtime,
        )

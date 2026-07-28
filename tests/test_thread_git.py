from __future__ import annotations

import subprocess

import pytest

from goal_chainer.thread_git import ThreadGitWorktrees
from goal_chainer.thread_models import ThreadExecutionError


def git(repository, *arguments):
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()


def repository(tmp_path, *, object_format="sha1"):
    path = tmp_path / "repository"
    path.mkdir()
    git(path, "init", f"--object-format={object_format}", "-b", "main")
    git(path, "config", "user.name", "Test User")
    git(path, "config", "user.email", "test@example.invalid")
    (path / "base.txt").write_text("base\n")
    git(path, "add", "base.txt")
    git(path, "commit", "-m", "base")
    return path


def test_detached_attempt_and_in_memory_integration_leave_caller_untouched(
    tmp_path,
) -> None:
    repo = repository(tmp_path)
    manager = ThreadGitWorktrees(repo, tmp_path / "worktrees")
    attempt = manager.create(
        thread_id="incident-42",
        task_id="collect-evidence",
        attempt=1,
    )
    caller_head = git(repo, "rev-parse", "HEAD")

    worktree = tmp_path / "worktrees" / "incident-42-collect-evidence-attempt-1"
    (worktree / "result.txt").write_text("accepted\n")
    worker_commit = manager.commit(attempt, message="Collect incident evidence")
    integrated = manager.integrate(
        worker_commit=worker_commit,
        integration_branch="goalchainer-integration",
        base_commit=attempt.base_commit,
        message="Integrate collect-evidence",
    )

    assert git(repo, "symbolic-ref", "--short", "HEAD") == "main"
    assert git(repo, "rev-parse", "HEAD") == caller_head
    assert git(repo, "status", "--porcelain") == ""
    assert git(repo, "rev-parse", "goalchainer-integration") == integrated
    assert git(repo, "show", "goalchainer-integration:result.txt") == "accepted"
    manager.remove(attempt)
    assert not worktree.exists()


def test_integration_refuses_to_update_a_checked_out_branch(tmp_path) -> None:
    repo = repository(tmp_path)
    manager = ThreadGitWorktrees(repo, tmp_path / "worktrees")
    attempt = manager.create(
        thread_id="incident-42",
        task_id="collect-evidence",
        attempt=1,
    )

    with pytest.raises(ThreadExecutionError, match="checked out"):
        manager.integrate(
            worker_commit=attempt.base_commit,
            integration_branch="main",
            base_commit=attempt.base_commit,
            message="Must not update main",
        )


def test_dirty_attempt_is_retained_for_inspection(tmp_path) -> None:
    repo = repository(tmp_path)
    manager = ThreadGitWorktrees(repo, tmp_path / "worktrees")
    attempt = manager.create(
        thread_id="incident-42",
        task_id="collect-evidence",
        attempt=1,
    )
    path = tmp_path / "worktrees" / "incident-42-collect-evidence-attempt-1"
    (path / "uncommitted.txt").write_text("retain\n")

    with pytest.raises(ThreadExecutionError, match="retained"):
        manager.remove(attempt)

    assert path.exists()


def test_sha256_repository_uses_full_object_ids(tmp_path) -> None:
    repo = repository(tmp_path, object_format="sha256")
    manager = ThreadGitWorktrees(repo, tmp_path / "worktrees")

    attempt = manager.create(
        thread_id="incident-42",
        task_id="collect-evidence",
        attempt=1,
    )

    assert len(attempt.base_commit) == 64
    assert set(attempt.base_commit) <= set("0123456789abcdef")

"""Isolated git worktrees and compare-and-swap integration branches."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from .thread_models import ThreadExecutionError, ThreadWorktree

_GIT_TIMEOUT_SECONDS = 30
_OID_LENGTHS = frozenset({40, 64})


class ThreadGitWorktrees:
    """Create detached attempts and integrate accepted commits off-worktree."""

    def __init__(
        self,
        repository: str | os.PathLike[str],
        worktree_root: str | os.PathLike[str],
    ) -> None:
        self.repository = Path(repository).expanduser().resolve()
        if self.repository.is_symlink() or not self.repository.is_dir():
            raise ThreadExecutionError("Thread git repository is not a real directory.")
        top = Path(self._git("rev-parse", "--show-toplevel").stdout.strip()).resolve()
        if top != self.repository:
            raise ThreadExecutionError(
                "Thread git repository must be its top-level directory.",
                details={"repository": str(self.repository), "top_level": str(top)},
            )
        self.root = Path(worktree_root).expanduser().absolute()
        if self.root.is_symlink():
            raise ThreadExecutionError("Thread worktree root must not be a symlink.")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if (
            not self.root.is_dir()
            or self.root.stat().st_uid != os.getuid()
            or stat.S_IMODE(self.root.stat().st_mode) & 0o077
        ):
            raise ThreadExecutionError(
                "Thread worktree root must be a private owned directory."
            )

    def create(
        self,
        *,
        thread_id: str,
        task_id: str,
        attempt: int,
        base: str = "HEAD",
    ) -> ThreadWorktree:
        _safe_component(thread_id, "thread id")
        _safe_component(task_id, "task id")
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt <= 0:
            raise ThreadExecutionError("Thread worktree attempt must be positive.")
        name = f"{thread_id}-{task_id}-attempt-{attempt}"
        destination = self.root / name
        if destination.exists() or destination.is_symlink():
            raise ThreadExecutionError(
                "Thread worktree destination already exists.",
                details={"path": str(destination)},
            )
        base_commit = self._oid(base)
        self._git(
            "worktree",
            "add",
            "--detach",
            "--lock",
            "--reason",
            f"GoalChainer thread {thread_id} task {task_id} attempt {attempt}",
            str(destination),
            base_commit,
        )
        return ThreadWorktree(
            path=str(destination),
            base_commit=base_commit,
            thread_id=thread_id,
            task_id=task_id,
            attempt=attempt,
        )

    def commit(
        self,
        worktree: ThreadWorktree,
        *,
        message: str,
    ) -> str:
        path = self._owned_worktree(worktree)
        if not isinstance(message, str) or not message.strip() or "\x00" in message:
            raise ThreadExecutionError("Thread worktree commit message is invalid.")
        self._git("-C", str(path), "add", "--all")
        staged = self._git(
            "-C",
            str(path),
            "diff",
            "--cached",
            "--quiet",
            check=False,
        )
        if staged.returncode == 0:
            return self._oid("HEAD", cwd=path)
        if staged.returncode != 1:
            raise ThreadExecutionError(
                "Thread worktree staged diff could not be inspected.",
                details={"stderr": staged.stderr.strip()},
            )
        self._git("-C", str(path), "commit", "-m", message)
        return self._oid("HEAD", cwd=path)

    def integrate(
        self,
        *,
        worker_commit: str,
        integration_branch: str,
        base_commit: str,
        message: str,
    ) -> str:
        branch = _branch(integration_branch)
        worker = self._oid(worker_commit)
        base = self._oid(base_commit)
        reference = f"refs/heads/{branch}"
        checked_out = _checked_out_branches(
            self._git("worktree", "list", "--porcelain", "-z").stdout
        )
        if reference in checked_out:
            raise ThreadExecutionError(
                "Thread integration branch is checked out in a worktree.",
                details={"branch": branch},
            )
        current_result = self._git(
            "rev-parse",
            "--verify",
            reference,
            check=False,
        )
        if current_result.returncode == 0:
            current = current_result.stdout.strip()
        else:
            current = base
        if (
            self._git(
                "merge-base",
                "--is-ancestor",
                current,
                worker,
                check=False,
            ).returncode
            == 0
        ):
            new_commit = worker
        else:
            merge = self._git(
                "merge-tree",
                "--write-tree",
                current,
                worker,
                check=False,
            )
            if merge.returncode != 0:
                raise ThreadExecutionError(
                    "Thread integration merge has conflicts.",
                    details={
                        "branch": branch,
                        "output": merge.stdout.strip(),
                        "stderr": merge.stderr.strip(),
                    },
                )
            tree = merge.stdout.splitlines()[0].strip()
            commit = self._git(
                "commit-tree",
                tree,
                "-p",
                current,
                "-p",
                worker,
                "-m",
                message,
            )
            new_commit = commit.stdout.strip()
        expected = (
            current
            if current_result.returncode == 0
            else "0" * self._object_id_length()
        )
        update = self._git(
            "update-ref",
            "-m",
            message,
            reference,
            new_commit,
            expected,
            check=False,
        )
        if update.returncode != 0:
            raise ThreadExecutionError(
                "Thread integration branch changed concurrently.",
                details={"branch": branch, "stderr": update.stderr.strip()},
            )
        return new_commit

    def remove(self, worktree: ThreadWorktree) -> None:
        path = self._owned_worktree(worktree)
        status = self._git(
            "-C",
            str(path),
            "status",
            "--porcelain=v1",
        ).stdout
        if status:
            raise ThreadExecutionError(
                "Thread worktree is dirty and was retained.",
                details={"path": str(path)},
            )
        self._git("worktree", "unlock", str(path))
        self._git("worktree", "remove", str(path))

    def _owned_worktree(self, worktree: ThreadWorktree) -> Path:
        if not isinstance(worktree, ThreadWorktree):
            raise TypeError("worktree must be ThreadWorktree")
        path = Path(worktree.path).absolute()
        if path.parent != self.root or not path.is_dir() or path.is_symlink():
            raise ThreadExecutionError(
                "Thread worktree is outside the configured root.",
                details={"path": str(path)},
            )
        return path

    def _oid(self, value: str, *, cwd: Path | None = None) -> str:
        result = self._git(
            "rev-parse",
            "--verify",
            f"{value}^{{commit}}",
            cwd=cwd,
        ).stdout.strip()
        if len(result) not in _OID_LENGTHS or any(
            character not in "0123456789abcdef" for character in result
        ):
            raise ThreadExecutionError("Git returned a malformed object ID.")
        return result

    def _object_id_length(self) -> int:
        object_format = self._git(
            "rev-parse",
            "--show-object-format",
        ).stdout.strip()
        if object_format == "sha1":
            return 40
        if object_format == "sha256":
            return 64
        raise ThreadExecutionError(
            "Git returned an unsupported object format.",
            details={"object_format": object_format},
        )

    def _git(
        self,
        *arguments: str,
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(
            ["git", "-C", str(cwd or self.repository), *arguments],
            capture_output=True,
            check=False,
            env=environment,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
        if check and result.returncode != 0:
            raise ThreadExecutionError(
                "Thread git command failed.",
                details={
                    "arguments": list(arguments),
                    "returncode": result.returncode,
                    "stderr": result.stderr.strip(),
                },
            )
        return result


def _safe_component(value: str, name: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or not value[0].isalpha()
        or any(
            not (character.isascii() and (character.isalnum() or character in "_-"))
            for character in value
        )
    ):
        raise ThreadExecutionError(f"Thread {name} is unsafe.")


def _branch(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ThreadExecutionError("Thread integration branch is empty.")
    result = subprocess.run(
        ["git", "check-ref-format", "--branch", value],
        capture_output=True,
        check=False,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise ThreadExecutionError(
            "Thread integration branch is invalid.",
            details={"branch": value},
        )
    return value


def _checked_out_branches(output: str) -> set[str]:
    return {
        field.removeprefix("branch ")
        for field in output.split("\0")
        if field.startswith("branch refs/heads/")
    }


__all__ = ["ThreadGitWorktrees"]

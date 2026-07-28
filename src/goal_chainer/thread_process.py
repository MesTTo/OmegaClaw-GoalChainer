"""Bounded worker process execution with passive liveness observation."""

from __future__ import annotations

import errno
import json
import os
import pty
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from .thread_models import (
    ThreadExecutionError,
    ThreadProcessObservation,
    ThreadSupervision,
    ThreadTask,
)

_DEFAULT_OUTPUT_LIMIT = 1024 * 1024
_SELECT_INTERVAL_SECONDS = 0.1
_TERMINATION_GRACE_SECONDS = 1.0
_MAX_ACTIVITY_FILES = 10_000


class ThreadProcessSupervisor:
    """Run one command under lease, activity, output, and wall bounds."""

    def __init__(
        self,
        *,
        output_limit: int = _DEFAULT_OUTPUT_LIMIT,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            isinstance(output_limit, bool)
            or not isinstance(output_limit, int)
            or output_limit <= 0
        ):
            raise ValueError("output limit must be a positive integer")
        self.output_limit = output_limit
        self._monotonic = monotonic

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: str | os.PathLike[str],
        supervision: ThreadSupervision,
        env: Mapping[str, str] | None = None,
        renew_lease: Callable[[], bool] | None = None,
        use_pty: bool = True,
    ) -> ThreadProcessObservation:
        argv = _command(command)
        workspace = _workspace(cwd)
        executable = shutil.which(argv[0])
        if executable is None:
            return ThreadProcessObservation(
                exit_reason="spawn-failed",
                exit_code=127,
                output=f"executable not found: {argv[0]}",
                output_bytes=0,
                duration_seconds=0.0,
                activity_events=0,
                lease_renewals=0,
            )
        argv[0] = executable
        child_env = os.environ.copy()
        if env is not None:
            if not all(
                isinstance(key, str)
                and isinstance(value, str)
                and "\x00" not in key
                and "\x00" not in value
                and "=" not in key
                for key, value in env.items()
            ):
                raise ThreadExecutionError(
                    "Thread worker environment must contain valid text pairs."
                )
            child_env.update(env)
        if use_pty:
            return self._run_pty(
                argv,
                workspace=workspace,
                supervision=supervision,
                env=child_env,
                renew_lease=renew_lease,
            )
        return self._run_pipe(
            argv,
            workspace=workspace,
            supervision=supervision,
            env=child_env,
            renew_lease=renew_lease,
        )

    def _run_pty(
        self,
        argv: list[str],
        *,
        workspace: Path,
        supervision: ThreadSupervision,
        env: Mapping[str, str],
        renew_lease: Callable[[], bool] | None,
    ) -> ThreadProcessObservation:
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(
                argv,
                cwd=workspace,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=slave,
                stderr=slave,
                close_fds=True,
                start_new_session=True,
            )
        except OSError as exc:
            os.close(master)
            os.close(slave)
            return ThreadProcessObservation(
                exit_reason="spawn-failed",
                exit_code=127,
                output=f"{type(exc).__name__}: {exc}",
                output_bytes=0,
                duration_seconds=0.0,
                activity_events=0,
                lease_renewals=0,
            )
        os.close(slave)
        return self._observe(
            process,
            master,
            workspace=workspace,
            supervision=supervision,
            renew_lease=renew_lease,
        )

    def _run_pipe(
        self,
        argv: list[str],
        *,
        workspace: Path,
        supervision: ThreadSupervision,
        env: Mapping[str, str],
        renew_lease: Callable[[], bool] | None,
    ) -> ThreadProcessObservation:
        try:
            process = subprocess.Popen(
                argv,
                cwd=workspace,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                close_fds=True,
                start_new_session=True,
            )
        except OSError as exc:
            return ThreadProcessObservation(
                exit_reason="spawn-failed",
                exit_code=127,
                output=f"{type(exc).__name__}: {exc}",
                output_bytes=0,
                duration_seconds=0.0,
                activity_events=0,
                lease_renewals=0,
            )
        if process.stdout is None:
            _terminate_group(process)
            raise ThreadExecutionError("Thread worker stdout pipe was not created.")
        output_fd = os.dup(process.stdout.fileno())
        process.stdout.close()
        return self._observe(
            process,
            output_fd,
            workspace=workspace,
            supervision=supervision,
            renew_lease=renew_lease,
        )

    def _observe(
        self,
        process: subprocess.Popen[bytes],
        output_fd: int,
        *,
        workspace: Path,
        supervision: ThreadSupervision,
        renew_lease: Callable[[], bool] | None,
    ) -> ThreadProcessObservation:
        os.set_blocking(output_fd, False)
        selector = selectors.DefaultSelector()
        selector.register(output_fd, selectors.EVENT_READ)
        output = bytearray()
        started = self._monotonic()
        last_activity = started
        next_lease = started + supervision.lease_seconds / 2
        workspace_state = _workspace_state(workspace)
        activity_events = 0
        lease_renewals = 0
        exit_reason = "process-exited"
        try:
            while True:
                now = self._monotonic()
                if now - started >= supervision.wall_timeout_seconds:
                    exit_reason = "wall-timeout"
                    _terminate_group(process)
                    break
                if now - last_activity >= supervision.idle_timeout_seconds:
                    exit_reason = "idle-timeout"
                    _terminate_group(process)
                    break
                if now >= next_lease:
                    if renew_lease is not None and not renew_lease():
                        exit_reason = "lease-expired"
                        _terminate_group(process)
                        break
                    lease_renewals += 1
                    next_lease = now + supervision.lease_seconds / 2
                events = selector.select(_SELECT_INTERVAL_SECONDS)
                for key, _ in events:
                    chunk = _read_available(key.fd)
                    if chunk:
                        output.extend(chunk)
                        last_activity = self._monotonic()
                        activity_events += 1
                        if len(output) > self.output_limit:
                            del output[self.output_limit :]
                            exit_reason = "output-limit"
                            _terminate_group(process)
                            break
                    elif process.poll() is not None:
                        selector.unregister(output_fd)
                if exit_reason == "output-limit":
                    break
                current_state = _workspace_state(workspace)
                if current_state != workspace_state:
                    workspace_state = current_state
                    last_activity = self._monotonic()
                    activity_events += 1
                if process.poll() is not None:
                    remaining = _read_available(output_fd)
                    if remaining:
                        output.extend(remaining[: self.output_limit - len(output)])
                    break
            return_code = process.wait()
        finally:
            selector.close()
            try:
                os.close(output_fd)
            except OSError:
                pass
        finished = self._monotonic()
        return ThreadProcessObservation(
            exit_reason=exit_reason,  # type: ignore[arg-type]
            exit_code=return_code,
            output=bytes(output).decode("utf-8", errors="replace"),
            output_bytes=len(output),
            duration_seconds=finished - started,
            activity_events=activity_events,
            lease_renewals=lease_renewals,
        )


def run_evaluator_command(
    evaluator: Sequence[str],
    *,
    cwd: str | os.PathLike[str],
    task: ThreadTask,
    observation: ThreadProcessObservation,
    supervision: ThreadSupervision,
    process_supervisor: ThreadProcessSupervisor | None = None,
) -> tuple[str, str]:
    """Run an evaluator against one private worker-result document."""

    workspace = _workspace(cwd)
    supervisor = process_supervisor or ThreadProcessSupervisor()
    descriptor, temporary = tempfile.mkstemp(
        prefix=".goalchainer-evaluation-",
        suffix=".json",
        dir=workspace,
        text=True,
    )
    context_path = Path(temporary)
    try:
        os.chmod(context_path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "task": {
                        "task_id": task.task_id,
                        "acceptance": task.acceptance,
                        "stakes": task.stakes,
                    },
                    "worker": {
                        "exit_reason": observation.exit_reason,
                        "exit_code": observation.exit_code,
                        "output": observation.output,
                    },
                },
                handle,
                ensure_ascii=False,
                sort_keys=True,
            )
            handle.flush()
            os.fsync(handle.fileno())
        result = supervisor.run(
            [*evaluator, str(context_path)],
            cwd=workspace,
            supervision=supervision,
            use_pty=False,
        )
        if result.exit_reason != "process-exited" or result.exit_code != 0:
            raise ThreadExecutionError(
                "Thread evaluator command failed.",
                details={
                    "exit_reason": result.exit_reason,
                    "exit_code": result.exit_code,
                },
            )
        lines = [line for line in result.output.splitlines() if line.strip()]
        if not lines:
            raise ThreadExecutionError("Thread evaluator command returned no verdict.")
        payload = json.loads(lines[-1])
        if (
            not isinstance(payload, dict)
            or set(payload) != {"reason", "verdict"}
            or payload["verdict"] not in {"accept", "reject"}
            or not isinstance(payload["reason"], str)
            or not payload["reason"]
        ):
            raise ThreadExecutionError("Thread evaluator verdict is malformed.")
        return payload["verdict"], payload["reason"]
    except json.JSONDecodeError as exc:
        raise ThreadExecutionError(
            "Thread evaluator verdict is malformed.",
            details={"error": str(exc)},
        ) from exc
    finally:
        context_path.unlink(missing_ok=True)


def _command(command: Sequence[str]) -> list[str]:
    if (
        isinstance(command, (str, bytes))
        or not command
        or not all(
            isinstance(argument, str) and bool(argument) and "\x00" not in argument
            for argument in command
        )
    ):
        raise ThreadExecutionError(
            "Thread worker command must be a nonempty argument sequence."
        )
    return list(command)


def _workspace(cwd: str | os.PathLike[str]) -> Path:
    path = Path(cwd).expanduser().absolute()
    if path.is_symlink() or not path.is_dir():
        raise ThreadExecutionError(
            "Thread worker workspace must be an existing real directory.",
            details={"path": str(path)},
        )
    return path


def _read_available(file_descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        try:
            chunk = os.read(file_descriptor, 64 * 1024)
        except BlockingIOError:
            break
        except OSError as exc:
            if exc.errno == errno.EIO:
                break
            raise
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=_TERMINATION_GRACE_SECONDS)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def _workspace_state(path: Path) -> tuple[int, int]:
    latest = path.stat().st_mtime_ns
    count = 0
    pending = [path]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            if entry.name == ".git":
                continue
            count += 1
            if count > _MAX_ACTIVITY_FILES:
                raise ThreadExecutionError(
                    "Thread workspace exceeds the passive observation file limit.",
                    details={"path": str(path), "limit": _MAX_ACTIVITY_FILES},
                )
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            latest = max(latest, metadata.st_mtime_ns)
            if entry.is_dir(follow_symlinks=False):
                pending.append(Path(entry.path))
    return latest, count


__all__ = ["ThreadProcessSupervisor", "run_evaluator_command"]

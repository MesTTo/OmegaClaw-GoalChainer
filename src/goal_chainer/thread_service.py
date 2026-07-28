"""Typed request surface for CLI and OmegaClaw thread orchestration."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .thread_demo import run_thread_demo
from .thread_models import ThreadExecutionError, ThreadUsage
from .thread_orchestrator import ThreadOrchestrator
from .thread_plan import compile_thread_markdown
from .thread_render import render_thread_status
from .thread_spec import read_thread_markdown_source

_OPERATIONS = {
    "compile": {"operation", "spec", "plan", "audit"},
    "inspect": {"operation", "spec", "plan", "audit"},
    "route": {
        "operation",
        "spec",
        "plan",
        "audit",
        "task",
        "local_iterations",
        "hard",
    },
    "record-usage": {
        "operation",
        "spec",
        "plan",
        "audit",
        "task",
        "attempt",
        "prompt_tokens",
        "completion_tokens",
    },
    "render": {"operation", "spec", "plan", "audit"},
    "run": {
        "operation",
        "spec",
        "plan",
        "audit",
        "task",
        "command",
        "cwd",
        "evaluator_command",
        "adjudicator_command",
        "prompt_tokens",
        "completion_tokens",
        "local_iterations",
        "hard",
        "pty",
        "repository",
        "worktree_root",
    },
    "demo": {"operation", "directory"},
}


def run_thread_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and execute one versioned thread request."""

    if not isinstance(payload, dict):
        raise ThreadExecutionError("Thread request must be a JSON object.")
    operation = payload.get("operation")
    if not isinstance(operation, str) or operation not in _OPERATIONS:
        raise ThreadExecutionError(
            "Unknown thread operation.",
            details={
                "operation": operation,
                "available": sorted(_OPERATIONS),
            },
        )
    if not all(isinstance(name, str) for name in payload):
        raise ThreadExecutionError("Thread request field names must be strings.")
    unknown = sorted(set(payload) - _OPERATIONS[operation])
    if unknown:
        raise ThreadExecutionError(
            "Thread request contains unknown fields.",
            details={"unknown": unknown},
        )
    if operation == "demo":
        directory = payload.get("directory")
        if directory is not None and not isinstance(directory, str):
            raise ThreadExecutionError("Thread demo directory must be a path.")
        return run_thread_demo(directory)
    spec_path = _path(payload, "spec")
    plan_path = _path(payload, "plan")
    audit_path = _path(payload, "audit")
    source, source_file = read_thread_markdown_source(spec_path)
    if operation == "compile":
        compilation = compile_thread_markdown(
            source,
            source_path=str(source_file),
            plan_path=plan_path,
        )
        thread = ThreadOrchestrator(
            compilation.specification,
            plan_path=plan_path,
            audit_path=audit_path,
        )
        return {
            "operation": operation,
            "protocol": "goalchainer-thread-v1",
            "result": compilation.to_dict(),
            "inspection": thread.inspect(),
        }
    compilation = compile_thread_markdown(
        source,
        source_path=str(source_file),
    )
    thread = ThreadOrchestrator(
        compilation.specification,
        plan_path=plan_path,
        audit_path=audit_path,
    )
    if operation == "inspect":
        result: object = thread.inspect()
    elif operation == "route":
        result = thread.route(
            _text(payload, "task"),
            local_iterations=_integer(
                payload,
                "local_iterations",
                default=0,
            ),
            hard=_boolean(payload, "hard", default=False),
        )
    elif operation == "record-usage":
        result = {
            "spent_tokens": thread.record_usage(
                ThreadUsage(
                    _integer(payload, "prompt_tokens"),
                    _integer(payload, "completion_tokens"),
                ),
                task_id=_text(payload, "task"),
                attempt=_integer(payload, "attempt"),
            )
        }
    elif operation == "render":
        result = render_thread_status(thread)
    elif operation == "run":
        command = _command(payload, "command")
        evaluator = _command(payload, "evaluator_command")
        adjudicator = (
            _command(payload, "adjudicator_command")
            if "adjudicator_command" in payload
            else None
        )
        usage = ThreadUsage(
            _integer(payload, "prompt_tokens", default=0),
            _integer(payload, "completion_tokens", default=0),
        )
        local_iterations = _integer(
            payload,
            "local_iterations",
            default=0,
        )
        hard = _boolean(payload, "hard", default=False)
        use_pty = _boolean(payload, "pty", default=True)
        repository = payload.get("repository")
        worktree_root = payload.get("worktree_root")
        if (repository is None) != (worktree_root is None):
            raise ThreadExecutionError(
                "Thread run requires both repository and worktree_root."
            )
        if repository is not None:
            if not isinstance(repository, str) or not isinstance(
                worktree_root,
                str,
            ):
                raise ThreadExecutionError("Thread worktree paths must be strings.")
            result = thread.run_task_in_worktree(
                _text(payload, "task"),
                command,
                repository=repository,
                worktree_root=worktree_root,
                evaluator=evaluator,
                adjudicator=adjudicator,
                usage=usage,
                local_iterations=local_iterations,
                hard=hard,
                use_pty=use_pty,
            )
        else:
            result = thread.run_task(
                _text(payload, "task"),
                command,
                cwd=_path(payload, "cwd"),
                evaluator=evaluator,
                adjudicator=adjudicator,
                usage=usage,
                local_iterations=local_iterations,
                hard=hard,
                use_pty=use_pty,
            )
    else:
        raise AssertionError(f"unhandled thread operation: {operation}")
    return {
        "operation": operation,
        "protocol": "goalchainer-thread-v1",
        "result": _serialize(result),
    }


def _path(payload: dict[str, Any], name: str) -> Path:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise ThreadExecutionError(f"Thread {name} path is required.")
    return Path(value).expanduser().absolute()


def _text(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise ThreadExecutionError(f"Thread {name} must be nonempty text.")
    return value


def _integer(
    payload: dict[str, Any],
    name: str,
    *,
    default: int | None = None,
) -> int:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ThreadExecutionError(f"Thread {name} must be a nonnegative integer.")
    return value


def _boolean(
    payload: dict[str, Any],
    name: str,
    *,
    default: bool,
) -> bool:
    value = payload.get(name, default)
    if not isinstance(value, bool):
        raise ThreadExecutionError(f"Thread {name} must be a boolean.")
    return value


def _command(payload: dict[str, Any], name: str) -> list[str]:
    value = payload.get(name)
    if (
        not isinstance(value, list)
        or not value
        or not all(
            isinstance(argument, str) and bool(argument) and "\x00" not in argument
            for argument in value
        )
    ):
        raise ThreadExecutionError(f"Thread {name} must be a nonempty argument array.")
    return value


def _serialize(value: object) -> object:
    method = getattr(value, "to_dict", None)
    if callable(method):
        return method()
    if is_dataclass(value):
        return asdict(value)  # type: ignore[arg-type]
    return value


__all__ = ["run_thread_request"]

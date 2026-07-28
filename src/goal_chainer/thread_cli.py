"""Argument parsing for the `goalchainer thread` command group."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .thread_models import ThreadExecutionError
from .thread_service import run_thread_request


def add_thread_arguments(parser: argparse.ArgumentParser) -> None:
    operations = parser.add_subparsers(dest="thread_operation", required=True)
    for name in ("compile", "inspect", "render"):
        command = operations.add_parser(name)
        _state_paths(command, audit=True)
        command.add_argument("--json", action="store_true")
    route = operations.add_parser("route")
    _state_paths(route, audit=True)
    route.add_argument("--task", required=True)
    route.add_argument("--local-iterations", type=int, default=0)
    route.add_argument("--hard", action="store_true")
    route.add_argument("--json", action="store_true")
    usage = operations.add_parser("record-usage")
    _state_paths(usage, audit=True)
    usage.add_argument("--task", required=True)
    usage.add_argument("--attempt", type=int, required=True)
    usage.add_argument("--prompt-tokens", type=int, required=True)
    usage.add_argument("--completion-tokens", type=int, required=True)
    usage.add_argument("--json", action="store_true")
    run = operations.add_parser("run")
    _state_paths(run, audit=True)
    run.add_argument("--task", required=True)
    run.add_argument("--cwd", required=True)
    run.add_argument("--worker-command", required=True)
    run.add_argument("--evaluator-command", required=True)
    run.add_argument("--adjudicator-command")
    run.add_argument("--prompt-tokens", type=int, default=0)
    run.add_argument("--completion-tokens", type=int, default=0)
    run.add_argument("--local-iterations", type=int, default=0)
    run.add_argument("--hard", action="store_true")
    run.add_argument("--no-pty", action="store_true")
    run.add_argument("--repository")
    run.add_argument("--worktree-root")
    run.add_argument("--json", action="store_true")
    demo = operations.add_parser("demo")
    demo.add_argument("--directory")
    demo.add_argument("--json", action="store_true")


def run_thread_command(args: argparse.Namespace) -> dict[str, Any]:
    operation = args.thread_operation
    request: dict[str, Any] = {"operation": operation}
    for source, target in (
        ("spec", "spec"),
        ("plan", "plan"),
        ("audit", "audit"),
        ("task", "task"),
        ("attempt", "attempt"),
        ("prompt_tokens", "prompt_tokens"),
        ("completion_tokens", "completion_tokens"),
        ("local_iterations", "local_iterations"),
        ("repository", "repository"),
        ("worktree_root", "worktree_root"),
        ("directory", "directory"),
    ):
        value = getattr(args, source, None)
        if value is not None:
            request[target] = value
    if operation in {"route", "run"}:
        request["hard"] = args.hard
    if operation == "run":
        request.update(
            {
                "cwd": args.cwd,
                "command": _json_command(
                    args.worker_command,
                    "worker command",
                ),
                "evaluator_command": _json_command(
                    args.evaluator_command,
                    "evaluator command",
                ),
                "pty": not args.no_pty,
            }
        )
        if args.adjudicator_command is not None:
            request["adjudicator_command"] = _json_command(
                args.adjudicator_command,
                "adjudicator command",
            )
    return run_thread_request(request)


def _state_paths(
    parser: argparse.ArgumentParser,
    *,
    audit: bool,
) -> None:
    parser.add_argument("--spec", required=True)
    parser.add_argument("--plan", required=True)
    if audit:
        parser.add_argument("--audit", required=True)


def _json_command(source: str, name: str) -> list[str]:
    try:
        value = json.loads(source)
    except json.JSONDecodeError as exc:
        raise ThreadExecutionError(
            f"Thread {name} must be a JSON argument array.",
            details={"error": str(exc)},
        ) from exc
    if not isinstance(value, list):
        raise ThreadExecutionError(f"Thread {name} must be a JSON argument array.")
    return value


__all__ = ["add_thread_arguments", "run_thread_command"]

"""Host-effect atoms called by the PeTTa ThreadKeeper program."""

from __future__ import annotations

import base64
import json
from typing import Any, cast

from goal_chainer.thread_models import (
    ThreadCapability,
    ThreadExitReason,
    ThreadProcessObservation,
    ThreadStakes,
    ThreadSupervision,
    ThreadTask,
)
from goal_chainer.thread_process import (
    ThreadProcessSupervisor,
    run_evaluator_command,
)


def run_process(
    command_json: str,
    cwd: str,
    lease_seconds: int,
    idle_timeout_seconds: int,
    wall_timeout_seconds: int,
    environment_json: str,
    use_pty: object,
) -> str:
    """Execute one bounded worker and return a MeTTa observation."""

    command = _command(_decode_text(command_json))
    environment = _environment(_decode_text(environment_json))
    supervision = _supervision(
        lease_seconds,
        idle_timeout_seconds,
        wall_timeout_seconds,
    )
    observation = ThreadProcessSupervisor().run(
        command,
        cwd=_decode_text(cwd),
        supervision=supervision,
        env=environment,
        use_pty=_boolean(use_pty),
    )
    return _observation_atom(observation)


def evaluate(
    command_json: str,
    cwd: str,
    task_id: str,
    capability: str,
    acceptance: str,
    stakes: str,
    exit_reason: str,
    exit_code: int,
    output: str,
    output_bytes: int,
    duration_seconds: float,
    activity_events: int,
    lease_renewals: int,
    lease_seconds: int,
    idle_timeout_seconds: int,
    wall_timeout_seconds: int,
) -> str:
    """Run one external evaluation command and return a MeTTa verdict."""

    command = _command(_decode_text(command_json))
    task = ThreadTask(
        task_id=task_id,
        capability=cast(ThreadCapability, capability),
        acceptance=acceptance,
        stakes=cast(ThreadStakes, stakes),
    )
    observation = ThreadProcessObservation(
        exit_reason=cast(ThreadExitReason, exit_reason),
        exit_code=exit_code,
        output=_decode_text(output),
        output_bytes=output_bytes,
        duration_seconds=duration_seconds,
        activity_events=activity_events,
        lease_renewals=lease_renewals,
    )
    try:
        verdict, reason = run_evaluator_command(
            command,
            cwd=_decode_text(cwd),
            task=task,
            observation=observation,
            supervision=_supervision(
                lease_seconds,
                idle_timeout_seconds,
                wall_timeout_seconds,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        verdict = "reject"
        reason = f"evaluator failed: {type(exc).__name__}: {exc}"
    return f"(verdict {verdict} {_encode_text(reason)})"


def _supervision(lease: int, idle: int, wall: int) -> ThreadSupervision:
    return ThreadSupervision(
        lease_seconds=lease,
        idle_timeout_seconds=idle,
        wall_timeout_seconds=wall,
        max_retries=0,
    )


def _command(source: str) -> list[str]:
    value = json.loads(source)
    if (
        not isinstance(value, list)
        or not value
        or not all(
            isinstance(argument, str) and bool(argument) and "\x00" not in argument
            for argument in value
        )
    ):
        raise ValueError("command must be a nonempty JSON argument array")
    return value


def _environment(source: str) -> dict[str, str] | None:
    value: Any = json.loads(source)
    if value is None:
        return None
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise ValueError("environment must be a JSON object or null")
    return value


def _boolean(value: object) -> bool:
    if value in {True, "True", "true"}:
        return True
    if value in {False, "False", "false"}:
        return False
    raise ValueError("PTY flag must be boolean")


def _decode_text(value: str) -> str:
    if not value.startswith("b64_"):
        raise ValueError("encoded host text has no b64_ prefix")
    return base64.urlsafe_b64decode(value[4:].encode("ascii")).decode("utf-8")


def _encode_text(value: str) -> str:
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
    return "b64_" + encoded


def _observation_atom(observation: ThreadProcessObservation) -> str:
    return " ".join(
        (
            "(observation",
            observation.exit_reason,
            str(observation.exit_code),
            _encode_text(observation.output),
            str(observation.output_bytes),
            repr(observation.duration_seconds),
            str(observation.activity_events),
            str(observation.lease_renewals) + ")",
        )
    )


__all__ = ["evaluate", "run_process"]

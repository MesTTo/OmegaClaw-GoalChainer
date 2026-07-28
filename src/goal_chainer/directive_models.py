"""Typed values returned by OmegaClaw's PeTTa directive runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from .snars_models import SnarsError, SnarsInvalidInputError, SnarsProtocolError

TaskState = Literal[
    "backlog",
    "ready",
    "in-progress",
    "blocked",
    "upstream-blocked",
    "decomposed",
    "done",
]
LifecycleKind = Literal["claim", "unclaim", "complete", "block", "unblock"]


@dataclass(frozen=True, slots=True)
class DirectiveAssignment:
    task: str
    agent: str
    rule: str


@dataclass(frozen=True, slots=True)
class DirectiveStatus:
    tasks: tuple[str, ...]
    ready: tuple[str, ...]
    claimed: tuple[str, ...]
    blocked: tuple[str, ...]
    upstream_blocked: tuple[str, ...]
    completed: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DirectiveBoard:
    backlog: tuple[str, ...]
    ready: tuple[str, ...]
    in_progress: tuple[str, ...]
    blocked: tuple[str, ...]
    done: tuple[str, ...]


def directive_board_lanes(
    board: DirectiveBoard,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return the stable external name and task IDs for each board lane."""

    return (
        ("backlog", board.backlog),
        ("ready", board.ready),
        ("in-progress", board.in_progress),
        ("blocked", board.blocked),
        ("done", board.done),
    )


@dataclass(frozen=True, slots=True)
class DirectiveSummary:
    total: int
    backlog: int
    ready: int
    in_progress: int
    blocked: int
    done: int
    progress_pct: int | float


@dataclass(frozen=True, slots=True)
class DirectiveAnalysis:
    cycles: tuple[tuple[str, ...], ...]
    consistent: bool
    rendered: bool | None = None


@dataclass(frozen=True, slots=True)
class DirectiveSnapshot:
    status: DirectiveStatus
    next_actions: tuple[DirectiveAssignment, ...]
    board: DirectiveBoard
    summary: DirectiveSummary
    info: tuple[tuple[str, str], ...]
    assignments: tuple[DirectiveAssignment, ...]
    analysis: DirectiveAnalysis

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["info"] = dict(self.info)
        return _to_json_values(payload)


@dataclass(frozen=True, slots=True)
class DirectiveLifecycleResult:
    kind: LifecycleKind
    outcome: str
    task: str
    version: int | None
    plan_complete: bool
    accepted: bool
    reason: str | None
    snapshot: DirectiveSnapshot

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["snapshot"] = self.snapshot.to_dict()
        return _to_json_values(payload)


@dataclass(frozen=True, slots=True)
class DirectiveTaskState:
    task: str
    state: TaskState


@dataclass(frozen=True, slots=True)
class DirectiveValidation:
    valid: bool
    strict: bool


@dataclass(frozen=True, slots=True)
class DirectiveRun:
    operation: str
    value: object
    transcript: tuple[str, ...] = ()
    plan_path: str | None = None
    digest_before: str | None = None
    digest_after: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = self.value
        if hasattr(value, "to_dict"):
            serialized = value.to_dict()
        elif hasattr(value, "__dataclass_fields__"):
            serialized = asdict(value)
        else:
            serialized = value
        return _to_json_values(
            {
                "operation": self.operation,
                "result": serialized,
                "transcript": list(self.transcript),
                "plan_path": self.plan_path,
                "digest_before": self.digest_before,
                "digest_after": self.digest_after,
            }
        )


def _to_json_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _to_json_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_values(item) for item in value]
    return value


class DirectivePlanError(SnarsError):
    code = "directive_plan_error"


class DirectiveInvalidInputError(SnarsInvalidInputError):
    """Directive input did not satisfy the stable adapter contract."""


class DirectiveProtocolError(SnarsProtocolError):
    """PeTTa returned a malformed GoalChainer directive record."""


__all__ = [
    "DirectiveAnalysis",
    "DirectiveAssignment",
    "DirectiveBoard",
    "DirectiveInvalidInputError",
    "DirectiveLifecycleResult",
    "DirectivePlanError",
    "DirectiveProtocolError",
    "DirectiveRun",
    "DirectiveSnapshot",
    "DirectiveStatus",
    "DirectiveSummary",
    "DirectiveTaskState",
    "DirectiveValidation",
    "LifecycleKind",
    "TaskState",
    "directive_board_lanes",
]

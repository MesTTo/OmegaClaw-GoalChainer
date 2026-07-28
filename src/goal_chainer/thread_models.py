"""Immutable values for MeTTa Markdown thread orchestration."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol, cast

from .snars_models import (
    SnarsInvalidInputError,
    SnarsPettaExecutionError,
    SnarsProtocolError,
)

ThreadCapability = Literal["local", "specialist", "either"]
ThreadStakes = Literal["normal", "high"]
ThreadMergeMode = Literal["none", "integration-branch"]
ThreadRouteTarget = Literal["worker", "specialist", "denied"]
ThreadOutcome = Literal["complete", "retry", "permanent-failure"]
ThreadExitReason = Literal[
    "process-exited",
    "idle-timeout",
    "lease-expired",
    "wall-timeout",
    "output-limit",
    "spawn-failed",
]
ThreadVerdict = Literal["accept", "reject", "not-required"]
_SAFE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def _positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _nonnegative_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _nonempty(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty")
    return value


def _safe_id(name: str, value: str) -> str:
    result = _nonempty(name, value)
    if not _SAFE_ID_RE.fullmatch(result):
        raise ValueError(
            f"{name} must start with a letter and contain only letters, "
            "digits, hyphens, or underscores"
        )
    return result


def _validate_process_completion(
    exit_reason: ThreadExitReason,
    exit_code: int,
    output: str,
    *,
    output_name: str,
) -> None:
    if exit_reason not in {
        "process-exited",
        "idle-timeout",
        "lease-expired",
        "wall-timeout",
        "output-limit",
        "spawn-failed",
    }:
        raise ValueError(f"unsupported exit reason: {exit_reason}")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise TypeError("exit code must be an integer")
    if not isinstance(output, str):
        raise TypeError(f"{output_name} must be text")


@dataclass(frozen=True, slots=True)
class ThreadFact:
    atom: str
    line: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "atom", _nonempty("fact atom", self.atom))
        object.__setattr__(self, "line", _positive_int("fact line", self.line))


@dataclass(frozen=True, slots=True)
class ParsedThreadMarkdown:
    facts: tuple[ThreadFact, ...]
    semantic_digest: str
    source_path: str | None = None

    def __post_init__(self) -> None:
        if not self.facts or not all(
            isinstance(fact, ThreadFact) for fact in self.facts
        ):
            raise ValueError("facts must contain at least one ThreadFact")
        if len(self.semantic_digest) != 64:
            raise ValueError("semantic digest must be a SHA-256 hex digest")
        if self.source_path is not None:
            object.__setattr__(
                self,
                "source_path",
                _nonempty("source path", self.source_path),
            )


@dataclass(frozen=True, slots=True)
class ThreadBudget:
    ceiling_tokens: int
    soft_threshold_tokens: int
    min_local_iterations: int

    def __post_init__(self) -> None:
        ceiling = _positive_int("token ceiling", self.ceiling_tokens)
        soft = _nonnegative_int("soft threshold", self.soft_threshold_tokens)
        minimum = _nonnegative_int(
            "minimum local iterations",
            self.min_local_iterations,
        )
        if soft > ceiling:
            raise ValueError("soft threshold must not exceed the token ceiling")
        object.__setattr__(self, "ceiling_tokens", ceiling)
        object.__setattr__(self, "soft_threshold_tokens", soft)
        object.__setattr__(self, "min_local_iterations", minimum)


@dataclass(frozen=True, slots=True)
class ThreadSupervision:
    lease_seconds: int
    idle_timeout_seconds: int
    wall_timeout_seconds: int
    max_retries: int

    def __post_init__(self) -> None:
        lease = _positive_int("lease duration", self.lease_seconds)
        idle = _positive_int("idle timeout", self.idle_timeout_seconds)
        wall = _positive_int("wall timeout", self.wall_timeout_seconds)
        retries = _nonnegative_int("maximum retries", self.max_retries)
        if idle > wall:
            raise ValueError("idle timeout must not exceed the wall timeout")
        object.__setattr__(self, "lease_seconds", lease)
        object.__setattr__(self, "idle_timeout_seconds", idle)
        object.__setattr__(self, "wall_timeout_seconds", wall)
        object.__setattr__(self, "max_retries", retries)


@dataclass(frozen=True, slots=True)
class ThreadRoles:
    control: str
    worker: str
    supervisor: str
    evaluator: str
    specialist: str
    adjudicator: str | None

    def __post_init__(self) -> None:
        role_values = {
            "control": self.control,
            "worker": self.worker,
            "supervisor": self.supervisor,
            "evaluator": self.evaluator,
            "specialist": self.specialist,
        }
        if self.adjudicator is not None:
            role_values["adjudicator"] = self.adjudicator
        normalized = {
            name: _safe_id(f"{name} role", value) for name, value in role_values.items()
        }
        if len(set(normalized.values())) != len(normalized):
            raise ValueError("thread role identities must be distinct")
        for name, value in normalized.items():
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class ThreadTask:
    task_id: str
    capability: ThreadCapability
    acceptance: str
    stakes: ThreadStakes
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        task_id = _safe_id("task id", self.task_id)
        if self.capability not in {"local", "specialist", "either"}:
            raise ValueError(f"unsupported task capability: {self.capability}")
        if self.stakes not in {"normal", "high"}:
            raise ValueError(f"unsupported task stakes: {self.stakes}")
        acceptance = _safe_id("task acceptance", self.acceptance)
        if not isinstance(self.dependencies, tuple) or not all(
            isinstance(dependency, str) and bool(_SAFE_ID_RE.fullmatch(dependency))
            for dependency in self.dependencies
        ):
            raise ValueError("task dependencies must be a tuple of safe task IDs")
        if task_id in self.dependencies:
            raise ValueError("a task cannot depend on itself")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("task dependencies must not contain duplicates")
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "acceptance", acceptance)


@dataclass(frozen=True, slots=True)
class ThreadMergePolicy:
    mode: ThreadMergeMode
    integration_branch: str | None

    def __post_init__(self) -> None:
        if self.mode not in {"none", "integration-branch"}:
            raise ValueError(f"unsupported thread merge mode: {self.mode}")
        if self.mode == "integration-branch":
            if self.integration_branch is None:
                raise ValueError(
                    "integration branch is required for integration-branch mode"
                )
            object.__setattr__(
                self,
                "integration_branch",
                _nonempty("integration branch", self.integration_branch),
            )
        elif self.integration_branch not in {None, "none"}:
            raise ValueError("merge mode none must not name an integration branch")
        else:
            object.__setattr__(self, "integration_branch", None)


@dataclass(frozen=True, slots=True)
class ThreadSpecification:
    thread_id: str
    title: str
    owner: str
    budget: ThreadBudget
    supervision: ThreadSupervision
    roles: ThreadRoles
    tasks: tuple[ThreadTask, ...]
    merge_policy: ThreadMergePolicy
    semantic_digest: str
    source_path: str | None
    facts: tuple[ThreadFact, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _safe_id("thread id", self.thread_id))
        object.__setattr__(self, "title", _nonempty("thread title", self.title))
        object.__setattr__(self, "owner", _safe_id("thread owner", self.owner))
        if not isinstance(self.budget, ThreadBudget):
            raise TypeError("budget must be a ThreadBudget")
        if not isinstance(self.supervision, ThreadSupervision):
            raise TypeError("supervision must be a ThreadSupervision")
        if not isinstance(self.roles, ThreadRoles):
            raise TypeError("roles must be ThreadRoles")
        if not self.tasks or not all(
            isinstance(task, ThreadTask) for task in self.tasks
        ):
            raise ValueError("tasks must contain at least one ThreadTask")
        task_ids = tuple(task.task_id for task in self.tasks)
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("thread task IDs must be unique")
        available = set(task_ids)
        missing = sorted(
            {
                dependency
                for task in self.tasks
                for dependency in task.dependencies
                if dependency not in available
            }
        )
        if missing:
            raise ValueError(f"thread dependencies reference missing tasks: {missing}")
        if not isinstance(self.merge_policy, ThreadMergePolicy):
            raise TypeError("merge_policy must be a ThreadMergePolicy")
        if len(self.semantic_digest) != 64:
            raise ValueError("semantic digest must be a SHA-256 hex digest")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ThreadRouteDecision:
    target: ThreadRouteTarget
    allowed: bool
    reason: str
    requires_adjudication: bool

    def __post_init__(self) -> None:
        if self.target not in {"worker", "specialist", "denied"}:
            raise ValueError(f"unsupported route target: {self.target}")
        if self.allowed != (self.target != "denied"):
            raise ValueError("route target and allowed flag disagree")
        object.__setattr__(self, "reason", _nonempty("route reason", self.reason))


@dataclass(frozen=True, slots=True)
class ThreadOutcomeDecision:
    outcome: ThreadOutcome
    reason: str

    def __post_init__(self) -> None:
        if self.outcome not in {"complete", "retry", "permanent-failure"}:
            raise ValueError(f"unsupported thread outcome: {self.outcome}")
        object.__setattr__(self, "reason", _nonempty("outcome reason", self.reason))


@dataclass(frozen=True, slots=True)
class ThreadUsage:
    prompt_tokens: int
    completion_tokens: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "prompt_tokens",
            _nonnegative_int("prompt tokens", self.prompt_tokens),
        )
        object.__setattr__(
            self,
            "completion_tokens",
            _nonnegative_int("completion tokens", self.completion_tokens),
        )

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class ThreadEvaluation:
    evaluator: str
    verdict: ThreadVerdict
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evaluator",
            _safe_id("evaluator identity", self.evaluator),
        )
        if self.verdict not in {"accept", "reject", "not-required"}:
            raise ValueError(f"unsupported evaluation verdict: {self.verdict}")
        object.__setattr__(
            self,
            "reason",
            _nonempty("evaluation reason", self.reason),
        )


@dataclass(frozen=True, slots=True)
class ThreadAttemptResult:
    task_id: str
    attempt: int
    worker: str
    route: ThreadRouteTarget
    engine: Literal["petta-native", "python-callable"]
    exit_reason: ThreadExitReason
    exit_code: int
    output: str
    usage: ThreadUsage
    evaluation: ThreadEvaluation
    adjudication: ThreadEvaluation | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _safe_id("task id", self.task_id))
        object.__setattr__(self, "attempt", _positive_int("attempt", self.attempt))
        object.__setattr__(
            self,
            "worker",
            _safe_id("worker identity", self.worker),
        )
        if self.route not in {"worker", "specialist"}:
            raise ValueError(f"unsupported attempt route: {self.route}")
        if self.engine not in {"petta-native", "python-callable"}:
            raise ValueError(f"unsupported attempt engine: {self.engine}")
        _validate_process_completion(
            self.exit_reason,
            self.exit_code,
            self.output,
            output_name="attempt output",
        )
        if not isinstance(self.usage, ThreadUsage):
            raise TypeError("usage must be ThreadUsage")
        if not isinstance(self.evaluation, ThreadEvaluation):
            raise TypeError("evaluation must be ThreadEvaluation")
        if self.adjudication is not None and not isinstance(
            self.adjudication,
            ThreadEvaluation,
        ):
            raise TypeError("adjudication must be ThreadEvaluation or None")


@dataclass(frozen=True, slots=True)
class ThreadAuditEvent:
    sequence: int
    timestamp: str
    thread_id: str
    event_type: str
    actor: str
    payload: Mapping[str, Any]
    previous_hash: str
    event_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _positive_int("sequence", self.sequence))
        object.__setattr__(
            self,
            "thread_id",
            _safe_id("thread id", self.thread_id),
        )
        object.__setattr__(
            self,
            "event_type",
            _safe_id("event type", self.event_type),
        )
        object.__setattr__(self, "actor", _safe_id("actor", self.actor))
        if not isinstance(self.payload, Mapping):
            raise TypeError("audit payload must be a mapping")
        for name, value in (
            ("previous hash", self.previous_hash),
            ("event hash", self.event_hash),
        ):
            if len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ValueError(f"{name} must be a SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class ThreadProcessObservation:
    exit_reason: ThreadExitReason
    exit_code: int
    output: str
    output_bytes: int
    duration_seconds: float
    activity_events: int
    lease_renewals: int

    def __post_init__(self) -> None:
        _validate_process_completion(
            self.exit_reason,
            self.exit_code,
            self.output,
            output_name="process output",
        )
        object.__setattr__(
            self,
            "output_bytes",
            _nonnegative_int("output bytes", self.output_bytes),
        )
        if (
            isinstance(self.duration_seconds, bool)
            or not isinstance(self.duration_seconds, (int, float))
            or self.duration_seconds < 0
        ):
            raise ValueError("duration must be a nonnegative number")
        object.__setattr__(
            self,
            "activity_events",
            _nonnegative_int("activity events", self.activity_events),
        )
        object.__setattr__(
            self,
            "lease_renewals",
            _nonnegative_int("lease renewals", self.lease_renewals),
        )


@dataclass(frozen=True, slots=True)
class ThreadPettaAttempt:
    observation: ThreadProcessObservation
    evaluation: ThreadEvaluation
    adjudication: ThreadEvaluation
    outcome: ThreadOutcomeDecision

    def __post_init__(self) -> None:
        if not isinstance(self.observation, ThreadProcessObservation):
            raise TypeError("observation must be ThreadProcessObservation")
        if not isinstance(self.evaluation, ThreadEvaluation):
            raise TypeError("evaluation must be ThreadEvaluation")
        if not isinstance(self.adjudication, ThreadEvaluation):
            raise TypeError("adjudication must be ThreadEvaluation")
        if not isinstance(self.outcome, ThreadOutcomeDecision):
            raise TypeError("outcome must be ThreadOutcomeDecision")


@dataclass(frozen=True, slots=True)
class ThreadTaskExecution:
    task_id: str
    outcome: Literal["complete", "permanent-failure", "denied"]
    attempts: tuple[ThreadAttemptResult, ...]
    snapshot: Any

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _safe_id("task id", self.task_id))
        if self.outcome not in {"complete", "permanent-failure", "denied"}:
            raise ValueError(f"unsupported thread outcome: {self.outcome}")
        if not isinstance(self.attempts, tuple) or not all(
            isinstance(attempt, ThreadAttemptResult) for attempt in self.attempts
        ):
            raise TypeError("attempts must be a tuple of ThreadAttemptResult")

    def to_dict(self) -> dict[str, Any]:
        snapshot = self.snapshot
        return {
            "task_id": self.task_id,
            "outcome": self.outcome,
            "attempts": [asdict(attempt) for attempt in self.attempts],
            "snapshot": (
                snapshot.to_dict()
                if hasattr(snapshot, "to_dict")
                else asdict(snapshot)
                if hasattr(snapshot, "__dataclass_fields__")
                else snapshot
            ),
        }


@dataclass(frozen=True, slots=True)
class ThreadWorktree:
    path: str
    base_commit: str
    thread_id: str
    task_id: str
    attempt: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _nonempty("worktree path", self.path))
        if len(self.base_commit) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in self.base_commit
        ):
            raise ValueError("worktree base commit must be a full object ID")
        object.__setattr__(
            self,
            "thread_id",
            _safe_id("thread id", self.thread_id),
        )
        object.__setattr__(self, "task_id", _safe_id("task id", self.task_id))
        object.__setattr__(self, "attempt", _positive_int("attempt", self.attempt))


@dataclass(frozen=True, slots=True)
class ThreadWorktreeExecution:
    execution: ThreadTaskExecution
    worktree: ThreadWorktree
    worker_commit: str | None
    integrated_commit: str | None
    retained: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution": self.execution.to_dict(),
            "worktree": asdict(self.worktree),
            "worker_commit": self.worker_commit,
            "integrated_commit": self.integrated_commit,
            "retained": self.retained,
        }


@dataclass(frozen=True, slots=True)
class ThreadRun:
    operation: str
    value: object
    transcript: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = self.value
        serializable = cast(_Serializable, value)
        serialized = (
            serializable.to_dict()
            if callable(getattr(value, "to_dict", None))
            else asdict(cast(Any, value))
            if hasattr(value, "__dataclass_fields__")
            else value
        )
        return {
            "operation": self.operation,
            "result": serialized,
            "transcript": list(self.transcript),
        }


class _Serializable(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ThreadPlanCompilation:
    specification: ThreadSpecification
    plan: str
    snapshot: Any
    plan_path: str | None

    def to_dict(self) -> dict[str, Any]:
        snapshot = self.snapshot
        return {
            "specification": self.specification.to_dict(),
            "plan": self.plan,
            "snapshot": (
                snapshot.to_dict()
                if hasattr(snapshot, "to_dict")
                else asdict(snapshot)
                if hasattr(snapshot, "__dataclass_fields__")
                else snapshot
            ),
            "plan_path": self.plan_path,
        }


class ThreadSpecificationError(SnarsInvalidInputError):
    code = "thread_specification_error"


class ThreadProtocolError(SnarsProtocolError):
    code = "thread_protocol_error"


class ThreadExecutionError(SnarsPettaExecutionError):
    code = "thread_execution_error"


__all__ = [
    "ParsedThreadMarkdown",
    "ThreadAttemptResult",
    "ThreadAuditEvent",
    "ThreadBudget",
    "ThreadCapability",
    "ThreadEvaluation",
    "ThreadExecutionError",
    "ThreadExitReason",
    "ThreadFact",
    "ThreadMergeMode",
    "ThreadMergePolicy",
    "ThreadOutcome",
    "ThreadOutcomeDecision",
    "ThreadPettaAttempt",
    "ThreadPlanCompilation",
    "ThreadProcessObservation",
    "ThreadProtocolError",
    "ThreadRoles",
    "ThreadRouteDecision",
    "ThreadRouteTarget",
    "ThreadRun",
    "ThreadSpecification",
    "ThreadSpecificationError",
    "ThreadStakes",
    "ThreadSupervision",
    "ThreadTask",
    "ThreadTaskExecution",
    "ThreadUsage",
    "ThreadVerdict",
    "ThreadWorktree",
    "ThreadWorktreeExecution",
]

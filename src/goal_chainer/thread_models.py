"""Immutable values for MeTTa Markdown thread orchestration."""

from __future__ import annotations

import re
import uuid
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
ThreadMCPProfile = Literal["oh-my-goals"]
ThreadRouteTarget = Literal["worker", "specialist", "denied"]
ThreadRole = Literal[
    "control",
    "worker",
    "supervisor",
    "evaluator",
    "specialist",
    "adjudicator",
]
ThreadAssignmentRole = Literal["worker", "specialist", "route-selected"]
ThreadAtomspaceScope = Literal["shared", "private"]
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
_MAX_UNIX_EPOCH = 253_402_300_799
_MAX_WORKFLOW_STEPS = 12
_MAX_WORKFLOW_STEP_BYTES = 512
_MAX_WORKFLOW_BYTES = 2048
_MAX_MCP_TOOLS = 32
_AO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


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


def _ao_id(name: str, value: str) -> str:
    result = _nonempty(name, value)
    if not _AO_ID_RE.fullmatch(result):
        raise ValueError(
            f"{name} must contain 1 to 128 Agent Orchestrator ID characters"
        )
    return result


def canonical_agent_id(value: str) -> str:
    """Validate AO's lowercase canonical UUID project-agent identity."""

    result = _nonempty("Agent Orchestrator agent id", value)
    try:
        parsed = uuid.UUID(result)
    except (AttributeError, ValueError) as exc:
        raise ValueError(
            "Agent Orchestrator agent id must be a canonical UUID"
        ) from exc
    if str(parsed) != result:
        raise ValueError("Agent Orchestrator agent id must be a canonical UUID")
    return result


def _attempt_identity(
    *,
    project_id: str,
    thread_id: str,
    task_id: str,
    attempt: int,
    role: object,
    agent_key: str,
) -> tuple[str, str, str, int, Literal["worker", "specialist"], str]:
    if role not in {"worker", "specialist"}:
        raise ValueError(f"unsupported attempt role: {role}")
    return (
        _ao_id("Agent Orchestrator project id", project_id),
        _safe_id("thread id", thread_id),
        _safe_id("task id", task_id),
        _positive_int("attempt", attempt),
        cast(Literal["worker", "specialist"], role),
        _safe_id("agent key", agent_key),
    )


class _AttemptIdentityValue(Protocol):
    @property
    def project_id(self) -> str: ...

    @property
    def thread_id(self) -> str: ...

    @property
    def task_id(self) -> str: ...

    @property
    def attempt(self) -> int: ...

    @property
    def role(self) -> object: ...

    @property
    def agent_key(self) -> str: ...


def _set_attempt_identity(value: _AttemptIdentityValue) -> None:
    identity = _attempt_identity(
        project_id=value.project_id,
        thread_id=value.thread_id,
        task_id=value.task_id,
        attempt=value.attempt,
        role=value.role,
        agent_key=value.agent_key,
    )
    for name, normalized in zip(
        ("project_id", "thread_id", "task_id", "attempt", "role", "agent_key"),
        identity,
        strict=True,
    ):
        object.__setattr__(value, name, normalized)


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
    spec_version: Literal["thread-spec-v1", "thread-spec-v2"] = "thread-spec-v1"

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
        if self.spec_version not in {"thread-spec-v1", "thread-spec-v2"}:
            raise ValueError("unsupported thread specification version")


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

    def agent_for(self, role: ThreadRole) -> str | None:
        """Return the semantic agent key assigned to one role."""

        return cast(str | None, getattr(self, role))


@dataclass(frozen=True, slots=True)
class ThreadAgent:
    agent_key: str
    role: ThreadRole

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "agent_key",
            _safe_id("agent key", self.agent_key),
        )
        if self.role not in {
            "control",
            "worker",
            "supervisor",
            "evaluator",
            "specialist",
            "adjudicator",
        }:
            raise ValueError(f"unsupported agent role: {self.role}")


@dataclass(frozen=True, slots=True)
class ThreadTaskRolePolicy:
    task_id: str
    capability: ThreadCapability
    role: ThreadAssignmentRole

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _safe_id("task id", self.task_id))
        if self.capability not in {"local", "specialist", "either"}:
            raise ValueError(f"unsupported task capability: {self.capability}")
        expected = {
            "local": "worker",
            "specialist": "specialist",
            "either": "route-selected",
        }[self.capability]
        if self.role != expected:
            raise ValueError(
                f"task role {self.role} disagrees with capability {self.capability}"
            )


@dataclass(frozen=True, slots=True)
class ThreadAtomspaceLink:
    link_key: str
    scope: ThreadAtomspaceScope
    owner: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "link_key",
            _safe_id("Atomspace link key", self.link_key),
        )
        if self.scope not in {"shared", "private"}:
            raise ValueError(f"unsupported Atomspace scope: {self.scope}")
        owner = (
            _safe_id("Atomspace owner", self.owner)
            if self.scope == "private"
            else self.owner
        )
        if self.scope == "shared" and owner != "project":
            raise ValueError("shared Atomspace link must be owned by project")
        if self.scope == "private" and owner == "project":
            raise ValueError("private Atomspace link must be owned by an agent")
        object.__setattr__(self, "owner", owner)


@dataclass(frozen=True, slots=True)
class ThreadTask:
    task_id: str
    capability: ThreadCapability
    acceptance: str
    stakes: ThreadStakes
    dependencies: tuple[str, ...] = ()
    not_before_epoch: int | None = None

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
        if self.not_before_epoch is not None:
            not_before_epoch = _nonnegative_int(
                "task not-before epoch",
                self.not_before_epoch,
            )
            if not_before_epoch > _MAX_UNIX_EPOCH:
                raise ValueError(
                    "task not-before epoch must fit an RFC 3339 UTC timestamp"
                )
            object.__setattr__(
                self,
                "not_before_epoch",
                not_before_epoch,
            )
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "acceptance", acceptance)


@dataclass(frozen=True, slots=True)
class ThreadWorkflowStep:
    order: int
    instruction: str

    def __post_init__(self) -> None:
        order = _positive_int("workflow step order", self.order)
        instruction = _nonempty("workflow step instruction", self.instruction).strip()
        if len(instruction.encode("utf-8")) > _MAX_WORKFLOW_STEP_BYTES:
            raise ValueError("workflow step instruction exceeds 512 bytes")
        object.__setattr__(self, "order", order)
        object.__setattr__(self, "instruction", instruction)


@dataclass(frozen=True, slots=True)
class ThreadWorkflow:
    workflow_id: str
    steps: tuple[ThreadWorkflowStep, ...]

    def __post_init__(self) -> None:
        workflow_id = _safe_id("workflow id", self.workflow_id)
        if not isinstance(self.steps, tuple) or not all(
            isinstance(step, ThreadWorkflowStep) for step in self.steps
        ):
            raise TypeError("workflow steps must be a tuple of ThreadWorkflowStep")
        if len(self.steps) > _MAX_WORKFLOW_STEPS:
            raise ValueError("workflow must not contain more than 12 steps")
        orders = tuple(step.order for step in self.steps)
        if len(set(orders)) != len(orders):
            raise ValueError("workflow step orders must be unique")
        if orders != tuple(sorted(orders)):
            raise ValueError("workflow steps must be ordered")
        total_bytes = sum(len(step.instruction.encode("utf-8")) for step in self.steps)
        if total_bytes > _MAX_WORKFLOW_BYTES:
            raise ValueError("workflow instructions exceed 2048 bytes")
        object.__setattr__(self, "workflow_id", workflow_id)


@dataclass(frozen=True, slots=True)
class ThreadMCPAccess:
    profile: ThreadMCPProfile
    tools: tuple[str, ...]

    def __post_init__(self) -> None:
        profile = _safe_id("MCP profile", self.profile)
        if profile != "oh-my-goals":
            raise ValueError(f"unsupported MCP profile: {profile}")
        if not isinstance(self.tools, tuple) or not self.tools:
            raise ValueError("MCP tools must be a nonempty tuple")
        if len(self.tools) > _MAX_MCP_TOOLS:
            raise ValueError("MCP access must not contain more than 32 tools")
        tools = tuple(_safe_id("MCP tool", tool) for tool in self.tools)
        if len(set(tools)) != len(tools):
            raise ValueError("MCP tools must not contain duplicates")
        object.__setattr__(self, "profile", cast(ThreadMCPProfile, profile))
        object.__setattr__(self, "tools", tools)


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
    workflow: ThreadWorkflow
    mcp_access: ThreadMCPAccess
    tasks: tuple[ThreadTask, ...]
    merge_policy: ThreadMergePolicy
    semantic_digest: str
    source_path: str | None
    facts: tuple[ThreadFact, ...]
    spec_version: Literal["thread-spec-v1", "thread-spec-v2"] = "thread-spec-v1"
    project_id: str | None = None
    agents: tuple[ThreadAgent, ...] = ()
    task_role_policies: tuple[ThreadTaskRolePolicy, ...] = ()
    atomspace_links: tuple[ThreadAtomspaceLink, ...] = ()

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
        if not isinstance(self.workflow, ThreadWorkflow):
            raise TypeError("workflow must be a ThreadWorkflow")
        if not isinstance(self.mcp_access, ThreadMCPAccess):
            raise TypeError("mcp_access must be ThreadMCPAccess")
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
        if self.spec_version not in {"thread-spec-v1", "thread-spec-v2"}:
            raise ValueError("unsupported thread specification version")
        if self.spec_version == "thread-spec-v1":
            if (
                self.project_id is not None
                or self.agents
                or self.task_role_policies
                or self.atomspace_links
            ):
                raise ValueError("v1 specification cannot contain v2 identity fields")
            return
        if self.project_id is None:
            raise ValueError("v2 specification requires an Agent Orchestrator project")
        object.__setattr__(
            self,
            "project_id",
            _ao_id("Agent Orchestrator project id", self.project_id),
        )
        if not self.agents or not all(
            isinstance(agent, ThreadAgent) for agent in self.agents
        ):
            raise ValueError("v2 specification requires a typed agent registry")
        agent_key_rows = tuple(agent.agent_key for agent in self.agents)
        agent_role_rows = tuple(agent.role for agent in self.agents)
        if len(set(agent_key_rows)) != len(agent_key_rows):
            raise ValueError("v2 agent registry contains duplicate agent keys")
        if len(set(agent_role_rows)) != len(agent_role_rows):
            raise ValueError("v2 agent registry contains duplicate roles")
        if not all(
            isinstance(policy, ThreadTaskRolePolicy)
            for policy in self.task_role_policies
        ):
            raise TypeError(
                "task role policies must be ThreadTaskRolePolicy values"
            )
        if {policy.task_id for policy in self.task_role_policies} != set(task_ids):
            raise ValueError("v2 task role policies must cover every task exactly once")
        if len(self.task_role_policies) != len(task_ids):
            raise ValueError("v2 task role policies contain duplicate tasks")
        task_capabilities = {task.task_id: task.capability for task in self.tasks}
        if any(
            task_capabilities[policy.task_id] != policy.capability
            for policy in self.task_role_policies
        ):
            raise ValueError("v2 task role policies disagree with task capabilities")
        if not self.atomspace_links or not all(
            isinstance(link, ThreadAtomspaceLink)
            for link in self.atomspace_links
        ):
            raise ValueError("v2 specification requires Atomspace links")
        agent_keys = {agent.agent_key for agent in self.agents}
        role_keys = {
            value
            for value in (
                self.roles.control,
                self.roles.worker,
                self.roles.supervisor,
                self.roles.evaluator,
                self.roles.specialist,
                self.roles.adjudicator,
            )
            if value is not None
        }
        if agent_keys != role_keys:
            raise ValueError("v2 agent registry and role assignments disagree")
        expected_agents = {
            role: self.roles.agent_for(role)
            for role in (
                "control",
                "worker",
                "supervisor",
                "evaluator",
                "specialist",
                "adjudicator",
            )
            if self.roles.agent_for(role) is not None
        }
        if {
            agent.role: agent.agent_key for agent in self.agents
        } != expected_agents:
            raise ValueError("v2 agent registry roles disagree with role assignments")
        link_keys = tuple(link.link_key for link in self.atomspace_links)
        if len(set(link_keys)) != len(link_keys):
            raise ValueError("v2 Atomspace links contain duplicate keys")
        private = tuple(
            link for link in self.atomspace_links if link.scope == "private"
        )
        private_owners = {
            link.owner for link in private
        }
        shared = tuple(
            link for link in self.atomspace_links if link.scope == "shared"
        )
        if (
            len(shared) != 1
            or len(private) != len(agent_keys)
            or private_owners != agent_keys
        ):
            raise ValueError(
                "v2 requires one shared link and one private link per agent"
            )

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
class ThreadAgentBinding:
    agent_key: str
    agent_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "agent_key",
            _safe_id("agent key", self.agent_key),
        )
        if self.agent_id is not None:
            object.__setattr__(
                self,
                "agent_id",
                canonical_agent_id(self.agent_id),
            )


@dataclass(frozen=True, slots=True)
class ThreadDispatch:
    project_id: str
    thread_id: str
    task_id: str
    attempt: int
    role: Literal["worker", "specialist"]
    agent_key: str
    agent_id: str | None
    atomspace_links: tuple[ThreadAtomspaceLink, ...]
    mcp_access: ThreadMCPAccess
    workflow: ThreadWorkflow

    def __post_init__(self) -> None:
        _set_attempt_identity(self)
        if self.agent_id is not None:
            object.__setattr__(
                self,
                "agent_id",
                canonical_agent_id(self.agent_id),
            )
        if not self.atomspace_links or not all(
            isinstance(link, ThreadAtomspaceLink)
            for link in self.atomspace_links
        ):
            raise ValueError("dispatch requires logical Atomspace links")
        if not isinstance(self.mcp_access, ThreadMCPAccess):
            raise TypeError("dispatch MCP access must be ThreadMCPAccess")
        if not isinstance(self.workflow, ThreadWorkflow):
            raise TypeError("dispatch workflow must be ThreadWorkflow")


@dataclass(frozen=True, slots=True)
class ThreadSessionAttempt:
    project_id: str
    thread_id: str
    task_id: str
    attempt: int
    role: Literal["worker", "specialist"]
    agent_key: str
    agent_id: str
    agent_attempt: int
    session_id: str
    status: str
    activity: str
    is_terminated: bool
    updated_at: str

    def __post_init__(self) -> None:
        _set_attempt_identity(self)
        object.__setattr__(
            self,
            "agent_id",
            canonical_agent_id(self.agent_id),
        )
        object.__setattr__(
            self,
            "agent_attempt",
            _positive_int("Agent Orchestrator agent attempt", self.agent_attempt),
        )
        object.__setattr__(
            self,
            "session_id",
            _ao_id("Agent Orchestrator session id", self.session_id),
        )
        object.__setattr__(self, "status", _nonempty("session status", self.status))
        object.__setattr__(
            self,
            "activity",
            _nonempty("session activity", self.activity),
        )
        if not isinstance(self.is_terminated, bool):
            raise TypeError("session terminated flag must be boolean")
        object.__setattr__(
            self,
            "updated_at",
            _nonempty("session updated timestamp", self.updated_at),
        )


@dataclass(frozen=True, slots=True)
class ThreadReleaseDecision:
    allowed: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise TypeError("release allowed must be a boolean")
        object.__setattr__(self, "reason", _nonempty("release reason", self.reason))


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
    engine: Literal["host-supervised", "petta-native", "python-callable"]
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
        if self.engine not in {
            "host-supervised",
            "petta-native",
            "python-callable",
        }:
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
    project_id: str | None = None

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
        if self.project_id is not None:
            object.__setattr__(
                self,
                "project_id",
                _ao_id("Agent Orchestrator project id", self.project_id),
            )
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
    "canonical_agent_id",
    "ParsedThreadMarkdown",
    "ThreadAgent",
    "ThreadAgentBinding",
    "ThreadAttemptResult",
    "ThreadAtomspaceLink",
    "ThreadAtomspaceScope",
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
    "ThreadDispatch",
    "ThreadPlanCompilation",
    "ThreadProcessObservation",
    "ThreadProtocolError",
    "ThreadRoles",
    "ThreadRouteDecision",
    "ThreadRole",
    "ThreadReleaseDecision",
    "ThreadRouteTarget",
    "ThreadRun",
    "ThreadSpecification",
    "ThreadSpecificationError",
    "ThreadStakes",
    "ThreadSupervision",
    "ThreadTask",
    "ThreadTaskRolePolicy",
    "ThreadTaskExecution",
    "ThreadUsage",
    "ThreadSessionAttempt",
    "ThreadVerdict",
    "ThreadWorkflow",
    "ThreadWorkflowStep",
    "ThreadWorktree",
    "ThreadWorktreeExecution",
]

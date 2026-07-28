"""Loopback host adapter for Agent Orchestrator's GoalChainer UI projection."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from http.client import HTTPResponse
from typing import cast
from urllib.parse import quote, urlparse

from .directive_models import DirectiveSnapshot, directive_board_lanes
from .thread_models import ThreadExecutionError
from .thread_orchestrator import ThreadOrchestrator

PROTOCOL = "goalchainer-ui-v1"
DEFAULT_AO_URL = "http://127.0.0.1:3001"
_MAX_RESPONSE_BYTES = 1024 * 1024


def build_ui_projection(
    orchestrator: ThreadOrchestrator,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Build AO's read model from the verified GoalChainer state."""

    inspected = orchestrator.inspect()
    snapshot = orchestrator.session.snapshot().value
    if not isinstance(snapshot, DirectiveSnapshot):
        raise ThreadExecutionError("OmegaClaw returned no thread snapshot.")
    current = _current_utc(now)
    board_state = _board_states(snapshot)
    assignments = {
        assignment.task: assignment.agent for assignment in snapshot.assignments
    }
    attempts_value = inspected["attempts"]
    if not isinstance(attempts_value, dict):
        raise ThreadExecutionError("Thread attempt counts are malformed.")
    attempts = cast(dict[str, object], attempts_value)
    bindings = _session_bindings(orchestrator)
    rows_source = _ui_rows_source(
        orchestrator,
        board_state=board_state,
        assignments=assignments,
        attempts=attempts,
        bindings=bindings,
        upstream_blocked=frozenset(snapshot.status.upstream_blocked),
    )
    projection_value = orchestrator.runtime.ui_projection(
        rows_source=rows_source,
        now_epoch=int(current.timestamp()),
    ).value
    if not isinstance(projection_value, dict):
        raise ThreadExecutionError("MeTTaScript returned no thread UI projection.")
    projection = cast(dict[str, object], projection_value)
    summary = projection.get("summary")
    projected_tasks_value = projection.get("tasks")
    if not isinstance(summary, dict) or not isinstance(
        projected_tasks_value,
        tuple,
    ):
        raise ThreadExecutionError("MeTTaScript returned a malformed UI projection.")
    projected_tasks = cast(tuple[object, ...], projected_tasks_value)
    tasks = tuple(_ao_task(task) for task in projected_tasks)
    audit_events = inspected["audit_events"]
    audit_head = inspected["audit_head"]
    base: dict[str, object] = {
        "protocol": PROTOCOL,
        "threadId": orchestrator.specification.thread_id,
        "title": orchestrator.specification.title,
        "owner": orchestrator.specification.owner,
        "semanticDigest": orchestrator.specification.semantic_digest,
        "planDigest": orchestrator.session.digest(),
        "usageTokens": inspected["usage_tokens"],
        "summary": summary,
        "tasks": tasks,
        "audit": {
            "events": audit_events,
            **({"head": audit_head} if audit_head is not None else {}),
        },
    }
    revision_source = json.dumps(
        base,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return {
        **base,
        "sourceRevision": hashlib.sha256(revision_source).hexdigest(),
    }


def _ui_rows_source(
    orchestrator: ThreadOrchestrator,
    *,
    board_state: dict[str, str],
    assignments: dict[str, str],
    attempts: dict[str, object],
    bindings: dict[str, str],
    upstream_blocked: frozenset[str],
) -> str:
    codec = orchestrator.runtime.codec
    rows: list[list[object]] = []
    for task in orchestrator.specification.tasks:
        state = board_state.get(task.task_id)
        if state is None:
            raise ThreadExecutionError(
                "OmegaClaw board omitted a thread task.",
                details={"task": task.task_id},
            )
        attempt_count = attempts.get(task.task_id, 0)
        if (
            isinstance(attempt_count, bool)
            or not isinstance(attempt_count, int)
            or attempt_count < 0
        ):
            raise ThreadExecutionError(
                "Thread attempt count is malformed.",
                details={"task": task.task_id},
            )
        rows.append(
            codec.expression(
                "ui-task",
                codec.string(task.task_id),
                codec.string(task.capability),
                codec.string(task.acceptance),
                codec.string(task.stakes),
                [codec.string(dependency) for dependency in task.dependencies],
                codec.symbol(state),
                codec.symbol(
                    "True" if task.task_id in upstream_blocked else "False"
                ),
                (
                    codec.string(assignments[task.task_id])
                    if task.task_id in assignments
                    else codec.symbol("none")
                ),
                attempt_count,
                (
                    codec.string(bindings[task.task_id])
                    if task.task_id in bindings
                    else codec.symbol("none")
                ),
                (
                    task.not_before_epoch
                    if task.not_before_epoch is not None
                    else codec.symbol("none")
                ),
            )
        )
    return codec.emit(rows)


def _ao_task(task: object) -> dict[str, object]:
    if not isinstance(task, dict):
        raise ThreadExecutionError("MeTTaScript returned a malformed UI task.")
    task = cast(dict[str, object], task)
    state = task.get("state")
    not_before = task.get("notBeforeEpoch")
    release_reason = task.get("releaseReason")
    dependencies_value = task.get("dependencies")
    if not isinstance(dependencies_value, tuple):
        raise ThreadExecutionError(
            "MeTTaScript returned malformed UI task dependencies."
        )
    dependencies = cast(tuple[object, ...], dependencies_value)
    if not all(
        isinstance(dependency, str) for dependency in dependencies
    ):
        raise ThreadExecutionError(
            "MeTTaScript returned malformed UI task dependencies."
        )
    projected: dict[str, object] = {
        "id": task["id"],
        "capability": task["capability"],
        "acceptance": task["acceptance"],
        "stakes": task["stakes"],
        "dependencies": [
            dependency
            for dependency in dependencies
            if isinstance(dependency, str)
        ],
        "state": state,
        "upstreamBlocked": task["upstreamBlocked"],
        "assignedAgent": task["assignedAgent"],
        "attempts": task["attempts"],
        "sessionId": task["sessionId"],
    }
    if state == "scheduled" and isinstance(not_before, int):
        projected["scheduledAt"] = (
            datetime.fromtimestamp(not_before, UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )
    if isinstance(release_reason, str) and release_reason:
        projected["releaseReason"] = release_reason
    return projected


def sync_ui_projection(
    orchestrator: ThreadOrchestrator,
    *,
    project_id: str,
    ao_url: str = DEFAULT_AO_URL,
    timeout: float = 10.0,
    now: datetime | None = None,
) -> dict[str, object]:
    """PUT one projection into AO's loopback daemon."""

    projection = build_ui_projection(orchestrator, now=now)
    response = _request_json(
        "PUT",
        ao_url,
        "projects",
        _project_id(project_id),
        "goalchainer",
        body=projection,
        timeout=timeout,
    )
    return {"projection": projection, "agent_orchestrator": response}


def disconnect_ui_projection(
    *,
    project_id: str,
    ao_url: str = DEFAULT_AO_URL,
    timeout: float = 10.0,
) -> dict[str, object]:
    """Remove AO's cached projection without changing GoalChainer state."""

    return _request_json(
        "DELETE",
        ao_url,
        "projects",
        _project_id(project_id),
        "goalchainer",
        timeout=timeout,
    )


def observe_agent_orchestrator_sessions(
    orchestrator: ThreadOrchestrator,
    *,
    project_id: str,
    ao_url: str = DEFAULT_AO_URL,
    timeout: float = 10.0,
) -> dict[str, object]:
    """Copy bound AO session readings into the GoalChainer audit chain."""

    project = _project_id(project_id)
    observations: list[dict[str, object]] = []
    for task_id, session_id in sorted(_session_bindings(orchestrator).items()):
        response = _request_json(
            "GET",
            ao_url,
            "sessions",
            session_id,
            timeout=timeout,
        )
        observation = _session_observation(
            response,
            project_id=project,
            session_id=session_id,
        )
        status = observation["status"]
        activity = observation["activity"]
        is_terminated = observation["is_terminated"]
        updated_at = observation["updated_at"]
        if (
            not isinstance(status, str)
            or not isinstance(activity, str)
            or not isinstance(is_terminated, bool)
            or not isinstance(updated_at, str)
        ):
            raise ThreadExecutionError(
                "Agent Orchestrator session observation is malformed."
            )
        observations.append(
            orchestrator.record_agent_orchestrator_observation(
                task_id,
                session_id=session_id,
                status=status,
                activity=activity,
                is_terminated=is_terminated,
                updated_at=updated_at,
            )
        )
    return {
        "observed": observations,
        "created": sum(
            1 for observation in observations if observation["created"] is True
        ),
    }


def watch_agent_orchestrator(
    orchestrator: ThreadOrchestrator,
    *,
    project_id: str,
    ao_url: str = DEFAULT_AO_URL,
    timeout: float = 10.0,
    interval_seconds: float = 5.0,
    cycles: int | None = None,
    local_iterations: int = 0,
    hard: bool = False,
) -> dict[str, object]:
    """Observe sessions and dispatch newly released tasks until stopped."""

    interval = _positive_finite(
        interval_seconds,
        "Agent Orchestrator watch interval must be positive and finite.",
    )
    if cycles is not None and (
        isinstance(cycles, bool) or cycles < 1
    ):
        raise ThreadExecutionError(
            "Agent Orchestrator watch cycles must be positive."
        )
    completed = 0
    observed = 0
    dispatched = 0
    last: dict[str, object] | None = None
    interrupted = False
    try:
        while cycles is None or completed < cycles:
            observation = observe_agent_orchestrator_sessions(
                orchestrator,
                project_id=project_id,
                ao_url=ao_url,
                timeout=timeout,
            )
            dispatch = dispatch_due_tasks(
                orchestrator,
                project_id=project_id,
                ao_url=ao_url,
                timeout=timeout,
                local_iterations=local_iterations,
                hard=hard,
            )
            observed_rows = observation["observed"]
            dispatched_rows = dispatch["dispatched"]
            if not isinstance(observed_rows, list) or not isinstance(
                dispatched_rows,
                list,
            ):
                raise ThreadExecutionError(
                    "Agent Orchestrator watch cycle is malformed."
                )
            completed += 1
            observed += len(cast(list[object], observed_rows))
            dispatched += len(cast(list[object], dispatched_rows))
            last = {
                "observation": observation,
                "dispatch": dispatch,
            }
            if cycles is None or completed < cycles:
                time.sleep(interval)
    except KeyboardInterrupt:
        interrupted = True
    return {
        "cycles": completed,
        "observed": observed,
        "dispatched": dispatched,
        "interrupted": interrupted,
        "last": last,
    }


def dispatch_due_tasks(
    orchestrator: ThreadOrchestrator,
    *,
    project_id: str,
    ao_url: str = DEFAULT_AO_URL,
    timeout: float = 10.0,
    now: datetime | None = None,
    local_iterations: int = 0,
    hard: bool = False,
) -> dict[str, object]:
    """Start each MeTTa-released task once and refresh AO's board."""

    project = _project_id(project_id)
    current = _current_utc(now)
    projection = build_ui_projection(orchestrator, now=current)
    pending = _pending_agent_orchestrator_attempts(orchestrator)
    dispatched: list[dict[str, object]] = []
    tasks_value = projection["tasks"]
    if not isinstance(tasks_value, tuple):
        raise ThreadExecutionError("GoalChainer UI tasks are malformed.")
    tasks = cast(tuple[object, ...], tasks_value)
    for task in tasks:
        if not isinstance(task, dict):
            raise ThreadExecutionError("GoalChainer UI task is malformed.")
        task = cast(dict[str, object], task)
        if task.get("sessionId"):
            continue
        task_id = task.get("id")
        state = task.get("state")
        if not isinstance(task_id, str):
            raise ThreadExecutionError("GoalChainer UI task id is malformed.")
        started_here = False
        if state == "ready":
            route = orchestrator.route(
                task_id,
                local_iterations=local_iterations,
                hard=hard,
            )
            if not route.allowed:
                dispatched.append(
                    {
                        "task": task_id,
                        "status": "denied",
                        "reason": route.reason,
                    }
                )
                continue
            attempts = task.get("attempts")
            if isinstance(attempts, bool) or not isinstance(attempts, int):
                raise ThreadExecutionError(
                    "GoalChainer UI attempt count is malformed."
                )
            attempt = attempts + 1
            worker = (
                orchestrator.specification.roles.specialist
                if route.target == "specialist"
                else orchestrator.specification.roles.worker
            )
            _ = orchestrator.reserve_agent_orchestrator_attempt(
                task_id,
                attempt=attempt,
                worker=worker,
                now=current,
            )
            started_here = True
        elif state == "in-progress" and task_id in pending:
            attempt, worker = pending[task_id]
        else:
            continue

        try:
            response = _request_json(
                "POST",
                ao_url,
                "sessions",
                body={
                    "projectId": project,
                    "sourceTaskId": _external_source_task_id(
                        orchestrator.specification.thread_id,
                        task_id,
                        attempt,
                    ),
                    "kind": "worker",
                    "prompt": _task_prompt(orchestrator, task),
                    "mcpProfile": orchestrator.specification.mcp_access.profile,
                    "displayName": task_id[:20],
                },
                timeout=timeout,
            )
            session_id, created = _spawn_result(response)
            binding = orchestrator.bind_agent_orchestrator_session(
                task_id,
                attempt=attempt,
                session_id=session_id,
            )
        except Exception as exc:
            if started_here:
                _ = orchestrator.abandon_agent_orchestrator_attempt(
                    task_id,
                    attempt=attempt,
                    reason=f"{type(exc).__name__}: {exc}",
                )
            raise
        dispatched.append(
            {
                "task": task_id,
                "attempt": attempt,
                "sessionId": session_id,
                "created": created,
                "bindingCreated": binding["created"],
                "status": "dispatched",
            }
        )

    synchronized = sync_ui_projection(
        orchestrator,
        project_id=project,
        ao_url=ao_url,
        timeout=timeout,
        now=current,
    )
    return {
        "dispatched": dispatched,
        "projection": synchronized["projection"],
        "agent_orchestrator": synchronized["agent_orchestrator"],
    }


def _board_states(snapshot: DirectiveSnapshot) -> dict[str, str]:
    states: dict[str, str] = {}
    for state, task_ids in directive_board_lanes(snapshot.board):
        for task_id in task_ids:
            if task_id in states:
                raise ThreadExecutionError(
                    "OmegaClaw board placed a task in multiple states.",
                    details={"task": task_id},
                )
            states[task_id] = state
    return states


def _current_utc(now: datetime | None) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ThreadExecutionError(
            "GoalChainer UI clock must be timezone-aware."
        )
    return current.astimezone(UTC)


def _session_bindings(orchestrator: ThreadOrchestrator) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for event in orchestrator.audit.verify():
        if event.event_type != "ao-session-bound":
            continue
        task = event.payload.get("task")
        session_id = event.payload.get("session_id")
        if isinstance(task, str) and isinstance(session_id, str):
            bindings[task] = session_id
    return bindings


def _request_json(
    method: str,
    ao_url: str,
    *path_segments: str,
    body: dict[str, object] | None = None,
    timeout: object,
) -> dict[str, object]:
    base = _loopback_url(ao_url)
    request_timeout = _positive_finite(
        timeout,
        "Agent Orchestrator timeout must be a positive finite number.",
    )
    if not path_segments or not all(path_segments):
        raise ThreadExecutionError("Agent Orchestrator API path is invalid.")
    path = "/".join(quote(segment, safe="") for segment in path_segments)
    url = f"{base}/api/v1/{path}"
    encoded = (
        json.dumps(
            body,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        if body is not None
        else None
    )
    request = urllib.request.Request(
        url,
        data=encoded,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with cast(
            HTTPResponse,
            urllib.request.urlopen(request, timeout=request_timeout),
        ) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raw = exc.read(_MAX_RESPONSE_BYTES + 1)
        details = _decode_error(raw)
        raise ThreadExecutionError(
            "Agent Orchestrator rejected the GoalChainer projection.",
            details={
                "status": exc.code,
                "code": details.get("code"),
                "message": details.get("message"),
            },
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ThreadExecutionError(
            "Agent Orchestrator is unavailable.",
            details={"url": base, "error": str(exc)},
        ) from exc
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ThreadExecutionError("Agent Orchestrator response exceeds 1 MiB.")
    try:
        decoded = cast(object, json.loads(raw))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ThreadExecutionError(
            "Agent Orchestrator returned invalid JSON."
        ) from exc
    if not isinstance(decoded, dict):
        raise ThreadExecutionError(
            "Agent Orchestrator returned a non-object response."
        )
    return cast(dict[str, object], decoded)


def _loopback_url(value: object) -> str:
    if not isinstance(value, str):
        raise ThreadExecutionError(
            "Agent Orchestrator URL must be an HTTP loopback origin."
        )
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ThreadExecutionError(
            "Agent Orchestrator URL must be an HTTP loopback origin."
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise ThreadExecutionError(
            "Agent Orchestrator URL has an invalid port."
        ) from exc
    if port is None:
        raise ThreadExecutionError(
            "Agent Orchestrator URL must include a port."
        )
    return value.rstrip("/")


def _project_id(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
        value,
    ):
        raise ThreadExecutionError("Agent Orchestrator project id is invalid.")
    return value


def _pending_agent_orchestrator_attempts(
    orchestrator: ThreadOrchestrator,
) -> dict[str, tuple[int, str]]:
    reservations: dict[tuple[str, int], str] = {}
    for event in orchestrator.audit.verify():
        task = event.payload.get("task")
        attempt = event.payload.get("attempt")
        worker = event.payload.get("worker")
        if (
            isinstance(task, str)
            and isinstance(attempt, int)
            and not isinstance(attempt, bool)
        ):
            key = (task, attempt)
            if (
                event.event_type == "ao-dispatch-reserved"
                and event.payload.get("engine") == "agent-orchestrator"
                and isinstance(worker, str)
            ):
                reservations[key] = worker
            elif event.event_type in {"ao-session-bound", "ao-dispatch-failed"}:
                _ = reservations.pop(key, None)
    pending: dict[str, tuple[int, str]] = {}
    for (task, attempt), worker in reservations.items():
        pending[task] = (attempt, worker)
    return pending


def _external_source_task_id(
    thread_id: str,
    task_id: str,
    attempt: object,
) -> str:
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ThreadExecutionError(
            "Agent Orchestrator source attempt must be positive."
        )
    readable = f"goalchainer:{thread_id}:{task_id}:{attempt}"
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", readable):
        return readable
    digest = hashlib.sha256(
        f"{thread_id}\0{task_id}\0{attempt}".encode("utf-8")
    ).hexdigest()
    return f"goalchainer:{digest}"


def _task_prompt(
    orchestrator: ThreadOrchestrator,
    task: dict[str, object],
) -> str:
    dependencies = task.get("dependencies")
    dependency_values = (
        cast(list[object], dependencies) if isinstance(dependencies, list) else []
    )
    dependency_text = ", ".join(
        value for value in dependency_values if isinstance(value, str)
    )
    workflow = orchestrator.specification.workflow
    mcp_access = orchestrator.specification.mcp_access
    workflow_steps = "\n".join(
        f"{index}. {step.instruction}"
        for index, step in enumerate(workflow.steps, start=1)
    )
    prompt = "\n".join(
        (
            f"System workflow: {workflow.workflow_id}",
            workflow_steps,
            "",
            f"MCP profile: {mcp_access.profile}",
            "Available MCP tools: " + ", ".join(mcp_access.tools),
            "Use the Oh My Goals memory loop before planning consequential work.",
            "",
            "Task contract",
            f"Thread: {orchestrator.specification.title}",
            f"Task: {task['id']}",
            f"Acceptance: {task['acceptance']}",
            f"Dependencies: {dependency_text or 'none'}",
            "",
            "Work only on this released GoalChainer task.",
            "Do not claim completion in GoalChainer.",
            "The GoalChainer evaluator decides completion after your session.",
        )
    )
    if len(prompt.encode("utf-8")) > 4096:
        raise ThreadExecutionError(
            "Agent Orchestrator task prompt exceeds 4096 bytes.",
            details={"task": task.get("id")},
        )
    return prompt


def _spawn_result(response: dict[str, object]) -> tuple[str, bool]:
    session_value = response.get("session")
    created = response.get("created")
    session = (
        cast(dict[str, object], session_value)
        if isinstance(session_value, dict)
        else {}
    )
    session_id = session.get("id")
    if (
        not isinstance(session_id, str)
        or not session_id
        or not isinstance(created, bool)
    ):
        raise ThreadExecutionError(
            "Agent Orchestrator returned a malformed spawn response."
        )
    return session_id, created


def _session_observation(
    response: dict[str, object],
    *,
    project_id: str,
    session_id: str,
) -> dict[str, object]:
    session_value = response.get("session")
    if not isinstance(session_value, dict):
        raise ThreadExecutionError(
            "Agent Orchestrator returned a malformed session response."
        )
    session = cast(dict[str, object], session_value)
    activity_value = session.get("activity")
    if not isinstance(activity_value, dict):
        raise ThreadExecutionError(
            "Agent Orchestrator returned malformed session activity."
        )
    activity = cast(dict[str, object], activity_value).get("state")
    status = session.get("status")
    terminated = session.get("isTerminated")
    updated_at = session.get("updatedAt")
    if (
        session.get("id") != session_id
        or session.get("projectId") != project_id
        or not isinstance(status, str)
        or not isinstance(activity, str)
        or not isinstance(terminated, bool)
        or not isinstance(updated_at, str)
    ):
        raise ThreadExecutionError(
            "Agent Orchestrator session identity or state is malformed.",
            details={"session_id": session_id},
        )
    return {
        "status": status,
        "activity": activity,
        "is_terminated": terminated,
        "updated_at": updated_at,
    }


def _positive_finite(value: object, message: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ThreadExecutionError(message)
    return float(value)


def _decode_error(raw: bytes) -> dict[str, object]:
    if len(raw) > _MAX_RESPONSE_BYTES:
        return {}
    try:
        decoded = cast(object, json.loads(raw))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return cast(dict[str, object], decoded) if isinstance(decoded, dict) else {}


__all__ = [
    "DEFAULT_AO_URL",
    "PROTOCOL",
    "build_ui_projection",
    "dispatch_due_tasks",
    "disconnect_ui_projection",
    "observe_agent_orchestrator_sessions",
    "sync_ui_projection",
    "watch_agent_orchestrator",
]

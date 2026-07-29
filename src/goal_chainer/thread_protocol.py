"""Parse the versioned MeTTa protocol for thread orchestration."""

from __future__ import annotations

import base64
from collections.abc import Iterable
from typing import Any, Literal, cast

from .sexpr_protocol import (
    atom_to_python,
    parse_versioned_output,
    partition_protocol_output,
)
from .thread_models import (
    ParsedThreadMarkdown,
    ThreadAgent,
    ThreadAtomspaceLink,
    ThreadBudget,
    ThreadCapability,
    ThreadEvaluation,
    ThreadExecutionError,
    ThreadExitReason,
    ThreadMergeMode,
    ThreadMergePolicy,
    ThreadMCPAccess,
    ThreadMCPProfile,
    ThreadDispatch,
    ThreadOutcome,
    ThreadOutcomeDecision,
    ThreadPettaAttempt,
    ThreadProcessObservation,
    ThreadProtocolError,
    ThreadRoles,
    ThreadReleaseDecision,
    ThreadRouteDecision,
    ThreadRouteTarget,
    ThreadRun,
    ThreadSessionAttempt,
    ThreadSpecification,
    ThreadSpecificationError,
    ThreadStakes,
    ThreadSupervision,
    ThreadTask,
    ThreadTaskRolePolicy,
    ThreadVerdict,
    ThreadWorkflow,
    ThreadWorkflowStep,
)

PROTOCOL_VERSION_V1 = "goalchainer-thread-v1"
PROTOCOL_VERSION_V2 = "goalchainer-thread-v2"
PROTOCOL_VERSION = PROTOCOL_VERSION_V1


def parse_thread_output(
    lines: Iterable[str],
    codec: Any,
    *,
    expected_operation: str,
    parsed_markdown: ParsedThreadMarkdown | None = None,
    source_path: str | None = None,
    protocol_version: str = PROTOCOL_VERSION_V1,
) -> ThreadRun:
    """Parse exactly one thread protocol record."""

    output = tuple(lines)
    envelope = parse_versioned_output(
        output,
        codec,
        version=protocol_version,
        record_prefix="goalchainer-thread-",
        protocol_name="thread",
        protocol_error=ThreadProtocolError,
        execution_error=ThreadExecutionError,
        expected_operation=expected_operation,
    )
    payload = atom_to_python(envelope.payload, codec)
    try:
        if envelope.operation == "compile":
            value = _parse_compilation(
                payload,
                parsed_markdown,
                protocol_version=protocol_version,
            )
        elif envelope.operation == "plan":
            value = _parse_plan(payload)
        elif envelope.operation == "route":
            value = _parse_route(payload)
        elif envelope.operation == "release":
            value = _parse_release(payload)
        elif envelope.operation == "ui":
            value = (
                _parse_ui_v2(payload)
                if protocol_version == PROTOCOL_VERSION_V2
                else _parse_ui(payload)
            )
        elif envelope.operation == "dispatch":
            _require_v2(protocol_version, "dispatch")
            value = _parse_dispatch(payload)
        elif envelope.operation == "session":
            _require_v2(protocol_version, "session")
            value = _parse_session(payload)
        elif envelope.operation == "outcome":
            value = _parse_outcome(payload)
        elif envelope.operation == "markdown":
            value = _parse_markdown(payload, source_path=source_path)
        elif envelope.operation == "status":
            value = _parse_status(payload)
        elif envelope.operation == "attempt":
            value = _parse_attempt(payload)
        else:
            raise ThreadProtocolError(
                f"Unsupported thread operation: {envelope.operation}"
            )
    except (ThreadProtocolError, ThreadSpecificationError):
        raise
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise ThreadProtocolError(
            "Thread protocol payload is malformed.",
            details={"operation": envelope.operation, "error": str(exc)},
        ) from exc
    _, human_output = partition_protocol_output(output, "goalchainer-thread-")
    transcript = tuple(
        line for line in human_output if line not in {"true", "True", "()"}
    )
    return ThreadRun(envelope.operation, value, transcript)


def _parse_compilation(
    payload: Any,
    parsed_markdown: ParsedThreadMarkdown | None,
    *,
    protocol_version: str,
) -> ThreadSpecification:
    if parsed_markdown is None:
        raise ThreadProtocolError(
            "Compilation parsing requires the source Markdown facts."
        )
    expected_spec_version = (
        "thread-spec-v2"
        if protocol_version == PROTOCOL_VERSION_V2
        else "thread-spec-v1"
    )
    if parsed_markdown.spec_version != expected_spec_version:
        raise ThreadProtocolError(
            "Thread Markdown and compilation protocol versions disagree.",
            details={
                "markdown": parsed_markdown.spec_version,
                "protocol": protocol_version,
            },
        )
    row = _tag(payload, "compilation")
    fields = _fields(row[1:])
    valid = _boolean(_single(fields["valid"]))
    errors = tuple(_text(error) for error in _collection(fields["errors"], 1))
    if not valid:
        rendered = ", ".join(errors) if errors else "unknown-validation-error"
        raise ThreadSpecificationError(
            f"MeTTa thread specification validation failed: {rendered}.",
            details={"errors": list(errors)},
        )
    if errors:
        raise ThreadProtocolError(
            "Valid thread compilation returned validation errors.",
            details={"errors": list(errors)},
        )
    thread = _tag(fields["thread"], "thread")
    _arity(thread, 4)
    budget = _tag(fields["budget"], "budget")
    _arity(budget, 4)
    supervision = _tag(fields["supervision"], "supervision")
    _arity(supervision, 5)
    roles = _tag(fields["roles"], "roles")
    _arity(roles, 7)
    agents: tuple[ThreadAgent, ...] = ()
    task_role_policies: tuple[ThreadTaskRolePolicy, ...] = ()
    atomspace_links: tuple[ThreadAtomspaceLink, ...] = ()
    project_id: str | None = None
    spec_version = "thread-spec-v1"
    if protocol_version == PROTOCOL_VERSION_V2:
        spec_version = "thread-spec-v2"
        project = _tag(fields["project"], "project")
        _arity(project, 2)
        project_id = _text(project[1])
        agents = tuple(
            _parse_agent(agent)
            for agent in _collection(fields["agents"], 1)
        )
        task_role_policies = tuple(
            _parse_task_role_policy(policy)
            for policy in _collection(fields["task-role-policies"], 1)
        )
        atomspace_links = tuple(
            _parse_atomspace_link(link)
            for link in _collection(fields["atomspace-links"], 1)
        )
    workflow = _parse_workflow(fields["workflow"])
    mcp_access = _parse_mcp_access(fields["mcp-access"])
    tasks = tuple(_parse_task(task) for task in _collection(fields["tasks"], 1))
    merge = _tag(fields["merge-policy"], "merge-policy")
    _arity(merge, 3)
    mode = _text(merge[1])
    branch = _text(merge[2])
    return ThreadSpecification(
        thread_id=_text(thread[1]),
        title=_text(thread[2]),
        owner=_text(thread[3]),
        budget=ThreadBudget(
            ceiling_tokens=_integer(budget[1]),
            soft_threshold_tokens=_integer(budget[2]),
            min_local_iterations=_integer(budget[3]),
        ),
        supervision=ThreadSupervision(
            lease_seconds=_integer(supervision[1]),
            idle_timeout_seconds=_integer(supervision[2]),
            wall_timeout_seconds=_integer(supervision[3]),
            max_retries=_integer(supervision[4]),
        ),
        roles=ThreadRoles(
            control=_text(roles[1]),
            worker=_text(roles[2]),
            supervisor=_text(roles[3]),
            evaluator=_text(roles[4]),
            specialist=_text(roles[5]),
            adjudicator=None if roles[6] == "none" else _text(roles[6]),
        ),
        workflow=workflow,
        mcp_access=mcp_access,
        tasks=tasks,
        merge_policy=ThreadMergePolicy(
            mode=cast(ThreadMergeMode, mode),
            integration_branch=None if branch == "none" else branch,
        ),
        semantic_digest=parsed_markdown.semantic_digest,
        source_path=parsed_markdown.source_path,
        facts=parsed_markdown.facts,
        spec_version=cast(Any, spec_version),
        project_id=project_id,
        agents=agents,
        task_role_policies=task_role_policies,
        atomspace_links=atomspace_links,
    )


def _parse_agent(payload: Any) -> ThreadAgent:
    row = _tag(payload, "agent")
    _arity(row, 3)
    return ThreadAgent(
        agent_key=_text(row[1]),
        role=cast(Any, _text(row[2])),
    )


def _parse_task_role_policy(payload: Any) -> ThreadTaskRolePolicy:
    row = _tag(payload, "task-role-policy")
    _arity(row, 4)
    return ThreadTaskRolePolicy(
        task_id=_text(row[1]),
        capability=cast(ThreadCapability, _text(row[2])),
        role=cast(Any, _text(row[3])),
    )


def _parse_atomspace_link(payload: Any) -> ThreadAtomspaceLink:
    row = _tag(payload, "atomspace-link")
    _arity(row, 4)
    return ThreadAtomspaceLink(
        link_key=_text(row[1]),
        scope=cast(Any, _text(row[2])),
        owner=_text(row[3]),
    )


def _parse_workflow(payload: Any) -> ThreadWorkflow:
    row = _tag(payload, "workflow")
    _arity(row, 3)
    steps: list[ThreadWorkflowStep] = []
    for step in _expression(row[2]):
        step_row = _tag(step, "step")
        _arity(step_row, 3)
        steps.append(
            ThreadWorkflowStep(
                order=_integer(step_row[1]),
                instruction=_text(step_row[2]),
            )
        )
    return ThreadWorkflow(workflow_id=_text(row[1]), steps=tuple(steps))


def _parse_mcp_access(payload: Any) -> ThreadMCPAccess:
    row = _tag(payload, "mcp-access")
    _arity(row, 3)
    return ThreadMCPAccess(
        profile=cast(ThreadMCPProfile, _text(row[1])),
        tools=tuple(_text(tool) for tool in _expression(row[2])),
    )


def _parse_task(payload: Any) -> ThreadTask:
    row = _tag(payload, "task")
    _arity(row, 7)
    depends = _tag(row[5], "depends")
    _arity(depends, 2)
    not_before = _tag(row[6], "not-before")
    _arity(not_before, 2)
    return ThreadTask(
        task_id=_text(row[1]),
        capability=cast(ThreadCapability, _text(row[2])),
        acceptance=_text(row[3]),
        stakes=cast(ThreadStakes, _text(row[4])),
        dependencies=tuple(_text(value) for value in _expression(depends[1])),
        not_before_epoch=(
            None
            if not_before[1] == "none"
            else _integer(not_before[1])
        ),
    )


def _parse_plan(payload: Any) -> str:
    row = _tag(payload, "plan")
    fields = _fields(row[1:])
    lines = tuple(_text(line) for line in _collection(fields["lines"], 1))
    if not lines:
        raise ThreadProtocolError("Thread plan contains no directive atoms.")
    return "\n".join(lines) + "\n"


def _parse_route(payload: Any) -> ThreadRouteDecision:
    row = _tag(payload, "route")
    _arity(row, 5)
    return ThreadRouteDecision(
        target=cast(ThreadRouteTarget, _text(row[1])),
        allowed=_boolean(row[2]),
        reason=_text(row[3]),
        requires_adjudication=_boolean(row[4]),
    )


def _parse_release(payload: Any) -> ThreadReleaseDecision:
    row = _tag(payload, "release")
    _arity(row, 3)
    return ThreadReleaseDecision(
        allowed=_boolean(row[1]),
        reason=_text(row[2]),
    )


def _parse_dispatch(payload: Any) -> ThreadDispatch:
    row = _tag(payload, "dispatch")
    fields = _fields(row[1:])
    _require_valid_record(fields, "dispatch")
    fields = _exact_fields(
        row[1:],
        {
            "valid",
            "errors",
            "project",
            "attempt-key",
            "assignment",
            "atomspace-links",
            "mcp-access",
            "workflow",
        },
    )
    (
        project_id,
        thread_id,
        task_id,
        attempt,
        role,
        agent_key,
        raw_agent_id,
    ) = _parse_attempt_identity(
        fields["project"],
        fields["attempt-key"],
        fields["assignment"],
    )
    agent_id = None if raw_agent_id == "none" else raw_agent_id
    return ThreadDispatch(
        project_id=project_id,
        thread_id=thread_id,
        task_id=task_id,
        attempt=attempt,
        role=role,
        agent_key=agent_key,
        agent_id=agent_id,
        atomspace_links=tuple(
            _parse_atomspace_link(link)
            for link in _collection(fields["atomspace-links"], 1)
        ),
        mcp_access=_parse_mcp_access(fields["mcp-access"]),
        workflow=_parse_workflow(fields["workflow"]),
    )


def _parse_session(payload: Any) -> ThreadSessionAttempt:
    row = _tag(payload, "session")
    fields = _fields(row[1:])
    valid = _boolean(_single(fields["valid"]))
    errors = tuple(_text(error) for error in _collection(fields["errors"], 1))
    if not valid:
        raise ThreadProtocolError(
            "MeTTa session observation validation failed.",
            details={"errors": list(errors)},
        )
    _exact_fields(
        row[1:],
        {"valid", "errors", "session-attempt"},
    )
    attempt = _tag(fields["session-attempt"], "session-attempt")
    attempt_fields = _exact_fields(
        attempt[1:],
        {
            "attempt-key",
            "project",
            "assignment",
            "agent-attempt",
            "session-id",
            "state",
            "updated-at",
        },
    )
    (
        project_id,
        thread_id,
        task_id,
        attempt_number,
        role,
        agent_key,
        agent_id,
    ) = _parse_attempt_identity(
        attempt_fields["project"],
        attempt_fields["attempt-key"],
        attempt_fields["assignment"],
    )
    agent_attempt = _tag(attempt_fields["agent-attempt"], "agent-attempt")
    _arity(agent_attempt, 2)
    session_id = _tag(attempt_fields["session-id"], "session-id")
    _arity(session_id, 2)
    state = _tag(attempt_fields["state"], "state")
    _arity(state, 4)
    updated = _tag(attempt_fields["updated-at"], "updated-at")
    _arity(updated, 2)
    return ThreadSessionAttempt(
        project_id=project_id,
        thread_id=thread_id,
        task_id=task_id,
        attempt=attempt_number,
        role=role,
        agent_key=agent_key,
        agent_id=agent_id,
        agent_attempt=_integer(agent_attempt[1]),
        session_id=_text(session_id[1]),
        status=_text(state[1]),
        activity=_text(state[2]),
        is_terminated=_boolean(state[3]),
        updated_at=_text(updated[1]),
    )


def _parse_ui(payload: Any) -> dict[str, object]:
    row = _tag(payload, "ui-projection")
    _arity(row, 3)
    summary = _tag(row[1], "summary")
    _arity(summary, 9)
    task_collection = _tag(row[2], "tasks")
    _arity(task_collection, 2)
    tasks = tuple(_parse_ui_task(value) for value in _expression(task_collection[1]))
    _require_unique_ui_tasks(tasks)
    counts = _validated_summary(summary, tasks)
    return {
        "summary": counts,
        "tasks": tasks,
    }


def _parse_ui_v2(payload: Any) -> dict[str, object]:
    row = _tag(payload, "ui-projection-v2")
    fields = _exact_fields(
        row[1:],
        {"project", "agents", "summary", "tasks"},
    )
    project = _tag(fields["project"], "project")
    _arity(project, 2)
    agents = tuple(
        _parse_ui_agent(value)
        for value in _collection(fields["agents"], 1)
    )
    if len({cast(str, agent["agentKey"]) for agent in agents}) != len(agents):
        raise ThreadProtocolError("Thread UI projection contains duplicate agents.")
    summary = _tag(fields["summary"], "summary")
    _arity(summary, 9)
    tasks = tuple(
        _parse_ui_task_v2(value)
        for value in _collection(fields["tasks"], 1)
    )
    _require_unique_ui_tasks(tasks)
    counts = _validated_summary(summary, tasks)
    return {
        "projectId": _text(project[1]),
        "agents": agents,
        "summary": counts,
        "tasks": tasks,
    }


def _parse_ui_agent(payload: Any) -> dict[str, object]:
    row = _tag(payload, "agent")
    _arity(row, 4)
    return {
        "agentKey": _text(row[1]),
        "role": _text(row[2]),
        "agentId": "" if row[3] == "none" else _text(row[3]),
    }


def _parse_attempt_identity(
    project_value: Any,
    attempt_key_value: Any,
    assignment_value: Any,
) -> tuple[
    str,
    str,
    str,
    int,
    Literal["worker", "specialist"],
    str,
    str,
]:
    project = _tag(project_value, "project")
    _arity(project, 2)
    attempt_key = _tag(attempt_key_value, "attempt-key")
    _arity(attempt_key, 4)
    assignment = _tag(assignment_value, "assignment")
    _arity(assignment, 4)
    role = _text(assignment[1])
    if role not in {"worker", "specialist"}:
        raise ThreadProtocolError("Thread attempt assignment role is malformed.")
    return (
        _text(project[1]),
        _text(attempt_key[1]),
        _text(attempt_key[2]),
        _integer(attempt_key[3]),
        cast(Literal["worker", "specialist"], role),
        _text(assignment[2]),
        _text(assignment[3]),
    )


def _require_unique_ui_tasks(tasks: tuple[dict[str, object], ...]) -> None:
    task_ids = tuple(cast(str, task["id"]) for task in tasks)
    if len(task_ids) != len(set(task_ids)):
        raise ThreadProtocolError("Thread UI projection contains duplicate tasks.")


def _parse_ui_task_v2(payload: Any) -> dict[str, object]:
    row = _tag(payload, "ui-task-v2")
    fields = _exact_fields(
        row[1:],
        {"task", "execution", "assignment", "attempts", "atomspace-links"},
    )
    task = _tag(fields["task"], "task")
    _arity(task, 6)
    execution = _tag(fields["execution"], "execution")
    _arity(execution, 5)
    assignment = _tag(fields["assignment"], "assignment")
    _arity(assignment, 4)
    attempts = _tag(fields["attempts"], "attempts")
    _arity(attempts, 4)
    atomspace_links = _tag(fields["atomspace-links"], "atomspace-links")
    _arity(atomspace_links, 2)
    state = _text(execution[1])
    if state not in {
        "scheduled",
        "backlog",
        "ready",
        "in-progress",
        "blocked",
        "done",
    }:
        raise ThreadProtocolError(f"Thread UI state is malformed: {state}")
    not_before = execution[3]
    session_attempts = tuple(
        _parse_session_attempt_summary(value)
        for value in _expression(attempts[3])
    )
    count = _integer(attempts[1])
    if count != len(session_attempts):
        raise ThreadProtocolError(
            "Thread UI attempt count does not match session attempts."
        )
    return {
        "id": _text(task[1]),
        "capability": _text(task[2]),
        "acceptance": _text(task[3]),
        "stakes": _text(task[4]),
        "dependencies": tuple(_text(value) for value in _expression(task[5])),
        "state": state,
        "upstreamBlocked": _boolean(execution[2]),
        "notBeforeEpoch": None if not_before == "none" else _integer(not_before),
        "releaseReason": _string(execution[4]),
        "assignedRole": "" if assignment[1] == "none" else _text(assignment[1]),
        "agentKey": "" if assignment[2] == "none" else _text(assignment[2]),
        "agentId": "" if assignment[3] == "none" else _text(assignment[3]),
        "attempts": count,
        "sessionId": "" if attempts[2] == "none" else _text(attempts[2]),
        "sessionAttempts": session_attempts,
        "atomspaceLinks": tuple(
            _atomspace_link_dict(_parse_atomspace_link(value))
            for value in _expression(atomspace_links[1])
        ),
    }


def _parse_session_attempt_summary(payload: Any) -> dict[str, object]:
    row = _tag(payload, "session-attempt")
    _arity(row, 8)
    return {
        "attempt": _integer(row[1]),
        "agentId": _text(row[2]),
        "agentAttempt": _integer(row[3]),
        "sessionId": _text(row[4]),
        "status": _text(row[5]),
        "activity": _text(row[6]),
        "isTerminated": _boolean(row[7]),
    }


def _atomspace_link_dict(link: ThreadAtomspaceLink) -> dict[str, str]:
    return {
        "linkKey": link.link_key,
        "scope": link.scope,
        "owner": link.owner,
    }


def _validated_summary(
    summary: list[Any],
    tasks: tuple[dict[str, object], ...],
) -> dict[str, int]:
    state_keys = (
        ("scheduled", "scheduled"),
        ("backlog", "backlog"),
        ("ready", "ready"),
        ("inProgress", "in-progress"),
        ("blocked", "blocked"),
        ("done", "done"),
    )
    counts = {
        output_key: _integer(summary[index])
        for index, (output_key, _) in enumerate(state_keys, start=2)
    }
    total = _integer(summary[1])
    progress = _integer(summary[8])
    observed = {
        output_key: sum(task["state"] == state for task in tasks)
        for output_key, state in state_keys
    }
    expected_progress = 0 if total == 0 else counts["done"] * 100 // total
    if (
        total != len(tasks)
        or counts != observed
        or sum(counts.values()) != total
        or progress != expected_progress
    ):
        raise ThreadProtocolError(
            "Thread UI summary does not match its task projection."
        )
    return {
        "total": total,
        **counts,
        "progressPct": progress,
    }


def _parse_ui_task(payload: Any) -> dict[str, object]:
    row = _tag(payload, "ui-task")
    _arity(row, 13)
    state = _text(row[6])
    if state not in {
        "scheduled",
        "backlog",
        "ready",
        "in-progress",
        "blocked",
        "done",
    }:
        raise ThreadProtocolError(f"Thread UI state is malformed: {state}")
    not_before = row[11]
    return {
        "id": _text(row[1]),
        "capability": _text(row[2]),
        "acceptance": _text(row[3]),
        "stakes": _text(row[4]),
        "dependencies": tuple(_text(value) for value in _expression(row[5])),
        "state": state,
        "upstreamBlocked": _boolean(row[7]),
        "assignedAgent": "" if row[8] == "none" else _text(row[8]),
        "attempts": _integer(row[9]),
        "sessionId": "" if row[10] == "none" else _text(row[10]),
        "notBeforeEpoch": None if not_before == "none" else _integer(not_before),
        "releaseReason": _string(row[12]),
    }


def _parse_outcome(payload: Any) -> ThreadOutcomeDecision:
    row = _tag(payload, "outcome")
    _arity(row, 3)
    return ThreadOutcomeDecision(
        outcome=cast(ThreadOutcome, _text(row[1])),
        reason=_text(row[2]),
    )


def _parse_markdown(
    payload: Any,
    *,
    source_path: str | None,
) -> dict[str, object]:
    row = _tag(payload, "markdown")
    fields = _fields(row[1:])
    actions = []
    for value in _collection(fields["actions"], 1):
        action = _tag(value, "action")
        _arity(action, 5)
        actions.append(
            {
                "block": _text(action[1]),
                "kind": _text(action[2]),
                "line": _integer(action[3]),
                "atom": _text(action[4]),
            }
        )
    diagnostics = []
    for value in _collection(fields["diagnostics"], 1):
        diagnostic = _tag(value, "diagnostic")
        _arity(diagnostic, 3)
        diagnostics.append(
            {
                "block": _text(diagnostic[1]),
                "message": _text(diagnostic[2]),
            }
        )
    sources = {}
    for value in _collection(fields["sources"], 1):
        source = _tag(value, "source")
        _arity(source, 3)
        block = _text(source[1])
        if block in sources:
            raise ThreadProtocolError(
                f"Thread Markdown block source is duplicated: {block}"
            )
        sources[block] = _text(source[2])
    return {
        "actions": tuple(actions),
        "diagnostics": tuple(diagnostics),
        "sources": sources,
        "source_path": source_path,
    }


def _parse_attempt(payload: Any) -> ThreadPettaAttempt:
    row = _tag(payload, "attempt-result")
    _arity(row, 5)
    observation = _tag(row[1], "observation")
    _arity(observation, 8)
    return ThreadPettaAttempt(
        observation=ThreadProcessObservation(
            exit_reason=cast(ThreadExitReason, _text(observation[1])),
            exit_code=_integer(observation[2]),
            output=_base64_text(observation[3]),
            output_bytes=_integer(observation[4]),
            duration_seconds=_number(observation[5]),
            activity_events=_integer(observation[6]),
            lease_renewals=_integer(observation[7]),
        ),
        evaluation=_parse_evaluation(row[2]),
        adjudication=_parse_evaluation(row[3]),
        outcome=_parse_outcome(row[4]),
    )


def _parse_status(payload: Any) -> str:
    row = _tag(payload, "status-document")
    fields = _fields(row[1:])
    return _text(_single(fields["document"]))


def _parse_evaluation(payload: Any) -> ThreadEvaluation:
    row = _tag(payload, "evaluation")
    _arity(row, 4)
    return ThreadEvaluation(
        evaluator=_text(row[1]),
        verdict=cast(ThreadVerdict, _text(row[2])),
        reason=_base64_text(row[3]),
    )


def _fields(rows: list[Any]) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}
    for row in rows:
        if not isinstance(row, list) or not row:
            raise ThreadProtocolError("Thread protocol field is malformed.")
        name = _text(row[0])
        if name in result:
            raise ThreadProtocolError(f"Thread protocol field is duplicated: {name}")
        result[name] = row
    return result


def _exact_fields(
    rows: list[Any],
    expected: set[str],
) -> dict[str, list[Any]]:
    result = _fields(rows)
    if set(result) != expected:
        raise ThreadProtocolError(
            "Thread protocol record fields do not match its version.",
            details={
                "expected": sorted(expected),
                "received": sorted(result),
            },
        )
    return result


def _require_valid_record(
    fields: dict[str, list[Any]],
    name: str,
) -> None:
    valid = _boolean(_single(fields["valid"]))
    errors = tuple(_text(error) for error in _collection(fields["errors"], 1))
    if not valid:
        raise ThreadSpecificationError(
            f"MeTTa thread {name} validation failed: "
            + (", ".join(errors) if errors else "unknown-validation-error")
            + ".",
            details={"errors": list(errors)},
        )
    if errors:
        raise ThreadProtocolError(
            f"Valid thread {name} returned validation errors.",
            details={"errors": list(errors)},
        )


def _require_v2(protocol_version: str, operation: str) -> None:
    if protocol_version != PROTOCOL_VERSION_V2:
        raise ThreadProtocolError(
            f"Thread operation {operation} requires goalchainer-thread-v2."
        )


def _tag(atom: Any, expected: str) -> list[Any]:
    if not isinstance(atom, list) or not atom or atom[0] != expected:
        raise ThreadProtocolError(f"Expected thread protocol tag: {expected}")
    return atom


def _collection(row: Any, index: int) -> list[Any]:
    if (
        not isinstance(row, list)
        or len(row) <= index
        or not isinstance(row[index], list)
    ):
        raise ThreadProtocolError("Thread protocol collection is malformed.")
    return row[index]


def _expression(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ThreadProtocolError("Thread protocol expression is malformed.")
    return value


def _single(row: list[Any]) -> Any:
    _arity(row, 2)
    return row[1]


def _arity(row: list[Any], expected: int) -> None:
    if len(row) != expected:
        raise ThreadProtocolError(
            f"Thread protocol record has arity {len(row)}, expected {expected}."
        )


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ThreadProtocolError("Thread protocol text is empty or malformed.")
    return value


def _string(value: Any) -> str:
    if not isinstance(value, str):
        raise ThreadProtocolError("Thread protocol string is malformed.")
    return value


def _boolean(value: Any) -> bool:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    raise ThreadProtocolError(f"Thread protocol boolean is malformed: {value}")


def _integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ThreadProtocolError(f"Thread protocol integer is malformed: {value}")
    return value


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ThreadProtocolError(f"Thread protocol number is malformed: {value}")
    return float(value)


def _base64_text(value: Any) -> str:
    encoded = _text(value)
    if not encoded.startswith("b64_"):
        raise ThreadProtocolError("Thread protocol base64 text has no b64_ prefix.")
    try:
        return base64.urlsafe_b64decode(encoded[4:].encode("ascii")).decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise ThreadProtocolError("Thread protocol base64 text is malformed.") from exc


__all__ = ["PROTOCOL_VERSION", "parse_thread_output"]

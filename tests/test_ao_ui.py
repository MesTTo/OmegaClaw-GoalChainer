from __future__ import annotations

import json
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast, override

import pytest
from hypothesis import given, strategies as st
from thread_spec_fixture import (  # pyright: ignore[reportImplicitRelativeImport]
    VALID_THREAD_SPEC,
    VALID_THREAD_SPEC_V2,
)
from goal_chainer.ao_ui import (
    _external_source_task_id,  # pyright: ignore[reportPrivateUsage]
    _loopback_url,  # pyright: ignore[reportPrivateUsage]
    _project_id,  # pyright: ignore[reportPrivateUsage]
    build_ui_projection,
    disconnect_ui_projection,
    dispatch_due_tasks,
    observe_agent_orchestrator_sessions,
    sync_ui_projection,
    watch_agent_orchestrator,
)
from goal_chainer.directive_models import DirectiveTaskState
from goal_chainer.thread_models import ThreadExecutionError
from goal_chainer.thread_orchestrator import ThreadOrchestrator
from goal_chainer.thread_plan import compile_thread_markdown
from goal_chainer.thread_runtime import ThreadRuntime


class _AOStub(ThreadingHTTPServer):
    requests: list[tuple[str, str, dict[str, object] | None]]
    sessions: dict[str, str]
    session_projects: dict[str, str]
    session_agent_attempts: dict[str, int]
    agent_attempts: dict[str, int]
    failed_spawns: int
    session_status: str
    session_activity: str
    session_terminated: bool
    session_updated_at: str
    mismatched_v2_project: bool

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _AOHandler)
        self.requests = []
        self.sessions = {}
        self.session_projects = {}
        self.session_agent_attempts = {}
        self.agent_attempts = {}
        self.failed_spawns = 0
        self.session_status = "working"
        self.session_activity = "active"
        self.session_terminated = False
        self.session_updated_at = "2026-07-29T01:02:03Z"
        self.mismatched_v2_project = False


class _AOHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        server = cast(_AOStub, self.server)
        body = self._body()
        server.requests.append(("POST", self.path, body))
        if server.failed_spawns:
            server.failed_spawns -= 1
            self._json(
                503,
                {"code": "AO_UNAVAILABLE", "message": "spawn unavailable"},
            )
            return
        source_task_id = body.get("sourceTaskId") if body is not None else None
        if not isinstance(source_task_id, str):
            self._json(400, {"code": "BAD_SOURCE", "message": "missing source"})
            return
        created = source_task_id not in server.sessions
        if created:
            server.sessions[source_task_id] = f"ao-session-{len(server.sessions) + 1}"
        session_id = server.sessions[source_task_id]
        project_id = body.get("projectId") if body is not None else None
        if created and isinstance(project_id, str):
            server.session_projects[session_id] = project_id
        session: dict[str, object] = {"id": session_id}
        if body is not None and "projectAgentKey" in body:
            agent_key = body.get("projectAgentKey")
            if not isinstance(agent_key, str):
                self._json(
                    400,
                    {"code": "BAD_AGENT", "message": "missing project agent"},
                )
                return
            if created:
                agent_attempt = server.agent_attempts.get(agent_key, 0) + 1
                server.agent_attempts[agent_key] = agent_attempt
                server.session_agent_attempts[source_task_id] = agent_attempt
            session.update(
                {
                    "projectId": (
                        "wrong-project"
                        if server.mismatched_v2_project
                        else body.get("projectId")
                    ),
                    "projectAgentId": "019fa5d3-5228-74a0-8436-772684b85c24",
                    "projectAgentAttempt": server.session_agent_attempts[
                        source_task_id
                    ],
                    "status": server.session_status,
                    "activity": {"state": server.session_activity},
                    "isTerminated": server.session_terminated,
                    "updatedAt": server.session_updated_at,
                }
            )
        self._json(
            201 if created else 200,
            {"created": created, "session": session},
        )

    def do_GET(self) -> None:
        server = cast(_AOStub, self.server)
        server.requests.append(("GET", self.path, None))
        session_id = self.path.rsplit("/", 1)[-1]
        if session_id not in server.sessions.values():
            self._json(404, {"code": "NOT_FOUND", "message": "missing session"})
            return
        self._json(
            200,
            {
                "session": {
                    "id": session_id,
                    "projectId": server.session_projects.get(
                        session_id,
                        "goalchainer",
                    ),
                    "status": server.session_status,
                    "activity": {"state": server.session_activity},
                    "isTerminated": server.session_terminated,
                    "updatedAt": server.session_updated_at,
                }
            },
        )

    def do_PUT(self) -> None:
        body = self._body()
        cast(_AOStub, self.server).requests.append(("PUT", self.path, body))
        self._json(200, {"updated": True})

    def do_DELETE(self) -> None:
        cast(_AOStub, self.server).requests.append(("DELETE", self.path, None))
        self._json(200, {"deleted": True})

    @override
    def log_message(self, format: str, *args: object) -> None:
        del format
        del args

    def _body(self) -> dict[str, object] | None:
        size = int(self.headers.get("Content-Length", "0"))
        if size == 0:
            return None
        value = cast(object, json.loads(self.rfile.read(size)))
        if not isinstance(value, dict):
            raise ValueError("AO stub request must be an object")
        return cast(dict[str, object], value)

    def _json(self, status: int, value: dict[str, object]) -> None:
        raw = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        _ = self.wfile.write(raw)


@contextmanager
def _ao_server() -> Generator[_AOStub, None, None]:
    server = _AOStub()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture(scope="module")
def runtime() -> ThreadRuntime:
    return ThreadRuntime()


def _orchestrator(
    tmp_path: Path,
    runtime: ThreadRuntime,
    *,
    source: str = VALID_THREAD_SPEC,
) -> ThreadOrchestrator:
    plan = tmp_path / "thread.metta"
    compilation = compile_thread_markdown(
        source,
        plan_path=plan,
        thread_runtime=runtime,
    )
    return ThreadOrchestrator(
        compilation.specification,
        plan_path=plan,
        audit_path=tmp_path / "thread.jsonl",
        runtime=runtime,
    )


def _origin(server: _AOStub) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


def test_projection_is_derived_by_metta_from_omegaclaw_state(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    thread = _orchestrator(tmp_path, runtime)

    projection = build_ui_projection(
        thread,
        now=datetime(2026, 7, 29, tzinfo=UTC),
    )

    assert projection["protocol"] == "goalchainer-ui-v1"
    assert projection["summary"] == {
        "total": 2,
        "scheduled": 0,
        "backlog": 1,
        "ready": 1,
        "inProgress": 0,
        "blocked": 0,
        "done": 0,
        "progressPct": 0,
    }
    tasks = cast(tuple[dict[str, object], ...], projection["tasks"])
    assert [(task["id"], task["state"]) for task in tasks] == [
        ("collect-evidence", "ready"),
        ("redact-summary", "backlog"),
    ]
    assert len(cast(str, projection["sourceRevision"])) == 64


def test_projection_rejects_a_naive_release_clock(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    thread = _orchestrator(tmp_path, runtime)

    with pytest.raises(ThreadExecutionError, match="timezone-aware"):
        _ = build_ui_projection(thread, now=datetime(2026, 7, 29))


def test_v2_projection_contains_project_agents_and_logical_links(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    thread = _orchestrator(tmp_path, runtime, source=VALID_THREAD_SPEC_V2)

    projection = build_ui_projection(
        thread,
        now=datetime(2026, 7, 29, tzinfo=UTC),
    )

    assert projection["protocol"] == "goalchainer-ui-v2"
    assert projection["projectId"] == "project-incident-42"
    agents = cast(tuple[dict[str, object], ...], projection["agents"])
    assert {agent["agentKey"] for agent in agents} == {
        "local-control",
        "local-worker",
        "thread-supervisor",
        "result-evaluator",
        "security-specialist",
        "security-owner",
    }
    tasks = cast(tuple[dict[str, object], ...], projection["tasks"])
    collect = next(task for task in tasks if task["id"] == "collect-evidence")
    assert collect["assignedRole"] == "worker"
    assert collect["agentKey"] == "local-worker"
    assert collect["atomspaceLinks"] == (
        {"linkKey": "project-shared", "scope": "shared", "owner": "project"},
        {
            "linkKey": "worker-private",
            "scope": "private",
            "owner": "local-worker",
        },
    )
    assert "path" not in json.dumps(projection).casefold()


def test_dispatch_claims_spawns_binds_and_does_not_spawn_twice(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    thread = _orchestrator(tmp_path, runtime)
    with _ao_server() as server:
        first = dispatch_due_tasks(
            thread,
            project_id="goalchainer",
            ao_url=_origin(server),
            now=datetime(2026, 7, 29, tzinfo=UTC),
        )
        second = dispatch_due_tasks(
            thread,
            project_id="goalchainer",
            ao_url=_origin(server),
            now=datetime(2026, 7, 29, tzinfo=UTC),
        )

    assert first["dispatched"] == [
        {
            "task": "collect-evidence",
            "attempt": 1,
            "sessionId": "ao-session-1",
            "created": True,
            "bindingCreated": True,
            "status": "dispatched",
        }
    ]
    assert second["dispatched"] == []
    posts = [request for request in server.requests if request[0] == "POST"]
    assert len(posts) == 1
    posted = posts[0][2]
    assert posted is not None
    assert posted["sourceTaskId"] == (
        "goalchainer:incident-42:collect-evidence:1"
    )
    assert posted["mcpProfile"] == "oh-my-goals"
    assert "mcpProfiles" not in posted
    prompt = posted["prompt"]
    assert isinstance(prompt, str)
    assert prompt.startswith("System workflow: research-agent\n")
    assert "1. Inspect existing evidence and source material." in prompt
    assert "Task contract\nThread: Incident response" in prompt
    assert "MCP profile: oh-my-goals" in prompt
    assert "Available MCP tools: remember, query, solve" in prompt
    assert "Do not claim completion in GoalChainer." in prompt
    events = thread.audit.verify()
    event_types = [event.event_type for event in events]
    assert event_types.index("ao-dispatch-reserved") < event_types.index(
        "attempt-started"
    )
    assert event_types.index("attempt-started") < event_types.index(
        "ao-session-bound"
    )
    assert thread.inspect()["attempts"] == {"collect-evidence": 1}
    state = thread.session.task_state("collect-evidence").value
    assert isinstance(state, DirectiveTaskState)
    assert state.state == "in-progress"


def test_v2_dispatch_posts_metta_agent_and_normalizes_ao_identity(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    thread = _orchestrator(tmp_path, runtime, source=VALID_THREAD_SPEC_V2)
    with _ao_server() as server:
        result = dispatch_due_tasks(
            thread,
            project_id="project-incident-42",
            ao_url=_origin(server),
            now=datetime(2026, 7, 29, tzinfo=UTC),
        )

    posted = next(
        body
        for method, _, body in server.requests
        if method == "POST"
    )
    assert posted is not None
    assert posted["projectAgentKey"] == "local-worker"
    assert posted["projectAgentRole"] == "worker"
    assert "goalChainer" not in posted
    assert "knownAgentId" not in posted
    assert "atomspaceLinks" not in posted
    prompt = cast(str, posted["prompt"])
    assert "Project: project-incident-42" in prompt
    assert "MeTTa-selected role: worker" in prompt
    assert "Stable agent key: local-worker" in prompt
    assert "private persistent Atomspace" in prompt
    assert "Read your prior private project notes before starting work." in prompt
    assert "record sourced observations and decisions" in prompt
    assert len(prompt.encode()) <= 4096

    dispatched = cast(list[dict[str, object]], result["dispatched"])
    assert dispatched[0]["attempt"] == 1
    events = thread.audit.verify()
    event_types = [event.event_type for event in events]
    assert event_types.index("ao-dispatch-reserved") < event_types.index(
        "attempt-started"
    )
    assert event_types.index("attempt-started") < event_types.index(
        "ao-agent-bound"
    )
    assert event_types.index("ao-session-attempt") < event_types.index(
        "ao-session-bound"
    )
    binding = next(
        event for event in events if event.event_type == "ao-agent-bound"
    )
    assert binding.payload["agent_id"] == (
        "019fa5d3-5228-74a0-8436-772684b85c24"
    )
    projection = cast(dict[str, object], result["projection"])
    tasks = cast(tuple[dict[str, object], ...], projection["tasks"])
    collect = next(task for task in tasks if task["id"] == "collect-evidence")
    assert collect["agentId"] == "019fa5d3-5228-74a0-8436-772684b85c24"
    session_attempts = cast(
        tuple[dict[str, object], ...],
        collect["sessionAttempts"],
    )
    assert session_attempts[0]["sessionId"] == "ao-session-1"


def test_v2_goal_attempts_are_independent_from_stable_agent_attempts(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    source = VALID_THREAD_SPEC_V2.replace(
        "(thread-task incident-42 redact-summary specialist summary-redacted high)",
        "(thread-task incident-42 redact-summary local summary-redacted high)",
    ).replace(
        "(thread-depends incident-42 redact-summary collect-evidence)\n",
        "",
    )
    thread = _orchestrator(tmp_path, runtime, source=source)

    with _ao_server() as server:
        result = dispatch_due_tasks(
            thread,
            project_id="project-incident-42",
            ao_url=_origin(server),
        )

    dispatched = cast(list[dict[str, object]], result["dispatched"])
    assert [
        (row["task"], row["attempt"], row["sessionId"])
        for row in dispatched
    ] == [
        ("collect-evidence", 1, "ao-session-1"),
        ("redact-summary", 1, "ao-session-2"),
    ]
    attempts = [
        event.payload
        for event in thread.audit.verify()
        if event.event_type == "ao-session-attempt"
    ]
    assert [
        (row["task"], row["attempt"], row["agent_attempt"])
        for row in attempts
    ] == [
        ("collect-evidence", 1, 1),
        ("redact-summary", 1, 2),
    ]
    projection = cast(dict[str, object], result["projection"])
    tasks = cast(tuple[dict[str, object], ...], projection["tasks"])
    projected_attempts = {
        cast(str, task["id"]): cast(
            tuple[dict[str, object], ...],
            task["sessionAttempts"],
        )[0]
        for task in tasks
    }
    assert projected_attempts["collect-evidence"]["agentAttempt"] == 1
    assert projected_attempts["redact-summary"]["agentAttempt"] == 2


def test_v2_mismatched_ao_response_leaves_no_binding_and_retries(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    thread = _orchestrator(tmp_path, runtime, source=VALID_THREAD_SPEC_V2)
    with _ao_server() as server:
        server.mismatched_v2_project = True
        with pytest.raises(ThreadExecutionError, match="identity or state"):
            dispatch_due_tasks(
                thread,
                project_id="project-incident-42",
                ao_url=_origin(server),
            )
        assert not any(
            event.event_type
            in {"ao-session-bound", "ao-agent-bound", "ao-session-attempt"}
            for event in thread.audit.verify()
        )
        state = thread.session.task_state("collect-evidence").value
        assert isinstance(state, DirectiveTaskState)
        assert state.state == "ready"

        server.mismatched_v2_project = False
        retried = dispatch_due_tasks(
            thread,
            project_id="project-incident-42",
            ao_url=_origin(server),
        )

    dispatched = cast(list[dict[str, object]], retried["dispatched"])
    assert dispatched[0]["attempt"] == 1


@pytest.mark.parametrize("operation", ["sync", "observe", "dispatch", "watch"])
def test_v2_route_project_mismatch_makes_no_request_or_audit_write(
    tmp_path: Path,
    runtime: ThreadRuntime,
    operation: str,
) -> None:
    thread = _orchestrator(tmp_path, runtime, source=VALID_THREAD_SPEC_V2)
    before = thread.audit.verify()

    with _ao_server() as server:
        with pytest.raises(ThreadExecutionError, match="does not match"):
            if operation == "sync":
                _ = sync_ui_projection(
                    thread,
                    project_id="wrong-project",
                    ao_url=_origin(server),
                )
            elif operation == "observe":
                _ = observe_agent_orchestrator_sessions(
                    thread,
                    project_id="wrong-project",
                    ao_url=_origin(server),
                )
            elif operation == "dispatch":
                _ = dispatch_due_tasks(
                    thread,
                    project_id="wrong-project",
                    ao_url=_origin(server),
                )
            else:
                _ = watch_agent_orchestrator(
                    thread,
                    project_id="wrong-project",
                    ao_url=_origin(server),
                    cycles=1,
                )
        assert server.requests == []

    assert thread.audit.verify() == before


def test_future_task_is_scheduled_without_starting_an_agent(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    source = VALID_THREAD_SPEC.replace(
        "(thread-task incident-42 collect-evidence local evidence-collected normal)\n",
        (
            "(thread-task incident-42 collect-evidence local "
            "evidence-collected normal)\n"
            "(thread-not-before incident-42 collect-evidence 2000000000)\n"
        ),
    )
    thread = _orchestrator(tmp_path, runtime, source=source)

    with _ao_server() as server:
        result = dispatch_due_tasks(
            thread,
            project_id="goalchainer",
            ao_url=_origin(server),
            now=datetime(2026, 7, 29, tzinfo=UTC),
        )

    assert result["dispatched"] == []
    projection = cast(dict[str, object], result["projection"])
    tasks = cast(tuple[dict[str, object], ...], projection["tasks"])
    scheduled = next(task for task in tasks if task["id"] == "collect-evidence")
    assert scheduled["state"] == "scheduled"
    assert scheduled["scheduledAt"] == "2033-05-18T03:33:20Z"
    assert scheduled["releaseReason"] == (
        "not-before constraint has not elapsed"
    )
    assert not any(method == "POST" for method, _, _ in server.requests)
    state = thread.session.task_state("collect-evidence").value
    assert isinstance(state, DirectiveTaskState)
    assert state.state == "ready"


def test_failed_spawn_releases_claim_without_consuming_attempt(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    thread = _orchestrator(tmp_path, runtime)
    with _ao_server() as server:
        server.failed_spawns = 1
        with pytest.raises(ThreadExecutionError, match="rejected"):
            _ = dispatch_due_tasks(
                thread,
                project_id="goalchainer",
                ao_url=_origin(server),
            )
        assert thread.inspect()["attempts"] == {}
        state = thread.session.task_state("collect-evidence").value
        assert isinstance(state, DirectiveTaskState)
        assert state.state == "ready"

        retried = dispatch_due_tasks(
            thread,
            project_id="goalchainer",
            ao_url=_origin(server),
        )

    dispatched = cast(list[dict[str, object]], retried["dispatched"])
    assert dispatched[0]["attempt"] == 1
    assert thread.inspect()["attempts"] == {"collect-evidence": 1}
    assert [
        event.event_type
        for event in thread.audit.verify()
        if event.event_type == "ao-dispatch-failed"
    ] == ["ao-dispatch-failed"]


def test_reserved_dispatch_recovers_after_process_interruption(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    thread = _orchestrator(tmp_path, runtime)
    _ = thread.reserve_agent_orchestrator_attempt(
        "collect-evidence",
        attempt=1,
        worker="local-worker",
    )

    with _ao_server() as server:
        result = dispatch_due_tasks(
            thread,
            project_id="goalchainer",
            ao_url=_origin(server),
        )

    dispatched = cast(list[dict[str, object]], result["dispatched"])
    assert dispatched[0]["attempt"] == 1
    assert dispatched[0]["sessionId"] == "ao-session-1"
    assert thread.inspect()["attempts"] == {"collect-evidence": 1}


def test_session_observation_is_audit_only_and_deduplicated(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    thread = _orchestrator(tmp_path, runtime)
    with _ao_server() as server:
        _ = dispatch_due_tasks(
            thread,
            project_id="goalchainer",
            ao_url=_origin(server),
        )
        before = thread.session.task_state("collect-evidence").value
        first = observe_agent_orchestrator_sessions(
            thread,
            project_id="goalchainer",
            ao_url=_origin(server),
        )
        second = observe_agent_orchestrator_sessions(
            thread,
            project_id="goalchainer",
            ao_url=_origin(server),
        )
        server.session_status = "needs_input"
        server.session_activity = "blocked"
        server.session_updated_at = "2026-07-29T01:03:00+00:00"
        changed = observe_agent_orchestrator_sessions(
            thread,
            project_id="goalchainer",
            ao_url=_origin(server),
        )

    assert first["created"] == 1
    assert second["created"] == 0
    assert changed["created"] == 1
    after = thread.session.task_state("collect-evidence").value
    assert before == after
    observations = [
        event
        for event in thread.audit.verify()
        if event.event_type == "ao-session-observed"
    ]
    assert [event.payload["status"] for event in observations] == [
        "working",
        "needs_input",
    ]
    assert observations[-1].payload["activity"] == "blocked"


def test_v2_projection_overlays_latest_session_observation(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    thread = _orchestrator(tmp_path, runtime, source=VALID_THREAD_SPEC_V2)
    with _ao_server() as server:
        _ = dispatch_due_tasks(
            thread,
            project_id="project-incident-42",
            ao_url=_origin(server),
        )
        server.session_status = "needs_input"
        server.session_activity = "blocked"
        server.session_terminated = True
        server.session_updated_at = "2026-07-29T01:03:00Z"
        observed = observe_agent_orchestrator_sessions(
            thread,
            project_id="project-incident-42",
            ao_url=_origin(server),
        )

    assert observed["created"] == 1
    projection = build_ui_projection(thread)
    tasks = cast(tuple[dict[str, object], ...], projection["tasks"])
    collect = next(task for task in tasks if task["id"] == "collect-evidence")
    attempt = cast(
        tuple[dict[str, object], ...],
        collect["sessionAttempts"],
    )[0]
    assert attempt == {
        "attempt": 1,
        "agentId": "019fa5d3-5228-74a0-8436-772684b85c24",
        "agentAttempt": 1,
        "sessionId": "ao-session-1",
        "status": "needs_input",
        "activity": "blocked",
        "isTerminated": True,
    }


def test_watch_observes_existing_sessions_and_syncs_projection(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    thread = _orchestrator(tmp_path, runtime)
    with _ao_server() as server:
        _ = dispatch_due_tasks(
            thread,
            project_id="goalchainer",
            ao_url=_origin(server),
        )
        result = watch_agent_orchestrator(
            thread,
            project_id="goalchainer",
            ao_url=_origin(server),
            cycles=1,
        )

    assert result["cycles"] == 1
    assert result["observed"] == 1
    assert result["dispatched"] == 0
    assert result["interrupted"] is False
    assert any(method == "GET" for method, _, _ in server.requests)
    assert any(method == "PUT" for method, _, _ in server.requests)


def test_invalid_session_observation_is_rejected_before_audit(
    tmp_path: Path,
    runtime: ThreadRuntime,
) -> None:
    thread = _orchestrator(tmp_path, runtime)
    with _ao_server() as server:
        _ = dispatch_due_tasks(
            thread,
            project_id="goalchainer",
            ao_url=_origin(server),
        )
        server.session_activity = "guessing"
        before = len(thread.audit.verify())
        with pytest.raises(ThreadExecutionError, match="activity state"):
            _ = observe_agent_orchestrator_sessions(
                thread,
                project_id="goalchainer",
                ao_url=_origin(server),
            )

    assert len(thread.audit.verify()) == before


def test_disconnect_uses_the_project_projection_endpoint() -> None:
    with _ao_server() as server:
        result = disconnect_ui_projection(
            project_id="goalchainer",
            ao_url=_origin(server),
        )

    assert result == {"deleted": True}
    assert server.requests == [
        ("DELETE", "/api/v1/projects/goalchainer/goalchainer", None)
    ]


@given(st.text())
def test_project_id_accepts_exactly_the_shared_safe_identifier_grammar(
    value: str,
) -> None:
    import re

    expected = re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value)
    if expected is None:
        with pytest.raises(ThreadExecutionError):
            _ = _project_id(value)
    else:
        assert _project_id(value) == value


@given(st.text(), st.text(), st.integers(min_value=1))
def test_external_source_key_is_stable_and_bounded(
    thread_id: str,
    task_id: str,
    attempt: int,
) -> None:
    first = _external_source_task_id(thread_id, task_id, attempt)
    second = _external_source_task_id(thread_id, task_id, attempt)

    assert first == second
    assert 1 <= len(first) <= 128
    assert first.startswith("goalchainer:")
    assert all(character.isascii() for character in first)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:3001",
        "http://localhost:3001",
        "http://0.0.0.0:3001",
        "http://127.0.0.1",
        "http://127.0.0.1:3001/path",
        "http://user@127.0.0.1:3001",
    ],
)
def test_agent_orchestrator_origin_rejects_non_loopback_shapes(url: str) -> None:
    with pytest.raises(ThreadExecutionError):
        _ = _loopback_url(url)

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
from thread_spec_fixture import VALID_THREAD_SPEC  # pyright: ignore[reportImplicitRelativeImport]
from goal_chainer.ao_ui import (
    _external_source_task_id,  # pyright: ignore[reportPrivateUsage]
    _loopback_url,  # pyright: ignore[reportPrivateUsage]
    _project_id,  # pyright: ignore[reportPrivateUsage]
    build_ui_projection,
    disconnect_ui_projection,
    dispatch_due_tasks,
    observe_agent_orchestrator_sessions,
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
    failed_spawns: int
    session_status: str
    session_activity: str
    session_terminated: bool
    session_updated_at: str

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _AOHandler)
        self.requests = []
        self.sessions = {}
        self.failed_spawns = 0
        self.session_status = "working"
        self.session_activity = "active"
        self.session_terminated = False
        self.session_updated_at = "2026-07-29T01:02:03Z"


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
        session_id = server.sessions.setdefault(source_task_id, "ao-session-1")
        self._json(
            201 if created else 200,
            {"created": created, "session": {"id": session_id}},
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
                    "projectId": "goalchainer",
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
    prompt = posted["prompt"]
    assert isinstance(prompt, str)
    assert prompt.startswith("System workflow: research-agent\n")
    assert "1. Inspect existing evidence and source material." in prompt
    assert "Task contract\nThread: Incident response" in prompt
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

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from goal_chainer.ao_ui import build_ui_projection
from goal_chainer.thread_demo import run_thread_demo
from goal_chainer.thread_orchestrator import ThreadOrchestrator
from goal_chainer.thread_plan import compile_thread_markdown
from goal_chainer.thread_spec import read_thread_markdown_source

PROJECT_AGENT_DEMO = (
    Path(__file__).parents[1]
    / "examples"
    / "threadkeeper-project-agents-v2.md"
)


def test_live_thread_demo_checks_every_claimed_capability(tmp_path) -> None:
    report = run_thread_demo(tmp_path / "demo")

    assert report["durable"] is True
    verified = cast(dict[str, bool], report["verified"])
    assert all(verified.values())
    assert report["attempts"] == {
        "local": 1,
        "delegated": 1,
        "retry": 2,
        "permanent_failure": 3,
        "denied": 0,
    }
    assert "MeTTa Markdown task specifications" in cast(
        list[str],
        report["now"],
    )
    assert "claim and completion lifecycle only" in cast(
        list[str],
        report["before"],
    )


def test_project_agent_v2_example_compiles_dispatches_and_projects(
    tmp_path,
) -> None:
    source, source_path = read_thread_markdown_source(PROJECT_AGENT_DEMO)
    plan = tmp_path / "project-agent-demo.metta"
    compilation = compile_thread_markdown(
        source,
        source_path=str(source_path),
        plan_path=plan,
    )
    thread = ThreadOrchestrator(
        compilation.specification,
        plan_path=plan,
        audit_path=tmp_path / "project-agent-demo.jsonl",
    )

    dispatch = thread.derive_agent_orchestrator_dispatch(
        "inspect-evidence",
        route="worker",
        attempt=1,
    )
    projection = build_ui_projection(
        thread,
        now=datetime(2026, 7, 29, tzinfo=UTC),
    )

    assert dispatch.project_id == "research-project"
    assert dispatch.role == "worker"
    assert dispatch.agent_key == "research-worker"
    assert [(link.scope, link.owner) for link in dispatch.atomspace_links] == [
        ("shared", "project"),
        ("private", "research-worker"),
    ]
    assert projection["protocol"] == "goalchainer-ui-v2"
    tasks = cast(tuple[dict[str, object], ...], projection["tasks"])
    assert {
        (task["id"], task["assignedRole"], task["agentKey"])
        for task in tasks
    } == {
        ("inspect-evidence", "worker", "research-worker"),
        ("compare-sources", "worker", "research-worker"),
    }

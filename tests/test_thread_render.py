from __future__ import annotations

import sys

from thread_spec_fixture import VALID_THREAD_SPEC

from goal_chainer.thread_models import ThreadUsage
from goal_chainer.thread_orchestrator import ThreadOrchestrator
from goal_chainer.thread_plan import compile_thread_markdown
from goal_chainer.thread_render import render_thread_status
from goal_chainer.thread_spec import parse_thread_markdown


def test_mettabase_renders_status_and_preserves_specification_facts(
    tmp_path,
) -> None:
    plan = tmp_path / "thread.metta"
    compiled = compile_thread_markdown(
        VALID_THREAD_SPEC,
        plan_path=plan,
    )
    thread = ThreadOrchestrator(
        compiled.specification,
        plan_path=plan,
        audit_path=tmp_path / "thread.jsonl",
    )
    thread.run_task(
        "collect-evidence",
        [sys.executable, "-c", "print('evidence-collected')"],
        cwd=tmp_path,
        evaluator=lambda _task, _observation: ("accept", "checked"),
        usage=ThreadUsage(10, 5),
    )

    markdown = render_thread_status(thread)
    reparsed = parse_thread_markdown(markdown, runtime=thread.runtime.runtime)

    assert "## Board" in markdown
    assert "## Budget" in markdown
    assert "## Attempts" in markdown
    assert "## Audit chain" in markdown
    assert "| Spent | 15 |" in markdown
    assert reparsed.semantic_digest == compiled.specification.semantic_digest

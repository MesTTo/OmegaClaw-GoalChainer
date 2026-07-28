"""Checked end-to-end demonstration of thread orchestration capabilities."""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .thread_models import ThreadUsage
from .thread_orchestrator import ThreadOrchestrator
from .thread_plan import compile_thread_markdown
from .thread_render import render_thread_status
from .thread_spec import read_thread_markdown_source

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_SPEC = REPO_ROOT / "examples" / "threadkeeper-demo.md"


def run_thread_demo(
    directory: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    """Run and assert the local, delegated, retry, failure, and denial paths."""

    with _demo_directory(directory) as (root, durable):
        source, source_path = read_thread_markdown_source(DEMO_SPEC)
        plan_path = root / "threadkeeper-demo.metta"
        compilation = compile_thread_markdown(
            source,
            source_path=str(source_path),
            plan_path=plan_path,
        )
        thread = ThreadOrchestrator(
            compilation.specification,
            plan_path=plan_path,
            audit_path=root / "threadkeeper-demo.jsonl",
        )
        local = thread.run_task(
            "collect-evidence",
            [
                sys.executable,
                "-u",
                "-c",
                ("import time\nprint('evidence-collected')\ntime.sleep(1.2)\n"),
            ],
            cwd=root,
            evaluator=_accept_command(),
            usage=ThreadUsage(20, 10),
        )
        delegated = thread.run_task(
            "redact-summary",
            [sys.executable, "-c", "print('summary-redacted')"],
            cwd=root,
            evaluator=_accept_command(),
            adjudicator=_accept_command(),
            usage=ThreadUsage(20, 10),
            local_iterations=1,
            hard=True,
        )
        retried = thread.run_task(
            "retry-check",
            [sys.executable, "-c", "print('retry-accepted')"],
            cwd=root,
            evaluator=_reject_once_command(),
            usage=ThreadUsage(10, 5),
        )
        (root / ".goalchainer-demo-retried").unlink(missing_ok=True)
        failed = thread.run_task(
            "permanent-failure",
            [sys.executable, "-c", "raise SystemExit(2)"],
            cwd=root,
            evaluator=_accept_command(),
        )
        spent = thread.inspect()["usage_tokens"]
        assert isinstance(spent, int)
        thread.record_usage(
            ThreadUsage(
                compilation.specification.budget.ceiling_tokens - spent,
                0,
            ),
            task_id="budget-denied",
            attempt=0,
        )
        denied = thread.run_task(
            "budget-denied",
            [sys.executable, "-c", "print('must-not-run')"],
            cwd=root,
            evaluator=_accept_command(),
            local_iterations=1,
            hard=True,
        )
        events = thread.audit.verify()
        markdown = render_thread_status(thread)
        verified = {
            "local_worker_completed": local.outcome == "complete",
            "lease_renewed": any(
                event.event_type == "lease-renewed" for event in events
            ),
            "specialist_routed": (
                delegated.outcome == "complete"
                and delegated.attempts[0].route == "specialist"
            ),
            "adjudicator_gated": (
                delegated.attempts[0].adjudication is not None
                and delegated.attempts[0].adjudication.verdict == "accept"
            ),
            "petta_native_attempts": all(
                attempt.engine == "petta-native"
                for execution in (local, delegated, retried, failed)
                for attempt in execution.attempts
            ),
            "evaluator_retry": (
                retried.outcome == "complete"
                and [attempt.evaluation.verdict for attempt in retried.attempts]
                == ["reject", "accept"]
            ),
            "permanent_failure": failed.outcome == "permanent-failure",
            "downstream_failure_propagated": (
                "blocked-child" in failed.snapshot.status.upstream_blocked
            ),
            "budget_denied_fail_closed": (
                denied.outcome == "denied" and not denied.attempts
            ),
            "audit_chain_verified": bool(events),
            "mettabase_status_rendered": (
                "## Audit chain" in markdown
                and "## MeTTa Markdown specification" in markdown
            ),
        }
        if not all(verified.values()):
            raise AssertionError(f"Thread demo invariant failed: {verified}")
        return {
            "operation": "demo",
            "protocol": "goalchainer-thread-v1",
            "runtime": (
                "Mettabase Markdown + MeTTaScript policy + "
                "OmegaClaw lib_directive"
            ),
            "durable": durable,
            "directory": str(root) if durable else None,
            "verified": verified,
            "attempts": {
                "local": len(local.attempts),
                "delegated": len(delegated.attempts),
                "retry": len(retried.attempts),
                "permanent_failure": len(failed.attempts),
                "denied": len(denied.attempts),
            },
            "before": [
                "hard-coded incident tasks",
                "claim and completion lifecycle only",
            ],
            "now": [
                "MeTTa Markdown task specifications",
                "MeTTaScript plan, routing, release, projection, and outcomes",
                "retained PeTTa grounded attempts for bounded host effects",
                "OmegaClaw authoritative Kanban lifecycle",
                "passive lease and process supervision",
                "separate evaluator and adjudicator gates",
                "retry and downstream permanent-failure propagation",
                "hash-chained audit and Mettabase status rendering",
            ],
            "inspection": thread.inspect(),
            "markdown": markdown,
        }


def _accept_command() -> list[str]:
    return [
        sys.executable,
        "-c",
        (
            "import json\n"
            "print(json.dumps({'verdict':'accept',"
            "'reason':'acceptance condition observed'}))\n"
        ),
    ]


def _reject_once_command() -> list[str]:
    return [
        sys.executable,
        "-c",
        (
            "import json\n"
            "from pathlib import Path\n"
            "marker=Path('.goalchainer-demo-retried')\n"
            "if marker.exists():\n"
            " verdict='accept'\n"
            " reason='revised result accepted'\n"
            "else:\n"
            " marker.write_text('1')\n"
            " verdict='reject'\n"
            " reason='first result requires revision'\n"
            "print(json.dumps({'verdict':verdict,'reason':reason}))\n"
        ),
    ]


@contextmanager
def _demo_directory(directory):
    if directory is not None:
        root = Path(directory).expanduser().absolute()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        yield root, True
        return
    with tempfile.TemporaryDirectory(prefix="goalchainer-thread-demo-") as temporary:
        yield Path(temporary), False


__all__ = ["run_thread_demo"]

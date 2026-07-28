"""Render thread state through Mettabase's MeTTa Markdown authoring layer."""

from __future__ import annotations

from collections import defaultdict

from .directive_models import DirectiveSnapshot
from .thread_models import ThreadExecutionError
from .thread_orchestrator import ThreadOrchestrator


def render_thread_status(orchestrator: ThreadOrchestrator) -> str:
    """Render board, budget, attempts, audit, and source facts as Markdown."""

    inspection = orchestrator.inspect()
    snapshot = orchestrator.session.snapshot().value
    if not isinstance(snapshot, DirectiveSnapshot):
        raise ThreadExecutionError("OmegaClaw returned no thread snapshot.")
    events = orchestrator.audit.verify()
    codec = orchestrator.runtime.codec
    specification = orchestrator.specification
    spent = inspection["usage_tokens"]
    if not isinstance(spent, int):
        raise ThreadExecutionError("Thread usage total is malformed.")
    board_rows = []
    for state, tasks in (
        ("backlog", snapshot.board.backlog),
        ("ready", snapshot.board.ready),
        ("in-progress", snapshot.board.in_progress),
        ("blocked", snapshot.board.blocked),
        ("done", snapshot.board.done),
    ):
        board_rows.extend(
            codec.expression(
                "row",
                codec.string(task),
                codec.string(state),
            )
            for task in tasks
        )
    attempt_fields: dict[tuple[str, int], dict[str, str]] = defaultdict(dict)
    for event in events:
        task = event.payload.get("task")
        attempt = event.payload.get("attempt")
        if (
            not isinstance(task, str)
            or isinstance(attempt, bool)
            or not isinstance(attempt, int)
        ):
            continue
        fields = attempt_fields[(task, attempt)]
        if event.event_type == "attempt-finished":
            fields["exit"] = str(event.payload.get("exit_reason", "unknown"))
        elif event.event_type == "evaluation-recorded":
            fields["evaluation"] = str(event.payload.get("verdict", "unknown"))
        elif event.event_type == "outcome-decided":
            fields["outcome"] = str(event.payload.get("outcome", "unknown"))
    attempts = [
        codec.expression(
            "row",
            codec.string(task),
            codec.string(str(attempt)),
            codec.string(fields.get("exit", "")),
            codec.string(fields.get("evaluation", "")),
            codec.string(fields.get("outcome", "")),
        )
        for (task, attempt), fields in sorted(attempt_fields.items())
    ]
    audit = [
        codec.expression(
            "row",
            codec.string(str(event.sequence)),
            codec.string(event.timestamp),
            codec.string(event.event_type),
            codec.string(event.actor),
            codec.string(event.event_hash),
        )
        for event in events
    ]
    result = orchestrator.runtime.status_document(
        specification,
        board_source=codec.emit(board_rows),
        spent_tokens=spent,
        attempts_source=codec.emit(attempts),
        audit_source=codec.emit(audit),
    ).value
    if not isinstance(result, str):
        raise ThreadExecutionError("PeTTa returned no thread status document.")
    run = orchestrator.session.runtime.render_markdown(result)
    if not isinstance(run.value, str):
        raise ThreadExecutionError("Mettabase returned no thread Markdown.")
    return run.value


__all__ = ["render_thread_status"]

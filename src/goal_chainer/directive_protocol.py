"""Purpose: parse the GoalChainer directive adapter's versioned records of a caller-written plan's
reads and lifecycle changes."""

from __future__ import annotations

from typing import Any, Iterable

from .directive_models import (
    DirectiveAnalysis,
    DirectiveAssignment,
    DirectiveBoard,
    DirectiveLifecycleResult,
    DirectiveProtocolError,
    DirectiveRun,
    DirectiveSnapshot,
    DirectiveStatus,
    DirectiveSummary,
    DirectiveTaskState,
    DirectiveValidation,
)
from .sexpr.protocol import atom_to_python, parse_versioned_output, partition_protocol_output
from .errors import MettaEngineError
from .sexpr.codec import SexprCodec

PROTOCOL_VERSION = "goalchainer-directive-v1"
_ACKNOWLEDGEMENTS = frozenset({"true", "True", "()"})
_TASK_STATES = frozenset(
    {
        "backlog",
        "ready",
        "in-progress",
        "blocked",
        "upstream-blocked",
        "decomposed",
        "done",
    }
)


# One adapter record's value, parsed by its operation.
# am[implements a-ie-s6-directive-generic-1018@e69fb4]
def parse_directive_output(
    lines: Iterable[str],
    codec: SexprCodec,
    *,
    expected_operation: str,
) -> DirectiveRun:
    output = tuple(lines)
    envelope = parse_versioned_output(
        output,
        codec,
        version=PROTOCOL_VERSION,
        record_prefix="goalchainer-directive-",
        protocol_name="directive",
        protocol_error=DirectiveProtocolError,
        execution_error=MettaEngineError,
        expected_operation=expected_operation,
    )
    payload = atom_to_python(envelope.payload, codec)
    parsers = {
        "snapshot": _parse_snapshot,
        "task-state": _parse_task_state,
        "validate": _parse_validation,
        "analyze": _parse_analysis,
        "trace": _parse_trace,
        "markdown": _parse_markdown,
        "lifecycle": _parse_lifecycle,
    }
    parser = parsers.get(envelope.operation)
    if parser is None:
        raise DirectiveProtocolError(
            f"Unsupported directive operation: {envelope.operation}"
        )
    try:
        value = parser(payload)
    except DirectiveProtocolError:
        raise
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise DirectiveProtocolError(
            "Directive payload is malformed.",
            details={"operation": envelope.operation, "error": str(exc)},
        ) from exc
    _, human_output = partition_protocol_output(
        output,
        "goalchainer-directive-",
    )
    transcript = tuple(line for line in human_output if line not in _ACKNOWLEDGEMENTS)
    return DirectiveRun(envelope.operation, value, transcript)


def _parse_snapshot(payload: Any) -> DirectiveSnapshot:
    row = _tag(payload, "snapshot")
    fields = _fields(row[1:])
    status = _fields(_tag(fields["status"], "status")[1:])
    board = _fields(_tag(fields["board"], "board")[1:])
    summary = _fields(_tag(fields["summary"], "summary")[1:])
    analysis = _parse_analysis(fields["analysis"])
    info_row = _tag(fields["info"], "info")
    info: list[tuple[str, str]] = []
    for pair in _collection(info_row, 1):
        if not isinstance(pair, list) or len(pair) != 2:
            raise DirectiveProtocolError("Directive plan metadata is malformed.")
        info.append((_text(pair[0]), _text(pair[1])))
    return DirectiveSnapshot(
        status=DirectiveStatus(
            tasks=_strings(status["tasks"]),
            ready=_strings(status["ready"]),
            claimed=_strings(status["claimed"]),
            blocked=_strings(status["blocked"]),
            upstream_blocked=_strings(status["upstream-blocked"]),
            completed=_strings(status["completed"]),
        ),
        next_actions=_assignments(fields["next-actions"]),
        board=DirectiveBoard(
            backlog=_strings(board["backlog"]),
            ready=_strings(board["ready"]),
            in_progress=_strings(board["in-progress"]),
            blocked=_strings(board["blocked"]),
            done=_strings(board["done"]),
        ),
        summary=DirectiveSummary(
            total=_integer(_single(summary["total"])),
            backlog=_integer(_single(summary["backlog"])),
            ready=_integer(_single(summary["ready"])),
            in_progress=_integer(_single(summary["in-progress"])),
            blocked=_integer(_single(summary["blocked"])),
            done=_integer(_single(summary["done"])),
            progress_pct=_number(_single(summary["progress-pct"])),
        ),
        info=tuple(info),
        assignments=_assignments(fields["assignments"]),
        analysis=analysis,
    )


def _parse_lifecycle(payload: Any) -> DirectiveLifecycleResult:
    row = _tag(payload, "lifecycle")
    fields = _fields(row[1:])
    kind = _text(_single(fields["kind"]))
    if kind not in {"claim", "unclaim", "complete", "block", "unblock"}:
        raise DirectiveProtocolError(f"Unknown directive lifecycle kind: {kind}")
    result = _single(fields["result"])
    if not isinstance(result, list) or len(result) < 2:
        raise DirectiveProtocolError("Directive lifecycle result is malformed.")
    outcome = _text(result[0])
    if outcome == "err":
        if len(result) < 3:
            raise DirectiveProtocolError("Directive lifecycle error is malformed.")
        reason = _text(result[1])
        task = _text(result[2])
        accepted = False
        version = None
        plan_complete = False
    else:
        task = _text(result[1])
        reason = None
        accepted = outcome.startswith(
            ("claimed", "already-", "unclaimed", "completed", "blocked", "unblocked")
        )
        version = (
            _integer(result[2])
            if len(result) >= 3 and isinstance(result[2], (int, float))
            else None
        )
        plan_complete = "plan-complete" in result[2:]
    snapshot_row = _tag(fields["snapshot"], "snapshot")
    snapshot = _parse_snapshot(_single(snapshot_row))
    return DirectiveLifecycleResult(
        kind=kind,  # type: ignore[arg-type]
        outcome=outcome,
        task=task,
        version=version,
        plan_complete=plan_complete,
        accepted=accepted,
        reason=reason,
        snapshot=snapshot,
    )


def _parse_task_state(payload: Any) -> DirectiveTaskState:
    row = _tag(payload, "task-state")
    _arity(row, 3)
    state = _text(row[2])
    if state not in _TASK_STATES:
        raise DirectiveProtocolError(f"Unknown directive task state: {state}")
    return DirectiveTaskState(
        task=_text(row[1]),
        state=state,  # type: ignore[arg-type]
    )


def _parse_validation(payload: Any) -> DirectiveValidation:
    row = _tag(payload, "validation")
    fields = _fields(row[1:])
    return DirectiveValidation(
        valid=_boolean(_single(fields["valid"])),
        strict=_boolean(_single(fields["strict"])),
    )


def _parse_analysis(payload: Any) -> DirectiveAnalysis:
    row = _tag(payload, "analysis")
    fields = _fields(row[1:])
    cycles = tuple(
        tuple(_text(item) for item in group)
        for group in _collection(fields["cycles"], 1)
    )
    rendered = _boolean(_single(fields["rendered"])) if "rendered" in fields else None
    return DirectiveAnalysis(
        cycles=cycles,
        consistent=_boolean(_single(fields["consistent"])),
        rendered=rendered,
    )


def _parse_trace(payload: Any) -> dict[str, bool]:
    row = _tag(payload, "trace")
    fields = _fields(row[1:])
    return {"rendered": _boolean(_single(fields["rendered"]))}


def _parse_markdown(payload: Any) -> str:
    row = _tag(payload, "markdown")
    return _text(_single(row))


def _assignments(atom: Any) -> tuple[DirectiveAssignment, ...]:
    row = atom if isinstance(atom, list) and atom and atom[0] == "assignments" else None
    collection = _collection(row, 1) if row is not None else _collection(atom, 1)
    result = []
    for item in collection:
        assignment = _tag(item, "assign")
        _arity(assignment, 4)
        result.append(
            DirectiveAssignment(
                task=_text(assignment[1]),
                agent=_text(assignment[2]),
                rule=_text(assignment[3]),
            )
        )
    return tuple(result)


def _fields(rows: list[Any]) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}
    for row in rows:
        if not isinstance(row, list) or not row:
            raise DirectiveProtocolError("Directive field is malformed.")
        name = _text(row[0])
        if name in result:
            raise DirectiveProtocolError(f"Directive field is duplicated: {name}")
        result[name] = row
    return result


def _tag(atom: Any, expected: str) -> list[Any]:
    if not isinstance(atom, list) or not atom or atom[0] != expected:
        received = atom[0] if isinstance(atom, list) and atom else atom
        raise DirectiveProtocolError(
            f"Expected directive {expected}, received {received}."
        )
    return atom


def _collection(row: Any, index: int) -> list[Any]:
    if (
        not isinstance(row, list)
        or len(row) <= index
        or not isinstance(row[index], list)
    ):
        raise DirectiveProtocolError("Directive collection is malformed.")
    return row[index]


def _strings(row: list[Any]) -> tuple[str, ...]:
    return tuple(_text(item) for item in _collection(row, 1))


def _single(row: list[Any]) -> Any:
    _arity(row, 2)
    return row[1]


def _arity(row: list[Any], expected: int) -> None:
    if len(row) != expected:
        raise DirectiveProtocolError(
            f"Directive record has arity {len(row)}, expected {expected}."
        )


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise DirectiveProtocolError("Directive text field is empty or malformed.")
    return value


def _boolean(value: Any) -> bool:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    raise DirectiveProtocolError(f"Directive boolean is malformed: {value}")


def _number(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DirectiveProtocolError(f"Directive number is malformed: {value}")
    return value


def _integer(value: Any) -> int:
    number = _number(value)
    if not isinstance(number, int):
        raise DirectiveProtocolError(f"Directive integer is malformed: {value}")
    return number


__all__ = ["PROTOCOL_VERSION", "parse_directive_output"]

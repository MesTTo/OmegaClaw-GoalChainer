"""Purpose: run a caller-written durable plan's reads and claim lifecycle, each change made by the agent its caller names, through lib_directive, the MeTTa directive layer GoalChainer carries, in-process on pymetta under each caller's RunBudget."""

from __future__ import annotations

import fcntl
import hashlib
import os
import stat
import tempfile
from contextlib import contextmanager
from copy import copy
from functools import partial
from pathlib import Path
from typing import Any, BinaryIO, Iterator

from .deontic_engine import DEONTIC_DIRECTORY, DEONTIC_LIBRARY
from .directive_models import (
    DirectiveInvalidInputError,
    DirectivePlanError,
    DirectiveRun,
    DirectiveSnapshot,
    directive_board_lanes,
)
from .directive_protocol import parse_directive_output
from .errors import MettaEngineError
from .runtime.budget import RunBudget, run_bounded
from .runtime.engine import metta_engine
from .runtime.modules import MettaLibrary, initialize_once, load_metta_module, register_metta_library
from .sexpr.codec import SexprCodec

# The adapter ships inside the package beside this module, so an installed GoalChainer runs it.
# am[implements a-ev-directive-own-library@dd12a7]
ADAPTER_PATH = Path(__file__).resolve().parent / "goalchainer_directive.metta"
DIRECTIVE_LIBRARY = DEONTIC_DIRECTORY / "lib_directive.metta"
# The Markdown library the package carries renders an audit's authored tree, registered for the
# directive program as the library markdown.
# am[implements a-rt-p3-callers-1017@69a49e]
MARKDOWN_DIRECTORY = Path(__file__).resolve().parent / "markdown_library"
MARKDOWN_LIBRARY = MettaLibrary("markdown", "markdown")
DIRECTIVE_RUNTIME = "GoalChainer lib_directive in-process on pymetta"
# The adapter, lib_directive and the Markdown library load once per process into a space of their
# own, outside any speculation, as each SNARS world does, named with the & prefix by which the
# engine recognizes a freshly named space, as a module group's space is named.
# am[implements a-ev-rb-directive-inprocess-1018@7bd2f6] am[related a-rt-snars-worlds-by-includes-1017@54c05f]
# am[implements a-dg-amp-group-spaces-1019@9b4cf8] am[rests-on c-dg-unrecognized-space-defects-1019@e59ed6]
DIRECTIVE_SETUP = "directive"
DIRECTIVE_SPACE = "&gc-directive"
_LIFECYCLE_OPERATIONS = frozenset(
    {"claim", "unclaim", "complete", "block", "unblock"}
)
_SNAPSHOT_VIEWS = frozenset(
    {"snapshot", "status", "next", "board", "summary", "info", "assignments"}
)
_READ_OPERATIONS = _SNAPSHOT_VIEWS | frozenset(
    {"markdown", "validate", "analyze", "trace", "task-state"}
)
class DirectiveRuntime:
    """Run the versioned MeTTa adapter and lib_directive in-process on the process's pymetta engine.

    A runtime made here runs nothing: `bounded(budget)` gives the runtime bound to its caller's
    RunBudget, and every operation of that runtime is charged to the budget, inferences and wall
    time alike, so no directive work escapes the request it serves.
    """

    _budget: RunBudget | None = None

    # am[implements a-ev-directive-own-library@dd12a7] am[related a-rt-sexpr-codec-packaged-1017@608f80]
    # am[implements a-ev-rb-directive-inprocess-1018@7bd2f6]
    def __init__(self) -> None:
        self.codec = SexprCodec()
        for path in (DIRECTIVE_LIBRARY, ADAPTER_PATH):
            if not path.is_file():
                raise DirectivePlanError(
                    "GoalChainer's directive library is missing from its package.",
                    details={"path": str(path)},
                )

    # A request's directive work runs inside the request's one budget
    # (c-integrate-request-budget-required-1018), so the request binds its budget to the runtime it
    # uses.
    # am[implements a-ev-rb-pipeline-budget-1018@988a39]
    def bounded(self, budget: RunBudget) -> DirectiveRuntime:
        """This runtime with every operation charged to `budget` and run within what is left of it."""

        if not isinstance(budget, RunBudget):
            raise DirectiveInvalidInputError(
                "A bounded directive runtime takes its request's RunBudget.",
                details={"budget": repr(budget)},
            )
        runtime = copy(self)
        runtime._budget = budget
        return runtime

    def snapshot(self, path: Path) -> DirectiveRun:
        return self._path_operation("gc-directive-snapshot", "snapshot", path)

    def task_state(self, path: Path, task: str) -> DirectiveRun:
        return self._path_operation(
            "gc-directive-task-state",
            "task-state",
            path,
            self.codec.symbol(task),
        )

    def validate(self, path: Path, *, strict: bool = False) -> DirectiveRun:
        return self._path_operation(
            "gc-directive-validate",
            "validate",
            path,
            self.codec.symbol("True" if strict else "False"),
        )

    def analyze(self, path: Path) -> DirectiveRun:
        return self._path_operation("gc-directive-analyze", "analyze", path)

    def trace(self, path: Path) -> DirectiveRun:
        return self._path_operation("gc-directive-trace", "trace", path)

    # am[implements a-rt-p3-callers-1017@69a49e]
    def render_markdown(self, source: str) -> DirectiveRun:
        return self._execute(
            self.codec.expression(
                "gc-directive-markdown",
                self.codec.string(source),
            ),
            expected_operation="markdown",
        )

    # am[implements a-ev-rb-directive-inprocess-1018@7bd2f6]
    def lifecycle(
        self,
        path: Path,
        operation: str,
        task: str,
        agent: str,
        *,
        force: bool = False,
    ) -> DirectiveRun:
        if operation not in _LIFECYCLE_OPERATIONS:
            raise DirectiveInvalidInputError(
                f"Unknown directive lifecycle operation: {operation}"
            )
        arguments = [
            self.codec.symbol(task),
            self.codec.symbol(agent),
        ]
        if operation == "claim":
            arguments.append(self.codec.symbol("True" if force else "False"))
        return self._path_operation(
            f"gc-directive-{operation}",
            "lifecycle",
            path,
            *arguments,
            writes=True,
        )

    # am[implements a-ev-rb-directive-inprocess-1018@7bd2f6]
    def _path_operation(
        self,
        function: str,
        expected_operation: str,
        path: Path,
        *arguments: Any,
        writes: bool = False,
    ) -> DirectiveRun:
        return self._execute(
            self.codec.expression(
                function,
                self.codec.string(str(path)),
                *arguments,
            ),
            expected_operation=expected_operation,
            writes=writes,
        )

    # A read runs in the directive's space inside speculation, which rolls back every space write and
    # dynamic Prolog fact it made. A lifecycle change runs outside speculation: it appends to the plan
    # and then reasons over the plan again in the same call, and under speculation that second pass
    # answers the plan as it was before the append, where PeTTa answers it after. Each lifecycle
    # function resets and reloads the plan before it reasons, so what one change leaves in the
    # engine decides nothing later. The answer's text is what the directive protocol has always parsed.
    # Time: one engine run; speculation also discards what a read compiled, so each read pays
    # lib_directive's first-call compilation again, about 1.3 million inferences for a snapshot,
    # charged to the budget like every lifecycle change's inferences.
    # am[implements a-ev-directive-own-library@dd12a7] am[implements a-ev-rb-directive-inprocess-1018@7bd2f6]
    # am[addresses i-integrate-directive-budget-deadline-only-1018@9f0377]
    # am[rests-on c-rt-speculative-scope-process-wide-1017@008e5b] am[rests-on c-rt-speculate-covers-dynamic-db-1016@752bd1]
    # am[rests-on c-ev-lib-directive-inprocess-1018@b82ce0] am[rests-on c-ev-directive-speculative-mutation-stale-1018@bb0189]
    # am[implements a-integrate-pymetta-public-errors-1019@05202a]
    def _execute(self, expression: Any, *, expected_operation: str, writes: bool = False) -> DirectiveRun:
        from metta.errors import MettaError  # noqa: PLC0415 (metta_engine has already imported it)

        budget = self._budget
        if budget is None:
            raise DirectiveInvalidInputError(
                "A directive operation runs only under its caller's RunBudget; bind one with bounded(budget).",
                details={"operation": expected_operation},
            )
        with metta_engine(budget) as engine:
            initialize_once(DIRECTIVE_SETUP, partial(_load_directive, budget=budget.deadline_only()), budget=budget)
            space = engine.space(DIRECTIVE_SPACE)
            source = "!" + self.codec.emit(expression)
            try:
                if writes:
                    answers, _ = run_bounded(space, source, budget=budget)
                else:
                    with space.speculative():
                        answers, _ = run_bounded(space, source, budget=budget)
            except MettaError as error:
                raise MettaEngineError(
                    f"lib_directive failed on {expected_operation}: {error}",
                    details={"operation": expected_operation, "error": type(error).__name__},
                ) from error
        return parse_directive_output(
            [str(atom) for group in answers for atom in group],
            self.codec,
            expected_operation=expected_operation,
        )


# The deontic and Markdown libraries are registered under the names the adapter imports them by,
# the deontic one at the directory the reviews' engine registers, and the adapter imports
# lib_directive. The load runs within what is left of the first bound budget's deadline and is
# charged no inferences, being fixed per-process work, as a module group's preparation is.
# am[implements a-ev-rb-directive-inprocess-1018@7bd2f6] am[rests-on c-rel-one-deadline-1016@75de2a]
def _load_directive(engine: Any, *, budget: RunBudget) -> None:
    register_metta_library(DEONTIC_LIBRARY.name, DEONTIC_DIRECTORY, budget=budget)
    register_metta_library(MARKDOWN_LIBRARY.name, MARKDOWN_DIRECTORY, budget=budget)
    space = engine.space(DIRECTIVE_SPACE)
    load_metta_module(engine, MARKDOWN_LIBRARY, budget=budget, space=space)
    load_metta_module(engine, ADAPTER_PATH, budget=budget, space=space)


class DirectiveSession:
    """Coordinate reads and append-only lifecycle changes for one plan file."""

    # am[implements a-ev-rb-directive-inprocess-1018@7bd2f6]
    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        runtime: DirectiveRuntime,
    ) -> None:
        self.path = _existing_plan_path(path)
        self._identity = _plan_identity(self.path)
        self.runtime = runtime

    def snapshot(self) -> DirectiveRun:
        return self._read(self.runtime.snapshot)

    def digest(self) -> str:
        with _locked_plan(
            self.path,
            expected_identity=self._identity,
        ) as (handle, _):
            return _handle_digest(handle)

    def task_state(self, task: str) -> DirectiveRun:
        _validate_symbol(task, "task")
        return self._read(lambda path: self.runtime.task_state(path, task))

    def validate(self, *, strict: bool = False) -> DirectiveRun:
        return self._read(lambda path: self.runtime.validate(path, strict=strict))

    def analyze(self) -> DirectiveRun:
        return self._read(self.runtime.analyze)

    def trace(self) -> DirectiveRun:
        return self._read(self.runtime.trace)

    # am[related a-rt-p3-callers-1017@69a49e]
    def markdown(self) -> DirectiveRun:
        with _locked_plan(
            self.path,
            expected_identity=self._identity,
        ) as (handle, runtime_path):
            digest = _handle_digest(handle)
            snapshot_run = self.runtime.snapshot(runtime_path)
            snapshot = snapshot_run.value
            if not isinstance(snapshot, DirectiveSnapshot):
                raise DirectivePlanError("Directive plan returned no snapshot.")
            source = _handle_text(handle, self.path)
            run = self.runtime.render_markdown(
                build_markdown_document(
                    snapshot,
                    runtime=self.runtime,
                )
            )
            if not isinstance(run.value, str):
                raise DirectivePlanError(
                    "Markdown rendering returned no audit document."
                )
            rendered = (
                run.value.rstrip()
                + "\n\n## Plan and lifecycle log\n\n```metta\n"
                + source.rstrip()
                + "\n```"
            )
            return DirectiveRun(
                operation=run.operation,
                value=rendered,
                transcript=run.transcript,
                plan_path=str(self.path),
                digest_before=digest,
                digest_after=_handle_digest(handle),
            )

    # Every lifecycle change names the agent making it: a caller-written plan declares its own
    # agents, so no default could name one the caller chose.
    # am[implements a-integrate-directive-explicit-agent-1018@54e84d]
    def claim(
        self,
        task: str,
        agent: str,
        *,
        force: bool = False,
    ) -> DirectiveRun:
        return self._lifecycle("claim", task, agent, force=force)

    # am[implements a-integrate-directive-explicit-agent-1018@54e84d]
    def unclaim(self, task: str, agent: str) -> DirectiveRun:
        return self._lifecycle("unclaim", task, agent)

    # am[implements a-integrate-directive-explicit-agent-1018@54e84d]
    def complete(self, task: str, agent: str) -> DirectiveRun:
        return self._lifecycle("complete", task, agent)

    # am[implements a-integrate-directive-explicit-agent-1018@54e84d]
    def block(self, task: str, agent: str) -> DirectiveRun:
        return self._lifecycle("block", task, agent)

    # am[implements a-integrate-directive-explicit-agent-1018@54e84d]
    def unblock(self, task: str, agent: str) -> DirectiveRun:
        return self._lifecycle("unblock", task, agent)

    def _read(self, operation) -> DirectiveRun:
        with _locked_plan(
            self.path,
            expected_identity=self._identity,
        ) as (handle, runtime_path):
            digest = _handle_digest(handle)
            run = operation(runtime_path)
            return DirectiveRun(
                operation=run.operation,
                value=run.value,
                transcript=run.transcript,
                plan_path=str(self.path),
                digest_before=digest,
                digest_after=_handle_digest(handle),
            )

    def _lifecycle(
        self,
        operation: str,
        task: str,
        agent: str,
        *,
        force: bool = False,
    ) -> DirectiveRun:
        _validate_symbol(task, "task")
        _validate_symbol(agent, "agent")
        with _locked_plan(
            self.path,
            exclusive=True,
            expected_identity=self._identity,
        ) as (handle, runtime_path):
            before = _handle_digest(handle)
            run = self.runtime.lifecycle(
                runtime_path,
                operation,
                task,
                agent,
                force=force,
            )
            handle.flush()
            os.fsync(handle.fileno())
            after = _handle_digest(handle)
            return DirectiveRun(
                operation=run.operation,
                value=run.value,
                transcript=run.transcript,
                plan_path=str(self.path),
                digest_before=before,
                digest_after=after,
            )


# A directive operation is a request of its own (c-integrate-request-budget-required-1018), so every
# program it runs is bound by its caller's deadline. Every operation works on the plan its caller
# names, and every lifecycle change on the task and agent its caller names.
# am[implements a-ev-rb-pipeline-budget-1018@988a39] am[implements a-ie-s6-directive-generic-1018@e69fb4]
# am[implements a-integrate-directive-explicit-agent-1018@54e84d]
def run_directive_request(
    payload: dict[str, Any],
    *,
    runtime: DirectiveRuntime | None = None,
    budget: RunBudget,
) -> dict[str, Any]:
    """Run one validated directive operation for CLI and OmegaClaw callers under `budget`."""

    if not isinstance(payload, dict):
        raise DirectiveInvalidInputError(
            "Directive dispatch request must be a JSON object."
        )
    operation = payload.get("operation")
    allowed = sorted(_READ_OPERATIONS | _LIFECYCLE_OPERATIONS)
    if not isinstance(operation, str) or operation not in allowed:
        raise DirectiveInvalidInputError(
            "Unknown directive dispatch operation.",
            details={"operation": operation, "available": allowed},
        )
    request_fields = {"operation", "plan"}
    if operation in _LIFECYCLE_OPERATIONS | {"task-state"}:
        request_fields.add("task")
    if operation in _LIFECYCLE_OPERATIONS:
        request_fields.add("agent")
    if operation == "claim":
        request_fields.add("force")
    if operation == "validate":
        request_fields.add("strict")
    if not all(isinstance(field, str) for field in payload):
        raise DirectiveInvalidInputError(
            "Directive dispatch field names must be strings."
        )
    unknown = sorted(set(payload) - request_fields)
    if unknown:
        raise DirectiveInvalidInputError(
            "Directive dispatch request contains unknown fields.",
            details={"unknown": unknown},
        )
    plan_path = payload.get("plan")
    if not isinstance(plan_path, str) or not plan_path:
        raise DirectiveInvalidInputError(
            "Directive plan is required for this operation."
        )
    task = payload.get("task")
    if operation in _LIFECYCLE_OPERATIONS | {"task-state"}:
        if not isinstance(task, str):
            raise DirectiveInvalidInputError("Directive task must be a string.")
        _validate_symbol(task, "task")
    agent = payload.get("agent")
    if operation in _LIFECYCLE_OPERATIONS:
        if agent is None:
            raise DirectiveInvalidInputError(
                "Directive lifecycle operations require the agent making the change.",
                details={"operation": operation, "missing": ["agent"]},
            )
        if not isinstance(agent, str):
            raise DirectiveInvalidInputError("Directive agent must be a string.")
        _validate_symbol(agent, "agent")
    strict = payload.get("strict", False)
    if operation == "validate" and not isinstance(strict, bool):
        raise DirectiveInvalidInputError("Directive strict must be a boolean.")
    force = payload.get("force", False)
    if operation == "claim" and not isinstance(force, bool):
        raise DirectiveInvalidInputError("Directive force must be a boolean.")

    engine = (runtime or DirectiveRuntime()).bounded(budget)
    session = DirectiveSession(plan_path, runtime=engine)
    if operation in _SNAPSHOT_VIEWS:
        run = session.snapshot()
        result = run.to_dict()
        if operation != "snapshot":
            key = "next_actions" if operation == "next" else operation
            result["result"] = result["result"][key]
            result["operation"] = operation
        return result
    if operation == "markdown":
        return session.markdown().to_dict()
    if operation == "validate":
        return session.validate(strict=strict).to_dict()
    if operation == "analyze":
        return session.analyze().to_dict()
    if operation == "trace":
        return session.trace().to_dict()
    if operation == "task-state":
        return session.task_state(task).to_dict()

    method = getattr(session, operation)
    keywords = {"force": force} if operation == "claim" else {}
    return method(task, agent, **keywords).to_dict()


def create_plan(
    path: str | os.PathLike[str],
    plan: str,
) -> Path:
    """Create a new mode-0600 plan without replacing an existing audit log."""

    destination = _new_plan_path(path)
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise DirectivePlanError(
            "Directive plan already exists.",
            details={"path": str(destination)},
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(plan)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


# am[implements a-ev-directive-own-library@dd12a7]
def build_markdown_document(
    snapshot: DirectiveSnapshot,
    *,
    runtime: DirectiveRuntime | None = None,
) -> str:
    """Encode an orchestration audit in the MeTTa Markdown authoring form."""

    engine = runtime or DirectiveRuntime()
    codec = engine.codec
    states: list[tuple[str, str]] = []
    for state, tasks in directive_board_lanes(snapshot.board):
        states.extend((task, state) for task in tasks)
    board = codec.expression(
        "table",
        codec.expression("id", codec.symbol("board")),
        codec.expression("align", codec.symbol("none"), codec.symbol("none")),
        codec.expression(
            "head",
            codec.string("Task"),
            codec.string("State"),
        ),
        *(
            codec.expression(
                "row",
                codec.string(task),
                codec.string(state),
            )
            for task, state in sorted(states)
        ),
    )
    assignments = codec.expression(
        "table",
        codec.expression("id", codec.symbol("assignments")),
        codec.expression(
            "align",
            codec.symbol("none"),
            codec.symbol("none"),
            codec.symbol("none"),
        ),
        codec.expression(
            "head",
            codec.string("Task"),
            codec.string("Agent"),
            codec.string("Rule"),
        ),
        *(
            codec.expression(
                "row",
                codec.string(row.task),
                codec.string(row.agent),
                codec.string(row.rule),
            )
            for row in snapshot.assignments
        ),
    )
    summary = codec.expression(
        "table",
        codec.expression("id", codec.symbol("summary")),
        codec.expression("align", codec.symbol("none"), codec.symbol("right")),
        codec.expression(
            "head",
            codec.string("Measure"),
            codec.string("Value"),
        ),
        *(
            codec.expression("row", codec.string(name), codec.string(str(value)))
            for name, value in (
                ("Total", snapshot.summary.total),
                ("Backlog", snapshot.summary.backlog),
                ("Ready", snapshot.summary.ready),
                ("In progress", snapshot.summary.in_progress),
                ("Blocked", snapshot.summary.blocked),
                ("Done", snapshot.summary.done),
                ("Progress percent", snapshot.summary.progress_pct),
            )
        ),
    )
    document = codec.expression(
        "md",
        codec.symbol("goalchainer-directive-audit"),
        codec.expression("h1", codec.string("GoalChainer directive audit")),
        codec.expression(
            "p",
            codec.string(
                "lib_directive derives this board from the durable MeTTa plan."
            ),
        ),
        codec.expression("h2", codec.string("Board")),
        board,
        codec.expression("h2", codec.string("Assignments")),
        assignments,
        codec.expression("h2", codec.string("Summary")),
        summary,
    )
    return codec.emit(document)


@contextmanager
def _prepared_plan(
    plan: str,
    plan_path: str | os.PathLike[str] | None,
) -> Iterator[tuple[Path, bool]]:
    if plan_path is not None:
        yield create_plan(plan_path, plan), True
        return
    descriptor, temporary = tempfile.mkstemp(
        prefix="goalchainer-directive-",
        suffix=".metta",
        text=True,
    )
    path = Path(temporary)
    try:
        os.chmod(path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(plan)
            handle.flush()
            os.fsync(handle.fileno())
        yield path, False
    finally:
        path.unlink(missing_ok=True)


def _new_plan_path(path: str | os.PathLike[str]) -> Path:
    destination = Path(path).expanduser().absolute()
    if destination.suffix != ".metta":
        raise DirectiveInvalidInputError(
            "Directive plan path must end in .metta.",
            details={"path": str(destination)},
        )
    if not destination.parent.is_dir():
        raise DirectivePlanError(
            "Directive plan parent directory does not exist.",
            details={"path": str(destination.parent)},
        )
    if destination.is_symlink():
        raise DirectivePlanError(
            "Directive plan path must not be a symbolic link.",
            details={"path": str(destination)},
        )
    return destination


def _existing_plan_path(path: str | os.PathLike[str]) -> Path:
    candidate = _new_plan_path(path)
    if not candidate.is_file():
        raise DirectivePlanError(
            "Directive plan does not exist or is not a regular file.",
            details={"path": str(candidate)},
        )
    if not os.access(candidate, os.R_OK):
        raise DirectivePlanError(
            "Directive plan is not readable.",
            details={"path": str(candidate)},
        )
    return candidate


def _validate_symbol(value: str, name: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or any(character.isspace() or character in '();"\\' for character in value)
    ):
        raise DirectiveInvalidInputError(
            f"Directive {name} must be a safe MeTTa symbol.",
            details={name: value},
        )


@contextmanager
def _locked_plan(
    path: Path,
    *,
    exclusive: bool = False,
    expected_identity: tuple[int, int] | None = None,
) -> Iterator[tuple[BinaryIO, Path]]:
    flags = os.O_RDWR if exclusive else os.O_RDONLY
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise DirectivePlanError(
            "Directive plan could not be opened safely.",
            details={"path": str(path), "error": str(exc)},
        ) from exc
    mode = "r+b" if exclusive else "rb"
    with os.fdopen(descriptor, mode) as handle:
        file_stat = os.fstat(handle.fileno())
        if not stat.S_ISREG(file_stat.st_mode):
            raise DirectivePlanError(
                "Directive plan is not a regular file.",
                details={"path": str(path)},
            )
        identity = (file_stat.st_dev, file_stat.st_ino)
        if expected_identity is not None and identity != expected_identity:
            raise DirectivePlanError(
                "Directive plan changed since the session was created.",
                details={"path": str(path)},
            )
        _assert_plan_identity(path, file_stat)
        fcntl.flock(
            handle.fileno(),
            fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH,
        )
        runtime_path = Path(f"/proc/{os.getpid()}/fd/{handle.fileno()}")
        yield handle, runtime_path
        _assert_plan_identity(path, os.fstat(handle.fileno()))


def _plan_identity(path: Path) -> tuple[int, int]:
    with _locked_plan(path) as (handle, _):
        file_stat = os.fstat(handle.fileno())
        return file_stat.st_dev, file_stat.st_ino


def _assert_plan_identity(path: Path, file_stat: os.stat_result) -> None:
    try:
        path_stat = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise DirectivePlanError(
            "Directive plan path changed during the operation.",
            details={"path": str(path), "error": str(exc)},
        ) from exc
    if (
        path_stat.st_dev != file_stat.st_dev
        or path_stat.st_ino != file_stat.st_ino
    ):
        raise DirectivePlanError(
            "Directive plan path changed during the operation.",
            details={"path": str(path)},
        )


def _handle_bytes(handle: BinaryIO) -> bytes:
    size = os.fstat(handle.fileno()).st_size
    chunks = []
    offset = 0
    while offset < size:
        chunk = os.pread(
            handle.fileno(),
            min(1024 * 1024, size - offset),
            offset,
        )
        if not chunk:
            raise DirectivePlanError(
                "Directive plan changed while it was being read."
            )
        chunks.append(chunk)
        offset += len(chunk)
    return b"".join(chunks)


def _handle_text(handle: BinaryIO, path: Path) -> str:
    try:
        return _handle_bytes(handle).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DirectivePlanError(
            "Directive plan must be valid UTF-8.",
            details={"path": str(path), "error": str(exc)},
        ) from exc


def _handle_digest(handle: BinaryIO) -> str:
    return hashlib.sha256(_handle_bytes(handle)).hexdigest()


__all__ = [
    "DirectiveRuntime",
    "DirectiveSession",
    "build_markdown_document",
    "create_plan",
    "run_directive_request",
]

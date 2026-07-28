"""Durable GoalChainer orchestration through OmegaClaw's MeTTa directive layer."""

from __future__ import annotations

import fcntl
import hashlib
import os
import stat
import tempfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, BinaryIO, Iterator

from .deontic_engine import ACTION_ORDER
from .directive_models import (
    DirectiveInvalidInputError,
    DirectiveLifecycleResult,
    DirectivePlanError,
    DirectiveRun,
    DirectiveSnapshot,
    directive_board_lanes,
)
from .directive_protocol import parse_directive_output
from .snars_program import SexprCodec
from .snars_runtime import SnarsRuntime

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "integrations" / "directive" / "goalchainer_directive.metta"
DEFAULT_OMEGACLAW_DIR = REPO_ROOT / "external" / "OmegaClaw-Core"
DEVELOPMENT_OMEGACLAW_DIR = Path("/home/user/Dev/OmegaClaw-Core")
AGENT = "responder"
REVIEW_TASK = "review_decision"
_LIFECYCLE_OPERATIONS = frozenset(
    {"claim", "unclaim", "complete", "block", "unblock"}
)
_SNAPSHOT_VIEWS = frozenset(
    {"snapshot", "status", "next", "board", "summary", "info", "assignments"}
)
_READ_OPERATIONS = _SNAPSHOT_VIEWS | frozenset(
    {"markdown", "validate", "analyze", "trace", "task-state"}
)
DEMO_TASKS = ("collect_evidence", "summarize_findings", "publish_update")


class DirectiveRuntime:
    """Invoke the versioned MeTTa adapter on the authoritative PeTTa runtime."""

    def __init__(
        self,
        runtime: SnarsRuntime | None = None,
        *,
        omegaclaw_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        self.runtime = runtime or SnarsRuntime(require_text_ingestion=False)
        self.codec = SexprCodec(self.runtime)
        self.omegaclaw_dir = _resolve_omegaclaw_dir(omegaclaw_dir)
        library_import = (
            "!(import! &self "
            f"{self.codec.emit(self.codec.string(str(self.omegaclaw_dir / 'lib_directive.metta')))})"
        )
        adapter = ADAPTER_PATH.read_text(encoding="utf-8")
        self._adapter = adapter.replace(
            "!(import! &self (library OmegaClaw-Core lib_directive))",
            library_import,
            1,
        )
        if self._adapter == adapter:
            raise DirectivePlanError(
                "GoalChainer directive adapter has no OmegaClaw import marker."
            )

    def classify(self, deontic_by_action: dict[str, str]) -> dict[str, str]:
        rows = [
            [
                self.codec.symbol(action),
                self.codec.symbol(deontic_by_action.get(action, "unregulated")),
            ]
            for action in ACTION_ORDER
        ]
        run = self._execute(
            self.codec.expression("gc-directive-classify", rows),
            expected_operation="classify",
        )
        if not isinstance(run.value, dict):
            raise DirectivePlanError("Directive classification returned no task states.")
        return run.value

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

    def render_markdown(self, source: str) -> DirectiveRun:
        return self._execute(
            self.codec.expression(
                "gc-directive-markdown",
                self.codec.string(source),
            ),
            expected_operation="markdown",
            imports=("!(import! &self lib/mettabase/markdown)",),
        )

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
        )

    def _path_operation(
        self,
        function: str,
        expected_operation: str,
        path: Path,
        *arguments: Any,
    ) -> DirectiveRun:
        return self._execute(
            self.codec.expression(
                function,
                self.codec.string(str(path)),
                *arguments,
            ),
            expected_operation=expected_operation,
        )

    def _execute(
        self,
        expression: Any,
        *,
        expected_operation: str,
        imports: tuple[str, ...] = (),
    ) -> DirectiveRun:
        with _library_overlay(self.runtime, self.omegaclaw_dir) as library_base:
            library_prelude = "\n".join(
                (
                    (
                        "!(retractPredicate "
                        "(Predicate (library_path $gc-library)))"
                    ),
                    (
                        "!(assertaPredicate "
                        "(Predicate (library_path "
                        f"{self.codec.emit(self.codec.string(str(library_base)))})))"
                    ),
                )
            )
            program = (
                library_prelude
                + "\n"
                + "\n".join(imports)
                + ("\n" if imports else "")
                + self._adapter
                + "\n!"
                + self.codec.emit(expression)
                + "\n"
            )
            result = self.runtime.run_batch(program)
        return parse_directive_output(
            result.stdout.splitlines(),
            self.codec,
            expected_operation=expected_operation,
        )


def _resolve_omegaclaw_dir(
    explicit: str | os.PathLike[str] | None,
) -> Path:
    configured = (
        Path(explicit).expanduser().absolute()
        if explicit is not None
        else Path(os.environ["GOALCHAINER_OMEGACLAW_DIR"]).expanduser().absolute()
        if os.environ.get("GOALCHAINER_OMEGACLAW_DIR")
        else DEFAULT_OMEGACLAW_DIR
        if DEFAULT_OMEGACLAW_DIR.is_dir()
        else DEVELOPMENT_OMEGACLAW_DIR
    )
    resolved = configured.resolve()
    if (
        resolved.name != "OmegaClaw-Core"
        or not (resolved / "lib_directive.metta").is_file()
    ):
        raise DirectivePlanError(
            "OmegaClaw Core directive library is unavailable.",
            details={"path": str(resolved)},
        )
    return resolved


@contextmanager
def _library_overlay(
    runtime: SnarsRuntime,
    omegaclaw_dir: Path,
) -> Iterator[Path]:
    """Expose one pinned OmegaClaw beside PeTTa's required import helper."""

    with tempfile.TemporaryDirectory(prefix="goalchainer-petta-library-") as raw:
        root = Path(raw)
        library_base = root / "lib"
        library_base.mkdir(mode=0o700)
        petta_library = runtime.diagnostics.petta_dir / "lib"
        for filename in ("lib_import.metta", "lib_import.pl"):
            source = petta_library / filename
            if not source.is_file():
                raise DirectivePlanError(
                    "PeTTa import helper is unavailable.",
                    details={"path": str(source)},
                )
            (library_base / filename).symlink_to(source)
        (root / "OmegaClaw-Core").symlink_to(
            omegaclaw_dir,
            target_is_directory=True,
        )
        yield library_base


class DirectiveSession:
    """Coordinate reads and append-only lifecycle changes for one plan file."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        runtime: DirectiveRuntime | None = None,
    ) -> None:
        self.path = _existing_plan_path(path)
        self._identity = _plan_identity(self.path)
        self.runtime = runtime or DirectiveRuntime()

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
                    "Mettabase returned no Markdown audit document."
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

    def claim(
        self,
        task: str,
        agent: str = AGENT,
        *,
        force: bool = False,
    ) -> DirectiveRun:
        return self._lifecycle("claim", task, agent, force=force)

    def unclaim(self, task: str, agent: str = AGENT) -> DirectiveRun:
        return self._lifecycle("unclaim", task, agent)

    def complete(self, task: str, agent: str = AGENT) -> DirectiveRun:
        return self._lifecycle("complete", task, agent)

    def block(self, task: str, agent: str = AGENT) -> DirectiveRun:
        return self._lifecycle("block", task, agent)

    def unblock(self, task: str, agent: str = AGENT) -> DirectiveRun:
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


def register_directive(
    deontic_by_action: dict[str, str],
    *,
    selected_action: str | None = None,
    plan_path: str | os.PathLike[str] | None = None,
    claim: bool = True,
    runtime: DirectiveRuntime | None = None,
) -> dict[str, Any]:
    """Create an incident plan, inspect it, and optionally claim selected work."""

    engine = runtime or DirectiveRuntime()
    states = engine.classify(deontic_by_action)
    plan = build_plan(states, review_complete=True)
    selected = selected_action or next(
        (action for action in ACTION_ORDER if states.get(action) == "ready"),
        None,
    )
    if selected is not None:
        _validate_action(selected)

    with _prepared_plan(plan, plan_path) as (path, durable):
        session = DirectiveSession(path, runtime=engine)
        before = session.snapshot()
        if not isinstance(before.value, DirectiveSnapshot):
            raise DirectivePlanError("Directive plan returned no initial snapshot.")
        before_snapshot = before.value
        lifecycle = session.claim(selected) if claim and selected else None
        current = (
            lifecycle.value.snapshot
            if lifecycle is not None
            and isinstance(lifecycle.value, DirectiveLifecycleResult)
            else before.value
        )
        if not isinstance(current, DirectiveSnapshot):
            raise DirectivePlanError("Directive plan returned no snapshot.")

        claim_payload = None
        if lifecycle is not None:
            result = lifecycle.value
            if not isinstance(result, DirectiveLifecycleResult):
                raise DirectivePlanError("Directive claim returned no lifecycle result.")
            claim_payload = {
                "task": result.task,
                "version": result.version,
                "agent": AGENT,
                "outcome": result.outcome,
                "accepted": result.accepted,
                "reason": result.reason,
            }
        markdown = session.markdown()
        return {
            "skill": "goalchainer-directive",
            "runtime": "OmegaClaw-Core lib_directive on PeTTa",
            "protocol": "goalchainer-directive-v1",
            "plan_path": str(path) if durable else None,
            "durable": durable,
            "plan_digest": session.digest(),
            "classification": {
                action: {
                    "deontic": deontic_by_action.get(action, "unregulated"),
                    "task_state": states[action],
                }
                for action in ACTION_ORDER
            },
            "task_states": states,
            "plan": plan,
            "status": _legacy_status(current),
            "next_actions": [
                {
                    "task": row.task,
                    "agent": row.agent,
                    "rule": row.rule,
                }
                for row in before_snapshot.next_actions
            ],
            "claim": claim_payload,
            "snapshot": current.to_dict(),
            "markdown": markdown.value,
            "audit": {
                "initial": before.to_dict(),
                "lifecycle": lifecycle.to_dict() if lifecycle else None,
            },
        }


def execute_with_directive(
    action: str,
    deontic_by_action: dict[str, str],
    execute,
    *,
    plan_path: str | os.PathLike[str] | None = None,
    runtime: DirectiveRuntime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Claim selected work, execute it, then complete or block it."""

    _validate_action(action)
    engine = runtime or DirectiveRuntime()
    states = engine.classify(deontic_by_action)
    if states[action] != "ready":
        raise DirectivePlanError(
            "The selected action is not ready in the directive plan.",
            details={"action": action, "state": states[action]},
        )
    plan = build_plan(states, review_complete=True)
    with _prepared_plan(plan, plan_path) as (path, durable):
        session = DirectiveSession(path, runtime=engine)
        initial = session.snapshot()
        claim = session.claim(action)
        claim_value = claim.value
        if (
            not isinstance(claim_value, DirectiveLifecycleResult)
            or not claim_value.accepted
        ):
            reason = (
                claim_value.reason
                if isinstance(claim_value, DirectiveLifecycleResult)
                else "malformed lifecycle result"
            )
            raise DirectivePlanError(
                "Directive runtime rejected the selected action claim.",
                details={"action": action, "reason": reason},
            )

        try:
            execution = execute(action)
        except Exception as execution_error:
            try:
                session.block(action)
            except Exception as block_error:
                execution_error.add_note(
                    "Directive failure block also failed: "
                    f"{type(block_error).__name__}: {block_error}"
                )
            raise

        safe = bool(execution.get("leak_check", {}).get("safe"))
        authorized = bool(execution.get("authorized", True))
        final = (
            session.complete(action)
            if safe and authorized
            else session.block(action)
        )
        final_value = final.value
        if (
            not isinstance(final_value, DirectiveLifecycleResult)
            or not final_value.accepted
        ):
            reason = (
                final_value.reason
                if isinstance(final_value, DirectiveLifecycleResult)
                else "malformed lifecycle result"
            )
            raise DirectivePlanError(
                "Directive runtime rejected the post-execution lifecycle change.",
                details={"action": action, "reason": reason},
            )
        markdown = session.markdown()
        return execution, {
            "runtime": "OmegaClaw-Core lib_directive on PeTTa",
            "protocol": "goalchainer-directive-v1",
            "durable": durable,
            "plan_path": str(path) if durable else None,
            "plan_digest": session.digest(),
            "classification": states,
            "initial": initial.to_dict(),
            "claim": claim.to_dict(),
            "final": final.to_dict(),
            "markdown": markdown.value,
            "outcome": "completed" if safe and authorized else "blocked",
        }


def run_directive_request(
    payload: dict[str, Any],
    *,
    runtime: DirectiveRuntime | None = None,
) -> dict[str, Any]:
    """Run one validated directive operation for CLI and OmegaClaw callers."""

    if not isinstance(payload, dict):
        raise DirectiveInvalidInputError(
            "Directive dispatch request must be a JSON object."
        )
    operation = payload.get("operation")
    allowed = sorted(_READ_OPERATIONS | _LIFECYCLE_OPERATIONS | {"demo"})
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
    if operation == "demo":
        if plan_path is not None and not isinstance(plan_path, str):
            raise DirectiveInvalidInputError("Directive plan must be a path string.")
        return run_directive_demo(
            plan_path=plan_path,
            runtime=runtime or DirectiveRuntime(),
        )

    if not isinstance(plan_path, str) or not plan_path:
        raise DirectiveInvalidInputError(
            "Directive plan is required for this operation."
        )
    task = payload.get("task")
    if operation in _LIFECYCLE_OPERATIONS | {"task-state"}:
        if not isinstance(task, str):
            raise DirectiveInvalidInputError("Directive task must be a string.")
        _validate_symbol(task, "task")
    agent = payload.get("agent", AGENT)
    if operation in _LIFECYCLE_OPERATIONS:
        if not isinstance(agent, str):
            raise DirectiveInvalidInputError("Directive agent must be a string.")
        _validate_symbol(agent, "agent")
    strict = payload.get("strict", False)
    if operation == "validate" and not isinstance(strict, bool):
        raise DirectiveInvalidInputError("Directive strict must be a boolean.")
    force = payload.get("force", False)
    if operation == "claim" and not isinstance(force, bool):
        raise DirectiveInvalidInputError("Directive force must be a boolean.")

    engine = runtime or DirectiveRuntime()
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


def classify_task_states(
    deontic_by_action: dict[str, str],
    *,
    runtime: DirectiveRuntime | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Map deontic conclusions through the MeTTa adapter."""

    states = (runtime or DirectiveRuntime()).classify(deontic_by_action)
    return states, [states[action] for action in ACTION_ORDER]


def build_plan(
    states: dict[str, str],
    *,
    review_complete: bool = True,
) -> str:
    """Build a native MeTTa plan whose selected work depends on review."""

    lines = [
        '(meta plan (id "GC-INCIDENT") (title "GoalChainer incident decision")'
        f' (version "2.0.0") (status "active") (created "{date.today().isoformat()}")'
        ' (author "agent:goalchainer"))',
        f"(given agent-{AGENT}-available)",
        f"(given task-{REVIEW_TASK})",
        f"(given no-deps-{REVIEW_TASK})",
        f"(normally r-{REVIEW_TASK} (and task-{REVIEW_TASK} no-deps-{REVIEW_TASK})"
        f" ready-{REVIEW_TASK})",
        f"(normally assign-{REVIEW_TASK} (and ready-{REVIEW_TASK}"
        f" agent-{AGENT}-available) assign-to-{REVIEW_TASK}-{AGENT})",
    ]
    if review_complete:
        lines.append(f"(given completed-{REVIEW_TASK})")
    for action in ACTION_ORDER:
        lines.append(f"(given task-{action})")
    for action in ACTION_ORDER:
        state = states.get(action, "backlog")
        if state == "ready":
            lines += [
                f"(normally r-{action} (and task-{action} completed-{REVIEW_TASK})"
                f" ready-{action})",
                f"(normally assign-{action} (and ready-{action} agent-{AGENT}-available)"
                f" assign-to-{action}-{AGENT})",
            ]
        elif state == "blocked":
            lines += [
                f"(given forbid-{action})",
                f"(normally blk-{action} forbid-{action} blocked-{action})",
            ]
    return "\n".join(lines) + "\n"


def build_demo_plan() -> str:
    """Build the dependency chain used by the live orchestration demo."""

    lines = [
        '(meta plan (id "GC-DEMO") (title "GoalChainer dependency cascade")'
        f' (version "1.0.0") (status "active") (created "{date.today().isoformat()}")'
        ' (author "agent:goalchainer"))',
        f"(given agent-{AGENT}-available)",
    ]
    for task in DEMO_TASKS:
        lines.append(f"(given task-{task})")
    lines += [
        "(given no-deps-collect_evidence)",
        "(normally r-collect_evidence"
        " (and task-collect_evidence no-deps-collect_evidence)"
        " ready-collect_evidence)",
        "(normally r-summarize_findings"
        " (and task-summarize_findings completed-collect_evidence)"
        " ready-summarize_findings)",
        "(normally r-publish_update"
        " (and task-publish_update completed-summarize_findings)"
        " ready-publish_update)",
    ]
    for task in DEMO_TASKS:
        lines.append(
            f"(normally assign-{task} (and ready-{task} agent-{AGENT}-available)"
            f" assign-to-{task}-{AGENT})"
        )
    return "\n".join(lines) + "\n"


def run_directive_demo(
    *,
    plan_path: str | os.PathLike[str] | None = None,
    runtime: DirectiveRuntime | None = None,
) -> dict[str, Any]:
    """Exercise dependency blocking and the complete claim lifecycle on PeTTa."""

    engine = runtime or DirectiveRuntime()
    with _prepared_plan(build_demo_plan(), plan_path) as (path, durable):
        session = DirectiveSession(path, runtime=engine)
        runs = [
            ("initial", session.snapshot()),
            ("blocked-root", session.block("collect_evidence")),
            ("unblocked-root", session.unblock("collect_evidence")),
            ("claimed-root", session.claim("collect_evidence")),
            ("completed-root", session.complete("collect_evidence")),
            ("claimed-summary", session.claim("summarize_findings")),
            ("completed-summary", session.complete("summarize_findings")),
            ("claimed-publish", session.claim("publish_update")),
            ("completed-plan", session.complete("publish_update")),
        ]
        stages = [
            _demo_stage(name, run)
            for name, run in runs
        ]
        blocked_states = stages[1]["task_states"]
        unblocked_states = stages[2]["task_states"]
        final_states = stages[-1]["task_states"]
        verified = {
            "direct_block": blocked_states["collect_evidence"] == "blocked",
            "transitive_upstream_block": (
                blocked_states["summarize_findings"] == "upstream-blocked"
                and blocked_states["publish_update"] == "upstream-blocked"
            ),
            "unblock_clears_cascade": (
                unblocked_states["collect_evidence"] == "ready"
                and unblocked_states["summarize_findings"] == "backlog"
                and unblocked_states["publish_update"] == "backlog"
            ),
            "dependency_gating": (
                stages[4]["task_states"]["summarize_findings"] == "ready"
                and stages[6]["task_states"]["publish_update"] == "ready"
            ),
            "plan_completed": all(
                final_states[task] == "done"
                for task in DEMO_TASKS
            ),
        }
        if not all(verified.values()):
            raise DirectivePlanError(
                "The live directive demo did not satisfy its claimed invariants.",
                details={"verified": verified},
            )
        markdown = session.markdown()
        return {
            "runtime": "OmegaClaw-Core lib_directive on PeTTa",
            "protocol": "goalchainer-directive-v1",
            "operation": "demo",
            "durable": durable,
            "plan_path": str(path) if durable else None,
            "plan_digest": session.digest(),
            "tasks": list(DEMO_TASKS),
            "stages": stages,
            "verified": verified,
            "markdown": markdown.value,
        }


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


def build_markdown_document(
    snapshot: DirectiveSnapshot,
    *,
    runtime: DirectiveRuntime | None = None,
) -> str:
    """Encode an orchestration audit in Mettabase's MeTTa Markdown authoring form."""

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
                "OmegaClaw derives this board from the durable MeTTa plan."
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


def _validate_action(action: str) -> None:
    if action not in ACTION_ORDER:
        raise DirectiveInvalidInputError(
            f"Unknown incident action: {action}",
            details={"available": list(ACTION_ORDER)},
        )


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


def _demo_stage(name: str, run: DirectiveRun) -> dict[str, Any]:
    value = run.value
    snapshot = (
        value.snapshot
        if isinstance(value, DirectiveLifecycleResult)
        else value
    )
    if not isinstance(snapshot, DirectiveSnapshot):
        raise DirectivePlanError("Directive demo stage returned no snapshot.")
    return {
        "stage": name,
        "operation": run.operation,
        "task_states": _snapshot_task_states(snapshot),
        "summary": {
            "backlog": snapshot.summary.backlog,
            "ready": snapshot.summary.ready,
            "in_progress": snapshot.summary.in_progress,
            "blocked": snapshot.summary.blocked,
            "done": snapshot.summary.done,
            "progress_pct": snapshot.summary.progress_pct,
        },
        "event": run.to_dict(),
    }


def _snapshot_task_states(snapshot: DirectiveSnapshot) -> dict[str, str]:
    states = {task: "backlog" for task in snapshot.status.tasks}
    for state, tasks in (
        ("ready", snapshot.status.ready),
        ("in-progress", snapshot.status.claimed),
        ("upstream-blocked", snapshot.status.upstream_blocked),
        ("blocked", snapshot.status.blocked),
        ("done", snapshot.status.completed),
    ):
        for task in tasks:
            states[task] = state
    return states


def _legacy_status(snapshot: DirectiveSnapshot) -> dict[str, list[str]]:
    return {
        "ready": [
            task
            for task in snapshot.status.ready
            if task not in snapshot.status.completed
        ],
        "blocked": list(snapshot.status.blocked),
        "claimed": list(snapshot.status.claimed),
    }


__all__ = [
    "AGENT",
    "DirectiveRuntime",
    "DirectiveSession",
    "build_demo_plan",
    "build_plan",
    "build_markdown_document",
    "classify_task_states",
    "create_plan",
    "execute_with_directive",
    "register_directive",
    "run_directive_demo",
    "run_directive_request",
]

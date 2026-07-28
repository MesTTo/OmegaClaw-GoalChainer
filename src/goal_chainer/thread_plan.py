"""Compile MeTTa Markdown thread specifications into OmegaClaw plans."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from .directive import DirectiveRuntime, DirectiveSession, create_plan
from .directive_models import (
    DirectiveAnalysis,
    DirectiveSnapshot,
    DirectiveValidation,
)
from .thread_models import (
    ThreadPlanCompilation,
    ThreadSpecification,
    ThreadSpecificationError,
)
from .thread_runtime import ThreadRuntime
from .thread_spec import parse_thread_markdown


def compile_thread_markdown(
    source: str,
    *,
    source_path: str | None = None,
    plan_path: str | os.PathLike[str] | None = None,
    thread_runtime: ThreadRuntime | None = None,
    directive_runtime: DirectiveRuntime | None = None,
) -> ThreadPlanCompilation:
    """Parse, validate, preflight, and optionally persist one thread plan."""

    policy = thread_runtime or ThreadRuntime()
    directive = directive_runtime or DirectiveRuntime(policy.runtime)
    parsed = parse_thread_markdown(
        source,
        runtime=policy.runtime,
        source_path=source_path,
    )
    compiled = policy.compile(parsed).value
    if not isinstance(compiled, ThreadSpecification):
        raise ThreadSpecificationError(
            "PeTTa returned no compiled thread specification."
        )
    plan = build_thread_plan(compiled, policy)
    snapshot = _preflight_plan(plan, directive, plan_path=plan_path)
    destination = create_plan(plan_path, plan) if plan_path is not None else None
    return ThreadPlanCompilation(
        specification=compiled,
        plan=plan,
        snapshot=snapshot,
        plan_path=str(destination) if destination is not None else None,
    )


def build_thread_plan(
    specification: ThreadSpecification,
    runtime: ThreadRuntime,
) -> str:
    """Ask PeTTa to compile one native directive plan."""

    result = runtime.plan(
        specification,
        created=datetime.now(UTC).date().isoformat(),
    ).value
    if not isinstance(result, str):
        raise ThreadSpecificationError("PeTTa returned no compiled OmegaClaw plan.")
    return result


def _preflight_plan(
    plan: str,
    runtime: DirectiveRuntime,
    *,
    plan_path: str | os.PathLike[str] | None,
) -> DirectiveSnapshot:
    directory = (
        Path(plan_path).expanduser().absolute().parent
        if plan_path is not None
        else None
    )
    descriptor, temporary = tempfile.mkstemp(
        prefix=".goalchainer-thread-preflight-",
        suffix=".metta",
        dir=directory,
        text=True,
    )
    path = Path(temporary)
    try:
        os.chmod(path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(plan)
            handle.flush()
            os.fsync(handle.fileno())
        session = DirectiveSession(path, runtime=runtime)
        validation = session.validate(strict=True).value
        if not isinstance(validation, DirectiveValidation) or not validation.valid:
            raise ThreadSpecificationError(
                "OmegaClaw rejected the compiled thread plan."
            )
        analysis = session.analyze().value
        if not isinstance(analysis, DirectiveAnalysis):
            raise ThreadSpecificationError(
                "OmegaClaw returned no thread plan analysis."
            )
        if analysis.cycles:
            raise ThreadSpecificationError(
                "Thread task dependencies contain a cycle.",
                details={"cycles": [list(cycle) for cycle in analysis.cycles]},
            )
        if not analysis.consistent:
            raise ThreadSpecificationError("Compiled thread plan is inconsistent.")
        snapshot = session.snapshot().value
        if not isinstance(snapshot, DirectiveSnapshot):
            raise ThreadSpecificationError(
                "OmegaClaw returned no compiled thread snapshot."
            )
        return snapshot
    finally:
        path.unlink(missing_ok=True)


__all__ = ["build_thread_plan", "compile_thread_markdown"]

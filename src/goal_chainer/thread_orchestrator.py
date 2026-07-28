"""ThreadKeeper and Hence-style execution over one OmegaClaw directive plan."""

from __future__ import annotations

import fcntl
import os
import stat
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Concatenate, Literal, ParamSpec, TypeVar, cast

from .directive import DirectiveRuntime, DirectiveSession
from .directive_models import (
    DirectiveLifecycleResult,
    DirectiveSnapshot,
    DirectiveTaskState,
)
from .thread_audit import ThreadAuditStore
from .thread_git import ThreadGitWorktrees
from .thread_models import (
    ThreadAttemptResult,
    ThreadEvaluation,
    ThreadExecutionError,
    ThreadOutcomeDecision,
    ThreadPettaAttempt,
    ThreadProcessObservation,
    ThreadRouteDecision,
    ThreadSpecification,
    ThreadTask,
    ThreadTaskExecution,
    ThreadUsage,
    ThreadWorktreeExecution,
)
from .thread_process import ThreadProcessSupervisor, run_evaluator_command
from .thread_runtime import ThreadRuntime

EvaluationCallable = Callable[
    [ThreadTask, ThreadProcessObservation],
    tuple[Literal["accept", "reject"], str],
]
UsageCallable = Callable[[ThreadProcessObservation], ThreadUsage]
CompletionCallable = Callable[[ThreadAttemptResult], None]
Evaluator = EvaluationCallable | Sequence[str]
_P = ParamSpec("_P")
_Orchestrator = TypeVar("_Orchestrator", bound="ThreadOrchestrator")


def _recover_claimed_task(
    method: Callable[
        Concatenate[_Orchestrator, str, _P],
        ThreadTaskExecution,
    ],
) -> Callable[
    Concatenate[_Orchestrator, str, _P],
    ThreadTaskExecution,
]:
    @wraps(method)
    def guarded(
        self: _Orchestrator,
        task_id: str,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> ThreadTaskExecution:
        try:
            return method(self, task_id, *args, **kwargs)
        except BaseException as exc:
            try:
                with self._locked():
                    state = self.session.task_state(task_id).value
                    if (
                        isinstance(state, DirectiveTaskState)
                        and state.state == "in-progress"
                    ):
                        blocked = self.session.block(
                            task_id,
                            self.specification.roles.supervisor,
                        ).value
                        _require_lifecycle(blocked, "block")
                        self._event(
                            "task-permanent-failure",
                            {
                                "task": task_id,
                                "reason": (
                                    f"orchestration failed: {type(exc).__name__}: {exc}"
                                ),
                            },
                        )
            except Exception as recovery_error:  # noqa: BLE001
                exc.add_note(
                    "Thread lifecycle recovery also failed: "
                    f"{type(recovery_error).__name__}: {recovery_error}"
                )
            raise

    return cast(
        Callable[
            Concatenate[_Orchestrator, str, _P],
            ThreadTaskExecution,
        ],
        guarded,
    )


class ThreadOrchestrator:
    """Apply PeTTa policy and host observations to one durable plan."""

    def __init__(
        self,
        specification: ThreadSpecification,
        *,
        plan_path: str | os.PathLike[str],
        audit_path: str | os.PathLike[str],
        runtime: ThreadRuntime | None = None,
        process_supervisor: ThreadProcessSupervisor | None = None,
    ) -> None:
        self.specification = specification
        self.runtime = runtime or ThreadRuntime()
        self.session = DirectiveSession(
            plan_path,
            runtime=DirectiveRuntime(self.runtime.runtime),
        )
        self.audit = ThreadAuditStore(audit_path)
        self.process_supervisor = process_supervisor or ThreadProcessSupervisor()
        self._lock_path = self.session.path.with_suffix(
            self.session.path.suffix + ".thread.lock"
        )
        self._assert_plan_identity()
        self._assert_audit_identity()
        with self._locked():
            if not self.audit.verify():
                self._event(
                    "thread-compiled",
                    {
                        "semantic_digest": self.specification.semantic_digest,
                        "plan_path": str(self.session.path),
                    },
                )

    def inspect(self) -> dict[str, object]:
        with self._locked():
            snapshot = self._snapshot()
            events = self.audit.verify()
            return {
                "specification": self.specification.to_dict(),
                "snapshot": snapshot.to_dict(),
                "usage_tokens": _spent_tokens(events),
                "attempts": _attempt_counts(events),
                "audit_events": len(events),
                "audit_head": events[-1].event_hash if events else None,
            }

    def route(
        self,
        task_id: str,
        *,
        local_iterations: int,
        hard: bool,
    ) -> ThreadRouteDecision:
        with self._locked():
            return self._route(
                self._task(task_id),
                local_iterations=local_iterations,
                hard=hard,
            )

    def record_usage(
        self,
        usage: ThreadUsage,
        *,
        task_id: str,
        attempt: int,
    ) -> int:
        with self._locked():
            self._task(task_id)
            return self._record_usage(usage, task_id=task_id, attempt=attempt)

    @_recover_claimed_task
    def run_task(
        self,
        task_id: str,
        command: Sequence[str],
        *,
        cwd: str | os.PathLike[str],
        evaluator: Evaluator,
        usage: ThreadUsage | UsageCallable | None = None,
        adjudicator: Evaluator | None = None,
        local_iterations: int = 0,
        hard: bool = False,
        env: dict[str, str] | None = None,
        use_pty: bool = True,
        before_complete: CompletionCallable | None = None,
    ) -> ThreadTaskExecution:
        with self._locked():
            task = self._task(task_id)
            state = self.session.task_state(task_id).value
            if not isinstance(state, DirectiveTaskState) or state.state != "ready":
                raise ThreadExecutionError(
                    "Thread task is not ready.",
                    details={
                        "task": task_id,
                        "state": getattr(state, "state", None),
                    },
                )
            attempts: list[ThreadAttemptResult] = []
            first_attempt = _attempt_counts(self.audit.verify()).get(task_id, 0) + 1
            final_attempt = self.specification.supervision.max_retries + 1
            if first_attempt > final_attempt:
                raise ThreadExecutionError(
                    "Thread task has exhausted its configured attempts.",
                    details={"task": task_id, "attempts": first_attempt - 1},
                )
            for attempt_number in range(
                first_attempt,
                final_attempt + 1,
            ):
                route = self._route(
                    task,
                    local_iterations=local_iterations,
                    hard=hard,
                )
                if not route.allowed:
                    if attempts:
                        snapshot = self._block_permanently(
                            task,
                            reason=route.reason,
                            attempt=attempt_number,
                        )
                        return ThreadTaskExecution(
                            task_id=task_id,
                            outcome="permanent-failure",
                            attempts=tuple(attempts),
                            snapshot=snapshot,
                        )
                    return ThreadTaskExecution(
                        task_id=task_id,
                        outcome="denied",
                        attempts=(),
                        snapshot=self._snapshot(),
                    )
                worker = (
                    self.specification.roles.specialist
                    if route.target == "specialist"
                    else self.specification.roles.worker
                )
                claim = self.session.claim(
                    task_id,
                    self.specification.roles.supervisor,
                ).value
                _require_lifecycle(claim, "claim")
                self._event(
                    "task-claimed",
                    {
                        "task": task_id,
                        "attempt": attempt_number,
                        "worker": worker,
                        "route": route.target,
                    },
                )
                self._event(
                    "attempt-started",
                    {
                        "task": task_id,
                        "attempt": attempt_number,
                        "worker": worker,
                    },
                )
                native_attempt = not callable(evaluator) and (
                    not route.requires_adjudication or not callable(adjudicator)
                )
                petta_attempt = None
                if native_attempt:
                    evaluator_command = cast(Sequence[str], evaluator)
                    adjudicator_command = cast(
                        Sequence[str] | None,
                        adjudicator,
                    )
                    petta_attempt = self.runtime.attempt(
                        self.specification,
                        task,
                        worker_command=command,
                        evaluator_command=evaluator_command,
                        adjudicator_command=(
                            adjudicator_command
                            if route.requires_adjudication
                            and adjudicator_command is not None
                            else None
                        ),
                        cwd=cwd,
                        environment=env,
                        use_pty=use_pty,
                        attempt=attempt_number,
                        adjudication_required=route.requires_adjudication,
                    ).value
                    if not isinstance(petta_attempt, ThreadPettaAttempt):
                        raise ThreadExecutionError(
                            "PeTTa returned no native thread attempt."
                        )
                    observation = petta_attempt.observation
                    for _ in range(observation.lease_renewals):
                        self._renew_lease(task_id, attempt_number)
                else:
                    observation = self.process_supervisor.run(
                        command,
                        cwd=cwd,
                        supervision=self.specification.supervision,
                        env=env,
                        renew_lease=lambda attempt=attempt_number: self._renew_lease(
                            task_id,
                            attempt,
                        ),
                        use_pty=use_pty,
                    )
                self._event(
                    "attempt-finished",
                    {
                        "task": task_id,
                        "attempt": attempt_number,
                        "exit_reason": observation.exit_reason,
                        "exit_code": observation.exit_code,
                        "output_bytes": observation.output_bytes,
                        "duration_seconds": observation.duration_seconds,
                        "activity_events": observation.activity_events,
                        "engine": (
                            "petta-native"
                            if petta_attempt is not None
                            else "python-callable"
                        ),
                    },
                )
                measured_usage = _usage(usage, observation)
                self._record_usage(
                    measured_usage,
                    task_id=task_id,
                    attempt=attempt_number,
                )
                evaluation = (
                    petta_attempt.evaluation
                    if petta_attempt is not None
                    else self._evaluate(
                        evaluator,
                        identity=self.specification.roles.evaluator,
                        task=task,
                        observation=observation,
                        cwd=Path(cwd),
                    )
                )
                self._event(
                    "evaluation-recorded",
                    {
                        "task": task_id,
                        "attempt": attempt_number,
                        "verdict": evaluation.verdict,
                        "reason": evaluation.reason,
                    },
                    actor=evaluation.evaluator,
                )
                adjudication = None
                if route.requires_adjudication:
                    adjudication = (
                        petta_attempt.adjudication
                        if petta_attempt is not None
                        else self._adjudicate(
                            adjudicator,
                            task=task,
                            observation=observation,
                            cwd=Path(cwd),
                        )
                    )
                    self._event(
                        "adjudication-recorded",
                        {
                            "task": task_id,
                            "attempt": attempt_number,
                            "verdict": adjudication.verdict,
                            "reason": adjudication.reason,
                        },
                        actor=adjudication.evaluator,
                    )
                attempt = ThreadAttemptResult(
                    task_id=task_id,
                    attempt=attempt_number,
                    worker=worker,
                    route=route.target,  # type: ignore[arg-type]
                    engine=(
                        "petta-native"
                        if petta_attempt is not None
                        else "python-callable"
                    ),
                    exit_reason=observation.exit_reason,
                    exit_code=observation.exit_code,
                    output=observation.output,
                    usage=measured_usage,
                    evaluation=evaluation,
                    adjudication=adjudication,
                )
                attempts.append(attempt)
                decision = (
                    petta_attempt.outcome
                    if petta_attempt is not None
                    else self.runtime.outcome(
                        self.specification,
                        exit_reason=observation.exit_reason,
                        exit_code=observation.exit_code,
                        evaluator_verdict=evaluation.verdict,
                        attempt=attempt_number,
                        adjudication_required=route.requires_adjudication,
                        adjudicator_verdict=(
                            adjudication.verdict
                            if adjudication is not None
                            else "not-required"
                        ),
                    ).value
                )
                if not isinstance(decision, ThreadOutcomeDecision):
                    raise ThreadExecutionError(
                        "PeTTa returned no thread attempt outcome."
                    )
                self._event(
                    "outcome-decided",
                    {
                        "task": task_id,
                        "attempt": attempt_number,
                        "outcome": decision.outcome,
                        "reason": decision.reason,
                    },
                )
                if decision.outcome == "complete":
                    if before_complete is not None:
                        before_complete(attempt)
                    complete = self.session.complete(
                        task_id,
                        self.specification.roles.supervisor,
                    ).value
                    result = _require_lifecycle(complete, "complete")
                    self._event(
                        "task-completed",
                        {"task": task_id, "attempt": attempt_number},
                    )
                    return ThreadTaskExecution(
                        task_id=task_id,
                        outcome="complete",
                        attempts=tuple(attempts),
                        snapshot=result.snapshot,
                    )
                if decision.outcome == "retry":
                    unclaim = self.session.unclaim(
                        task_id,
                        self.specification.roles.supervisor,
                    ).value
                    _require_lifecycle(unclaim, "unclaim")
                    self._event(
                        "task-retried",
                        {
                            "task": task_id,
                            "attempt": attempt_number,
                            "reason": decision.reason,
                        },
                    )
                    continue
                snapshot = self._block_permanently(
                    task,
                    reason=decision.reason,
                    attempt=attempt_number,
                )
                return ThreadTaskExecution(
                    task_id=task_id,
                    outcome="permanent-failure",
                    attempts=tuple(attempts),
                    snapshot=snapshot,
                )
            raise ThreadExecutionError(
                "Thread retry loop exhausted without an outcome."
            )

    def run_task_in_worktree(
        self,
        task_id: str,
        command: Sequence[str],
        *,
        repository: str | os.PathLike[str],
        evaluator: Evaluator,
        usage: ThreadUsage | UsageCallable | None = None,
        adjudicator: Evaluator | None = None,
        worktree_root: str | os.PathLike[str],
        local_iterations: int = 0,
        hard: bool = False,
        env: dict[str, str] | None = None,
        use_pty: bool = True,
    ) -> ThreadWorktreeExecution:
        """Run accepted work in a detached tree and apply the merge policy."""

        with self._locked():
            first_attempt = _attempt_counts(self.audit.verify()).get(task_id, 0) + 1
        manager = ThreadGitWorktrees(repository, worktree_root)
        worktree = manager.create(
            thread_id=self.specification.thread_id,
            task_id=task_id,
            attempt=first_attempt,
        )
        self._event(
            "worktree-created",
            {
                "task": task_id,
                "attempt": first_attempt,
                "path": worktree.path,
                "base_commit": worktree.base_commit,
            },
        )
        try:
            worker_commit: str | None = None
            integrated_commit: str | None = None

            def integrate_before_completion(_attempt: ThreadAttemptResult) -> None:
                nonlocal worker_commit, integrated_commit
                merge_policy = self.specification.merge_policy
                if merge_policy.mode == "none":
                    return
                branch = merge_policy.integration_branch
                if branch is None:
                    raise ThreadExecutionError(
                        "Integration-branch policy has no branch."
                    )
                worker_commit = manager.commit(
                    worktree,
                    message=f"Complete thread task {task_id}",
                )
                integrated_commit = manager.integrate(
                    worker_commit=worker_commit,
                    integration_branch=branch,
                    base_commit=worktree.base_commit,
                    message=f"Integrate thread task {task_id}",
                )
                self._event(
                    "integration-completed",
                    {
                        "task": task_id,
                        "attempt": first_attempt,
                        "branch": branch,
                        "worker_commit": worker_commit,
                        "integrated_commit": integrated_commit,
                    },
                )

            execution = self.run_task(
                task_id,
                command,
                cwd=worktree.path,
                evaluator=evaluator,
                usage=usage,
                adjudicator=adjudicator,
                local_iterations=local_iterations,
                hard=hard,
                env=env,
                use_pty=use_pty,
                before_complete=integrate_before_completion,
            )
        except BaseException:
            self._event(
                "worktree-retained",
                {
                    "task": task_id,
                    "attempt": first_attempt,
                    "path": worktree.path,
                    "reason": "orchestration-error",
                },
            )
            raise
        if execution.outcome != "complete":
            retained = True
            try:
                manager.remove(worktree)
                retained = False
            except ThreadExecutionError:
                pass
            self._event(
                "worktree-retained" if retained else "worktree-removed",
                {
                    "task": task_id,
                    "attempt": first_attempt,
                    "path": worktree.path,
                    "reason": execution.outcome,
                },
            )
            return ThreadWorktreeExecution(
                execution=execution,
                worktree=worktree,
                worker_commit=None,
                integrated_commit=None,
                retained=retained,
            )
        if self.specification.merge_policy.mode == "none":
            retained = True
            try:
                manager.remove(worktree)
                retained = False
            except ThreadExecutionError:
                pass
            self._event(
                "worktree-retained" if retained else "worktree-removed",
                {
                    "task": task_id,
                    "attempt": first_attempt,
                    "path": worktree.path,
                    "reason": "merge-policy-none",
                },
            )
            return ThreadWorktreeExecution(
                execution=execution,
                worktree=worktree,
                worker_commit=None,
                integrated_commit=None,
                retained=retained,
            )
        manager.remove(worktree)
        self._event(
            "worktree-removed",
            {
                "task": task_id,
                "attempt": first_attempt,
                "path": worktree.path,
                "reason": "integrated",
            },
        )
        return ThreadWorktreeExecution(
            execution=execution,
            worktree=worktree,
            worker_commit=worker_commit,
            integrated_commit=integrated_commit,
            retained=False,
        )

    def _route(
        self,
        task: ThreadTask,
        *,
        local_iterations: int,
        hard: bool,
    ) -> ThreadRouteDecision:
        spent = _spent_tokens(self.audit.verify())
        result = self.runtime.route(
            self.specification,
            capability=task.capability,
            stakes=task.stakes,
            spent_tokens=spent,
            local_iterations=local_iterations,
            hard=hard,
        ).value
        if not isinstance(result, ThreadRouteDecision):
            raise ThreadExecutionError("PeTTa returned no thread route decision.")
        self._event(
            "route-decided",
            {
                "task": task.task_id,
                "spent_tokens": spent,
                "target": result.target,
                "allowed": result.allowed,
                "reason": result.reason,
                "requires_adjudication": result.requires_adjudication,
            },
        )
        return result

    def _record_usage(
        self,
        usage: ThreadUsage,
        *,
        task_id: str,
        attempt: int,
    ) -> int:
        self._event(
            "usage-recorded",
            {
                "task": task_id,
                "attempt": attempt,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
        )
        return _spent_tokens(self.audit.verify())

    def _evaluate(
        self,
        evaluator: Evaluator,
        *,
        identity: str,
        task: ThreadTask,
        observation: ThreadProcessObservation,
        cwd: Path,
    ) -> ThreadEvaluation:
        if observation.exit_reason != "process-exited" or observation.exit_code != 0:
            return ThreadEvaluation(
                evaluator=identity,
                verdict="reject",
                reason=(
                    f"worker {observation.exit_reason} "
                    f"with status {observation.exit_code}"
                ),
            )
        try:
            verdict, reason = (
                evaluator(task, observation)
                if callable(evaluator)
                else run_evaluator_command(
                    evaluator,
                    task=task,
                    observation=observation,
                    cwd=cwd,
                    supervision=self.specification.supervision,
                    process_supervisor=self.process_supervisor,
                )
            )
            return ThreadEvaluation(
                evaluator=identity,
                verdict=cast(Literal["accept", "reject"], verdict),
                reason=reason,
            )
        except Exception as exc:  # noqa: BLE001
            return ThreadEvaluation(
                evaluator=identity,
                verdict="reject",
                reason=f"evaluator failed: {type(exc).__name__}: {exc}",
            )

    def _adjudicate(
        self,
        adjudicator: Evaluator | None,
        *,
        task: ThreadTask,
        observation: ThreadProcessObservation,
        cwd: Path,
    ) -> ThreadEvaluation:
        identity = self.specification.roles.adjudicator
        if identity is None:
            raise ThreadExecutionError(
                "PeTTa required adjudication but no adjudicator role exists."
            )
        if adjudicator is None:
            return ThreadEvaluation(
                evaluator=identity,
                verdict="reject",
                reason="adjudicator implementation was not supplied",
            )
        return self._evaluate(
            adjudicator,
            identity=identity,
            task=task,
            observation=observation,
            cwd=cwd,
        )

    def _block_permanently(
        self,
        task: ThreadTask,
        *,
        reason: str,
        attempt: int,
    ) -> DirectiveSnapshot:
        blocked = self.session.block(
            task.task_id,
            self.specification.roles.supervisor,
        ).value
        result = _require_lifecycle(blocked, "block")
        self._event(
            "task-permanent-failure",
            {
                "task": task.task_id,
                "attempt": attempt,
                "reason": reason,
            },
        )
        return result.snapshot

    def _renew_lease(self, task_id: str, attempt: int) -> bool:
        self._event(
            "lease-renewed",
            {"task": task_id, "attempt": attempt},
        )
        return True

    def _task(self, task_id: str) -> ThreadTask:
        task = next(
            (
                candidate
                for candidate in self.specification.tasks
                if candidate.task_id == task_id
            ),
            None,
        )
        if task is None:
            raise ThreadExecutionError(
                "Thread task does not exist.",
                details={"task": task_id},
            )
        return task

    def _snapshot(self) -> DirectiveSnapshot:
        snapshot = self.session.snapshot().value
        if not isinstance(snapshot, DirectiveSnapshot):
            raise ThreadExecutionError("OmegaClaw returned no thread snapshot.")
        return snapshot

    def _assert_plan_identity(self) -> None:
        info = dict(self._snapshot().info)
        if info.get("source-digest") != self.specification.semantic_digest:
            raise ThreadExecutionError(
                "Thread plan does not match the specification digest.",
                details={
                    "plan_digest": info.get("source-digest"),
                    "specification_digest": self.specification.semantic_digest,
                },
            )

    def _assert_audit_identity(self) -> None:
        thread_ids = {event.thread_id for event in self.audit.verify()}
        if thread_ids and thread_ids != {self.specification.thread_id}:
            raise ThreadExecutionError(
                "Thread audit log belongs to another specification.",
                details={"thread_ids": sorted(thread_ids)},
            )

    def _event(
        self,
        event_type: str,
        payload: dict[str, object],
        *,
        actor: str | None = None,
    ) -> None:
        self.audit.append(
            thread_id=self.specification.thread_id,
            event_type=event_type,
            actor=actor or self.specification.roles.supervisor,
            payload=payload,
        )

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with _orchestration_lock(self._lock_path):
            self._assert_plan_identity()
            self._assert_audit_identity()
            yield


def _require_lifecycle(
    value: object,
    operation: str,
) -> DirectiveLifecycleResult:
    if not isinstance(value, DirectiveLifecycleResult) or not value.accepted:
        raise ThreadExecutionError(
            f"OmegaClaw rejected thread lifecycle operation: {operation}.",
            details={"reason": getattr(value, "reason", None)},
        )
    return value


def _usage(
    usage: ThreadUsage | UsageCallable | None,
    observation: ThreadProcessObservation,
) -> ThreadUsage:
    result = (
        usage(observation)
        if callable(usage)
        else usage
        if usage is not None
        else ThreadUsage(0, 0)
    )
    if not isinstance(result, ThreadUsage):
        raise ThreadExecutionError("Thread usage callback returned an invalid value.")
    return result


def _spent_tokens(events) -> int:
    return sum(
        event.payload["total_tokens"]
        for event in events
        if event.event_type == "usage-recorded"
        and isinstance(event.payload.get("total_tokens"), int)
        and not isinstance(event.payload.get("total_tokens"), bool)
    )


def _attempt_counts(events) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        if event.event_type != "attempt-started":
            continue
        task = event.payload.get("task")
        if isinstance(task, str):
            counts[task] = counts.get(task, 0) + 1
    return counts


@contextmanager
def _orchestration_lock(path: Path) -> Iterator[None]:
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ThreadExecutionError(
            "Thread orchestration lock could not be opened safely.",
            details={"path": str(path), "error": str(exc)},
        ) from exc
    try:
        with os.fdopen(descriptor, "r+b") as handle:
            descriptor = -1
            metadata = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise ThreadExecutionError(
                    "Thread orchestration lock is not a private owned file.",
                    details={"path": str(path)},
                )
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
    except OSError as exc:
        raise ThreadExecutionError(
            "Thread orchestration lock failed.",
            details={"path": str(path), "error": str(exc)},
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


__all__ = ["ThreadOrchestrator"]

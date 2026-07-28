"""Run ThreadKeeper policy through MeTTaScript with PeTTa host compatibility."""

from __future__ import annotations

import base64
import json
import os
import sysconfig
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .mettascript_runtime import MeTTaScriptRuntime
from .snars_program import SexprCodec
from .snars_runtime import SnarsRuntime
from .thread_models import (
    ParsedThreadMarkdown,
    ThreadCapability,
    ThreadExecutionError,
    ThreadRun,
    ThreadSpecification,
    ThreadStakes,
    ThreadTask,
)
from .thread_protocol import parse_thread_output

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ADAPTER_PATH = (
    REPO_ROOT / "integrations" / "threadkeeper" / "goalchainer_threadkeeper.metta"
)
INSTALLED_ADAPTER_PATH = (
    Path(sysconfig.get_path("data"))
    / "integrations"
    / "threadkeeper"
    / "goalchainer_threadkeeper.metta"
)


class ThreadRuntime:
    """Invoke MeTTaScript policy and retain PeTTa for legacy host atoms."""

    def __init__(
        self,
        runtime: SnarsRuntime | None = None,
        *,
        mettascript_runtime: MeTTaScriptRuntime | None = None,
    ) -> None:
        # Directive lifecycle and the existing py-call attempt surface still
        # consume this compatibility runtime. Pure GoalChainer policy runs on
        # MeTTaScript through self.mettascript_runtime.
        self.runtime = runtime or SnarsRuntime(require_text_ingestion=False)
        self.mettascript_runtime = mettascript_runtime or MeTTaScriptRuntime()
        self.codec = SexprCodec(self.runtime)
        adapter_path = next(
            (
                path
                for path in (SOURCE_ADAPTER_PATH, INSTALLED_ADAPTER_PATH)
                if path.is_file()
            ),
            None,
        )
        if adapter_path is None:
            raise ThreadExecutionError(
                "GoalChainer ThreadKeeper MeTTa adapter is unavailable.",
                details={
                    "searched": [
                        str(SOURCE_ADAPTER_PATH),
                        str(INSTALLED_ADAPTER_PATH),
                    ]
                },
            )
        self._adapter = adapter_path.read_text(encoding="utf-8")

    def compile(self, parsed: ParsedThreadMarkdown) -> ThreadRun:
        facts_source = "(" + " ".join(fact.atom for fact in parsed.facts) + ")"
        return self._execute(
            self.codec.expression(
                "gc-thread-compile",
                self.codec.string(facts_source),
            ),
            expected_operation="compile",
            parsed_markdown=parsed,
        )

    def plan(
        self,
        specification: ThreadSpecification,
        *,
        created: str,
    ) -> ThreadRun:
        """Compile a validated thread graph into OmegaClaw directive text."""

        facts_source = "(" + " ".join(fact.atom for fact in specification.facts) + ")"
        return self._execute(
            self.codec.expression(
                "gc-thread-plan",
                self.codec.string(facts_source),
                self.codec.string(specification.semantic_digest),
                self.codec.string(created),
            ),
            expected_operation="plan",
        )

    def parse_markdown_atoms(
        self,
        atoms_source: str,
        *,
        source_path: str | None = None,
    ) -> ThreadRun:
        """Lower Mettabase Markdown atoms through MeTTaScript policy."""

        return self._execute(
            self.codec.expression(
                "gc-thread-markdown-atoms",
                self.codec.string(atoms_source),
            ),
            expected_operation="markdown",
            source_path=source_path,
        )

    def route(
        self,
        specification: ThreadSpecification,
        *,
        capability: ThreadCapability,
        stakes: ThreadStakes,
        spent_tokens: int,
        local_iterations: int,
        hard: bool,
    ) -> ThreadRun:
        budget = specification.budget
        return self._execute(
            self.codec.expression(
                "gc-thread-route",
                self.codec.symbol(capability),
                self.codec.symbol(stakes),
                spent_tokens,
                budget.ceiling_tokens,
                budget.soft_threshold_tokens,
                budget.min_local_iterations,
                local_iterations,
                self.codec.symbol("True" if hard else "False"),
                self.codec.symbol(
                    "True" if specification.roles.adjudicator is not None else "False"
                ),
            ),
            expected_operation="route",
        )

    def release(
        self,
        *,
        not_before_epoch: int | None,
        now_epoch: int,
        dependency_ready: bool,
    ) -> ThreadRun:
        """Ask MeTTaScript whether a dependency-ready task may start now."""

        return self._execute(
            self.codec.expression(
                "gc-thread-release",
                (
                    self.codec.symbol("none")
                    if not_before_epoch is None
                    else not_before_epoch
                ),
                now_epoch,
                self.codec.symbol("True" if dependency_ready else "False"),
            ),
            expected_operation="release",
        )

    def ui_projection(
        self,
        *,
        rows_source: str,
        now_epoch: int,
    ) -> ThreadRun:
        """Ask MeTTaScript to derive the Agent Orchestrator read model."""

        return self._execute(
            self.codec.expression(
                "gc-thread-ui",
                self.codec.string(rows_source),
                now_epoch,
            ),
            expected_operation="ui",
        )

    def status_document(
        self,
        specification: ThreadSpecification,
        *,
        board_source: str,
        spent_tokens: int,
        attempts_source: str,
        audit_source: str,
    ) -> ThreadRun:
        """Build a Mettabase authoring AST for current thread state."""

        facts_source = "(" + " ".join(fact.atom for fact in specification.facts) + ")"
        budget = specification.budget
        return self._execute(
            self.codec.expression(
                "gc-thread-status",
                self.codec.string(specification.title),
                self.codec.string(facts_source),
                self.codec.string(board_source),
                budget.ceiling_tokens,
                budget.soft_threshold_tokens,
                spent_tokens,
                self.codec.string(attempts_source),
                self.codec.string(audit_source),
            ),
            expected_operation="status",
        )

    def outcome(
        self,
        specification: ThreadSpecification,
        *,
        exit_reason: str,
        exit_code: int,
        evaluator_verdict: str,
        attempt: int,
        adjudication_required: bool,
        adjudicator_verdict: str,
    ) -> ThreadRun:
        return self._execute(
            self.codec.expression(
                "gc-thread-outcome",
                self.codec.symbol(exit_reason),
                exit_code,
                self.codec.symbol(evaluator_verdict),
                attempt,
                specification.supervision.max_retries,
                self.codec.symbol("True" if adjudication_required else "False"),
                self.codec.symbol(adjudicator_verdict),
            ),
            expected_operation="outcome",
        )

    def attempt(
        self,
        specification: ThreadSpecification,
        task: ThreadTask,
        *,
        worker_command: Sequence[str],
        evaluator_command: Sequence[str],
        adjudicator_command: Sequence[str] | None,
        cwd: str | os.PathLike[str],
        environment: Mapping[str, str] | None,
        use_pty: bool,
        attempt: int,
        adjudication_required: bool,
    ) -> ThreadRun:
        """Run host effects through the retained PeTTa grounded-atom bridge."""

        supervision = specification.supervision
        return self._execute(
            self.codec.expression(
                "gc-thread-attempt",
                self.codec.symbol(_base64_text(json.dumps(list(worker_command)))),
                self.codec.symbol(_base64_text(json.dumps(list(evaluator_command)))),
                self.codec.symbol(
                    _base64_text(
                        json.dumps(
                            list(adjudicator_command)
                            if adjudicator_command is not None
                            else []
                        )
                    )
                ),
                self.codec.symbol(_base64_text(str(Path(cwd).expanduser().absolute()))),
                self.codec.symbol(
                    _base64_text(
                        json.dumps(
                            dict(environment) if environment is not None else None,
                            sort_keys=True,
                        )
                    )
                ),
                self.codec.symbol("True" if use_pty else "False"),
                self.codec.symbol(task.task_id),
                self.codec.symbol(task.capability),
                self.codec.symbol(task.acceptance),
                self.codec.symbol(task.stakes),
                self.codec.symbol(specification.roles.evaluator),
                self.codec.symbol(specification.roles.adjudicator or "none"),
                supervision.lease_seconds,
                supervision.idle_timeout_seconds,
                supervision.wall_timeout_seconds,
                attempt,
                supervision.max_retries,
                self.codec.symbol("True" if adjudication_required else "False"),
            ),
            expected_operation="attempt",
            compatibility_runtime=True,
        )

    def _execute(
        self,
        expression: Any,
        *,
        expected_operation: str,
        parsed_markdown: ParsedThreadMarkdown | None = None,
        source_path: str | None = None,
        compatibility_runtime: bool = False,
    ) -> ThreadRun:
        program = (
            self._adapter
            + "\n!"
            + self.codec.emit(expression)
            + "\n"
        )
        engine = self.runtime if compatibility_runtime else self.mettascript_runtime
        result = engine.run_batch(program)
        return parse_thread_output(
            result.stdout.splitlines(),
            self.codec,
            expected_operation=expected_operation,
            parsed_markdown=parsed_markdown,
            source_path=source_path,
        )


def _base64_text(value: str) -> str:
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
    return "b64_" + encoded


__all__ = ["INSTALLED_ADAPTER_PATH", "SOURCE_ADAPTER_PATH", "ThreadRuntime"]

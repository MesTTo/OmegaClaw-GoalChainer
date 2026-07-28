from __future__ import annotations

import pytest

from goal_chainer.thread_models import (
    ThreadBudget,
    ThreadMergePolicy,
    ThreadRoles,
    ThreadSupervision,
    ThreadTask,
    ThreadWorkflow,
    ThreadWorkflowStep,
)


def test_thread_budget_rejects_invalid_thresholds() -> None:
    with pytest.raises(ValueError, match="soft threshold"):
        ThreadBudget(
            ceiling_tokens=100,
            soft_threshold_tokens=101,
            min_local_iterations=1,
        )


def test_thread_supervision_rejects_idle_timeout_above_wall_timeout() -> None:
    with pytest.raises(ValueError, match="idle timeout"):
        ThreadSupervision(
            lease_seconds=30,
            idle_timeout_seconds=61,
            wall_timeout_seconds=60,
            max_retries=2,
        )


def test_thread_roles_must_be_distinct() -> None:
    with pytest.raises(ValueError, match="distinct"):
        ThreadRoles(
            control="control",
            worker="worker",
            supervisor="worker",
            evaluator="evaluator",
            specialist="specialist",
            adjudicator="adjudicator",
        )


def test_thread_task_rejects_self_dependency() -> None:
    with pytest.raises(ValueError, match="depend on itself"):
        ThreadTask(
            task_id="collect",
            capability="local",
            acceptance="evidence-collected",
            stakes="normal",
            dependencies=("collect",),
        )


def test_thread_task_rejects_negative_not_before_epoch() -> None:
    with pytest.raises(ValueError, match="not-before"):
        ThreadTask(
            task_id="collect",
            capability="local",
            acceptance="evidence-collected",
            stakes="normal",
            not_before_epoch=-1,
        )


def test_thread_task_rejects_not_before_outside_rfc3339_range() -> None:
    with pytest.raises(ValueError, match="RFC 3339"):
        ThreadTask(
            task_id="collect",
            capability="local",
            acceptance="evidence-collected",
            stakes="normal",
            not_before_epoch=253_402_300_800,
        )


def test_integration_merge_policy_requires_a_branch() -> None:
    with pytest.raises(ValueError, match="integration branch"):
        ThreadMergePolicy(mode="integration-branch", integration_branch=None)


def test_thread_workflow_rejects_oversized_guidance() -> None:
    steps = tuple(
        ThreadWorkflowStep(order=index, instruction="x" * 500)
        for index in range(1, 6)
    )

    with pytest.raises(ValueError, match="2048 bytes"):
        ThreadWorkflow(workflow_id="research", steps=steps)


def test_thread_workflow_rejects_duplicate_or_unsorted_steps() -> None:
    first = ThreadWorkflowStep(order=20, instruction="second")
    second = ThreadWorkflowStep(order=10, instruction="first")

    with pytest.raises(ValueError, match="ordered"):
        ThreadWorkflow(workflow_id="research", steps=(first, second))

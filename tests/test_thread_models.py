from __future__ import annotations

import pytest

from goal_chainer.thread_models import (
    ThreadBudget,
    ThreadMergePolicy,
    ThreadRoles,
    ThreadSupervision,
    ThreadTask,
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


def test_integration_merge_policy_requires_a_branch() -> None:
    with pytest.raises(ValueError, match="integration branch"):
        ThreadMergePolicy(mode="integration-branch", integration_branch=None)

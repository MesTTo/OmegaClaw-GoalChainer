from __future__ import annotations

import stat

import pytest
from thread_spec_fixture import VALID_THREAD_SPEC, VALID_THREAD_SPEC_V2

from goal_chainer.directive import DirectiveSession
from goal_chainer.snars_runtime import SnarsRuntime
from goal_chainer.thread_models import ThreadSpecificationError
from goal_chainer.thread_plan import compile_thread_markdown
from goal_chainer.thread_runtime import ThreadRuntime


@pytest.fixture(scope="module")
def runtime() -> ThreadRuntime:
    return ThreadRuntime(SnarsRuntime(require_text_ingestion=False))


def test_compile_preflights_without_creating_a_plan(runtime) -> None:
    result = compile_thread_markdown(
        VALID_THREAD_SPEC,
        thread_runtime=runtime,
    )

    assert result.plan_path is None
    assert result.snapshot.board.ready == ("collect-evidence",)
    assert result.snapshot.board.backlog == ("redact-summary",)
    assert "source-digest" in result.plan


def test_compile_creates_a_private_durable_omega_plan(tmp_path, runtime) -> None:
    path = tmp_path / "incident.metta"

    result = compile_thread_markdown(
        VALID_THREAD_SPEC,
        source_path="incident.md",
        plan_path=path,
        thread_runtime=runtime,
    )

    assert result.plan_path == str(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert DirectiveSession(path).snapshot().value.board.ready == ("collect-evidence",)


def test_v2_plan_binds_project_and_version(runtime) -> None:
    result = compile_thread_markdown(
        VALID_THREAD_SPEC_V2,
        thread_runtime=runtime,
    )

    assert result.specification.project_id == "project-incident-42"
    assert dict(result.snapshot.info)["project"] == "project-incident-42"
    assert dict(result.snapshot.info)["version"] == "thread-spec-v2"


def test_cycle_is_rejected_before_durable_plan_creation(tmp_path, runtime) -> None:
    source = VALID_THREAD_SPEC.replace(
        "(thread-depends incident-42 redact-summary collect-evidence)",
        (
            "(thread-depends incident-42 redact-summary collect-evidence)\n"
            "(thread-depends incident-42 collect-evidence redact-summary)"
        ),
    )
    destination = tmp_path / "cycle.metta"

    with pytest.raises(ThreadSpecificationError, match="cycle"):
        compile_thread_markdown(
            source,
            plan_path=destination,
            thread_runtime=runtime,
        )

    assert not destination.exists()

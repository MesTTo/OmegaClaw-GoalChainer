from __future__ import annotations

import pytest

from goal_chainer.snars_program import SexprCodec
from goal_chainer.snars_runtime import SnarsRuntime
from goal_chainer.thread_models import (
    ParsedThreadMarkdown,
    ThreadFact,
    ThreadProtocolError,
    ThreadSpecificationError,
)
from goal_chainer.thread_protocol import parse_thread_output


@pytest.fixture(scope="module")
def codec() -> SexprCodec:
    return SexprCodec(SnarsRuntime(require_text_ingestion=False))


@pytest.fixture
def parsed_markdown() -> ParsedThreadMarkdown:
    return ParsedThreadMarkdown(
        facts=(ThreadFact("(thread-spec-v1 incident-42)", 4),),
        semantic_digest="a" * 64,
        source_path="/specs/incident.md",
    )


def test_compile_protocol_builds_typed_specification(
    codec,
    parsed_markdown,
) -> None:
    run = parse_thread_output(
        [
            "(goalchainer-thread-v1 compile ok",
            "  (compilation",
            "    (valid True)",
            "    (errors ())",
            '    (thread incident-42 "Incident response" responder)',
            "    (budget 120000 60000 1)",
            "    (supervision 30 5 60 2)",
            "    (roles local-control local-worker thread-supervisor",
            "      result-evaluator security-specialist security-owner)",
            "    (workflow guided-research",
            '      ((step 10 "Inspect existing work.")',
            '       (step 20 "Verify acceptance.")))',
            "    (mcp-access oh-my-goals",
            "      (remember query solve revise forget explain",
            "       find_papers ingest_paper add_claim citations review check_retractions))",
            "    (tasks",
            "      ((task collect-evidence local evidence-collected normal (depends ()) (not-before none))",
            "       (task redact-summary specialist summary-redacted high",
            "         (depends (collect-evidence)) (not-before 1785283200))))",
            "    (merge-policy none none)))",
        ],
        codec,
        expected_operation="compile",
        parsed_markdown=parsed_markdown,
    )

    spec = run.value
    assert spec.thread_id == "incident-42"
    assert spec.budget.soft_threshold_tokens == 60000
    assert spec.roles.evaluator == "result-evaluator"
    assert spec.workflow.workflow_id == "guided-research"
    assert spec.workflow.steps[1].instruction == "Verify acceptance."
    assert spec.mcp_access.profile == "oh-my-goals"
    assert spec.mcp_access.tools[0] == "remember"
    assert spec.mcp_access.tools[-1] == "check_retractions"
    assert spec.tasks[1].dependencies == ("collect-evidence",)
    assert spec.tasks[1].not_before_epoch == 1785283200
    assert spec.semantic_digest == "a" * 64


def test_compile_protocol_surfaces_metta_validation_errors(
    codec,
    parsed_markdown,
) -> None:
    with pytest.raises(ThreadSpecificationError, match="missing-title"):
        parse_thread_output(
            [
                "(goalchainer-thread-v1 compile ok",
                "  (compilation (valid False) (errors (missing-title))))",
            ],
            codec,
            expected_operation="compile",
            parsed_markdown=parsed_markdown,
        )


def test_route_protocol_parses_adjudication(codec) -> None:
    run = parse_thread_output(
        [
            "(goalchainer-thread-v1 route ok",
            '  (route specialist True "under soft threshold" True))',
        ],
        codec,
        expected_operation="route",
    )

    assert run.value.target == "specialist"
    assert run.value.allowed is True
    assert run.value.requires_adjudication is True


def test_release_protocol_parses_schedule_decision(codec) -> None:
    run = parse_thread_output(
        [
            "(goalchainer-thread-v1 release ok",
            '  (release False "not-before constraint has not elapsed"))',
        ],
        codec,
        expected_operation="release",
    )

    assert run.value.allowed is False
    assert run.value.reason == "not-before constraint has not elapsed"


def test_ui_protocol_parses_metta_owned_projection(codec) -> None:
    run = parse_thread_output(
        [
            "(goalchainer-thread-v1 ui ok",
            "  (ui-projection",
            "    (summary 2 1 0 0 0 0 1 50)",
            "    (tasks",
            '      ((ui-task collect local accept normal () scheduled False',
            '         worker 0 none 200 "not-before constraint has not elapsed")',
            '       (ui-task publish local published normal (collect) done False',
            '         worker 1 session-7 none "")))))',
        ],
        codec,
        expected_operation="ui",
    )

    assert run.value["summary"] == {
        "total": 2,
        "scheduled": 1,
        "backlog": 0,
        "ready": 0,
        "inProgress": 0,
        "blocked": 0,
        "done": 1,
        "progressPct": 50,
    }
    assert run.value["tasks"][0]["notBeforeEpoch"] == 200
    assert run.value["tasks"][1]["sessionId"] == "session-7"


def test_ui_protocol_rejects_summary_drift(codec) -> None:
    with pytest.raises(
        ThreadProtocolError,
        match="summary does not match",
    ):
        parse_thread_output(
            [
                "(goalchainer-thread-v1 ui ok",
                "  (ui-projection",
                "    (summary 1 0 0 1 0 0 0 0)",
                "    (tasks",
                '      ((ui-task collect local accept normal () done False',
                '         none 0 none none "")))))',
            ],
            codec,
            expected_operation="ui",
        )


def test_outcome_protocol_parses_retry(codec) -> None:
    run = parse_thread_output(
        [
            "(goalchainer-thread-v1 outcome ok",
            '  (outcome retry "worker exited with status 2"))',
        ],
        codec,
        expected_operation="outcome",
    )

    assert run.value.outcome == "retry"
    assert run.value.reason == "worker exited with status 2"

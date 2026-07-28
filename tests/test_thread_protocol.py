from __future__ import annotations

import pytest

from goal_chainer.snars_program import SexprCodec
from goal_chainer.snars_runtime import SnarsRuntime
from goal_chainer.thread_models import (
    ParsedThreadMarkdown,
    ThreadFact,
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
            "    (tasks",
            "      ((task collect-evidence local evidence-collected normal (depends ()))",
            "       (task redact-summary specialist summary-redacted high",
            "         (depends (collect-evidence)))))",
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
    assert spec.tasks[1].dependencies == ("collect-evidence",)
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

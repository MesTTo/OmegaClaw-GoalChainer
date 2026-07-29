from __future__ import annotations

import pytest
from thread_spec_fixture import VALID_THREAD_SPEC, VALID_THREAD_SPEC_V2

from goal_chainer.snars_runtime import SnarsRuntime
from goal_chainer.thread_models import ThreadSpecificationError
from goal_chainer.thread_spec import parse_thread_markdown


@pytest.fixture(scope="module")
def runtime() -> SnarsRuntime:
    return SnarsRuntime(require_text_ingestion=False)


def test_parse_thread_markdown_uses_mettabase_normalized_facts(runtime) -> None:
    parsed = parse_thread_markdown(
        VALID_THREAD_SPEC,
        runtime=runtime,
        source_path="incident.md",
    )

    assert parsed.source_path == "incident.md"
    assert parsed.facts[0].atom == "(thread-spec-v1 incident-42)"
    assert parsed.facts[0].line == 6
    assert parsed.facts[-1].atom == "(thread-merge-policy incident-42 none none)"
    assert len(parsed.semantic_digest) == 64


def test_semantic_digest_ignores_explanatory_prose(runtime) -> None:
    first = parse_thread_markdown(VALID_THREAD_SPEC, runtime=runtime)
    second = parse_thread_markdown(
        VALID_THREAD_SPEC.replace(
            "The prose is explanatory and is not policy.",
            "Different prose. The semantic facts remain unchanged.",
        ),
        runtime=runtime,
    )

    assert first.semantic_digest == second.semantic_digest


def test_parse_thread_markdown_accepts_v2_identity_facts(runtime) -> None:
    parsed = parse_thread_markdown(VALID_THREAD_SPEC_V2, runtime=runtime)

    assert parsed.spec_version == "thread-spec-v2"
    assert any(
        fact.atom == '(thread-project incident-42 "project-incident-42")'
        for fact in parsed.facts
    )
    assert any(
        fact.atom
        == "(thread-atomspace-link incident-42 project-shared shared project)"
        for fact in parsed.facts
    )


@pytest.mark.parametrize("head", ["thread-agent-id", "thread-atomspace-path"])
def test_v2_markdown_rejects_durable_ids_and_raw_paths(runtime, head) -> None:
    source = f"""\
```metta
(thread-spec-v2 incident-42)
({head} incident-42 unsafe "/outside/project")
```
"""
    with pytest.raises(ThreadSpecificationError, match="not allowed"):
        parse_thread_markdown(source, runtime=runtime)


def test_parse_thread_markdown_rejects_evaluation_actions(runtime) -> None:
    source = """\
```metta
!(thread-spec-v1 incident-42)
```
"""
    with pytest.raises(ThreadSpecificationError, match="evaluation"):
        parse_thread_markdown(source, runtime=runtime)


def test_parse_thread_markdown_rejects_malformed_metta(runtime) -> None:
    source = """\
```metta
(thread-spec-v1 incident-42
```
"""
    with pytest.raises(ThreadSpecificationError, match="line 2"):
        parse_thread_markdown(source, runtime=runtime)


def test_parse_thread_markdown_rejects_unclosed_metta_fence(runtime) -> None:
    source = """\
```metta
(thread-spec-v1 incident-42)
"""
    with pytest.raises(ThreadSpecificationError, match="unclosed metta code fence"):
        parse_thread_markdown(source, runtime=runtime)


def test_parse_thread_markdown_rejects_unrecognized_fact_heads(runtime) -> None:
    source = """\
```metta
(thread-spec-v1 incident-42)
(py-call dangerous)
```
"""
    with pytest.raises(ThreadSpecificationError, match="not allowed"):
        parse_thread_markdown(source, runtime=runtime)


def test_parse_thread_markdown_requires_semantic_facts(runtime) -> None:
    with pytest.raises(ThreadSpecificationError, match="no semantic"):
        parse_thread_markdown("# Prose only\n", runtime=runtime)

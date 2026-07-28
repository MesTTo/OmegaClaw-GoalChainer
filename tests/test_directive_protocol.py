from __future__ import annotations

from types import SimpleNamespace

import pytest

from goal_chainer.directive_models import DirectiveProtocolError
from goal_chainer.directive_protocol import parse_directive_output
from goal_chainer.snars_program import SexprCodec
from goal_chainer.snars_runtime import REPO_ROOT


@pytest.fixture
def codec():
    runtime = SimpleNamespace(
        diagnostics=SimpleNamespace(mettabase_dir=REPO_ROOT / "external" / "mettabase")
    )
    return SexprCodec(runtime)


def test_markdown_protocol_preserves_literal_multiline_strings(codec) -> None:
    run = parse_directive_output(
        [
            "rendering audit",
            "(goalchainer-directive-v1 markdown ok",
            '  (markdown "# Board',
            "",
            "| Task | State |",
            "| --- | --- |",
            '| collect | ready |"))',
        ],
        codec,
        expected_operation="markdown",
    )

    assert run.value == (
        "# Board\n\n| Task | State |\n| --- | --- |\n| collect | ready |"
    )
    assert run.transcript == ("rendering audit",)


def test_directive_protocol_rejects_duplicate_machine_records(codec) -> None:
    record = "(goalchainer-directive-v1 task-state ok (task-state collect ready))"

    with pytest.raises(DirectiveProtocolError, match="exactly one"):
        parse_directive_output(
            [record, record],
            codec,
            expected_operation="task-state",
        )


def test_directive_protocol_rejects_malformed_lifecycle_result(codec) -> None:
    with pytest.raises(DirectiveProtocolError, match="malformed"):
        parse_directive_output(
            [
                "(goalchainer-directive-v1 lifecycle ok "
                "(lifecycle "
                "(kind claim) "
                "(result (err)) "
                "(snapshot (snapshot))))"
            ],
            codec,
            expected_operation="lifecycle",
        )


def test_directive_protocol_rejects_unknown_task_state(codec) -> None:
    with pytest.raises(DirectiveProtocolError, match="Unknown.*state"):
        parse_directive_output(
            ["(goalchainer-directive-v1 task-state ok (task-state collect invented))"],
            codec,
            expected_operation="task-state",
        )


def test_directive_protocol_wraps_missing_snapshot_fields(codec) -> None:
    with pytest.raises(DirectiveProtocolError, match="payload is malformed"):
        parse_directive_output(
            ["(goalchainer-directive-v1 snapshot ok (snapshot (board)))"],
            codec,
            expected_operation="snapshot",
        )


def test_directive_protocol_rejects_duplicate_fields(codec) -> None:
    with pytest.raises(DirectiveProtocolError, match="duplicated"):
        parse_directive_output(
            [
                "(goalchainer-directive-v1 validate ok "
                "(validation (valid true) (valid false) (strict false)))"
            ],
            codec,
            expected_operation="validate",
        )

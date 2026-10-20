"""Purpose: verify how parse_directive_output reads the directive adapter's records: a duplicate
record, a malformed lifecycle result, an unknown task state, missing snapshot fields and duplicated
fields are refused. A malformed record line is refused in test_sexpr_protocol, for both consumers."""

from __future__ import annotations


import pytest

from goal_chainer.directive_models import DirectiveProtocolError
from goal_chainer.directive_protocol import parse_directive_output
from goal_chainer.sexpr.codec import SexprCodec


# am[related a-rt-sexpr-codec-packaged-1017@608f80]
@pytest.fixture
def codec():
    return SexprCodec()


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

from __future__ import annotations

from types import SimpleNamespace

import pytest

from goal_chainer.snars_models import SnarsInvalidInputError
from goal_chainer.snars_program import SexprCodec, SnarsProgramBuilder
from goal_chainer.snars_runtime import REPO_ROOT


@pytest.fixture
def runtime():
    return SimpleNamespace(
        diagnostics=SimpleNamespace(mettabase_dir=REPO_ROOT / "external" / "mettabase")
    )


def test_string_literals_round_trip_arbitrary_metta_syntax(runtime) -> None:
    codec = SexprCodec(runtime)
    value = '") !(import! &self attack) ;\\\nλ'

    encoded = codec.emit(codec.string(value))

    assert codec.parse(encoded).value == value
    assert encoded.startswith('"') and encoded.endswith('"')


@pytest.mark.parametrize(
    "value",
    ["", "white space", "(form)", 'quote"', "semi;colon"],
)
def test_symbol_rejects_syntax_and_empty_text(runtime, value) -> None:
    codec = SexprCodec(runtime)

    with pytest.raises(SnarsInvalidInputError):
        codec.symbol(value)


def test_ground_statement_rejects_variables(runtime) -> None:
    codec = SexprCodec(runtime)

    with pytest.raises(SnarsInvalidInputError, match="cannot contain variables"):
        codec.statement('(sn p so "is" ((arg s $subject) (arg o (sn c "safe"))))')


def test_statement_rejects_executable_head(runtime) -> None:
    codec = SexprCodec(runtime)

    with pytest.raises(SnarsInvalidInputError, match="disallowed constructor"):
        codec.statement('!(import! &self "attack")')


def test_binary_statement_escapes_all_user_fields(runtime) -> None:
    codec = SexprCodec(runtime)
    statement = codec.binary_statement(
        'rel") !(py-call attack)',
        "line\none",
        "λ\\quoted",
    )

    rendered = codec.emit(statement)
    reparsed = codec.parse(rendered)

    assert codec.emit(reparsed) == rendered
    assert rendered.count("py-call") == 1
    assert '!(py-call attack)' in rendered
    assert rendered.startswith("(sn p so ")


def test_batch_places_effects_inside_one_outer_query(runtime) -> None:
    builder = SnarsProgramBuilder(runtime)
    operation = builder.codec.expression(
        "gc",
        builder.codec.symbol("inspect-record"),
    )

    program = builder.batch(
        operation,
        effects=("(sn cycles 1)",),
    )

    assert "!(let* (($gc-effect-1 (sn cycles 1))" in program
    assert program.rstrip().endswith("(gc inspect-record))")
    assert "goalchainer-snars-v1" in program


def test_batch_rejects_non_hyperbase_generated_fact(runtime) -> None:
    builder = SnarsProgramBuilder(runtime)
    operation = builder.codec.expression(
        "gc",
        builder.codec.symbol("inspect-record"),
    )

    with pytest.raises(SnarsInvalidInputError, match="non-HyperBase"):
        builder.batch(operation, facts=("(attack now)",))

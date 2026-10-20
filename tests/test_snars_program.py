"""Purpose: test the MeTTa text codec's escaping and statement checks, and SNARS batches: what a
batch carries, the checks made when one is built, and the modules each feature set's world loads
in order."""

from __future__ import annotations

import sys

import pytest

from goal_chainer.domains.readings import forms
from goal_chainer.errors import InvalidInputError
from goal_chainer.semantic_reader import SemanticReader
from goal_chainer.snars_program import (
    FEATURES,
    POLICY_PATH,
    PROTOCOL_PATH,
    SNARS_DIRECTORY,
    SnarsBatch,
    SnarsProgramBuilder,
    binary_statement,
    parse_statement,
    world_modules,
)
from goal_chainer.sexpr.codec import SexprCodec
from reading_support import INCIDENT

GUARD_PATH = SNARS_DIRECTORY / "snars-guard.metta"


# am[verifies a-rt-snars-batch-value-1017@0e8147]
def _inspect(builder: SnarsProgramBuilder):
    return builder.codec.expression("gc", builder.codec.symbol("inspect-record"))


# A reader of the incident declaration, as a session is opened with; making one loads no model.
# am[verifies a-dr-sr-snars-batch-declaration-1018@5c965d]
def _reader() -> SemanticReader:
    return SemanticReader(declaration=INCIDENT)


# am[related a-rt-sexpr-codec-packaged-1017@608f80]
def test_string_literals_round_trip_arbitrary_metta_syntax() -> None:
    codec = SexprCodec()
    value = '") !(import! &self attack) ;\\\nλ'

    encoded = codec.emit(codec.string(value))

    assert codec.parse(encoded).value == value
    assert encoded.startswith('"') and encoded.endswith('"')


# am[related a-rt-sexpr-codec-packaged-1017@608f80]
@pytest.mark.parametrize(
    "value",
    ["", "white space", "(form)", 'quote"', "semi;colon"],
)
def test_symbol_rejects_syntax_and_empty_text(value) -> None:
    codec = SexprCodec()

    with pytest.raises(InvalidInputError):
        codec.symbol(value)


# am[related a-rt-sexpr-codec-packaged-1017@608f80]
def test_ground_statement_rejects_variables() -> None:
    with pytest.raises(InvalidInputError, match="cannot contain variables"):
        parse_statement('(sn p so "is" ((arg s $subject) (arg o (sn c "safe"))))')


# am[related a-rt-sexpr-codec-packaged-1017@608f80]
def test_statement_rejects_executable_head() -> None:
    with pytest.raises(InvalidInputError, match="disallowed constructor"):
        parse_statement('!(import! &self "attack")')


# am[related a-rt-sexpr-codec-packaged-1017@608f80]
def test_binary_statement_escapes_all_user_fields() -> None:
    codec = SexprCodec()
    statement = binary_statement(
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


# Every codec reads and writes through one module, so atoms one parses are the classes another
# compares against.
# am[verifies a-rt-sexpr-codec-packaged-1017@608f80]
def test_every_codec_shares_the_packaged_atom_classes() -> None:
    first, second = SexprCodec(), SexprCodec()

    assert isinstance(first.parse("(a b)")[0], second.Symbol)
    assert first.Symbol is second.Symbol and first.StringLiteral is second.StringLiteral


# am[verifies a-rt-snars-batch-value-1017@0e8147]
def test_batch_places_effects_inside_one_outer_query() -> None:
    builder = SnarsProgramBuilder()

    batch = builder.batch(_inspect(builder), effects=("(sn cycles 1)",))

    assert batch == SnarsBatch((), frozenset(), "(let* (($gc-effect-1 (sn cycles 1))) (gc inspect-record))")


# The policy believes the request's readings and runs two cycles before the operation, after the
# caller's own effects.
# am[verifies a-rt-snars-batch-value-1017@0e8147] am[verifies a-ie-s7-metta-1018@0ca8fe]
def test_the_policy_feature_adds_its_effects_after_the_callers() -> None:
    builder = SnarsProgramBuilder(_reader())

    batch = builder.batch(_inspect(builder), effects=("(sn cycles 1)",), includes={"policy"})

    assert batch.includes == frozenset({"policy"})
    assert batch.directive == (
        "(let* (($gc-effect-1 (sn cycles 1)) ($gc-effect-2 (gc assert-request-context!)) "
        "($gc-effect-3 (sn cycles 2))) (gc inspect-record))"
    )


# am[verifies a-jev-snars-ingest-1016] am[verifies a-rt-snars-batch-value-1017@0e8147]
def test_batch_rejects_a_fact_that_is_not_a_reading() -> None:
    builder = SnarsProgramBuilder(_reader())

    with pytest.raises(InvalidInputError, match="gc-reading"):
        builder.batch(_inspect(builder), facts=("(attack now)",))


# A batch carries the declaration its readings were admitted against, and its rows go to the world
# only with the policy, the one module that reads them. A batch with readings and no declaration is
# refused; one without readings needs none, the policy's included, whose rows are then empty, as a
# session opened without a reader builds them.
# am[verifies a-dr-sr-snars-batch-declaration-1018@5c965d] am[verifies a-ie-sr-readerless-session-1018@9ffb9b]
def test_a_batch_carries_its_declaration_and_its_rows_only_with_the_policy() -> None:
    builder = SnarsProgramBuilder(_reader())
    with_policy = builder.batch(_inspect(builder), facts=(_reading("ctx", 1.0, "sensitive-data"),), includes={"policy"})
    without = builder.batch(_inspect(builder), facts=(_reading("ctx", 1.0, "sensitive-data"),), includes={"guard"})

    assert with_policy.declaration is INCIDENT and with_policy.rows == forms(INCIDENT)
    assert without.declaration is INCIDENT and without.rows == ()
    pure = SnarsProgramBuilder().batch(_inspect(builder))
    readerless = SnarsProgramBuilder().batch(_inspect(builder), includes={"policy"})
    assert pure.declaration is None and pure.rows == ()
    assert readerless.declaration is None and readerless.rows == () and readerless.includes == {"policy"}
    for includes in (frozenset(), frozenset({"policy"})):
        with pytest.raises(InvalidInputError, match="needs the reading declaration"):
            SnarsBatch((_reading("ctx", 1.0, "sensitive-data"),), includes, "(gc inspect-record)")
    with pytest.raises(InvalidInputError, match="must be a ReadingDeclaration"):
        SnarsBatch((), frozenset({"policy"}), "(gc inspect-record)", "incident")
    with pytest.raises(InvalidInputError, match="needs the reader its session was opened with"):
        SnarsProgramBuilder().text_ingestion("Raw logs.", source="s", trust=1.0, budget=None)


# A declaration refused for being no ReadingDeclaration is named where repr cannot write it.
# am[verifies a-rt-rr-safe-repr-1018@ec9700]
def test_a_batch_names_a_declaration_repr_cannot_write() -> None:
    with pytest.raises(InvalidInputError, match="must be a ReadingDeclaration") as refusal:
        SnarsBatch((), frozenset({"policy"}), "(gc inspect-record)", 10**5000)

    assert refusal.value.details["declaration"] == f"an integer of more than {sys.get_int_max_str_digits()} digits"


# am[verifies a-rt-snars-batch-value-1017@0e8147]
def test_a_batch_includes_only_features_the_world_modules_define() -> None:
    builder = SnarsProgramBuilder()

    with pytest.raises(InvalidInputError, match="optional features"):
        builder.batch(_inspect(builder), includes={"policy", "hyperbase"})
    with pytest.raises(InvalidInputError, match="frozenset"):
        SnarsBatch((), {"policy"}, "(gc inspect-record)")


# A directive is one expression: anything that would add a second top-level form, or leave one
# open, is refused, since the engine would run every form it reads.
# am[verifies a-rt-snars-batch-value-1017@0e8147]
@pytest.mark.parametrize(
    "directive",
    [
        "(gc inspect-record) (= (gc attack) x)",
        "(gc inspect-record)) (!(gc attack)",
        "(gc inspect-record",
        "gc",
        "",
        "()",
    ],
)
def test_a_batch_directive_is_exactly_one_expression(directive) -> None:
    with pytest.raises(InvalidInputError):
        SnarsBatch((), frozenset(), directive)


# One reading of the reading table as a gc-reading fact, under a source and trust.
# am[verifies a-ev-wt-context-mean-1017@46162f]
def _reading(source: str, trust: float, reading_id: str) -> str:
    return (f'(gc-reading "{source}" {trust} {reading_id} supported 0.9 '
            f'(provenance "jev-1.13.0" "key-{reading_id}" "a passage"))')


# A source's readings carry one trust, since the policy believes them once under it: a batch that
# gives one source two trusts is refused, naming the source and its trusts, and one in which two
# sources differ in trust is made.
# am[verifies a-ev-wt-context-mean-1017@46162f] am[rests-on c-ev-rt-agrees-batch-trust-1017@18bf73]
def test_a_batch_refuses_two_trusts_for_one_source_and_takes_one_per_source() -> None:
    with pytest.raises(InvalidInputError, match="one trust") as refused:
        SnarsBatch(
            (_reading("ctx", 1.0, "sensitive-data"), _reading("ctx", 0.0, "public-data")),
            frozenset(),
            "(gc inspect-record)",
            INCIDENT,
        )
    made = SnarsBatch(
        (_reading("ctx", 1.0, "sensitive-data"), _reading("other", 0.0, "public-data")),
        frozenset(),
        "(gc inspect-record)",
        INCIDENT,
    )

    assert refused.value.details == {"source": "ctx", "trusts": [0.0, 1.0]}
    assert len(made.facts) == 2


# The modules each world loads after SNARS, in the order batch programs always loaded them; no world
# loads a reading declaration, which each batch carries, and none loads a scoring policy.
# am[verifies a-rt-snars-batch-value-1017@0e8147]
# am[verifies a-integrate-ecan-feature-test-1017] am[verifies a-dr-sr-snars-batch-declaration-1018@5c965d]
# am[verifies a-ie-s2b-scalar-modules-1018@df30d8]
@pytest.mark.parametrize("attention", [False, True], ids=["native", "attention"])
@pytest.mark.parametrize(
    "includes, modules",
    [
        (frozenset(), (PROTOCOL_PATH,)),
        (frozenset({"policy"}), (POLICY_PATH, PROTOCOL_PATH)),
        (frozenset({"guard"}), (PROTOCOL_PATH, GUARD_PATH)),
        (frozenset({"policy", "guard"}), (POLICY_PATH, PROTOCOL_PATH, GUARD_PATH)),
    ],
)
def test_each_feature_set_loads_its_modules_in_batch_order(includes, modules, attention) -> None:
    assert FEATURES == ("policy", "guard", "attention")
    if attention:
        includes |= {"attention"}
        modules += tuple(PROTOCOL_PATH.with_name(name) for name in (
            "goalchainer_attention.metta", "goalchainer_attention_graph.metta",
            "goalchainer_attention_control.metta", "goalchainer_attention_query.metta",
        ))
    assert world_modules(includes) == modules
    assert all(path.is_file() for path in modules)

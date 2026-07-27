from __future__ import annotations

from types import SimpleNamespace

import pytest

from goal_chainer.snars_models import SnarsProtocolError
from goal_chainer.snars_program import SexprCodec
from goal_chainer.snars_protocol import (
    atom_to_python,
    parse_belief,
    parse_protocol_output,
    state_digest,
)
from goal_chainer.snars_runtime import REPO_ROOT


@pytest.fixture
def codec():
    runtime = SimpleNamespace(
        diagnostics=SimpleNamespace(mettabase_dir=REPO_ROOT / "external" / "mettabase")
    )
    return SexprCodec(runtime)


def test_protocol_parses_strings_empty_lists_and_exponent_numbers(codec) -> None:
    envelope = parse_protocol_output(
        [
            "true",
            '(goalchainer-snars-v1 ask ok '
            '(answers ("quoted \\"source\\"" () -2 3.5 4e-2)))',
        ],
        codec,
        expected_operation="ask",
    )

    assert atom_to_python(envelope.payload, codec) == [
        "answers",
        ['quoted "source"', [], -2, 3.5, 0.04],
    ]


def test_protocol_rejects_unknown_version(codec) -> None:
    with pytest.raises(SnarsProtocolError, match="Unsupported"):
        parse_protocol_output(
            ["(goalchainer-snars-v2 ask ok (answers ()))"],
            codec,
        )


def test_protocol_requires_exactly_one_tagged_record(codec) -> None:
    with pytest.raises(SnarsProtocolError, match="exactly one"):
        parse_protocol_output(
            [
                "(goalchainer-snars-v1 ask ok (answers ()))",
                "(goalchainer-snars-v1 ask ok (answers ()))",
            ],
            codec,
        )


def test_protocol_rejects_operation_mismatch(codec) -> None:
    with pytest.raises(SnarsProtocolError, match="does not match"):
        parse_protocol_output(
            ["(goalchainer-snars-v1 prove ok (proof-result))"],
            codec,
            expected_operation="ask",
        )


def test_belief_parser_preserves_receipts_opinion_evidence_and_stamps(codec) -> None:
    envelope = parse_protocol_output(
        [
            """
            (goalchainer-snars-v1 belief ok
              (belief sid-1
                (sh (tag P d so ()) "is"
                  (args ((arg s (sn c "a")) (arg o (sn c "b")))))
                (opinion 0.6 0.1 0.3 0.5)
                (evidence 6 1 0.5)
                (receipts ((receipt receipt-1 "source one" sid-1 0.75)))
                (proofs ((proof
                  (Opinion 0.6 0.1 0.3 0.5)
                  (rule-a ax-1 ax-2)
                  (sh (tag P d so ()) "is"
                    (args ((arg s (sn c "a")) (arg o (sn c "b")))))
                  (stamps (ax-1 ax-2)))))
                (occurrences ())))
            """
        ],
        codec,
        expected_operation="belief",
    )

    belief = parse_belief(envelope.payload, codec)

    assert belief.statement_id == "sid-1"
    assert belief.opinion.expectation == pytest.approx(0.75)
    assert belief.evidence.positive == 6
    assert belief.sources == ("source one",)
    assert belief.receipts[0].trust == 0.75
    assert belief.proofs[0].kind == "rule-a"
    assert belief.proofs[0].axiom_stamps == ("ax-1", "ax-2")
    assert [premise.kind for premise in belief.proofs[0].premises] == [
        "axiom",
        "axiom",
    ]


def test_state_digest_is_structural_and_deterministic(codec) -> None:
    atom = codec.parse('(state (receipt "a") (opinion 0.5 0.0 0.5 0.5))')

    assert state_digest(atom, codec) == state_digest(
        codec.parse(codec.emit(atom)),
        codec,
    )
    assert state_digest(atom, codec) != state_digest(
        codec.parse('(state (receipt "b") (opinion 0.5 0.0 0.5 0.5))'),
        codec,
    )

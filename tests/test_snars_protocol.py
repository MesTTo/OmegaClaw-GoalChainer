from __future__ import annotations

from types import SimpleNamespace

import pytest

from goal_chainer.snars_models import SnarsProtocolError
from goal_chainer.snars_program import SexprCodec
from goal_chainer.snars_protocol import (
    atom_to_python,
    parse_assessment,
    parse_belief,
    parse_counterfactual,
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


def _belief_record(statement_id: str, expectation: float = 0.75) -> str:
    belief = expectation - 0.1
    uncertainty = 0.2
    disbelief = 1.0 - belief - uncertainty
    return f"""
      (belief {statement_id}
        (sn p so "acceptable" ((arg s (sn c "action")) (arg o (sn c "state"))))
        (opinion {belief} {disbelief} {uncertainty} 0.5)
        (evidence 6 1 0.5)
        (receipts ((receipt receipt-{statement_id} "request" {statement_id} 1.0)))
        (proofs ())
        (occurrences ()))
    """


def test_assessment_parser_preserves_three_beliefs_and_conflict(codec) -> None:
    payload = codec.parse(
        f"""
        (assessment
          (action "publish_raw_log"
            (acceptable {_belief_record("acceptable-id", 0.3)})
            (risky {_belief_record("risky-id", 0.8)})
            (forbidden {_belief_record("forbidden-id", 0.7)})
            (conflict 0.25)))
        """
    )

    assessments = parse_assessment(payload, codec)

    assert [row.action_id for row in assessments] == ["publish_raw_log"]
    assert assessments[0].acceptable.opinion.expectation == pytest.approx(0.3)
    assert assessments[0].risky.statement_id == "risky-id"
    assert assessments[0].forbidden.statement_id == "forbidden-id"
    assert assessments[0].conflict_degree == 0.25


def test_belief_parser_deduplicates_repeated_supporting_receipts(codec) -> None:
    payload = codec.parse(
        """
        (belief conclusion-id
          (sn p so "acceptable" ((arg s (sn c "action")) (arg o (sn c "state"))))
          (opinion 0.6 0.1 0.3 0.5)
          (evidence 6 1 0.5)
          (receipts
            ((receipt receipt-1 "request" premise-id 0.75)
             (receipt receipt-1 "request" premise-id 0.75)))
          (proofs ())
          (occurrences ()))
        """
    )

    belief = parse_belief(payload, codec)

    assert len(belief.receipts) == 1
    assert belief.receipts[0].statement_id == "premise-id"


def test_counterfactual_parser_checks_structural_rollback(codec) -> None:
    payload = codec.parse(
        """
        (counterfactual
          (hypothesis (sn p so "is" ((arg s (sn c "request")) (arg o (sn c "public")))))
          (query (sn p so "is" ((arg s (sn c "raw")) (arg o (sn c "acceptable")))))
          (opinion (Opinion 0.7 0.1 0.2 0.5))
          (proofs ())
          (state-before (state (statements ()) (receipts ())))
          (state-after (state (statements ()) (receipts ()))))
        """
    )

    result = parse_counterfactual(payload, codec)

    assert result.opinion.expectation == pytest.approx(0.8)
    assert result.digest_before == result.digest_after


def test_counterfactual_parser_rejects_state_leak(codec) -> None:
    payload = codec.parse(
        """
        (counterfactual
          (hypothesis (sn p so "is" ((arg s (sn c "request")) (arg o (sn c "public")))))
          (query (sn p so "is" ((arg s (sn c "raw")) (arg o (sn c "acceptable")))))
          (opinion (Opinion 0.7 0.1 0.2 0.5))
          (proofs ())
          (state-before (state (statements ())))
          (state-after (state (statements (changed)))))
        """
    )

    with pytest.raises(SnarsProtocolError, match="roll back"):
        parse_counterfactual(payload, codec)

"""Purpose: test the parsers of GoalChainer's versioned SNARS protocol: its envelope, beliefs with
their receipts, state digests and counterfactual rollback."""

from __future__ import annotations


import pytest
from hypothesis import given, settings, strategies as st

from goal_chainer.errors import ProtocolError
from goal_chainer.sexpr.codec import SexprCodec
from goal_chainer.snars_protocol import (
    atom_to_python,
    parse_belief,
    parse_counterfactual,
    parse_protocol_output,
    state_digest,
)


# am[related a-rt-sexpr-codec-packaged-1017@608f80]
@pytest.fixture
def codec():
    return SexprCodec()


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
    with pytest.raises(ProtocolError, match="Unsupported"):
        parse_protocol_output(
            ["(goalchainer-snars-v2 ask ok (answers ()))"],
            codec,
        )


def test_protocol_requires_exactly_one_tagged_record(codec) -> None:
    with pytest.raises(ProtocolError, match="exactly one"):
        parse_protocol_output(
            [
                "(goalchainer-snars-v1 ask ok (answers ()))",
                "(goalchainer-snars-v1 ask ok (answers ()))",
            ],
            codec,
        )


def test_protocol_rejects_operation_mismatch(codec) -> None:
    with pytest.raises(ProtocolError, match="does not match"):
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


# am[verifies a-v2-receipt-conflict-refusal-1020@051877]
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


# am[verifies a-v2-receipt-conflict-refusal-1020@051877]
def _receipt_belief(codec, receipts):
    return parse_belief(codec.parse(
        '(belief conclusion (sn c "claim") (opinion 0.6 0.1 0.3 0.5) '
        f'(evidence 6 1 0.5) (receipts ({" ".join(receipts)})) '
        '(proofs ()) (occurrences ()))'
    ), codec)


# am[verifies a-v2-receipt-conflict-refusal-1020@051877]
@pytest.mark.parametrize("changed", [
    '(receipt receipt-1 "different source" premise-id 0.75)',
    '(receipt receipt-1 "request" premise-id 0.25)',
])
def test_belief_parser_refuses_conflicting_receipt_payloads_in_either_order(codec, changed):
    original = '(receipt receipt-1 "request" premise-id 0.75)'
    for rows in ((original, changed), (changed, original)):
        with pytest.raises(ProtocolError, match="conflicting payloads") as caught:
            _receipt_belief(codec, rows)
        assert caught.value.details == {"receipt_id": "receipt-1", "statement_id": "premise-id"}


# am[verifies a-v2-receipt-conflict-refusal-1020@051877]
def test_receipt_trust_can_change_between_separate_belief_responses(codec):
    for trust in (0.25, 0.75):
        belief = _receipt_belief(codec, [f'(receipt receipt-1 "request" premise-id {trust})'])
        assert belief.receipts[0].trust == trust


# Time: linear in the generated receipt occurrences for each order and duplicate variant.
# am[verifies a-v2-receipt-conflict-refusal-1020@051877]
@settings(max_examples=60, deadline=None)
@given(st.lists(st.tuples(*(st.integers(0, 3) for _ in range(4))), max_size=20))
def test_receipt_acceptance_depends_on_identity_consistency_not_order_or_multiplicity(rows):
    codec = SexprCodec()
    payloads = {}
    for receipt_id, statement_id, source, trust in rows:
        payloads.setdefault((receipt_id, statement_id), set()).add((source, trust))
    conflicts = any(len(values) != 1 for values in payloads.values())
    for ordered in (rows, list(reversed(rows)), rows + rows):
        terms = [f'(receipt r{rid} "s{source}" p{sid} {trust / 4})'
                 for rid, sid, source, trust in ordered]
        if conflicts:
            with pytest.raises(ProtocolError, match="conflicting payloads"):
                _receipt_belief(codec, terms)
        else:
            belief = _receipt_belief(codec, terms)
            observed = {(item.receipt_id, item.statement_id): (item.source, item.trust)
                        for item in belief.receipts}
            expected = {(f"r{rid}", f"p{sid}"): (f"s{source}", trust / 4)
                        for (rid, sid), values in payloads.items() for source, trust in values}
            assert observed == expected
            assert len(belief.receipts) == len(payloads)


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

    with pytest.raises(ProtocolError, match="roll back"):
        parse_counterfactual(payload, codec)

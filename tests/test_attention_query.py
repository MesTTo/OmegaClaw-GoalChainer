"""Purpose: verify forward query witnesses, incompleteness and preservation of evidence support."""

import pytest

from test_attention_control import POLICY, _run
from test_attention_graph import _atom, _statement


# A bare reference is not an observation; negative and vacuous observations still are support.
# am[verifies a-integrate-ecan-packaged-query-1017]
def _existing_program(kind):
    query = _statement("is", [("s", _atom("left")), ("o", _atom("right"))])
    if kind == "bare":
        effect = f"(sn intern! (sn sid (sn canon {query})) (sn canon {query}) instance aleatory)"
    else:
        positive, negative = {"positive": (8, 0), "negative": (0, 8), "vacuous": (0, 0)}[kind]
        effect = f'(believe! {query} ((evidence {positive} {negative}) (source "observation") (trust 1.0)))'
    return (f"(let* (($given {effect}) ($answer (gc forward-query-record {query}))) "
            "(Existing $answer (gc-attention-rows)))")


# Neither evidence sign nor weight licenses an unsupported node. Existing support needs no graph
# construction or frontier work.
# am[verifies a-integrate-ecan-packaged-query-1017] am[verifies a-rt-attention-query-oracle-1018@5b0697]
@pytest.mark.parametrize("kind", ["bare", "positive", "negative", "vacuous"])
def test_existing_support_returns_a_witness_but_a_bare_node_is_incomplete(kind):
    assert (POLICY / "goalchainer_attention_query.metta").is_file()
    tag, record, rows = _run(_existing_program(kind), query=True)
    assert tag == "Existing"
    assert record[:3] == ["goalchainer-snars-v1", "forward-query", "ok"]
    fields = dict((item[0], item[1:]) for item in record[3][1:])
    assert fields["status"] == ["Incomplete" if kind == "bare" else "Witness"]
    assert fields["steps"] == ["0"]
    answers = fields["answers"][0]
    if kind == "bare":
        assert answers == []
    else:
        assert len(answers) == 1
        assert rows == []
        opinion = answers[0][1]
        assert opinion[0] == "Opinion"
        if kind == "positive":
            assert float(opinion[1]) > 0 and float(opinion[2]) == 0
        elif kind == "negative":
            assert float(opinion[1]) == 0 and float(opinion[2]) > 0
        else:
            assert list(map(float, opinion[1:4])) == [0.0, 0.0, 1.0]


# The query consumes newly derived support in the same batch. Receipts and source trust do not
# change merely because scheduling changes.
# am[verifies a-integrate-ecan-packaged-query-1017] am[verifies a-rt-attention-query-oracle-1018@5b0697]
def test_forward_query_finds_a_new_two_edge_witness():
    assert (POLICY / "goalchainer_attention_query.metta").is_file()
    statements = [_statement("is", [("s", _atom(left)), ("o", _atom(right))])
                  for left, right in (("a", "b"), ("b", "c"), ("a", "c"))]
    body = (f'(let* (($a (believe! {statements[0]} ((evidence 8 0) (source "a") (trust 1.0)))) '
            f'($b (believe! {statements[1]} ((evidence 8 0) (source "b") (trust 1.0)))) '
            '($before (msort (collapse (match &self (sn receipt $sid $src $hash) (Receipt $sid $src $hash))))) '
            '($trust-before (Trust (sn_tr_rs src "a") (sn_tr_rs src "b"))) '
            f'($answer (gc forward-query-record {statements[2]})) '
            '($after (msort (collapse (match &self (sn receipt $sid $src $hash) (Receipt $sid $src $hash))))) '
            '($trust-after (Trust (sn_tr_rs src "a") (sn_tr_rs src "b")))) '
            '(Derived $answer $before $after $trust-before $trust-after (gc-attention-rows)))')
    tag, record, before, after, trust_before, trust_after, rows = _run(body, query=True)
    assert tag == "Derived" and before == after
    assert trust_before == trust_after
    fields = dict((item[0], item[1:]) for item in record[3][1:])
    assert fields["status"] == ["Witness"]
    assert int(fields["steps"][0]) > 0
    assert len(fields["answers"][0]) == 1
    assert float(fields["answers"][0][0][1][1]) > 0
    assert sum(float(row[2]) for row in rows) == pytest.approx(1.0)

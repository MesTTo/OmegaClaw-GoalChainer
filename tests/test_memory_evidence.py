"""Purpose: test the memory-evidence boundary every native and offline decision admits items through."""

from __future__ import annotations


import pytest
from hypothesis import given, settings, strategies as st

from goal_chainer import memory_evidence
from goal_chainer.memory_evidence import (
    NO_MEMORY,
    MemoryEvidenceError,
    admit_memory_evidence,
    consumed_slots,
    memory_text_omissions,
)
from goal_chainer.sexpr.codec import SexprCodec
from request_support import budget

ACTIONS = ("publish_raw_log", "publish_redacted_summary", "hold_external_update")
STV_SLOT = "acceptability-belief-evidence"
EC_SLOT = "contextual-appraisal-evidence"
# A 401-digit integer, which the codec reads as a Python int beyond the float range.
BEYOND_FLOAT = "1" + "0" * 400


# am[verifies a-ev-memory-admission@56c9f7]
def _codec() -> SexprCodec:
    return SexprCodec()


CODEC = _codec()
REQUEST = "Checkout is down. Raw logs include customer emails."


# am[verifies a-ev-memory-admission@56c9f7]
def _admit(items):
    return admit_memory_evidence(items, ACTIONS, codec=lambda: CODEC, request=REQUEST, budget=budget())


# am[verifies a-ev-memory-admission@56c9f7]
def _stv(action: str, strength: float, confidence: float, **provenance) -> dict:
    return {
        "goalchainer_slot": STV_SLOT,
        "atom": f"(: b-{action} (Acceptable {action}) (STV {strength} {confidence}))",
        **provenance,
    }


# am[verifies a-ev-memory-admission@56c9f7]
def _ec(action: str, support: float, opposition: float, **provenance) -> dict:
    return {
        "goalchainer_slot": EC_SLOT,
        "atom": (
            f"(EvidencePacket (Acceptable {action}) (EC {support} {opposition}) "
            "((domain incident-response)) pe-x)"
        ),
        **provenance,
    }


# am[verifies a-ev-memory-admission@56c9f7]
def _refuse_codec():
    raise AssertionError("items GoalChainer ignores must not need a MeTTa runtime")


# WMTM's {id, content, sti} items are memory texts the native appraisal reads, and admitting them
# needs no MeTTa codec.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ev-wt-host-1017@2731e9]
def test_wmtm_items_are_memory_texts_and_need_no_runtime() -> None:
    items = [
        {"id": "w1", "content": "CPU usage on server-1 is 95%.", "sti": 10.0},
        {"id": "w2", "content": "Support says logs include emails.", "sti": 4.5},
    ]

    admission = admit_memory_evidence(items, ACTIONS, codec=_refuse_codec, request=REQUEST, budget=budget())

    assert admission.admitted == ()
    assert [(d.index, d.status, d.reason) for d in admission.dispositions] == [
        (0, "text", "ContextText"),
        (1, "text", "ContextText"),
    ]
    assert [(text.index, text.text) for text in admission.texts] == [
        (0, items[0]["content"]),
        (1, items[1]["content"]),
    ]
    assert admission.to_dict()["counts"] == {
        "admitted": 0,
        "text": 2,
        "duplicate": 0,
        "ignored": 0,
        "empty": 0,
    }


# A text's identity is its content, which only removes copies: a later copy is a duplicate of the
# first, a copy of the request is a duplicate of the request, a blank text says nothing, and an
# item with neither a slot nor text is no evidence.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ev-wt-policy-1017@3df281]
def test_copies_of_a_text_or_of_the_request_are_duplicates_and_blank_text_is_empty() -> None:
    items = [
        {"id": "w1", "content": "Support says logs include emails.", "sti": 1.0},
        {"id": "w2", "content": "Support says logs include emails.", "sti": 9.0},
        {"id": "w3", "content": REQUEST, "sti": 5.0},
        {"id": "w4", "content": "  \n", "sti": 2.0},
        {"id": "w5", "sti": 2.0},
    ]

    admission = _admit(items)

    assert [(d.status, d.reason, d.representative) for d in admission.dispositions] == [
        ("text", "ContextText", None),
        ("duplicate", "SameIdentity", 0),
        ("duplicate", "SameAsRequest", None),
        ("empty", "BlankText", None),
        ("ignored", "NoGoalChainerSlot", None),
    ]
    assert [text.index for text in admission.texts] == [0]
    assert admission.dispositions[1].identity == admission.dispositions[0].identity
    assert admission.digest != _admit([]).digest


# Content that is not text is malformed, like any other item part of the wrong type.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ev-wt-host-1017@2731e9]
def test_content_that_is_not_text_is_refused() -> None:
    with pytest.raises(MemoryEvidenceError, match="content") as refused:
        _admit([{"id": "w1", "content": ["not", "text"], "sti": 1.0}])

    assert refused.value.details == {"index": 0, "type": "list"}


# am[verifies a-ev-ma-ignored@596975]
def test_unconsumed_slots_and_other_actions_are_ignored() -> None:
    admission = _admit(
        [
            {"goalchainer_slot": "other", "atom": "(Acceptable publish_raw_log) (STV 1.0 1.0)"},
            _ec("restart_service", 2, 1),
        ]
    )

    assert admission.admitted == ()
    assert [d.reason for d in admission.dispositions] == [
        "SlotNotConsumed",
        "NotACandidateAction",
    ]


# am[verifies a-ev-ma-malformed@7a443b]
@pytest.mark.parametrize(
    ("items", "message"),
    [
        ("not a list", "list of mappings"),
        ({"goalchainer_slot": STV_SLOT}, "list of mappings"),
        (["not a mapping"], "must be a mapping"),
        ([{"goalchainer_slot": 7, "atom": "(x)"}], "goalchainer_slot must be text"),
        ([{"goalchainer_slot": STV_SLOT}], "atom must be nonempty text"),
        ([{"goalchainer_slot": STV_SLOT, "atom": "not-an-atom"}], "does not encode"),
        ([{"goalchainer_slot": STV_SLOT, "atom": "(Acceptable a"}], "not a MeTTa expression"),
        ([{"goalchainer_slot": STV_SLOT, "atom": "(Rejected publish_raw_log) (STV 0.5 0.5)"}], "does not encode"),
        ([{"goalchainer_slot": EC_SLOT, "atom": "(Acceptable publish_raw_log) (STV 0.5 0.5)"}], "does not encode"),
        ([_stv("publish_raw_log", 1.5, 0.2)], "strength must lie in"),
        ([_stv("publish_raw_log", -0.1, 0.2)], "strength must lie in"),
        ([_stv("publish_raw_log", 0.5, 1.0)], "confidence must lie in"),
        ([_stv("publish_raw_log", "nan", 0.5)], "finite number"),
        ([_stv("publish_raw_log", BEYOND_FLOAT, 0.5)], "STV strength must be a finite number"),
        ([_stv("publish_raw_log", 0.5, "-" + BEYOND_FLOAT)], "STV confidence must be a finite number"),
        ([_ec("publish_raw_log", BEYOND_FLOAT, 1)], "EC support must be a finite number"),
        ([_ec("publish_raw_log", -1, 2)], "nonnegative"),
        ([_stv("publish_raw_log", 0.5, 0.5, belief_id="")], "belief_id must be nonempty"),
        ([_stv("publish_raw_log", 0.5, 0.5, belief_id=" b-1")], "surrounding whitespace"),
        ([_stv("publish_raw_log", 0.5, 0.5, cluster_id=3)], "cluster_id must be nonempty"),
    ],
)
def test_malformed_consumed_items_raise_before_reasoning(items, message) -> None:
    with pytest.raises(MemoryEvidenceError, match=message) as raised:
        _admit(items)

    assert raised.value.code == "invalid_input"


# am[verifies a-ev-ma-malformed@7a443b]
def test_the_error_names_the_offending_index() -> None:
    items = [_stv("publish_raw_log", 0.5, 0.5), {"goalchainer_slot": STV_SLOT, "atom": "junk"}]

    with pytest.raises(MemoryEvidenceError) as raised:
        _admit(items)

    assert raised.value.details["index"] == 1


# am[verifies a-ev-ma-identity@0acd7f]
def test_identity_is_belief_then_promotion_then_content() -> None:
    admission = _admit(
        [
            _stv("publish_raw_log", 0.2, 0.5, belief_id="b-1", cluster_id="c", promotion_event="p"),
            _stv("publish_redacted_summary", 0.9, 0.5, cluster_id="c-2", promotion_event="p-2"),
            _ec("hold_external_update", 3, 1),
        ]
    )

    kinds = [item.identity.kind for item in admission.admitted]
    assert kinds == ["belief", "promotion", "content"]
    assert admission.admitted[0].identity.source == 'memory:["belief","b-1"]'
    assert admission.admitted[1].identity.source == 'memory:["promotion","c-2","p-2"]'


# am[verifies a-ev-ma-identity@0acd7f]
def test_identical_anonymous_items_are_one_piece_of_evidence() -> None:
    admission = _admit([_ec("hold_external_update", 3, 1), _ec("hold_external_update", 3, 1)])

    assert len(admission.admitted) == 1
    assert [(d.status, d.representative) for d in admission.dispositions] == [
        ("admitted", None),
        ("duplicate", 0),
    ]


# am[verifies a-ev-ma-identity@0acd7f]
def test_one_identity_cannot_name_two_actions() -> None:
    items = [
        _stv("publish_raw_log", 0.2, 0.5, belief_id="b-1"),
        _ec("hold_external_update", 3, 1, belief_id="b-1"),
    ]

    with pytest.raises(MemoryEvidenceError, match="different actions") as raised:
        _admit(items)

    assert raised.value.details["actions"] == ["hold_external_update", "publish_raw_log"]


# am[verifies a-ev-ma-identity@0acd7f]
def test_representative_is_the_stv_value_then_the_lowest_confidence() -> None:
    admission = _admit(
        [
            _ec("publish_redacted_summary", 9, 1, belief_id="b-shared"),
            _stv("publish_redacted_summary", 0.91, 0.74, belief_id="b-shared"),
            _stv("publish_redacted_summary", 0.6, 0.5, belief_id="b-shared"),
        ]
    )

    (kept,) = admission.admitted
    assert kept.index == 2
    assert kept.encoding == "stv"
    assert kept.strength == pytest.approx(0.6)
    assert [d.status for d in admission.dispositions] == ["duplicate", "duplicate", "admitted"]


# am[verifies a-ev-ma-weights@67499b]
def test_stv_maps_to_evidence_units_and_back() -> None:
    (item,) = _admit([_stv("publish_redacted_summary", 0.91, 0.74)]).admitted

    # The convention under test: confidence c reads as w / (w + 2) evidence units.
    weight = 2.0 * 0.74 / (1.0 - 0.74)
    assert item.counts.positive == pytest.approx(0.91 * weight)
    assert item.counts.negative == pytest.approx(0.09 * weight)
    assert item.strength == pytest.approx(0.91)
    assert item.confidence == pytest.approx(0.74)


# am[verifies a-ev-ma-weights@67499b]
def test_ec_counts_pass_through() -> None:
    (item,) = _admit([_ec("publish_raw_log", 9, 1)]).admitted

    assert (item.counts.positive, item.counts.negative) == (9.0, 1.0)
    assert item.strength == pytest.approx(0.9)
    assert item.confidence == pytest.approx(10 / 12)


# am[verifies a-ev-ma-weights@67499b]
def test_zero_weight_items_are_reported_empty() -> None:
    admission = _admit([_stv("publish_raw_log", 0.5, 0.0), _ec("hold_external_update", 0, 0)])

    assert admission.admitted == ()
    assert [d.reason for d in admission.dispositions] == ["ZeroEvidence", "ZeroEvidence"]


# am[verifies a-ev-ma-malformed@7a443b]
def test_ec_counts_whose_sum_overflows_are_refused() -> None:
    with pytest.raises(MemoryEvidenceError, match="weight must be finite"):
        _admit([_ec("publish_raw_log", "1e308", "1e308")])


# An integer count is read as its float wherever a float holds it, however many digits it has: only one
# beyond the float range is refused (a-integrate-evidence-number-refusal-1018).
# am[verifies a-ev-nr-finite-float-1018@6fcba4] am[verifies a-integrate-evidence-number-refusal-1018@63a51f]
def test_an_integer_count_within_the_float_range_is_read_as_its_float() -> None:
    (item,) = _admit([_ec("publish_raw_log", "1" + "0" * 300, 1)]).admitted

    assert (item.counts.positive, item.counts.negative) == (1e300, 1.0)


# am[verifies a-ev-memory-admission@56c9f7]
def test_no_memory_is_the_empty_admission() -> None:
    assert _admit(None) is NO_MEMORY
    assert NO_MEMORY.to_dict()["received"] == 0


item_strategy = st.one_of(
    st.builds(
        _stv,
        st.sampled_from(ACTIONS),
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        st.floats(min_value=0.01, max_value=0.99, allow_nan=False),
        belief_id=st.one_of(st.none(), st.sampled_from(["b-1", "b-2", "b-3"])),
    ),
    st.builds(
        _ec,
        st.sampled_from(ACTIONS),
        st.integers(min_value=1, max_value=50),
        st.integers(min_value=0, max_value=50),
    ),
    st.builds(
        lambda note: {"id": "w", "content": note, "sti": 1.0},
        st.text(max_size=20),
    ),
)


# am[verifies a-ev-memory-admission@56c9f7]
def _consistent(items: list[dict]) -> list[dict]:
    """Drop items whose belief_id already names another action, as a producer must."""

    actions: dict[str, str] = {}
    kept = []
    for item in items:
        belief = item.get("belief_id")
        action = item.get("atom", "").split("(Acceptable ")[-1].split(")")[0]
        if belief is not None and actions.setdefault(belief, action) != action:
            continue
        kept.append(item)
    return kept


# am[verifies a-ev-ma-dedup-property@e71cb7]
@settings(max_examples=200, deadline=None)
@given(st.lists(item_strategy, max_size=8), st.data())
def test_a_resupplied_item_never_changes_the_admitted_evidence(items, data) -> None:
    items = _consistent(items)
    baseline = _admit(items)
    if not items:
        return
    copy = data.draw(st.sampled_from(items))

    resupplied = _admit(items + [dict(copy)])

    assert resupplied.digest == baseline.digest
    assert resupplied.admitted == tuple(
        item for item in baseline.admitted
    )


# am[verifies a-ev-ma-dedup-property@e71cb7]
@settings(max_examples=200, deadline=None)
@given(st.lists(item_strategy, max_size=8))
def test_every_received_item_gets_exactly_one_disposition(items) -> None:
    items = _consistent(items)
    admission = _admit(items)

    assert [d.index for d in admission.dispositions] == list(range(len(items)))
    admitted = {item.index for item in admission.admitted}
    assert admitted == {d.index for d in admission.dispositions if d.status == "admitted"}
    assert len({item.identity for item in admission.admitted}) == len(admission.admitted)
    texts = {text.index for text in admission.texts}
    assert texts == {d.index for d in admission.dispositions if d.status == "text"}
    assert len({text.text for text in admission.texts}) == len(admission.texts)
    assert REQUEST not in {text.text for text in admission.texts}


# The memory policy's input-independent tables are read once per process, charged to the request
# that first needs them, and every later request reads them for nothing.
# am[verifies a-ev-rb-pipeline-budget-1018@988a39]
def test_the_policy_tables_are_charged_once_to_the_first_request(monkeypatch) -> None:
    monkeypatch.setattr(memory_evidence, "_TABLES", {})
    first, second = budget(), budget()

    slots = consumed_slots(budget=first)
    omissions = memory_text_omissions(budget=first)

    assert first.spent > 0
    assert consumed_slots(budget=second) is slots
    assert memory_text_omissions(budget=second) is omissions
    assert second.spent == 0
    assert dict(slots) == {"acceptability-belief-evidence": "stv", "contextual-appraisal-evidence": "ec"}
    assert omissions == frozenset({"not_cached", "refused"})

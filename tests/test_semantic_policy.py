"""Purpose: test goalchainer_policy.metta's reading rule in a real SNARS session, reading what the
session believes of each declared proposition as SnarsSession.belief of its statement: a decided
supported reading is evidence for the proposition, contradicted is evidence against, unknown believes
nothing, and each source keeps its own receipt discounted by its trust; and test that the policy
holds no domain's knowledge, so a world believes only what readings and callers give it.

The readings are hand-written gc-reading facts that the session ingests through its own
ingest_text, so these tests hold the policy to exact inputs; what Jev answers for real texts is
tested on captured replays."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from request_support import budget as request_budget
from goal_chainer.snars_models import SnarsBelief
from goal_chainer.snars_program import ProgramFragments, SnarsProgramBuilder, TextIngestion
from goal_chainer.snars_reasoner import SnarsSession
from reading_support import INCIDENT, incident_reader, reading_statement

REQUEST = "goalchainer:request"
MEMORY = 'memory:["text","0123456789abcdef"]'


# am[verifies a-jev-reading-belief-1016]
def _reading(source: str, trust: float, reading_id: str, answer: str, p: float) -> str:
    source_text = source.replace("\\", "\\\\").replace('"', '\\"')
    return (
        f'(gc-reading "{source_text}" {trust} {reading_id} {answer} {p} '
        f'(provenance "jev-1.13.0" "synthetic-{reading_id}" "a passage"))'
    )


# Reading a text hands back the next scripted reading of it instead of asking a reader, so a
# session ingests exact facts through its own ingest_text and reads them as it reads any text; its
# batches carry the incident reader's declaration, which admits those facts.
# am[verifies a-jev-reading-belief-1016] am[related a-rt-snars-batch-speculative-1017@451056]
# am[verifies a-dr-sr-snars-batch-declaration-1018@5c965d]
class _Builder(SnarsProgramBuilder):
    def __init__(self, script: dict[str, list[tuple[str, list[str]]]]) -> None:
        super().__init__(incident_reader())
        self.script = {text: list(readings) for text, readings in script.items()}

    def text_ingestion(self, text: str, *, source: str, trust: float, budget: object) -> TextIngestion:
        revision, facts = self.script[text].pop(0) if len(self.script[text]) > 1 else self.script[text][0]
        return TextIngestion(revision=revision, fragments=ProgramFragments(facts=tuple(facts)))


# Each (source, trust) is one synthetic text read under that source, read as often as `times` says.
# am[verifies a-jev-reading-belief-1016] am[related a-rt-snars-batch-speculative-1017@451056]
@contextmanager
def _session(*readings: tuple[str, float, str, str, float], times: int = 1) -> Iterator[SnarsSession]:
    by_source: dict[tuple[str, float], list[str]] = {}
    for source, trust, reading_id, answer, p in readings:
        by_source.setdefault((source, trust), []).append(_reading(source, trust, reading_id, answer, p))
    texts = {key: f"synthetic text from {key[0]}" for key in by_source}
    session = SnarsSession.ephemeral(budget=request_budget(), reader=incident_reader())
    session.builder = _Builder({texts[key]: [("synthetic", facts)] for key, facts in by_source.items()})
    with session:
        for _ in range(times):
            for (source, trust), text in texts.items():
                session.ingest_text(text, source=source, trust=trust)
        yield session


# What the session believes of each declared proposition named, by its id.
# am[verifies a-ie-s7-tests-1018@5c72ce]
def _beliefs(session: SnarsSession, *ids: str) -> dict[str, SnarsBelief]:
    return {proposition_id: session.belief(reading_statement(proposition_id)) for proposition_id in ids}


# am[verifies a-jev-reading-belief-1016]
# am[verifies a-jev-decided-nli-1016] am[verifies a-ie-s7-tests-1018@5c72ce]
def test_supported_contradicted_and_unknown_readings_become_for_against_and_nothing() -> None:
    with _session(
        (REQUEST, 1.0, "sensitive-data", "supported", 0.9),
        (REQUEST, 1.0, "public-data", "contradicted", 0.8),
        (REQUEST, 1.0, "unverified", "unknown", 0.95),
        (REQUEST, 1.0, "customer-emails", "supported", 0.97),
    ) as session:
        belief = _beliefs(session, "sensitive-data", "public-data", "unverified", "coordination-needed")

    sensitive, public, unverified = belief["sensitive-data"], belief["public-data"], belief["unverified"]
    assert (sensitive.evidence.positive, sensitive.evidence.negative) == (pytest.approx(7.2), 0.0)
    assert (public.evidence.positive, public.evidence.negative) == (0.0, pytest.approx(6.4))
    assert (unverified.evidence.positive, unverified.evidence.negative) == (0.0, 0.0)
    assert unverified.opinion.uncertainty == pytest.approx(1.0)
    assert unverified.receipts == ()
    assert [r.source for r in sensitive.receipts] == [REQUEST]
    assert belief["coordination-needed"].receipts == ()


# am[verifies a-jev-reading-belief-1016] am[verifies a-ie-s7-tests-1018@5c72ce]
def test_each_source_keeps_its_own_receipt_discounted_by_its_trust() -> None:
    with _session(
        (REQUEST, 1.0, "sensitive-data", "supported", 0.9),
        (MEMORY, 0.5, "sensitive-data", "supported", 0.7),
        (MEMORY, 0.5, "coordination-needed", "supported", 0.7),
    ) as session:
        belief = _beliefs(session, "sensitive-data", "coordination-needed")

    sensitive, coordination = belief["sensitive-data"], belief["coordination-needed"]
    assert sorted(r.source for r in sensitive.receipts) == sorted([REQUEST, MEMORY])
    assert sensitive.evidence.positive == pytest.approx(7.2 + 8 * 0.7 * 0.5)
    assert coordination.evidence.positive == pytest.approx(2.8)
    assert [r.source for r in coordination.receipts] == [MEMORY]


# Every evidence direction a reading declaration can give an answer is one the policy decides, both
# read from the MeTTa and the declaration grammar themselves, so an answer with a new direction
# cannot reach SNARS undecided: each direction has a gc direction-unit rule, the unit of evidence it
# asserts or none.
# am[verifies a-jev-derive-answers-1016@4b73ac] am[verifies a-ev-wt-context-mean-1017@46162f]
def test_the_policy_decides_every_direction_the_reading_table_names() -> None:
    import metta

    from goal_chainer.runtime.engine import metta_engine
    from goal_chainer.domains.readings import DIRECTIONS
    from goal_chainer.snars_program import POLICY_PATH

    v = metta.V
    rule = metta.Symbol("=")(
        metta.Symbol("gc")(metta.Symbol("direction-unit"), v.direction, v.s, v.t, v.i, v.w, v.p),
        v.body,
    )
    with metta_engine(None) as engine:
        space = engine.space()
        space.load(POLICY_PATH)
        decided = {str(row.direction) for row in space.match(rule)}

    assert decided == {"for", "against", "none"}
    assert set(DIRECTIONS) == decided
    assert {option.direction for option in INCIDENT.options} <= decided


# The policy holds no domain's knowledge: loaded alone it registers no rewrite row, and a policy
# batch of a session that read nothing believes no statement at all, so everything a world believes
# comes from a reading or a caller. The inspection's cells field is SNARS's count of the cells it
# holds evidence for, (sn cells), so an empty world reads (cells 0).
# am[verifies a-ie-s7-metta-1018@0ca8fe]
def test_the_policy_holds_no_domain_rules_or_facts() -> None:
    import metta

    from goal_chainer.runtime.engine import metta_engine
    from goal_chainer.snars_program import POLICY_PATH

    v = metta.V
    row = metta.Symbol("sn")(metta.Symbol("rw"), v.name, v.kind, v.first, v.second, v.conclusion)
    with metta_engine(None) as engine:
        space = engine.space()
        space.load(POLICY_PATH)
        rows = list(space.match(row))
    with SnarsSession.ephemeral(budget=request_budget(), reader=incident_reader()) as session:
        inspection = session.inspect().payload

    assert rows == []
    assert {field[0]: field[1] for field in inspection[1:]}["cells"] == [0]


# The next three cases are adopted from Roman Treutlein's original PeTTaChainer at b0e24f9
# (public copy https://github.com/BekLG/PeTTaChainer), whose tests pin the same evidence semantics
# for its STV proof store.

# test_negated_evidence_merge.metta: evidence for and evidence against one proposition from
# different sources do not overlap, so both stand and neither erases the other.
# am[verifies a-chainer-prior-art-tests-1016] am[verifies a-ie-s7-tests-1018@5c72ce]
def test_evidence_for_and_against_from_different_sources_both_stand() -> None:
    with _session(
        (REQUEST, 1.0, "sensitive-data", "supported", 0.9),
        (MEMORY, 0.5, "sensitive-data", "contradicted", 0.8),
    ) as session:
        sensitive = session.belief(reading_statement("sensitive-data"))

    # SNARS also learns a lower trust ratio for a source that disagrees with the others, so the
    # memory's evidence against is at most its trust-discounted 8 * 0.8 * 0.5, not exactly that.
    assert sensitive.evidence.positive == pytest.approx(7.2)
    assert 0.0 < sensitive.evidence.negative <= 8 * 0.8 * 0.5
    assert sorted(r.source for r in sensitive.receipts) == sorted([REQUEST, MEMORY])


# test_evidence_semantics.metta: evidence shared by two derivations is counted once. Here the same
# text read twice under one source is one testimony, not two.
# am[verifies a-chainer-prior-art-tests-1016] am[verifies a-ie-s7-tests-1018@5c72ce]
def test_one_text_read_twice_counts_once() -> None:
    with _session((REQUEST, 1.0, "sensitive-data", "supported", 0.9), times=2) as session:
        sensitive = session.belief(reading_statement("sensitive-data"))

    assert sensitive.evidence.positive == pytest.approx(7.2)
    assert [r.source for r in sensitive.receipts] == [REQUEST]


# test_negated_facts.metta: a negated fact keeps its source proof name. Here a contradicted
# reading's belief keeps the reading's provenance and estimator class in its meta channel.
# am[verifies a-chainer-prior-art-tests-1016]
def test_a_contradicted_reading_keeps_its_provenance() -> None:
    with _session((REQUEST, 1.0, "public-data", "contradicted", 0.8)) as session:
        inspection = session.inspect().raw

    assert '"synthetic-public-data"' in inspection
    assert "model-proposed" in inspection


# A promoted reranker changes the reader revision and may ground the same cached Jev answer in
# another passage, but it is the same testimony: SNARS keys a receipt by statement and source
# alone (mettabase c079c89: believe! hashes (sn rh $cell $sigma), snars_receipt_hash(sid, sigma)),
# and fuses evidence only for a new receipt. So the second reading adds no evidence, while its
# grounding still lands in the statement's meta channel beside the first.
# am[verifies a-jev-snars-ingest-1016] am[verifies a-ie-s7-tests-1018@5c72ce]
def test_a_new_ranker_grounding_the_same_answer_adds_no_evidence() -> None:
    text = "Checkout is down. Raw logs include customer emails."
    readings = [
        (revision, [f'(gc-reading "{REQUEST}" 1.0 sensitive-data supported 0.9 '
                    f'(provenance "jev-1.13.0" "same-answer-key" "{passage}"))'])
        for revision, passage in (("ranker-base", "Raw logs include customer emails."),
                                  ("ranker-promoted", "Checkout is down."))
    ]
    session = SnarsSession.ephemeral(budget=request_budget(), reader=incident_reader())
    session.builder = _Builder({text: readings})
    with session:
        session.ingest_text(text, source=REQUEST)
        session.ingest_text(text, source=REQUEST)
        sensitive = session.belief(reading_statement("sensitive-data"))
        inspection = session.inspect().raw
        events = session.store.events()

    assert [event.payload["reader_revision"] for event in events] == ["ranker-base", "ranker-promoted"]
    assert sensitive.evidence.positive == pytest.approx(7.2)
    assert [r.source for r in sensitive.receipts] == [REQUEST]
    assert "Raw logs include customer emails." in inspection and "Checkout is down." in inspection


# A reading whose text this session did not read is not believed, though the store holds it, so
# a decision believes nothing an earlier request said (c-batch-replays-every-ingestion-1017).
# am[verifies a-jev-session-reads-1017@3d73d9] am[verifies a-ie-s7-tests-1018@5c72ce]
def test_a_stored_reading_outside_the_session_is_not_believed() -> None:
    with _session((MEMORY, 0.5, "coordination-needed", "supported", 0.7)) as session:
        session.store.append(
            "ingest_text",
            {"text": "an earlier request", "source": REQUEST, "trust": 1.0, "reader_revision": "synthetic",
             "facts": [_reading(REQUEST, 1.0, "sensitive-data", "supported", 0.9)], "effects": []},
        )
        belief = _beliefs(session, "sensitive-data", "coordination-needed")

    assert belief["sensitive-data"].receipts == () and belief["sensitive-data"].evidence.positive == 0.0
    assert [r.source for r in belief["coordination-needed"].receipts] == [MEMORY]

"""Purpose: test SNARS text ingestion through the semantic reader: text_ingestion turns one reading
into gc-reading facts with its revision, every batch accepts exactly well-formed readings, a
policy batch carries the reading declaration, a promoted reranker re-reading a text adds no
evidence, and a session believes only the texts it read itself, whatever its store holds."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from jev_support import answering, client, sure

from request_support import budget as request_budget
from goal_chainer import semantic_reader as sr
from goal_chainer.errors import InvalidInputError
from goal_chainer.sexpr.codec import SexprCodec
from goal_chainer.snars_ingestion import ReadingFact
from goal_chainer.snars_program import SnarsProgramBuilder, TextIngestion
from goal_chainer.snars_reasoner import SnarsSession
from reading_support import INCIDENT as TABLE, incident_reader, reading_statement



# A reader whose one reading is built by hand: ingestion is held to exact readings here, and
# captured Jev answers are replayed by the native tests. The incident declaration declares no
# binding, so the reading binds nothing.
# am[verifies a-jev-snars-ingest-1016] am[related a-bnd-reading-1019@105c81]
class _Reader:
    declaration = TABLE

    def __init__(self) -> None:
        self.read_texts: list[str] = []
        self.budgets: list[object] = []

    def read(self, text: str, *, budget: object) -> sr.Reading:
        self.read_texts.append(text)
        self.budgets.append(budget)
        return sr.Reading(
            text=text, model=TABLE.model, revision="0123456789abcdef", declaration=TABLE, passages=(text,),
            propositions=tuple(
                sr.PropositionReading(
                    proposition=p, answer="supported" if p.id == "sensitive-data" else "unknown",
                    direction="for" if p.id == "sensitive-data" else "none",
                    probability=0.9, probabilities={"supported": 0.9, "contradicted": 0.05, "unknown": 0.05},
                    draws=1, key=f"k-{p.id}",
                    grounding=sr.Grounding(text, 0.9) if p.id == "sensitive-data" else None,
                )
                for p in TABLE.propositions
            ),
            choices=(),
            bindings=(),
        )


# am[verifies a-jev-snars-ingest-1016@2517b8]
def test_text_ingestion_turns_one_reading_into_facts_with_its_revision() -> None:
    reader = _Reader()
    text = '") !(import! &self attack)'
    budget = request_budget()
    ingested = SnarsProgramBuilder(reader=reader).text_ingestion(
        text, source="goalchainer:request", trust=0.75, budget=budget
    )

    assert isinstance(ingested, TextIngestion)
    assert ingested.revision == "0123456789abcdef"
    assert reader.read_texts == [text]
    assert reader.budgets == [budget] and reader.budgets[0] is budget
    assert ingested.fragments.effects == ()
    assert len(ingested.fragments.facts) == len(TABLE.propositions)
    codec = SexprCodec()
    for fact in ingested.fragments.facts:
        ReadingFact.parse(fact, codec)
    sensitive = next(f for f in ingested.fragments.facts if " sensitive-data " in f)
    assert sensitive.startswith('(gc-reading "goalchainer:request" 0.75 sensitive-data supported 0.9')
    assert codec.parse(sensitive)[6][3].value == text


# am[verifies a-jev-snars-ingest-1016]
def test_empty_text_is_refused_before_any_reading() -> None:
    reader = _Reader()
    with pytest.raises(InvalidInputError, match="nonempty"):
        SnarsProgramBuilder(reader=reader).text_ingestion("  ", source="s", trust=1.0, budget=request_budget())
    assert reader.read_texts == []


# A session reads the text it ingests under its own budget, the one its request opened it with.
# am[verifies a-dr-reader-budget-required-1018@0b0cce] am[verifies a-rt-rbs-session-budget-1018@8c3da2]
def test_a_session_reads_its_text_under_the_budget_it_was_opened_with() -> None:
    class Stop(Exception):
        pass

    received = []

    class Recording(SnarsProgramBuilder):
        def text_ingestion(self, text, *, source, trust, budget):
            received.append(budget)
            raise Stop

    budget = request_budget()
    with SnarsSession.ephemeral(budget=budget, reader=incident_reader()) as session:
        session.builder = Recording()
        with pytest.raises(Stop):
            session.ingest_text("Checkout is down.", source="goalchainer:request")
    assert len(received) == 1 and received[0] is budget


# am[verifies a-jev-snars-ingest-1016]
@pytest.mark.parametrize(
    "fact",
    [
        '(hb tree hb1 (sh-atom (tag C c NoRoles ()) "safe"))',
        '(attack now)',
        '(gc-reading "s" 1.0 sensitive-data maybe 0.9 (provenance "m" "k" "p"))',
        '(gc-reading "s" 1.5 sensitive-data supported 0.9 (provenance "m" "k" "p"))',
        '(gc-reading "s" 1.0 sensitive-data supported -0.1 (provenance "m" "k" "p"))',
        '(gc-reading s 1.0 sensitive-data supported 0.9 (provenance "m" "k" "p"))',
        '(gc-reading "s" 1.0 sensitive-data supported 0.9 (provenance "m" "k"))',
        '(gc-reading "s" 1.0 sensitive-data supported 0.9 (import! &self attack))',
        '(gc-reading "s" 1.0 "sensitive-data" supported 0.9 (provenance "m" "k" "p"))',
    ],
)
def test_batches_refuse_any_fact_but_a_well_formed_reading(fact) -> None:
    builder = SnarsProgramBuilder(reader=_Reader())
    with pytest.raises(InvalidInputError):
        builder.batch(builder.codec.expression("gc", builder.codec.symbol("inspect-record")), facts=(fact,))


# A policy batch carries its reader's declaration as the section's forms, which run_snars_batch
# adds to the world ahead of the facts and of the directive that runs the policy; a batch without
# the policy carries none.
# am[verifies a-jev-reading-belief-1016] am[related a-rt-snars-batch-value-1017@0e8147]
# am[verifies a-dr-sr-snars-batch-declaration-1018@5c965d]
def test_a_policy_batch_carries_the_reading_table_before_the_policy() -> None:
    builder = SnarsProgramBuilder(reader=_Reader())
    operation = builder.codec.expression("gc", builder.codec.symbol("inspect-record"))

    with_policy = builder.batch(operation, includes={"policy"})
    without_policy = builder.batch(operation)

    assert any(row.startswith("(gc-reading-model ") for row in with_policy.rows)
    assert any(row.startswith("(gc-reading-proposition ") for row in with_policy.rows)
    assert "(gc assert-request-context!)" in with_policy.directive
    assert without_policy.rows == ()


# A promoted reranker re-reads the request text. The cached Jev answer replays with no second
# request; the new ranker grounds it in another passage and the event records another reader
# revision; SNARS still holds one receipt and the same evidence, because it keys a receipt by
# statement and source (c-snars-receipt-statement-source-1016). Jev and both rankers are
# synthetic, so no hosted call is made.
# am[verifies a-jev-snars-ingest-1016] am[verifies a-ie-s7-tests-1018@5c72ce]
def test_a_promoted_ranker_rereading_a_text_adds_no_evidence(tmp_path) -> None:
    text = "Checkout is down. Raw logs include customer emails."
    calls = []

    def answer_for(q, state):
        if q == "mood":
            return sure(q, state)
        top = "supported" if q == "sensitive-data" else "unknown"
        return {option: (0.9 if option == top else 0.05) for option in TABLE.answers}

    favourite = {"base": "Raw logs include customer emails.", "promoted": "Checkout is down."}
    served = {"now": sr.ServedRanker("base", tmp_path)}

    def load(ranker):
        best = favourite[ranker.identity]
        return SimpleNamespace(scores=lambda pairs: tuple(0.9 if p == best else 0.1 for _q, p in pairs))

    jev = sr.JevClient(sr.AnswerCache(tmp_path / "answers"), TABLE.model,
                       client_factory=client(answering(answer_for, calls=calls)))
    reader = sr.SemanticReader(declaration=TABLE, jev=jev, serve=lambda: served["now"], load=load)
    session = SnarsSession.ephemeral(budget=request_budget(), reader=incident_reader())
    session.builder = SnarsProgramBuilder(reader=reader)
    source = "text:checkout"
    with session:
        session.ingest_text(text, source=source)
        served["now"] = sr.ServedRanker("promoted", tmp_path)
        session.ingest_text(text, source=source)
        sensitive = session.belief(reading_statement("sensitive-data"))
        events = session.store.events()

    assert len(calls) == 1
    assert len({event.payload["reader_revision"] for event in events}) == 2
    assert [any(f'"{favourite[name]}"' in fact for fact in event.payload["facts"])
            for name, event in zip(("base", "promoted"), events)] == [True, True]
    assert sensitive.evidence.positive == pytest.approx(7.2)
    assert [r.source for r in sensitive.receipts] == [source]


# A store keeps the readings of every text it ever read, but a decision on one request believes
# nothing another request said, even under the same source, as the CLI's constant --source gives:
# the second text's session on a shared store sees exactly what it sees on a store of its own, and
# asking again changes nothing. Jev and the ranker are synthetic, so no hosted call is made.
# am[verifies a-jev-session-reads-1017@3d73d9] am[verifies a-ie-s7-tests-1018@5c72ce]
def test_a_session_believes_only_the_texts_it_read_itself(tmp_path) -> None:
    sensitive = "Raw logs include customer emails."
    public = "The logs are public and safe to share."
    supported = {"sensitive-data": sensitive, "public-data": public}

    def answer_for(q, state):
        if q == "mood":
            return sure(q, state)
        top = "supported" if supported.get(q) == state["text"] else "unknown"
        return {option: (0.9 if option == top else 0.05) for option in TABLE.answers}

    jev = sr.JevClient(sr.AnswerCache(tmp_path / "answers"), TABLE.model,
                       client_factory=client(answering(answer_for)))
    reader = sr.SemanticReader(
        declaration=TABLE, jev=jev, serve=lambda: sr.ServedRanker("base", tmp_path),
        load=lambda ranker: SimpleNamespace(scores=lambda pairs: tuple(0.5 for _pair in pairs)),
    )

    # What the session believes of sensitive-data and public-data, in that order.
    def beliefs(text, store):
        session = SnarsSession.persistent(store, budget=request_budget(), reader=incident_reader())
        session.builder = SnarsProgramBuilder(reader=reader)
        with session:
            session.ingest_text(text, source="cli")
            return tuple(session.belief(reading_statement(name)) for name in ("sensitive-data", "public-data"))

    first = beliefs(sensitive, tmp_path / "shared.sqlite3")
    second = beliefs(public, tmp_path / "shared.sqlite3")
    alone = beliefs(public, tmp_path / "alone.sqlite3")
    again = beliefs(public, tmp_path / "shared.sqlite3")

    assert first[0].evidence.positive == pytest.approx(7.2)
    assert second[0].evidence.positive == 0
    assert second[1].evidence.positive == pytest.approx(7.2)
    assert second == alone == again

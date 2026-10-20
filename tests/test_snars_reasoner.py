"""Purpose: test SNARS sessions, their event replay and the features each operation's batch
includes against a fake executor standing in for the engine, and that a session opens its store and
appends each operation's event only within its request's budget, reads its store only within that
budget, and answers a what-if without writing whatever another session appends meanwhile."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing

import pytest

from request_support import budget as request_budget
from goal_chainer import snars_reasoner
from goal_chainer.snars_engine import snars_identity
from goal_chainer.snars_models import (
    Evidence,
    EvidenceCounts,
)
from goal_chainer.errors import InvalidInputError, MettaEngineError, PersistenceError, ProtocolError
from goal_chainer.event_store import digest
from goal_chainer.runtime import budget as budget_module
from goal_chainer.runtime.budget import InferenceBudgetExceeded, ReviewTimeout, RunBudget
from goal_chainer.snars_reasoner import (
    SnarsSession,
)
from goal_chainer.snars_store import SnarsEventStore
from goal_chainer.snars_program import ProgramFragments, TextIngestion
from reading_support import incident_reader

STATEMENT = (
    '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
)
OTHER_STATEMENT = (
    '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "c"))))'
)


# Answers each batch with the next canned output, or raises, and keeps every batch it was given;
# a batch's text is its facts and directive, what a test reads to see what a batch carried.
# am[related a-rt-snars-batch-speculative-1017@451056]
class FakeExecutor:
    def __init__(self, outputs=(), error: Exception | None = None) -> None:
        self.outputs = list(outputs)
        self.error = error
        self.batches = []

    def __call__(self, batch, budget):
        self.batches.append(batch)
        if self.error is not None:
            raise self.error
        return tuple(self.outputs.pop(0))

    @property
    def programs(self) -> list[str]:
        return ["\n".join((*batch.facts, batch.directive)) for batch in self.batches]


def _belief_record(operation: str = "belief") -> list[str]:
    return [
        f"""
        (goalchainer-snars-v1 {operation} ok
          (belief sid-1
            {STATEMENT}
            (opinion 0.6 0.1 0.3 0.5)
            (evidence 6 1 0.5)
            (receipts ((receipt receipt-1 "caller" sid-1 1.0)))
            (proofs ())
            (occurrences ())))
        """
    ]


# am[related a-rt-snars-batch-speculative-1017@451056]
def test_successful_belief_is_appended_after_petta_returns() -> None:
    runtime = FakeExecutor([_belief_record()])
    with SnarsSession.ephemeral(execute=runtime, budget=request_budget(), reader=incident_reader()) as session:
        belief = session.believe(
            STATEMENT,
            evidence=EvidenceCounts(2.0, 1.0, 0.5),
            source="caller",
        )

        assert belief.opinion.expectation == pytest.approx(0.75)
        assert [event.kind for event in session.store.events()] == ["belief"]


# am[related a-rt-snars-batch-speculative-1017@451056]
def test_failed_mutation_does_not_append_an_event() -> None:
    runtime = FakeExecutor(
        error=MettaEngineError("failed", details={"returncode": 1})
    )
    store = SnarsEventStore.memory(snars_identity=snars_identity())
    session = SnarsSession(store, execute=runtime, budget=request_budget(), reader=incident_reader())

    with pytest.raises(MettaEngineError):
        session.believe(STATEMENT)

    assert store.events() == ()
    session.close()


# am[related a-rt-snars-batch-speculative-1017@451056]
def test_persistent_replay_reconstructs_the_successful_belief(tmp_path) -> None:
    database = tmp_path / "snars.sqlite3"
    writer = FakeExecutor([_belief_record()])
    with SnarsSession.persistent(database, execute=writer, budget=request_budget(),
                                 reader=incident_reader()) as session:
        session.believe(
            STATEMENT,
            evidence=EvidenceCounts(2.0, 1.0, 0.5),
            source="caller",
        )

    reader = FakeExecutor([_belief_record()])
    with SnarsSession.persistent(database, execute=reader, budget=request_budget(),
                                 reader=incident_reader()) as session:
        replayed = session.belief(STATEMENT)

    assert replayed.statement_id == "sid-1"
    assert "(believe!" in reader.programs[0]
    assert '(source "caller")' in reader.programs[0]


# A store whose events another SNARS library recorded would replay them through this one, so the
# session refuses it before running anything.
# am[verifies a-rt-snars-store-identity-1017@deb59d]
def test_a_store_written_against_another_snars_library_is_refused() -> None:
    store = SnarsEventStore.memory(snars_identity="d" * 64)

    with pytest.raises(PersistenceError, match="different SNARS library"):
        SnarsSession(store, execute=FakeExecutor(), budget=request_budget(), reader=incident_reader())
    store.close()


# Each operation names the optional features its batch's world loads: the guard beside the
# session's own features; the rest, the belief of a reading's statement among them, take the
# session's default, the policy unless the session was made without it.
# am[verifies a-rt-snars-batch-value-1017@0e8147] am[verifies a-ie-s7-tests-1018@5c72ce]
# am[verifies a-ie-s2c-scalar-tests-proofs-1018@5a0031]
@pytest.mark.parametrize(
    "policy, operation, includes",
    [
        (True, lambda session: session.belief(STATEMENT), {"policy"}),
        (False, lambda session: session.belief(STATEMENT), set()),
        (True, lambda session: session.guard("(sn-goal x)"), {"policy", "guard"}),
        (False, lambda session: session.guard("(sn-goal x)"), {"guard"}),
        (True, lambda session: session.inspect(), {"policy"}),
        (False, lambda session: session.inspect(), set()),
    ],
)
def test_each_operation_runs_with_the_features_it_needs(policy, operation, includes) -> None:
    executor = FakeExecutor(error=MettaEngineError("stop", details={}))
    with SnarsSession.ephemeral(execute=executor, include_goalchainer_policy=policy, budget=request_budget(),
                                reader=incident_reader()) as session:
        with pytest.raises(MettaEngineError):
            operation(session)

    assert [batch.includes for batch in executor.batches] == [frozenset(includes)]


# am[verifies a-jev-snars-ingest-1016]
def test_redacted_ingestion_replays_only_the_prepared_payload(monkeypatch) -> None:
    runtime = FakeExecutor(
        [
            ["(goalchainer-snars-v1 inspect ok (inspection))"],
        ]
    )
    store = SnarsEventStore.memory(
        snars_identity=snars_identity(),
        redactor=lambda kind, payload: {
            **payload,
            "text": "[redacted]",
            "facts": ['(gc-reading "user" 1.0 sensitive-data supported 0.9 (provenance "m" "k" "[redacted]"))'],
        },
    )
    session = SnarsSession(store, execute=runtime, budget=request_budget(), reader=incident_reader())
    ingested = TextIngestion(
        revision="synthetic",
        fragments=ProgramFragments(
            facts=('(gc-reading "user" 1.0 sensitive-data supported 0.9 (provenance "m" "k" "secret"))',),
        ),
    )
    monkeypatch.setattr(session.builder, "text_ingestion", lambda *args, **kwargs: ingested)

    session.ingest_text("secret")

    event = store.events()[0]
    assert event.payload["text"] == "[redacted]"
    assert session.last_ingestion_payload == event.payload
    assert '"secret"' not in runtime.programs[0]
    assert "redacted" in runtime.programs[0]
    session.close()


# am[verifies a-jev-snars-ingest-1016]
def test_repeated_identical_ingestion_is_idempotent(monkeypatch) -> None:
    runtime = FakeExecutor(
        [
            ["(goalchainer-snars-v1 inspect ok (inspection))"],
            ["(goalchainer-snars-v1 inspect ok (inspection))"],
        ]
    )
    session = SnarsSession.ephemeral(execute=runtime, budget=request_budget(), reader=incident_reader())
    ingested = TextIngestion(
        revision="synthetic",
        fragments=ProgramFragments(
            facts=('(gc-reading "request" 1.0 public-data contradicted 0.8 (provenance "m" "k" "safe"))',),
        ),
    )
    monkeypatch.setattr(session.builder, "text_ingestion", lambda *args, **kwargs: ingested)

    session.ingest_text("same", source="request")
    first_digest = session.store.state_digest()
    session.ingest_text("same", source="request")

    assert len(session.store.events()) == 1
    assert session.store.state_digest() == first_digest
    session.close()


# am[verifies a-ev-oe-once@57dc67]
def _outcome_record() -> list[str]:
    return [
        '(goalchainer-snars-v1 outcome ok (outcome-audit (OUTCOME sid-1 0.6 0.7 1.0 "goalchainer:execution" 1) '
        '(source "goalchainer:execution") (trust-before 0.5) (trust-after 0.55)))'
    ]


# am[verifies a-ev-br-session-1017@c3ddf0]
def _transform_record() -> list[str]:
    return ["(goalchainer-snars-v1 transform ok (transform marginal sid-1))"]


# Evidence that gives no rate is stored with a null rate, and neither the batch that believes it nor
# a later replay writes a (rate R) clause, so SNARS reads it at the rate its world configures; a
# rate the caller gives is written and stored as given.
# am[verifies a-ev-br-session-1017@c3ddf0] am[verifies a-ev-br-builder-1017@fa66f9]
def test_a_belief_given_no_rate_is_stored_and_replayed_without_one(tmp_path) -> None:
    database = tmp_path / "rate.sqlite3"
    writer = FakeExecutor([_belief_record(), _belief_record()])
    with SnarsSession.persistent(database, execute=writer, budget=request_budget(),
                                 reader=incident_reader()) as session:
        session.believe(STATEMENT, evidence=Evidence(2.0, 1.0), source="unstated")
        session.believe(STATEMENT, evidence=Evidence(2.0, 1.0, 0.7), source="stated")
        rates = [event.payload["base_rate"] for event in session.store.events()]

    reader = FakeExecutor([_belief_record()])
    with SnarsSession.persistent(database, execute=reader, budget=request_budget(),
                                 reader=incident_reader()) as session:
        session.belief(STATEMENT)

    assert rates == [None, 0.7]
    assert "(rate" not in writer.programs[0]
    assert "(rate 0.7)" in writer.programs[1]
    assert reader.programs[0].count("(rate") == 1


# outcome! takes the rate as an argument, so an outcome given none hands SNARS its configured
# default there, in the batch that records it and in every batch that replays it.
# am[verifies a-ev-br-session-1017@c3ddf0] am[verifies a-ev-br-builder-1017@fa66f9]
def test_an_outcome_given_no_rate_is_fused_at_the_configured_default(tmp_path) -> None:
    database = tmp_path / "outcome-rate.sqlite3"
    writer = FakeExecutor([_outcome_record()])
    with SnarsSession.persistent(database, execute=writer, budget=request_budget(),
                                 reader=incident_reader()) as session:
        session.record_outcome(
            STATEMENT,
            evidence=Evidence(1.0, 0.0),
            source="goalchainer:execution",
            observation_id="obs-1",
        )
        (event,) = session.store.events()

    reader = FakeExecutor([_belief_record()])
    with SnarsSession.persistent(database, execute=reader, budget=request_budget(),
                                 reader=incident_reader()) as session:
        session.belief(STATEMENT)

    assert event.payload["base_rate"] is None
    assert '(sn config default-rate) "goalchainer:execution"' in writer.programs[0]
    assert "(gc outcome-record" in writer.programs[0]
    assert "(sn outcome!" in reader.programs[0]
    assert '(sn config default-rate) "goalchainer:execution"' in reader.programs[0]


# A what-if hypothesis and a marginal pass a rate only when the caller gives one: the hypothesis
# leaves out its (rate R) clause and the marginal seeds SNARS's configured default.
# am[verifies a-ev-br-session-1017@c3ddf0]
def test_a_what_if_hypothesis_and_a_marginal_pass_a_rate_only_when_given() -> None:
    hypothesis = FakeExecutor(error=MettaEngineError("stopped", details={"returncode": 1}))
    with SnarsSession.ephemeral(execute=hypothesis, budget=request_budget(), reader=incident_reader()) as session:
        for evidence in (None, Evidence(2.0, 1.0, 0.7)):
            with pytest.raises(MettaEngineError):
                session.what_if(STATEMENT, STATEMENT, evidence=evidence)
    marginal = FakeExecutor([_transform_record(), _transform_record()])
    with SnarsSession.ephemeral(execute=marginal, budget=request_budget(), reader=incident_reader()) as session:
        session.transform("marginal", STATEMENT)
        session.transform("marginal", STATEMENT, base_rate=0.7)

    assert "(evidence 8.0 0.0)" in hypothesis.programs[0]
    assert "(rate" not in hypothesis.programs[0]
    assert "(rate 0.7)" in hypothesis.programs[1]
    assert "NoStatement (sn config default-rate))" in marginal.programs[0]
    assert "NoStatement 0.7)" in marginal.programs[1]


# am[verifies a-ev-nm-replay@856e27]
def test_an_identical_belief_is_not_appended_twice() -> None:
    runtime = FakeExecutor([_belief_record(), _belief_record()])
    with SnarsSession.ephemeral(execute=runtime, budget=request_budget(), reader=incident_reader()) as session:
        digests = []
        for _ in range(2):
            session.believe(
                STATEMENT,
                evidence=EvidenceCounts(2.0, 1.0, 0.5),
                source='memory:["belief","b-1"]',
            )
            digests.append(session.store.state_digest())

        assert [event.kind for event in session.store.events()] == ["belief"]
        assert digests[0] == digests[1]
        # The resupplied belief replays the stored event and adds nothing pending.
        assert runtime.programs[0] == runtime.programs[1]


# am[verifies a-ev-oe-once@57dc67]
def test_an_observation_is_recorded_as_an_outcome_once() -> None:
    runtime = FakeExecutor([_outcome_record()])
    with SnarsSession.ephemeral(execute=runtime, budget=request_budget(), reader=incident_reader()) as session:
        first = session.record_outcome(
            STATEMENT,
            evidence=EvidenceCounts(1.0, 0.0, 0.5),
            source="goalchainer:execution",
            observation_id="obs-1",
        )
        second = session.record_outcome(
            STATEMENT,
            evidence=EvidenceCounts(1.0, 0.0, 0.5),
            source="goalchainer:execution",
            observation_id="obs-1",
        )

        assert first is not None and first.operation == "outcome"
        assert second is None
        assert session.has_outcome("obs-1")
        assert not session.has_outcome("obs-2")
        assert len(runtime.programs) == 1
        (event,) = session.store.events()
        assert event.payload["observation_id"] == "obs-1"


# am[verifies a-ev-oe-once@57dc67]
def test_an_outcome_needs_an_observation_identity() -> None:
    with SnarsSession.ephemeral(execute=FakeExecutor(), budget=request_budget(), reader=incident_reader()) as session:
        with pytest.raises(InvalidInputError, match="observation_id"):
            session.record_outcome(
                STATEMENT,
                evidence=EvidenceCounts(1.0, 0.0, 0.5),
                source="goalchainer:execution",
                observation_id=" ",
            )


# The outcome every test below records first, by keyword.
RECORDED = {
    "statement": STATEMENT,
    "evidence": EvidenceCounts(1.0, 0.0, 0.5),
    "source": "goalchainer:execution",
    "trust": 1.0,
}


# Two sessions on one store both find the observation unrecorded: the second session's batch runs
# once its check has passed, and the first session records the observation meanwhile. The second's
# keyed append then meets the recorded key, so the same outcome answers None and a different one is
# refused, and the store holds the first session's one event either way.
# am[verifies a-ev-oe-once@57dc67] am[verifies a-v2-outcome-sequential-conflict-1020@10212e]
@pytest.mark.parametrize("evidence", [EvidenceCounts(1.0, 0.0, 0.5), EvidenceCounts(0.0, 1.0, 0.5)],
                         ids=["same outcome", "different evidence"])
def test_two_sessions_racing_on_one_store_record_an_observation_once(tmp_path, evidence) -> None:
    database = tmp_path / "race.sqlite3"
    first = SnarsSession.persistent(database, execute=FakeExecutor([_outcome_record()]), budget=request_budget(),
                                    reader=incident_reader())
    recorded = []

    # The second session's batch: the first session records the observation while it runs.
    # am[verifies a-v2-outcome-sequential-conflict-1020@10212e]
    def second_batch(batch, budget):
        recorded.append(first.record_outcome(**RECORDED, observation_id="obs-race"))
        return tuple(_outcome_record())

    second = SnarsSession.persistent(database, execute=second_batch, budget=request_budget(),
                                     reader=incident_reader())
    try:
        if evidence == RECORDED["evidence"]:
            assert second.record_outcome(**{**RECORDED, "evidence": evidence}, observation_id="obs-race") is None
        else:
            with pytest.raises(PersistenceError, match="different event is already recorded"):
                second.record_outcome(**{**RECORDED, "evidence": evidence}, observation_id="obs-race")
        events = first.store.events()
    finally:
        first.close()
        second.close()

    assert len(recorded) == 1 and recorded[0] is not None
    assert [(event.kind, event.payload["positive"]) for event in events] == [("outcome", 1.0)]


# A retry of a recorded observation is decided by the store's own keyed-append rule before any batch
# runs: a change to its statement, evidence, base rate, source or trust under the same observation id
# is refused, and the recorded outcome itself again answers None, so the store keeps its one event
# and the retrying session runs nothing. The session's key check once answered None for any retry,
# so changed evidence vanished without a word (c-v2-outcome-early-return-1020).
# am[verifies a-v2-outcome-sequential-conflict-1020@10212e] am[verifies a-ev-oe-once@57dc67]
@pytest.mark.parametrize("change", [
    {"statement": OTHER_STATEMENT},
    {"evidence": EvidenceCounts(0.0, 1.0, 0.5)},
    {"evidence": EvidenceCounts(1.0, 0.0, 0.7)},
    {"source": "goalchainer:other"},
    {"trust": 0.5},
], ids=["statement", "evidence", "base rate", "source", "trust"])
def test_a_retry_changing_a_recorded_observation_is_refused_before_any_batch(tmp_path, change) -> None:
    database = tmp_path / "retry.sqlite3"
    with SnarsSession.persistent(database, execute=FakeExecutor([_outcome_record()]), budget=request_budget(),
                                 reader=incident_reader()) as session:
        session.record_outcome(**RECORDED, observation_id="obs-1")
        (recorded,) = session.store.events()
    retry = FakeExecutor()
    with SnarsSession.persistent(database, execute=retry, budget=request_budget(),
                                 reader=incident_reader()) as session:
        with pytest.raises(PersistenceError, match="different event is already recorded") as refused:
            session.record_outcome(**{**RECORDED, **change}, observation_id="obs-1")
        repeated = session.record_outcome(**RECORDED, observation_id="obs-1")
        events = session.store.events()

    assert refused.value.details["key"] == "obs-1"
    assert repeated is None
    assert events == (recorded,)
    assert retry.batches == []


# A temporal query's now is a real number a finite float holds, refused before anything runs or
# is stored: a bare float() took true as 1.0 and parsed a numeric string, NaN reached the event
# store, and an integer beyond the float range escaped as OverflowError.
# am[verifies a-rt-nr-repair-1018@72901e]
@pytest.mark.parametrize("now", [True, "2", float("nan"), float("inf"), 10**400])
def test_a_temporal_now_no_finite_float_holds_is_refused_before_anything_runs(now) -> None:
    runtime = FakeExecutor()
    with SnarsSession.ephemeral(execute=runtime, budget=request_budget(), reader=incident_reader()) as session:
        with pytest.raises(InvalidInputError, match="now must be a finite real number"):
            session.temporal(STATEMENT, now=now)
        assert session.store.events() == ()
    assert runtime.batches == []


# A probability given as an integer beyond the float range is out of [0, 1], not an OverflowError.
# am[verifies a-rt-nr-repair-1018@72901e]
def test_a_trust_beyond_the_float_range_is_refused_as_out_of_range() -> None:
    runtime = FakeExecutor()
    with SnarsSession.ephemeral(execute=runtime, budget=request_budget(), reader=incident_reader()) as session:
        with pytest.raises(InvalidInputError, match=r"trust must be in \[0, 1\]"):
            session.what_if(STATEMENT, STATEMENT, trust=10**400)
    assert runtime.batches == []


# A store is a caller's file, and an event whose content hash is recomputed passes the store's own
# checks, so replay refuses a number no finite float holds as a store it cannot read.
# am[verifies a-rt-nr-repair-1018@72901e]
def test_a_stored_number_no_finite_float_holds_is_refused_on_replay(tmp_path) -> None:
    database = tmp_path / "snars.sqlite3"
    with SnarsSession.persistent(database, execute=FakeExecutor([_belief_record()]), budget=request_budget(),
                                 reader=incident_reader()) as session:
        session.believe(STATEMENT, evidence=EvidenceCounts(2.0, 1.0, 0.5), source="caller")
    store = SnarsEventStore(database, snars_identity=snars_identity())
    belief, = store.events()
    store.append(belief.kind, {**belief.payload, "positive": 10**400})
    store.close()

    with pytest.raises(PersistenceError, match="numeric field is invalid"):
        with SnarsSession.persistent(database, execute=FakeExecutor([_belief_record()] * 2),
                                     budget=request_budget(), reader=incident_reader()) as session:
            session.belief(STATEMENT)


# A session opened under a budget already spent raises that budget's exhaustion as its store opens,
# before any batch: a persistent session makes no database file, and an ephemeral one is refused alike.
# am[verifies a-v2rs-snars-budget-1020@5469ea]
@pytest.mark.parametrize("persistent", [False, True], ids=["ephemeral", "persistent"])
def test_a_session_under_a_spent_budget_is_refused_as_its_store_opens(tmp_path, persistent) -> None:
    spent = RunBudget(inference_budget=1, timeout_seconds=60)
    spent.charge(1)
    executor = FakeExecutor()

    with pytest.raises(InferenceBudgetExceeded):
        if persistent:
            SnarsSession.persistent(tmp_path / "snars.sqlite3", execute=executor, budget=spent)
        else:
            SnarsSession.ephemeral(execute=executor, budget=spent)

    assert list(tmp_path.iterdir()) == [] and executor.batches == []


# An append waits for the store's write lock no longer than the request's deadline: with another
# connection holding the lock, the belief the batch computed raises the budget's ReviewTimeout after
# about its 0.5 s, not the store's own 5 s, and the store records nothing; the same belief under a
# fresh budget, once the lock is free, records it once.
# am[verifies a-v2rs-snars-budget-1020@5469ea]
def test_an_append_held_past_the_deadline_raises_its_timeout_and_records_nothing(tmp_path) -> None:
    database = tmp_path / "snars.sqlite3"
    SnarsSession.persistent(database, execute=FakeExecutor(), budget=request_budget()).close()
    with closing(sqlite3.connect(database, isolation_level=None)) as holder:
        holder.execute("BEGIN IMMEDIATE")
        budget = RunBudget(inference_budget=None, timeout_seconds=0.5)
        start = time.monotonic()
        with SnarsSession.persistent(database, execute=FakeExecutor([_belief_record()]), budget=budget) as session:
            with pytest.raises(ReviewTimeout):
                session.believe(STATEMENT)
        waited = time.monotonic() - start
        holder.execute("ROLLBACK")
    with SnarsSession.persistent(database, execute=FakeExecutor([_belief_record()]),
                                 budget=request_budget()) as session:
        session.believe(STATEMENT)
        events = session.store.events()

    assert 0.45 <= waited < 2.0
    assert [event.kind for event in events] == ["belief"]


# The goal and temporal answers each operation's canned batch gives.
# am[verifies a-v2rs-snars-budget-1020@5469ea]
def _goal_record() -> list[str]:
    return [f'(goalchainer-snars-v1 goal ok (goal gid-1 {STATEMENT} "owner" individual 1.0 True "cli" (subgoals ())))']


# Each operation that persists an event, run on a session, with the canned answer its batch gives.
# am[verifies a-v2rs-snars-budget-1020@5469ea]
PERSISTING = {
    "ingest_text": (lambda session: session.ingest_text("text"), ["(goalchainer-snars-v1 inspect ok (inspection))"]),
    "believe": (lambda session: session.believe(STATEMENT), _belief_record()),
    "register_goal": (lambda session: session.register_goal(STATEMENT, owner="owner", kind="individual", desire=1.0,
                                                            required=True, source="cli"), _goal_record()),
    "temporal": (lambda session: session.temporal(STATEMENT, now=1.0), ["(goalchainer-snars-v1 temporal ok (temporal))"]),
    "record_outcome": (lambda session: session.record_outcome(**RECORDED, observation_id="obs-1"), _outcome_record()),
}


# A batch that spends what is left of the budget leaves its event uncommitted: the append reads the
# budget before it commits, so every operation that persists raises the budget's exhaustion, answers
# nothing and records nothing, and its batch ran once.
# am[verifies a-v2rs-snars-budget-1020@5469ea]
@pytest.mark.parametrize("operation", PERSISTING, ids=list(PERSISTING))
def test_an_operation_whose_batch_spends_the_budget_records_nothing(tmp_path, monkeypatch, operation) -> None:
    run, answer = PERSISTING[operation]
    batches = []

    # am[verifies a-v2rs-snars-budget-1020@5469ea]
    def spending(batch, budget):
        batches.append(batch)
        budget.charge(budget.inference_budget - budget.spent)
        return tuple(answer)

    with SnarsSession.persistent(tmp_path / "snars.sqlite3", execute=spending,
                                 budget=RunBudget(inference_budget=1000, timeout_seconds=60)) as session:
        monkeypatch.setattr(session.builder, "text_ingestion",
                            lambda *args, **kwargs: TextIngestion(revision="synthetic", fragments=ProgramFragments()))
        with pytest.raises(InferenceBudgetExceeded):
            run(session)
        events = session.store.events()

    assert events == () and len(batches) == 1


# Two sessions submitting one event at once append it once, for each operation that appends its event
# only when no identical one exists: the second session's batch runs while the first records the same
# event, and the store's keyed append decides between them, so the second's identical append adds
# nothing and its answer still stands.
# am[verifies a-v2rs-snars-keyed-dedup-1020@85653f]
@pytest.mark.parametrize("operation", ["ingest_text", "believe", "register_goal"])
def test_two_sessions_submitting_one_event_at_once_append_it_once(tmp_path, monkeypatch, operation) -> None:
    run, answer = PERSISTING[operation]
    database = tmp_path / "race.sqlite3"
    first = SnarsSession.persistent(database, execute=FakeExecutor([answer]), budget=request_budget())

    # The second session's batch: the first records the same event while it runs.
    # am[verifies a-v2rs-snars-keyed-dedup-1020@85653f]
    def second_batch(batch, budget):
        run(first)
        return tuple(answer)

    second = SnarsSession.persistent(database, execute=second_batch, budget=request_budget())
    for session in (first, second):
        monkeypatch.setattr(session.builder, "text_ingestion",
                            lambda *args, **kwargs: TextIngestion(revision="synthetic", fragments=ProgramFragments()))
    try:
        run(second)
        events = first.store.events()
        keyed = first.store.event_keys()
    finally:
        first.close()
        second.close()

    assert len(events) == 1 and list(keyed) == [events[0].sequence]


# Beliefs that differ only in their source are two events, each appended once, even when their
# sessions submit them at once.
# am[verifies a-v2rs-snars-keyed-dedup-1020@85653f]
def test_differing_beliefs_submitted_at_once_are_both_recorded(tmp_path) -> None:
    database = tmp_path / "race.sqlite3"
    first = SnarsSession.persistent(database, execute=FakeExecutor([_belief_record()]), budget=request_budget())

    # The second session's batch: the first records its own belief while it runs.
    # am[verifies a-v2rs-snars-keyed-dedup-1020@85653f]
    def second_batch(batch, budget):
        first.believe(STATEMENT, source="first")
        return tuple(_belief_record())

    second = SnarsSession.persistent(database, execute=second_batch, budget=request_budget())
    try:
        second.believe(STATEMENT, source="second")
        events = first.store.events()
    finally:
        first.close()
        second.close()

    assert sorted(event.payload["source"] for event in events) == ["first", "second"]


# A belief an earlier version stored unkeyed is still the session's identical event: resupplying it
# appends nothing, the session finding it by its payload, while a different belief is appended keyed.
# am[verifies a-v2rs-snars-keyed-dedup-1020@85653f]
def test_a_belief_stored_unkeyed_is_not_appended_again(tmp_path) -> None:
    with SnarsSession.ephemeral(execute=FakeExecutor([_belief_record()]), budget=request_budget()) as session:
        session.believe(STATEMENT)
        (written,) = session.store.events()
    database = tmp_path / "unkeyed.sqlite3"
    with SnarsEventStore(database, snars_identity=snars_identity()) as store:
        store.append_prepared("belief", written.payload)
    with SnarsSession.persistent(database, execute=FakeExecutor([_belief_record(), _belief_record()]),
                                 budget=request_budget()) as session:
        session.believe(STATEMENT)
        session.believe(STATEMENT, source="another")
        events = session.store.events()
        keys = session.store.event_keys()

    assert [event.payload["source"] for event in events] == ["caller", "another"]
    assert list(keys) == [events[1].sequence]


# A state report describes one read of the store: another writer appending after every read the
# session makes, as a concurrent session would between two reads, cannot make the report's digest
# and its event count describe different events.
# am[verifies a-v2rs-state-one-read-1020@736ce1]
def test_a_state_report_takes_its_digest_and_count_from_one_read(tmp_path, monkeypatch) -> None:
    with SnarsSession.persistent(tmp_path / "snars.sqlite3", execute=FakeExecutor([_belief_record()]),
                                 budget=request_budget()) as session:
        session.believe(STATEMENT)
        read = session.store.events
        reads = []

        # One read, then another writer's append before the session reads again.
        # am[verifies a-v2rs-state-one-read-1020@736ce1]
        def read_then_append(**options):
            events = read(**options)
            reads.append(events)
            session.store.append_prepared("belief", {**events[0].payload, "source": f"writer-{len(reads)}"})
            return events

        monkeypatch.setattr(session.store, "events", read_then_append)
        state = session.state_payload()

    assert len(reads) == 1
    assert (state["digest"], state["event_count"]) == (digest(reads[0]), len(reads[0]))


# The state report's hashing is its last step: the deadline passing while it hashes the events it
# read raises the budget's ReviewTimeout, so the report never answers past the deadline.
# am[verifies a-v2rs-kr-session-1020@53ac31]
def test_a_state_report_hashing_past_its_deadline_raises_its_timeout(tmp_path, monkeypatch) -> None:
    now = [0.0]
    monkeypatch.setattr(budget_module.time, "monotonic", lambda: now[0])
    budget = RunBudget(inference_budget=None, timeout_seconds=10)
    with SnarsSession.persistent(tmp_path / "snars.sqlite3", execute=FakeExecutor([_belief_record()]),
                                 budget=budget) as session:
        session.believe(STATEMENT)
        hashing = snars_reasoner.digest

        # The hashing takes 100 s by the clock.
        # am[verifies a-v2rs-kr-session-1020@53ac31]
        def slow_digest(events):
            now[0] += 100.0
            return hashing(events)

        monkeypatch.setattr(snars_reasoner, "digest", slow_digest)
        with pytest.raises(ReviewTimeout):
            session.state_payload()


# A session whose budget is spent after it opened stops at its replay read, before any batch: the
# read of the store's events is the operation's first stage under the budget.
# Each read a session's operation makes of its store before any batch runs, after the session has
# recorded the observation obs-1: a belief query's and a what-if's replay reads, a repeated outcome's
# lookup of its observation, has_outcome, and the state report.
# am[verifies a-v2rs-events-budget-1020@a8933d] am[verifies a-v2rs-kr-session-1020@53ac31]
SESSION_READS = {
    "belief": lambda session: session.belief(STATEMENT),
    "what_if": lambda session: session.what_if(STATEMENT, STATEMENT),
    "repeated record_outcome": lambda session: session.record_outcome(**RECORDED, observation_id="obs-1"),
    "has_outcome": lambda session: session.has_outcome("obs-1"),
    "state_payload": lambda session: session.state_payload(),
}


# A session whose budget is spent after it opened raises that exhaustion at the first read its
# operation makes of the store, and runs no further batch: every read takes the request's budget. A
# repeated outcome and has_outcome once answered past a spent budget, None and True, and the state
# report read the whole stream past it (i-v2rs-key-reads-unbudgeted-1020).
# am[verifies a-v2rs-events-budget-1020@a8933d] am[verifies a-v2rs-kr-session-1020@53ac31]
@pytest.mark.parametrize("read", SESSION_READS, ids=list(SESSION_READS))
def test_a_session_whose_budget_is_spent_raises_at_its_first_store_read(tmp_path, read) -> None:
    budget = RunBudget(inference_budget=10, timeout_seconds=60)
    executor = FakeExecutor([_outcome_record()])
    with SnarsSession.persistent(tmp_path / "snars.sqlite3", execute=executor, budget=budget) as session:
        session.record_outcome(**RECORDED, observation_id="obs-1")
        budget.charge(10)
        with pytest.raises(InferenceBudgetExceeded):
            SESSION_READS[read](session)

    assert len(executor.batches) == 1


# A what-if answer whose SNARS state reads `before` before its hypothesis and `after` once it is
# rolled back.
# am[verifies a-v2rs-kr-session-1020@53ac31]
def _what_if_record(after: str = "(state (statements ()))") -> list[str]:
    return [
        f"(goalchainer-snars-v1 what-if ok (counterfactual (hypothesis {STATEMENT}) (query {STATEMENT}) "
        f"(opinion (Opinion 0.0 0.0 1.0 0.5)) (proofs ()) (state-before (state (statements ()))) "
        f"(state-after {after})))"
    ]


# A what-if writes nothing: it leaves its store as it found it, and an answer whose SNARS state was not
# rolled back is refused. Another session appending while the what-if's batch runs therefore leaves
# the what-if's answer standing, the store holding the other session's event alone; the session once
# compared the whole stream's digest before and after its batch and called that append the
# counterfactual's own change (i-v2rs-what-if-false-conflict-1020).
# am[verifies a-v2rs-kr-session-1020@53ac31]
def test_a_what_if_writes_nothing_and_stands_whatever_another_session_appends(tmp_path) -> None:
    alone = FakeExecutor([_belief_record(), _what_if_record(), _what_if_record(after="(state (statements (s)))")])
    with SnarsSession.ephemeral(execute=alone, budget=request_budget()) as session:
        session.believe(STATEMENT)
        before = session.store.events()
        session.what_if(STATEMENT, STATEMENT)
        with pytest.raises(ProtocolError, match="did not roll back its state"):
            session.what_if(STATEMENT, STATEMENT)
        assert session.store.events() == before

    database = tmp_path / "what-if.sqlite3"
    first = SnarsSession.persistent(database, execute=FakeExecutor([_belief_record()]), budget=request_budget())

    # The what-if's batch: the first session records a belief while it runs.
    # am[verifies a-v2rs-kr-session-1020@53ac31]
    def what_if_batch(batch, budget):
        first.believe(STATEMENT)
        return tuple(_what_if_record())

    second = SnarsSession.persistent(database, execute=what_if_batch, budget=request_budget())
    try:
        answer = second.what_if(STATEMENT, STATEMENT)
        events = first.store.events()
    finally:
        first.close()
        second.close()

    assert answer.digest_before == answer.digest_after
    assert [event.kind for event in events] == ["belief"]

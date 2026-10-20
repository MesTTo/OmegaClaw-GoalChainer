"""Purpose: run non-skipped acceptance tests against the in-process SNARS executor and its
packaged SNARS library."""

from __future__ import annotations

from goal_chainer.snars_engine import run_snars_batch
from goal_chainer.snars_models import Evidence, EvidenceCounts
from goal_chainer.snars_program import SnarsBatch
from goal_chainer.snars_reasoner import SnarsSession
from request_support import budget
from reading_support import INCIDENT, incident_reader


# Evidence given no rate reaches SNARS at the rate the session's world configures, read from that
# world rather than written here, through a belief and an outcome; a rate given is applied as given.
# SNARS keeps the newest unit's rate, so the outcome leaves the stated statement at the default.
# am[verifies a-ev-br-tests-1017@bf0a6d] am[rests-on c-ev-snars-default-applies-1017@1fc3d2]
# am[rests-on c-ev-snars-rate-last-writer-1017@8b6dde]
def test_evidence_given_no_rate_reaches_snars_at_the_rate_its_world_configures() -> None:
    (configured,) = run_snars_batch(
        SnarsBatch((), frozenset({"policy"}), "(sn config default-rate)", INCIDENT),
        budget=budget(),
    ).output_lines
    unstated = '(sn p so "is" ((arg s (sn c "unstated")) (arg o (sn c "rate"))))'
    stated = '(sn p so "is" ((arg s (sn c "stated")) (arg o (sn c "rate"))))'
    with SnarsSession.ephemeral(budget=budget(), reader=incident_reader()) as session:
        given_none = session.believe(unstated, evidence=Evidence(2.0, 1.0), source="unstated")
        given = session.believe(stated, evidence=Evidence(2.0, 1.0, 0.7), source="stated")
        session.record_outcome(
            stated,
            evidence=Evidence(1.0, 0.0),
            source="goalchainer:execution",
            observation_id="obs-rate",
        )
        after_outcome = session.belief(stated)

    assert given_none.evidence.base_rate == float(configured)
    assert given.evidence.base_rate == 0.7
    assert after_outcome.evidence.base_rate == float(configured)


# A live session answers every reasoning and inspection operation it offers.
# am[verifies a-rt-snars-batch-speculative-1017@451056] am[verifies a-ie-s2c-scalar-tests-proofs-1018@5a0031]
def test_live_session_exposes_reasoning_and_inspection_surfaces() -> None:
    statement = (
        '(sn p so "is" '
        '((arg s (sn c "alpha")) (arg o (sn c "beta"))))'
    )
    pattern = (
        '(sn p so "is" '
        '((arg s (sn c "alpha")) (arg o $what)))'
    )
    with SnarsSession.ephemeral(budget=budget(), reader=incident_reader()) as session:
        belief = session.believe(
            statement,
            evidence=EvidenceCounts(2.0, 1.0, 0.5),
            source="acceptance",
            occurrence=1.0,
        )
        goal = session.register_goal(
            statement,
            owner="acceptance",
            kind="individual",
            desire=0.8,
            required=True,
            source="acceptance",
        )

        assert belief.receipts[0].source == "acceptance"
        assert session.ask(pattern).operation == "ask"
        assert session.prove(statement).operation == "prove"
        explanation = session.explain(statement)
        assert explanation.operation == "explain"
        assert explanation.payload[2][0] == "why"
        assert explanation.payload[2][1]
        assert explanation.payload[3][0] == "proof-trees"
        assert session.discover(pattern).operation == "discover"
        assert goal.desire == 0.8
        assert session.subgoals(statement).operation == "subgoals"
        assert session.temporal(statement, now=2.0).operation == "temporal"
        assert session.truth(statement).operation == "truth"
        assert session.control(1).operation == "control"
        assert session.structural().operation == "structural"
        assert session.transform(
            "marginal",
            statement,
            base_rate=0.7,
        ).operation == "transform"
        assert session.transform(
            "disjunction",
            statement,
            other_statement=statement,
        ).operation == "transform"
        assert session.compiled_prove(statement).operation == "compiled-prove"
        assert session.mine(2).operation == "mine"
        assert session.trust().operation == "trust"
        assert session.inspect().operation == "inspect"
        # am[verifies a-integrate-guard-metta-gate-1019@1bf9e1]
        guard = session.guard(
            "(safe redacted)",
            rules=("(safe redacted)",),
        )
        # Payload booleans are spelled as the engine prints them, True and False; the typed readers
        # also accept true and false.
        assert guard.payload[2] == ["proves", "True"]

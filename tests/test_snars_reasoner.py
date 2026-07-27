from __future__ import annotations

from types import SimpleNamespace

import pytest

from goal_chainer.models import CandidateAction
from goal_chainer.snars_models import (
    EvidenceCounts,
    EvidenceReceipt,
    SnarsActionAssessment,
    SnarsBelief,
    SnarsPettaExecutionError,
    SubjectiveOpinion,
)
from goal_chainer.snars_reasoner import (
    SnarsActionReasoner,
    SnarsOperation,
    SnarsSession,
)
from goal_chainer.snars_runtime import REPO_ROOT
from goal_chainer.snars_store import SnarsEventStore

COMMIT = "c" * 40
STATEMENT = (
    '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
)


class FakeRuntime:
    def __init__(self, outputs=(), error: Exception | None = None) -> None:
        self.diagnostics = SimpleNamespace(
            mettabase_dir=REPO_ROOT / "external" / "mettabase",
            mettabase_commit=COMMIT,
        )
        self.outputs = list(outputs)
        self.error = error
        self.programs: list[str] = []

    def run_batch(self, program: str):
        self.programs.append(program)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(output_lines=tuple(self.outputs.pop(0)))


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


def _belief(statement_id: str, expectation: float) -> SnarsBelief:
    uncertainty = 0.2
    belief = expectation - 0.1
    opinion = SubjectiveOpinion(
        belief,
        1.0 - belief - uncertainty,
        uncertainty,
        0.5,
    )
    return SnarsBelief(
        statement_id,
        STATEMENT,
        opinion,
        EvidenceCounts(6.0, 1.0, 0.5),
        (EvidenceReceipt(f"receipt-{statement_id}", "request", statement_id, 1.0),),
        (),
        ("request",),
    )


def _action() -> CandidateAction:
    return CandidateAction(
        id="publish_raw_log",
        label="raw",
        description="",
        satisfies=(),
        evidence_query="",
        evidence_atoms=(),
        default_strength=0.1,
    )


def test_successful_belief_is_appended_after_petta_returns() -> None:
    runtime = FakeRuntime([_belief_record()])
    with SnarsSession.ephemeral(runtime) as session:
        belief = session.believe(
            STATEMENT,
            evidence=EvidenceCounts(2.0, 1.0, 0.5),
            source="caller",
        )

        assert belief.opinion.expectation == pytest.approx(0.75)
        assert [event.kind for event in session.store.events()] == ["belief"]


def test_failed_mutation_does_not_append_an_event() -> None:
    runtime = FakeRuntime(
        error=SnarsPettaExecutionError("failed", details={"returncode": 1})
    )
    store = SnarsEventStore.memory(mettabase_commit=COMMIT)
    session = SnarsSession(runtime, store)

    with pytest.raises(SnarsPettaExecutionError):
        session.believe(STATEMENT)

    assert store.events() == ()
    session.close()


def test_persistent_replay_reconstructs_the_successful_belief(tmp_path) -> None:
    database = tmp_path / "snars.sqlite3"
    writer = FakeRuntime([_belief_record()])
    with SnarsSession.persistent(writer, database) as session:
        session.believe(
            STATEMENT,
            evidence=EvidenceCounts(2.0, 1.0, 0.5),
            source="caller",
        )

    reader = FakeRuntime([_belief_record()])
    with SnarsSession.persistent(reader, database) as session:
        replayed = session.belief(STATEMENT)

    assert replayed.statement_id == "sid-1"
    assert "(believe!" in reader.programs[0]
    assert '(source "caller")' in reader.programs[0]


def test_action_reasoner_projects_native_values_and_deontic_gate() -> None:
    assessment = SnarsActionAssessment(
        "publish_raw_log",
        _belief("acceptable", 0.3),
        _belief("risky", 0.8),
        _belief("forbidden", 0.7),
        0.2,
    )
    reasoner = SnarsActionReasoner(
        (assessment,),
        {"publish_raw_log": "forbidden"},
    )

    projection = reasoner.project(_action())

    assert projection.expectation == pytest.approx(0.3)
    assert projection.strength == pytest.approx(0.3)
    assert projection.confidence == pytest.approx(0.8)
    assert projection.opinion is assessment.acceptable.opinion
    assert projection.receipts == assessment.acceptable.receipts
    assert projection.deontic == "forbidden"
    assert projection.conflict_degree == 0.2


def test_action_reasoner_parses_metta_score_rows() -> None:
    assessment = SnarsActionAssessment(
        "publish_raw_log",
        _belief("acceptable", 0.3),
        _belief("risky", 0.8),
        _belief("forbidden", 0.7),
    )
    session = SimpleNamespace(
        score=lambda rows: SnarsOperation(
            "score",
            [
                "ranking",
                [
                    [
                        "DecisionRow",
                        "publish_raw_log",
                        0,
                        -1.0,
                        "blocked",
                        "forbidden",
                        0.3,
                        0.5,
                        0.5,
                        0.5,
                        1,
                        "coverage-expectation",
                    ]
                ],
                ["tied", ["publish_raw_log"]],
                ["automatic", "false"],
            ],
            "",
        )
    )
    reasoner = SnarsActionReasoner(
        (assessment,),
        {"publish_raw_log": "forbidden"},
        session=session,
    )

    verdicts = reasoner.score_rows([{"action_id": "publish_raw_log"}])

    assert verdicts == {
        "publish_raw_log": (-1.0, "blocked", "coverage-expectation")
    }


def test_redacted_ingestion_replays_only_the_prepared_payload(monkeypatch) -> None:
    runtime = FakeRuntime(
        [
            ["(goalchainer-snars-v1 inspect ok (inspection))"],
        ]
    )
    store = SnarsEventStore.memory(
        mettabase_commit=COMMIT,
        redactor=lambda kind, payload: {
            **payload,
            "text": "[redacted]",
            "facts": ["(hb tree redacted (sh-atom (tag C c NoRoles ()) \"safe\"))"],
        },
    )
    session = SnarsSession(runtime, store)
    fragments = SimpleNamespace(
        facts=("(hb tree raw (sh-atom (tag C c NoRoles ()) \"secret\"))",),
        effects=(),
    )
    monkeypatch.setattr(session.builder, "text_ingestion", lambda *args, **kwargs: fragments)

    session.ingest_text("secret")

    event = store.events()[0]
    assert event.payload["text"] == "[redacted]"
    assert "(hb tree raw " not in runtime.programs[0]
    assert "redacted" in runtime.programs[0]
    session.close()

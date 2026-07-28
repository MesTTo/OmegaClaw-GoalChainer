"""Non-skipped acceptance tests against the pinned PeTTa SNARS runtime."""

from __future__ import annotations

from goal_chainer.pipeline import solve_incident
from goal_chainer.snars_decision import native_decision_payload
from goal_chainer.snars_models import EvidenceCounts
from goal_chainer.snars_reasoner import SnarsSession
from goal_chainer.snars_runtime import SnarsRuntime

PRIVATE_REQUEST = (
    "Checkout is down. Raw logs include customer emails. "
    "Engineering needs the incident room."
)
PUBLIC_REQUEST = (
    "The logs contain public information and are safe to publish. "
    "Engineering needs the incident room."
)
UNVERIFIED_REQUEST = (
    "The facts are unverified. Engineering is still investigating the incident."
)
NEGATED_PUBLIC_REQUEST = (
    "The logs are not public. Engineering needs the incident room."
)


def _decision(payload, action_id):
    return next(
        row for row in payload["decisions"] if row["action_id"] == action_id
    )


def test_native_decision_differentials_and_counterfactual_rollback() -> None:
    private = native_decision_payload(PRIVATE_REQUEST)
    public = native_decision_payload(PUBLIC_REQUEST)
    unverified = native_decision_payload(UNVERIFIED_REQUEST)
    negated_public = native_decision_payload(NEGATED_PUBLIC_REQUEST)

    private_raw = _decision(private, "publish_raw_log")
    public_raw = _decision(public, "publish_raw_log")
    redacted = _decision(private, "publish_redacted_summary")

    assert private["native_snars_ran"] is True
    assert private_raw["status"] == "blocked"
    assert private_raw["norm_status"] == "forbidden"
    assert public_raw["status"] != "blocked"
    assert public_raw["norm_status"] == "permitted"
    assert negated_public["request_context"]["public"]["evidence"]["positive"] == 0
    assert (
        _decision(negated_public, "publish_raw_log")["evidence"]["counts"]["positive"]
        == 0
    )
    assert unverified["decisions"][0]["action_id"] == "hold_external_update"

    assert redacted["evidence"]["opinion"] is not None
    assert redacted["evidence"]["counts"]["positive"] > 0
    assert redacted["evidence"]["receipts"]
    assert redacted["evidence"]["native_proofs"]
    assert redacted["evidence"]["sources"]
    assert redacted["metadata"]["score_engine"] == "snars-metta-on-petta"
    assert redacted["metadata"]["score_formula"] == "motivation-expectation"

    counterfactual = private["counterfactual"]
    assert counterfactual["rolled_back"] is True
    assert counterfactual["digest_before"] == counterfactual["digest_after"]
    assert (
        counterfactual["opinion"]["expectation"]
        > private_raw["evidence"]["expectation"]
    )


def test_persistent_native_replay_is_structurally_identical(tmp_path) -> None:
    database = tmp_path / "snars.sqlite3"

    first = native_decision_payload(PRIVATE_REQUEST, store_path=database)
    second = native_decision_payload(PRIVATE_REQUEST, store_path=database)

    assert first["decisions"] == second["decisions"]
    assert first["assessments"] == second["assessments"]
    assert first["request_context"] == second["request_context"]
    assert first["state"]["digest"] == second["state"]["digest"]
    assert first["state"]["event_count"] == second["state"]["event_count"]


def test_native_solve_records_execution_outcome_and_trust_audit(tmp_path) -> None:
    report = solve_incident(
        PRIVATE_REQUEST,
        mode="native",
        store_path=tmp_path / "solve.sqlite3",
    )

    assert report["decided"] == "publish_redacted_summary"
    assert report["executed"]["leak_check"]["safe"] is True
    assert report["feedback"]["safe"] is True
    assert report["feedback"]["native_outcome"][0] == "outcome-audit"
    assert report["feedback"]["trust_before"][0] == "trust"
    assert report["feedback"]["trust_after"][0] == "trust"


def test_live_session_exposes_reasoning_and_inspection_surfaces() -> None:
    statement = (
        '(sn p so "is" '
        '((arg s (sn c "alpha")) (arg o (sn c "beta"))))'
    )
    pattern = (
        '(sn p so "is" '
        '((arg s (sn c "alpha")) (arg o $what)))'
    )
    runtime = SnarsRuntime()
    with SnarsSession.ephemeral(runtime) as session:
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
        guard = session.guard(
            "safe(redacted)",
            rules=("safe(redacted).",),
        )
        assert guard.payload[2] == ["proves", "true"]
        tied = session.score(
            [
                {
                    "action_id": action_id,
                    "order": order,
                    "deontic": "permitted",
                    "expectation": 0.5,
                    "goal_score": 0.5,
                    "individual_score": 0.5,
                    "collective_score": 0.5,
                    "motivation": None,
                    "missing_required_count": 0,
                }
                for order, action_id in enumerate(("a", "b"))
            ]
        )
        assert tied.payload[2] == ["tied", ["a", "b"]]
        assert tied.payload[3] == ["automatic", "false"]

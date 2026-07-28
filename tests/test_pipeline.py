from __future__ import annotations

import pytest

from goal_chainer import pipeline


def test_native_mode_is_the_default(monkeypatch) -> None:
    expected = {"mode": "native", "native_snars_ran": True}
    monkeypatch.delenv("GOALCHAINER_MODE", raising=False)
    monkeypatch.setattr(
        "goal_chainer.snars_decision.native_decision_payload",
        lambda request, store_path=None, execute=None, orchestrate=None: expected,
    )

    assert pipeline.decide_incident("request") is expected


def test_offline_mode_is_explicitly_labelled(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline,
        "_offline_decision",
        lambda request: {
            "request": request,
            "mode": "offline",
            "native_snars_ran": False,
        },
    )

    result = pipeline.decide_incident("request", mode="offline")

    assert result["mode"] == "offline"
    assert result["native_snars_ran"] is False


def test_invalid_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="native or offline"):
        pipeline.decide_incident("request", mode="automatic")


def test_solve_executes_inside_native_session_callback(monkeypatch) -> None:
    def decide(
        request,
        *,
        mode=None,
        store_path=None,
        execute=None,
        orchestrate=None,
    ):
        executed, orchestration = orchestrate(
            "publish_redacted_summary",
            {
                "publish_raw_log": "forbidden",
                "publish_redacted_summary": "obligated",
                "hold_external_update": "permitted",
            },
            execute,
        )
        return {
            "mode": "native",
            "native_snars_ran": True,
            "runtime": {"reasoner": "snars"},
            "state": {"kind": "ephemeral"},
            "decisions": [
                {
                    "action_id": "publish_redacted_summary",
                    "label": "Publish redacted summary",
                    "status": "recommended",
                }
            ],
            "motivation": None,
            "feedback": {"safe": True},
            "execution": executed,
            "orchestration": orchestration,
        }

    monkeypatch.setattr(pipeline, "decide_incident", decide)

    report = pipeline.solve_incident("request")

    assert report["decided"] == "publish_redacted_summary"
    assert report["executed"]["leak_check"]["safe"] is True
    assert report["feedback"] == {"safe": True}
    assert report["orchestration"]["outcome"] == "completed"

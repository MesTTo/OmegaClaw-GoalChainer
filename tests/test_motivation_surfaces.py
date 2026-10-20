"""Purpose: verify one recorded motivational cycle through the CLI, child skill process and readable
review, using the same native domain policy and durable stream as Python callers."""

from __future__ import annotations

import json
import sys

import pytest
from motivation_support import CORE, NEEDS, at
from request_support import CLI_LIMITS, LIMITS

import gcskill
from goal_chainer import cli
from goal_chainer.motivation import MotivationStore
from goal_chainer.motivation.requests import run_motivation_request
from goal_chainer.runtime.budget import RunBudget


# The host reports the attempt and observation explicitly; reviewing and rendering append neither.
# am[verifies a-v2-cli-skill-surface-1020@6f755c]
def test_cli_and_child_skill_share_the_stream_and_show_why_the_review_holds(tmp_path, capsys) -> None:
    domain = tmp_path / "companion.metta"
    domain.write_text(CORE + NEEDS, encoding="utf-8")
    database = tmp_path / "needs.sqlite3"
    selected = {"domain": {"path": str(domain)},
                "motivation": {"store": str(database), "stream": "companion"}}
    request_file = tmp_path / "request.json"

    # am[verifies a-v2-cli-skill-surface-1020@6f755c]
    def command(name, payload):
        request_file.write_text(json.dumps(payload), encoding="utf-8")
        status = cli.main([name, *CLI_LIMITS, "--input", str(request_file)])
        output = capsys.readouterr().out
        assert status == 0, output
        return json.loads(output)

    baseline = [{"need": need, "level": level, "scale": [0, 1], "estimator": "measured",
                 "source": "host:check-in", "observed_at": at(10).isoformat()}
                for need, level in (("nurture", 0.3), ("calm", 0.5))]
    observed = command("motivation", {**selected, "operation": "observe", "observations": baseline})
    assert len(observed["recorded"]) == 2 and observed["already_recorded"] == []

    attempt = {**selected, **LIMITS, "operation": "attempt",
               "attempts": [{"attempt": "host-1", "action": "empathize", "applied_at": at(20).isoformat()}]}
    applied = gcskill.call(sys.executable, "goalchainer-motivation-dispatch", json.dumps(attempt))
    assert applied["recorded"] == ["host-1"]
    repeated = gcskill.call(sys.executable, "goalchainer-motivation-dispatch", json.dumps(attempt))
    assert repeated["recorded"] == [] and repeated["already_recorded"] == ["host-1"]

    outcome = {**baseline[0], "level": 0.7, "observed_at": at(30).isoformat(), "produced_by": "host-1"}
    command("motivation", {**selected, "operation": "observe", "observations": [outcome]})
    status = gcskill.call(sys.executable, "goalchainer-motivation-dispatch", json.dumps(
        {**selected, **LIMITS, "operation": "status", "as_of": at(100).isoformat()}))
    learned = next(change for change in status["snapshot"]["changes"]
                   if (change["action"], change["need"]) == ("empathize", "nurture"))
    assert learned["state"] == "measured" and learned["count"] == 1
    assert learned["change"] == pytest.approx(0.4)

    with MotivationStore(database, stream="companion") as store:
        before = store.history()
    result = command("request", {**selected, "operation": "review", "context": {
        "review_id": "companion-turn", "subject": "companion", "trigger": "host-observation",
        "as_of": at(100).isoformat(), "authority": "advisory",
        "readings": [{"signal": "session_open", "state": "detected", "source": "host:session",
                      "estimator": "deterministic", "observed_at": at(100).isoformat()}],
    }})
    assert result["review"]["disposition"] == "hold"
    assert set(result["review"]["hold"]["satisfied"]) == {"nurture", "calm"}
    assert result["authorization"] == "unresolved" and result["applies_effects"] is False
    request_file.write_text(json.dumps(result), encoding="utf-8")
    assert cli.main(["show", "--input", str(request_file)]) == 0
    text = capsys.readouterr().out
    assert "disposition: hold" in text and "needs in their target bands:" in text
    assert "nurture: observed, level 0.7" in text
    with MotivationStore(database, stream="companion") as store:
        assert store.history() == before


# A freshness check reads the same stream at the packet's time; later observations do not
# change that snapshot, while a new observation inside it withdraws the earlier support.
# am[verifies a-v2-cli-freshness-stream-1020@14de3d]
def test_relevance_commands_read_the_named_stream_at_the_packet_time(tmp_path, capsys) -> None:
    domain = tmp_path / "companion.metta"
    domain.write_text(CORE + NEEDS, encoding="utf-8")
    database = tmp_path / "needs.sqlite3"
    selection = {"store": str(database), "stream": "companion"}
    configuration = tmp_path / "motivation.json"
    configuration.write_text(json.dumps(selection), encoding="utf-8")
    packet = tmp_path / "packet.json"
    packet.write_text(json.dumps({
        "protocol": "goalchainer-relevance-packet-v1", "review_id": "need-review",
        "subject": "companion", "trigger": "check-in", "as_of": at(100).isoformat(),
        "authority": "advisory", "budget": {"inferences": 1_000_000_000, "timeout_seconds": 300},
        "readings": [{"signal": "session_open", "state": "detected", "source": "host:session",
                      "estimator": "deterministic", "observed_at": at(0).isoformat()}],
    }), encoding="utf-8")
    saved_review = tmp_path / "review.json"
    arguments = ["--packet", str(packet), "--domain-file", str(domain), "--motivation", str(configuration)]

    # am[verifies a-v2-cli-freshness-stream-1020@14de3d]
    def observe(level, seconds):
        run_motivation_request({"operation": "observe", "domain": {"path": str(domain)},
                                "motivation": selection, "observations": [{
                                    "need": "nurture", "level": level, "scale": [0, 1], "estimator": "measured",
                                    "source": "host:check-in", "observed_at": at(seconds).isoformat()}]},
                               budget=RunBudget(inference_budget=1_000_000_000, timeout_seconds=300))

    # am[verifies a-v2-cli-freshness-stream-1020@14de3d]
    def command(operation, *, as_json=True):
        extra = ["--review", str(saved_review)] if operation == "check" else []
        status = cli.main(["relevance", operation, *arguments, *extra, *(["--json"] if as_json else [])])
        output = capsys.readouterr()
        return status, json.loads(output.out) if as_json else output

    observe(0.3, 10)
    status, reviewed = command("review")
    assert status == 0 and reviewed["motivation"]["stream"] == "companion"
    assert next(level for level in reviewed["motivation"]["levels"] if level["need"] == "nurture")["level"] == 0.3
    saved_review.write_text(json.dumps(reviewed), encoding="utf-8")
    status, fresh = command("check")
    assert status == 0 and fresh["status"] == "fresh" and fresh["motivation_changed"] is False
    assert cli.main(["relevance", "check", *arguments[:-2], "--review", str(saved_review), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid-motivation"
    observe(0.8, 150)
    assert command("check")[1]["status"] == "fresh"
    observe(0.7, 50)
    status, stale = command("check")
    assert status == 0 and stale["status"] == "stale" and stale["motivation_changed"] is True
    status, printed = command("check", as_json=False)
    assert status == 0 and "motivation changed" in printed.out

    missing = tmp_path / "absent.sqlite3"
    # The relevance commands answer every refusal of their motivation selection or its store in their
    # own vocabulary, invalid-motivation, where the motivation command family keeps the store's codes.
    # am[verifies a-v2-relevance-error-boundary-1020]
    for value in ({"store": str(missing), "stream": "companion"}, {"store": str(missing)}, []):
        configuration.write_text(json.dumps(value), encoding="utf-8")
        for operation in ("review", "check"):
            status, error = command(operation)
            assert status == 1 and error["error"]["code"] == "invalid-motivation"
        assert not missing.exists()

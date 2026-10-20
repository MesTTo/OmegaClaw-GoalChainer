"""Purpose: test explicit directive operations supplied as JSON to the command line."""

from __future__ import annotations

import json
import io
import sys
from request_support import CLI_LIMITS

from directive_support import AGENT, CHAIN, CHAIN_PLAN
from goal_chainer import cli
from goal_chainer.directive import create_plan


# The command line runs the caller's operation on the caller's plan: a task-state read, then a
# claim by the agent the request names.
# am[verifies a-ie-s6-directive-generic-1018@e69fb4]
# am[verifies a-integrate-request-budget-surface-1018@d6882c]
# am[verifies a-integrate-domain-surface-1018@759698]
def test_directive_cli_reads_and_changes_a_durable_plan(tmp_path, capsys) -> None:
    path = create_plan(tmp_path / "cli-plan.metta", CHAIN_PLAN)
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"operation": "task-state", "plan": str(path), "task": CHAIN[0]}))
    exit_code = cli.main(["directive", *CLI_LIMITS, "--input", str(request)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["operation"] == "task-state"
    assert payload["result"] == {"task": CHAIN[0], "state": "ready"}

    request.write_text(json.dumps({"operation": "claim", "plan": str(path), "task": CHAIN[0], "agent": AGENT}))
    exit_code = cli.main(["directive", *CLI_LIMITS, "--input", str(request)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["result"]["accepted"] is True
    assert f"(claims agent:{AGENT}" in path.read_text()


# The command line answers a refused request as a typed error and changes nothing: the retired demo
# operation, and a lifecycle change that names no agent.
# am[verifies a-ie-s6-directive-generic-1018@e69fb4] am[verifies a-integrate-directive-explicit-agent-1018@54e84d]
# am[verifies a-integrate-domain-surface-1018@759698]
def test_directive_cli_refuses_the_demo_and_an_unnamed_agent(tmp_path, monkeypatch, capsys) -> None:
    path = create_plan(tmp_path / "cli-refusal.metta", CHAIN_PLAN)
    for request in ({"operation": "demo"}, {"operation": "claim", "plan": str(path), "task": CHAIN[0]}):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
        exit_code = cli.main(["directive", *CLI_LIMITS])
        payload = json.loads(capsys.readouterr().out)

        assert exit_code == 1, request
        assert payload["ok"] is False and payload["error"]["code"] == "invalid_input", request
    assert path.read_text() == CHAIN_PLAN

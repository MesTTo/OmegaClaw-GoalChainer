"""Purpose: verify the SNARS command's structured results and typed CLI failures."""

from __future__ import annotations

import json
import pytest

from goal_chainer import cli
from goal_chainer.errors import DependencyUnavailableError
from request_support import CLI_LIMITS, LIMITS


# am[verifies a-integrate-guard-metta-gate-1019@1bf9e1]
@pytest.mark.parametrize("goal,exit_code", [("(safe redacted)", 0), ("safe(redacted)", 1)])
def test_guard_cli_accepts_metta_terms_and_refuses_prolog_text(goal, exit_code, capsys):
    assert cli.main(["snars", *CLI_LIMITS, "guard", "--guard-rule", "(safe redacted)",
                     "--guard-goal", goal, "--json"]) == exit_code
    payload = json.loads(capsys.readouterr().out)
    if exit_code:
        assert payload["error"]["code"] == "invalid_input"
    else:
        assert payload["result"]["payload"][2] == ["proves", "True"]


# The command hands run_snars_command the one budget its bounded flags built.
# am[verifies a-rt-rbr-snars-envelope-1018@920fe4]
def test_snars_command_emits_structured_json(monkeypatch, capsys) -> None:
    budgets = []
    monkeypatch.setattr(
        cli,
        "run_snars_command",
        lambda args, *, budget: budgets.append(budget) or {
            "operation": args.operation,
            "mode": "native",
            "native_snars_ran": True,
            "state": {"kind": "ephemeral"},
            "result": {"rows": []},
        },
    )

    exit_code = cli.main(["snars", *CLI_LIMITS, "inspect", "--request", "", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["operation"] == "inspect"
    assert [(budget.inference_budget, budget.timeout_seconds) for budget in budgets] == [
        (LIMITS["inference_budget"], LIMITS["timeout_seconds"])
    ]
    assert payload["native_snars_ran"] is True


# am[verifies a-integrate-cli-typed-errors-1018@160cf8]
def test_native_failure_is_nonzero_with_stable_json_error(monkeypatch, capsys) -> None:
    def fail(argv):
        raise DependencyUnavailableError(
            "Mettabase is missing.",
            details={"path": "/missing"},
        )

    monkeypatch.setattr(cli, "_main", fail)

    exit_code = cli.main(["snars", "inspect", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload == {
        "ok": False,
        "error": {
            "code": "dependency_unavailable",
            "message": "Mettabase is missing.",
            "details": {"path": "/missing"},
        },
    }

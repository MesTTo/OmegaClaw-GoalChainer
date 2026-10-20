"""Purpose: verify that motivation requests cross the CLI and skill boundaries unchanged, under
one explicit budget, and that refusals keep their typed JSON representation."""

from __future__ import annotations

import io
import json
import sys
from types import ModuleType

import pytest

import gcskill
from goal_chainer import cli, omegaclaw_skill
from goal_chainer.errors import InvalidInputError, PersistenceError

LIMITS = {"inference_budget": 100, "timeout_seconds": 30}
CLI_LIMITS = ["--inference-budget", "100", "--timeout-seconds", "30"]
SKILL = "goalchainer-motivation-dispatch"


# am[verifies a-v2-cli-skill-surface-1020@6f755c]
@pytest.fixture
def request_entry(monkeypatch):
    module = ModuleType("goal_chainer.motivation.requests")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module


# Each boundary carries the same operation and result; no observation or attempt is invented.
# am[verifies a-v2-cli-skill-surface-1020@6f755c]
@pytest.mark.parametrize("operation", ["observe", "attempt", "status"])
def test_motivation_command_and_skill_preserve_the_operation_and_one_budget(
    request_entry, operation, tmp_path, capsys, monkeypatch,
):
    payload = {"operation": operation, "domain": {"path": "companion.metta"},
               "motivation": {"store": "needs.db", "stream": "companion"}}
    answer = {"protocol": "goalchainer-motivation-request-v1", "operation": operation,
              "recorded": [], "already_recorded": ["existing"]}
    budgets = []

    # am[verifies a-v2-cli-skill-surface-1020@6f755c]
    def run(payload_in, *, budget):
        assert payload_in == payload
        assert budget.inference_budget == LIMITS["inference_budget"]
        assert budget.timeout_seconds == LIMITS["timeout_seconds"]
        budgets.append(budget)
        return answer

    request_entry.run_motivation_request = run
    saved = tmp_path / "request.json"
    saved.write_text(json.dumps(payload), encoding="utf-8")
    assert cli.main(["motivation", *CLI_LIMITS, "--input", str(saved)]) == 0
    assert json.loads(capsys.readouterr().out) == answer
    assert omegaclaw_skill.run_skill(SKILL, json.dumps({**payload, **LIMITS})) == {"skill": SKILL, **answer}
    assert len(budgets) == 2 and budgets[0] is not budgets[1]
    monkeypatch.setattr(gcskill, "call", lambda python, name, request: (
        {"skill": name, **answer} if name == SKILL and json.loads(request) == payload else None))
    assert json.loads(gcskill.motivation_dispatch("python", json.dumps(payload))) == {"skill": SKILL, **answer}


# am[verifies a-v2-cli-skill-surface-1020@6f755c]
@pytest.mark.parametrize("error", [InvalidInputError("bad observation"), PersistenceError("conflicting attempt")])
def test_motivation_refusal_keeps_its_code_and_details(request_entry, error, tmp_path, capsys):
    # am[verifies a-v2-cli-skill-surface-1020@6f755c]
    def refuse(payload, *, budget):
        raise error

    request_entry.run_motivation_request = refuse
    saved = tmp_path / "request.json"
    saved.write_text("{}", encoding="utf-8")
    assert cli.main(["motivation", *CLI_LIMITS, "--input", str(saved)]) == 1
    expected = {"ok": False, "error": error.to_dict()}
    assert json.loads(capsys.readouterr().out) == expected
    assert omegaclaw_skill.main([SKILL, "--request", json.dumps(LIMITS)]) == 1
    assert json.loads(capsys.readouterr().out) == expected


# A refusal before dispatch must not load or call the writer.
# am[verifies a-v2-cli-skill-surface-1020@6f755c]
@pytest.mark.parametrize("written", ["{", "[]", "null"])
def test_malformed_motivation_json_never_reaches_the_writer(request_entry, written, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(written.encode("utf-8"))))
    assert cli.main(["motivation", *CLI_LIMITS]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_input"
    assert omegaclaw_skill.main([SKILL, "--request", written]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_input"


# am[verifies a-v2-cli-skill-surface-1020@6f755c]
def test_motivation_limits_are_required_before_dispatch(request_entry, tmp_path, capsys):
    saved = tmp_path / "request.json"
    saved.write_text("{}", encoding="utf-8")
    for flag in ([], ["--inference-budget", "1"], ["--timeout-seconds", "1"]):
        with pytest.raises(SystemExit) as caught:
            cli.main(["motivation", "--input", str(saved), *flag])
        assert caught.value.code == 2
    with pytest.raises(InvalidInputError, match="inference_budget"):
        omegaclaw_skill.run_skill(SKILL, "{}")
    assert cli.main(["motivation", "--input", str(saved), "--inference-budget", "0", "--timeout-seconds", "1"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_input"

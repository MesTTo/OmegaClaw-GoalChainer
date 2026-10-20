"""Purpose: verify explicit limits, unchanged payloads, typed failures and one allowance across public request boundaries."""

import io
import json
import sys
from types import ModuleType

import pytest

from goal_chainer import cli, omegaclaw_skill as skill
from goal_chainer.errors import InvalidInputError
from goal_chainer.relevance.errors import ERROR_CODES, RelevanceError
from goal_chainer.runtime.budget import InferenceBudgetExceeded, RunBudget

SKILLS = tuple(skill.DISPATCH)
LIMITS = {"inference_budget": 100, "timeout_seconds": 30}


# Every request transport preserves the relevance code, including errors after native work.
# am[verifies a-v2-unified-error-family-1020@c7807b]
@pytest.mark.parametrize("code", sorted(ERROR_CODES))
@pytest.mark.parametrize("entry", ["request", "motivation", *SKILLS])
def test_relevance_failure_is_json_at_each_request_boundary(monkeypatch, capsys, code, entry):
    failure = RelevanceError(code, "The request cannot produce a result.", details={"subject": "task-1"})

    # am[verifies a-v2-unified-error-family-1020@c7807b]
    def refuse(*args, **kwargs):
        raise failure

    if entry in SKILLS:
        monkeypatch.setitem(skill.DISPATCH, entry, refuse)
        status = skill.main([entry, "--request", json.dumps(LIMITS)])
    else:
        module_name = "goal_chainer.requests" if entry == "request" else "goal_chainer.motivation.requests"
        function = "run_request" if entry == "request" else "run_motivation_request"
        module = ModuleType(module_name)
        setattr(module, function, refuse)
        monkeypatch.setitem(sys.modules, module_name, module)
        monkeypatch.setattr(cli, "_read_payload", lambda path: {})
        status = cli.main([entry, "--inference-budget", "100", "--timeout-seconds", "30"])
    captured = capsys.readouterr()
    assert status == 1
    assert captured.err == ""
    assert json.loads(captured.out) == {"ok": False, "error": failure.to_dict()}


# The malformed timestamp travels through the real request parser, not an injected exception.
# am[verifies a-v2-unified-error-family-1020@c7807b]
@pytest.mark.parametrize("entry", ["cli", "skill"])
def test_invalid_review_context_returns_json_from_the_public_entry(monkeypatch, capsys, entry):
    payload = {
        "operation": "review", "domain": {"packaged": "task-control"},
        "context": {"review_id": "r1", "subject": "s", "trigger": "t", "as_of": "yesterday",
                    "authority": "advisory", "readings": []},
    }
    if entry == "cli":
        monkeypatch.setattr(cli, "_read_payload", lambda path: payload)
        status = cli.main(["request", "--inference-budget", "100000000", "--timeout-seconds", "30"])
    else:
        status = skill.main(["goalchainer-request", "--request", json.dumps({
            **payload, "inference_budget": 100000000, "timeout_seconds": 30,
        })])
    captured = capsys.readouterr()
    assert status == 1
    assert captured.err == ""
    answer = json.loads(captured.out)
    assert answer["ok"] is False
    assert answer["error"]["code"] == "invalid-packet"
    assert answer["error"]["message"] == "as_of must be an ISO-8601 time, got 'yesterday'"


# am[verifies a-integrate-cli-typed-errors-1018@160cf8]
def test_error_after_work_preserves_the_error_without_inventing_execution_history(monkeypatch, capsys):
    budget = RunBudget(inference_budget=10, timeout_seconds=30)

    # am[verifies a-integrate-cli-typed-errors-1018@160cf8]
    def request(argv):
        budget.charge(11)
        budget.remaining()

    monkeypatch.setattr(cli, "_main", request)
    assert cli.main(["request"]) == 1
    assert budget.spent == 11
    assert json.loads(capsys.readouterr().out) == {
        "ok": False, "error": InferenceBudgetExceeded(10, 11).to_dict(),
    }


# am[verifies a-integrate-domain-surface-1018@759698]
@pytest.mark.parametrize("name", SKILLS)
def test_skill_preserves_payload_and_constructs_one_explicit_budget(monkeypatch, name):
    operation = {"operation": "plan", "reading": {"text": "  original\nwords  "}, "context": {"readings": []}}
    seen = []

    # am[verifies a-integrate-domain-surface-1018@759698]
    def dispatch(payload, *, budget):
        seen.append((payload, budget))
        budget.charge(7)
        return {"spent": budget.spent}

    monkeypatch.setitem(skill.DISPATCH, name, dispatch)
    answer = skill.run_skill(name, json.dumps({**operation, **LIMITS}))
    assert answer == {"spent": 7}
    assert len(seen) == 1
    payload, budget = seen[0]
    assert payload == operation
    assert isinstance(budget, RunBudget)
    assert budget.inference_budget == 100
    assert 0 < budget.remaining()[1] <= 30


# am[verifies a-integrate-domain-surface-1018@759698]
@pytest.mark.parametrize("name", SKILLS)
@pytest.mark.parametrize("field,value", [
    ("inference_budget", None), ("inference_budget", True),
    ("inference_budget", 0), ("inference_budget", -1),
    ("inference_budget", 1.5), ("inference_budget", "100"),
    ("timeout_seconds", None), ("timeout_seconds", False),
    ("timeout_seconds", 0), ("timeout_seconds", -1),
    ("timeout_seconds", float("inf")), ("timeout_seconds", float("nan")),
])
def test_bad_limits_are_rejected_before_dispatch(monkeypatch, name, field, value):
    # am[verifies a-integrate-domain-surface-1018@759698]
    def forbidden(*args, **kwargs):
        pytest.fail("invalid limits reached the operation")

    monkeypatch.setitem(skill.DISPATCH, name, forbidden)
    packet = {"operation": "plan", **LIMITS, field: value}
    with pytest.raises(InvalidInputError):
        skill.run_skill(name, json.dumps(packet))


# The operation owns its fields; the envelope owns only its two limits.
# am[verifies a-integrate-domain-surface-1018@759698]
@pytest.mark.parametrize("name", SKILLS)
@pytest.mark.parametrize("packet", [
    "not JSON", "null", "[]", "{}",
    '{"operation":"plan","inference_budget":100}',
    '{"operation":"plan","timeout_seconds":30}',
])
def test_envelope_requires_an_object_and_both_limits(monkeypatch, name, packet):
    # am[verifies a-integrate-domain-surface-1018@759698]
    def forbidden(*args, **kwargs):
        pytest.fail("malformed input reached the operation")

    monkeypatch.setitem(skill.DISPATCH, name, forbidden)
    with pytest.raises(InvalidInputError):
        skill.run_skill(name, packet)


# am[verifies a-integrate-domain-surface-1018@759698]
@pytest.mark.parametrize("command", [["request"], ["directive"], ["snars", "ask"]])
@pytest.mark.parametrize("flags", [[], ["--inference-budget", "100"], ["--timeout-seconds", "30"]])
def test_cli_requires_both_limits_before_reasoning(command, flags):
    with pytest.raises(SystemExit) as error:
        cli.main([*command, *flags])
    assert error.value.code == 2


# The fake operation isolates transport; real domain composition has its own integration tests.
# am[verifies a-integrate-domain-surface-1018@759698]
# am[verifies a-integrate-budget-stdin-fixture-1019@931549]
@pytest.mark.parametrize("command", ["request", "directive"])
@pytest.mark.parametrize("source", ["stdin", "file"])
def test_cli_passes_unmodified_json_and_its_one_budget(monkeypatch, capsys, tmp_path, command, source):
    payload = {"operation": "plan", "reading": {"text": "  unmodified\nrequête  "}}
    seen = []

    # am[verifies a-integrate-domain-surface-1018@759698]
    def operation(value, *, budget):
        seen.append((value, budget))
        budget.charge(7)
        return {"spent": budget.spent}

    module = ModuleType("goal_chainer.requests")
    module.run_request = operation
    monkeypatch.setitem(sys.modules, "goal_chainer.requests", module)
    monkeypatch.setattr(cli, "run_directive_request", operation)
    text = json.dumps(payload, ensure_ascii=False)
    path = "-"
    if source == "file":
        file = tmp_path / "request.json"
        file.write_text(text, encoding="utf-8")
        path = str(file)
    else:
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(text.encode("utf-8")), encoding="utf-8"))
    assert cli.main([command, "--input", path, "--inference-budget", "100",
                     "--timeout-seconds", "30"]) == 0
    assert json.loads(capsys.readouterr().out) == {"spent": 7}
    assert len(seen) == 1
    assert seen[0][0] == payload
    assert seen[0][1].inference_budget == 100 and seen[0][1].spent == 7


# am[verifies a-integrate-domain-surface-1018@759698]
# am[verifies a-integrate-budget-stdin-fixture-1019@931549]
@pytest.mark.parametrize("text,message", [
    ("{", "Cannot read JSON input:"),
    ("null", "The JSON input must be an object."),
    ("[]", "The JSON input must be an object."),
])
def test_cli_invalid_json_returns_a_typed_error(monkeypatch, capsys, text, message):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(text.encode("utf-8")), encoding="utf-8"))
    assert cli.main(["request", "--inference-budget", "100", "--timeout-seconds", "30"]) == 1
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "invalid_input"
    assert error["message"].startswith(message)


# A callee returning after exhaustion cannot turn the overrun into success.
# am[verifies a-integrate-domain-surface-1018@759698]
@pytest.mark.parametrize("name", SKILLS)
def test_skill_checks_the_same_budget_after_dispatch(monkeypatch, name):
    seen = []

    # am[verifies a-integrate-domain-surface-1018@759698]
    def overspend(payload, *, budget):
        seen.append(budget)
        budget.charge(101)
        return {"ok": True}

    monkeypatch.setitem(skill.DISPATCH, name, overspend)
    with pytest.raises(InferenceBudgetExceeded):
        skill.run_skill(name, json.dumps({"operation": "plan", **LIMITS}))
    assert len(seen) == 1 and seen[0].spent == 101

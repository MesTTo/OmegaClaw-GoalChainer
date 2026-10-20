"""Purpose: verify unambiguous JSON, typed guard arrays and consistent relevance command failures."""

import json
from types import SimpleNamespace

import pytest
from hypothesis import given, strategies as st

from goal_chainer import cli, omegaclaw_skill as skill, relevance_cli, snars_cli
from goal_chainer.errors import InvalidInputError, PersistenceError
from goal_chainer.relevance.errors import RelevanceError
from goal_chainer.runtime.budget import InferenceBudgetExceeded, ReviewTimeout, RunBudget


# am[verifies a-v2-json-input-1020@b37a9e]
@pytest.mark.parametrize("body", [
    '"operation":"status","operation":"observe"',
    '"inference_budget":1,"inference_budget":1000000000',
    '"nested":{"source":"a","source":"b"}',
    '"nested":[{"source":"a","sou\\u0072ce":"b"}]',
    *[f'"nested":[{{"value":{value}}}]' for value in ("NaN", "Infinity", "-Infinity", "1e999", "-1e999")],
])
@pytest.mark.parametrize("entry", ["cli", "skill", "relevance"])
def test_ambiguous_or_nonfinite_json_is_refused_before_dispatch(body, entry, monkeypatch):
    written = '{"inference_budget":100,"timeout_seconds":30,' + body + '}'
    monkeypatch.setattr(cli, "input_text", lambda *args: written)
    monkeypatch.setattr(relevance_cli, "input_text", lambda *args: written)
    with pytest.raises((InvalidInputError, RelevanceError)) as caught:
        if entry == "cli":
            cli._read_payload("input.json")
        elif entry == "skill":
            skill._bounded_request(written)
        else:
            relevance_cli._read_json("packet.json", "invalid-packet")
    assert caught.value.code == ("invalid-packet" if entry == "relevance" else "invalid_input")


JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | st.text(),
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=20,
)


# am[verifies a-v2-json-input-1020@b37a9e]
@given(JSON_VALUES)
def test_each_reader_preserves_valid_json_values(value):
    payload = {"data": value}
    with pytest.MonkeyPatch.context() as patch:
        written = json.dumps(payload, allow_nan=False)
        patch.setattr(cli, "input_text", lambda *args: written)
        patch.setattr(relevance_cli, "input_text", lambda *args: written)
        assert cli._read_payload("input.json") == payload
        assert relevance_cli._read_json("packet.json", "invalid-packet") == payload
    decoded, _budget = skill._bounded_request(json.dumps({
        **payload, "inference_budget": 100, "timeout_seconds": 30,
    }, allow_nan=False))
    assert decoded == payload


# am[verifies a-v2-snars-dispatch-input-1020@a10217]
@pytest.mark.parametrize("rules", [None, 5, True, "(allowed alice)", {"(allowed alice)": True}, [None], [5], [[]]])
def test_guard_rules_must_be_an_array_of_text_before_a_session_opens(rules, monkeypatch):
    called = []
    monkeypatch.setattr(snars_cli, "run_snars_command", lambda *args, **kwargs: called.append(args) or {})
    with pytest.raises(InvalidInputError, match="guard_rules"):
        snars_cli.run_snars_request({
            "group": "trust-discovery", "operation": "guard", "guard_goal": "(allowed alice)",
            "guard_rules": rules,
        }, budget=RunBudget(inference_budget=100, timeout_seconds=30))
    assert called == []


# am[verifies a-v2-snars-dispatch-input-1020@a10217]
@pytest.mark.parametrize("fields", [{}, {"guard_rules": []}, {"guard_rules": ["(allowed alice)", "(:- (safe $x) (allowed $x))"]}])
def test_guard_rule_arrays_pass_unchanged_to_the_shared_command(fields, monkeypatch):
    seen = []
    monkeypatch.setattr(snars_cli, "run_snars_command", lambda args, **kwargs: seen.append(args.guard_rules) or {})
    snars_cli.run_snars_request({
        "group": "trust-discovery", "operation": "guard", "guard_goal": "(allowed alice)", **fields,
    }, budget=RunBudget(inference_budget=100, timeout_seconds=30))
    assert seen == [fields.get("guard_rules", [])]


# am[verifies a-v2-relevance-error-boundary-1020@bd1acf]
@pytest.mark.parametrize("failure,code", [
    (InvalidInputError("bad stream", details={"field": "stream"}), "invalid-motivation"),
    (PersistenceError("missing store", details={"path": "absent.db"}), "invalid-motivation"),
    (ReviewTimeout(0.5), "review-timeout"),
    (InferenceBudgetExceeded(10, 11), "review-budget-exceeded"),
])
@pytest.mark.parametrize("operation", ["review", "check"])
@pytest.mark.parametrize("as_json", [False, True])
def test_relevance_motivation_failures_use_the_relevance_contract(failure, code, operation, as_json, monkeypatch, capsys):
    from goal_chainer.motivation import requests

    budget = RunBudget(inference_budget=100, timeout_seconds=30)
    packet = SimpleNamespace(as_of=None, budget=SimpleNamespace(run_budget=lambda: budget))
    monkeypatch.setattr(relevance_cli, "parse_packet", lambda value: packet)
    monkeypatch.setattr(relevance_cli, "_read_json", lambda *args: {})
    monkeypatch.setattr(relevance_cli, "_domain", lambda *args: None)

    # am[verifies a-v2-relevance-error-boundary-1020@bd1acf]
    def refuse(*args, **kwargs):
        raise failure

    monkeypatch.setattr(requests, "stream_snapshot", refuse)
    arguments = ["relevance", operation, "--packet", "packet.json", "--motivation", "stream.json"]
    if operation == "check":
        arguments += ["--review", "review.json"]
    assert cli.main([*arguments, *(["--json"] if as_json else [])]) == 1
    output = capsys.readouterr()
    if as_json:
        error = json.loads(output.out)["error"]
        assert error["code"] == code and output.err == ""
        assert error["details"] == dict(failure.details)
    else:
        assert output.out == ""
        assert output.err.startswith(f"goalchainer relevance error [{code}]: ")

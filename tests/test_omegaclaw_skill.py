"""Purpose: verify the OmegaClaw skill prompt and typed dispatch results without rewriting their meaning."""

import io
import json
import sys
from types import ModuleType

import pytest

import gcskill
from goal_chainer import omegaclaw_skill as skill
from goal_chainer.errors import InvalidInputError

LIMITS = {"inference_budget": 100, "timeout_seconds": 30}


# am[verifies a-integrate-domain-surface-1018@759698]
# am[verifies a-v2-cli-skill-surface-1020@6f755c]
def test_system_prompt_names_domain_reading_and_separate_execution_authority():
    payload = skill.run_skill("goalchainer-system-prompt", "")
    assert payload == {"skill": "goalchainer-system-prompt", "prompt": skill.SYSTEM_PROMPT}
    for requirement in ("domain", "reading.text", "original words", "inference_budget",
                        "timeout_seconds", "do not authorize execution", "goalchainer-motivation-dispatch",
                        "a review never records an attempt"):
        assert requirement in payload["prompt"]


# A returned planning distinction crosses both Python entry points without being flattened.
# am[verifies a-integrate-domain-surface-1018@759698]
@pytest.mark.parametrize("answer", [
    {"planning": {"type": "Inquiry", "literal": "s"}},
    {"admission": {"type": "Stale", "expected": "a", "found": "b"}},
    {"admission": {"type": "Ambiguous", "classes": 2}},
    {"planning": {"type": "Plan", "steps": []}, "authorization": "unresolved"},
])
def test_domain_skill_and_host_preserve_the_structured_answer(monkeypatch, answer):
    request = {"operation": "plan", "domain": {"packaged": "example"}}
    module = ModuleType("goal_chainer.requests")

    # am[verifies a-integrate-domain-surface-1018@759698]
    def run_request(payload, *, budget):
        assert payload == request
        assert budget.inference_budget == 100
        return answer

    module.run_request = run_request
    monkeypatch.setitem(sys.modules, "goal_chainer.requests", module)
    result = skill.run_skill("goalchainer-request", json.dumps({**request, **LIMITS}))
    assert result == {"skill": "goalchainer-request", **answer}
    monkeypatch.setattr(gcskill, "call", lambda *args: result)
    assert json.loads(gcskill.request("python", json.dumps(request))) == result


# am[verifies a-integrate-domain-surface-1018@759698]
@pytest.mark.parametrize("kind", ["snars", "directive"])
def test_dispatch_passes_its_typed_operation_and_budget(monkeypatch, kind):
    operation = {"operation": "inspect", "group": "trust-discovery"}
    seen = []

    # am[verifies a-integrate-domain-surface-1018@759698]
    def dispatch(payload, *, budget):
        seen.append((payload, budget))
        return {"operation": payload["operation"], "result": ["unchanged"]}

    monkeypatch.setattr(skill, "run_" + kind + "_request", dispatch)
    result = skill.run_skill("goalchainer-" + kind + "-dispatch", json.dumps({**operation, **LIMITS}))
    assert result == {"skill": "goalchainer-" + kind + "-dispatch",
                      "operation": "inspect", "result": ["unchanged"]}
    assert len(seen) == 1
    assert seen[0][0] == operation and seen[0][1].inference_budget == 100


# am[verifies a-integrate-domain-surface-1018@759698]
# am[verifies a-v2-cli-skill-surface-1020@6f755c]
@pytest.mark.parametrize("name", list(skill.DISPATCH))
def test_malformed_skill_json_is_a_typed_error(name):
    with pytest.raises(InvalidInputError, match="valid JSON"):
        skill.run_skill(name, "{")


# am[verifies a-integrate-domain-surface-1018@759698]
def test_skill_process_prints_typed_input_failure(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"{"), encoding="utf-8"))
    assert skill.main(["goalchainer-request", "--request-file", "-"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_input"


# am[verifies a-integrate-domain-surface-1018@759698]
def test_skill_process_reports_an_unreadable_input_file(tmp_path, capsys):
    assert skill.main(["goalchainer-request", "--request-file", str(tmp_path / "missing.json")]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_input"


# A JSON integer can have any number of digits; a timeout no finite float holds is the skill's
# typed refusal before anything runs, where isfinite() raised OverflowError.
# am[verifies a-rt-nr-repair-1018@72901e]
def test_a_skill_timeout_beyond_the_float_range_is_a_typed_refusal():
    request = {"group": "trust-discovery", "operation": "trust", "inference_budget": 1_000, "timeout_seconds": 10**400}
    with pytest.raises(InvalidInputError, match="timeout_seconds must be a finite positive number"):
        skill.run_skill("goalchainer-snars-dispatch", json.dumps(request))


# json.loads raises a plain ValueError for an integer longer than the interpreter reads and
# RecursionError for nesting deeper than its parser reaches; each is the request's typed refusal, in
# the skill and in its process.
# am[verifies a-rt-rr-json-read-1018@305497]
@pytest.mark.parametrize("request_text", [
    '{"inference_budget": 1' + "0" * 5000 + ', "timeout_seconds": 5}',
    '{"inference_budget": 1000, "timeout_seconds": 1' + "0" * 5000 + "}",
    '{"inference_budget": 1000, "timeout_seconds": 5, "operation": ' + "[" * 100_000 + "]" * 100_000 + "}",
], ids=["inference budget of 5001 digits", "timeout of 5001 digits", "nested 100000 deep"])
def test_a_request_json_cannot_read_is_a_typed_refusal(monkeypatch, capsys, request_text):
    with pytest.raises(InvalidInputError, match="valid JSON"):
        skill.run_skill("goalchainer-snars-dispatch", request_text)

    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(request_text.encode()), encoding="utf-8"))
    assert skill.main(["goalchainer-snars-dispatch", "--request-file", "-"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_input"


# The same bytes mean the same request even when stdin's text decoder uses another locale.
# am[verifies a-v2-skill-utf8-1020@3763d0]
@pytest.mark.parametrize("encoding", ["ascii", "latin-1", "utf-8"])
@pytest.mark.parametrize("raw", [b'{"text":"\xff"}', '{"text":"requête"}'.encode()])
def test_skill_reads_utf8_bytes_independently_of_stdin_locale(monkeypatch, capsys, encoding, raw):
    seen = []

    # am[verifies a-v2-skill-utf8-1020@3763d0]
    def dispatch(name, request):
        seen.append(json.loads(request))
        return {"received": seen[-1]}

    monkeypatch.setattr(skill, "run_skill", dispatch)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding=encoding, errors="surrogateescape"))
    status = skill.main(["goalchainer-request", "--request-file", "-"])
    answer = json.loads(capsys.readouterr().out)
    if b"\xff" in raw:
        assert status == 1 and seen == []
        assert answer["error"]["code"] == "invalid_input"
        assert "UTF-8" in answer["error"]["message"]
    else:
        assert status == 0
        assert seen == [{"text": "requête"}]

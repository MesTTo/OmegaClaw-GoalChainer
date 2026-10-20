"""Purpose: test the hackathon recorders against GoalChainer's real skill process and request
command. The live terminal demo runs through the stock Omega loop driver with a scripted Codex and no
hosted call: it opens with the stock provider self-test and stops when Codex is logged out, gives
Codex GoalChainer's system prompt through the plugin's prompt extension and only the loop's tools,
shows the terminal exactly the JSON each skill returned, framing only the answer the loop names as
a skill's and never text the agent or the user writes, however it reads, runs goalchainer-request
only with the run's own request, refusing any other unrun, counts the request only when it returned
a result, refuses an answer before it, and prints its completion line only after an answer that
follows it.
The renderer shows a skill's JSON as it is, and the audit recorder shows its request file, the
review the request command computes from it and that same review's recorded provenance, with
nothing from another checkout."""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from omega_support import (FORGED, INCIDENT, LOOKALIKES, LOOP, admitted, changing, evaluated, json_turn, module,
                           scripted_tree, shown_request, stock_core)
from request_support import CLI_LIMITS, review_request

import gcskill
from goal_chainer import cli, omegaclaw_skill
from goal_chainer.planning.procedures import SignalLiteral
from goal_chainer.planning.projection import Ambiguous, Blocked, Inquiry, NoPlan, Plan, Stale, Unsolved
from goal_chainer.planning.transport import encode
from goal_chainer.requests import REQUEST_PROTOCOL

ROOT = Path(__file__).resolve().parents[1]
RECORDERS = ROOT / "hackathon/video/scripts/recorders"
DEMO = RECORDERS / "live-terminal-full-demo.sh"
COMPLETE = "Terminal demo complete."
REFUSED = "(send refused: goalchainer-request has not returned a result)"
REFUSAL = "goalchainer-request refused, not evaluated: its argument"
AT = json.loads(review_request(INCIDENT))["context"]["as_of"]
NO_READINGS = {"ok": False, "error": {"code": "invalid_input", "details": {},
                                      "message": "The selected domain declares no semantic readings."}}


# The renderer loads from the recorder's own directory, as the recorder imports it.
# am[verifies a-cd-rec-render-1018@3743ce]
def _renderer() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("goalchainer_render", RECORDERS / "goalchainer_render.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Every planner answer and admission verdict the request skill can return, as the transport
# encodes it, and the refusal object the skill process prints.
RESULTS = {
    "inquiry": {"skill": "goalchainer-request", "planning": encode(Inquiry(
        SignalLiteral("owner_mismatch"), "owner-registry", Plan((), True), NoPlan((), None)))},
    "no-plan": {"skill": "goalchainer-request", "planning": encode(NoPlan(
        (Unsolved(SignalLiteral("owner_mismatch"), "no-way"),), None))},
    "stale": {"skill": "goalchainer-request", "admission": encode(Stale("expected-digest", "found-digest"))},
    "ambiguous": {"skill": "goalchainer-request", "admission": encode(Ambiguous(2))},
    "blocked": {"skill": "goalchainer-request", "admission": encode(Blocked((SignalLiteral("review_open"),)))},
    "refused": NO_READINGS,
}


# The frame names the command and every other line is the JSON itself, so nothing is added to it.
# am[verifies a-cd-rec-render-1018@3743ce]
@pytest.mark.parametrize("payload", RESULTS.values(), ids=RESULTS.keys())
def test_the_renderer_prints_the_returned_json_and_nothing_else(payload):
    frame, body = _renderer().render_skill_payload("(goalchainer-request ...)", payload).split("\n", 1)

    assert frame == "RESULTS: ((COMMAND_RETURN: (goalchainer-request ...)))"
    assert body == json.dumps(payload, indent=2, sort_keys=True)
    assert json.loads(body) == payload


JSON = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | st.text(),
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(st.text(), inner, max_size=4),
    max_leaves=24,
)


# am[verifies a-cd-rec-render-1018@3743ce]
@settings(deadline=None, max_examples=200)
@given(payload=st.dictionaries(st.text(), JSON, max_size=6))
def test_any_returned_object_reads_back_from_its_rendering(payload):
    frame, body = _renderer().render_skill_payload("(goalchainer-request ...)", payload).split("\n", 1)

    assert frame == "RESULTS: ((COMMAND_RETURN: (goalchainer-request ...)))"
    assert json.loads(body) == payload


# The live terminal demo run as a recording runs it, against a scripted tree: the real wrapper, the
# real loop driver, the scripted Codex, and Omega scripted unless `core` names a stock checkout. With
# no `incident` the demo's own incident is the request's text.
# am[verifies a-tr-tests-migrate-1018@3b663c]
def _demo(tmp_path: Path, agent: str, *, core: Path | None = None, env: dict[str, str] | None = None,
          provider: str | None = None, stub: str | None = None,
          incident: str | None = INCIDENT) -> subprocess.CompletedProcess[str]:
    tree = scripted_tree(tmp_path, agent, driver=LOOP, core=core, provider=provider, stub=stub)
    return subprocess.run(["bash", str(DEMO), *([] if incident is None else [incident])], capture_output=True,
                          text=True, check=False, env={**tree, "TERMINAL_DEMO_LINE_DELAY": "0", **(env or {})})


# The JSON the loop gave Codex for the request in the next turn's LAST_SKILL_USE_RESULTS, read from
# the context Codex was shown.
# am[verifies a-tr-tests-migrate-1018@3b663c]
def _returned(tmp_path: Path, turn: int) -> dict:
    context = (tmp_path / f"context.{turn}").read_text(encoding="utf-8")
    [line] = [line for line in context.splitlines() if line.startswith("SUCCESS, RETURN: ")]
    [answer] = ast.literal_eval(line.removeprefix("SUCCESS, RETURN: "))
    return json.loads(answer)


# The rendered skill result as the terminal shows it, at the loop report's indent.
# am[verifies a-tr-tests-migrate-1018@3b663c]
def _shown(command: str, payload: dict) -> str:
    rendered = _renderer().render_skill_payload(f"({command} ...)", payload)
    return "\n".join(f"   {line}" for line in rendered.splitlines())


# The demo opens with the stock provider self-test, the Codex CLI's version and login and the
# skills the plugin registers, before the loop's first cycle; a logged-out Codex stops it there,
# with no turn taken, nothing evaluated and no completion claimed.
# am[verifies a-tr-selftest-stock-1018@9096d5] am[verifies a-tr-terminal-wrapper-1018@a7ad4c]
def test_the_demo_opens_with_the_stock_self_test_and_a_logged_out_codex_stops_it(tmp_path):
    agent = "\n".join(("pin the incident", "goalchainer-request @REQUEST@", "send Post the summary."))
    run = _demo(tmp_path / "in", agent)
    out = _demo(tmp_path / "out", agent, env={"CODEX_LOGGED_OUT": "1"})

    assert run.returncode == 0, run.stdout + run.stderr
    opening = run.stdout.split("Starting the decision loop.", 1)[0]
    for shown in ("$ codex --version", "codex-cli 0.0.0-scripted", "$ codex login status",
                  "Logged in using ChatGPT", "registered", "goalchainer-request"):
        assert shown in opening, shown
    assert "agent cycle 1" in run.stdout.split("Starting the decision loop.", 1)[1]
    assert out.returncode != 0 and "Not logged in" in out.stdout
    assert "agent cycle" not in out.stdout and COMPLETE not in out.stdout
    assert not (tmp_path / "out" / "turns").exists() and not evaluated(tmp_path / "out")


# The self-test alone, as the draft's clip recorder runs it, shows the same checks.
# am[verifies a-tr-selftest-stock-1018@9096d5]
def test_the_self_test_alone_shows_the_stock_provider_path(tmp_path):
    tree = scripted_tree(tmp_path, "")
    run = subprocess.run(["bash", str(RECORDERS / "live-codex-selftest.sh")], capture_output=True, text=True,
                         check=False, env=tree)

    assert run.returncode == 0, run.stderr
    assert ["codex-cli 0.0.0-scripted", "Logged in using ChatGPT", "goalchainer-request"] == [
        line for line in run.stdout.splitlines() if not line.startswith(("\x1b", "$")) and line.strip()][:3]


# The demo's own incident reaches the loop's explicit review unchanged, the loop runs it and
# answers, the terminal shows the skill's JSON rendered under its call, and the completion line
# follows the loop's answer once.
# am[verifies a-tr-terminal-wrapper-1018@a7ad4c] am[verifies a-cd-rec-render-1018@3743ce]
def test_the_demo_runs_its_own_incident_through_the_loop_and_renders_the_result(tmp_path):
    run = _demo(tmp_path, "\n".join(("pin the incident", "goalchainer-request @REQUEST@", "send Post the summary.")),
                incident=None)

    assert run.returncode == 0, run.stdout + run.stderr
    text = shown_request(tmp_path)["reading"]["text"]
    assert text.startswith("Checkout is down and I have to post an update.") and text.endswith(
        "What should I send now, and what should I avoid sending?")
    assert [command for command, _ in evaluated(tmp_path)] == ["goalchainer-request"]
    assert _shown("goalchainer-request", {"authorization": "unresolved", "skill": "goalchainer-request"}) in run.stdout
    assert run.stdout.count(COMPLETE) == 1
    assert run.stdout.index("The agent answered after goalchainer-request's result") < run.stdout.index(COMPLETE)


ATTRIBUTED = ('del request["reading"]; request["context"]["readings"] = [{"signal": "customer-emails", '
              '"state": "detected", "estimator": "human-asserted", "source": "support:incident-room", '
              '"observed_at": request["context"]["as_of"]}]; text = json.dumps(request)')


# A goalchainer-request that is not the run's own request runs nothing: the user's words changed, or
# the attributed envelope, is refused with the members it changes, Codex reads the refusal as its
# next result, and the exact request on a later turn is the one evaluated, before the completion line.
# am[verifies a-od-count-only-the-request-1018@f2f5a8] am[verifies a-od-request-match-value-1018@e60dde]
# am[verifies a-tr-tests-migrate-1018@3b663c]
@pytest.mark.parametrize("change,named", [
    ('request["reading"]["text"] = "The caller never supplied these words."; text = json.dumps(request)', "reading.text"),
    (ATTRIBUTED, "context.readings, reading"),
], ids=["changed-text", "attributed"])
def test_a_request_that_is_not_the_runs_is_refused_unrun(tmp_path, change, named):
    agent = "\n".join(("goalchainer-request @CHANGED@", "goalchainer-request @REQUEST@", "send Post the summary."))
    run = _demo(tmp_path, agent, provider=changing(change))

    assert run.returncode == 0, run.stdout + run.stderr
    refusal = f"{REFUSAL} changes {named}."
    assert refusal in (tmp_path / "context.2").read_text(encoding="utf-8") and run.stdout.count(refusal) == 1
    assert evaluated(tmp_path) == [("goalchainer-request", [json.dumps(shown_request(tmp_path), sort_keys=True)])]
    assert run.stdout.index(refusal) < run.stdout.index("RESULTS: ((COMMAND_RETURN: (goalchainer-request ...)))") \
        < run.stdout.index(COMPLETE)


# A goalchainer-request the skill answers with its alert has not returned the review: it does not
# count, every answer after it is refused, and the demo fails with no completion line.
# am[verifies a-od-count-only-the-request-1018@f2f5a8] am[verifies a-tr-tests-migrate-1018@3b663c]
def test_a_request_the_skill_refuses_does_not_count(tmp_path):
    run = _demo(tmp_path, "\n".join(("goalchainer-request @REQUEST@", "send Post the summary.") * 2),
                env={"EVAL_FAILS": "1"})

    assert run.returncode != 0 and COMPLETE not in run.stdout
    assert [command for command, _ in evaluated(tmp_path)] == ["goalchainer-request"] * 2
    assert "ALERT_FAILED(Error (python_error GoalChainerSkillError" in run.stdout and REFUSED in run.stdout
    assert "the agent asked to send" not in run.stdout


# A send before goalchainer-request has returned is refused, the next turn tells Codex so, and the
# demo goes on to the request; the completion line follows the request's result, once.
# am[verifies a-tr-tests-migrate-1018@3b663c] am[related c-integrate-recorder-early-send-1018@11a28e]
def test_a_send_before_the_request_returns_is_refused(tmp_path):
    run = _demo(tmp_path, "\n".join(("send Post the update now.", "goalchainer-request @REQUEST@", "send Post the summary.")))

    assert run.returncode == 0, run.stdout + run.stderr
    assert REFUSED in (tmp_path / "context.2").read_text(encoding="utf-8")
    assert len(evaluated(tmp_path)) == 1 and run.stdout.count(COMPLETE) == 1
    assert run.stdout.index(REFUSED) < run.stdout.index("codex calls:  goalchainer-request ...") < run.stdout.index(COMPLETE)
    assert "the agent asked to send: Post the update now." not in run.stdout


# A demo whose turns run out before goalchainer-request returns fails, runs no request and prints no
# completion line.
# am[verifies a-tr-tests-migrate-1018@3b663c] am[related c-integrate-recorder-early-send-1018@11a28e]
def test_a_demo_that_never_calls_the_request_claims_no_completion(tmp_path):
    run = _demo(tmp_path, "\n".join(("send Post the update now.",) * 4))

    assert run.returncode != 0 and COMPLETE not in run.stdout
    assert not evaluated(tmp_path) and run.stdout.count(REFUSED) == 4


# A stock pinned Omega checkout with the plugin installed, from a pymetta host.
# am[verifies a-tr-tests-migrate-1018@3b663c]
@pytest.fixture(scope="module")
def core(tmp_path_factory) -> Path:
    return stock_core(tmp_path_factory)


# Against Omega itself: Codex is given GoalChainer's system prompt through the plugin's prompt
# extension and only the loop's tools, the plugin's being skills the skill process accepts and no
# system-prompt tool among them; the terminal shows exactly the JSON the skill returned, the answer
# Codex read in its next turn's LAST_SKILL_USE_RESULTS.
# am[verifies a-tr-tests-migrate-1018@3b663c] am[verifies a-cd-rec-render-1018@3743ce]
# am[rests-on c-tr-system-prompt-is-extension-1018@b7a6a1]
def test_codex_and_the_terminal_see_what_omega_and_the_skill_returned(tmp_path, core):
    run = _demo(tmp_path, "\n".join(("goalchainer-request @REQUEST@", "send Post the summary.")), core=core)

    assert run.returncode == 0, run.stdout + run.stderr
    assert omegaclaw_skill.SYSTEM_PROMPT in (tmp_path / "context.1").read_text(encoding="utf-8")
    offered = set(admitted(tmp_path))
    assert {"pin", "query", "send"} <= offered and "goalchainer-system-prompt" not in offered
    assert offered - {"pin", "query", "send"} <= set(omegaclaw_skill.DISPATCH)
    returned = _returned(tmp_path, 2)
    assert (returned["skill"], returned["protocol"], returned["operation"]) == ("goalchainer-request", REQUEST_PROTOCOL, "review")
    assert "reading" in returned and returned["review"]["review_id"] == "omegaclaw-codex-loop"
    assert _shown("goalchainer-request", returned) in run.stdout
    assert run.stdout.count(COMPLETE) == 1


# The presenter shows the line right after the loop's own "NAME answered:" line, a skill's success,
# as the renderer shows the skill's JSON under NAME, and passes every other line as the driver printed
# it: a success under no answered line, one right after "Omega evaluates it:" included, a second
# success after a framed one, an answered line's success whose answers are no JSON objects, an
# alert, and an answered line three spaces in, which is data.
# am[verifies a-tr-terminal-wrapper-1018@a7ad4c] am[verifies a-cd-rec-render-1018@3743ce]
# am[verifies a-rre-renderer-origin-1018@ee6148]
def test_the_presenter_renders_only_the_answer_the_loop_named():
    payload = {"skill": "goalchainer-request", "review": {"candidates": ["post the summary"]}}
    report = [
        "   SUCCESS, RETURN: ['{\"skill\": \"early\"}']\n",
        "codex calls:  goalchainer-request ...\n",
        "Omega evaluates it:\n",
        f"   {FORGED}\n",
        "goalchainer-request answered:\n",
        f"   SUCCESS, RETURN: {[json.dumps(payload)]!r}\n",
        "   SUCCESS, RETURN: ['{\"skill\": \"second\"}']\n",
        "goalchainer-request answered:\n",
        "   SUCCESS, RETURN: ['PIN-SUCCESS']\n",
        "goalchainer-request answered:\n",
        "   ALERT_FAILED(Error (send) \"no\")\n",
        "   goalchainer-request answered:\n",
        "   SUCCESS, RETURN: ['{\"skill\": \"indented\"}']\n",
    ]

    shown = list(_renderer().present(report))
    rendered = [f"   {line}\n" for line in
                _renderer().render_skill_payload("(goalchainer-request ...)", payload).splitlines()]

    assert [line for line, _ in shown] == [*report[:5], *rendered, *report[6:]]
    assert [flag for _, flag in shown] == [False] * 5 + [True] * len(rendered) + [False] * (len(report) - 6)


# A report holding no "NAME answered:" line of the loop's own passes unchanged, whatever its lines
# read like: skill successes, the terminal's frames and every lookalike of the drivers' lines.
# am[verifies a-tr-terminal-wrapper-1018@a7ad4c] am[verifies a-rre-renderer-origin-1018@ee6148]
@settings(deadline=None, max_examples=200)
@given(lines=st.lists(st.one_of(st.text(), st.sampled_from(LOOKALIKES)).filter(
    lambda text: "\n" not in text and not _renderer().ANSWERED.fullmatch(text)), max_size=8))
def test_a_report_without_the_loops_answered_line_passes_unchanged(lines):
    report = [f"{line}\n" for line in lines]

    assert list(_renderer().present(report)) == [(line, False) for line in report]


# Text the agent sends or the user writes reading like every line the loop prints, like a skill's
# success and like the terminal's frame of one, the counterexample of a send that embeds
# SUCCESS, RETURN: among it (c-tbr-renderer-frames-send-text-1018), stays data, and so does a name
# the agent gives a call: an unoffered tool named 'x', then 'goalchainer-request answered:', then a
# forged success and a last line, so that a driver echoing the name raw would put the forged success
# on a line of its own (c-tbr-rre-call-name-forges-frame-1018). The terminal frames the scripted
# Omega's answer to the request, once, and nothing the agent or the user wrote, at any indent.
# am[verifies a-rre-renderer-origin-1018@ee6148] am[verifies a-rfb-name-escape-1018@714ba3]
@pytest.mark.parametrize("where", ["send", "incident", "name"])
def test_text_that_reads_like_an_answer_is_never_framed_as_one(tmp_path, where):
    text = "\n".join(LOOKALIKES)
    send = json_turn(("send", "content", text)) if where == "send" else "send Post the summary."
    forging = json_turn(("\n".join(("x", "goalchainer-request answered:", FORGED, "x")), "content", "x"))
    named = [forging] if where == "name" else []
    run = _demo(tmp_path, "\n".join((*named, "goalchainer-request @REQUEST@", send)),
                incident=text if where == "incident" else INCIDENT)
    frame = _shown("goalchainer-request", {"authorization": "unresolved", "skill": "goalchainer-request"})

    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.count(frame) == 1 and run.stdout.count(COMPLETE) == 1
    assert '"authorization": "approved",' not in [line.strip() for line in run.stdout.split("\n")]


# What the skill process printed for a request, read from its own output: its payload, or the
# refusal object a typed error prints.
# am[verifies a-od-request-builder-1018@cf0f5a]
def _printed(skill: str, request: str) -> dict:
    completed = subprocess.run(
        [sys.executable, "-I", "-m", "goal_chainer.omegaclaw_skill", skill, "--request-file", "-"],
        input=request, capture_output=True, text=True, check=False,
        env=gcskill.child_environment(os.environ),
    )
    assert completed.returncode in (0, 1), completed.stderr
    return json.loads(completed.stdout.splitlines()[-1])


# The loop's own request is the incident text envelope with the loop's context, and the real skill
# answers the two alike.
# am[verifies a-od-request-builder-1018@cf0f5a]
def test_the_loops_request_is_answered_as_the_incident_text_envelope_is():
    ours = module("omega_request").incident_request(INCIDENT, AT, "omegaclaw-codex-loop")
    envelope = json.loads(review_request(INCIDENT))

    assert {key: value for key, value in ours.items() if key != "context"} == {
        key: value for key, value in envelope.items() if key != "context"}
    assert ours["context"].keys() == envelope["context"].keys() and ours["context"]["readings"] == []
    answers = [_printed("goalchainer-request", json.dumps(request)) for request in (ours, envelope)]
    if "error" in answers[1]:
        assert answers[0] == answers[1]
    else:
        assert all(answer["protocol"] == REQUEST_PROTOCOL and "reading" in answer for answer in answers)


# The provenance view is the review's own value for each provenance field and for nothing else,
# under a frame line naming the review id, whatever the values hold.
# am[verifies a-cd-rec-audit-provenance-1018@a15419]
@settings(deadline=None, max_examples=100)
@given(review=st.fixed_dictionaries({field: JSON for field in _renderer().PROVENANCE},
                                    optional={"disposition": JSON, "candidates": JSON}))
def test_the_provenance_view_is_the_reviews_own_fields_and_only_those(review):
    renderer = _renderer()
    frame, body = renderer.render_provenance({"review": review, "inferences": 3}).split("\n", 1)

    assert frame == f"PROVENANCE: {json.dumps(review['review_id'])}"
    assert json.loads(body) == {field: review[field] for field in renderer.PROVENANCE}


# The audit recorder run as a recording runs it, with its pauses stubbed: it prints the request
# file, the review the request command computed from it and that same review's recorded
# provenance, and nothing from another checkout. The fingerprint names the review's inputs and
# not its spend, so an independent run of the same request records the same one.
# am[verifies a-cd-rec-audit-1018@09ddac] am[verifies a-cd-rec-audit-provenance-1018@a15419]
def test_the_audit_recorder_shows_its_request_its_review_and_that_reviews_provenance(tmp_path, capsys):
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "sleep").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (stub / "sleep").chmod(0o755)
    env = {**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}",
           "OMEGACLAW_GOALCHAINER_DIR": str(ROOT), "GOALCHAINER_PYTHON": sys.executable}
    request_file = RECORDERS / "incident-review-request.json"

    completed = subprocess.run(["bash", str(RECORDERS / "live-goalchainer-audit.sh")], env=env,
                               capture_output=True, text=True, check=False)

    assert completed.returncode == 0, completed.stderr
    assert f"request --input {request_file} {' '.join(CLI_LIMITS)}" in completed.stdout
    assert "showcase" not in completed.stdout and "PeTTaChainer" not in completed.stdout
    # Each section follows one shown command: cd, cat, the request, the provenance.
    _, after_cd, shown_request, shown_result, shown_provenance = re.split(
        r"^\x1b\[1;36m\$ .*\x1b\[0m\n", completed.stdout, flags=re.MULTILINE)
    assert after_cd == "" and shown_request == request_file.read_text(encoding="utf-8")
    result = json.loads(shown_result)
    assert (result["protocol"], result["operation"], result["authorization"], result["applies_effects"]) == (
        REQUEST_PROTOCOL, "review", "unresolved", False)
    assert shown_provenance == _renderer().render_provenance(result) + "\n"
    assert cli.main(["request", "--input", str(request_file), *CLI_LIMITS]) == 0
    assert json.loads(capsys.readouterr().out)["review"]["fingerprint"] == result["review"]["fingerprint"]

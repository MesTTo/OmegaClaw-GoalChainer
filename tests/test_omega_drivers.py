"""Purpose: test the two Codex + Omega drivers, their live wrappers and the explicit incident request
they send, with a scripted provider and no hosted call, in a home where no Codex login is found,
whatever the test process carries. With Omega's answers scripted, the drivers offer Codex the tools
they serve under a reply schema made of them, evaluate a goalchainer-request only when it is
omega_request's review, spacing, key order and number spelling aside, refuse any other
unevaluated with the members it changes, count only that request's result, refuse an answer before
it, feed back the alert for a call Omega refused without evaluating it, refuse a loop turn of more
than one call with none of them run, and fail without the result or when the provider's turn failed
or its reply went unread. Both drivers keep data as data: no line the user, the agent, Codex or a
skill writes stands in the first column, where only a driver's own lines are, or carries a control
character, a name the agent gives a call reaches a driver's line only as one escaped token, through
the scripted reader and Omega's own decoder alike, and a skill's answer follows a line only the
driver prints. Against a stock Omega
checkout with the plugin installed, Omega's own
provider path reads Codex's reply, the review runs through Omega's own registry on pymetta and the
report shows the loop's result and the agent's whole answer, with no authorization or delivery
claim."""

from __future__ import annotations

import codecs
import copy
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from omega_support import (DRIVER, DRIVER_LINE_FORMS, FORGED, INCIDENT, LIB, LOOKALIKES, LOOP, OMEGACLAW,
                           OWN_LOOKALIKES, ROOT, SKILLS, admitted, answer_after, changing, evaluated, json_turn,
                           module, run_driver, scripted_tree, shown_request, stock_core, ungrammatical,
                           with_skill)
from request_support import LIMITS

from goal_chainer.omegaclaw_skill import DISPATCH, SYSTEM_PROMPT
from goal_chainer.requests import REQUEST_PROTOCOL

RECORDERS = ROOT / "hackathon" / "video" / "scripts" / "recorders"
ANSWER = "send The review says:\n- publish_raw_log is forbidden\n- post the redacted summary"


# Nothing a scripted run starts finds a Codex login, even when the test process carries one, as a
# session given a Codex home or an API key does: ~ is the run's own empty home, and no CODEX_ or
# OPENAI_ variable reaches it.
# am[verifies a-tr-harness-private-home-1018@6ed615]
@pytest.mark.parametrize("stock", [False, True], ids=["scripted", "stock-core"])
def test_a_scripted_run_finds_no_codex_login(tmp_path, monkeypatch, stock):
    monkeypatch.setenv("CODEX_HOME", str(Path.home() / ".codex"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-scripted-not-a-key")
    env = scripted_tree(tmp_path, "", core=tmp_path / "core" if stock else None)
    probe = ("import os; print(os.path.expanduser('~/.codex/auth.json'));"
             "print(sorted(name for name in os.environ if name.startswith(('CODEX_', 'OPENAI_'))))")
    run = subprocess.run([sys.executable, "-I", "-c", probe], env=env, capture_output=True, text=True, check=True)

    assert run.stdout.splitlines() == [str(tmp_path / "home" / ".codex" / "auth.json"), "[]"]
    assert not (tmp_path / "home" / ".codex").exists()


# am[verifies a-od-request-builder-1018@cf0f5a]
def _explicit_review(request: dict, review_id: str) -> None:
    at = request["context"]["as_of"]
    assert request == {
        "operation": "review", "domain": {"packaged": "incident"},
        "context": {"review_id": review_id, "subject": "checkout", "trigger": "incident-report",
                    "as_of": at, "authority": "advisory", "policy_version": "incident-v1", "readings": []},
        "reading": {"text": INCIDENT, "observed_at": at, "valid_until": None},
        **LIMITS,
    }


# The loop offers Codex exactly the tools it serves, the plugin's skills and pin, query and send,
# under a reply schema made of them, and the context carries them with Omega's rules, the plugin's
# extension and the run's request.
# am[verifies a-op-reply-schema-1018@d51383] am[verifies a-op-drivers-tools-1018@a61ed7]
def test_the_loop_offers_codex_the_tools_it_serves(tmp_path):
    run = run_driver(LOOP, tmp_path, "\n".join(("pin the incident", "goalchainer-request @REQUEST@", "send Post the summary.")))

    assert run.returncode == 0, run.stdout + run.stderr
    assert admitted(tmp_path) == ["pin", "query", "send", "goalchainer-request"]
    context = (tmp_path / "context.1").read_text(encoding="utf-8")
    [tools] = [line.removeprefix("TOOLS: ") for line in context.splitlines() if line.startswith("TOOLS: ")]
    assert [tool["function"]["name"] for tool in json.loads(tools)] == admitted(tmp_path)
    assert "File I/O is restricted." in context and "Use goalchainer-request with JSON." in context


# The single-shot driver offers every skill, as Omega's loop offers its provider.
# am[verifies a-op-reply-schema-1018@d51383] am[verifies a-op-drivers-tools-1018@a61ed7]
def test_the_driver_offers_codex_every_skill(tmp_path):
    run = run_driver(DRIVER, tmp_path, "goalchainer-request @REQUEST@")

    assert run.returncode == 0, run.stdout + run.stderr
    assert admitted(tmp_path) == list(SKILLS)


# The loop pins, runs goalchainer-request with exactly the host's explicit review, and ends on the
# agent's answer having delivered nothing.
# am[verifies a-od-drivers-1018@e5f805] am[verifies a-od-request-builder-1018@cf0f5a]
def test_the_loop_sends_the_explicit_review_and_delivers_nothing(tmp_path):
    run = run_driver(LOOP, tmp_path, "\n".join(("pin the incident", "goalchainer-request @REQUEST@", "send Post the summary.")))

    assert run.returncode == 0, run.stderr
    request = shown_request(tmp_path)
    _explicit_review(request, "omegaclaw-codex-loop")
    assert evaluated(tmp_path) == [("goalchainer-request", [json.dumps(request, sort_keys=True)])]
    assert "PIN-SUCCESS" in run.stdout and "the agent asked to send: Post the summary." in run.stdout
    assert "The agent answered after goalchainer-request's result; nothing was delivered" in run.stdout


REFUSED = "(send refused: goalchainer-request has not returned a result)"


# An answer before the request's result is refused, the refusal is what Codex reads next, and the
# loop goes on to the request and answers once, after it.
# am[verifies a-od-drivers-1018@e5f805] am[related c-integrate-recorder-early-send-1018@11a28e]
def test_an_answer_before_the_request_is_refused_and_the_loop_goes_on(tmp_path):
    run = run_driver(LOOP, tmp_path, "\n".join(("send Post now.", "goalchainer-request @REQUEST@", "send Post the summary.")))

    assert run.returncode == 0, run.stdout + run.stderr
    assert REFUSED in (tmp_path / "context.2").read_text(encoding="utf-8")
    assert len(evaluated(tmp_path)) == 1
    assert run.stdout.index(REFUSED) < run.stdout.index("codex calls:  goalchainer-request ...")
    assert run.stdout.count("The agent answered after goalchainer-request's result") == 1
    assert "the agent asked to send: Post now." not in run.stdout


# A call Omega refused is not evaluated: its alert is what Codex reads next, and the loop goes on.
# A reply refused whole is fed back the same way.
# am[verifies a-op-drivers-tools-1018@a61ed7] am[verifies a-op-calls-1018@94747e]
@pytest.mark.parametrize("refused,alert", [
    ('{"tool_calls": [{"name": "shell", "arguments": {"cmd": "ls"}}]}', "ALERT_FAILED(Error (shell) \"Unknown tool: 'shell'\")"),
    ('{"tool_calls": []}', 'ALERT_FAILED(Error () "List of tool calls is empty")'),
], ids=["refused-call", "refused-reply"])
def test_a_call_omega_refused_is_fed_back_unevaluated(tmp_path, refused, alert):
    run = run_driver(LOOP, tmp_path, "\n".join((refused, "goalchainer-request @REQUEST@", "send Post the summary.")))

    assert run.returncode == 0, run.stdout + run.stderr
    assert alert in run.stdout and alert in (tmp_path / "context.2").read_text(encoding="utf-8")
    assert [command for command, _ in evaluated(tmp_path)] == ["goalchainer-request"]


# A loop turn is one call: a reply Omega read as two, here the run's own request and an answer, is
# refused whole, neither of them run, and the refusal is what Codex reads next; the next turn's
# single request is the one evaluated, and only then is an answer let through.
# am[verifies a-tr-one-call-loop-1018@af4f6b]
@pytest.mark.parametrize("turn", [
    "goalchainer-request @REQUEST@\\nsend Post the summary now.",
    "send Post the summary now.\\ngoalchainer-request @REQUEST@",
], ids=["request-then-send", "send-then-request"])
def test_a_loop_turn_of_two_calls_is_refused_with_none_run(tmp_path, turn):
    run = run_driver(LOOP, tmp_path, "\n".join((turn, "goalchainer-request @REQUEST@", "send Post the summary.")))

    assert run.returncode == 0, run.stdout + run.stderr
    refusal = "(turn refused, nothing evaluated: this loop takes one tool call a turn, and the reply made 2: "
    assert refusal in run.stdout and refusal in (tmp_path / "context.2").read_text(encoding="utf-8")
    assert evaluated(tmp_path) == [("goalchainer-request", [json.dumps(shown_request(tmp_path), sort_keys=True)])]
    assert "the agent asked to send: Post the summary now." not in run.stdout
    assert run.stdout.count("The agent answered after goalchainer-request's result") == 1
    assert run.stdout.index(refusal) < run.stdout.index("the agent asked to send: Post the summary.")


# The single-shot driver keeps its multi-call turn: both of a two-call reply's calls are answered.
# am[verifies a-tr-one-call-loop-1018@af4f6b] am[verifies a-od-drivers-1018@e5f805]
def test_the_driver_still_answers_every_call_of_its_turn(tmp_path):
    run = run_driver(DRIVER, tmp_path, "goalchainer-request @REQUEST@\nsend Post the summary.")

    assert run.returncode == 0, run.stdout + run.stderr
    assert [command for command, _ in evaluated(tmp_path)] == ["goalchainer-request"]
    assert "(Omega's own send; this driver runs only the GoalChainer plugin's skills)" in run.stdout


# The lookalikes read as the drivers' own lines: every form a driver prints in the first column has
# one, so a test putting them where data goes puts every kind of driver line there.
# am[verifies a-rre-renderer-origin-1018@ee6148]
def test_the_lookalikes_read_as_every_kind_of_driver_line():
    assert [form for form in DRIVER_LINE_FORMS if not any(re.fullmatch(form, line) for line in OWN_LOOKALIKES)] == []


# No data a run shows, the user's words, the agent's calls with the names it gives them, and the
# answers to them, stands as one of the driver's own lines or carries a control character, though
# it reads like every one of them: each lookalike is printed three spaces in, escaped, a call to an
# unoffered tool named by them all is named on the driver's line as one escaped token, and the only
# "answered:" line in the first column is the driver's own for the request Omega evaluated. The
# single-shot driver shows the agent's calls, the loop the agent's send.
# am[verifies a-rre-renderer-origin-1018@ee6148] am[verifies a-rfb-name-escape-1018@714ba3]
@pytest.mark.parametrize("driver", [LOOP, DRIVER])
def test_no_data_a_run_shows_stands_as_a_drivers_own_line(tmp_path, driver):
    text = "\n".join(LOOKALIKES)
    if driver == LOOP:
        agent = "\n".join((json_turn((text, "content", "x")), "goalchainer-request @REQUEST@",
                           json_turn(("send", "content", text))))
    else:
        agent = json_turn((text, "content", "x"), ("goalchainer-request", "json_request", text),
                          ("send", "content", text))
    run = run_driver(driver, tmp_path, agent, incident=text)
    lines = run.stdout.split("\n")

    assert ungrammatical(run.stdout) == [], run.stdout
    assert lines.count("goalchainer-request answered:") == (1 if driver == LOOP else 0)
    assert f"   {FORGED}" in lines and "   \\x0dgoalchainer-request answered:" in lines
    if driver == LOOP:
        [named] = [line for line in lines if line.startswith("codex calls:  ") and "\\x0a" in line]
        assert "\\x0agoalchainer-request\\x20answered:\\x0a" in named and "\\x1b[2K" in named
    assert "   answered\\u202e:goalchainer-request" in lines


# Codex's run, shown with CODEX_SHOW, is Codex's own text: codex_turn shows each line of the parts it
# keeps as data, every lookalike included, gives back Codex's reply as it was, and returns only once
# the last of that run is shown, so a line the caller prints next comes after it.
# am[verifies a-rre-renderer-origin-1018@ee6148]
def test_codex_turn_shows_codexs_run_as_data(tmp_path):
    kept = ["OpenAI Codex (scripted)", *LOOKALIKES, "hook: SessionStart", *LOOKALIKES]
    transcript = [*kept[:1 + len(LOOKALIKES)], "user", "the context Codex read", *kept[1 + len(LOOKALIKES):]]
    (tmp_path / "transcript").write_text("\n".join(transcript) + "\n", encoding="utf-8")
    (tmp_path / "reply").write_text('{"tool_calls": []}', encoding="utf-8")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "codex").write_text('#!/bin/sh\ncat "$CODEX_TRANSCRIPT" >&2\ncat "$CODEX_REPLY"\n',
                                            encoding="utf-8")
    (tmp_path / "bin" / "codex").chmod(0o755)
    run = subprocess.run(["bash", "-c", 'source "$1"; codex_turn "the context" 1 "{}"; echo "turn returned" >&2',
                          "turn", str(LIB)],
                         capture_output=True, text=True, check=False,
                         env={"PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin", "HOME": str(tmp_path), "CODEX_SHOW": "1",
                              "CODEX_TRANSCRIPT": str(tmp_path / "transcript"), "CODEX_REPLY": str(tmp_path / "reply")})
    *shown, returned, end = run.stderr.split("\n")

    assert (run.returncode, run.stdout) == (0, '{"tool_calls": []}'), run.stderr
    assert (returned, end) == ("turn returned", ""), run.stderr
    assert all(line.startswith("   ") for line in shown)
    assert not any(c != "\t" and unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") for line in shown for c in line)
    assert [codecs.decode(line[3:], "unicode_escape") for line in shown] == kept


# A request that fails gives no result, so every answer after it is refused, and a loop that never
# requests has none either: each ends with an error and no answer claimed. The skill's alert is
# reported as Omega's loop words it, a host that could not run the skill as that failure.
# am[verifies a-od-drivers-1018@e5f805] am[related c-integrate-recorder-early-send-1018@11a28e]
@pytest.mark.parametrize("agent,env,evaluations,shown", [
    (("goalchainer-request @REQUEST@", "send Post the summary.", "send Post it anyway."), {"EVAL_FAILS": "1"}, 1,
     'ALERT_FAILED(Error (python_error GoalChainerSkillError "goalchainer-request failed") (goalchainer-request))'),
    (("goalchainer-request @REQUEST@", "send Post the summary."), {"HOST_FAILS": "1"}, 1,
     "(goalchainer-request could not run, status 1)"),
    (("send Post now.",) * 4, {}, 0, REFUSED),
], ids=["failed-request", "host-failed", "never-requested"])
def test_a_loop_without_a_request_result_answers_nothing_and_fails(tmp_path, agent, env, evaluations, shown):
    run = run_driver(LOOP, tmp_path, "\n".join(agent), env=env)

    assert len(evaluated(tmp_path)) == evaluations
    assert run.returncode == 1 and shown in run.stdout and REFUSED in run.stdout
    assert "The agent answered" not in run.stdout and "the agent asked to send" not in run.stdout
    assert "Loop ended without an answer that follows a goalchainer-request result." in run.stdout


# The single-shot driver evaluates the plugin's call with the host's review and shows Omega's own
# call unrun.
# am[verifies a-od-drivers-1018@e5f805] am[verifies a-od-request-builder-1018@cf0f5a]
def test_the_driver_runs_the_explicit_review(tmp_path):
    run = run_driver(DRIVER, tmp_path, "goalchainer-request @REQUEST@\nsend Post the summary.")

    assert run.returncode == 0, run.stderr
    request = shown_request(tmp_path)
    _explicit_review(request, "omegaclaw-codex-driver")
    assert evaluated(tmp_path) == [("goalchainer-request", [json.dumps(request, sort_keys=True)])]
    assert "(Omega's own send; this driver runs only the GoalChainer plugin's skills)" in run.stdout


UNREVIEWED = "!! no goalchainer-request with this run's REQUEST returned a result."


# A single-shot run without the run's own request's result fails: Codex called no GoalChainer
# tool, the request it called failed or could not run, or Omega refused the call.
# am[verifies a-od-drivers-1018@e5f805] am[verifies a-op-calls-1018@94747e]
@pytest.mark.parametrize("agent,env,evaluations", [
    ("send Post the raw logs.", {}, 0),
    ("goalchainer-request @REQUEST@\nsend Post the summary.", {"EVAL_FAILS": "1"}, 1),
    ("goalchainer-request @REQUEST@", {"HOST_FAILS": "1"}, 1),
    ('{"tool_calls": [{"name": "goalchainer-reqest", "arguments": {"json_request": "{}"}}]}', {}, 0),
], ids=["no-goalchainer-call", "failed-request", "host-failed", "refused-call"])
def test_a_driver_run_without_a_goalchainer_result_fails(tmp_path, agent, env, evaluations):
    run = run_driver(DRIVER, tmp_path, agent, env=env)

    assert len(evaluated(tmp_path)) == evaluations
    assert run.returncode == 1
    assert run.stdout.rstrip().endswith(UNREVIEWED)


REFUSAL = "goalchainer-request refused, not evaluated: its argument"
ANSWERS = "\n".join(("goalchainer-request @CHANGED@", "send The review is complete."))
# Each change the agent might make to the REQUEST, and how the refusal names it.
CHANGES = {
    "text": ('request["reading"]["text"] = "The caller never supplied these words."; text = json.dumps(request)',
             "changes reading.text."),
    "domain": ('request["domain"] = {"packaged": "task_control"}; text = json.dumps(request)', "changes domain.packaged."),
    "context": ('request["context"]["authority"] = "operator"; text = json.dumps(request)', "changes context.authority."),
    "limits": ('request["inference_budget"] = 10; text = json.dumps(request)', "changes inference_budget."),
    "duplicate-key": ('text = text[:-1] + ", " + json.dumps({"operation": "plan"})[1:]',
                      "is not strict JSON (the key 'operation' appears more than once)."),
    "malformed": ("text = text[:-1]", "is not strict JSON ("),
}
# Every key order reversed, the separators spaced and the timeout written as 600.0: the same request.
REFORMATTED = ('request["timeout_seconds"] = 600.0; request["context"] = dict(reversed(list(request["context"].items()))); '
               'text = json.dumps(dict(reversed(list(request.items()))), separators=(" , ", " : "))')


# The success control: spacing, key order and the way a number is written are not part of the
# request, so a request re-spelled that way is the run's REQUEST, evaluated as Codex wrote it.
# am[verifies a-od-request-match-value-1018@e60dde] am[verifies a-od-count-only-the-request-1018@f2f5a8]
@pytest.mark.parametrize("driver", [LOOP, DRIVER])
def test_a_reformatted_request_is_the_runs_request(tmp_path, driver):
    run = run_driver(driver, tmp_path, ANSWERS, provider=changing(REFORMATTED))

    assert run.returncode == 0, run.stdout + run.stderr
    [(_, [sent])] = evaluated(tmp_path)
    assert sent != json.dumps(shown_request(tmp_path), sort_keys=True)
    assert json.loads(sent) == shown_request(tmp_path) and '"timeout_seconds" : 600.0' in sent


# A request whose argument is not this run's REQUEST is refused before Omega evaluates it, the
# refusal naming what changed, and no review is claimed: either driver fails, the loop after Codex
# read the refusal and its answer was refused.
# am[verifies a-od-count-only-the-request-1018@f2f5a8] am[verifies a-od-request-match-value-1018@e60dde]
@pytest.mark.parametrize("driver", [LOOP, DRIVER])
@pytest.mark.parametrize("change,named", CHANGES.values(), ids=CHANGES.keys())
def test_a_changed_or_malformed_request_is_refused_unevaluated(tmp_path, driver, change, named):
    run = run_driver(driver, tmp_path, ANSWERS, provider=changing(change))

    assert run.returncode == 1, run.stdout
    assert not evaluated(tmp_path)
    assert f"{REFUSAL} {named}" in run.stdout
    assert "The agent answered" not in run.stdout
    if driver == LOOP:
        assert f"{REFUSAL} {named}" in (tmp_path / "context.2").read_text(encoding="utf-8") and REFUSED in run.stdout
    else:
        assert run.stdout.rstrip().endswith(UNREVIEWED)


# Another plugin skill's success is evaluated and shown as Omega would, and counts for nothing:
# the single-shot run fails without the run's own request, and the loop refuses the answer after it.
# am[verifies a-od-count-only-the-request-1018@f2f5a8]
@pytest.mark.parametrize("driver", [LOOP, DRIVER])
def test_another_plugin_skills_result_counts_for_nothing(tmp_path, driver):
    dispatch = '{"group": "trust-discovery", "operation": "inspect"}'
    run = run_driver(driver, tmp_path, f"goalchainer-snars-dispatch {dispatch}\nsend The review is complete.",
               stub=with_skill("goalchainer-snars-dispatch"))

    assert run.returncode == 1, run.stdout
    assert evaluated(tmp_path) == [("goalchainer-snars-dispatch", [dispatch])]
    assert '\\"skill\\": \\"goalchainer-snars-dispatch\\"' in run.stdout or '"skill": "goalchainer-snars-dispatch"' in run.stdout
    assert "The agent answered" not in run.stdout
    assert (REFUSED if driver == LOOP else UNREVIEWED) in run.stdout


# A refused request does not end the loop: Codex reads the refusal, sends the run's REQUEST on its
# next turn, and that request's result lets the answer through.
# am[verifies a-od-count-only-the-request-1018@f2f5a8] am[verifies a-od-request-match-value-1018@e60dde]
def test_a_refused_request_is_recovered_by_a_later_exact_one(tmp_path):
    agent = "\n".join(("goalchainer-request @CHANGED@", "goalchainer-request @REQUEST@", "send Post the summary."))
    run = run_driver(LOOP, tmp_path, agent, provider=changing(CHANGES["text"][0]))

    assert run.returncode == 0, run.stdout + run.stderr
    assert f"{REFUSAL} changes reading.text." in (tmp_path / "context.2").read_text(encoding="utf-8")
    assert evaluated(tmp_path) == [("goalchainer-request", [json.dumps(shown_request(tmp_path), sort_keys=True)])]
    assert run.stdout.count("The agent answered after goalchainer-request's result") == 1


# A provider turn that fails, or a reply the host could not read, fails either driver as that
# failure, with its status, before anything is evaluated.
# am[verifies a-od-provider-failure-1018@69017b]
@pytest.mark.parametrize("driver,failing,shown", [
    (LOOP, "PROVIDER_FAILS", "(the provider's turn failed, status 3; ending)"),
    (LOOP, "READ_FAILS", "(Omega could not read the agent's reply, status 3; ending)"),
    (DRIVER, "PROVIDER_FAILS", "!! the provider's turn failed, status 3."),
    (DRIVER, "READ_FAILS", "!! Omega could not read the agent's reply, status 3."),
], ids=["loop-provider", "loop-read", "driver-provider", "driver-read"])
def test_a_failed_provider_turn_or_reply_read_fails_therun_driver(tmp_path, driver, failing, shown):
    run = run_driver(driver, tmp_path, "goalchainer-request @REQUEST@", env={failing: "1"})

    assert run.returncode == 1
    assert shown in run.stdout.splitlines()
    assert not evaluated(tmp_path)
    assert "codex calls:" not in run.stdout and "codex (the agent) calls:" not in run.stdout


# A stock pinned Omega checkout with the plugin installed, from a pymetta host.
# am[verifies a-od-tests-1018@252294]
@pytest.fixture(scope="module")
def core(tmp_path_factory) -> Path:
    return stock_core(tmp_path_factory)


# Against Omega itself: Codex is offered the plugin's dispatchers beside pin, query and send under
# their schema, Omega's provider path reads its replies, the explicit review runs through Omega's
# registry on pymetta and is reported as the loop's success, and the agent's multi-line answer is
# reported whole and delivered nowhere.
# am[verifies a-od-drivers-1018@e5f805] am[verifies a-od-tests-1018@252294] am[verifies a-op-drivers-tools-1018@a61ed7]
# am[verifies a-v2-omega-registry-test-1020@6718b9]
def test_the_loop_runs_the_review_through_omega_and_reports_it_as_answered(tmp_path, core):
    agent = "\n".join(("pin the incident", "goalchainer-request @REQUEST@", ANSWER.replace("\n", "\\n")))
    run = run_driver(LOOP, tmp_path, agent, core=core)

    assert run.returncode == 0, run.stdout + run.stderr
    context = (tmp_path / "context.1").read_text(encoding="utf-8")
    assert SYSTEM_PROMPT in context and '"name": "goalchainer-request"' in context
    assert set(admitted(tmp_path)) == {*DISPATCH, "pin", "query", "send"}
    review = answer_after(run.stdout, "codex calls:  goalchainer-request ...")
    assert (review["skill"], review["protocol"], review["operation"]) == ("goalchainer-request", REQUEST_PROTOCOL, "review")
    assert (review["authorization"], review["applies_effects"]) == ("unresolved", False)
    assert "reading" in review and review["review"]["review_id"] == "omegaclaw-codex-loop"
    for line in ANSWER.removeprefix("send ").splitlines():
        assert line in run.stdout
    assert "delivered to" not in run.stdout


# Omega's own decoder hands a call to an unoffered tool back with its alert and the name the agent
# gave it, cut at its first white space but keeping every control and format character before it
# (c-tbr-rre-real-decoder-names-1018). So a name moving the cursor up three lines and erasing one
# (c-tbr-rre-call-name-escapes-reach-terminal-1018), and one holding ESC, BEL, BS, DEL, the C1 CSI,
# a right-to-left override and a zero-width space, each reach the loop's line. The loop shows each as
# one escaped token that decodes back to the whole name, no line of the report holds a raw control,
# the only "answered:" line in the first column is the request's, and the run still answers.
# am[verifies a-rfb-boundary-tests-1018@ac6d70] am[verifies a-rfb-name-escape-1018@714ba3]
# am[rests-on c-tbr-rre-real-decoder-names-1018@9bd411]
@pytest.mark.parametrize("name", [
    f"x{chr(0x1B)}[3A{chr(0x1B)}[2Kgoalchainer-request",
    "x" + "".join(map(chr, (0x1B, 0x07, 0x08, 0x7F, 0x9B, 0x202E, 0x200B))) + "goalchainer-request",
], ids=["cursor-up", "every-surviving-control"])
def test_omegas_own_decoder_leaves_a_supplied_name_escaped(tmp_path, core, name):
    agent = "\n".join((json_turn((name, "content", "x")), "goalchainer-request @REQUEST@", "send Post the summary."))
    run = run_driver(LOOP, tmp_path, agent, core=core)
    lines = run.stdout.split("\n")

    assert run.returncode == 0, run.stdout + run.stderr
    assert ungrammatical(run.stdout) == [], run.stdout
    [named] = [line for line in lines if line.startswith("codex calls:  x")]
    assert named.encode("ascii").decode("unicode_escape") == f"codex calls:  {name} ...", run.stdout
    assert [line for line in lines if line.endswith(" answered:") and not line.startswith(" ")] == [
        "goalchainer-request answered:"]


# Against Omega itself: the single-shot driver reads Codex's reply through Omega's provider path,
# keeps a multi-line answer whole, runs the review through the registry, shows Omega's own send
# unrun, and shows a call to no registered skill with upstream's alert, unrun.
# am[verifies a-od-drivers-1018@e5f805] am[verifies a-od-tests-1018@252294] am[verifies a-op-calls-1018@94747e]
def test_the_driver_runs_the_review_through_omega(tmp_path, core):
    run = run_driver(DRIVER, tmp_path, "goalchainer-request @REQUEST@\n" + ANSWER, core=core)
    unknown = run_driver(DRIVER, tmp_path / "unknown", '{"tool_calls": [{"name": "no-such-tool", "arguments": {"x": "y"}}]}', core=core)

    assert run.returncode == 0, run.stdout + run.stderr
    called = run.stdout.split("codex (the agent) calls:", 1)[1].split("Omega evaluates", 1)[0]
    assert "send The review says:\n   - publish_raw_log is forbidden\n   - post the redacted summary" in called
    review = answer_after(run.stdout, "Omega evaluates the agent's call(s):")
    assert (review["protocol"], review["authorization"], review["applies_effects"]) == (REQUEST_PROTOCOL, "unresolved", False)
    assert "(Omega's own send; this driver runs only the GoalChainer plugin's skills)" in run.stdout
    assert unknown.returncode == 1 and unknown.stdout.rstrip().endswith(UNREVIEWED)
    assert "ALERT_FAILED(Error (no-such-tool \"y\") \"Unknown tool: 'no-such-tool'\")" in unknown.stdout


# Each live wrapper runs its driver from the repository it names, with the request text and the
# recording's settings: Codex's run shown and the line pace from TERMINAL_DEMO_LINE_DELAY.
# am[verifies a-od-drivers-1018@e5f805]
@pytest.mark.parametrize("wrapper,driver,pace", [
    ("live-codex-omegaclaw.sh", DRIVER, "0.35"), ("live-codex-omegaclaw-loop.sh", LOOP, "0.28")])
def test_each_live_wrapper_runs_its_driver_with_the_recordings_settings(tmp_path, wrapper, driver, pace):
    stub = tmp_path / "integrations" / "omegaclaw" / driver
    stub.parent.mkdir(parents=True)
    stub.write_text('printf "%s|%s|%s\\n" "$1" "$CODEX_SHOW" "$DEMO_DELAY"\n', encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "OMEGACLAW_GOALCHAINER_DIR": str(tmp_path)}

    shown = subprocess.run(["bash", str(RECORDERS / wrapper), "Checkout is down."], env=env,
                           capture_output=True, text=True, check=False)
    paced = subprocess.run(["bash", str(RECORDERS / wrapper), "Checkout is down."],
                           env={**env, "TERMINAL_DEMO_LINE_DELAY": "0"}, capture_output=True, text=True, check=False)

    assert (shown.returncode, shown.stdout) == (0, f"Checkout is down.|1|{pace}\n"), shown.stderr
    assert paced.stdout == "Checkout is down.|1|0\n"


# omega_request.py's build command: the user's words from standard input, newlines included, in the
# explicit review observed now, under the given review id, on one line; and its match command, which
# exits 0 for that line and prints the refusal, exiting 1, for a changed one.
# am[verifies a-od-request-builder-1018@cf0f5a]
def test_the_request_builder_prints_the_explicit_review_on_one_line():
    built = subprocess.run([sys.executable, "-I", str(OMEGACLAW / "omega_request.py"), "build", "--review-id", "probe"],
                           input=INCIDENT, capture_output=True, text=True, check=True)

    [line] = built.stdout.splitlines()
    _explicit_review(json.loads(line), "probe")
    match = [sys.executable, "-I", str(OMEGACLAW / "omega_request.py"), "match", line]
    same = subprocess.run(match, input=line, capture_output=True, text=True, check=False)
    other = subprocess.run(match, input=line.replace('"advisory"', '"operator"'), capture_output=True, text=True, check=False)
    assert (same.returncode, same.stdout) == (0, "")
    assert other.returncode == 1 and other.stdout.startswith(f"{REFUSAL} changes context.authority.")


OMEGA_REQUEST = module("omega_request")
REVIEW = OMEGA_REQUEST.incident_request(INCIDENT, "2026-10-18T00:00:00+00:00", "probe")
# Every member of the review whose value an agent could change, as a path of keys.
MEMBERS = [("operation",), ("domain", "packaged"), *[("context", key) for key in REVIEW["context"]],
           *[("reading", key) for key in REVIEW["reading"]], ("inference_budget",), ("timeout_seconds",)]


# Any key order at any depth, any JSON spacing and any spelling of each number as an integer or a
# float leave the review the same request.
# am[verifies a-od-request-match-value-1018@e60dde]
@settings(max_examples=80, deadline=None)
@given(st.randoms(use_true_random=False), st.sampled_from([(",", ":"), (", ", ": "), (" , ", " : ")]))
def test_any_spacing_key_order_or_number_spelling_is_the_same_request(rnd, separators):
    def respell(value):
        if isinstance(value, dict):
            items = list(value.items())
            rnd.shuffle(items)
            return {key: respell(member) for key, member in items}
        if isinstance(value, int) and not isinstance(value, bool):
            return rnd.choice([value, float(value)])
        return value

    assert OMEGA_REQUEST.refusal(REVIEW, json.dumps(respell(REVIEW), separators=separators)) is None


# A member given another JSON value, of the same type or another, is refused by its path.
# am[verifies a-od-request-match-value-1018@e60dde]
@settings(max_examples=120, deadline=None)
@given(st.sampled_from(MEMBERS), st.one_of(st.text(max_size=12), st.integers(), st.booleans(), st.none(),
                                           st.lists(st.integers(), max_size=2)))
def test_a_changed_member_is_refused_by_its_path(member, value):
    changed = copy.deepcopy(REVIEW)
    *outer, last = member
    target = changed
    for key in outer:
        target = target[key]
    assume(json.dumps(target[last]) != json.dumps(value))
    target[last] = value

    assert f"{REFUSAL} changes {'.'.join(member)}." in OMEGA_REQUEST.refusal(REVIEW, json.dumps(changed))

"""Purpose: test the Omega drivers' host side, _omega_lib.sh and omega_metta.py. Run as the drivers
run them on a stock pinned Omega checkout with the plugin installed, they answer the plugin's skills,
its prompt extension and Omega's skill rules, offer each skill as a tool exactly as upstream's
provider renders one, under a reply schema within the strict subset Codex sends, read a reply's calls
through upstream's own provider path with the loop's alert for each call or reply upstream refuses,
answer a review request with the loop's success and a refused one with the loop's alert, and refuse
a command the plugin did not register; the shell helpers report a result by its status, read a
call's parts and show any name a reply supplies as one token of printable ASCII that reads back as
itself and any data three spaces in, and the host delivers nothing on the agent's send."""

from __future__ import annotations

import ast
import json
import os
import re
import shlex
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from request_support import LIMITS
from test_setup_omegaclaw import _setup, _stock_core

from goal_chainer.omegaclaw_skill import SYSTEM_PROMPT
from goal_chainer.runtime.engine import metta_engine

OMEGACLAW = Path(__file__).resolve().parents[1] / "integrations" / "omegaclaw"
LIB = OMEGACLAW / "_omega_lib.sh"
# The plugin's skills in the order its loader adds them.
PLUGIN_SKILLS = ["goalchainer-request", "goalchainer-directive-dispatch", "goalchainer-snars-dispatch"]
# The plugin README's incident review, without reading text, so no Jev answer is needed.
REVIEW = {
    "operation": "review",
    "domain": {"packaged": "incident"},
    "context": {
        "review_id": "incident-42", "subject": "checkout", "trigger": "incident-report",
        "as_of": "2026-10-16T09:00:00+00:00", "authority": "advisory", "policy_version": "incident-v1",
        "readings": [],
    },
    **LIMITS,
}
# Upstream's AIProvider.convert_tool over providers.getTools, run on the checkout's own modules in a
# process of its own, with a stand-in for the openai package it imports and never calls here.
CONVERT = r'''
import json, sys, types
core = sys.argv[1]
sys.path[:0] = [core, core + "/src", core + "/providers"]
sys.modules["openai"] = types.ModuleType("openai")
import lib_llm_ext, providers
skills = [(f["name"], f["description"], f["parameters"]["required"]) for f in json.loads(sys.stdin.read())]
print(json.dumps([lib_llm_ext.AIProvider.convert_tool(None, tool) for tool in providers.getTools(skills)]))
'''
# The keywords of the strict structured-output subset Codex sends a schema under.
STRICT_KEYWORDS = {"type", "properties", "required", "additionalProperties", "items", "anyOf", "enum", "description"}


# One shell helper of _omega_lib.sh, sourced as the drivers source it, after `prelude`.
# am[verifies a-rt-oh-pymetta-run-1018@ace6fb]
def _host(function: str, *arguments: str, core: Path | None = None, stdin: str = "",
          prelude: str = "") -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **({"OMEGACLAW_DIR": str(core)} if core else {})}
    return subprocess.run(["bash", "-c", f'source "$0" || exit 1\n{prelude}\n"$@"', str(LIB), function, *arguments],
                          input=stdin, capture_output=True, text=True, check=False, env=env)


# A stock pinned Omega checkout with the plugin installed by scripts/setup-omegaclaw.sh, which
# records this test run's locked interpreter for the plugin's skills. The test process boots its
# own pymetta first, which sets SWI_HOME_DIR in its environment, so every helper below runs from a
# pymetta host as a GoalChainer process would launch a driver.
# am[verifies a-rt-oh-pymetta-run-1018@ace6fb]
@pytest.fixture(scope="module")
def core(tmp_path_factory) -> Path:
    with metta_engine(None):
        pass
    assert os.environ.get("SWI_HOME_DIR")
    installed = _stock_core(tmp_path_factory.mktemp("omega") / "OmegaClaw-Core")
    _setup(installed)
    return installed


# The tools the drivers offer for `names`, as omega_tools prints them.
# am[verifies a-op-reply-schema-1018@d51383]
def _tools(core: Path, *names: str) -> list[dict]:
    offered = _host("omega_tools", *names, core=core)
    assert offered.returncode == 0, offered.stderr
    return json.loads(offered.stdout)


# The offer every reading below is made against: pin, send and goalchainer-request.
# am[verifies a-op-calls-1018@94747e]
@pytest.fixture(scope="module")
def reading_tools(core) -> str:
    return json.dumps(_tools(core, "pin", "send", "goalchainer-request"))


# Every object closed and every property required, anyOf only below the root, and no keyword
# outside the strict subset.
# am[verifies a-op-reply-schema-1018@d51383]
def _strict(schema: dict, root: bool = True) -> None:
    assert set(schema) <= STRICT_KEYWORDS, set(schema) - STRICT_KEYWORDS
    assert not (root and "anyOf" in schema) and (not root or schema["type"] == "object")
    if schema.get("type") == "object":
        assert schema["additionalProperties"] is False and schema["required"] == list(schema["properties"])
        for member in schema["properties"].values():
            _strict(member, root=False)
    if schema.get("type") == "array":
        _strict(schema["items"], root=False)
    for branch in schema.get("anyOf", []):
        _strict(branch, root=False)


# Omega's own getSkills, with the plugin loaded by its entry point, names the plugin's three skills;
# the plugin's prompt extension is the skill process's system prompt, and the skill rules are
# Omega's getSkillRules.
# am[verifies a-op-session-self-1018@bd8329] am[verifies a-rt-oh-derived-menu-1018@d6bf3d]
def test_the_plugins_skills_prompt_extension_and_omegas_rules(core):
    registered = _host("omega_registered", core=core)
    extensions = _host("omega_extensions", core=core)
    rules = _host("omega_rules", core=core)

    assert (registered.returncode, extensions.returncode, rules.returncode) == (0, 0, 0), registered.stderr
    assert registered.stdout.split() == PLUGIN_SKILLS
    assert extensions.stdout.strip() == SYSTEM_PROMPT
    assert "File I/O is restricted: always use get-io-policy before reading/writing files to verify allowed base paths." \
        in rules.stdout.splitlines()


# Each skill is offered as upstream's provider sends it: upstream's own convert_tool over its
# getTools renders the same tools, and each carries the registry's description and arguments.
# am[verifies a-op-reply-schema-1018@d51383] am[verifies a-op-session-self-1018@bd8329]
def test_each_skill_is_offered_as_upstreams_provider_sends_it(core):
    offered = _tools(core, "goalchainer-request", "pin", "write-file")
    upstream = subprocess.run([sys.executable, "-I", "-c", CONVERT, str(core)], input=json.dumps(
        [tool["function"] for tool in offered]), capture_output=True, text=True, check=True)

    assert offered == json.loads(upstream.stdout)
    assert [(t["function"]["name"], t["function"]["parameters"]["required"]) for t in offered] == [
        ("pin", ["message"]), ("write-file", ["filename", "content"]), ("goalchainer-request", ["json_request"])]
    assert offered[2]["function"]["description"] == (
        "Review, plan or check a current step against a selected domain; include explicit inference and time limits")
    assert {tool["function"]["name"] for tool in _tools(core)} >= {*PLUGIN_SKILLS, "send", "shell", "metta"}
    assert _host("omega_tools", "goalchainer-not-a-skill", core=core).returncode != 0


# The reply schema stays inside the strict subset and admits exactly one call shape per offered
# tool: its name and its parameters object; an offer of no tool has no schema.
# am[verifies a-op-reply-schema-1018@d51383]
def test_the_reply_schema_admits_only_the_offered_calls(core):
    offered = _tools(core, "goalchainer-request", "send")
    schema = _host("omega_reply_schema", json.dumps(offered), core=core)
    empty = _host("omega_reply_schema", "[]", core=core)

    assert schema.returncode == 0, schema.stderr
    reply = json.loads(schema.stdout)
    _strict(reply)
    branches = reply["properties"]["tool_calls"]["items"]["anyOf"]
    assert [(b["properties"]["name"]["enum"], b["properties"]["arguments"]) for b in branches] == [
        ([tool["function"]["name"]], tool["function"]["parameters"]) for tool in offered]
    assert empty.returncode != 0 and "no tool is offered" in empty.stderr


TRICKY = 'line one\nsays "hi" and \\ back (paren\tand é'
# Replies and what Omega's reading answers for each: the offered tools are pin, send and
# goalchainer-request; every alert is the loop's, worded by upstream's validation.
READINGS = {
    "calls": ({"tool_calls": [{"name": "goalchainer-request", "arguments": {"json_request": json.dumps(REVIEW)}},
                              {"name": "send", "arguments": {"content": TRICKY}}]},
              [{"id": "call_1", "command": "goalchainer-request", "arguments": [json.dumps(REVIEW)], "alert": None},
               {"id": "call_2", "command": "send", "arguments": [TRICKY], "alert": None}]),
    "unknown-tool": ({"tool_calls": [{"name": "shell", "arguments": {"cmd": "ls"}}]},
                     [{"id": "call_1", "command": "shell", "arguments": ["ls"],
                       "alert": "ALERT_FAILED(Error (shell \"ls\") \"Unknown tool: 'shell'\")"}]),
    "missing-parameter": ({"tool_calls": [{"name": "send", "arguments": {}}]},
                          [{"id": "call_1", "command": "send", "arguments": [], "alert":
                            "ALERT_FAILED(Error (send) \"Call tool parameter is not set: tool: 'send', parameter: 'content'\")"}]),
    "not-a-string": ({"tool_calls": [{"name": "send", "arguments": {"content": 5}}]},
                     [{"id": "call_1", "command": "send", "arguments": ["5"], "alert":
                       "ALERT_FAILED(Error (send \"5\") \"Call tool parameter is not a string: tool: 'send', parameter: 'content'\")"}]),
    "arguments-not-an-object": ({"tool_calls": [{"name": "send", "arguments": "x"}]},
                                [{"id": "call_1", "command": "send", "arguments": [],
                                  "alert": "ALERT_FAILED(Error (send) \"Tool arguments must be a JSON object\")"}]),
    "no-calls": ({"tool_calls": []},
                 [{"id": None, "command": None, "arguments": [], "alert": "ALERT_FAILED(Error () \"List of tool calls is empty\")"}]),
    "no-call-list": ({"calls": []}, [{"id": None, "command": None, "arguments": [],
                                      "alert": "ALERT_FAILED(Error () \"Codex's reply is no JSON object with a tool_calls list\")"}]),
}


# A reply is read as Omega's loop reads one: validated against the offered tools, rendered and read
# back by sread, so each call's arguments are the strings Omega would evaluate, quotes, backslashes,
# newlines and parentheses included, and each call or reply upstream refused carries the loop's
# alert instead.
# am[verifies a-op-calls-1018@94747e]
@pytest.mark.parametrize("reply,expected", READINGS.values(), ids=READINGS.keys())
def test_a_reply_is_read_as_upstreams_loop_reads_it(core, reading_tools, reply, expected):
    read = _host("omega_calls", reading_tools, json.dumps(reply), core=core)

    assert read.returncode == 0, read.stderr
    assert [json.loads(line) for line in read.stdout.splitlines()] == expected


# A reply that is no JSON, or one whose rendering sread cannot parse, here a tool named "send)", is
# refused whole with the loop's alert, the unreadable text written as a String.
# am[verifies a-op-calls-1018@94747e]
def test_an_unreadable_reply_is_refused_whole(core, reading_tools):
    garbled = _host("omega_calls", reading_tools, "Here is my answer.", core=core)
    unparsed = _host("omega_calls", reading_tools, json.dumps({"tool_calls": [{"name": "send)", "arguments": {"content": "x"}}]}), core=core)

    assert (garbled.returncode, unparsed.returncode) == (0, 0), garbled.stderr + unparsed.stderr
    [refused] = map(json.loads, garbled.stdout.splitlines())
    [unread] = map(json.loads, unparsed.stdout.splitlines())
    assert refused["alert"].startswith("ALERT_FAILED(Error () \"Codex's reply is not JSON: Expecting value")
    assert unread["command"] is None and unread["alert"].startswith('ALERT_FAILED(Error (syntax_error "Parse error in form: ')


# A review request answers the loop's success with the skill's JSON, which resolves no authorization.
# am[verifies a-rt-oh-request-review-1018@4f055a] am[verifies a-op-calls-1018@94747e]
def test_a_review_request_answers_the_loops_success_and_authorizes_nothing(core):
    evaluated = _host("omega_eval_skill", "goalchainer-request", json.dumps([json.dumps(REVIEW)]), core=core)

    assert evaluated.returncode == 0, evaluated.stderr
    [line] = evaluated.stdout.splitlines()
    [answer] = ast.literal_eval(line.removeprefix("SUCCESS, RETURN: "))
    answer = json.loads(answer)
    assert (answer["skill"], answer["operation"], answer["protocol"]) == (
        "goalchainer-request", "review", "goalchainer-request-v1")
    assert (answer["authorization"], answer["applies_effects"]) == ("unresolved", False)
    assert answer["review"]["candidates"]


# A request the skill refuses answers the loop's alert, status 3, naming the skill's error class,
# its message and the call that failed.
# am[verifies a-op-calls-1018@94747e]
def test_a_refused_request_answers_the_loops_alert(core):
    refused = _host("omega_eval_skill", "goalchainer-request", json.dumps(['{"operation": "nope"}']), core=core)

    assert refused.returncode == 3, refused.stderr
    assert refused.stdout.splitlines() == [
        'ALERT_FAILED(Error (python_error GoalChainerSkillError "goalchainer-request failed (invalid_input): '
        'inference_budget is required and must be a positive integer.") (goalchainer-request "{\\"operation\\": \\"nope\\"}"))']


# am[verifies a-rt-oh-request-review-1018@4f055a]
def test_a_command_the_plugin_did_not_register_is_refused(core):
    refused = _host("omega_eval_skill", "shell", json.dumps(["ls /"]), core=core)

    assert refused.returncode not in (0, 3)
    assert "shell is no skill the GoalChainer plugin registered." in refused.stderr


# A result is reported as the evaluation printed it for a success or an alert, and as the host's
# failure for any other status, which the status keeps.
# am[verifies a-op-drivers-tools-1018@a61ed7]
@pytest.mark.parametrize("status,printed,reported", [
    (0, "SUCCESS, RETURN: ['done']", "SUCCESS, RETURN: ['done']"),
    (3, "ALERT_FAILED(Error (x) \"no\")", "ALERT_FAILED(Error (x) \"no\")"),
    (1, "", "(goalchainer-request could not run, status 1)"),
], ids=["success", "alert", "host"])
def test_a_result_is_reported_by_its_status(status, printed, reported):
    stub = f"omega_eval_skill() {{ printf '%s' {shlex.quote(printed)}; return {status}; }}"
    result = _host("omega_result", "goalchainer-request", "[]", prelude=stub)

    assert (result.returncode, result.stdout) == (status, reported + "\n")


# A call's parts read as text: a string as it is, null as nothing, a list as JSON or one of its
# elements; a call as its command and each argument, and a reply refused whole as "(the reply)".
# am[verifies a-op-drivers-tools-1018@a61ed7] am[verifies a-rt-oh-request-review-1018@4f055a]
def test_a_calls_parts_read_as_text():
    call = json.dumps({"id": "call_1", "command": "write-file", "arguments": ["a b", "two\nlines"], "alert": None})
    whole = json.dumps({"id": None, "command": None, "arguments": [], "alert": "ALERT_FAILED(Error () \"x\")"})

    assert [_host("omega_field", call, *key).stdout for key in (("command",), ("alert",), ("arguments", "1"), ("arguments",))] == [
        "write-file", "", "two\nlines", json.dumps(["a b", "two\nlines"])]
    assert _host("omega_call_text", call).stdout == "write-file a b two\nlines"
    assert _host("omega_call_text", whole).stdout == "(the reply)"


# The host never sends: the agent's text is shown as asked and reported undelivered.
# am[verifies a-rt-oh-request-review-1018@4f055a]
def test_the_host_delivers_nothing_on_the_agents_send():
    sent = _host("omega_send", "Posting the raw log for debugging.")

    assert sent.returncode == 1
    assert sent.stdout.splitlines() == [
        "(not delivered: GoalChainer's results authorize nothing, and this host has no authorization of its own to send)",
        "the agent asked to send: Posting the raw log for debugging.",
    ]


# What the escaper must never print raw: in a name any character but printable ASCII, which a shown
# name's escapes are written in too, and in data any control or format character but a tab.
# am[verifies a-rfb-escape-properties-1018@d9201b] am[verifies a-rfb-name-ascii-raw-1018@55758d]
def _raw(text: str, *, name: bool) -> list[str]:
    if name:
        return [c for c in text if not "!" <= c <= "~"]
    return [c for c in text if c not in " \t" and unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp")]


# Text with every escape in the forms Python's backslashreplace writes read back as the characters
# they name; text holding no backslash of its own reads back as itself.
# am[verifies a-rfb-escape-properties-1018@d9201b]
def _unescaped(text: str) -> str:
    return re.sub(r"\\(?:x([0-9a-f]{2})|u([0-9a-f]{4})|U([0-9a-f]{8}))",
                  lambda match: chr(int(next(digits for digits in match.groups() if digits), 16)), text)


# Any name a reply supplies, a character past U+FFFF and the text of an escape included, is shown as
# one token of printable ASCII, so a character that renders as nothing or as a blank, U+034F, U+FE0F,
# U+3164 or U+2800 among them, shows as its escape (i-rfb-name-invisible-kept-1018), and it reads
# back as the name.
# am[verifies a-rfb-escape-properties-1018@d9201b] am[verifies a-rfb-name-escape-1018@714ba3]
# am[verifies a-rfb-name-injective-1018@0bffc5] am[verifies a-rfb-name-ascii-raw-1018@55758d]
@settings(deadline=None, max_examples=200)
@given(name=st.text(st.characters(blacklist_categories=("Cs",), blacklist_characters=(chr(0),))))
@example(name=f"x{chr(0xE0001)}1")
@example(name=f"goalchainer{chr(0x200B)}-request answered:{chr(0x0A)}{chr(0x1B)}[3A")
@example(name=f"x{chr(0x5C)}x1b{chr(0x1B)}")
@example(name=f"goalchainer{chr(0x034F)}-request")
@example(name=f"goalchainer-request{chr(0xFE0F)}")
@example(name=f"goalchainer{chr(0x3164)}-request")
@example(name=f"goalchainer{chr(0x2800)}-request")
@example(name=f"caf{chr(0xE9)}")
def test_any_name_is_shown_as_one_token_that_reads_back_as_itself(name):
    shown = _host("omega_name", name)

    assert shown.returncode == 0, shown.stderr
    assert _raw(shown.stdout, name=True) == []
    assert _unescaped(shown.stdout) == name


# Any lines of data without a backslash are shown each three spaces in, keeping its spaces and tabs
# and holding no other raw control or format character, and each reads back as its line.
# am[verifies a-rfb-escape-properties-1018@d9201b]
@settings(deadline=None, max_examples=200)
@given(lines=st.lists(st.text(st.characters(blacklist_categories=("Cs",),
                                            blacklist_characters=(chr(0), chr(0x0A), chr(0x5C)))), max_size=4))
@example(lines=[f"a{chr(0xE0001)}1", f"{chr(0x0D)}goalchainer-request answered:", "tab\tand space"])
def test_any_data_is_shown_three_spaces_in_and_reads_back_as_itself(lines):
    shown = _host("omega_data", stdin="".join(f"{line}\n" for line in lines))
    printed = shown.stdout.split("\n")

    assert shown.returncode == 0, shown.stderr
    assert printed[-1] == "" and all(line.startswith("   ") for line in printed[:-1])
    assert [_raw(line, name=False) for line in printed] == [[] for _ in printed]
    assert [_unescaped(line[3:]) for line in printed[:-1]] == lines


# Any bytes as a name, undecodable ones and the text of an escape included, are shown as one token of
# printable ASCII that reads back as those bytes, so the byte 0x9b and the control U+009B show apart
# (c-rfb-name-bytes-collide-1018).
# am[verifies a-rfb-escape-properties-1018@d9201b] am[verifies a-rfb-name-injective-1018@0bffc5]
# am[verifies a-rfb-name-ascii-raw-1018@55758d]
@settings(deadline=None, max_examples=200)
@given(raw=st.binary().filter(lambda raw: 0 not in raw))
@example(raw=bytes([0x78, 0x9B]))
@example(raw="x".encode() + chr(0x9B).encode())
@example(raw=bytes([0x78, 0x5C, 0x78, 0x66, 0x66, 0xFF]))
def test_any_bytes_as_a_name_are_shown_as_one_token_that_reads_back_as_those_bytes(raw):
    shown = _host("omega_name", os.fsdecode(raw))

    assert shown.returncode == 0, shown.stderr
    assert _raw(shown.stdout, name=True) == []
    assert os.fsencode(_unescaped(shown.stdout)) == raw

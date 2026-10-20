"""Purpose: test that the shared goalchainer reader, through which the request, directive and show
commands read their JSON, reads standard input as UTF-8 whatever the process locale, as it reads a file.
As real child processes, under each decoding the interpreter can be told to give its standard input, a
byte that is no UTF-8 is refused with the command's typed invalid_input error, in the file form's words
with standard input for the path, and valid non-ASCII text arrives unchanged. In process, a standard
input that cannot be read, absent, text alone or a closed stream, is refused in the same words."""

from __future__ import annotations

import codecs
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from goal_chainer.cli import main as cli_main
from goal_chainer.domains.forms import input_text

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "planning" / "task-control.request.json"
MAIN = "import sys; from goal_chainer.cli import main; sys.exit(main())"
LIMITS = ["--inference-budget", "1000000000", "--timeout-seconds", "600"]
MARK = b"rr-MARK"
# Each way the interpreter can be told to decode its standard input, with the encoding and error
# handler sys.stdin then has; PYTHONIOENCODING sets standard output's alike. The C locale turns UTF-8
# mode on (PEP 540), so its stdin's text holds a lone surrogate for a byte that is no UTF-8.
DECODINGS = {
    "C locale": ({"LC_ALL": "C"}, ("utf-8", "surrogateescape")),
    "UTF-8 mode": ({"PYTHONUTF8": "1"}, ("utf-8", "surrogateescape")),
    "surrogateescape": ({"PYTHONIOENCODING": "utf-8:surrogateescape"}, ("utf-8", "surrogateescape")),
    "latin-1": ({"PYTHONIOENCODING": "latin-1"}, ("latin-1", "strict")),
    "strict UTF-8": ({"PYTHONIOENCODING": "utf-8:strict"}, ("utf-8", "strict")),
}


# A child's environment: this process's without any setting of how it decodes text, the checkout's
# src first on the path, and `decoding`'s settings.
# am[verifies a-integrate-cli-stdin-verify-1018@ce4641]
def environment(decoding: str) -> dict[str, str]:
    unset = {"LANG", "LC_ALL", "LC_CTYPE", "PYTHONUTF8", "PYTHONIOENCODING"}
    env = {key: value for key, value in os.environ.items() if key not in unset}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH")]))
    return {**env, **DECODINGS[decoding][0]}


# One JSON input of each command, holding MARK once inside a string: a review request on the shipped
# example, a directive operation and a saved review result.
# am[verifies a-integrate-cli-stdin-verify-1018@ce4641]
def inputs() -> dict[str, dict]:
    request = {key: value for key, value in json.loads(EXAMPLE.read_text(encoding="utf-8")).items()
               if key not in ("goal", "procedures")}
    request["operation"] = "review"
    request["context"] = {**request["context"], "review_id": MARK.decode()}
    review = {"review_id": MARK.decode(), "subject": "s", "domain": {"policy_version": "v"}, "fingerprint": "f",
              "proposal": None, "disposition": "no proposal", "escalation": None, "blockers": [], "steps": [],
              "missing_information": {"unknown_signals": [], "unestimated_dimensions": []},
              "engine": {"inferences": 1, "budget": {"inferences": 2}}}
    result = {"protocol": "goalchainer-request-v1", "operation": "review", "review": review,
              "authorization": "unresolved", "applies_effects": False, "inferences": 1}
    return {"request": request, "directive": {"operation": MARK.decode()}, "show": result}


# The command's input as bytes with MARK's text replaced by rr- and `injected`.
# am[verifies a-integrate-cli-stdin-verify-1018@ce4641]
def written(command: str, injected: bytes) -> bytes:
    text = json.dumps(inputs()[command]).encode("utf-8")
    assert text.count(MARK) == 1, command
    return text.replace(MARK, b"rr-" + injected)


# The command run as a child process of this checkout under `decoding`, reading `source` ("-" for the
# standard input `stdin`), run from the repository root so the example's domain path resolves.
# am[verifies a-integrate-cli-stdin-verify-1018@ce4641]
def run(command: str, source: str, stdin: bytes, decoding: str) -> subprocess.CompletedProcess:
    argv = [command, "--input", source, *(LIMITS if command != "show" else [])]
    return subprocess.run([sys.executable, "-c", MAIN, *argv], input=stdin, capture_output=True,
                          env=environment(decoding), cwd=ROOT, check=False, timeout=None)


# The typed error a command answers with: request and directive print the error JSON on standard
# output, show prints its words on standard error; each exits with status 1.
# am[verifies a-integrate-cli-stdin-verify-1018@ce4641]
def refusal(command: str, completed: subprocess.CompletedProcess) -> str:
    assert completed.returncode == 1, (completed.stdout, completed.stderr)
    if command == "show":
        line = completed.stderr.decode("utf-8", "backslashreplace").strip().splitlines()[-1]
        assert line.startswith("GoalChainer error [invalid_input]: "), line
        return line.removeprefix("GoalChainer error [invalid_input]: ")
    error = json.loads(completed.stdout)
    assert error["ok"] is False and error["error"]["code"] == "invalid_input", error
    return error["error"]["message"]


# Each decoding is what it is said to be, so no case below passes for want of the decoding it names;
# an encoding is compared by its codec's own name, since sys.stdin reports latin-1 as iso8859-1.
# am[verifies a-integrate-cli-stdin-reproduce-1018@4c91dc]
@pytest.mark.parametrize("decoding", list(DECODINGS))
def test_each_child_decodes_its_standard_input_as_its_environment_says(decoding) -> None:
    probe = "import sys; print(sys.stdin.encoding, sys.stdin.errors)"
    completed = subprocess.run([sys.executable, "-c", probe], input=b"", capture_output=True,
                               env=environment(decoding), cwd=ROOT, check=True)
    encoding, errors = completed.stdout.decode().split()
    expected_encoding, expected_errors = DECODINGS[decoding][1]
    assert (codecs.lookup(encoding).name, errors) == (codecs.lookup(expected_encoding).name, expected_errors)


# A byte that is no UTF-8, from standard input or from a file, is refused before the command reads
# anything else, in file_text's words with the source named, whatever the child's decoding.
# am[verifies a-integrate-cli-stdin-reproduce-1018@4c91dc] am[verifies a-integrate-cli-stdin-utf8-1018@e333fc]
@pytest.mark.parametrize("decoding", list(DECODINGS))
@pytest.mark.parametrize("command", ["request", "directive", "show"])
def test_a_byte_that_is_no_utf8_is_refused_from_standard_input_as_from_a_file(command, decoding, tmp_path) -> None:
    data = written(command, b"\xff")
    at = data.index(b"\xff")
    saved = tmp_path / "input.json"
    saved.write_bytes(data)
    stdin = refusal(command, run(command, "-", data, decoding))
    assert stdin == f"Cannot read JSON input: standard input: cannot be read as UTF-8 text: invalid start byte at byte {at}"
    from_file = refusal(command, run(command, str(saved), b"", decoding))
    assert from_file == f"Cannot read JSON input: {saved.resolve()}: cannot be read as UTF-8 text: invalid start byte at byte {at}"


# The two UTF-8 bytes of é arrive as é under every decoding: the request's review names rr-é, and show
# words it, written in the child's own output encoding.
# am[verifies a-integrate-cli-stdin-reproduce-1018@4c91dc] am[verifies a-integrate-cli-stdin-utf8-1018@e333fc]
@pytest.mark.parametrize("decoding", list(DECODINGS))
def test_valid_non_ascii_text_on_standard_input_arrives_unchanged(decoding) -> None:
    requested = run("request", "-", written("request", "é".encode()), decoding)
    assert requested.returncode == 0, requested.stdout + requested.stderr
    assert json.loads(requested.stdout)["review"]["review_id"] == "rr-é"
    shown = run("show", "-", written("show", "é".encode()), decoding)
    assert shown.returncode == 0, shown.stderr
    assert shown.stdout.decode(DECODINGS[decoding][1][0]).splitlines()[0].startswith("relevance review rr-é of s ")


# A standard input with no bytes to read, absent as when fd 0 is closed or replaced by text alone, is
# refused in the same words rather than read as text no UTF-8 decoding produced.
# am[verifies a-integrate-cli-stdin-utf8-1018@e333fc]
@pytest.mark.parametrize("stdin", [None, io.StringIO("{}")], ids=["absent", "text-only"])
def test_a_standard_input_that_is_no_byte_stream_is_refused(stdin, monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdin", stdin)
    assert cli_main(["show"]) == 1
    assert capsys.readouterr().err.strip() == ("GoalChainer error [invalid_input]: Cannot read JSON input: standard input: "
                                               "cannot be read as UTF-8 text: it is no byte stream")


# The refusal a test hands input_text, so the helper's own words are read back.
# am[verifies a-integrate-input-text-closed-buffer-1018@7d108d]
class Refused(Exception):
    pass


# A standard input whose byte stream is closed, as a closed text wrapper's buffer is, raises ValueError
# when read, which is no OSError. The reader refuses it in its usual words, and through the reader show
# and request answer it by their own contracts.
# am[verifies a-integrate-input-text-closed-buffer-1018@7d108d]
def test_a_closed_standard_input_stream_is_refused_by_the_reader_and_its_commands(monkeypatch, capsys) -> None:
    words = "standard input: cannot be read as UTF-8 text: I/O operation on closed file."

    def closed() -> io.TextIOWrapper:
        stream = io.TextIOWrapper(io.BytesIO(b"{}"))
        stream.close()
        return stream

    monkeypatch.setattr("sys.stdin", closed())
    with pytest.raises(Refused) as caught:
        input_text("-", Refused)
    assert str(caught.value) == words
    monkeypatch.setattr("sys.stdin", closed())
    assert cli_main(["show"]) == 1
    assert capsys.readouterr().err.strip() == f"GoalChainer error [invalid_input]: Cannot read JSON input: {words}"
    monkeypatch.setattr("sys.stdin", closed())
    assert cli_main(["request", *LIMITS]) == 1
    error = json.loads(capsys.readouterr().out)
    assert error["ok"] is False and error["error"]["code"] == "invalid_input"
    assert error["error"]["message"] == f"Cannot read JSON input: {words}"

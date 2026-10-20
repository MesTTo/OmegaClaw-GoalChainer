"""Purpose: test the Jev capture tool: the key comes only from TYPESAFE_API_KEY or a private file's
key line, a missing key is exit 2 with nothing sent, the pytest plugin logs every answer an offline
run reads, every live request and refusal at the cap, and every test a run will run, and shards share
one cache and one request cap and prune only once they ran the whole suite. Every other test run, a
pytest run or the plugin suite's, reads offline with no key whatever environment it started in."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from goal_chainer import semantic_capture as capture
from goal_chainer import semantic_reader as sr
from request_support import CLI_LIMITS

KEY = "synthetic-capture-key"
CAPTURE_ENV = (capture.READ_LOG_ENV, capture.MAX_REQUESTS_ENV, capture.REQUEST_LOG_ENV, capture.COLLECT_LOG_ENV)
# Where OBSERVER, loaded into a child pytest, writes the Jev settings that run read.
JEV_REPORT_ENV = "GOALCHAINER_TEST_JEV_REPORT"


# A capture runs this module too, with its own logs in these variables; every test here starts
# with none of them, so nothing a test configures writes into the capture running it.
# am[verifies a-jev-capture-plugin-tests-hermetic-1017@a243e1]
@pytest.fixture(autouse=True)
def no_capture_environment(monkeypatch):
    for name in CAPTURE_ENV:
        monkeypatch.delenv(name, raising=False)


# A test that reads a key file writes the key straight into os.environ and then removes it with
# monkeypatch, which would restore it at teardown unless the fixture had recorded the variable's
# starting state; setenv records that state, absent included, so the last undo puts it back and no
# key outlives the test.
# am[verifies a-jev-capture-1016] am[related a-dr-suite-offline-unless-capture-1018@f388c2]
@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "")
    monkeypatch.delenv("TYPESAFE_API_KEY")


# am[verifies a-jev-capture-1016]
def test_the_key_is_read_from_its_line_in_a_private_file(tmp_path, no_key, monkeypatch) -> None:
    env_file = tmp_path / "env"
    env_file.write_text(f"OTHER=value\nexport TYPESAFE_API_KEY='{KEY}'\n", encoding="utf-8")
    env_file.chmod(0o600)

    capture.load_key(env_file)

    assert os.environ["TYPESAFE_API_KEY"] == KEY
    assert "OTHER" not in os.environ or os.environ["OTHER"] != "value"
    monkeypatch.delenv("TYPESAFE_API_KEY")


# am[verifies a-jev-capture-1016]
@pytest.mark.parametrize(
    ("mode", "text"),
    [(0o644, f"TYPESAFE_API_KEY={KEY}\n"), (0o640, f"TYPESAFE_API_KEY={KEY}\n"),
     (0o602, f"TYPESAFE_API_KEY={KEY}\n"), (0o600, "OTHER=1\n")],
)
def test_a_readable_or_keyless_file_is_refused(tmp_path, no_key, mode, text) -> None:
    env_file = tmp_path / "env"
    env_file.write_text(text, encoding="utf-8")
    env_file.chmod(mode)

    with pytest.raises(capture.UsageError):
        capture.load_key(env_file)
    assert "TYPESAFE_API_KEY" not in os.environ


# Owner-only is the rule, so a read-only private file is accepted too.
# am[verifies a-jev-capture-1016]
def test_a_read_only_private_file_is_accepted(tmp_path, no_key, monkeypatch) -> None:
    env_file = tmp_path / "env"
    env_file.write_text(f"TYPESAFE_API_KEY={KEY}\n", encoding="utf-8")
    env_file.chmod(0o400)

    capture.load_key(env_file)

    assert os.environ["TYPESAFE_API_KEY"] == KEY
    monkeypatch.delenv("TYPESAFE_API_KEY")


# am[verifies a-jev-capture-1016]
def test_an_environment_key_wins_and_no_file_is_read(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", KEY)
    capture.load_key(tmp_path / "absent")
    assert os.environ["TYPESAFE_API_KEY"] == KEY


# am[verifies a-jev-live-smoke-1016]
def test_without_any_key_the_smoke_exits_2_and_says_why(tmp_path, no_key, capsys) -> None:
    assert capture.main(["--env-file", str(tmp_path / "absent"), "--cache", str(tmp_path / "c"),
                         "smoke", *CLI_LIMITS]) == 2
    assert "no TYPESAFE_API_KEY" in capsys.readouterr().err
    assert not (tmp_path / "c").exists()


# A process with no home directory imports the tool and starts the command, which asks for the key
# file by --env-file instead of failing as it is imported, and reads the file it is given.
# am[verifies a-dr-cache-home-typed-1018@63015f]
def test_with_no_home_the_command_asks_for_the_key_file_by_name(tmp_path, no_key, monkeypatch, capsys) -> None:
    script = ("import pathlib\n"
              "def no_home(cls):\n"
              "    raise RuntimeError('Could not determine home directory.')\n"
              "pathlib.Path.home = classmethod(no_home)\n"
              "import goal_chainer.semantic_capture\n")
    imported = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False,
                              env={**os.environ, "PYTHONPATH": str(Path(capture.__file__).resolve().parents[1])})
    assert imported.returncode == 0, imported.stderr

    def no_home(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", classmethod(no_home))
    assert capture.main(["--cache", str(tmp_path / "c"), "smoke", *CLI_LIMITS]) == 2
    assert "name the key file with --env-file" in capsys.readouterr().err
    assert capture.main(["--env-file", str(tmp_path / "absent"), "--cache", str(tmp_path / "c"),
                         "smoke", *CLI_LIMITS]) == 2
    assert "no TYPESAFE_API_KEY" in capsys.readouterr().err


# With the key already in the environment, a process with no home directory runs the command
# without looking for a key file at all, so it needs no --env-file; the smoke is stubbed, so
# nothing is asked of Jev.
# am[verifies a-dr-cache-home-typed-1018@63015f]
def test_with_no_home_an_environment_key_needs_no_key_file(tmp_path, monkeypatch, capsys) -> None:
    def no_home(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", classmethod(no_home))
    monkeypatch.setenv("TYPESAFE_API_KEY", KEY)
    monkeypatch.setattr(capture, "smoke", lambda cache, *, budget: {"cache": str(cache.directory)})

    assert capture.main(["--cache", str(tmp_path / "c"), "smoke", *CLI_LIMITS]) == 0
    assert '"cache"' in capsys.readouterr().out


# The smoke runs outside any request, so its command line must give the limits its domain read and
# its request run under: without them it is a usage error, before any key is read or request sent.
# am[verifies a-dr-sr-tool-budgets-1018@e4d351]
def test_the_smoke_takes_its_limits_from_its_command_line(tmp_path, no_key, capsys) -> None:
    assert capture.main(["--env-file", str(tmp_path / "absent"), "--cache", str(tmp_path / "c"), "smoke"]) == 2
    assert "--inference-budget" in capsys.readouterr().err
    assert not (tmp_path / "c").exists()


# An installed package has no tests to capture from and no checkout to hold the replay cache.
# am[verifies a-jev-capture-1016]
def test_outside_a_checkout_capture_refuses_and_smoke_needs_a_cache(tmp_path, no_key, monkeypatch, capsys) -> None:
    monkeypatch.setattr(capture, "REPO_ROOT", tmp_path / "site-packages")

    assert capture.main(["--env-file", str(tmp_path / "absent"), "capture"]) == 2
    assert capture.main(["--env-file", str(tmp_path / "absent"), "smoke", *CLI_LIMITS]) == 2
    assert "outside one, smoke needs --cache" in capsys.readouterr().err
    assert capture.main(["--env-file", str(tmp_path / "absent"), "--cache", str(tmp_path / "c"),
                         "smoke", *CLI_LIMITS]) == 2
    assert "no TYPESAFE_API_KEY" in capsys.readouterr().err


# am[verifies a-jev-capture-1016]
def test_the_plugin_logs_every_answer_read_and_caps_live_requests(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sr.AnswerCache, "get", sr.AnswerCache.get)
    monkeypatch.setattr(sr.JevClient, "_request", sr.JevClient._request)
    log = tmp_path / "read.log"
    monkeypatch.setenv(capture.READ_LOG_ENV, str(log))
    monkeypatch.setenv(capture.MAX_REQUESTS_ENV, "0")

    capture.pytest_configure(None)

    cache = sr.AnswerCache(tmp_path / "cache")
    assert cache.admit("k1", {"model": "jev-1.13.0", "probabilities": {"supported": 1.0, "contradicted": 0.0, "unknown": 0.0}})
    assert cache.get("k1") is not None and cache.get("absent") is None
    assert log.read_text(encoding="utf-8").split() == ["k1"]

    jev = sr.JevClient(cache, "jev-1.13.0")
    with pytest.raises(SystemExit, match="cap of 0"):
        jev._request({"text": "x"}, {}, {})


# am[verifies a-jev-capture-shards-1016@92ab34]
def test_the_plugin_logs_each_live_request_and_each_refusal_at_the_cap(tmp_path, monkeypatch) -> None:
    asked = []
    monkeypatch.setattr(sr.JevClient, "_request", lambda self, state, batch, keys: asked.append(state))
    monkeypatch.delenv(capture.READ_LOG_ENV, raising=False)
    requests = tmp_path / "requests.log"
    monkeypatch.setenv(capture.MAX_REQUESTS_ENV, "1")
    monkeypatch.setenv(capture.REQUEST_LOG_ENV, str(requests))

    capture.pytest_configure(None)

    jev = sr.JevClient(sr.AnswerCache(tmp_path / "cache"), "jev-1.13.0")
    jev._request({"text": "first"}, {}, {})
    with pytest.raises(SystemExit, match="cap of 1"):
        jev._request({"text": "second"}, {}, {})
    assert asked == [{"text": "first"}]
    assert requests.read_text(encoding="utf-8").split() == ["ask", "cap"]


# A parametrised test's ID can hold spaces, so the log keeps one node ID per line.
# am[verifies a-jev-capture-shards-1016@92ab34]
def test_the_plugin_lists_every_test_a_run_will_run(tmp_path, monkeypatch) -> None:
    log = tmp_path / "ran.log"
    monkeypatch.setenv(capture.COLLECT_LOG_ENV, str(log))
    session = SimpleNamespace(items=[SimpleNamespace(nodeid="tests/a.py::t[x y]"), SimpleNamespace(nodeid="tests/b.py::u")])

    capture.pytest_collection_finish(session)
    capture.pytest_collection_finish(session)

    assert log.read_text(encoding="utf-8").splitlines() == ["tests/a.py::t[x y]", "tests/b.py::u"] * 2


# Stands in for the pytest runs capture launches, through the same environment contract: an asking
# run makes the live requests its shard needs while the cap it was given lasts, logging each, and an
# offline run logs the answers it reads and the tests it ran; a collection lists the suite.
# am[verifies a-jev-capture-shards-1016@92ab34]
class Runs:
    def __init__(self, shards: dict[str, dict], suite: list[str]) -> None:
        self.shards = shards
        self.suite = suite
        self.offered: list[tuple[str, int]] = []
        self.replayed: list[str] = []

    def __call__(self, arguments: list[str], env: dict[str, str]) -> int:
        if "--collect-only" in arguments:
            _append(env[capture.COLLECT_LOG_ENV], self.suite)
            return 0
        name = arguments[-1]
        shard = self.shards[name]
        if env[sr.JEV_OFFLINE_ENV] == "0":
            left = int(env[capture.MAX_REQUESTS_ENV])
            self.offered.append((name, left))
            _append(env[capture.REQUEST_LOG_ENV], ["ask"] * min(shard["needs"], left))
            if shard["needs"] > left:
                _append(env[capture.REQUEST_LOG_ENV], ["cap"])
                return 1
            return 1 if shard.get("fails") else 0
        assert "TYPESAFE_API_KEY" not in env
        self.replayed.append(name)
        _append(env[capture.READ_LOG_ENV], shard["reads"])
        _append(env[capture.COLLECT_LOG_ENV], shard["tests"])
        return 0


# am[verifies a-jev-capture-shards-1016@92ab34]
def _append(path: str, lines: list[str]) -> None:
    with open(path, "a", encoding="utf-8") as stream:
        stream.writelines(f"{line}\n" for line in lines)


# am[verifies a-jev-capture-shards-1016@92ab34]
def _cache(tmp_path: Path, *keys: str) -> sr.AnswerCache:
    cache = sr.AnswerCache(tmp_path / "cache")
    for key in keys:
        assert cache.admit(key, {"model": "jev-1.13.0", "probabilities": {"supported": 1.0, "contradicted": 0.0, "unknown": 0.0}})
    return cache


# am[verifies a-jev-capture-shards-1016@92ab34]
def _stems(cache: sr.AnswerCache) -> set[str]:
    return {path.stem for path in cache.directory.glob("*.json")}


SHARDS = {
    "tests/a.py": {"needs": 2, "reads": ["k1"], "tests": ["tests/a.py::t"]},
    "tests/b.py": {"needs": 1, "reads": ["k2"], "tests": ["tests/b.py::u", "tests/b.py::v[x y]"]},
}
SUITE = ["tests/a.py::t", "tests/b.py::u", "tests/b.py::v[x y]"]


# am[verifies a-jev-capture-shards-1016@92ab34]
def test_shards_share_one_cap_and_prune_what_no_shard_read(tmp_path, monkeypatch, capsys) -> None:
    runs = Runs(SHARDS, SUITE)
    monkeypatch.setattr(capture, "_pytest", runs)
    cache = _cache(tmp_path, "k1", "k2", "k3")

    assert capture.capture([["tests/a.py"], ["tests/b.py"]], ["-q"], cache, 5) == 0

    assert runs.offered == [("tests/a.py", 5), ("tests/b.py", 3)]
    assert runs.replayed == ["tests/a.py", "tests/b.py"]
    assert _stems(cache) == {"k1", "k2"}
    out = capsys.readouterr().out
    assert "shard 1 of 2 (tests/a.py) asked 2 live Jev requests, 2 of the cap of 5 so far" in out
    assert "shard 2 of 2 (tests/b.py) asked 1 live Jev requests, 3 of the cap of 5 so far" in out
    assert "3 live Jev requests in all; offline replay passed; removed 1 unread answers" in out


# am[verifies a-jev-capture-shards-1016@92ab34]
def test_the_cap_stops_the_capture_before_later_shards_and_prunes_nothing(tmp_path, monkeypatch, capsys) -> None:
    runs = Runs(SHARDS, SUITE)
    monkeypatch.setattr(capture, "_pytest", runs)
    cache = _cache(tmp_path, "k1", "k2", "k3")

    assert capture.capture([["tests/a.py"], ["tests/b.py"]], [], cache, 1) == 1

    assert runs.offered == [("tests/a.py", 1)] and runs.replayed == []
    assert _stems(cache) == {"k1", "k2", "k3"}
    assert "stopped at the cap of 1 live Jev requests; nothing pruned" in capsys.readouterr().err


# am[verifies a-jev-capture-shards-1016@92ab34]
def test_shards_that_skip_a_suite_test_keep_every_unread_answer(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(capture, "_pytest", Runs(SHARDS, [*SUITE, "tests/c.py::w"]))
    cache = _cache(tmp_path, "k1", "k2", "k3")

    assert capture.capture([["tests/a.py"], ["tests/b.py"]], [], cache, 5) == 0

    assert _stems(cache) == {"k1", "k2", "k3"}
    assert "the shards ran 1 fewer tests than the suite, so unread answers are kept" in capsys.readouterr().out


# A shard whose tests fail still leaves the next shard asking, so one pass gathers every answer the
# cap allows; the failed shard is not replayed, since its tests would fail again.
# am[verifies a-jev-capture-shards-1016@92ab34]
def test_a_failing_shard_lets_the_others_ask_and_prunes_nothing(tmp_path, monkeypatch, capsys) -> None:
    runs = Runs({**SHARDS, "tests/a.py": {**SHARDS["tests/a.py"], "fails": True}}, SUITE)
    monkeypatch.setattr(capture, "_pytest", runs)
    cache = _cache(tmp_path, "k1", "k2", "k3")

    assert capture.capture([["tests/a.py"], ["tests/b.py"]], [], cache, 5) == 1

    assert runs.offered == [("tests/a.py", 5), ("tests/b.py", 3)] and runs.replayed == ["tests/b.py"]
    assert _stems(cache) == {"k1", "k2", "k3"}
    assert "shards [1] failed; nothing pruned" in capsys.readouterr().err


# Whatever each shard needs, no shard is offered more than the cap leaves, the capture stops at the
# first shard that needs more, and it reports every request it made.
# am[verifies a-jev-capture-shards-1016@92ab34]
@settings(max_examples=60, deadline=None, derandomize=True)
@given(needs=st.lists(st.integers(min_value=0, max_value=6), min_size=1, max_size=5), cap=st.integers(min_value=0, max_value=12))
def test_shards_never_ask_past_the_cap(tmp_path_factory, needs, cap) -> None:
    names = [f"tests/s{index}.py" for index in range(len(needs))]
    shards = {name: {"needs": need, "reads": [], "tests": [f"{name}::t"]} for name, need in zip(names, needs)}
    runs = Runs(shards, [f"{name}::t" for name in names])
    cache = _cache(tmp_path_factory.mktemp("capture"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(capture, "_pytest", runs)
        status = capture.capture([[name] for name in names], [], cache, cap)

    spent = 0
    for (name, offered), need in zip(runs.offered, needs):
        assert offered == cap - spent
        spent += min(need, offered)
    stopped = next((index for index, need in enumerate(needs) if need > cap - sum(needs[:index])), None)
    assert len(runs.offered) == (len(needs) if stopped is None else stopped + 1)
    assert status == (0 if stopped is None else 1)
    assert spent <= cap


# am[verifies a-jev-capture-shards-1016@92ab34]
def test_capture_takes_each_shard_as_one_quoted_argument(tmp_path, monkeypatch) -> None:
    seen = []
    monkeypatch.setenv("TYPESAFE_API_KEY", KEY)
    monkeypatch.setattr(capture, "capture", lambda shards, common, cache, cap: seen.append((shards, common, cap)) or 0)

    argv = ["--cache", str(tmp_path / "c"), "capture", "--max-requests", "7",
            "--shard", "tests/a.py -k 'x and y'", "--shard", "tests/b.py", "-q"]
    assert capture.main(argv) == 0
    assert seen == [([["tests/a.py", "-k", "x and y"], ["tests/b.py"]], ["-q"], 7)]
    assert capture.main(["--cache", str(tmp_path / "c"), "capture", "--max-requests", "-1"]) == 2


# Each shard's count reaches a redirected, block-buffered log before the next pytest run writes to
# it, so a long capture shows its progress, in order, while it runs. The pytest runs are stood in
# for at subprocess.run, so the real _pytest runs.
# am[verifies a-jev-capture-shards-1016@92ab34] am[verifies i-capture-progress-buffered-1017@73c83f]
def test_each_shard_count_reaches_a_redirected_log_before_the_next_run(tmp_path, monkeypatch) -> None:
    runs = Runs(SHARDS, SUITE)
    log = tmp_path / "capture.log"
    on_disk: list[str] = []

    def run(command, cwd, env, check):
        on_disk.append(log.read_text(encoding="utf-8"))
        return SimpleNamespace(returncode=runs(command[5:], env))

    monkeypatch.setattr(capture.subprocess, "run", run)
    with open(log, "w", encoding="utf-8") as stream:
        monkeypatch.setattr(sys, "stdout", stream)
        assert capture.capture([["tests/a.py"], ["tests/b.py"]], [], _cache(tmp_path, "k1", "k2"), 5) == 0

    # The runs are: shard 1 asking and offline, shard 2 asking and offline, the suite's collection.
    assert "shard 1 of 2" in on_disk[1] and "shard 2 of 2" not in on_disk[1]
    assert "shard 2 of 2" in on_disk[3]


# Run the plugin's own tests the way a capture runs them, its four logs set, and nothing may reach
# those logs: a refusal one test expects once landed in a capture's request log and stopped the
# capture as if capped (i-capture-plugin-test-leaks-1017).
# am[verifies a-jev-capture-plugin-tests-hermetic-1017@a243e1]
def test_the_plugin_tests_write_nothing_into_a_capture_running_them(tmp_path) -> None:
    logs = {name: tmp_path / f"{name}.log" for name in CAPTURE_ENV if name != capture.MAX_REQUESTS_ENV}
    env = {**os.environ, **{name: str(path) for name, path in logs.items()}, capture.MAX_REQUESTS_ENV: "5"}
    plugin_tests = [
        f"{__file__}::{name}"
        for name in (
            "test_the_plugin_logs_every_answer_read_and_caps_live_requests",
            "test_the_plugin_logs_each_live_request_and_each_refusal_at_the_cap",
            "test_the_plugin_lists_every_test_a_run_will_run",
        )
    ]
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *plugin_tests],
        cwd=capture.REPO_ROOT, env=env, capture_output=True, text=True, check=False,
    )

    assert run.returncode == 0, run.stdout[-2000:]
    assert {name: path.read_text(encoding="utf-8") for name, path in logs.items() if path.exists()} == {}


# A plugin a child pytest loads to report the Jev settings its run reads at the start of the session,
# once every pytest_configure, tests/conftest.py's included, has run, and again at its end, once every
# test it ran has been torn down.
OBSERVER = (
    "import json, os\n\n\n"
    "STARTED = []\n\n\n"
    "def read():\n"
    f"    return [os.environ.get({sr.JEV_OFFLINE_ENV!r}), 'TYPESAFE_API_KEY' in os.environ]\n\n\n"
    "def pytest_sessionstart(session):\n"
    "    STARTED[:] = read()\n\n\n"
    "def pytest_sessionfinish(session, exitstatus):\n"
    f"    with open(os.environ[{JEV_REPORT_ENV!r}], 'w', encoding='utf-8') as report:\n"
    "        json.dump({'start': STARTED, 'finish': read()}, report)\n"
)


# Environments a pytest run might start in, and what conftest leaves it to read: an inherited empty
# or 0 switch with a key, a capture cap without the capture plugin, or the plugin without its cap,
# all read offline with no key; only the capture's asking run, plugin and cap together, keeps the 0
# and the key it was given.
ONLINE = {sr.JEV_OFFLINE_ENV: "0", "TYPESAFE_API_KEY": KEY}
STARTS = {
    "inherited-empty": ({**ONLINE, sr.JEV_OFFLINE_ENV: ""}, False, ["1", False]),
    "inherited-zero": (ONLINE, False, ["1", False]),
    "cap-without-plugin": ({**ONLINE, capture.MAX_REQUESTS_ENV: "5"}, False, ["1", False]),
    "plugin-without-cap": (ONLINE, True, ["1", False]),
    "capture-asking-run": ({**ONLINE, capture.MAX_REQUESTS_ENV: "5"}, True, ["0", True]),
}


# A child pytest from the checkout, as the capture runs the suite, so tests/conftest.py loads as
# pytest finds it, with OBSERVER loaded: what its run read at its start and at its end.
# Time: one pytest start and one collection of this module.
# am[verifies a-dr-suite-offline-unless-capture-1018@f388c2]
def _child_reads(tmp_path: Path, env: dict[str, str], arguments: list[str]) -> dict[str, list]:
    (tmp_path / "jev_observer.py").write_text(OBSERVER, encoding="utf-8")
    report = tmp_path / "jev.json"
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "jev_observer", *arguments],
        cwd=capture.REPO_ROOT,
        env={**os.environ, **env, JEV_REPORT_ENV: str(report), "PYTHONPATH": str(tmp_path)},
        capture_output=True, text=True, check=False,
    )
    assert run.returncode == 0, run.stdout[-2000:]
    return json.loads(report.read_text(encoding="utf-8"))


# Each start only collects this module, so the child runs no test and asks Jev nothing.
# am[verifies a-dr-suite-offline-unless-capture-1018@f388c2] am[verifies a-tbr-jev-exempt-needs-capture-plugin-1018@303e5c]
@pytest.mark.parametrize(("start", "plugin", "expected"), STARTS.values(), ids=STARTS.keys())
def test_only_the_captures_asking_run_reads_jev_live(tmp_path, start, plugin, expected) -> None:
    plugins = ["-p", "goal_chainer.semantic_capture"] if plugin else []

    assert _child_reads(tmp_path, start, ["--collect-only", *plugins, __file__])["start"] == expected


# The tests that read a key from a file leave none behind them: the run ends without a key, as it
# began, so no later test of the session meets one.
# am[verifies a-dr-suite-offline-unless-capture-1018@f388c2]
def test_a_key_read_from_a_file_does_not_outlive_its_test(tmp_path) -> None:
    tests = [f"{__file__}::{name}" for name in ("test_the_key_is_read_from_its_line_in_a_private_file",
                                                 "test_a_read_only_private_file_is_accepted")]

    assert _child_reads(tmp_path, {}, tests) == {"start": ["1", False], "finish": ["1", False]}


# The plugin suite's runner gives each file's process the replay settings whatever it inherits, an
# online switch and a key included, since no capture runs it and its skill processes carry no cap.
# It runs from a copy beside a stand-in Omega checkout, and a stand-in interpreter reports what each
# file's process reads.
# am[verifies a-tbr-plugin-suite-replays-1018@53843d]
def test_the_plugin_suite_runner_replays_whatever_it_inherits(tmp_path) -> None:
    tree = tmp_path / "goalchainer"
    for path in ("plugins/goalchainer/tests/run.sh", "integrations/omegaclaw/_omega_lib.sh"):
        (tree / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(capture.REPO_ROOT / path, tree / path)
    (tree / "plugins/goalchainer/tests/test_probe.metta").write_text("!(println! probe)\n", encoding="utf-8")
    omega = tmp_path / "omega"
    (omega / "plugins" / "goalchainer").mkdir(parents=True)
    report = tmp_path / "jev.txt"
    python = tmp_path / "python"
    python.write_text(f"#!/bin/sh\nprintf '%s %s\\n' \"$GOALCHAINER_JEV_OFFLINE\" \"${{TYPESAFE_API_KEY:+key}}\" > '{report}'\n"
                      "echo '✅ probe'\n", encoding="utf-8")
    python.chmod(0o755)

    run = subprocess.run(["bash", str(tree / "plugins/goalchainer/tests/run.sh")], capture_output=True, text=True,
                         check=False, env={"PATH": "/usr/bin:/bin", "OMEGACLAW_DIR": str(omega),
                                           "GOALCHAINER_PYTHON": str(python), **ONLINE})

    assert run.returncode == 0, run.stdout + run.stderr
    assert report.read_text(encoding="utf-8") == "1 \n"

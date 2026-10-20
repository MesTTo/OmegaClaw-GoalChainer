"""Purpose: capture the Jev answers GoalChainer's tests replay, and smoke-test one live Jev request.

`smoke --inference-budget N --timeout-seconds S` sends one request, the incident domain's reading
questions about one short incident text, within those limits, checks the answering model and every
answer's options, stores the answers in the replay cache, and reports how many met a different
answer already stored under the same key, which stands. `capture
[--max-requests N] [--shard ARGS]... [pytest args]` runs each shard's tests once asking Jev for
every answer the replay cache lacks, then again offline, which must pass. The shards run one after
another into the same cache, under one cap on live requests, and the pytest args go to every
shard; without --shard the suite is one shard. It reports the live requests each shard asked. When
every offline run passed and the shards' tests together are the whole suite, it deletes every
cached answer no offline run read, as multinetmetta's tools/refresh_test_answers.py does (vcrpy's
new_episodes then none record modes, at the level of the answer cache).

The key comes from TYPESAFE_API_KEY, or else from a file of yours that no other user can read or
write (mode 600, or 400) holding a TYPESAFE_API_KEY=... line (default ~/.config/typesafe/env, or
--env-file). It is never printed. Exit codes: 0 done, 1 a test run failed or Jev did not answer,
or the cap stopped the asking, 2 usage or no usable key.

Usage, from the checkout:
    uv run --frozen --extra dev --extra semantic python -m goal_chainer.semantic_capture smoke \
        --inference-budget 1000000 --timeout-seconds 120
    uv run --frozen --extra dev --extra semantic python -m goal_chainer.semantic_capture capture
    uv run --frozen --extra dev --extra semantic python -m goal_chainer.semantic_capture capture \
        --shard "tests/test_reading_contract.py tests/test_domain_requests.py" --shard "-k 'not native'" -q
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .runtime.engine import child_environment
from .runtime.budget import RunBudget
from .semantic_reader import (
    JEV_CACHE_ENV,
    JEV_OFFLINE_ENV,
    AnswerCache,
    JevClient,
    default_reader,
)
from .errors import GoalChainerError

REPO_ROOT = Path(__file__).resolve().parents[2]
REPLAY_CACHE = REPO_ROOT / "tests" / "data" / "jev"
READ_LOG_ENV = "GOALCHAINER_JEV_CAPTURE_LOG"
MAX_REQUESTS_ENV = "GOALCHAINER_JEV_MAX_REQUESTS"
REQUEST_LOG_ENV = "GOALCHAINER_JEV_CAPTURE_REQUESTS"
COLLECT_LOG_ENV = "GOALCHAINER_JEV_CAPTURE_TESTS"
SMOKE_TEXT = (
    "Checkout is down. Raw logs include customer emails. Engineering needs the incident room."
)


# am[implements a-jev-capture-1016@3f3b27]
class UsageError(Exception):
    """The command cannot run as asked; the message says why."""


# The key file the operator was asked to keep, ~/.config/typesafe/env, found only when a key must be
# read from it, so a process with no home directory still starts, needs no file when the key is in
# its environment, and can name its file with --env-file otherwise.
# am[implements a-jev-capture-1016@3f3b27] am[implements a-dr-cache-home-typed-1018@63015f]
def default_env_file() -> Path:
    try:
        return Path.home() / ".config" / "typesafe" / "env"
    except RuntimeError as error:
        raise UsageError("no home directory can be found, so name the key file with --env-file") from error


# am[implements a-jev-capture-1016@3f3b27] am[implements a-dr-cache-home-typed-1018@63015f]
def load_key(env_file: Path | None) -> None:
    """Put TYPESAFE_API_KEY into this process's environment from env_file, by default
    default_env_file(), when it is not set; when it is, no file is read or even looked for.

    The file must be a regular file owned by this user with no group or other permission bits, the
    protection the operator was asked to give it (mode 600); only its TYPESAFE_API_KEY line is read,
    and nothing executes.
    """

    if os.environ.get("TYPESAFE_API_KEY", "").strip():
        return
    env_file = default_env_file() if env_file is None else env_file
    try:
        info = env_file.stat()
    except FileNotFoundError as error:
        raise UsageError(f"no TYPESAFE_API_KEY in the environment and no key file at {env_file}") from error
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise UsageError(
            f"{env_file} must be a regular file of yours that no other user can read or write "
            "(chmod 600)"
        )
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.strip().removeprefix("export ").partition("=")
        if separator and name.strip() == "TYPESAFE_API_KEY":
            key = value.strip().strip("'\"")
            if key:
                os.environ["TYPESAFE_API_KEY"] = key
                return
    raise UsageError(f"{env_file} holds no TYPESAFE_API_KEY line")


# The smoke runs outside any decide or solve request, under the limits its command line gives, which
# bound reading the incident domain's declaration and the request alike.
# am[implements a-jev-live-smoke-1016@553d4e] am[implements a-dr-reader-budget-required-1018@0b0cce]
# am[implements a-dr-sr-tool-budgets-1018@e4d351]
def smoke(cache: AnswerCache, *, budget: RunBudget) -> dict[str, Any]:
    """One live request within budget: every reading question about SMOKE_TEXT, answers stored in
    cache."""

    declaration = default_reader(budget=budget).declaration
    jev = JevClient(cache, declaration.model)
    try:
        questions = declaration.questions()
        answers = jev.answers({"text": SMOKE_TEXT}, questions, budget=budget)
    finally:
        jev.close()
    return {
        "model": next(iter(answers.values())).model,
        "requests": jev.requests,
        "input_tokens": jev.input_tokens,
        "conflicts": jev.conflicts,
        "answers": {q: answers[q].decided() for q in questions},
        "cache": str(cache.directory),
    }


# Whatever the capture printed reaches its log before this run writes to the same stream, so a
# redirected log reads in order and shows each shard's count while the next shard runs; print to
# a file is block-buffered, and the counts otherwise appeared only when the capture exited.
# am[implements a-jev-capture-1016@3f3b27] am[addresses i-capture-progress-buffered-1017@73c83f]
def _pytest(arguments: list[str], env: dict[str, str]) -> int:
    sys.stdout.flush()
    sys.stderr.flush()
    command = [sys.executable, "-m", "pytest", "-p", "goal_chainer.semantic_capture", *arguments]
    return subprocess.run(command, cwd=REPO_ROOT, env=env, check=False).returncode


# am[implements a-jev-capture-shards-1016@92ab34]
def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


# Shards bound how long one pytest run takes, so no run has to cover the suite: each shard asks into
# the same cache under what is left of one request cap, and a shard that fails to ask leaves the
# others asking, so one pass still gathers every answer it can. A prune deletes what no offline run
# read, so it runs only when the tests the offline runs ran are every test the suite collects,
# whatever the shards were. The logs the pytest runs write live in a scratch directory under
# TMPDIR, never in the cache, which is committed.
# Time: two pytest runs per shard, plus one collection of the suite when every shard passes.
# am[implements a-jev-capture-shards-1016@92ab34] am[implements a-integrate-petta-child-engine-environment-1017@8f59bb]
def capture(shards: list[list[str]], common: list[str], cache: AnswerCache, max_requests: int) -> int:
    """Ask, then replay offline, shard by shard; prune what no offline run read once the shards'
    tests are the suite's."""

    shards = shards or [[]]
    base = dict(child_environment(), **{JEV_CACHE_ENV: str(cache.directory)})
    offline_env = {key: value for key, value in base.items() if key != "TYPESAFE_API_KEY"}
    asked = 0
    failed: list[int] = []
    with tempfile.TemporaryDirectory(prefix="goalchainer-capture-") as scratch:
        logs = Path(scratch)
        for number, shard in enumerate(shards, start=1):
            arguments = [*common, *shard]
            requests = logs / f"requests-{number}.log"
            status = _pytest(arguments, {
                **base, JEV_OFFLINE_ENV: "0", MAX_REQUESTS_ENV: str(max_requests - asked),
                REQUEST_LOG_ENV: str(requests),
            })
            events = _lines(requests)
            asked += events.count("ask")
            print(
                f"capture: shard {number} of {len(shards)} ({shlex.join(shard) or 'the whole suite'}) "
                f"asked {events.count('ask')} live Jev requests, {asked} of the cap of {max_requests} so far"
            )
            if "cap" in events:
                print(f"capture: stopped at the cap of {max_requests} live Jev requests; nothing pruned",
                      file=sys.stderr)
                return 1
            if status != 0:
                print(f"capture: shard {number}'s asking run failed with status {status}", file=sys.stderr)
                failed.append(number)
                continue
            status = _pytest(arguments, {
                **offline_env, JEV_OFFLINE_ENV: "1", READ_LOG_ENV: str(logs / "read.log"),
                COLLECT_LOG_ENV: str(logs / "ran.log"),
            })
            if status != 0:
                print(f"capture: shard {number}'s offline run failed with status {status}", file=sys.stderr)
                failed.append(number)
        if failed:
            print(f"capture: {asked} live Jev requests in all; shards {failed} failed; nothing pruned",
                  file=sys.stderr)
            return 1
        status = _pytest(["--collect-only", "-q", *common], {**offline_env, COLLECT_LOG_ENV: str(logs / "suite.log")})
        missing = set(_lines(logs / "suite.log")) - set(_lines(logs / "ran.log"))
        if status != 0 or missing:
            print(
                f"capture: {asked} live Jev requests in all; offline replay passed; the shards ran "
                f"{'an uncollectable suite' if status else f'{len(missing)} fewer tests than the suite'}, "
                "so unread answers are kept"
            )
            return 0
        read = set(_lines(logs / "read.log"))
        removed = 0
        for path in cache.directory.glob("*.json"):
            if path.stem not in read:
                path.unlink()
                removed += 1
    print(f"capture: {asked} live Jev requests in all; offline replay passed; removed {removed} unread answers")
    return 0


# --- the pytest plugin both capture runs load with `-p goal_chainer.semantic_capture` ---


# am[implements a-jev-capture-1016@3f3b27] am[implements a-jev-capture-shards-1016@92ab34]
def pytest_configure(config: Any) -> None:
    """Record every answer key the offline run reads, and stop the asking run at its request cap,
    logging each live request it makes as `ask` and each it refuses as `cap`."""

    del config
    log = os.environ.get(READ_LOG_ENV)
    if log:
        original_get = AnswerCache.get

        def logged_get(self: AnswerCache, key: str) -> Any:
            found = original_get(self, key)
            if found is not None:
                with open(log, "a", encoding="utf-8") as stream:
                    stream.write(key + "\n")
            return found

        AnswerCache.get = logged_get  # type: ignore[method-assign]
    cap = os.environ.get(MAX_REQUESTS_ENV)
    if cap:
        limit = int(cap)
        requests = os.environ.get(REQUEST_LOG_ENV)
        original_request = JevClient._request
        made = {"count": 0}

        def logged(event: str) -> None:
            if requests:
                with open(requests, "a", encoding="utf-8") as stream:
                    stream.write(event + "\n")

        # A request Jev refuses as too long is split and asked again by _request itself, through
        # this wrapper, so every live request is counted once, the refused one included.
        def capped_request(self: JevClient, state: Any, batch: Any, keys: Any) -> None:
            if made["count"] >= limit:
                logged("cap")
                raise SystemExit(f"capture: stopped at the cap of {limit} live Jev requests")
            made["count"] += 1
            logged("ask")
            original_request(self, state, batch, keys)

        JevClient._request = capped_request  # type: ignore[method-assign]


# am[implements a-jev-capture-shards-1016@92ab34]
def pytest_collection_finish(session: Any) -> None:
    """Append the node ID of every test this run will run, after deselection, when the capture
    asks for them."""

    tests = os.environ.get(COLLECT_LOG_ENV)
    if tests:
        with open(tests, "a", encoding="utf-8") as stream:
            stream.writelines(f"{item.nodeid}\n" for item in session.items)


# am[implements a-jev-capture-1016@3f3b27] am[implements a-jev-capture-shards-1016@92ab34]
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m goal_chainer.semantic_capture")
    parser.add_argument("--env-file", type=Path, default=None, help="the key file, by default ~/.config/typesafe/env")
    parser.add_argument("--cache", type=Path, default=REPLAY_CACHE)
    sub = parser.add_subparsers(dest="command", required=True)
    smoke_parser = sub.add_parser("smoke", help="ask Jev one request and check its answers")
    smoke_parser.add_argument("--inference-budget", type=int, required=True,
                              help="maximum engine inferences for the smoke")
    smoke_parser.add_argument("--timeout-seconds", type=float, required=True,
                              help="wall-clock limit for the smoke")
    run = sub.add_parser("capture", help="refill the replay cache from the tests' requests")
    run.add_argument("--max-requests", type=int, default=200)
    run.add_argument(
        "--shard", action="append", default=[], metavar="ARGS",
        help="pytest arguments for one shard, quoted as one word; repeat for more shards, run in order",
    )
    try:
        args, rest = parser.parse_known_args(argv)
    except SystemExit as exit_:
        return 2 if exit_.code else 0
    if (args.command == "smoke" and rest) or (args.command == "capture" and args.max_requests < 0):
        parser.print_usage(sys.stderr)
        return 2
    # capture runs a checkout's own tests and refills its tests/data/jev, so both need a checkout;
    # an installed package has neither, and smoke there must be told where to store its answers.
    in_checkout = (REPO_ROOT / "pyproject.toml").is_file() and (REPO_ROOT / "tests").is_dir()
    if not in_checkout and (args.command == "capture" or args.cache == REPLAY_CACHE):
        print(
            "semantic-capture: capture runs from a GoalChainer checkout; outside one, smoke needs --cache",
            file=sys.stderr,
        )
        return 2
    try:
        load_key(args.env_file)
    except UsageError as error:
        print(f"semantic-capture: {error}", file=sys.stderr)
        return 2
    cache = AnswerCache(args.cache.absolute())
    try:
        if args.command == "smoke":
            budget = RunBudget(inference_budget=args.inference_budget, timeout_seconds=args.timeout_seconds)
            print(json.dumps(smoke(cache, budget=budget), indent=2, sort_keys=True))
            return 0
        return capture([shlex.split(shard) for shard in args.shard], rest, cache, args.max_requests)
    except GoalChainerError as error:
        print(f"semantic-capture: {json.dumps(error.to_dict(), sort_keys=True)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["capture", "load_key", "main", "smoke"]

"""Purpose: measure how a motivation snapshot's cost grows with its stream: for streams of m attempts,
each with a baseline and an attributed outcome observation, the policy's inferences and seconds,
and separately the seconds to read the same stream back from its store file, as JSON lines.

Run from a provisioned checkout with the test fixtures on the path:

    PYTHONPATH=src:tests python -m benchmarks.motivation --attempts 10 40 160 640 2560

The first line identifies the engine, the revision, the Python and the digest of the motivation
policy file measured, which names the code even where the tree differs from the revision. Each
following line is one stream size. The snapshot's first call in a process prepares the policy,
which no review is charged for, so a warm-up stream runs first and is not reported.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import platform
import subprocess
import tempfile
import time
from pathlib import Path

from goal_chainer.motivation import MotivationStore
from goal_chainer.relevance.motivation import motivation_snapshot
from goal_chainer.relevance.policy import POLICY_DIRECTORY
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.runtime.engine import metta_engine, pymetta_identity
from motivation_support import Att, History, Obs, at, domain


# A stream of m attempts cycling through the domain's actions, each between a baseline of one need
# and the outcome it produced, ten seconds apart, so every attempt gives one sample.
# am[implements a-v2m-snapshot-sweep-1020@fefbd6]
def stream(m: int, actions: tuple[str, ...]) -> tuple[list, list]:
    observations, attempts = [], []
    for k in range(m):
        base = 10.0 * k
        observations.append(Obs("nurture", 0.3 + 0.001 * (k % 7), at(base), name=f"b{k}"))
        attempts.append(Att(f"a{k:06d}", actions[k % len(actions)], at(base + 1)))
        observations.append(Obs("nurture", 0.4 + 0.001 * (k % 5), at(base + 2), produced_by=f"a{k:06d}", name=f"o{k}"))
    return observations, attempts


# One row per stream size: the policy's inferences and seconds on the stream held in memory, the
# samples it found, and the seconds to read the stream back from a store file written beforehand.
# Time: the snapshot's own cost per size plus one batch append and one read of 3m records.
# am[implements a-v2m-snapshot-sweep-1020@fefbd6]
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--attempts", type=int, nargs="+", required=True)
    args = parser.parse_args(argv)
    regulated = domain()
    revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    with metta_engine(RunBudget(inference_budget=None, timeout_seconds=600)) as engine:
        identity = asdict(pymetta_identity(engine))
    policy = POLICY_DIRECTORY / "motivation.metta"
    print(json.dumps({"engine": identity, "revision": revision, "python": platform.python_version(),
                      "policy": "sha256:" + hashlib.sha256(policy.read_bytes()).hexdigest()}), flush=True)
    warm = stream(2, regulated.action_ids)
    motivation_snapshot(regulated, History(*warm), stream="warm", as_of=at(100),
                        budget=RunBudget(inference_budget=None, timeout_seconds=600))
    with tempfile.TemporaryDirectory(dir=Path.cwd() / "ai-tmp") as scratch:
        for m in args.attempts:
            observations, attempts = stream(m, regulated.action_ids)
            budget = RunBudget(inference_budget=None, timeout_seconds=3600)
            started = time.perf_counter()
            taken = motivation_snapshot(regulated, History(observations, attempts), stream="bench",
                                        as_of=at(10.0 * m + 5), budget=budget)
            policy_seconds = time.perf_counter() - started
            path = Path(scratch) / f"stream-{m}.sqlite3"
            with MotivationStore(path, stream="bench") as store:
                store.record(regulated, observations=observations, attempts=attempts)
            started = time.perf_counter()
            with MotivationStore(path, stream="bench", create=False) as store:
                history = store.history()
            read_seconds = time.perf_counter() - started
            print(json.dumps({"attempts": m, "observations": len(observations), "samples": len(taken.samples),
                              "inferences": budget.spent, "policy_seconds": round(policy_seconds, 4),
                              "read_records": len(history.observations) + len(history.attempts),
                              "read_seconds": round(read_seconds, 4)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Purpose: measure native, ECAN and seeded random scheduling under whole-query budgets."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import platform
import random
import time
from typing import Any

# am[implements a-integrate-parent-artifacts-compose-1018@e3c6d7]
from goal_chainer.runtime.budget import InferenceBudgetExceeded, ReviewTimeout, RunBudget, run_bounded
from goal_chainer.runtime.engine import metta_engine, pymetta_identity
from goal_chainer.runtime.modules import load_metta_module, register_metta_library
from goal_chainer.sexpr.codec import SexprCodec
from goal_chainer.sexpr.protocol import atom_to_python
from goal_chainer.snars_program import SNARS_DIRECTORY, SNARS_LIBRARY, world_modules

ARMS = ("native", "ecan", "random")
SPACE = "&goalchainer-attention-benchmark"
CODEC = SexprCodec()


# Counter-based sampling gives each pair one rank without process-global random state.
# Time and space: linear in the premise identifiers' text length.
# am[implements a-integrate-cairn-harness-1018@4ba2ae]
def random_priority(seed: int, left: Any, right: Any) -> float:
    return random.Random(json.dumps([seed, str(left), str(right)])).random()


# am[implements a-integrate-cairn-harness-1018@4ba2ae]
@dataclass(frozen=True)
class Workload:
    edges: tuple[tuple[str, str], ...]
    goal: tuple[str, str]

    # am[implements a-integrate-cairn-harness-1018@4ba2ae]
    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


# Distractor components create real derivable work; none changes the target chain.
# Time and space: O(length + distractors) edges.
# am[implements a-integrate-cairn-harness-1018@4ba2ae]
def chain(length: int, distractors: int, *, missing: bool = False) -> Workload:
    if length < 1 or distractors < 0:
        raise ValueError("length must be positive and distractors nonnegative")
    edges = [(f"chain-{i}", f"chain-{i + 1}") for i in range(length)]
    if missing:
        del edges[length // 2]
    edges.extend((f"other-{j}-{i}", f"other-{j}-{i + 1}")
                 for j in range(distractors) for i in range(2))
    return Workload(tuple(edges), ("chain-0", f"chain-{length}"))


# Names are quoted by the existing codec; no benchmark label becomes executable text.
# am[implements a-integrate-cairn-harness-1018@4ba2ae]
def statement(edge: tuple[str, str]) -> str:
    left, right = (CODEC.emit(CODEC.string(value)) for value in edge)
    return f'(sn p so "is" ((arg s (sn c {left})) (arg o (sn c {right}))))'


# Compilation is fixed startup work, reported separately from each warm query.
# Time: module loading and hashing once per process; later calls verify loader identities.
# The SNARS library is registered as startup work outside any request, so with no budget.
# am[implements a-integrate-cairn-harness-1018@4ba2ae] am[implements a-integrate-attention-fixture-closure-1018@05ac6b]
def prepare() -> dict[str, Any]:
    started = time.perf_counter()
    with metta_engine(None) as engine:
        space = engine.space(SPACE)
        register_metta_library(SNARS_LIBRARY.name, SNARS_DIRECTORY, budget=None)
        modules = [SNARS_LIBRARY, *world_modules(frozenset({"attention"})),
                   Path(__file__).with_suffix(".metta")]
        identities = [(str(module), load_metta_module(engine, module, space=space))
                      for module in modules]
        identity = asdict(pymetta_identity(engine))
    return {"runtime": identity, "modules": identities,
            "python": platform.python_version(),
            "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "preparation_seconds": time.perf_counter() - started}


# One budget bounds the whole query: its deadline ends the wait for the engine, and one bounded
# call shares replay, admission, attention construction, search and invariant reads.
# Search cost is output-sensitive and bounded by the caller, not by a benchmark step cutoff.
# am[implements a-integrate-cairn-harness-1018@4ba2ae] am[implements a-integrate-benchmark-hold-budget-1018@1bd14c]
def run(workload: Workload, arm: str, *, seed: int, budget: RunBudget) -> dict[str, Any]:
    started = time.perf_counter()
    if arm not in ARMS:
        raise ValueError(f"unknown schedule: {arm}")
    effects = [f"(add-atom &self (gc-benchmark {arm} {seed}))"]
    effects.extend(f'(believe! {statement(edge)} ((evidence 8 0) '
                   f'(source "edge-{i}") (trust 1.0)))'
                   for i, edge in enumerate(workload.edges))
    bindings = " ".join(f"($effect-{i} {effect})" for i, effect in enumerate(effects))
    source = (f"!(let* ({bindings} ($before (gc-benchmark-evidence)) "
              f"($answer (gc forward-query-record {statement(workload.goal)})) "
              "($after (gc-benchmark-evidence))) "
              "(Benchmark $answer (== $before $after) $after))")
    result: dict[str, Any] = {"workload": workload.digest, "arm": arm, "seed": seed,
                             "inference_budget": budget.inference_budget,
                             "timeout_seconds": budget.timeout_seconds}
    try:
        with metta_engine(budget) as engine:
            space = engine.space(SPACE)
            with space.speculative(), space.capture():
                answers, _ = run_bounded(space, source, budget=budget)
        rows = [atom_to_python(CODEC.parse(str(atom)), CODEC)
                for group in answers for atom in group]
        if len(rows) != 1 or len(rows[0]) != 4 or rows[0][0] != "Benchmark":
            raise RuntimeError(f"unexpected benchmark answer: {rows}")
        _, record, stable, receipts = rows[0]
        if stable not in ("True", True):
            raise RuntimeError("scheduling changed receipt identities or source trust")
        if record[:3] != ["goalchainer-snars-v1", "forward-query", "ok"]:
            raise RuntimeError(f"unexpected query record: {record}")
        fields = {row[0]: row[1] for row in record[3][1:]}
        result.update(status=fields["status"], steps=fields["steps"],
                      answers=fields["answers"], receipts=receipts)
    except (InferenceBudgetExceeded, ReviewTimeout) as error:
        result.update(status=type(error).__name__, answers=None, steps=None)
    result.update(inferences=budget.spent, seconds=time.perf_counter() - started)
    return result


# The caller declares the experimental grid; rows are streamed so interruption preserves results.
# Time: the sum of measured query costs over the explicit grid. Space: one experiment row.
# am[implements a-integrate-cairn-harness-1018@4ba2ae]
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lengths", type=int, nargs="+", required=True)
    parser.add_argument("--distractors", type=int, nargs="+", required=True)
    parser.add_argument("--budgets", type=int, nargs="+", required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--seconds", type=float, required=True)
    args = parser.parse_args()
    # Validate the whole grid before compiling a world or emitting a partial experiment.
    for length in args.lengths:
        for distractors in args.distractors:
            chain(length, distractors)
    for limit in args.budgets:
        RunBudget(inference_budget=limit, timeout_seconds=args.seconds)
    print(json.dumps({"kind": "setup", **prepare()}), flush=True)
    workloads = (chain(length, distractors, missing=missing)
                 for length in args.lengths for distractors in args.distractors
                 for missing in (False, True))
    for workload in workloads:
        print(json.dumps({"kind": "workload", "digest": workload.digest,
                          **asdict(workload)}), flush=True)
        for limit in args.budgets:
            for seed in args.seeds:
                arms = list(ARMS)
                random.Random(seed).shuffle(arms)
                for arm in arms:
                    budget = RunBudget(inference_budget=limit, timeout_seconds=args.seconds)
                    print(json.dumps({"kind": "query", **run(workload, arm, seed=seed,
                                                              budget=budget)}), flush=True)


if __name__ == "__main__":
    main()

"""Purpose: compare the current planner and a preserved experimental composer on generated finite
worlds, recording bounded computation separately from independently simulated goal outcomes.

This development command uses the acceptance suite's World renderer and independent oracle.
Run with PYTHONPATH=src:tests. It never executes host actions or calls a text provider.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import random
import subprocess
import time

from goal_chainer.domains.loader import read_domain
from goal_chainer.errors import ProtocolError
from goal_chainer.planning.group import PLANNING
from goal_chainer.planning.procedures import library_term, literal_term, read_procedures
from goal_chainer.planning.projection import Plan, plan
from goal_chainer.planning.transport import encode
from goal_chainer.runtime.budget import InferenceBudgetExceeded, ReviewTimeout, RunBudget
from goal_chainer.runtime.engine import metta_engine, pymetta_identity
from goal_chainer.runtime.evaluator import ModuleGroup, evaluate, plain_value, prepare
from planning_oracle import Cost, Oracle, State, matches, replay, start_state
from test_planning_acceptance import AT, World

HERE = Path(__file__).resolve().parent
HISTORICAL_REVISION = "0a7ef56a5e3226c090c575799fb7b54c2cc223c6"
HISTORICAL_BLOB = "55a63c78c7fc058fd774ae2265cb37446a775503"
HISTORICAL = ModuleGroup("benchmark-historical-composer", (
    HERE / "fixtures" / "composer-0a7ef56a.metta", HERE / "planning_entry.metta",
))
ARMS = ("projection", "experimental-composer")


# Each generated procedure achieves one signal after achieving its predecessor, then acting.
# Alternatives add another way to the same goal; missing and cyclic links alter the graph itself.
# Time and space: O(length + alternatives) procedures, each with at most three steps.
# am[implements a-integrate-plan-eval-generator-1019@ed9341]
def workload(length: int, variant: str, prefix: str = "w") -> World:
    if length < 1 or variant not in ("chain", "alternative", "missing", "cycle", "unknown", "true", "false"):
        raise ValueError("positive length and a declared graph variant are required")
    signals = tuple(f"{prefix}-s{i}" for i in range(length + 1))
    action = f"{prefix}-act"
    procedures = []
    for index in range(length):
        before = (signals[index - 1], True) if index else None
        if index == 0 and variant in ("missing", "cycle"):
            before = (signals[length if variant == "missing" else length - 1], True)
        steps = (() if before is None else (("need", "achieve", before, ()),))
        steps += (("work", "act", action, () if before is None else ("need",)),)
        conditions = ((signals[-1], True),) if index == 0 and variant in ("unknown", "true", "false") else ()
        procedures.append((f"{prefix}-p{index}", ((signals[index], True),), conditions, steps))
    if variant == "alternative":
        # The first declared way has two acts; the alternative achieves the same goal with one.
        last = procedures[-1]
        procedures[-1] = (*last[:3], last[3] + (("extra", "act", action, ("work",)),))
        procedures.append((f"{prefix}-short", *last[1:]))
    readings = () if variant not in ("true", "false") else (
        (signals[-1], ("detected" if variant == "true" else "refuted", "deterministic")),)
    investigators = ((f"{prefix}-ask", ((signals[-1], True),)),) if variant == "unknown" else ()
    return World(signals, (action,), f"{prefix}-entity", f"{prefix}-control", tuple(procedures),
                 investigators, readings, ((signals[length - 1], True),))


# am[implements a-integrate-plan-eval-generator-1019@ed9341]
def digest(world: World) -> str:
    return hashlib.sha256(json.dumps(asdict(world), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# Preparation is fixed work, outside measured warm requests, with both its elapsed time and counts
# reported. Both arms use current declaration validation before their respective planning stage.
# am[implements a-integrate-plan-eval-baseline-1019@1bbdc8]
def preparation() -> dict:
    started = time.perf_counter()
    fixture = HISTORICAL.modules[0].read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(fixture)).encode() + b"\0" + fixture).hexdigest()
    if blob != HISTORICAL_BLOB:
        raise ProtocolError("The historical composer differs from its recorded git blob.")
    budget = RunBudget(inference_budget=100_000_000, timeout_seconds=120)
    modules = {group.name: prepare(group, budget=budget) for group in (PLANNING, HISTORICAL)}
    with metta_engine(budget) as engine:
        identity = asdict(pymetta_identity(engine))
    warm = [run(workload(1, "chain"), arm, 100_000_000, 120) for arm in ARMS]
    if any(row["status"] != "answered" for row in warm):
        raise ProtocolError("Planner benchmark preparation did not answer in both arms.")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip()
    return {"kind": "metadata", "revision": revision, "runtime": identity, "modules": modules,
            "historical_revision": HISTORICAL_REVISION, "historical_blob": blob,
            "python": platform.python_version(), "preparation_seconds": time.perf_counter() - started,
            "warmup": warm, "files": {str(path.relative_to(HERE.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (Path(__file__), HERE / "planning_entry.metta",
                             HERE.parent / "tests" / "planning_oracle.py",
                             HERE.parent / "tests" / "test_planning_acceptance.py")}}


# The old composer selects ways but supplies no executable schedule. For this monotone, single-entity
# graph family only, replay each selected procedure at most once using the independent model's
# enabled transitions and Finish/Derive priority. A blocked selection is not a reached goal.
# Time: at most sum(2 + number of steps) moves over selected procedures; each model move scans the
# library. State storage is linear in the selected procedures and their steps.
# am[implements a-integrate-plan-eval-harness-1019@88aa3d]
def simulate_selection(oracle: Oracle, initial: State, names: tuple[str, ...]) -> dict:
    model, state, cost = oracle.model, oracle.model.settle(initial), Cost()
    remaining = {model.index[name] for name in names}
    while remaining:
        enabled = tuple(move for move in model.enabled(state) if move.index in remaining)
        if not enabled:
            break
        move = enabled[0]
        state = model.apply(state, move)
        cost = cost.plus(move)
        if move.kind in ("finish", "derive"):
            remaining.remove(move.index)
    return {"goal_reached_in_model": all(state.holds(goal) for goal in oracle.goal) and model.settled(state),
            "simulated_cost": asdict(cost), "uncompleted_procedures": len(remaining)}


# Every input is data passed through typed holes. The unchanged old policy sees the same checked
# readings, no established tracks, and the same library as the current planner: the oracle's start_state
# reads the readings the planner is given.
# am[implements a-integrate-plan-eval-baseline-1019@1bbdc8] am[implements a-integrate-oracle-benchmark-callers-1019@68a85a]
def compose(world: World, library, budget: RunBudget):
    from metta import Expression, S

    known, _ = start_state(world.signal_readings())
    judged = Expression(tuple(S.Judged(S.Signal(signal),
        S.Holds if (signal, True) in known else S.Fails if (signal, False) in known else S.Undecided)
        for signal in world.signals))
    atom = evaluate(HISTORICAL, "gc-benchmark-compose", literal_term(world.goal_literals()[0]),
                    library_term(library), judged, Expression(()), budget=budget)
    value = plain_value(atom)
    if not isinstance(value, tuple) or len(value) != 5 or str(value[0]) != "Composed":
        raise ProtocolError("Historical composer returned no Composed answer.", details={"answer": str(value)})
    choices = value[3]
    if not isinstance(choices, tuple) or any(not isinstance(choice, tuple) or len(choice) != 4
                                           or str(choice[0]) != "Choice" for choice in choices):
        raise ProtocolError("Historical composer returned malformed choices.")
    return value, tuple(choice[2] for choice in choices), str(atom)


# Charge declaration reads and the planning call to one budget. Host elapsed time covers construction
# and decoding too. Independent validation runs after measurement and has its own reported time.
# Unexpected failures stop the experiment; only declared budget exhaustion becomes a result row.
# am[implements a-integrate-plan-eval-harness-1019@88aa3d] am[implements a-integrate-oracle-benchmark-callers-1019@68a85a]
def run(world: World, arm: str, inferences: int, seconds: float) -> dict:
    if arm not in ARMS:
        raise ValueError("unknown benchmark arm")
    started = time.perf_counter()
    budget = RunBudget(inference_budget=inferences, timeout_seconds=seconds)
    row = {"kind": "query", "workload": digest(world), "arm": arm,
           "inference_budget": inferences, "timeout_seconds": seconds}
    try:
        domain = read_domain(world.domain_text(), "benchmark-domain", budget=budget)
        library = read_procedures(world.library_text(), "benchmark-procedures", domain, budget=budget)
        if arm == "projection":
            answer = plan(world.goal_literals(), domain=domain, library=library, readings=world.signal_readings(),
                          journal=(), rows=(), receipts={}, at=AT, budget=budget)
            result = encode(answer)
        else:
            answer, names, result = compose(world, library, budget)
        budget.remaining()
    except (InferenceBudgetExceeded, ReviewTimeout) as error:
        row.update(status=type(error).__name__, elapsed_seconds=time.perf_counter() - started, inferences=budget.spent)
        return row
    row.update(status="answered", elapsed_seconds=time.perf_counter() - started, inferences=budget.spent,
               result=result)
    validating = time.perf_counter()
    oracle = Oracle.of(library, domain, world.goal)
    known, assumable = start_state(world.signal_readings())
    state = State(known)
    if arm == "projection":
        matches(oracle, answer, state, assumable)
        row.update(answer=type(answer).__name__, goal_reached_in_model=isinstance(answer, Plan))
        if isinstance(answer, Plan):
            _, cost = replay(oracle.model, state, answer.steps)
            row["simulated_cost"] = asdict(cost)
    else:
        row.update(answer=str(answer[2]), selected_procedures=list(names),
                   **simulate_selection(oracle, state, names))
    row["validation_seconds"] = time.perf_counter() - validating
    return row


# A seeded permutation changes only run order, never the frozen task or its evidence.
# am[implements a-integrate-plan-eval-harness-1019@88aa3d]
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lengths", type=int, nargs="+", required=True)
    parser.add_argument("--budgets", type=int, nargs="+", required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--seconds", type=float, required=True)
    args = parser.parse_args()
    if any(length < 1 for length in args.lengths):
        parser.error("lengths must be positive")
    for bound in args.budgets:
        RunBudget(inference_budget=bound, timeout_seconds=args.seconds)
    print(json.dumps(preparation(), sort_keys=True), flush=True)
    for length in args.lengths:
        for variant in ("chain", "alternative", "missing", "cycle", "unknown", "true", "false"):
            world = workload(length, variant)
            print(json.dumps({"kind": "workload", "digest": digest(world), "length": length,
                              "variant": variant, "world": asdict(world)}, sort_keys=True), flush=True)
            for bound in args.budgets:
                for seed in args.seeds:
                    arms = list(ARMS)
                    random.Random(seed).shuffle(arms)
                    for arm in arms:
                        print(json.dumps({**run(world, arm, bound, args.seconds), "seed": seed}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

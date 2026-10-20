"""Purpose: record what planning_oracle answers on the acceptance file's pinned worlds and a seeded sample of its
sublanguage into data/planning_model_conformance.json, the oracle proofs/PlanningModel.lean's main compares
the Lean model with. Each world's library is recorded once with its cases, and each case holds a state: the
snapshot a run of the model leaves, with the classification the oracle reads off the worlds its readings
admit, or a state the model reaches from the world's settled start, observed as it is; then the oracle's
settled start state, the moves it enables there and the state each leaves. Signals, actions, procedures and
steps are numbered in declaration order, as the Lean model numbers them. test_mathematical_contracts.py
records again and diffs the committed record; `python tests/record_planning_model_conformance.py` rewrites it."""

from __future__ import annotations

import json
import random
from pathlib import Path

from goal_chainer.planning.procedures import AchieveStep, ActStep
from planning_oracle import Lit, Model, Move, State, lit, observe, observing, start_state, undo_cycle
from test_planning_acceptance import (
    BRANCH_CONTRADICTED,
    CERTAIN_OPEN,
    DROPPED_INQUIRY_ASKED_LATER,
    EFFECTIVE_WRITES,
    INFLIGHT_SENSITIVE,
    INVESTIGATION_IN_FLIGHT,
    MEASURED,
    OBSERVATION_ENABLES_FINISH,
    OPPOSITE_GUARDS,
    SIMULTANEOUS,
    STALE_REACTION,
    TRANSIENT_FINISH,
    UNKNOWN_WRITE_MOVES,
    World,
    walked,
)

# The worlds, their cases and what the oracle answered.
# am[implements a-jk-pf-conformance-1019@8a012a]
RECORDED = Path(__file__).resolve().parent / "data" / "planning_model_conformance.json"
# The seeded sample: enough worlds, and enough of each world's reachable states, that every rule of the model
# and every kind of state occurs, while lean --run checks the whole record in seconds. The seed fixes the
# sample, so the record belongs to the oracle's revision alone.
# am[implements a-jk-pf-conformance-1019@8a012a]
SEED, SAMPLE, REACHED = 20261019, 120, 6
# Each pinned world with a run of the model to start from, the walk's choices and the act left in flight,
# and an investigator's answer read into the snapshot it leaves, or None.
# am[implements a-jk-pf-conformance-1019@8a012a]
PINNED = (
    ("simultaneous", SIMULTANEOUS, [], None, None), ("simultaneous-walked", SIMULTANEOUS, [0, 0, 0, 0], None, None),
    ("opposite-guards", OPPOSITE_GUARDS, [0, 0], None, None), ("effective-writes", EFFECTIVE_WRITES, [0, 0, 0], None, None),
    ("measured-detected", MEASURED["detected"], [], None, None), ("branch-contradicted", BRANCH_CONTRADICTED, [], None, None),
    ("branch-contradicted-not-x", BRANCH_CONTRADICTED, [], None, ("x", False)),
    ("transient-embedding", TRANSIENT_FINISH["embedding"], [0, 0], None, None),
    ("transient-goal", TRANSIENT_FINISH["goal"], [0, 0, 0], None, None), ("certain-open", CERTAIN_OPEN, [0, 0], None, None),
    ("observation-enables-finish", OBSERVATION_ENABLES_FINISH, [0, 0], None, None),
    ("observation-enables-finish-y", OBSERVATION_ENABLES_FINISH, [0, 0], None, ("y", True)),
    ("stale-reaction-refreshed", STALE_REACTION, [0, 0], None, None),
    ("inflight-sensitive", INFLIGHT_SENSITIVE["needy"], [0], 0, None),
    ("investigation-in-flight", INVESTIGATION_IN_FLIGHT, [0, 0], 0, None),
    ("dropped-inquiry", DROPPED_INQUIRY_ASKED_LATER, [0], 0, None), ("unknown-write-moves", UNKNOWN_WRITE_MOVES, [0], 0, None),
)


# A world of the acceptance generator's sublanguage drawn from `rng`: one to four signals, one to three
# actions, a third of them toggling one signal, one to three procedures of one to three steps with After
# naming earlier steps, a third of them Derives, achieves of distinct signals, and at most one checked reading
# per signal. When holds at most one literal and most signals are read, so that most states enable some move
# and the record checks every kind of move as well as the settle. Names are immaterial to the Lean model,
# which numbers everything.
# Time: a constant number of draws per procedure, step and signal.
# am[implements a-jk-pf-conformance-1019@8a012a]
def sampled(rng: random.Random) -> World:
    signals = tuple(f"s{n}" for n in range(rng.randint(1, 4)))
    actions = tuple(f"a{n}" for n in range(rng.randint(1, 3)))

    def literals(low: int, high: int) -> tuple[Lit, ...]:
        chosen = rng.sample(signals, min(rng.randint(low, high), len(signals)))
        return tuple((signal, rng.random() < 0.5) for signal in chosen)

    procedures = []
    for index in range(rng.randint(1, 3)):
        derive = rng.random() < 1 / 3
        steps: list[tuple[str, str, object, tuple[str, ...]]] = []
        for position in range(rng.randint(1, 3)):
            kind = "achieve" if derive else rng.choice(("act", "investigate", "achieve"))
            target = rng.choice(actions) if kind == "act" else (rng.choice(signals), rng.random() < 0.5)
            after = tuple(rng.sample([step[0] for step in steps], rng.randint(0, min(2, len(steps)))))
            steps.append((f"t{position}", kind, target, after))
        procedures.append((f"p{index}", literals(1, 2), literals(0, 1), tuple(steps)))
    readings = tuple((signal, (rng.choice(("detected", "refuted")), "deterministic"))
                     for signal in signals if rng.random() < 0.8)
    reactions = tuple((action, (rng.choice(signals), rng.random() < 0.5)) for action in actions if rng.random() < 1 / 3)
    return World(signals, actions, "thing", "Thing", tuple(procedures), (), readings, ((signals[0], True),), reactions)


# One world's record, or None for a library R2 refuses, which no plan reaches: its library, then the snapshot
# the run `walk` and `dispatch` leave, with `reading` read into it when given, observed under the
# classification the worlds its readings admit give, and the first `reached` states the model reaches from the
# world's settled start, breadth first, each observed as it is.
# Time: one open_worlds enumeration, 2^k valuations for k signals, plus one settle per enabled move of each
# of the 1 + reached states.
# am[implements a-jk-pf-conformance-1019@8a012a]
def recorded(name: str, world: World, walk: list[int], dispatch: int | None, reading: Lit | None) -> dict | None:
    oracle = world.oracle()
    model = oracle.model
    if undo_cycle(model) is not None:
        return None
    numbers = Numbering(world, model)
    _, snapshot, _ = walked(world, model, walk, dispatch)
    if reading is not None:
        snapshot = observing(snapshot, *reading)
    cases = [numbers.case("snapshot", snapshot, observe(model, snapshot, oracle.worlds(snapshot)))]
    observed, _ = start_state(world.signal_readings())
    states = [model.settle(State(observed))]
    for state in states:
        if len(states) >= REACHED:
            break
        states.extend(following for following in dict.fromkeys(model.apply(state, move) for move in model.enabled(state))
                      if following not in states)
    cases.extend(numbers.case(f"reached-{number}", state, state) for number, state in enumerate(states[:REACHED]))
    return {"name": name, "library": numbers.library(), "cases": cases}


# The Lean model's numbering of one world: signals and actions by declaration, each procedure's steps by
# their position in it.
# am[implements a-jk-pf-conformance-1019@8a012a]
class Numbering:
    def __init__(self, world: World, model: Model) -> None:
        self.model = model
        self.signals = {signal: index for index, signal in enumerate(world.signals)}
        self.actions = {action: index for index, action in enumerate(world.actions)}
        self.steps = [{step.id: position for position, step in enumerate(procedure.steps)}
                      for procedure in model.procedures]

    def lit(self, literal: Lit) -> list:
        return [self.signals[literal[0]], literal[1]]

    def library(self) -> dict:
        procedures = []
        for index, procedure in enumerate(self.model.procedures):
            steps = []
            for step in procedure.steps:
                encoded = {"id": self.steps[index][step.id], "after": [self.steps[index][after] for after in step.after]}
                if isinstance(step, ActStep):
                    encoded |= {"kind": "act", "action": self.actions[step.action]}
                elif isinstance(step, AchieveStep):
                    encoded |= {"kind": "achieve", "literal": self.lit(lit(step.literal))}
                else:
                    encoded |= {"kind": "investigate"}
                steps.append(encoded)
            procedures.append({"achieves": list(map(self.lit, self.model.achieves(procedure))),
                               "when": sorted(map(self.lit, self.model.when(procedure))), "steps": steps})
        reactions = [[self.actions[action], self.lit(read), self.lit(write)]
                     for action, (read, write) in sorted(self.model.reactions.items()) if action in self.actions]
        return {"procedures": procedures, "reactions": reactions}

    def state(self, state: State) -> dict:
        def instances(entries) -> list:
            return sorted([index, sorted(self.steps[index][step] for step in done)] for index, done in entries)

        return {"known": sorted(map(self.lit, state.known)), "open": instances(state.open),
                "uncertain": instances(state.uncertain), "completed": sorted(index for index, _ in state.completed),
                "changed": sorted(self.signals[signal] for signal in state.changed),
                "inflight": sorted([index, self.steps[index][step]] for index, step in state.inflight)}

    def move(self, move: Move) -> list:
        return [move.index, move.part if move.kind != "step" else self.steps[move.index][move.part]]

    # One case: the state as given and the classification taking it to `observed`, each instance the given
    # state has open completed, kept open or neither; then the oracle's settled start, the moves it enables
    # and the state each leaves.
    def case(self, name: str, given: State, observed: State) -> dict:
        model = self.model
        start = model.settle(observed)
        moves = model.enabled(start)
        opened = dict(given.open)
        return {
            "name": name,
            "snapshot": self.state(given),
            "observation": {"completes": sorted(index for index, _ in observed.completed if index in opened),
                            "keeps": sorted(index for index, _ in observed.open),
                            "entailed": sorted(map(self.lit, observed.known - given.known))},
            "start": self.state(start),
            "enabled": [self.move(move) for move in moves],
            "successors": [self.state(model.apply(start, move)) for move in moves],
        }


# The whole record: the pinned worlds, then the seeded sample, each sampled world with a walk and an act in
# flight drawn from the same generator.
# am[implements a-jk-pf-conformance-1019@8a012a]
def record() -> dict:
    worlds = [recorded(name, world, walk, dispatch, reading) for name, world, walk, dispatch, reading in PINNED]
    rng = random.Random(SEED)
    for number in range(SAMPLE):
        world = sampled(rng)
        walk = [rng.randint(0, 5) for _ in range(rng.randint(0, 6))]
        dispatch = rng.choice((None, rng.randint(0, 5)))
        worlds.append(recorded(f"sample-{number}", world, walk, dispatch, None))
    return {"worlds": [world for world in worlds if world is not None]}


# The record as committed: compact JSON with sorted keys, so recording again diffs exactly.
# am[implements a-jk-pf-conformance-1019@8a012a]
def text() -> str:
    return json.dumps(record(), separators=(",", ":"), sort_keys=True) + "\n"


if __name__ == "__main__":
    RECORDED.write_text(text())

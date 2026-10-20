"""Purpose: an independent finite model of the planning projection on its one-entity sublanguage, and the
checks comparing plan's answers with it, for the planner's acceptance tests and any test holding a
library, its domain and a goal of that sublanguage. A state is the signals known true or known false, the
rest unknown, each open procedure instance's done steps, the instances some world may already have
finished, the signals some world may have moved since the observations, and the acts in flight. The
rules are compile.metta's header's: Start, each executed step with its action's reaction, Finish and
Derive, with Finish and Derive a priority class; where an unknown literal or an act in flight leaves a
Finish, Derive or reaction possibly applied, the state forgets what it could overwrite where a world may
have moved it, K0's rule for an effect whose condition may hold, and an instance whose Finish may have
fired is uncertain. Each schedule's cost key is search.metta's header's, (U A E M ORDER), compared
lexicographically, brute force searches every reachable state, and an inquiry's branch is the snapshot
with the investigator's answer as a reading. The worlds a plan must hold in are the completions of the
unknown signals whose settled states agree with what was observed. The model reads only the library's
data model and the readings, never the planner's modules, so what it expects comes from the
specification and not from the code under test (c-integrate-planner-oracle-independence-1018); the
checks read plan's answers only through its public answer types. Oracle.of refuses a library or domain
the model does not represent, start_state such readings and lit such a literal, so an entity binding is
refused wherever it enters: a domain declaring one, an entity reading, or a signal placed on an entity.
start_state reads the readings plan itself is given. Oracle.reference gives one answer a planner meeting
the model would give, in those types, so the model's own answers can be checked in every world with no
planner run. The agreed soundness contract (c-jk-pc-agreed-1019) shapes the
rest: a plan passes only through roots whose own Finish and Derive moves end in one rest state (R1); a
library whose Derives can undo each other in a live cycle is refused (R2); each journal instance is
classified by the worlds the readings admit, completed where every one finished it, its entailed effects
then known, open where none did, else uncertain (R3, exact); a snapshot no world settles to consistently
with its checked readings answers Contradicted (C1); and the worlds start from every valuation, observed
signals included, since a reading sees only the rest."""

from __future__ import annotations

import heapq
import itertools
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from goal_chainer.planning.procedures import (
    ActStep,
    AchieveStep,
    InvestigateStep,
    NegatedLiteral,
    Procedure,
    ProcedureLibrary,
    ProcedureLiteral,
    SignalLiteral,
)
from goal_chainer.planning.projection import Inquiry, NoPlan, Plan, PlanningRefused, PlanStep, Unsolved, Witness
from goal_chainer.reading_projection import EntityReading
from goal_chainer.relevance.signals import SignalReading, SignalState

# A literal of the sublanguage: a signal and the value it asserts, (Signal s) True and (Not (Signal s)) False.
Lit = tuple[str, bool]
# The estimators whose reading justification checks, so it becomes structure (term contract 2.3).
CHECKED_ESTIMATORS = frozenset({"deterministic", "measured", "human-asserted"})
# How every refusal of an input the model does not represent begins: Oracle.of's, start_state's and lit's.
# am[implements a-jk-pc-outside-binding-1019@59f29c]
OUTSIDE = "outside the acceptance model's sublanguage: "


# The model's literal for a library literal of the sublanguage, a signal or its negation, or None for any
# other: a SNARS statement, or a signal placed on one entity, (On (Signal S) E), which the model's one entity
# would read as the bare signal whatever entity a binding chose (a-jk-pc-outside-binding-1019).
# am[implements a-jk-po-model-1018@482efb] am[implements a-jk-pc-outside-binding-1019@59f29c]
def modelled(literal: ProcedureLiteral) -> Lit | None:
    negated = isinstance(literal, NegatedLiteral)
    signal = literal.literal if negated else literal
    return (signal.name, not negated) if isinstance(signal, SignalLiteral) else None


# am[implements a-jk-po-model-1018@482efb] am[implements a-jk-pc-outside-binding-1019@59f29c]
# am[related c-jk-ob-lit-crash-1019@889537]
def lit(literal: ProcedureLiteral) -> Lit:
    """The model's literal for a library literal of the sublanguage, which names a signal; ValueError for
    any other literal, which the model does not represent."""

    found = modelled(literal)
    if found is None:
        raise ValueError(f"{OUTSIDE}the literal {literal}")
    return found


# The library literal for a model literal, lit's inverse.
# am[implements a-jk-po-model-1018@482efb]
def procedure_literal(literal: Lit) -> SignalLiteral | NegatedLiteral:
    return SignalLiteral(literal[0]) if literal[1] else NegatedLiteral(SignalLiteral(literal[0]))


# `known` with `literals` written over it, each literal's signal taking its value.
# am[implements a-jk-po-model-1018@482efb]
def written(known: Iterable[Lit], literals: Iterable[Lit]) -> frozenset[Lit]:
    values = dict(known)
    values.update(literals)
    return frozenset(values.items())


# A model state: the known literals, at most one value per signal; each open instance's procedure index
# with its done step ids; each uncertain instance, one whose Finish some world may have taken, with the
# steps it had done then; the signals some world may hold differently from what was observed, which the
# plan's own writes and the model's cancellations put there (a-jk-po-k0-changed-1018); and each act a
# journal dispatched with no receipt yet, as (procedure index, step id), neither done nor to be taken
# again (a-jk-po-replanning-1018). Start is barred while an instance of its procedure is open, so on one
# entity a procedure has at most one instance, and states compare exactly
# (c-ev-pk-open-instance-bar-1018). A world is a state that knows every signal, where no instance is
# uncertain. A completed instance is a journal instance every admitted world finished before the readings,
# with the Achieves literals it added to what they observe, which only a journal-only Finish closes
# (a-jk-pc-r3-exact-amend-1019); a world never holds one.
# am[implements a-jk-po-model-1018@482efb] am[implements a-jk-po-k0-model-1018@bde32b] am[implements a-jk-po-k0-changed-1018@d600c3]
# am[implements a-jk-po-replanning-1018@ad5d23] am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
@dataclass(frozen=True)
class State:
    known: frozenset[Lit]
    open: tuple[tuple[int, frozenset[str]], ...] = ()
    uncertain: tuple[tuple[int, frozenset[str]], ...] = ()
    changed: frozenset[str] = frozenset()
    inflight: frozenset[tuple[int, str]] = frozenset()
    completed: tuple[tuple[int, frozenset[Lit]], ...] = ()

    def holds(self, literal: Lit) -> bool:
        return literal in self.known

    def possibly(self, literals: Iterable[Lit]) -> bool:
        """No literal of `literals` is known false: each is known true or unknown."""

        return not any((signal, not value) in self.known for signal, value in literals)

    def done(self, index: int) -> frozenset[str] | None:
        return dict(self.open).get(index)

    def dispatched(self, index: int) -> frozenset[str]:
        """The acts of `index`'s instance in flight."""

        return frozenset(step for owner, step in self.inflight if owner == index)

    def with_open(self, index: int, done: frozenset[str] | None) -> tuple[tuple[int, frozenset[str]], ...]:
        """The open instances with `index` set to `done`, or closed for None."""

        instances = dict(self.open)
        if done is None:
            instances.pop(index, None)
        else:
            instances[index] = done
        return tuple(sorted(instances.items()))


# One rule application: which part of which procedure, as the plan names it.
# am[implements a-jk-po-model-1018@482efb]
@dataclass(frozen=True)
class Move:
    index: int
    part: str  # "start", "finish", "derive" or an executed step's id

    @property
    def kind(self) -> str:
        return self.part if self.part in ("start", "finish", "derive") else "step"


# The cost key of search.metta's header, (U A E M ORDER): applications whose procedure's record does not
# hold for every Achieves literal (with no tracks, every application the plan commits to), assumptions,
# executed steps, model steps (Start, Finish, Derive) and the steps' procedure indices, compared
# lexicographically. The plan commits to an application at its Start, at its Derive, and at the first step
# or Finish it takes of an instance the executor's journal started, `touches` saying a move is that
# (a-jk-po-first-touch-1018); a completed instance's journal-only Finish commits to it only where the
# instance added a literal to what was observed (a-jk-pc-r3-exact-amend-1019).
# am[implements a-jk-po-model-1018@482efb] am[implements a-jk-po-first-touch-1018@dc89ae]
@dataclass(frozen=True, order=True)
class Cost:
    unestablished: int = 0
    assumptions: int = 0
    executed: int = 0
    model: int = 0
    order: tuple[int, ...] = ()

    def plus(self, move: Move, touches: bool = False) -> Cost:
        commits = move.kind in ("start", "derive") or touches
        executed = move.kind == "step"
        return Cost(self.unestablished + commits, self.assumptions, self.executed + executed,
                    self.model + (not executed), self.order + (move.index,))


# The instances of `state` the executor's journal started whose first touch commits the plan, each a
# procedure index: at the start of a search or a replay every open or uncertain instance is, since the plan
# has started none yet, and each completed one whose effects the readings did not already give.
# am[implements a-jk-po-first-touch-1018@dc89ae] am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
def journal_instances(state: State) -> frozenset[int]:
    return frozenset([*(index for index, _ in (*state.open, *state.uncertain)),
                      *(index for index, added in state.completed if added)])


# Whether `move` is the plan's first touch of an instance the journal started and the plan has not touched,
# with the instances still untouched after it.
# am[implements a-jk-po-first-touch-1018@dc89ae]
def touch(move: Move, untouched: frozenset[int]) -> tuple[bool, frozenset[int]]:
    touches = move.kind in ("step", "finish") and move.index in untouched
    return touches, untouched - {move.index} if touches else untouched


# The library as the model reads it: each procedure's executed steps and the literals and Dones that
# the backward walk through After reaches; and each action's reaction, (the literal it reads, the one it
# writes), for an act toggling one signal of the entity (a-jk-po-act-reactions-1018).
# am[implements a-jk-po-model-1018@482efb] am[implements a-jk-po-act-reactions-1018@4ac76f]
class Model:
    def __init__(self, library: ProcedureLibrary, reactions: Mapping[str, tuple[Lit, Lit]] | None = None) -> None:
        self.procedures: tuple[Procedure, ...] = library.procedures
        self.index = {procedure.name: index for index, procedure in enumerate(self.procedures)}
        self.reactions = dict(reactions or {})
        self._closures: dict[State, frozenset[State] | None] = {}

    # compile.metta's backward walk: from `ids` through After, an executed step is reached and stops the
    # walk, and an Achieve step contributes its literal and continues to its own predecessors.
    # Time: each step visited at most once, s steps.
    def reach(self, procedure: Procedure, ids: Iterable[str]) -> tuple[frozenset[str], frozenset[Lit]]:
        steps = {step.id: step for step in procedure.steps}
        executed: set[str] = set()
        literals: set[Lit] = set()
        seen: set[str] = set()
        pending = list(ids)
        while pending:
            step = steps[pending.pop()]
            if step.id in seen:
                continue
            seen.add(step.id)
            if isinstance(step, AchieveStep):
                literals.add(lit(step.literal))
                pending.extend(step.after)
            else:
                executed.add(step.id)
        return frozenset(executed), frozenset(literals)

    def executed_steps(self, procedure: Procedure) -> tuple[str, ...]:
        return tuple(step.id for step in procedure.steps if not isinstance(step, AchieveStep))

    def terminal(self, procedure: Procedure) -> tuple[str, ...]:
        named = {step_id for step in procedure.steps for step_id in step.after}
        return tuple(step.id for step in procedure.steps if step.id not in named)

    def when(self, procedure: Procedure) -> frozenset[Lit]:
        return frozenset(lit(literal) for literal in procedure.when)

    def achieves(self, procedure: Procedure) -> tuple[Lit, ...]:
        return tuple(lit(literal) for literal in procedure.achieves)

    # The reaction an executed step's act applies, (read, write), or None for an investigation or an act
    # whose action declares no reaction.
    def reaction(self, index: int, step_id: str) -> tuple[Lit, Lit] | None:
        step = next(step for step in self.procedures[index].steps if step.id == step_id)
        return self.reactions.get(step.action) if isinstance(step, ActStep) else None

    # What a procedure's write reads, as the executed steps it needs done and the literals it needs
    # holding: a Derive (no executed step) its When and every Achieve literal; a Finish what the walk back
    # from the steps nothing follows reaches, never its When.
    def reads(self, procedure: Procedure) -> tuple[frozenset[str], frozenset[Lit]]:
        if not self.executed_steps(procedure):
            return frozenset(), self.when(procedure) | self.reach(procedure, [step.id for step in procedure.steps])[1]
        return self.reach(procedure, self.terminal(procedure))

    # The rules writing `literal`, as search.metta's NoPlan reasons count them, each as (the signals it
    # reads, the signals its write variants read): the Finish or Derive of a procedure achieving it whose
    # write does not already read it (a-jk-po-effective-writers-1018), whose variants also read its
    # Achieves subjects; and each act whose action's reaction writes it, which compile.metta makes that
    # reaction too, reading When, what the walk back from its After reaches and the literal the reaction
    # reads (a-jk-po-reaction-writers-1018).
    # Time: p procedures times s steps, each a walk of at most s steps.
    # am[implements a-jk-po-reaction-writers-1018@3653ec]
    def writers(self, literal: Lit) -> tuple[tuple[frozenset[str], frozenset[str]], ...]:
        found = []
        for index, procedure in enumerate(self.procedures):
            reads = self.reads(procedure)[1]
            if literal in self.achieves(procedure) and literal not in reads:
                signals = frozenset(signal for signal, _ in reads)
                found.append((signals, signals | {signal for signal, _ in self.achieves(procedure)}))
            for step in procedure.steps:
                reaction = self.reaction(index, step.id)
                if reaction is not None and reaction[1] == literal:
                    needs = self.when(procedure) | self.reach(procedure, step.after)[1] | {reaction[0]}
                    signals = frozenset(signal for signal, _ in needs)
                    found.append((signals, signals))
        return tuple(found)

    # K0's weakening to a fixpoint (c-jk-po-k0-split-proposed-1018, after Palacios and Geffner, JAIR 2009):
    # a Finish or Derive is maybe-enabled when every executed step it reads is done or in flight, no
    # literal it reads is known false, and one read, a literal or an in-flight act's Done, is unknown; an
    # act in flight is one too until its receipt, its reaction's write the only thing it writes. A
    # maybe-enabled item makes unknown a literal it writes whose opposite is known, since a world where it
    # fires holds the literal and one where it does not keeps the opposite, but only where a world may
    # have moved since the observations (c-jk-po-k0-changed-agreed-1018): an item reading a changed signal
    # moves every write the state does not know with its value, forgetting those known opposite and
    # putting all of them among the changed (a-jk-po-moved-writes-1018); an item with no moved read
    # cancels only its writes on changed signals, since every world the observations leave open settled
    # with them, so such an item already fired there if its reads held, and fires again only once a
    # target moves. A Finish reads the Done markers of the plan's own instance and an act in flight its
    # own Done, which a step wrote, so both always have a moved read. An open instance whose Finish is
    # maybe-enabled becomes uncertain, and an uncertain instance goes on weakening while no literal its
    # Finish reads is known false, since a world that has not finished it may finish it then. Knowledge
    # only shrinks and uncertainty and change only grow, so the fixpoint is unique.
    # Time: at most k + p + c rounds, k known literals, p procedures and c signals, each round p reads of
    # at most s steps and one write per act in flight.
    def settle(self, state: State) -> State:
        while True:
            known, opened, uncertain = set(state.known), dict(state.open), dict(state.uncertain)
            changed = set(state.changed)
            items: list[tuple[bool, tuple[Lit, ...]]] = []
            for index, procedure in enumerate(self.procedures):
                steps, reads = self.reads(procedure)
                if not state.possibly(reads):
                    continue
                if not self.executed_steps(procedure):
                    maybe = not reads <= state.known
                    moved = any(signal in state.changed for signal, _ in reads)
                elif index in opened:
                    landed = opened[index] | state.dispatched(index)
                    maybe = steps <= landed and not (steps <= opened[index] and reads <= state.known)
                    moved = True
                    if maybe:
                        uncertain[index] = opened.pop(index)
                else:
                    maybe = index in uncertain
                    moved = True
                if maybe:
                    items.append((moved, self.achieves(procedure)))
            for index, step_id in state.inflight:
                reaction = self.reaction(index, step_id)
                if reaction is not None:
                    items.append((True, (reaction[1],)))
            for moved, writes in items:
                for signal, value in writes:
                    if (signal, value) in state.known or not (moved or signal in state.changed):
                        continue
                    known.discard((signal, not value))
                    changed.add(signal)
            following = replace(state, known=frozenset(known), open=tuple(sorted(opened.items())),
                                uncertain=tuple(sorted(uncertain.items())), changed=frozenset(changed))
            if following == state:
                return state
            state = following

    # Every rule application enabled in `state`, as the compiled rules read it:
    #   Derive (no executed step): When and every Achieve literal known, and it changes some literal;
    #   Start: When known and no instance of the procedure open or uncertain;
    #   an executed step of an open instance: not done, not in flight, When known, the walk back from its
    #     After finds each executed step done and each Achieve literal known, and an act's reaction finds
    #     the literal it reads known, which its redex matches as structure;
    #   Finish of an open instance: the walk back from the steps nothing follows finds the same.
    # An uncertain instance takes no step and no Finish: some world has finished it and another has not.
    # Finish and Derive are a priority class: where one is enabled, only those apply.
    # Time: p procedures times s steps, each a walk of at most s steps.
    def enabled(self, state: State) -> tuple[Move, ...]:
        priority: list[Move] = []
        ordinary: list[Move] = []
        uncertain = dict(state.uncertain)
        for index, procedure in enumerate(self.procedures):
            steps, reads = self.reads(procedure)
            if not self.executed_steps(procedure):
                if reads <= state.known and not set(self.achieves(procedure)) <= state.known:
                    priority.append(Move(index, "derive"))
                continue
            if index in uncertain:
                continue
            # A completed instance's journal-only Finish, which bars its procedure's Start until taken.
            if index in dict(state.completed):
                priority.append(Move(index, "finish"))
                continue
            when = self.when(procedure) <= state.known
            done = state.done(index)
            if done is None:
                if when:
                    ordinary.append(Move(index, "start"))
                continue
            if steps <= done and reads <= state.known:
                priority.append(Move(index, "finish"))
            for step in procedure.steps:
                if isinstance(step, AchieveStep) or step.id in done or (index, step.id) in state.inflight or not when:
                    continue
                before, needs = self.reach(procedure, step.after)
                reaction = self.reaction(index, step.id)
                if before <= done and needs <= state.known and (reaction is None or reaction[0] in state.known):
                    ordinary.append(Move(index, step.id))
        return tuple(priority) if priority else tuple(ordinary)

    # No Finish or Derive is enabled: the state the world rests in, where the goal is judged
    # (a-jk-po-k0-refinements-1018).
    def settled(self, state: State) -> bool:
        return not any(move.kind in ("finish", "derive") for move in self.enabled(state))

    # The state a move leaves, as a world takes it: Start opens an instance with nothing done, a step
    # marks itself done and an act applies its reaction, Finish closes the instance and writes its
    # Achieves literals, Derive writes them; a write sets its literal whatever the literal held
    # (compile.metta's Sets) and moves its signal.
    def step(self, state: State, move: Move) -> State:
        procedure = self.procedures[move.index]
        if move.kind == "start":
            return replace(state, open=state.with_open(move.index, frozenset()))
        if move.kind == "step":
            following = replace(state, open=state.with_open(move.index, state.done(move.index) | {move.part}))
            reaction = self.reaction(move.index, move.part)
            return following if reaction is None else self._write(following, (reaction[1],))
        if move.kind == "finish" and move.index in dict(state.completed):
            return replace(state, completed=tuple(entry for entry in state.completed if entry[0] != move.index))
        following = self._write(state, self.achieves(procedure))
        if move.kind == "finish":
            following = replace(following, open=state.with_open(move.index, None),
                                inflight=frozenset(item for item in state.inflight if item[0] != move.index))
        return following

    # The model's state a move leaves: the world's, settled.
    def apply(self, state: State, move: Move) -> State:
        return self.settle(self.step(state, move))

    # The rest states the model's own Finish and Derive moves reach from `root`, each followed by the
    # settle, or None where some run of them revisits a state (a-jk-pc-r1-closure-1019). A state on a run
    # that reaches a state above it on the same path lies on a cycle with it, so remembering None is exact.
    # Time: each state the closure reaches expanded once, times its priority moves and one settle each.
    def closure(self, root: State) -> frozenset[State] | None:
        def visit(state: State, path: frozenset[State]) -> frozenset[State] | None:
            if state in path:
                return None
            if state in self._closures:
                return self._closures[state]
            priority = [move for move in self.enabled(state) if move.kind in ("finish", "derive")]
            result: frozenset[State] | None = frozenset({state}) if not priority else frozenset()
            for move in priority:
                rests = visit(self.apply(state, move), path | {state})
                if rests is None:
                    result = None
                    break
                result |= rests
            self._closures[state] = result
            return result

        return visit(root, frozenset())

    # R1: every run of the root's Finish and Derive moves is finite and ends in the same rest state, rest
    # states compared with CHANGED as the search keys them (c-ev-pc-changed-is-model-state-1019).
    def determined(self, root: State) -> bool:
        rests = self.closure(root)
        return rests is not None and len(rests) == 1

    # A world where an act in flight lands: its step done and its reaction's write applied over the state
    # as it stands, the redex not read again (c-jk-po-inflight-semantics-agreed-1018).
    def land(self, state: State, act: tuple[int, str]) -> State:
        index, step_id = act
        done = state.done(index)
        following = replace(state, inflight=state.inflight - {act},
                            open=state.open if done is None else state.with_open(index, done | {step_id}))
        reaction = self.reaction(index, step_id)
        return following if reaction is None else self._write(following, (reaction[1],))

    def _write(self, state: State, literals: Iterable[Lit]) -> State:
        literals = tuple(literals)
        return replace(state, known=written(state.known, literals), changed=state.changed | {signal for signal, _ in literals})


# What brute force found: the least cost of a goal state, None for none, and one schedule reaching it.
# am[implements a-jk-po-brute-force-1018@41762b]
@dataclass(frozen=True)
class Search:
    cost: Cost | None
    schedule: tuple[Move, ...]
    states: int


# Uniform-cost search over every state reachable from `start` once settled, keyed by the state and the
# journal's instances the plan has not touched: with no tracks a move's cost depends on the move and
# whether it first touches such an instance only, so the first time a key is popped its cost is least,
# and the first goal state popped is a least schedule (search.metta's header). A goal state knows every
# goal literal and is settled. A root, the start or the state an ordinary move leaves, whose own Finish and
# Derive moves are not determined is no state any plan passes through (R1).
# Time: n states, each popped once, times the moves enabled there and one settle each, plus n log n heap
# operations; n is at most 3^k valuations times the procedures' progress states times 2^j untouched
# sets, k signals and j journal instances; each root adds one closure, its states remembered across roots.
# am[implements a-jk-po-brute-force-1018@41762b] am[implements a-jk-po-k0-model-1018@bde32b]
# am[implements a-jk-po-first-touch-1018@dc89ae] am[implements a-jk-pc-r1-closure-1019@f9b888]
def least(model: Model, start: State, goal: Sequence[Lit]) -> Search:
    counter = itertools.count()
    first = model.settle(start)
    if not model.determined(first):
        return Search(None, (), 0)
    frontier: list[tuple[Cost, int, State, frozenset[int], tuple[Move, ...]]] = [
        (Cost(), next(counter), first, journal_instances(first), ())]
    settled: set[tuple[State, frozenset[int]]] = set()
    while frontier:
        cost, _, state, untouched, schedule = heapq.heappop(frontier)
        if (state, untouched) in settled:
            continue
        settled.add((state, untouched))
        if all(state.holds(literal) for literal in goal) and model.settled(state):
            return Search(cost, schedule, len(settled))
        for move in model.enabled(state):
            successor = model.apply(state, move)
            if move.kind in ("start", "step") and not model.determined(successor):
                continue
            touches, rest = touch(move, untouched)
            if (successor, rest) not in settled:
                heapq.heappush(frontier, (cost.plus(move, touches), next(counter), successor, rest, schedule + (move,)))
    return Search(None, (), len(settled))


# A plan's steps replayed on the model from `start` settled: each must be enabled where it is taken,
# priority included, and each application numbered in plan order names one procedure throughout. Answers
# the final state and the plan's cost, its first touch of each journal instance charged, or raises
# AssertionError naming the first step the model refuses.
# am[implements a-jk-po-brute-force-1018@41762b] am[implements a-jk-po-first-touch-1018@dc89ae]
def replay(model: Model, start: State, steps: Sequence[object]) -> tuple[State, Cost]:
    state, cost = model.settle(start), Cost()
    untouched = journal_instances(state)
    applications: dict[int, int] = {}
    for position, step in enumerate(steps):
        index = model.index[step.procedure]
        assert applications.setdefault(step.application, index) == index, (position, "application renamed")
        part = step.step if step.kind in ("act", "investigate") else step.kind
        move = Move(index, part)
        assert move in model.enabled(state), (position, step.procedure, step.kind, step.step, "not enabled")
        touches, untouched = touch(move, untouched)
        state, cost = model.apply(state, move), cost.plus(move, touches)
    return state, cost


# The literals checked readings observe and those an unchecked reading only offers as assumptions, read from
# the readings plan is given: a detected signal is true, a refuted one false, and an unknown reading, which
# the shared vocabulary reads as silence, leaves it unknown as no reading does. The model holds one reading
# per signal and none placed on an entity, so a second reading of a signal, which plan's justification
# resolves, and an EntityReading, a binding's placing of a signal on one entity, are refused as outside it
# (a-jk-pc-outside-binding-1019).
# Time: one set lookup per reading.
# am[implements a-jk-po-model-1018@482efb] am[implements a-jk-pc-outside-binding-1019@59f29c]
# am[rests-on c-jk-ob-design-start-1019@78e9dd] am[rests-on c-jk-ob-oracle-readings-mapping-1019@cb9439]
def start_state(readings: Iterable[SignalReading | EntityReading]) -> tuple[frozenset[Lit], frozenset[Lit]]:
    observed, assumable, read = set(), set(), set()
    for reading in readings:
        if isinstance(reading, EntityReading):
            raise ValueError(f"{OUTSIDE}the entity reading of {reading.reading.signal} on {reading.entity}")
        if reading.signal in read:
            raise ValueError(f"{OUTSIDE}a second reading of {reading.signal}")
        read.add(reading.signal)
        if reading.state is not SignalState.UNKNOWN:
            literal = (reading.signal, reading.state is SignalState.DETECTED)
            (observed if reading.estimator in CHECKED_ESTIMATORS else assumable).add(literal)
    return frozenset(observed), frozenset(assumable)


# A snapshot as the model starts from it, `worlds` the rests its readings admit (open_worlds): a journal
# instance whose needed steps all have receipts may have finished while the world settled before the
# readings, so each instance is classified by those rests (R3, exact, a-jk-pc-r3-exact-amend-1019). Closed in
# every one, every world finished it: it is completed, only a journal-only Finish closes it and its acts in
# flight drop, and each of its Achieves literals every rest holds joins what was observed, as a reading
# does, so the settle forgets it wherever an act in flight could overwrite it after the readings
# (c-jk-pc-entailed-as-observation-1019). Open in every one, it stays open, and otherwise it is uncertain.
# With no admitted world C1 refuses the snapshot, which stays as the journal has it. Assumable literals
# decide nothing.
# Time: w worlds times the open instances, each a lookup, plus w membership tests per Achieves literal.
# am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
def observe(model: Model, snapshot: State, worlds: frozenset[State]) -> State:
    if not worlds:
        return snapshot
    opened, uncertain, completed = {}, dict(snapshot.uncertain), dict(snapshot.completed)
    known = set(snapshot.known)
    for index, done in snapshot.open:
        status = {index in dict(world.open) for world in worlds}
        if status == {True}:
            opened[index] = done
        elif status == {False}:
            completed[index] = frozenset(literal for literal in model.achieves(model.procedures[index])
                                         if all(literal in world.known for world in worlds)) - snapshot.known
            known |= completed[index]
        else:
            uncertain[index] = done
    return replace(snapshot, known=frozenset(known), open=tuple(sorted(opened.items())),
                   uncertain=tuple(sorted(uncertain.items())), completed=tuple(sorted(completed.items())),
                   inflight=frozenset(act for act in snapshot.inflight if act[0] not in completed))


# R2's live undo graph (a-jk-pc-r2-undo-graph-1019): an edge from Derive d' to Derive d when d' writes the
# negation of an effective write of d, an Achieves literal d does not read (c-jk-pc-r2-effective-writes-1019),
# and the two read no signal oppositely that no Derive writes effectively. A Derive is no edge of its own: one
# writing a literal and its negation is refused as contradictory-achieves before any cycle is looked for, as
# the policy reads it. Answers the names of the Derives on a cycle, which production refuses as cyclic-undo,
# or None.
# Time: d^2 edges over d Derives, each a comparison of their literal sets, and one depth-first search.
# am[implements a-jk-pc-r2-undo-graph-1019@fc3557]
def undo_cycle(model: Model) -> tuple[str, ...] | None:
    derives = [index for index, procedure in enumerate(model.procedures) if not model.executed_steps(procedure)]
    reads = {index: model.reads(model.procedures[index])[1] for index in derives}
    effective = {index: frozenset(model.achieves(model.procedures[index])) - reads[index] for index in derives}
    written = {signal for index in derives for signal, _ in effective[index]}

    def undoes(source: int, target: int) -> bool:
        if not any((signal, not value) in effective[source] for signal, value in effective[target]):
            return False
        return not any((signal, not value) in reads[target] and signal not in written
                       for signal, value in reads[source])

    edges = {source: [target for target in derives if target != source and undoes(source, target)] for source in derives}
    state: dict[int, int] = {}

    def visit(node: int, path: list[int]) -> list[int] | None:
        state[node] = 1
        for target in edges[node]:
            if state.get(target) == 1:
                return path[path.index(target):] + [node] if target in path else [target, node]
            if target not in state:
                cycle = visit(target, path + [node])
                if cycle is not None:
                    return cycle
        state[node] = 2
        return None

    for node in derives:
        if node not in state:
            cycle = visit(node, [])
            if cycle is not None:
                return tuple(model.procedures[index].name for index in cycle)
    return None


# --- expected answers ---------------------------------------------------------------------------------


# What plan must answer, as the model derives it (c-jk-po-boundary-agreed-1018):
#   Expected("plan", cost, schedule)         the least valid plan's cost and one schedule reaching it,
#                                            with the literals it assumes where it is an alternative;
#   Expected("inquire", metric, choices)     the (DEAD DEPTH STEPS) of the best inquiry and, for each
#                                            signal tying at it, the expected answer of its branches;
#   Expected("dead", unsolved, alternative)  NoPlan: each unestablished goal literal's reason and the
#                                            alternative's expected plan, None for none;
#   Expected("contradicted")                 PlanningRefused: no world settles to the readings (C1).
# am[implements a-jk-po-brute-force-1018@41762b]
@dataclass(frozen=True)
class Expected:
    kind: str
    cost: Cost | None = None
    metric: tuple[int, int, int] | None = None
    choices: Mapping[str, tuple[Expected, Expected]] | None = None
    unsolved: tuple[tuple[Lit, str, frozenset[str]], ...] = ()
    alternative: Expected | None = None
    schedule: tuple[Move, ...] = ()
    assumed: tuple[Lit, ...] = ()


# A snapshot with `signal` observed as `value`, replacing what was observed of it before: an investigator's
# answer is a reading of the snapshot, so its branch settles from the snapshot and answers what plan
# answers once that reading arrives (a-jk-po-observation-as-reading-1018).
# am[implements a-jk-po-brute-force-1018@41762b] am[implements a-jk-po-observation-as-reading-1018@32a792]
def observing(snapshot: State, signal: str, value: bool) -> State:
    return replace(snapshot, known=written(snapshot.known, ((signal, value),)))


# The expected answers of one problem: the model, the goal, the declared signals and the signals each
# investigator observes, solved recursively over the signals an inquiry observes.
# am[implements a-jk-po-brute-force-1018@41762b] am[implements a-jk-po-oracle-api-1018@6ad604]
class Oracle:
    def __init__(self, model: Model, goal: Sequence[Lit], signals: Iterable[str],
                 investigators: Mapping[str, frozenset[str]]) -> None:
        self.model = model
        self.goal = tuple(goal)
        self.signals = frozenset(signals)
        self.investigators = dict(investigators)
        self.covered = frozenset().union(*self.investigators.values())
        self._answers: dict[tuple[State, frozenset[Lit], frozenset[str]], Expected] = {}
        self._solving: set[tuple[State, frozenset[Lit], frozenset[str]]] = set()
        self._worlds: dict[State, frozenset[State]] = {}

    # The oracle for a library read against its domain and a goal of (signal, value) literals, or
    # ValueError naming what the model does not represent (outside).
    @classmethod
    def of(cls, library: ProcedureLibrary, domain: object, goal: Sequence[Lit]) -> Oracle:
        refused = outside(library, domain, goal)
        if refused is not None:
            raise ValueError(f"{OUTSIDE}{refused}")
        control = domain.bigraph.entities[0].control
        reactions = {reaction.action: toggle(reaction, control) for reaction in domain.bigraph.reactions}
        return cls.over(library, reactions, domain.signal_ids, goal)

    # The oracle for a library of the sublanguage, each action's toggle as (the literal its redex reads, the
    # one its reactum writes), the declared signals and a goal, with no domain read.
    @classmethod
    def over(cls, library: ProcedureLibrary, reactions: Mapping[str, tuple[Lit, Lit]], signals: Iterable[str],
             goal: Sequence[Lit]) -> Oracle:
        investigators = {investigator.name: frozenset(lit(literal)[0] for literal in investigator.observes)
                         for investigator in library.investigators}
        return cls(Model(library, reactions), goal, signals, investigators)

    def investigates(self, investigator: str, signal: str) -> bool:
        return signal in self.investigators.get(investigator, ())

    # A Plan leaf (0 0 its executed steps), a dead branch (1 0 0), an Inquire the sum of its branches'
    # dead, one more than their deepest depth, and their most steps.
    @staticmethod
    def metric(answer: Expected) -> tuple[int, int, int]:
        if answer.kind == "plan":
            return (0, 0, answer.cost.executed)
        if answer.kind == "dead":
            return (1, 0, 0)
        return answer.metric

    # The answer from a snapshot, what was observed with the journal's open instances and acts in
    # flight, `assumable` the literals only an unchecked reading gives and `asked` the signals an
    # inquiry above has asked: the least plan from the settled snapshot if one exists; else, over every
    # covered signal that state leaves unknown and nothing above asked, the inquiry whose branches, each
    # the snapshot with that signal observed one way (observing), minimise (DEAD DEPTH STEPS), a signal
    # no branch keeps once settled or whose two branches are both dead being no candidate
    # (a-jk-po-inquiry-progress-1018, c-jk-po-progress-agreed-1018); else NoPlan. A signal is asked once
    # on a path, so the inquiries beneath one are finite, and a branch whose settling forgets its answer
    # goes on from the parent's knowledge with that signal no longer askable.
    # Time: each distinct (snapshot, assumable, asked) solved once; a solve is one brute force per
    # candidate branch, at most 2^u * u! brute forces for u covered unknown signals.
    # am[implements a-jk-po-observation-as-reading-1018@32a792]
    def answer(self, snapshot: State, assumable: frozenset[Lit], asked: frozenset[str] = frozenset()) -> Expected:
        key = (snapshot, assumable, asked)
        if key in self._answers:
            return self._answers[key]
        assert key not in self._solving, ("an inquiry beneath itself", snapshot, asked)
        self._solving.add(key)
        state = self.start(snapshot)
        found = least(self.model, state, self.goal) if self.admitted(snapshot) else None
        if found is None:
            # C1 (a-jk-pc-c1-admitted-1019, c-jk-pc-c1-forms-1019): no world settles to the readings; the
            # root is refused, and a branch answers NoPlan contradicted for every goal literal, dead.
            result = (Expected("contradicted") if not asked else
                      Expected("dead", unsolved=tuple((literal, "contradicted", frozenset()) for literal in self.goal)))
        elif found.cost is not None:
            result = Expected("plan", cost=found.cost, schedule=found.schedule)
        else:
            known = {signal for signal, _ in state.known}
            options: dict[str, tuple[tuple[int, int, int], tuple[Expected, Expected]]] = {}
            for signal in sorted(self.covered - known - asked):
                observed = tuple(observing(snapshot, signal, value) for value in (True, False))
                if not any(signal in {s for s, _ in self.start(branch).known} for branch in observed):
                    continue
                rest = frozenset(lit for lit in assumable if lit[0] != signal)
                branches = tuple(self.answer(branch, rest, asked | {signal}) for branch in observed)
                if all(branch.kind == "dead" for branch in branches):
                    continue
                dead = sum(self.metric(branch)[0] for branch in branches)
                depth = 1 + max(self.metric(branch)[1] for branch in branches)
                steps = max(self.metric(branch)[2] for branch in branches)
                options[signal] = ((dead, depth, steps), branches)
            if options:
                best = min(metric for metric, _ in options.values())
                result = Expected("inquire", metric=best,
                                  choices={signal: branches for signal, (metric, branches) in options.items() if metric == best})
            else:
                result = Expected("dead", unsolved=self.unsolved(state, asked),
                                  alternative=self.alternative(snapshot, state, assumable))
        self._solving.discard(key)
        self._answers[key] = result
        return result

    # One answer a planner meeting the model gives from a snapshot, in plan's public types: the least
    # schedule's steps; the inquiry about the first signal tying at the least metric, through the first
    # investigator observing it; NoPlan with the model's reasons and its least alternative; or
    # PlanningRefused where no world settles to the readings (C1). Ties are the planner's to break, so this
    # is one representative of what matches accepts, for checking the model's own answers in every world
    # (holds_everywhere) where no planner runs (a-jk-pc-model-answers-1019).
    # am[implements a-jk-pc-model-answers-1019@a0f897]
    def reference(self, snapshot: State, assumable: frozenset[Lit], asked: frozenset[str] = frozenset()) -> object:
        want = self.answer(snapshot, assumable, asked)
        if want.kind == "contradicted":
            return PlanningRefused(("Contradicted: no world settles to the checked readings",))
        if want.kind == "plan":
            return Plan(plan_steps(self.model, want.schedule), established=want.cost.unestablished == 0)
        if want.kind == "inquire":
            signal = min(want.choices)
            investigator = min(name for name, signals in self.investigators.items() if signal in signals)
            rest = frozenset(literal for literal in assumable if literal[0] != signal)
            if_true, if_false = (self.reference(observing(snapshot, signal, value), rest, asked | {signal})
                                 for value in (True, False))
            return Inquiry(SignalLiteral(signal), investigator, if_true, if_false)
        unsolved = tuple(Unsolved(procedure_literal(literal), reason, tuple(SignalLiteral(s) for s in sorted(waits)))
                         for literal, reason, waits in want.unsolved)
        alternative = want.alternative
        return NoPlan(unsolved, None if alternative is None else
                      Plan(plan_steps(self.model, alternative.schedule), established=alternative.cost.unestablished == 0,
                           assumptions=tuple(map(procedure_literal, alternative.assumed))))

    # The rests a snapshot's readings admit (open_worlds), each computed once.
    # am[implements a-jk-pc-c1-admitted-1019@321a3b]
    def worlds(self, snapshot: State) -> frozenset[State]:
        if snapshot not in self._worlds:
            self._worlds[snapshot] = open_worlds(self.model, snapshot, self.signals)
        return self._worlds[snapshot]

    # C1: some world settles, with no act landing, to a rest state holding every checked literal of the
    # snapshot, an investigator's answer and an assumption included.
    # am[implements a-jk-pc-c1-admitted-1019@321a3b]
    def admitted(self, snapshot: State) -> bool:
        return bool(self.worlds(snapshot))

    # The model's state at a snapshot: its instances classified by the rests it admits (observe), settled.
    # am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
    def start(self, snapshot: State) -> State:
        return self.model.settle(observe(self.model, snapshot, self.worlds(snapshot)))

    # Each goal literal the state does not establish, with its reason over the rules writing it
    # (Model.writers): no-way when no rule writes it; unknowable when every writer reads a signal the
    # state leaves unknown and no investigator can observe on this path, a signal an inquiry above asked
    # being one (a-jk-po-asked-uncovered-1018), naming those its write variants read; and blocked otherwise.
    # am[implements a-jk-po-effective-writers-1018@0983fd] am[implements a-jk-po-reaction-writers-1018@3653ec]
    # am[implements a-jk-po-asked-uncovered-1018@91b320]
    def unsolved(self, state: State, asked: frozenset[str] = frozenset()) -> tuple[tuple[Lit, str, frozenset[str]], ...]:
        known = {signal for signal, _ in state.known}
        dark = self.signals - known - (self.covered - asked)
        found = []
        for literal in self.goal:
            if state.holds(literal):
                continue
            writers = self.model.writers(literal)
            if not writers:
                found.append((literal, "no-way", frozenset()))
            elif all(reads & dark for reads, _ in writers):
                found.append((literal, "unknowable", frozenset().union(*(variants & dark for _, variants in writers))))
            else:
                found.append((literal, "blocked", frozenset()))
        return tuple(found)

    # NoPlan's explanatory alternative: the least key, assumptions counted after the unestablished
    # applications, over every set of literals an unchecked reading gives and the settled state leaves
    # unknown, each assumed before the first step, as observed, with its schedule and the set it assumes;
    # None when no set opens a plan.
    # Time: 2^a brute forces, a assumable literals.
    def alternative(self, snapshot: State, state: State, assumable: frozenset[Lit]) -> Expected | None:
        known = {signal for signal, _ in state.known}
        open_literals = sorted(lit for lit in assumable if lit[0] not in known)
        best: Expected | None = None
        for size in range(1, len(open_literals) + 1):
            for chosen in itertools.combinations(open_literals, size):
                assumed = replace(snapshot, known=snapshot.known | set(chosen))
                if not self.admitted(assumed):
                    continue
                found = least(self.model, self.start(assumed), self.goal)
                if found.cost is not None:
                    cost = Cost(found.cost.unestablished, size, found.cost.executed, found.cost.model, found.cost.order)
                    if best is None or cost < best.cost:
                        best = Expected("plan", cost=cost, schedule=found.schedule, assumed=chosen)
        return best


# A schedule as plan's steps: applications numbered from 0 in plan order, a Start or a Derive opening one
# and an instance the journal started opening one at its first touch; the binding, the executor's instance
# id and the witness are the planner's own records, which the model does not derive, so they stay empty.
# Time: one pass over the schedule, each step's lookup at most s steps.
# am[implements a-jk-pc-model-answers-1019@a0f897]
def plan_steps(model: Model, schedule: Sequence[Move]) -> tuple[PlanStep, ...]:
    counter, current, found = itertools.count(), {}, []
    for move in schedule:
        procedure = model.procedures[move.index]
        if move.kind in ("start", "derive") or move.index not in current:
            current[move.index] = next(counter)
        application = current.pop(move.index) if move.kind in ("finish", "derive") else current[move.index]
        step = next(step for step in procedure.steps if step.id == move.part) if move.kind == "step" else None
        kind = move.kind if step is None else "investigate" if isinstance(step, InvestigateStep) else "act"
        found.append(PlanStep(procedure.name, None if step is None else step.id, kind, application, None, (),
                              Witness("", "", ())))
    return tuple(found)


# An atom's children, none for a leaf, whose children pymetta refuses with TypeError.
# am[implements a-jk-po-act-reactions-1018@4ac76f]
def children(atom: object) -> tuple[object, ...]:
    try:
        return tuple(atom.children)
    except (AttributeError, TypeError):
        return ()


# An atom as nested tuples of its parts' shapes, a leaf as its text, so terms compare by structure:
# (Inner 1 ()) is ("Inner", "1", "()").
# Time: one visit per subterm.
# am[implements a-jk-po-toggle-structure-1018@af3d3f]
def shape(atom: object) -> object:
    parts = children(atom)
    return tuple(shape(part) for part in parts) if parts else str(atom)


# A literal control in shape, ("Signal", NAME) or ("Not", ("Signal", NAME)), as the model's literal, or
# None for any other control.
# am[implements a-jk-po-act-reactions-1018@4ac76f]
def section_literal(control: object) -> Lit | None:
    if isinstance(control, tuple) and len(control) == 2 and control[0] == "Signal" and isinstance(control[1], str):
        return (control[1], True)
    if isinstance(control, tuple) and len(control) == 2 and control[0] == "Not":
        inner = section_literal(control[1])
        return None if inner is None or not inner[1] else (inner[0], False)
    return None


# One side of a toggle as (the entity's node id, the literal its other node holds), or None unless the
# term is exactly that shape up to its node ids: one site and one root, neither with names, the node of
# the entity's `control` in root 0 holding the literal's node and the site, and no link. A node or the site
# placed elsewhere, a second root, a name or a link is a structure the model's toggle of the entity's
# signal misreads, though the loader reads it, since it leaves the terms to the kernel
# (c-jk-po-toggle-shapes-loader-a5b068b-1018).
# Time: one visit per subterm of the term.
# am[implements a-jk-po-toggle-structure-1018@af3d3f]
def toggle_side(term: object, control: str) -> tuple[str, Lit] | None:
    parts = shape(term)
    if not isinstance(parts, tuple) or len(parts) != 6 or parts[0] != "Bigraph":
        return None
    _, inner, outer, nodes, place, link = parts
    if inner != ("Inner", "1", "()") or outer != ("Outer", "1", "()") or link != ("Link",):
        return None
    if not isinstance(nodes, tuple) or len(nodes) != 3 or nodes[0] != "Nodes":
        return None
    entity = held = None
    for row in nodes[1:]:
        if not (isinstance(row, tuple) and len(row) == 3 and row[0] == "N" and isinstance(row[1], str)):
            return None
        literal = section_literal(row[2])
        if literal is not None and held is None:
            held = (row[1], literal)
        elif row[2] == control and entity is None:
            entity = row[1]
        else:
            return None
    if entity is None or held is None or entity == held[0]:
        return None
    rows = {("In", entity, ("Root", "0")), ("In", held[0], entity), ("In", ("Site", "0"), entity)}
    if not isinstance(place, tuple) or len(place) != 4 or place[0] != "Place" or set(place[1:]) != rows:
        return None
    return entity, held[1]


# A reaction toggling one signal of the entity, as (the literal its redex reads, the literal its
# reactum writes), or None for any other reaction: redex and reactum each in toggle_side's shape, their
# literals of one signal and opposite values, with the identity site map and no condition, as
# WRITES_SENSITIVE in tests/test_planning_knowledge.py writes it (a-jk-po-act-reactions-1018). Which node
# an act binds needs no check here: read_procedures refuses a bind on any node but the reaction's entity
# node as mistyped-bind (c-jk-po-toggle-shapes-loader-a5b068b-1018).
# am[implements a-jk-po-act-reactions-1018@4ac76f] am[implements a-jk-po-toggle-structure-1018@af3d3f]
def toggle(reaction: object, control: str) -> tuple[Lit, Lit] | None:
    redex, reactum = toggle_side(reaction.redex, control), toggle_side(reaction.reactum, control)
    if (redex is None or reactum is None or redex[1] != (reactum[1][0], not reactum[1][1])
            or shape(reaction.eta) != ("Eta", ("0", "0")) or shape(reaction.conditions) != ("Conditions",)):
        return None
    return redex[1], reactum[1]


# What in a library, its domain or a goal lies outside the sublanguage the model represents, or None: the
# model knows one entity whose every anchored literal is a declared signal on it, the section's
# (Signal NAME) term, with no port link, and whose every reaction is exactly a toggle of one signal of
# it (toggle); signal
# literals only, no statement and no signal placed on an entity (modelled); an act binding a node only where
# its action has such a reaction, its one node bound to the entity; goal literals of declared signals; and a
# reading section binding no proposition to an entity, since a request's model reading over a binding gives
# plan entity readings, which the model does not represent (c-jk-ob-request-entity-needs-binding-1019).
# A library declaring a track promotion rule is outside it too: only under one can receipts make a track
# hold, and the model, which takes no receipts, counts every application unestablished.
# am[implements a-jk-po-oracle-api-1018@6ad604] am[implements a-jk-pc-outside-binding-1019@59f29c]
# am[rests-on c-jk-ob-request-entity-needs-binding-1019@29f628] am[implements a-jk-ob-track-refusal-1019@8f148f]
def outside(library: ProcedureLibrary, domain: object, goal: Sequence[Lit]) -> str | None:
    section = domain.bigraph
    if section is None:
        return "a domain with no bigraph section"
    if len(section.entities) != 1:
        return f"{len(section.entities)} entities"
    entity = section.entities[0].id
    if section.links:
        return f"the port link {section.links[0]}"
    declaration = domain.readings
    if declaration is not None and declaration.bindings:
        binding = declaration.bindings[0]
        return f"the binding of {binding.signal} to an entity of {binding.control}"
    for reaction in section.reactions:
        if toggle(reaction, section.entities[0].control) is None:
            return f"the reaction of {reaction.action}, which toggles no one signal of the entity"
    reacting = {reaction.action for reaction in section.reactions}
    signals = set(domain.signal_ids)
    for anchor in section.anchors:
        parts = [str(part) for part in children(anchor.literal)]
        if parts[:1] != ["Signal"] or len(parts) != 2 or parts[1] not in signals or anchor.entity != entity or anchor.via:
            return f"the anchor {anchor}"
    if library.promotion is not None:
        return "the track promotion rule, under which receipts can make a track hold"
    literals = [literal for investigator in library.investigators for literal in investigator.observes]
    for procedure in library.procedures:
        literals += [*procedure.achieves, *procedure.when]
        for step in procedure.steps:
            if isinstance(step, (AchieveStep, InvestigateStep)):
                literals.append(step.literal)
            elif isinstance(step, ActStep) and step.binds and (step.action not in reacting or len(step.binds) != 1
                                                                 or step.binds[0][1] != entity):
                return f"the act {step.id} of {procedure.name}, which binds what no toggling reaction of the entity reads"
    for literal in literals:
        if modelled(literal) is None:
            return f"the literal {literal}"
    for signal, _ in goal:
        if signal not in signals:
            return f"the goal literal of {signal}, which the domain does not declare"
    return None


# --- the worlds a plan must hold in -------------------------------------------------------------------


# A world whose Finish and Derive moves cycle with no fixpoint: a failure of any plan that leads there.
# am[implements a-jk-po-worlds-1018@36f08f]
class NoFixpoint(AssertionError):
    pass


# Every state a world rests in from `state`: Finish and Derive taken as the world takes them, in every
# order, until none is enabled, a Derive only when it changes something; with `landing`, each act in
# flight may also land at any rest state (a-jk-po-landing-worlds-1018), and a rest state where some
# have not landed is one too. A cycle with no rest raises NoFixpoint naming the states on it.
# Time: at most the states reachable by priority moves and landings alone, each expanded once.
# am[implements a-jk-po-worlds-1018@36f08f] am[implements a-jk-po-landing-worlds-1018@84871d]
def fixpoints(model: Model, state: State, landing: bool = False) -> frozenset[State]:
    settled: dict[State, frozenset[State]] = {}

    def visit(current: State, path: tuple[State, ...]) -> frozenset[State]:
        if current in path:
            raise NoFixpoint(("Finish and Derive cycle with no fixpoint", path))
        if current in settled:
            return settled[current]
        priority = [move for move in model.enabled(current) if move.kind in ("finish", "derive")]
        if priority:
            result = frozenset().union(*(visit(model.step(current, move), path + (current,)) for move in priority))
        else:
            landed = sorted(current.inflight) if landing else []
            result = frozenset({current}).union(*(visit(model.land(current, act), path + (current,)) for act in landed))
        settled[current] = result
        return result

    return visit(state, ())


# The worlds a snapshot leaves open, as they rest when the readings are taken: every valuation of the
# declared signals, observed ones included, since what each held while the journal's receipts landed is
# unknown (c-jk-pc-all-valuation-worlds-1019), every act in flight still pending, taken to its fixpoints,
# keeping the branches that hold every observed literal, since a reading, an assumption or an
# investigator's answer observes the settled world before any act in flight lands
# (c-jk-po-k0-split-proposed-1018, a-jk-po-k0-refinements-1018, c-jk-po-inflight-semantics-agreed-1018).
# A valuation that never settles is no world anything observed.
# Time: 2^n valuations, n declared signals, each taken to its fixpoints.
# am[implements a-jk-po-worlds-1018@36f08f] am[implements a-jk-po-replanning-1018@ad5d23] am[implements a-jk-po-landing-worlds-1018@84871d]
# am[implements a-jk-pc-all-valuations-1019@bdbebc]
def open_worlds(model: Model, snapshot: State, signals: Iterable[str]) -> frozenset[State]:
    every = sorted(set(signals))
    found: set[State] = set()
    for values in itertools.product((True, False), repeat=len(every)):
        world = State(frozenset(zip(every, values)), snapshot.open, inflight=snapshot.inflight)
        try:
            branches = fixpoints(model, world)
        except NoFixpoint:
            continue
        found |= {branch for branch in branches if snapshot.known <= branch.known}
    return frozenset(found)


# A plan's ordinary steps replayed from `branches`, the worlds as they rest at the readings, as the world
# runs them (c-jk-po-boundary-agreed-1018, c-ev-pk-finish-eager-1018): an act in flight may land at any
# rest state from the start on, each Start, act or investigate step must be enabled at its turn in every
# branch, Finish and Derive are taken to a fixpoint in every order after it, and the goal must hold at
# the end of every branch. Raises AssertionError naming the first step and world that fail.
# am[implements a-jk-po-worlds-1018@36f08f] am[implements a-jk-po-landing-worlds-1018@84871d]
def holds_in(model: Model, branches: frozenset[State], steps: Sequence[object], goal: Sequence[Lit]) -> None:
    states = frozenset().union(*(fixpoints(model, branch, landing=True) for branch in branches))
    for position, step in enumerate(steps):
        if step.kind not in ("start", "act", "investigate"):
            continue
        move = Move(model.index[step.procedure], step.step if step.kind != "start" else "start")
        following: set[State] = set()
        for state in states:
            assert move in ordinary_moves(model, state), (position, step.procedure, step.kind, step.step, "not enabled in", state)
            following |= fixpoints(model, model.step(state, move), landing=True)
        states = frozenset(following)
    for state in states:
        assert all(state.holds(literal) for literal in goal), ("goal fails in", state)


# The ordinary moves a state enables, Finish and Derive aside: what a world can take once no priority
# move is enabled.
# am[implements a-jk-po-worlds-1018@36f08f]
def ordinary_moves(model: Model, state: State) -> tuple[Move, ...]:
    return tuple(move for move in model.enabled(state) if move.kind in ("start", "step"))


# The model's state embeds a world's, term contract 4.4 in K0's form (a-jk-po-k0-refinements-1018): every
# literal the model knows holds in the world, every open instance is open there with the same done
# steps, an uncertain instance is open there with the steps it had done or closed, and no other
# instance is open there; an act in flight may have landed in the world, adding its step to the done
# ones (a-jk-po-replanning-1018).
# am[implements a-jk-po-worlds-1018@36f08f] am[implements a-jk-po-replanning-1018@ad5d23]
def embedded(model_state: State, world: State) -> bool:
    opened = dict(world.open)
    certain, uncertain = dict(model_state.open), dict(model_state.uncertain)

    def agrees(index: int, done: frozenset[str]) -> bool:
        return index in opened and done <= opened[index] <= done | model_state.dispatched(index)

    return (model_state.known <= world.known
            and all(agrees(index, done) for index, done in certain.items())
            and all(index in certain or index in uncertain and agrees(index, uncertain[index]) for index in opened))


# --- checking plan's answers ----------------------------------------------------------------------------


# plan's answer matches what the model expects from a snapshot, recursively through an inquiry's
# branches, `asked` the signals inquiries above have asked:
#   a Plan rests on no assumption, costs the least key, is classed established exactly when no
#   application it commits to is unestablished, and replays on the model under priority to a settled
#   state holding the goal;
#   an Inquiry asks about a signal no inquiry above asked, so that no path asks one twice and the
#   inquiries are finite whatever rule chooses them, tying at the least (DEAD DEPTH STEPS), through an
#   investigator that observes it, and each branch is the model's answer with that signal observed that
#   way;
#   a NoPlan names each unestablished goal literal with the model's reason and the signals an
#   unknowable one waits on, and its alternative, when the model has one, assumes only literals an
#   unchecked reading gives and the settled start leaves unknown, and costs the model's least key,
#   assumptions counted after U.
# Raises AssertionError naming the first disagreement.
# am[implements a-jk-po-brute-force-1018@41762b] am[implements a-jk-po-oracle-api-1018@6ad604]
# am[implements a-jk-po-inquiry-progress-1018@e8df05] am[implements a-jk-po-observation-as-reading-1018@32a792]
def matches(oracle: Oracle, answer: object, snapshot: State, assumable: frozenset[Lit],
            asked: frozenset[str] = frozenset()) -> None:
    model = oracle.model
    if isinstance(answer, Inquiry):
        assert lit(answer.literal)[0] not in asked, ("asks again what an inquiry above asked", answer.literal, asked)
    want = oracle.answer(snapshot, assumable, asked)
    state = oracle.start(snapshot)
    if want.kind == "contradicted":
        assert isinstance(answer, PlanningRefused), (answer, want)
        assert any("Contradicted" in problem for problem in answer.problems), answer.problems
    elif want.kind == "plan":
        assert isinstance(answer, Plan), (answer, want)
        assert answer.assumptions == ()
        final, cost = replay(model, state, answer.steps)
        assert all(final.holds(literal) for literal in oracle.goal) and model.settled(final), final
        assert cost == want.cost, (cost, want.cost)
        assert answer.established == (cost.unestablished == 0)
    elif want.kind == "inquire":
        assert isinstance(answer, Inquiry), (answer, want)
        signal, value = lit(answer.literal)
        assert signal in want.choices, (signal, want)
        assert oracle.investigates(answer.investigator, signal), (answer.investigator, signal)
        rest = frozenset(literal for literal in assumable if literal[0] != signal)
        for branch, holds in ((answer.if_true, value), (answer.if_false, not value)):
            matches(oracle, branch, observing(snapshot, signal, holds), rest, asked | {signal})
    else:
        assert isinstance(answer, NoPlan), (answer, want)
        found = tuple((lit(u.literal), u.reason, frozenset(lit(name)[0] for name in u.unknowable)) for u in answer.unsolved)
        assert found == want.unsolved, (found, want)
        if want.alternative is None:
            assert answer.alternative is None, answer.alternative
        else:
            alternative = answer.alternative
            assert isinstance(alternative, Plan), (answer, want)
            assumed = {lit(literal) for literal in alternative.assumptions}
            assert assumed and assumed <= assumable and not {s for s, _ in assumed} & {s for s, _ in state.known}
            final, cost = replay(model, oracle.start(replace(snapshot, known=snapshot.known | assumed)), alternative.steps)
            assert all(final.holds(literal) for literal in oracle.goal) and model.settled(final), final
            assert Cost(cost.unestablished, len(assumed), cost.executed, cost.model, cost.order) == want.alternative.cost


# Every plan the answer holds, in every world a snapshot leaves open, an inquiry's answer and an
# alternative's assumptions observed too, runs as the world runs it (holds_in) to the goal, and the
# model's state along it embeds every world's (embedded); a plan over no admitted world is a failure, not a
# vacuous pass (a-jk-pc-nonvacuous-1019). Raises AssertionError naming the first world and turn that fail.
# am[implements a-jk-po-worlds-1018@36f08f] am[implements a-jk-po-oracle-api-1018@6ad604]
# am[implements a-jk-po-observation-as-reading-1018@32a792] am[implements a-jk-pc-nonvacuous-1019@63deb0]
def holds_everywhere(oracle: Oracle, answer: object, snapshot: State) -> None:
    if isinstance(answer, Inquiry):
        signal, value = lit(answer.literal)
        for branch, holds in ((answer.if_true, value), (answer.if_false, not value)):
            holds_everywhere(oracle, branch, observing(snapshot, signal, holds))
        return
    if isinstance(answer, PlanningRefused):
        return
    if isinstance(answer, NoPlan):
        if answer.alternative is not None:
            assumed = frozenset(lit(literal) for literal in answer.alternative.assumptions)
            holds_everywhere(oracle, answer.alternative, replace(snapshot, known=snapshot.known | assumed))
        return
    model = oracle.model
    branches = oracle.worlds(snapshot)
    assert branches, ("a plan over no world the readings admit", snapshot)
    holds_in(model, branches, answer.steps, oracle.goal)
    branches = frozenset().union(*(fixpoints(model, branch, landing=True) for branch in branches))
    ordinary = [step for step in answer.steps if step.kind in ("start", "act", "investigate")]
    for turn, (state, step) in enumerate(zip(_turns(model, oracle.start(snapshot), answer.steps),
                                             ordinary + [None])):
        for branch in branches:
            assert embedded(state, branch), ("the model's state does not embed the world", turn, state, branch)
        if step is not None:
            move = Move(model.index[step.procedure], step.step if step.kind != "start" else "start")
            branches = frozenset().union(*(fixpoints(model, model.step(branch, move), landing=True) for branch in branches))


# The model's state before each ordinary step of a plan and after its last step.
# am[implements a-jk-po-worlds-1018@36f08f]
def _turns(model: Model, state: State, steps: Sequence[object]) -> list[State]:
    turns = []
    for step in steps:
        if step.kind in ("start", "act", "investigate"):
            turns.append(state)
        state = model.apply(state, Move(model.index[step.procedure], step.step if step.kind in ("act", "investigate") else step.kind))
    return turns + [state]


# --- the composer -------------------------------------------------------------------------------------


# The composer's choice on a single-act library: for each goal literal the state does not establish, the
# first declared procedure achieving it whose unmet When literals the composer can establish in turn,
# chaining backward and never through a procedure already chosen on the way. Answers the procedures
# in the order they are applied, or None when some goal literal has no admitted way.
# Time: at most p! chains over p procedures, p at most 3 here.
# am[implements a-jk-po-composer-1018@c2af62]
def composed(model: Model, state: State, goal: Sequence[Lit]) -> tuple[int, ...] | None:
    def way(literal: Lit, known: frozenset[Lit], chain: tuple[int, ...]) -> tuple[tuple[int, ...], frozenset[Lit]] | None:
        if literal in known:
            return (), known
        for index, procedure in enumerate(model.procedures):
            if index in chain or literal not in model.achieves(procedure):
                continue
            applied: tuple[int, ...] = ()
            current = known
            for needed in sorted(model.when(procedure)):
                sub = way(needed, current, chain + (index,))
                if sub is None:
                    break
                applied, current = applied + sub[0], sub[1]
            else:
                return applied + (index,), written(current, model.achieves(procedure))
        return None

    order: tuple[int, ...] = ()
    known = state.known
    for literal in goal:
        found = way(literal, known, ())
        if found is None:
            return None
        order, known = order + found[0], found[1]
    return order

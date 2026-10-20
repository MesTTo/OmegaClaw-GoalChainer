"""Purpose: test the planner's public plan and admit against an independent finite model, planning_oracle,
over generated worlds of the one-entity sublanguage: renamed signals, actions, entities, controls,
procedures, steps and investigators, read through read_domain and read_procedures, with readings detected
or refuted, checked or unchecked, or absent, under the agreed soundness contract (c-jk-pc-agreed-1019).
read_procedures refuses a world's library exactly where the model finds a live undo cycle among its
Derives (R2), and otherwise reads the library the world's data builds. plan's answer is the model's:
PlanningRefused naming Contradicted where no world settles to the readings (C1); a Plan exactly when brute
force over the model's state, which forgets what a possibly enabled Finish or Derive could overwrite, finds a
schedule to a settled state holding the goal through roots whose own Finish and Derive moves end in one
rest state (R1), at its least cost key, replaying under Finish and Derive priority; else the inquiry
minimal by dead branches, depth and steps, each branch the model's answer for its state and a branch no
world settles to dead; else NoPlan with each goal literal's reason and the least assumption-resting
alternative. Every plan reaches the goal in every world the observations leave open, of which there is at
least one, and the model's state along it embeds each world's. The model's own answers do too, with no
planner run: the finite instance of proofs/PlanningModel.lean's plan_sound. Replayed as the executor's
journal, each plan step is admitted at its turn. Called again with the journal and readings any run of the
model leaves, an act in flight or an instance whose needed steps all have receipts included, classified by
the worlds the readings admit (R3), plan answers as the model does from that snapshot. On single-act
libraries the planner departs from the composer's first-declared way only for a smaller (U E M). The pinned
worlds include each counterexample the contract repairs. The planner's tests start its module group and
call no service."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

from hypothesis import HealthCheck, event, example, given, settings
from hypothesis import strategies as st
import pytest

from goal_chainer.domains.loader import read_domain
from goal_chainer.planning.procedures import (
    AchieveStep,
    ActStep,
    InvestigateStep,
    Investigator,
    NegatedLiteral,
    Procedure,
    ProcedureError,
    ProcedureLibrary,
    QualifiedLiteral,
    SignalLiteral,
    read_procedures,
)
from goal_chainer.planning.projection import (
    Admitted,
    Dispatched,
    Finished,
    Inquiry,
    NoPlan,
    Plan,
    PlanningRefused,
    Receipt,
    Started,
    admit,
    plan,
)
from goal_chainer.reading_projection import EntityReading
from goal_chainer.relevance.signals import SignalReading
from planning_oracle import (
    Cost,
    Lit,
    Model,
    Move,
    Oracle,
    State,
    composed,
    holds_everywhere,
    lit,
    matches,
    procedure_literal,
    replay,
    start_state,
    undo_cycle,
)
from request_support import budget

AT = datetime(2026, 10, 18, 6, 0, tzinfo=timezone.utc)
# When the executor dispatched an act: after the readings its admission rested on, observed a minute
# before the plan, and no later than the plan's time, past which plan refuses a dispatch
# (a-integrate-oracle-feedback-api-1018).
# am[implements a-integrate-oracle-feedback-api-1018@666c8f]
DISPATCHED_AT = AT - timedelta(seconds=30)
# When the executor reads again what an act's reaction, a Finish or a Derive it recorded wrote: after every
# dispatch, as the planner's precondition asks of readings an act may have superseded
# (c-jk-pc-request-path-currentness-1019).
# am[implements a-jk-pc-currentness-boundary-1019@542623]
REFRESHED_AT = AT - timedelta(seconds=10)
# About 50 worlds per property keeps the file near two minutes; the same worlds every run, as the
# repository's other gated properties draw them, so a gate's verdict belongs to its revision.
# am[rests-on c-jk-po-boundary-agreed-1018@eea636]
ACCEPTANCE = settings(max_examples=50, deadline=None, derandomize=True, suppress_health_check=[HealthCheck.too_slow])
ESTIMATORS = ("deterministic", "model-proposed")
# Plain names the domain and procedure readers accept, MeTTa keywords and the grammars' and the
# planner's own heads among them, so no part of the planner may read a name as anything but data. An
# entity named agenda, or a control named after a planner control, is a world plan refused at b3c52ef
# (i-jk-po-reserved-entity-names-1018), kept in the space and pinned as examples below. True and False
# are no plain name to read_domain, nor is Error, MeTTa's error constructor, from 7955695; the procedure
# reader takes Error as data, so it names procedures, steps and investigators here.
# am[implements a-jk-po-generators-1018@3f02c5] am[rests-on c-jk-po-boundary-agreed-1018@eea636]
# am[implements a-jk-po-names-by-reader-1018@6e831f] am[rests-on c-jk-po-error-library-names-d6f50ec-1018@cdc16a]
KEYWORDS = ("if", "let", "case", "superpose", "empty", "Not", "Signal", "Step", "When", "None", "Done", "Inst",
            "Cost", "new", "build", "Root", "Site", "agenda", "Statement", "Instance", "Agenda")
NAMES = st.one_of(st.from_regex(r"[a-z][a-z0-9_-]{0,6}", fullmatch=True), st.sampled_from(KEYWORDS))
LIBRARY_NAMES = st.one_of(NAMES, st.just("Error"))


# One generated world of the sublanguage, as names and plain values, rendered to the readers' texts.
# am[implements a-jk-po-generators-1018@3f02c5]
@dataclass(frozen=True)
class World:
    signals: tuple[str, ...]
    actions: tuple[str, ...]
    entity: str
    control: str
    # (name, achieves, when, steps): a literal is (signal, value) and a step (id, kind, target, after).
    procedures: tuple[tuple[str, tuple[Lit, ...], tuple[Lit, ...], tuple[tuple[str, str, object, tuple[str, ...]], ...]], ...]
    investigators: tuple[tuple[str, tuple[Lit, ...]], ...]
    readings: tuple[tuple[str, tuple[str, str]], ...]
    goal: tuple[Lit, ...]
    # (action, the literal its reaction reads): the action's act turns that literal to its opposite.
    reactions: tuple[tuple[str, Lit], ...] = ()

    def domain_text(self) -> str:
        return "\n".join([
            '(gc-domain "generated")',
            "(gc-policy-version generated-v1)",
            '(gc-authority advisory 0 "Recommend.")',
            *(f"(gc-estimator-ceiling {estimator} advisory)"
              for estimator in ("model-proposed", "receipt-calibrated", "measured", "deterministic", "human-asserted")),
            *(f'(gc-action {action} "act" "An act." (authority advisory))' for action in self.actions),
            '(gc-goal finish owner individual 0.5 "Finish." (priority-source policy:generated))',
            "(gc-reading-domain generated)",
            '(gc-reading-model "jev-1.13.0")',
            '(gc-reading-language "en")',
            '(gc-reading-instructions "Decide. Proposition: ")',
            '(gc-reading-option supported for "true")',
            '(gc-reading-option contradicted against "false")',
            '(gc-reading-option unknown none "silent")',
            *(f'(gc-reading-proposition {signal} "A signal holds." "Does it hold?")' for signal in self.signals),
            '(gc-ranking-instruction "Retrieve.")',
            f"(gc-brs-control {self.control} (Ports) active)",
            f"(gc-brs-entity {self.entity} {self.control})",
            f"(gc-brs-in {self.entity} (Root 0))",
            *(f"(gc-brs-literal (Signal {signal}) (On {self.entity}))" for signal in self.signals),
            *(self.reaction_text(action, read) for action, read in self.reactions),
        ])

    # A reaction toggling one signal of the entity, in the form WRITES_SENSITIVE of
    # tests/test_planning_knowledge.py writes: its redex holds the entity's node and the literal it reads,
    # its reactum the same node and that literal's opposite (a-jk-po-act-reactions-1018).
    def reaction_text(self, action: str, read: Lit) -> str:
        def term(node: str, value: Lit) -> str:
            control = f"(Signal {value[0]})" if value[1] else f"(Not (Signal {value[0]}))"
            return (f"(Bigraph (Inner 1 ()) (Outer 1 ()) (Nodes (N I {self.control}) (N {node} {control}))"
                    f" (Place (In I (Root 0)) (In {node} I) (In (Site 0) I)) (Link))")

        return (f"(gc-brs-reaction {action} (Redex {term('w', read)}) (Reactum {term('s', (read[0], not read[1]))})"
                " (Eta (0 0)) (Conditions))")

    def library_text(self) -> str:
        reacting = {action for action, _ in self.reactions}

        def literal(value: Lit) -> str:
            return f"(Signal {value[0]})" if value[1] else f"(Not (Signal {value[0]}))"

        def step(step_id: str, kind: str, target: object, after: tuple[str, ...]) -> str:
            shown = target if kind == "act" else literal(target)
            binds = f" (Bind (I {self.entity}))" if kind == "act" and target in reacting else ""
            return f"(Step {step_id} {kind} {shown} (After {' '.join(after)}){binds})"

        rows = ["(gc-procedures generated-v1)"]
        for name, achieves, when, steps in self.procedures:
            rows.append(f"(gc-procedure {name} (Achieves {' '.join(map(literal, achieves))}) "
                        f"(When {' '.join(map(literal, when))}) (Steps {' '.join(step(*s) for s in steps)}))")
        for name, observes in self.investigators:
            rows.append(f"(gc-investigator {name} {' '.join(map(literal, observes))})")
        return "\n".join(rows)

    # The library as the procedure dataclasses hold it, built from the world's data with no reader, so the
    # model can say what read_procedures must refuse without reading through it.
    # am[implements a-jk-pc-acceptance-1019@69487b]
    def library(self) -> ProcedureLibrary:
        reacting = {action for action, _ in self.reactions}

        def step(step_id: str, kind: str, target: object, after: tuple[str, ...]):
            if kind == "act":
                return ActStep(step_id, target, after, (("I", self.entity),) if target in reacting else ())
            return (InvestigateStep if kind == "investigate" else AchieveStep)(step_id, procedure_literal(target), after)

        procedures = tuple(Procedure(name, tuple(map(procedure_literal, achieves)), tuple(map(procedure_literal, when)),
                                     tuple(step(*s) for s in steps))
                           for name, achieves, when, steps in self.procedures)
        investigators = tuple(Investigator(name, tuple(map(procedure_literal, observes)))
                              for name, observes in self.investigators)
        return ProcedureLibrary("generated-v1", "generated-procedures.metta", "", procedures, investigators)

    # The model's oracle over the world's own data, no reader run: its library, each action's reaction the
    # toggle of the literal it reads, as Oracle.of reads the domain's reaction terms.
    # am[implements a-jk-pc-model-answers-1019@a0f897]
    def oracle(self) -> Oracle:
        reactions = {action: (read, (read[0], not read[1])) for action, read in self.reactions}
        return Oracle.over(self.library(), reactions, self.signals, self.goal)

    # The domain and the library as the readers give them, or None where the model finds a live undo cycle
    # among the library's Derives, once read_procedures is seen to refuse it as cyclic-undo (R2); wherever the
    # reader accepts, it reads the library the world's data builds.
    # am[implements a-jk-pc-acceptance-1019@69487b] am[implements a-jk-pc-refusal-forms-1019@d6bf39] am[verifies a-jk-pc-r2-undo-graph-1019@fc3557]
    def read(self) -> tuple[object, ProcedureLibrary] | None:
        domain = read_domain(self.domain_text(), "generated", budget=budget())
        built = self.library()
        if undo_cycle(Model(built)) is not None:
            with pytest.raises(ProcedureError, match="cyclic-undo"):
                read_procedures(self.library_text(), "generated-procedures.metta", domain, budget=budget())
            return None
        library = read_procedures(self.library_text(), "generated-procedures.metta", domain, budget=budget())
        assert (library.procedures, library.investigators) == (built.procedures, built.investigators)
        return domain, library

    def signal_readings(self) -> list[SignalReading]:
        return [SignalReading(signal, state, "test", estimator, observed_at=AT - timedelta(minutes=1))
                for signal, (state, estimator) in self.readings]

    def goal_literals(self) -> tuple[SignalLiteral | NegatedLiteral, ...]:
        return tuple(map(procedure_literal, self.goal))

    # plan's answer with no receipts, or None where read refuses the library (R2): no generated library
    # declares a promotion rule, so no procedure's track holds and every application a plan commits to is
    # unestablished, the U the model counts.
    # am[implements a-integrate-oracle-feedback-api-1018@666c8f]
    def plan(self) -> tuple[object, ProcedureLibrary, object] | None:
        read = self.read()
        if read is None:
            return None
        domain, library = read
        return domain, library, planned(self.goal_literals(), domain=domain, library=library,
                                        readings=self.signal_readings(), journal=(), rows=(), receipts={}, at=AT,
                                        budget=budget())


# plan's answer, or the PlanningRefused it raises for readings no world settles to (C1), which is the
# answer the model expects there, so a test compares it like any other.
# am[implements a-jk-pc-acceptance-1019@69487b] am[implements a-jk-pc-refusal-forms-1019@d6bf39]
def planned(goal, **inputs) -> object:
    try:
        return plan(goal, **inputs)
    except PlanningRefused as refused:
        return refused


# `count` distinct names drawn from `names`.
# am[implements a-jk-po-generators-1018@3f02c5]
def distinct(count: int, names=NAMES):
    return st.lists(names, min_size=count, max_size=count, unique=True)


# A world: one to four signals, one to three actions, a third of them toggling one signal by their
# reaction, one to three procedures of one to three steps over those signals, at most two
# investigators, one reading or none per signal, and a goal of one or two literals of distinct
# signals. Every procedure is one the procedure policy accepts: distinct procedure
# names, distinct investigator names and distinct step ids within a procedure, the policy's three
# separate namespaces, so one name may be a procedure, an investigator and a step at once; at least one
# step; After naming earlier steps only; and no literal achieved beside its negation. A single-act world
# gives each procedure exactly one act step and its actions no reaction, the composer's libraries.
# am[implements a-jk-po-generators-1018@3f02c5] am[implements a-jk-po-act-reactions-1018@4ac76f]
@st.composite
def worlds(draw, single_act: bool = False) -> World:
    signals = tuple(draw(distinct(draw(st.integers(1, 4)))))
    actions = tuple(draw(distinct(draw(st.integers(1, 3)))))
    entity, control = draw(distinct(2))
    literals = st.tuples(st.sampled_from(signals), st.booleans())

    def consistent(values):
        return tuple(dict(values).items())

    procedures = []
    for name in draw(distinct(draw(st.integers(1, 3)), LIBRARY_NAMES)):
        achieves = consistent(draw(st.lists(literals, min_size=1, max_size=2)))
        when = consistent(draw(st.lists(literals, max_size=2)))
        steps = []
        for step_id in draw(distinct(1 if single_act else draw(st.integers(1, 3)), LIBRARY_NAMES)):
            kind = "act" if single_act else draw(st.sampled_from(("act", "investigate", "achieve")))
            target = draw(st.sampled_from(actions)) if kind == "act" else draw(literals)
            after = tuple(draw(st.lists(st.sampled_from([s[0] for s in steps]), unique=True, max_size=2))) if steps else ()
            steps.append((step_id, kind, target, after))
        procedures.append((name, achieves, when, tuple(steps)))
    investigators = tuple((name, consistent(draw(st.lists(literals, min_size=1, max_size=2))))
                          for name in draw(distinct(draw(st.integers(0, 2)), LIBRARY_NAMES)))
    readings = tuple((signal, (draw(st.sampled_from(("detected", "refuted"))), draw(st.sampled_from(ESTIMATORS))))
                     for signal in signals if draw(st.booleans()))
    goal = consistent(draw(st.lists(literals, min_size=1, max_size=2)))
    reactions = () if single_act else tuple((action, draw(literals)) for action in actions if draw(st.integers(0, 2)) == 0)
    return World(signals, actions, entity, control, tuple(procedures), investigators, readings, goal, reactions)


# A procedure writing not-x, one needing not-x to reach y, and a Derive reading not-x and writing z: the
# minimal world where plan at b3c52ef answers NoPlan, since no step follows a Derive
# (c-jk-po-derive-blocks-after-b3c52ef-1018), while the model plans past the Derive.
# am[verifies a-jk-po-brute-force-1018@41762b] am[rests-on c-jk-po-derive-blocks-after-b3c52ef-1018@a907e6]
DERIVE_THEN_STEP = World(
    signals=("x", "y", "z"), actions=("go",), entity="thing", control="Thing",
    procedures=(("writer", (("x", False),), (), (("w", "act", "go", ()),)),
                ("user", (("y", True),), (("x", False),), (("u", "act", "go", ()),)),
                ("derive", (("z", True),), (), (("d", "achieve", ("x", False), ()),))),
    investigators=(), readings=(), goal=(("y", True),))
# The same one-act world with its entity named after the planner's own agenda node
# (c-jk-po-entity-name-collisions-b3c52ef-1018), its control after the planner's witness control
# (c-jk-po-control-named-not-b3c52ef-1018), or its procedure after MeTTa's error constructor
# (c-jk-po-error-library-names-d6f50ec-1018).
# am[verifies a-jk-po-generators-1018@3f02c5] am[rests-on c-jk-po-entity-name-collisions-b3c52ef-1018@83ba24]
# am[rests-on c-jk-po-control-named-not-b3c52ef-1018@e56120] am[rests-on c-jk-po-error-library-names-d6f50ec-1018@cdc16a]
NAMED = {f"{part} {name}": World(signals=("qa", "zz"), actions=("go_a",),
                                 entity=name if part == "entity" else "thing", control=name if part == "control" else "Thing",
                                 procedures=((name if part == "procedure" else "p-one", (("qa", True),), (),
                                              (("s1", "act", "go_a", ()),)),),
                                 investigators=(), readings=(), goal=(("qa", True),))
         for part, name in (("entity", "agenda"), ("control", "Not"), ("procedure", "Error"))}
# toggle's Finish reads a=False and writes a=True, reset's writes a=False, and a is unknown: plan at
# b3c52ef interleaves Start toggle, s1, Start reset, t1, which a world holding a=False leaves at once,
# finishing toggle before reset undoes it (c-jk-po-eager-finish-unsound-b3c52ef-1018); every world
# follows Start toggle, Start reset, t1, s1.
# am[verifies a-jk-po-worlds-1018@36f08f] am[rests-on c-jk-po-eager-finish-unsound-b3c52ef-1018@e25e7d]
EAGER_FINISH = World(
    signals=("a",), actions=("go",), entity="thing", control="Thing",
    procedures=(("toggle", (("a", True),), (), (("s1", "act", "go", ()), ("s2", "achieve", ("a", False), ()))),
                ("reset", (("a", False),), (), (("t1", "act", "go", ()),))),
    investigators=(), readings=(), goal=(("a", True),))
# keep's Finish reads the literal it achieves, x unknown and uncovered: no procedure can make x false
# (c-jk-po-self-reading-writer-b3c52ef-1018).
# am[verifies a-jk-po-brute-force-1018@41762b] am[rests-on c-jk-po-self-reading-writer-b3c52ef-1018@f9c0bf]
SELF_READING_FINISH = World(
    signals=("x",), actions=("go",), entity="thing", control="Thing",
    procedures=(("keep", (("x", False),), (), (("s1", "act", "go", ()), ("s2", "achieve", ("x", False), ()))),),
    investigators=(), readings=(), goal=(("x", False),))
# raise_b, a Derive, reads not-a through two achieve steps and writes b, with a refuted and b unread: every
# world fires it, while plan at b3c52ef answered blocked, since the Derive's repeated read was never matched
# (c-jk-po-derive-duplicate-read-b3c52ef-1018). The Derive writes b and not a: one writing a whenever not-a
# holds leaves no world resting with a refuted, which C1 refuses before any read is matched.
# am[verifies a-jk-po-brute-force-1018@41762b] am[rests-on c-jk-po-derive-duplicate-read-b3c52ef-1018@b0a910]
DUPLICATE_READ_DERIVE = World(
    signals=("a", "b"), actions=("go",), entity="thing", control="Thing",
    procedures=(("raise_b", (("b", True),), (), (("s1", "achieve", ("a", False), ()), ("s2", "achieve", ("a", False), ()))),),
    investigators=(), readings=(("a", ("refuted", "deterministic")),), goal=(("b", True),))
# p's Finish writes g and undo, a Derive, reads g and writes not-g: every world ends not-g, while plan at
# b3c52ef judges the goal before undo fires (c-jk-po-goal-before-fixpoint-b3c52ef-1018).
# am[verifies a-jk-po-worlds-1018@36f08f] am[rests-on c-jk-po-goal-before-fixpoint-b3c52ef-1018@ac0a29]
GOAL_THEN_UNDO = World(
    signals=("g",), actions=("go",), entity="thing", control="Thing",
    procedures=(("p", (("g", True),), (), (("s1", "act", "go", ()),)),
                ("undo", (("g", False),), (), (("u1", "achieve", ("g", True), ()),))),
    investigators=(), readings=(), goal=(("g", True),))
# d, a Derive, reads the unknown x and writes z, which a checked reading observes false; p needs not-z.
# Every world the reading leaves open settled with x false, since one with x true would hold z, so d
# moved nothing and p plans; a K0 cancelling where no world moved would forget not-z and answer NoPlan
# (c-jk-po-k0-changed-agreed-1018).
# am[verifies a-jk-po-k0-changed-1018@d600c3]
UNRELATED_DERIVE = World(
    signals=("x", "y", "z"), actions=("go",), entity="thing", control="Thing",
    procedures=(("d", (("z", True),), (), (("s1", "achieve", ("x", True), ()),)),
                ("p", (("y", True),), (("z", False),), (("t1", "act", "go", ()),))),
    investigators=(), readings=(("z", ("refuted", "deterministic")),), goal=(("y", True),))
# p needs w and, for its act, z; q writes z and not-w, with w checked: q's Finish either comes after
# p's Start, and then p's act no longer finds w, or before it, and then p never starts, so no plan exists;
# a planner whose executed step skips re-reading When would plan p's act after q
# (c-jk-po-mutation-sites-d6f50ec-1018).
# am[verifies a-jk-po-mutants-1018@966a2f] am[rests-on c-jk-po-mutation-sites-d6f50ec-1018@71a6ff]
STEP_REREADS_WHEN = World(
    signals=("w", "z", "g"), actions=("go",), entity="thing", control="Thing",
    procedures=(("p", (("g", True),), (("w", True),), (("s", "achieve", ("z", True), ()), ("a", "act", "go", ("s",)))),
                ("q", (("z", True), ("w", False)), (), (("b", "act", "go", ()),))),
    investigators=(), readings=(("w", ("detected", "deterministic")),), goal=(("g", True),))
# p needs w, and its act's reaction reads w and writes not-w, the goal, with w checked: the act reads w
# once, as When and as its reaction's redex, so p starts, acts and finishes; an act rule holding w twice,
# once for When and once for the reaction, matches no state, which holds w once
# (c-jk-po-act-reads-when-twice-568231d-1018).
# am[verifies a-jk-po-act-reactions-1018@4ac76f] am[rests-on c-jk-po-act-reads-when-twice-568231d-1018@492709]
REACTION_READS_ITS_WHEN = World(
    signals=("w", "z"), actions=("hold",), entity="thing", control="Thing",
    procedures=(("p", (("z", True),), (("w", True),), (("k", "act", "hold", ()),)),),
    investigators=(), readings=(("w", ("detected", "deterministic")),), goal=(("w", False),),
    reactions=(("hold", ("w", True)),))
# The same act reading w through the Achieve step its After reaches instead of through When
# (c-jk-po-act-reads-achieve-twice-568231d-1018).
# am[verifies a-jk-po-act-reactions-1018@4ac76f] am[rests-on c-jk-po-act-reads-achieve-twice-568231d-1018@f7ad6a]
REACTION_READS_ITS_ACHIEVE = World(
    signals=("w",), actions=("hold",), entity="thing", control="Thing",
    procedures=(("p", (("w", False),), (), (("s", "achieve", ("w", True), ()), ("k", "act", "hold", ("s",)))),),
    investigators=(), readings=(("w", ("detected", "deterministic")),), goal=(("w", False),),
    reactions=(("hold", ("w", True)),))
# Only flip's reaction, turning not-a into a, writes the goal a, and a is unknown with no investigator: the
# act is a's writer and reads a, so NoPlan names a unknowable, not no-way (a-jk-po-reaction-writers-1018).
# am[verifies a-jk-po-reaction-writers-1018@3653ec]
REACTION_WRITES_GOAL = World(
    signals=("a", "b"), actions=("flip",), entity="thing", control="Thing",
    procedures=(("p", (("a", False),), (), (("f", "act", "flip", ()),)),),
    investigators=(), readings=(), goal=(("a", True),), reactions=(("flip", ("a", False)),))
# flip's reaction turns the read not-g into g, and p's Finish, enabled by that act, writes not-g back: the
# Finish fires with the act, so no world rests holding g, and a planner that let the Finish wait would
# stop after the act with g (c-jk-po-m1-unobservable-empty-journal-1018, which a reaction defeats).
# am[verifies a-jk-po-mutants-1018@966a2f] am[rests-on c-jk-po-m1-unobservable-empty-journal-1018@ef344f]
FINISH_UNDOES_REACTION = World(
    signals=("g",), actions=("flip",), entity="thing", control="Thing",
    procedures=(("p", (("g", False),), (), (("k", "act", "flip", ()),)),),
    investigators=(), readings=(("g", ("refuted", "deterministic")),), goal=(("g", True),),
    reactions=(("flip", ("g", False)),))
# second's Finish waits on q, which first's act turns true by flip's reaction, and the two Finishes write y
# and not-y: once both are enabled a world takes them in either order and rests in either value. The planner
# at 1d48c6c interleaves the instances so that both are enabled after first's act, and a world finishing
# second first ends with y and fails the goal not-y; R1 refuses that root, and the plan finishes first before
# second's act (c-jk-pf-cx-simultaneous-1019).
# am[verifies a-jk-pc-r1-closure-1019@f9b888] am[rests-on c-jk-pf-cx-simultaneous-1019@884a2c]
SIMULTANEOUS = World(
    signals=("q", "y"), actions=("go", "flip"), entity="thing", control="Thing",
    procedures=(("second", (("y", False),), (), (("b", "act", "go", ()), ("c", "achieve", ("q", True), ("b",)))),
                ("first", (("y", True),), (), (("a1", "act", "flip", ()),))),
    investigators=(), readings=(("q", ("refuted", "deterministic")),), goal=(("y", False),),
    reactions=(("flip", ("q", False)),))
# d1 turns a into not-a and d2 not-a into a, both once g holds, and p's Finish writes g: every world reaching
# the goal cycles with no rest, as the planner at 1d48c6c plans it, so R2 refuses the library
# (c-jk-pf-cx-derive-cycle-1019).
# am[verifies a-jk-pc-r2-undo-graph-1019@fc3557] am[rests-on c-jk-pf-cx-derive-cycle-1019@93ff37]
SMALL_CYCLE = World(
    signals=("g", "a"), actions=("go",), entity="thing", control="Thing",
    procedures=(("p", (("g", True),), (), (("x", "act", "go", ()),)),
                ("d1", (("a", False),), (), (("s", "achieve", ("g", True), ()), ("t", "achieve", ("a", True), ()))),
                ("d2", (("a", True),), (), (("s", "achieve", ("g", True), ()), ("t", "achieve", ("a", False), ())))),
    investigators=(), readings=(("g", ("refuted", "deterministic")),), goal=(("g", True),))
# up and down write y and not-y under x and not-x, and only setx's Finish writes x: no Derive moves x, so the
# two are never armed together, the undo edges between them are pruned, and R2 reads the library.
# am[verifies a-jk-pc-r2-undo-graph-1019@fc3557]
OPPOSITE_GUARDS = World(
    signals=("x", "y"), actions=("go",), entity="thing", control="Thing",
    procedures=(("up", (("y", True),), (), (("s", "achieve", ("x", True), ()),)),
                ("down", (("y", False),), (), (("s", "achieve", ("x", False), ()),)),
                ("setx", (("x", True),), (), (("k", "act", "go", ()),))),
    investigators=(), readings=(("x", ("refuted", "deterministic")),), goal=(("y", True),))
# d1 reads a and writes a and b, and d2 reads b and writes not-a: d1's write of a is no effective write, so
# d2 undoes nothing of d1's and d1 nothing of d2's, every world rests once p's Finish sets a, and R2 reads the
# library a graph over every Achieves literal would refuse (c-jk-pc-r2-effective-writes-1019).
# am[verifies a-jk-pc-r2-undo-graph-1019@fc3557] am[rests-on c-jk-pc-r2-effective-writes-1019@46c730]
EFFECTIVE_WRITES = World(
    signals=("a", "b"), actions=("go",), entity="thing", control="Thing",
    procedures=(("d1", (("a", True), ("b", True)), (), (("s", "achieve", ("a", True), ()),)),
                ("d2", (("a", False),), (), (("s", "achieve", ("b", True), ()),)),
                ("p", (("a", True),), (), (("k", "act", "go", ()),))),
    investigators=(), readings=(("a", ("refuted", "deterministic")), ("b", ("refuted", "deterministic"))),
    goal=(("b", True),))
# The parent's measured input: derive_b writes b once a holds, a is detected, and b is read refuted or
# detected. Refuted, no world rests holding a and not-b, so plan refuses the readings as Contradicted, where
# the planner at 410fc76a planned derive_b over no world; detected, the one world holds the goal and the plan
# is empty (C1, c-integrate-planner-empty-world-plan-1019).
# am[verifies a-jk-pc-c1-admitted-1019@321a3b] am[verifies a-jk-pc-nonvacuous-1019@63deb0] am[rests-on c-integrate-planner-empty-world-plan-1019@1d202f]
MEASURED = {state: World(
    signals=("a", "b"), actions=("go",), entity="thing", control="Thing",
    procedures=(("derive_b", (("b", True),), (), (("needs_a", "achieve", ("a", True), ()),)),),
    investigators=(), readings=(("a", ("detected", "deterministic")), ("b", (state, "deterministic"))),
    goal=(("b", True),)) for state in ("refuted", "detected")}
# dx writes b once x holds, b is read refuted, and px and pn reach g under x and under not-x, with xi
# observing x: plan inquires x, and its x-true branch, which no world settles to, is NoPlan contradicted,
# never a plan over no world (C1 in a branch, c-jk-pc-c1-forms-1019).
# am[verifies a-jk-pc-c1-admitted-1019@321a3b] am[rests-on c-jk-pc-c1-forms-1019@5de134]
BRANCH_CONTRADICTED = World(
    signals=("x", "b", "g"), actions=("go",), entity="thing", control="Thing",
    procedures=(("dx", (("b", True),), (), (("s", "achieve", ("x", True), ()),)),
                ("px", (("g", True),), (("x", True),), (("p1", "act", "go", ()),)),
                ("pn", (("g", True),), (("x", False),), (("n1", "act", "go", ()),))),
    investigators=(("xi", (("x", True),)),), readings=(("b", ("refuted", "deterministic")),), goal=(("g", True),))


# plan's answer is the model's, from the start state through every inquiry branch, and every plan it
# holds holds in every world the evidence leaves open, its states embedding each world's; a library R2
# refuses is checked refused (World.read).
# am[verifies a-jk-po-brute-force-1018@41762b] am[verifies a-jk-po-worlds-1018@36f08f] am[verifies a-ev-pk-api-tests-1018@a874ce]
# am[verifies a-ev-brs-worlds-oracle-1018@18b67c] am[verifies a-jk-pc-acceptance-1019@69487b]
@ACCEPTANCE
@given(worlds())
@example(DERIVE_THEN_STEP)
@example(NAMED["entity agenda"])
@example(NAMED["control Not"])
@example(NAMED["procedure Error"])
@example(EAGER_FINISH)
@example(SELF_READING_FINISH)
@example(DUPLICATE_READ_DERIVE)
@example(GOAL_THEN_UNDO)
@example(UNRELATED_DERIVE)
@example(STEP_REREADS_WHEN)
@example(REACTION_READS_ITS_WHEN)
@example(REACTION_READS_ITS_ACHIEVE)
@example(REACTION_WRITES_GOAL)
@example(FINISH_UNDOES_REACTION)
@example(SIMULTANEOUS)
@example(SMALL_CYCLE)
@example(OPPOSITE_GUARDS)
@example(EFFECTIVE_WRITES)
@example(MEASURED["refuted"])
@example(MEASURED["detected"])
@example(BRANCH_CONTRADICTED)
def test_plans_answer_as_the_model_does_and_hold_in_every_open_world(world: World) -> None:
    planned_world = world.plan()
    if planned_world is None:
        return
    domain, library, answer = planned_world
    oracle = Oracle.of(library, domain, world.goal)
    observed, assumable = start_state(world.signal_readings())
    matches(oracle, answer, State(observed), assumable)
    holds_everywhere(oracle, answer, State(observed))


# The executor's record of the steps it runs, keyed by whatever names an application to the caller: the
# journal the planner reads and the readings after those steps. Each Start opens a fresh instance; an act
# or investigation is dispatched, naming its decision and time, and receipted as applied, or only
# dispatched while it is in flight; a Finish closes its instance; and a deterministic reading replaces
# what was read of each literal a receipted act's reaction, a Finish or a Derive wrote, since the planner
# rebuilds its state from the evidence and never from a prediction, read after the dispatches as the
# planner's currentness precondition asks.
# am[verifies a-jk-po-admit-1018@8e5e63] am[verifies a-jk-po-replanning-1018@ad5d23]
# am[implements a-jk-pc-currentness-boundary-1019@542623]
@dataclass
class Execution:
    readings: dict[str, tuple[str, str]]
    journal: list[object] = field(default_factory=list)
    instances: dict[object, str] = field(default_factory=dict)
    done: dict[object, set[str]] = field(default_factory=dict)
    refreshed: set[str] = field(default_factory=set)

    def evidence(self) -> list[SignalReading]:
        return [SignalReading(s, state, "test", estimator,
                              observed_at=REFRESHED_AT if s in self.refreshed else AT - timedelta(minutes=1))
                for s, (state, estimator) in self.readings.items()]

    def take(self, key: object, procedure: str, kind: str, step: str | None, writes,
             decision: str | None = None) -> None:
        if kind == "start":
            self.instances[key], self.done[key] = f"i{len(self.journal)}", set()
            self.journal.append(Started(self.instances[key], procedure, f"j{len(self.journal)}"))
            return
        if kind in ("act", "investigate"):
            self.dispatch(key, step, decision)
            attempt = f"a{len(self.journal) - 1}"
            self.journal.append(Receipt(f"r{len(self.journal)}", self.instances[key], step, attempt, True))
            self.done[key].add(step)
        elif kind == "finish":
            self.journal.append(Finished(self.instances.pop(key)))
            del self.done[key]
        self.refresh(writes)

    # A deterministic reading of each literal of `writes`, read after the dispatches.
    def refresh(self, writes) -> None:
        for signal, value in writes:
            self.readings[signal] = ("detected" if value else "refuted", "deterministic")
            self.refreshed.add(signal)

    # No reading of the signals of `writes`: what was read of them is superseded.
    def omit(self, writes) -> None:
        for signal, _ in writes:
            self.readings.pop(signal, None)
            self.refreshed.discard(signal)

    # A dispatch names its decision: a plan step's witness digest, which the attempt's receipt would name
    # as its review fingerprint, or, for a step the model's walk takes and no plan answered, an opaque
    # digest of its instance and step. No receipt is passed, so plan reads no decision against one.
    # am[implements a-integrate-oracle-feedback-api-1018@666c8f]
    def dispatch(self, key: object, step: str, decision: str | None = None) -> None:
        instance = self.instances[key]
        self.journal.append(Dispatched(instance, step, f"a{len(self.journal)}",
                                       decision or f"sha256:walk-{instance}-{step}", DISPATCHED_AT))


# A plan replayed as the executor's journal: each step is admitted at its turn, with no reading added but
# a deterministic one for each literal a Finish or Derive has predicted (Execution). Every world takes a
# Finish or Derive as soon as it is enabled, so by its turn a reading of what it writes is superseded: a
# caller keeping its readings current, as the planner's precondition asks, omits that reading to ask about
# the step and reads it again once the step is taken. Kept, the reading can describe the world before an act
# whose Finish has since run, which strict C1 refuses as Contradicted, and read again first, it leaves a
# Derive nothing to write, which admission answers Blocked (a-ev-pc-c1-strict-1019,
# c-jk-pc-request-path-currentness-1019).
# am[verifies a-jk-po-admit-1018@8e5e63] am[verifies a-ev-pk-api-tests-1018@a874ce] am[verifies a-jk-pc-currentness-boundary-1019@542623]
@ACCEPTANCE
@given(worlds())
@example(DERIVE_THEN_STEP)
def test_every_step_of_a_plan_is_admitted_at_its_turn_through_the_journal(world: World) -> None:
    planned_world = world.plan()
    if planned_world is None or not isinstance(planned_world[2], Plan):
        return
    domain, library, answer = planned_world
    run = Execution(dict(world.readings))
    model = Oracle.of(library, domain, world.goal).model
    for position, step in enumerate(answer.steps):
        instance = None if step.kind in ("start", "derive") else run.instances[step.application]
        move = Move(model.index[step.procedure], step.step if step.kind in ("act", "investigate") else step.kind)
        if step.kind in ("finish", "derive"):
            run.omit(writes(model, move))
        verdict = admit(step, instance_id=instance, domain=domain, library=library, readings=run.evidence(),
                        journal=tuple(run.journal), rows=(), at=AT, budget=budget())
        assert isinstance(verdict, Admitted), (position, step.kind, step.procedure, step.step, verdict)
        run.take(step.application, step.procedure, step.kind, step.step, writes(model, move), step.witness.digest)


# What a move writes once taken: a Finish's or Derive's Achieves literals, an act's reaction's write.
# am[verifies a-jk-po-act-reactions-1018@4ac76f]
def writes(model: Model, move: Move) -> tuple[Lit, ...]:
    if move.kind in ("finish", "derive"):
        return model.achieves(model.procedures[move.index])
    reaction = model.reaction(move.index, move.part) if move.kind == "step" else None
    return () if reaction is None else (reaction[1],)


# A run of the model as the executor records it: from the settled start, a walk of moves the model enables,
# priority respected, each the `walk` choice among them, is run as the executor records it (Execution), and
# `dispatch`, when given, picks an act left in flight after it. Answers the run with the snapshot its
# journal and readings describe, the open instances with their receipted steps and the act in flight, and
# the literals its unchecked readings offer. A walk that stops right after an instance's last act leaves
# its Finish pending, which the worlds the readings admit decide (R3), and an act in flight may have written
# what its reaction writes, or finished its instance where it was the last step
# (a-jk-po-replanning-1018, c-jk-po-m1-unobservable-empty-journal-1018).
# am[verifies a-jk-po-replanning-1018@ad5d23]
def walked(world: World, model: Model, walk: list[int], dispatch: int | None) -> tuple[Execution, State, frozenset[Lit]]:
    observed, _ = start_state(world.signal_readings())
    state, run = model.settle(State(observed)), Execution(dict(world.readings))
    for choice in walk:
        options = model.enabled(state)
        if not options:
            break
        move = options[choice % len(options)]
        kind = move.kind if move.kind != "step" else "act"
        run.take(move.index, model.procedures[move.index].name, kind, move.part if move.kind == "step" else None,
                 writes(model, move))
        state = model.apply(state, move)
    inflight: frozenset[tuple[int, str]] = frozenset()
    acts = [move for move in model.enabled(state) if move.kind == "step"]
    if acts and dispatch is not None:
        move = acts[dispatch % len(acts)]
        run.dispatch(move.index, move.part)
        inflight = frozenset({(move.index, move.part)})
    observed, assumable = start_state(run.evidence())
    snapshot = State(observed, tuple(sorted((index, frozenset(done)) for index, done in run.done.items())), inflight=inflight)
    return run, snapshot, assumable


# Re-planning mid-run: plan called again with the journal and readings a run leaves (walked) answers as the
# model does from the snapshot they describe, and every plan it gives holds in every world the snapshot
# leaves open (a-jk-po-replanning-1018); an inquiry about a literal an act in flight may have written must
# make progress (a-jk-po-inquiry-progress-1018).
# am[verifies a-jk-po-replanning-1018@ad5d23] am[verifies a-jk-po-inquiry-progress-1018@e8df05]
def replanned(world: World, walk: list[int], dispatch: int | None) -> None:
    read = world.read()
    if read is None:
        return
    domain, library = read
    oracle = Oracle.of(library, domain, world.goal)
    run, snapshot, assumable = walked(world, oracle.model, walk, dispatch)
    answer = planned(world.goal_literals(), domain=domain, library=library, readings=run.evidence(),
                     journal=tuple(run.journal), rows=(), receipts={}, at=AT, budget=budget())
    matches(oracle, answer, snapshot, assumable)
    holds_everywhere(oracle, answer, snapshot)


# The measured input of c-integrate-k0-inflight-inquiry-exhausts-1018 as WRITES_SENSITIVE writes it:
# writer's act turns not-s into s by its reaction, s read false, and user needs not-s; with writer's
# act in flight, s may have turned, so user cannot start. data-probe observing s makes no difference,
# since observing not-s is forgotten again and observing s leaves user dead; a needy procedure needing
# s plans in the branch that observes it.
# am[verifies a-jk-po-inquiry-progress-1018@e8df05] am[rests-on c-jk-po-progress-agreed-1018@943db8]
INFLIGHT_SENSITIVE = {
    name: World(signals=("s", "u", "c"), actions=("hold", "publish"), entity="thing", control="Thing",
                procedures=(("writer", (("u", True),), (), (("w", "act", "hold", ()),)),
                            ("user", (("c", True),), (("s", False),), (("p", "act", "publish", ()),)), *extra),
                investigators=probe, readings=(("s", ("refuted", "deterministic")),), goal=(("c", True),),
                reactions=(("hold", ("s", False)),))
    for name, probe, extra in (("alone", (), ()), ("probed", (("data-probe", (("s", True),)),), ()),
                               ("needy", (("data-probe", (("s", True),)),),
                                (("needy", (("c", True),), (("s", True),), (("n", "act", "publish", ()),)),)))}
# An investigation in flight whose instance's Finish writes not-if, with an investigator for if: the
# shrunk input that exhausted 92b31f1's bound, every true branch forgetting its answer.
# am[verifies a-jk-po-inquiry-progress-1018@e8df05]
INVESTIGATION_IN_FLIGHT = World(
    signals=("if",), actions=("a",), entity="a", control="if",
    procedures=(("a", (("if", False),), (), (("a0", "act", "a", ()), ("if", "investigate", ("if", False), ("a0",)))),),
    investigators=(("new", (("if", True),)),), readings=(), goal=(("if", False),))
# keeper's act in flight turns x into not-x by its reaction, and keeper's Finish, which waits on y,
# writes x, so neither answer about x survives the settle and x is no inquiry there; y is, and once y is
# observed false keeper's Finish can no longer fire, not-x survives, and x is asked beneath it: the
# literal an inquiry drops stays askable on the paths below (a-jk-po-inquiry-progress-1018).
# am[verifies a-jk-po-inquiry-progress-1018@e8df05]
DROPPED_INQUIRY_ASKED_LATER = World(
    signals=("x", "y", "g"), actions=("hold", "qa", "ra"), entity="thing", control="Thing",
    procedures=(("keeper", (("x", True),), (), (("k", "act", "hold", ()), ("w", "achieve", ("y", True), ("k",)))),
                ("q", (("g", True),), (("x", False),), (("q1", "act", "qa", ()),)),
                ("r", (("g", True),), (("y", True),), (("r1", "act", "ra", ()),))),
    investigators=(("xi", (("x", True),)), ("yi", (("y", True),))), readings=(("x", ("detected", "deterministic")),),
    goal=(("g", True),), reactions=(("hold", ("x", True)),))
# p's act is receipted and its Finish waits on y, so the snapshot cannot tell whether p has finished;
# observing y true decides it: every world that reading admits has finished p, so p is completed with g
# entailed, and the branch plans p's journal-only Finish as plan does once a reading of y arrives
# (a-jk-po-observation-as-reading-1018, a-jk-pc-r3-exact-amend-1019).
# am[verifies a-jk-po-observation-as-reading-1018@32a792] am[verifies a-jk-pc-r3-exact-amend-1019@9a3391]
OBSERVATION_ENABLES_FINISH = World(
    signals=("y", "g"), actions=("pa",), entity="thing", control="Thing",
    procedures=(("p", (("g", True),), (), (("p1", "act", "pa", ()), ("w", "achieve", ("y", True), ("p1",)))),),
    investigators=(("yi", (("y", True),)),), readings=(), goal=(("g", True),))
# mover's act in flight lets its Finish set a, which nothing read, and deriver reads a and writes not-b
# over the b that was read: in the world where a was false at the snapshot, mover lands, finishes and
# deriver then steps, so b is no longer known and the empty plan is no answer (a-jk-po-moved-writes-1018).
# am[verifies a-jk-po-moved-writes-1018@e149e1]
UNKNOWN_WRITE_MOVES = World(
    signals=("a", "b"), actions=("go",), entity="thing", control="Thing",
    procedures=(("mover", (("a", True),), (), (("m", "act", "go", ()),)),
                ("deriver", (("b", False),), (), (("d", "achieve", ("a", True), ()),))),
    investigators=(), readings=(("b", ("detected", "deterministic")),), goal=(("b", True),))
# keeper's act in flight may turn x into not-x, and q's Finish reads not-x: asking x plans q where the
# answer is not-x, and where it is x the settle forgets it, x can be asked no more on that path, and g
# is unknowable there for want of x (a-jk-po-asked-uncovered-1018).
# am[verifies a-jk-po-asked-uncovered-1018@91b320]
ASKED_THEN_FORGOTTEN = World(
    signals=("x", "z", "g"), actions=("hold", "qa"), entity="thing", control="Thing",
    procedures=(("keeper", (("z", True),), (), (("k", "act", "hold", ()),)),
                ("q", (("g", True),), (), (("q1", "act", "qa", ()), ("c", "achieve", ("x", False), ("q1",))))),
    investigators=(("xi", (("x", True),)),), readings=(("x", ("detected", "deterministic")),), goal=(("g", True),),
    reactions=(("hold", ("x", True)),))
# The journal started p and the plan acts and finishes it: its first step of that instance commits to
# the application, so the plan is unestablished (a-jk-po-first-touch-1018).
# am[verifies a-jk-po-first-touch-1018@dc89ae]
JOURNAL_FIRST_TOUCH = World(
    signals=("g",), actions=("go",), entity="thing", control="Thing",
    procedures=(("p", (("g", True),), (), (("s", "act", "go", ()),)),),
    investigators=(), readings=(), goal=(("g", True),))
# i's act k is receipted and its Finish reads l, which a checked reading refutes, and d1 turns x into l: in a
# world with x true before the readings d1 fires, i finishes and writes not-x and not-l, resting with the
# reading and i closed, and in one with x false i stays open. The planner at 1d48c6c keeps i open, so its
# state does not embed the first world (goal not-l) or its plan fails there once setter's act turns not-l
# into l (goal not-l and z); R3 makes i uncertain (c-jk-pf-cx-transient-finish-1019).
# am[verifies a-jk-pc-r3-exact-amend-1019@9a3391] am[rests-on c-jk-pf-cx-transient-finish-1019@b0e89c]
TRANSIENT_FINISH = {name: World(
    signals=("x", "l", "z"), actions=("go", "flip"), entity="thing", control="Thing",
    procedures=(("i", (("x", False), ("l", False)), (), (("k", "act", "go", ()), ("c", "achieve", ("l", True), ("k",)))),
                ("d1", (("l", True),), (), (("s", "achieve", ("x", True), ()),)),
                ("setter", (("z", True),), (), (("a", "act", "flip", ()), ("b", "act", "go", ("a",))))),
    investigators=(), readings=(("l", ("refuted", "deterministic")),), goal=goal,
    reactions=(("flip", ("l", False)),)) for name, goal in (("embedding", (("l", False),)),
                                                            ("goal", (("l", False), ("z", True))))}
# p's act p1 is receipted and its Finish reads u, which a checked reading refutes and verify's Finish writes:
# a world with u true before the readings finishes p and keeps u, so no reading admits it, and p is open in
# every world that is admitted. Exact R3 keeps p open and plans verify, then p's Finish; the syntactic rule,
# which makes p uncertain because its read is not known, loses that plan (a-jk-pc-r3-exact-amend-1019).
# am[verifies a-jk-pc-r3-exact-amend-1019@9a3391]
CERTAIN_OPEN = World(
    signals=("u", "c"), actions=("go", "check"), entity="thing", control="Thing",
    procedures=(("p", (("c", True),), (), (("p1", "act", "go", ()), ("w", "achieve", ("u", True), ("p1",)))),
                ("verify", (("u", True),), (), (("v1", "act", "check", ()),))),
    investigators=(), readings=(("u", ("refuted", "deterministic")),), goal=(("c", True),))


# am[verifies a-jk-po-replanning-1018@ad5d23] am[verifies a-ev-pk-api-tests-1018@a874ce]
@ACCEPTANCE
@given(worlds(), st.lists(st.integers(0, 5), max_size=6), st.none() | st.integers(0, 5))
@example(INFLIGHT_SENSITIVE["alone"], [0], 0)
@example(INFLIGHT_SENSITIVE["probed"], [0], 0)
@example(INFLIGHT_SENSITIVE["needy"], [0], 0)
@example(INVESTIGATION_IN_FLIGHT, [0, 0], 0)
@example(DROPPED_INQUIRY_ASKED_LATER, [0], 0)
@example(OBSERVATION_ENABLES_FINISH, [0, 0], None)
@example(UNKNOWN_WRITE_MOVES, [0], 0)
@example(ASKED_THEN_FORGOTTEN, [0], 0)
@example(JOURNAL_FIRST_TOUCH, [0], None)
@example(TRANSIENT_FINISH["embedding"], [0, 0], None)
@example(TRANSIENT_FINISH["goal"], [0, 0], None)
@example(CERTAIN_OPEN, [0, 0], None)
def test_plan_answers_again_as_the_model_does_from_any_journal_a_run_leaves(world: World, walk: list[int],
                                                                            dispatch: int | None) -> None:
    replanned(world, walk, dispatch)


# The model's own answers, as a planner meeting it gives them (Oracle.reference), hold in every world each
# snapshot leaves open, at the start and after any run, and agree with what the model expects (matches):
# the finite instance of proofs/PlanningModel.lean's plan_sound and plan_nonvacuous under R1, R2, R3 and C1,
# checked with no planner run, so a gap in the contract shows apart from a defect of the planner. A library
# R2 refuses has no answer to check. The events count each kind of answer, which
# --hypothesis-show-statistics reports.
# am[verifies a-jk-pc-model-answers-1019@a0f897] am[rests-on c-jk-pc-agreed-1019@fd2f81] am[rests-on c-jk-pc-invariant-1019@bd062e]
@ACCEPTANCE
@given(worlds(), st.lists(st.integers(0, 5), max_size=6), st.none() | st.integers(0, 5))
@example(SIMULTANEOUS, [], None)
@example(SMALL_CYCLE, [], None)
@example(OPPOSITE_GUARDS, [], None)
@example(EFFECTIVE_WRITES, [], None)
@example(MEASURED["refuted"], [], None)
@example(MEASURED["detected"], [], None)
@example(BRANCH_CONTRADICTED, [], None)
@example(TRANSIENT_FINISH["embedding"], [0, 0], None)
@example(TRANSIENT_FINISH["goal"], [0, 0], None)
@example(CERTAIN_OPEN, [0, 0], None)
@example(OBSERVATION_ENABLES_FINISH, [0, 0], None)
def test_the_models_own_answers_hold_in_every_open_world(world: World, walk: list[int], dispatch: int | None) -> None:
    oracle = world.oracle()
    if undo_cycle(oracle.model) is not None:
        event("R2 refuses the library")
        return
    _, snapshot, assumable = walked(world, oracle.model, walk, dispatch)
    answer = oracle.reference(snapshot, assumable)
    event(f"the model answers {type(answer).__name__}")
    matches(oracle, answer, snapshot, assumable)
    holds_everywhere(oracle, answer, snapshot)


# The composer differential: on a single-act library, where the composer's first declared way per goal
# literal is a valid plan the model replays to the goal, plan finds a plan too, and it applies other
# procedures than the composer only for a strictly smaller (U E M), ORDER deciding nothing (the
# projection proposal section 5's named change); each disagreement is named in the failure.
# am[verifies a-jk-po-composer-1018@c2af62] am[verifies a-ev-pk-api-tests-1018@a874ce]
@ACCEPTANCE
@given(worlds(single_act=True))
def test_plan_departs_from_the_composer_only_for_a_smaller_unestablished_executed_model_count(world: World) -> None:
    _, library, answer = world.plan()  # a single-act library has no Derive, so R2 never refuses it
    model = Model(library)
    observed, _ = start_state(world.signal_readings())
    start = model.settle(State(observed))
    order = composed(model, start, world.goal)
    if order is None:
        return
    state, cost = start, Cost()
    for index in order:
        for part in ("start", model.executed_steps(model.procedures[index])[0], "finish"):
            move = Move(index, part)
            if move not in model.enabled(state):
                return  # the composer's way is no valid plan here: it never sees interference
            state, cost = model.apply(state, move), cost.plus(move)
    if not (all(state.holds(literal) for literal in world.goal) and model.settled(state)):
        return
    assert isinstance(answer, Plan), ("the composer plans and plan does not", order, answer)
    _, planned = replay(model, start, answer.steps)
    applied = sorted(model.index[step.procedure] for step in answer.steps if step.kind in ("start", "derive"))
    if applied != sorted(order):
        key = (planned.unestablished, planned.executed, planned.model)
        composer = (cost.unestablished, cost.executed, cost.model)
        assert key < composer, ("plan departs from the composer without the named change", applied, order, key, composer)


# The model's boundary on reactions: flip's toggle as the generator writes it, and changes to its redex
# the domain loader reads, each keeping the node controls, Eta and conditions, that place the signal's
# node or the site elsewhere, add a root or an outer name, or add a link row. Oracle.of reads only the
# toggle and refuses the rest (a-jk-po-toggle-structure-1018, c-jk-po-toggle-shapes-loader-a5b068b-1018).
# am[verifies a-jk-po-toggle-structure-1018@af3d3f]
TOGGLE = World(signals=("g",), actions=("flip",), entity="thing", control="Thing",
               procedures=(("p", (("g", True),), (), (("k", "act", "flip", ()),)),),
               investigators=(), readings=(), goal=(("g", True),), reactions=(("flip", ("g", False)),))


# am[verifies a-jk-po-toggle-structure-1018@af3d3f]
@pytest.mark.parametrize(("old", "new"), [
    ("(In w I)", "(In w (Root 0))"),
    ("(In (Site 0) I)", "(In (Site 0) (Root 0))"),
    ("(In (Site 0) I)", "(In (Site 0) w)"),
    ("(Outer 1 ())", "(Outer 2 ())"),
    ("(Outer 1 ())", "(Outer 1 (x))"),
    ("(Link))", "(Link (P w 0 x)))"),
], ids=["signal-under-root", "site-under-root", "site-under-signal", "two-roots", "outer-name", "link-row"])
def test_the_model_refuses_a_reaction_the_loader_reads_but_no_toggle_of_the_entity(old: str, new: str) -> None:
    text = TOGGLE.domain_text()
    assert old in text
    domain = read_domain(text.replace(old, new, 1), "generated", budget=budget())
    library = read_procedures(TOGGLE.library_text(), "generated-procedures.metta", domain, budget=budget())
    with pytest.raises(ValueError, match="the reaction of flip, which toggles no one signal of the entity"):
        Oracle.of(library, domain, TOGGLE.goal)


# The toggle itself is read as its literals, and a bind on its signal's node, which would let an act stand
# for that node, never reaches the model, since the procedure reader refuses it.
# am[verifies a-jk-po-toggle-structure-1018@af3d3f]
def test_the_model_reads_the_toggle_and_the_reader_refuses_a_bind_on_its_signal_node() -> None:
    domain, library = TOGGLE.read()
    assert Oracle.of(library, domain, TOGGLE.goal).model.reactions == {"flip": (("g", False), ("g", True))}
    with pytest.raises(ProcedureError, match="mistyped-bind"):
        read_procedures(TOGGLE.library_text().replace("(Bind (I thing))", "(Bind (w thing))"),
                        "generated-procedures.metta", domain, budget=budget())


# An entity binding is outside the model wherever it enters (a-jk-pc-outside-binding-1019). TOGGLE's domain
# with its entity described and g's proposition bound over the entity's control is one plan takes, and a
# request's model reading over it gives plan entity readings; an entity reading placing g on the entity may
# be handed to plan directly; and g placed on the entity, (On (Signal g) thing), may be achieved by a
# procedure or asked by a goal. The model reads each as the bare signal, so each is refused by name.
# am[verifies a-jk-pc-outside-binding-1019@59f29c] am[rests-on c-jk-ob-request-entity-needs-binding-1019@29f628]
def test_the_model_refuses_a_domain_binding_a_proposition_to_an_entity_though_plan_takes_it() -> None:
    text = TOGGLE.domain_text().replace("(gc-brs-entity thing Thing)", '(gc-brs-entity thing Thing "the one thing")')
    domain = read_domain(f'{text}\n(gc-reading-binding g Thing "Which thing does it hold of? " "No thing named.")',
                         "generated", budget=budget())
    assert [binding.entities for binding in domain.readings.bindings] == [(("thing", "the one thing"),)]
    library = read_procedures(TOGGLE.library_text(), "generated-procedures.metta", domain, budget=budget())
    answer = plan(TOGGLE.goal_literals(), domain=domain, library=library, readings=TOGGLE.signal_readings(),
                  journal=(), rows=(), receipts={}, at=AT, budget=budget())
    assert isinstance(answer, (Plan, Inquiry, NoPlan)), answer
    with pytest.raises(ValueError, match="the binding of g to an entity of Thing"):
        Oracle.of(library, domain, TOGGLE.goal)


# am[verifies a-jk-pc-outside-binding-1019@59f29c] am[related c-jk-ob-lit-crash-1019@889537]
def test_the_model_refuses_an_entity_reading_and_a_signal_placed_on_an_entity() -> None:
    domain, library = TOGGLE.read()
    detected = SignalReading("g", "detected", "test", "deterministic", observed_at=AT - timedelta(minutes=1))
    with pytest.raises(ValueError, match="the entity reading of g on thing"):
        start_state([EntityReading(detected, "thing", "jev:test")])
    on = QualifiedLiteral(SignalLiteral("g"), "thing")
    for literal in (on, NegatedLiteral(on)):
        with pytest.raises(ValueError, match=re.escape(f"the literal {literal}")):
            lit(literal)
    (procedure,) = library.procedures
    for achieving in (replace(procedure, achieves=(on,)), replace(procedure, when=(NegatedLiteral(on),))):
        with pytest.raises(ValueError, match="the literal (Negated|Qualified)Literal"):
            Oracle.of(replace(library, procedures=(achieving,)), domain, TOGGLE.goal)


# start_state reads exactly the readings plan is given: an unknown reading is silence, as no reading is, an
# unchecked one only offers its literal, and a second reading of one signal, which plan's justification
# resolves, is outside the model's one reading per signal (c-jk-ob-design-start-1019).
# am[verifies a-jk-pc-outside-binding-1019@59f29c] am[rests-on c-jk-ob-design-start-1019@78e9dd]
def test_start_state_reads_an_unknown_reading_as_none_and_refuses_a_second_reading() -> None:
    def reading(state: str, estimator: str | None = "deterministic") -> SignalReading:
        return SignalReading("g", state, "test", estimator, observed_at=AT - timedelta(minutes=1))

    assert start_state([reading("unknown", None)]) == (frozenset(), frozenset())
    assert start_state([reading("refuted")]) == (frozenset({("g", False)}), frozenset())
    assert start_state([reading("detected", "model-proposed")]) == (frozenset(), frozenset({("g", True)}))
    with pytest.raises(ValueError, match="a second reading of g"):
        start_state([reading("detected"), reading("refuted", "measured")])


# A track is outside the model as well: only a library declaring a promotion rule can hold one, from receipts
# the oracle never takes, while the model counts every application unestablished (c-jk-ob-track-unrefused-1019).
# am[verifies a-jk-ob-track-refusal-1019@8f148f]
def test_the_model_refuses_a_library_declaring_a_track_promotion_rule() -> None:
    domain, library = TOGGLE.read()
    promoted = read_procedures(f"{TOGGLE.library_text()}\n(gc-track-promotion (Trials 3) (Threshold 0.5))",
                               "generated-procedures.metta", domain, budget=budget())
    assert (promoted.procedures, promoted.promotion is not None) == (library.procedures, True)
    with pytest.raises(ValueError, match="the track promotion rule"):
        Oracle.of(promoted, domain, TOGGLE.goal)


# k's reaction turns not-s into s, p's Finish, which needs only k, writes g, and the goal is not-s. A checked
# reading refuting s, taken before k ran, is supplied after k's receipt in three ways. Kept, it is stale, yet
# every world with s false and k done rests holding it, so C1 admits the snapshot and plan, as the model
# does, takes the reading as current and plans on not-s: p's journal-only Finish. C1 checks that the supplied
# snapshot is consistent and detects no stale reading, so refreshing or omitting a reading an act may have
# superseded is the caller's precondition (c-integrate-c1-currentness-boundary-1019,
# c-jk-pc-stale-reaction-undetected-1019). Refreshed after the receipt the reading shows s, and omitted it
# leaves s unknown; either way no rule writes not-s, so there is no plan. Admission takes the stale reading as
# current too, admitting the stale plan's step.
# am[verifies a-jk-pc-currentness-boundary-1019@542623] am[rests-on c-jk-pc-stale-reaction-undetected-1019@5c82f9]
STALE_REACTION = World(
    signals=("s", "g"), actions=("flip",), entity="thing", control="Thing",
    procedures=(("p", (("g", True),), (), (("k", "act", "flip", ()),)),),
    investigators=(), readings=(("s", ("refuted", "deterministic")),), goal=(("s", False),),
    reactions=(("flip", ("s", False)),))


# am[verifies a-jk-pc-currentness-boundary-1019@542623]
@pytest.mark.parametrize(("supplied", "kind"), [("stale", Plan), ("refreshed", NoPlan), ("omitted", NoPlan)])
def test_a_reading_an_act_superseded_is_the_callers_to_refresh_or_omit(supplied: str, kind: type) -> None:
    domain, library = STALE_REACTION.read()
    oracle = Oracle.of(library, domain, STALE_REACTION.goal)
    run = Execution(dict(STALE_REACTION.readings))
    run.take(0, "p", "start", None, ())
    run.take(0, "p", "act", "k", (("s", True),) if supplied == "refreshed" else ())
    if supplied == "omitted":
        del run.readings["s"]
    observed, assumable = start_state(run.evidence())
    snapshot = State(observed, tuple(sorted((index, frozenset(done)) for index, done in run.done.items())))
    answer = planned(STALE_REACTION.goal_literals(), domain=domain, library=library, readings=run.evidence(),
                     journal=tuple(run.journal), rows=(), receipts={}, at=AT, budget=budget())
    assert isinstance(answer, kind), answer
    matches(oracle, answer, snapshot, assumable)
    holds_everywhere(oracle, answer, snapshot)
    if isinstance(answer, Plan):
        verdict = admit(answer.steps[0], instance_id=run.instances[0], domain=domain, library=library,
                        readings=run.evidence(), journal=tuple(run.journal), rows=(), at=AT, budget=budget())
        assert isinstance(verdict, Admitted), verdict

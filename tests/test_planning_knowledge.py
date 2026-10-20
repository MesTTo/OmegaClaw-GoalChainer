"""Purpose: verify planning/knowledge.metta's rules, on hand-built terms in the planning group's space and
through plan. gc-pk-faults names each load-time fault kind, and none for a rule that reads its evidential
entity through a site or replaces a polarity it read. gc-pk-sets-of compiles each Set entry to one rule per
prior polarity and several entries to their product, and a rule or variant that changes nothing to no rule.
gc-pk-build makes only checked knowledge structure, linked Via its names. Through plan, a procedure finishes
a literal from refuted and from unknown, a Derive fires once between the steps its reads follow, however
often it reads a literal, and never holds the priority class, a goal counts only once Finish and Derive have
settled, a Finish or Derive that may step in some completion leaves no plan resting on what it could undo,
an attempt in flight moves what its reaction writes and what any Derive that write enables writes, though the
snapshot left it unknown, an inquiry asks each literal once on a path even where the settle cancels its
answer, an entity or a control may take a name the planner's own terms are headed by, an unchecked When
literal is only an assumption NoPlan's explanatory alternative names, and a
domain reaction that closes an evidential entity, writes a signal it never read or reads a signal's
absence is refused, the signal spelled either way a section spells one, as is a reaction's node of a
literal no anchor declares. A plan never passes a state whose Finishes rest two ways, plan and admit refuse
readings no world settles to, a branch no world settles to answers its goal literals contradicted, a
journal instance every world finished takes its journal Finish, which writes nothing and commits to nothing,
one every world leaves open still finishes in the plan, and one some world finished is uncertain. A Derive
step is admitted when due and blocked naming the Achieve literal it reads that the evidence refutes.
Every planner entry Python evaluates is a typed wrapper over an untyped worker."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

import pytest

from goal_chainer.domains.loader import read_domain
from goal_chainer.planning import group, projection
from goal_chainer.planning.procedures import NegatedLiteral, ProcedureError, SignalLiteral, read_procedures
from goal_chainer.planning.projection import (
    Admitted,
    Blocked,
    Dispatched,
    Inquiry,
    NoPlan,
    Plan,
    PlanningRefused,
    Receipt,
    Started,
    Unsolved,
    admit,
    plan,
)
from goal_chainer.relevance.signals import SignalReading
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.evaluator import prepare
from policy_support import group_answers
from request_support import budget


# am[verifies a-ev-brs-compiled-sets-1018@1ec6e4] am[verifies a-ev-brs-evidential-frame-check-1018@046321]
def _term(inner: int, nodes: str, place: str) -> str:
    return f"(Bigraph (Inner {inner} ()) (Outer 1 ()) (Nodes {nodes}) (Place {place}) (Link))"


# am[verifies a-ev-brs-compiled-sets-1018@1ec6e4] am[verifies a-ev-brs-evidential-frame-check-1018@046321]
def _declared(redex: str, reactum: str, eta: str = "(Eta (0 0))", conditions: str = "(Conditions)",
              sets: str = "(Sets)") -> str:
    return f"(Declared r {redex} {reactum} {eta} {conditions} (Priority 0) {sets})"


# A task T holding (Signal "x") as evidence, its contents under site 0; a second task U with site 1.
OPEN = _term(1, "(N T Task)", "(In T (Root 0)) (In (Site 0) T)")
TWO = _term(2, "(N T Task) (N U Task)", "(In T (Root 0)) (In U (Root 0)) (In (Site 0) T) (In (Site 1) U)")
# OPEN with a Mark placed under T, so a rule from OPEN to it changes every state it matches.
MARKED = _term(1, "(N T Task) (N m Mark)", "(In T (Root 0)) (In m T) (In (Site 0) T)")
EVIDENTIAL = '((Evidential (Signal "x") Task))'
SET_X = '(Set T (Signal "x") True (Via))'
SET_Y = '(Set T (Signal "y") False (Via))'

# Each case's rule and the faults gc-pk-faults names for it, as plain values of the symbols S gives.
FAULTS = {
    "reads its entity through a site": (OPEN, OPEN, "(Eta (0 0))", "(Conditions)", lambda S: ()),
    "closes an evidential entity": (_term(0, "(N T Task)", "(In T (Root 0))"), _term(0, "(N T Task)", "(In T (Root 0))"),
                                    "(Eta)", "(Conditions)", lambda S: ((S.ClosedEvidentialNode, S.r, S.T),)),
    "moves each task's contents under the other": (
        TWO, _term(2, "(N T Task) (N U Task)", "(In T (Root 0)) (In U (Root 0)) (In (Site 0) U) (In (Site 1) T)"),
        "(Eta (0 0) (1 1))", "(Conditions)",
        lambda S: ((S.Frame, S.r, S.moved, S.T, S.U), (S.Frame, S.r, S.moved, S.U, S.T))),
    "merges both tasks' contents under a new node": (
        TWO, _term(2, "(N T Task) (N U Task) (N W Box)",
                   "(In T (Root 0)) (In U (Root 0)) (In W (Root 0)) (In (Site 0) W) (In (Site 1) W)"),
        "(Eta (0 0) (1 1))", "(Conditions)", lambda S: ((S.Frame, S.r, S.merged, S.W),)),
    "writes a polarity it never read": (
        OPEN, _term(1, '(N T Task) (N p (Signal "x"))', "(In T (Root 0)) (In p T) (In (Site 0) T)"),
        "(Eta (0 0))", "(Conditions)", lambda S: ((S.UnreadPolarity, S.r, S.T, (S.Signal, "x")),)),
    "replaces a polarity it read": (
        _term(1, '(N T Task) (N q (Not (Signal "x")))', "(In T (Root 0)) (In q T) (In (Site 0) T)"),
        _term(1, '(N T Task) (N p (Signal "x"))', "(In T (Root 0)) (In p T) (In (Site 0) T)"),
        "(Eta (0 0))", "(Conditions)", lambda S: ()),
    "reads evidence from structural absence": (
        OPEN, OPEN, "(Eta (0 0))", f'(Conditions (Absent (Parameter 0) {_term(0, "(N k (Signal \"x\"))", "(In k (Root 0))")}))',
        lambda S: ((S.StructuralAbsent, S.r, (S.Signal, "x")),)),
    "writes its own Unknown condition": (
        OPEN, OPEN, "(Eta (0 0))", '(Conditions (Unknown (Parameter 0) (Signal "x") (Via)))',
        lambda S: ((S.HandWrittenUnknown, S.r, (S.Signal, "x")),)),
}


# A rule loads only when it reads evidence through its subject or witness: a closed evidential redex
# node would read the absence of every unknown child, a parameter moved or merged under another
# evidential node could leave a witness beside a subject, a polarity placed under a matched node must
# replace one the redex read, and an Absent pattern or a hand-written Unknown would read evidence from
# missing structure. Each fault names its rule and what it refuses.
# am[verifies a-ev-brs-refuse-closed-evidential-redex-1018@39b0cd] am[verifies a-ev-brs-evidential-frame-check-1018@046321]
# am[verifies i-ev-brs-closed-evidential-redex-1018@6d09e6] am[verifies i-ev-brs-parameter-merge-1018@e41781]
# am[verifies i-ev-brs-blind-write-1018@a2a238] am[verifies i-jk-absence-not-evidence-1018@be354d]
@pytest.mark.parametrize("case", FAULTS)
def test_each_load_time_fault_names_its_rule_and_what_it_refuses(case: str) -> None:
    from metta import S

    redex, reactum, eta, conditions, expected = FAULTS[case]
    [faults] = group_answers(group.PLANNING, f"(gc-pk-faults {_declared(redex, reactum, eta, conditions)} {EVIDENTIAL})")
    assert faults == expected(S)


# A Set entry writes its literal whatever it held: one rule keeps a prior of the written polarity, one
# replaces the opposite, and one adds the literal where an Unknown condition finds neither, each new
# node placed under the entity; two entries compile to the product of their variants. The rule places a
# Mark as well, so each variant changes the state.
# am[verifies a-ev-brs-compiled-sets-1018@1ec6e4] am[rests-on c-ev-brs-tvla-three-valued-1018@a074bd]
def test_each_set_entry_compiles_to_one_rule_per_prior_polarity_and_several_to_their_product() -> None:
    from metta import S

    x, base = (S.Signal, "x"), {(S.N, S.T, S.Task), (S.N, S.m, S.Mark)}
    prior, post = (S.Prior, S.T, x), (S.Post, S.T, x)
    one = group_answers(group.PLANNING, f"(gc-pk-sets-of {_declared(OPEN, MARKED, sets=f'(Sets {SET_X})')})")

    def added(bigraph) -> tuple:
        return tuple(node for node in bigraph[3][1:] if node not in base)

    assert len(one) == 3
    assert {(added(rule[2]), added(rule[3]), rule[5][1:]) for rule in one} == {
        (((S.N, prior, x),), ((S.N, prior, x),), ()),
        (((S.N, prior, (S.Not, x)),), ((S.N, post, x),), ()),
        ((), ((S.N, post, x),), ((S.Unknown, (S.Parameter, 0), x, (S.Via,)),)),
    }
    for rule in one:
        for bigraph in (rule[2], rule[3]):
            assert all((S.In, node[1], S.T) in bigraph[4][1:] for node in added(bigraph))

    two = group_answers(group.PLANNING, f"(gc-pk-sets-of {_declared(OPEN, MARKED, sets=f'(Sets {SET_X} {SET_Y})')})")
    assert len(two) == len(set(two)) == 9


# A rule that rewrites every state it matches to itself would stay enabled forever, and in Finish and
# Derive's priority class pre-empt every ordinary step, so it is no rule. One whose reactum is its redex
# under the identity Eta compiles to none; with a Set entry it keeps the variants that replace or add the
# literal and drops the one keeping it, and with two entries the eight variants that change something.
# Equal terms under an Eta that swaps two parameters still change the state, so that rule stays.
# am[verifies a-ev-pk-noop-variants-dropped-1018@2d74fc] am[verifies i-ev-pk-derive-noop-blocks-1018@e0a1cf]
def test_a_rule_or_variant_that_changes_nothing_compiles_to_no_rule() -> None:
    assert not group_answers(group.PLANNING, f"(gc-pk-sets-of {_declared(OPEN, OPEN)})")
    one = group_answers(group.PLANNING, f"(gc-pk-sets-of {_declared(OPEN, OPEN, sets=f'(Sets {SET_X})')})")
    assert len(one) == 2 and all(rule[2] != rule[3] for rule in one)
    two = group_answers(group.PLANNING, f"(gc-pk-sets-of {_declared(OPEN, OPEN, sets=f'(Sets {SET_X} {SET_Y})')})")
    assert len(two) == len(set(two)) == 8
    assert len(group_answers(group.PLANNING, f"(gc-pk-sets-of {_declared(TWO, TWO, '(Eta (0 1) (1 0))')})")) == 1


# Only checked knowledge becomes structure: a checked answer builds its literal's subject or witness under
# its entity, linked to its Via names in order; an unchecked one is offered as an assumption only, and an
# unknown one builds nothing.
# am[verifies a-ev-pk-builder-1018@cfcf1f] am[verifies a-ev-brs-unchecked-assumable-1018@044f3c]
# am[verifies i-ev-brs-unchecked-as-structure-1018@c49fa0]
def test_only_checked_knowledge_becomes_structure_linked_via_its_names() -> None:
    from metta import S

    world = _term(0, "(N T Task)", "(In T (Root 0))")
    answers = ('((Answer (Lit (Signal "x") T (Via occupancy)) (Known True Checked)) '
               '(Answer (Lit (Signal "y") T (Via)) (Known False Checked)) '
               '(Answer (Lit (Signal "z") T (Via)) (Known True Unchecked)) '
               '(Answer (Lit (Signal "w") T (Via)) Unknown))')
    [(built, state, assumable)] = group_answers(group.PLANNING, f"(gc-pk-build {world} {answers})")
    x, y = (S.new, S.build, (S.Signal, "x"), S.T, 0), (S.new, S.build, (S.Signal, "y"), S.T, 0)
    assert built == S.Built
    assert state[3][1:] == ((S.N, S.T, S.Task), (S.N, x, (S.Signal, "x")), (S.N, y, (S.Not, (S.Signal, "y"))))
    assert state[4][1:] == ((S.In, S.T, (S.Root, 0)), (S.In, x, S.T), (S.In, y, S.T))
    assert state[5][1:] == ((S.P, x, 0, S.occupancy),)
    assert assumable == ((S.Assumable, (S.Lit, (S.Signal, "z"), S.T, (S.Via,)), True),)


AT = datetime(2026, 10, 18, 6, 0, tzinfo=timezone.utc)


# A section with one entity of one control anchoring the three signals the tests plan over.
# am[verifies a-ev-pk-python-api-1018@db9b94]
def _section(entity: str, control: str) -> str:
    return "\n".join([
        f"(gc-brs-control {control} (Ports) active)",
        f"(gc-brs-entity {entity} {control})",
        f"(gc-brs-in {entity} (Root 0))",
        *(f"(gc-brs-literal (Signal {signal}) (On {entity}))" for signal in ("coordination-needed", "sensitive-data", "unverified")),
    ])


# The packaged incident domain with a section and a one-act library its caller supplies, planning the
# goal coordination-needed, or `goal`, from the readings `states` give, those of `unchecked` read as
# model-proposed, and the executor's `journal`. `procedures` replaces the library's one procedure, and
# `entity` and `control` name the section's entity and its control, or `section` replaces the whole section.
# am[verifies a-ev-pk-python-api-1018@db9b94] am[verifies a-ev-brs-compiled-sets-1018@1ec6e4]
def _plan(states: dict[str, str], *, reaction: str = "", bind: str = "", when: str = "", unchecked: tuple[str, ...] = (),
          procedures: str = "", entity: str = "incident", control: str = "Incident", goal: str = "coordination-needed",
          journal: tuple = (), section: str = ""):
    domain, library, readings = _inputs(states, reaction=reaction, bind=bind, when=when, unchecked=unchecked,
                                        procedures=procedures, entity=entity, control=control, section=section)
    return plan((SignalLiteral(goal),), domain=domain, library=library, readings=readings,
                journal=journal, rows=(), receipts={}, at=AT, budget=budget())


# _plan's domain, library and readings, for a caller that admits a step as well.
# am[verifies a-ev-pk-python-api-1018@db9b94]
def _inputs(states: dict[str, str], *, reaction: str = "", bind: str = "", when: str = "", unchecked: tuple[str, ...] = (),
            procedures: str = "", entity: str = "incident", control: str = "Incident", section: str = ""):
    text = (resources.files("goal_chainer.domains") / "data" / "incident.metta").read_text(encoding="utf-8")
    domain = read_domain(f"{text}\n{section or _section(entity, control)}\n{reaction}", "incident", budget=budget())
    library = read_procedures(f"""
(gc-procedures incident-v1)
{procedures or f'''(gc-procedure hold-for-coordination
  (Achieves (Signal coordination-needed))
  (When {when})
  (Steps (Step hold act hold_external_update (After) {bind})))'''}
""", "knowledge-procedures.metta", domain, budget=budget())
    readings = [SignalReading(signal, state, "test", "model-proposed" if signal in unchecked else "deterministic",
                              observed_at=AT - timedelta(minutes=1))
                for signal, state in states.items()]
    return domain, library, readings


# A procedure's write sets its literal whatever the literal held: from refuted the compiled Finish
# replaces the witness, and from unknown, with no investigator to ask, it adds the subject.
# am[verifies a-ev-brs-compiled-sets-1018@1ec6e4] am[verifies i-ev-brs-blind-write-1018@a2a238]
@pytest.mark.parametrize("states", [{"coordination-needed": "refuted"}, {}], ids=["refuted", "unknown"])
def test_a_procedure_finishes_its_literal_from_refuted_and_from_unknown(states: dict[str, str]) -> None:
    answer = _plan(states)
    assert isinstance(answer, Plan)
    assert [(s.kind, s.procedure, s.step) for s in answer.steps] == [
        ("start", "hold-for-coordination", None), ("act", "hold-for-coordination", "hold"),
        ("finish", "hold-for-coordination", None)]


# A writer of not sensitive-data, and a user that needs it to reach coordination-needed.
WRITER = """(gc-procedure writer (Achieves (Not (Signal sensitive-data))) (When)
  (Steps (Step w act hold_external_update (After))))"""
USER = """(gc-procedure user (Achieves (Signal coordination-needed)) (When (Not (Signal sensitive-data)))
  (Steps (Step u act hold_external_update (After))))"""
# Each case's Derive and the procedure whose derive step the plan takes, None where it takes none.
DERIVES = {
    "none": ("", None),
    "sets-another-literal": ("""(gc-procedure noted (Achieves (Signal unverified)) (When)
  (Steps (Step d achieve (Not (Signal sensitive-data)) (After))))""", "noted"),
    "reads-it-by-when-and-achieve": ("""(gc-procedure twice (Achieves (Signal unverified)) (When (Not (Signal sensitive-data)))
  (Steps (Step d achieve (Not (Signal sensitive-data)) (After))))""", "twice"),
    "reads-it-by-two-achieves": ("""(gc-procedure twice (Achieves (Signal unverified)) (When)
  (Steps (Step d achieve (Not (Signal sensitive-data)) (After)) (Step e achieve (Not (Signal sensitive-data)) (After d))))""",
                                 "twice"),
    "sets-what-it-reads": ("""(gc-procedure echo (Achieves (Not (Signal sensitive-data))) (When)
  (Steps (Step e achieve (Not (Signal sensitive-data)) (After))))""", None),
}


# A Derive applies once its reads hold and never again: one reading not sensitive-data and setting
# unverified fires between the writer's Finish and the user's Start, which priority makes it precede, and
# one setting what it reads is no rule, wherever the library declares it. Its variant keeping unverified
# once set, or the whole Derive that sets what it reads, changes nothing, and kept as a rule it would hold
# the priority class and leave the goal blocked (c-jk-po-derive-blocks-after-b3c52ef-1018). A Derive
# reading the literal by its When and an achieve step, or by two achieve steps, reads it once, since one
# literal is one node (c-jk-po-derive-duplicate-read-b3c52ef-1018).
# am[verifies a-ev-pk-noop-variants-dropped-1018@2d74fc] am[verifies i-ev-pk-derive-noop-blocks-1018@e0a1cf]
# am[verifies a-ev-pk-reads-once-1018@d8bb52] am[verifies i-ev-pk-duplicate-read-1018@ce5030]
@pytest.mark.parametrize("first", [True, False], ids=["declared-first", "declared-last"])
@pytest.mark.parametrize("derive", DERIVES)
def test_a_derive_applies_once_between_the_steps_its_reads_follow(derive: str, first: bool) -> None:
    text, fires = DERIVES[derive]
    procedures = [text, WRITER, USER] if first else [WRITER, USER, text]
    answer = _plan({}, procedures="\n".join(procedures))
    assert isinstance(answer, Plan)
    between = [("derive", fires, None)] if fires else []
    assert [(s.kind, s.procedure, s.step) for s in answer.steps] == [
        ("start", "writer", None), ("act", "writer", "w"), ("finish", "writer", None), *between,
        ("start", "user", None), ("act", "user", "u"), ("finish", "user", None)]


# Admitting a Derive step reads what its rule reads, its When and its Achieve steps' literals. noted, setting
# unverified while sensitive-data is false, is due with sensitive-data refuted and unverified unread; with
# sensitive-data detected it is blocked naming its Achieve step's literal; with unverified read its write
# already holds, so it has no transition though everything it reads holds, and its block names nothing
# (i-ev-pc-admit-unnamed-block-1019).
# am[verifies a-ev-pc-admit-derive-reads-1019@450a34] am[verifies i-ev-pc-admit-unnamed-block-1019@cd9f50]
@pytest.mark.parametrize("states, verdict", [
    ({"sensitive-data": "refuted"}, Admitted),
    ({"sensitive-data": "detected"}, Blocked((NegatedLiteral(SignalLiteral("sensitive-data")),))),
    ({"sensitive-data": "refuted", "unverified": "detected"}, Blocked(())),
], ids=["due", "read-unmet", "write-holds"])
def test_a_derive_step_is_admitted_or_blocked_by_what_its_rule_reads(states: dict[str, str], verdict) -> None:
    procedures = "\n".join([DERIVES["sets-another-literal"][0], WRITER, USER])
    (derive,) = [step for step in _plan({}, procedures=procedures).steps if step.kind == "derive"]
    domain, library, readings = _inputs(states, procedures=procedures)
    answer = admit(derive, instance_id=None, domain=domain, library=library, readings=readings, journal=(),
                   rows=(), at=AT, budget=budget())
    assert (isinstance(answer, verdict) if isinstance(verdict, type) else answer == verdict), answer


HOLD = """(gc-procedure hold (Achieves (Signal coordination-needed)) (When)
  (Steps (Step h act hold_external_update (After))))"""
# A Derive setting not coordination-needed whenever sensitive-data holds.
LAW = """(gc-procedure law (Achieves (Not (Signal coordination-needed))) (When)
  (Steps (Step l achieve (Signal sensitive-data) (After))))"""


# Finish and Derive apply before any other rule, as the world applies a procedure's effects when its last
# step completes, so a goal counts only in a state where neither still steps. With sensitive-data
# detected the Derive undoes coordination-needed each time the procedure's Finish sets it, so the goal is
# blocked; with sensitive-data refuted the Derive never applies and the procedure plans.
# am[verifies a-ev-pk-goal-settled-1018@797476] am[verifies i-ev-pk-goal-before-settled-1018@408d3c]
def test_a_goal_counts_only_in_a_state_finish_and_derive_have_settled() -> None:
    undone = _plan({"sensitive-data": "detected"}, procedures=f"{HOLD}\n{LAW}")
    assert isinstance(undone, NoPlan) and undone.alternative is None
    assert undone.unsolved == (Unsolved(SignalLiteral("coordination-needed"), "blocked", ()),)
    kept = _plan({"sensitive-data": "refuted"}, procedures=f"{HOLD}\n{LAW}")
    assert isinstance(kept, Plan)
    assert [(s.kind, s.procedure) for s in kept.steps] == [("start", "hold"), ("act", "hold"), ("finish", "hold")]


# With sensitive-data unread the Derive steps in the completion where it holds, so no assumption-free plan
# rests on coordination-needed, which it would undo there: the goal is blocked, or, with an investigator
# for sensitive-data, inquired, planning in the branch where it is false. A literal the snapshot observed
# stays known: the Derive's read has not moved since, so where it holds the Derive had already applied
# and coordination-needed observed holds in every surviving world (a-jk-po-k0-changed-1018).
# am[verifies a-ev-pk-maybe-enabled-k0-1018@287f15] am[verifies i-ev-pk-maybe-enabled-priority-1018@4095c9]
def test_a_derive_that_may_step_leaves_no_plan_resting_on_what_it_could_undo() -> None:
    blocked = _plan({}, procedures=f"{HOLD}\n{LAW}")
    assert isinstance(blocked, NoPlan) and blocked.alternative is None
    assert blocked.unsolved == (Unsolved(SignalLiteral("coordination-needed"), "blocked", ()),)
    inquired = _plan({}, procedures=f"{HOLD}\n{LAW}\n(gc-investigator data-probe (Signal sensitive-data))")
    assert isinstance(inquired, Inquiry)
    assert (inquired.literal, inquired.investigator) == (SignalLiteral("sensitive-data"), "data-probe")
    assert isinstance(inquired.if_true, NoPlan) and isinstance(inquired.if_false, Plan)
    assert [(s.kind, s.procedure) for s in inquired.if_false.steps] == [("start", "hold"), ("act", "hold"), ("finish", "hold")]
    observed = _plan({"coordination-needed": "detected"}, procedures=f"{HOLD}\n{LAW}")
    assert isinstance(observed, Plan) and observed.steps == ()


# toggle's Finish reads not unverified and sets unverified; reset sets not unverified.
TOGGLE = """(gc-procedure toggle (Achieves (Signal unverified)) (When)
  (Steps (Step s1 act hold_external_update (After)) (Step g achieve (Not (Signal unverified)) (After s1))))"""
RESET = """(gc-procedure reset (Achieves (Not (Signal unverified))) (When)
  (Steps (Step t1 act hold_external_update (After))))"""


# An instance whose Finish may have fired in some completion never finishes later in the plan: with
# unverified unread, finishing toggle's s1 before reset would let toggle finish at once in the world where
# unverified is false, and reset then leave it false, so toggle's act waits until reset has made its
# Finish's read known (Cortez's c-jk-po-eager-finish-unsound-b3c52ef-1018, where b3c52ef interleaved s1 first).
# am[verifies a-ev-pk-maybe-enabled-k0-1018@287f15] am[verifies i-ev-pk-maybe-enabled-priority-1018@4095c9]
def test_an_instance_whose_finish_may_have_fired_never_finishes_later() -> None:
    answer = _plan({}, procedures=f"{TOGGLE}\n{RESET}", goal="unverified")
    assert isinstance(answer, Plan)
    assert [(s.kind, s.procedure, s.step) for s in answer.steps] == [
        ("start", "toggle", None), ("start", "reset", None), ("act", "reset", "t1"), ("finish", "reset", None),
        ("act", "toggle", "s1"), ("finish", "toggle", None)]


# hold_external_update's reaction writes sensitive-data over its witness; writer runs it, and user needs
# not sensitive-data to reach coordination-needed by another action.
WRITES_SENSITIVE = ("(gc-brs-reaction hold_external_update"
                    f" (Redex {_term(1, '(N I Incident) (N w (Not (Signal sensitive-data)))', '(In I (Root 0)) (In w I) (In (Site 0) I)')})"
                    f" (Reactum {_term(1, '(N I Incident) (N s (Signal sensitive-data))', '(In I (Root 0)) (In s I) (In (Site 0) I)')})"
                    " (Eta (0 0)) (Conditions))")


# writer runs hold_external_update on the incident and achieves `achieves`.
# am[verifies a-ev-pk-maybe-enabled-k0-1018@287f15] am[verifies a-integrate-k0-inquiry-termination-1018@e862f7]
# am[verifies a-ev-pk-moved-writes-join-1018@68c796]
def _writer(achieves: str) -> str:
    return f"""(gc-procedure writer (Achieves {achieves}) (When)
  (Steps (Step w act hold_external_update (After) (Bind (I incident)))))"""


INFLIGHT_LIBRARY = f"""{_writer("(Signal unverified)")}
(gc-procedure user (Achieves (Signal coordination-needed)) (When (Not (Signal sensitive-data)))
  (Steps (Step u act publish_redacted_summary (After))))"""

# writer's act w, dispatched two minutes before the plan under its witness digest, with no receipt yet.
WRITER_IN_FLIGHT = (Started("i1", "writer", "j1"), Dispatched("i1", "w", "a1", "sha256:w-witness", AT - timedelta(minutes=2)))


# An attempt still in flight may have applied its action's reaction in some world, so what the reaction
# writes is no longer known: with writer's act dispatched and unreceipted, not sensitive-data, though
# observed, may be false, and user cannot start; with nothing in flight user plans.
# am[verifies a-ev-pk-maybe-enabled-k0-1018@287f15] am[verifies i-ev-pk-maybe-enabled-priority-1018@4095c9]
def test_an_attempt_in_flight_leaves_unknown_what_its_reaction_writes() -> None:
    states = {"sensitive-data": "refuted"}
    free = _plan(states, reaction=WRITES_SENSITIVE, procedures=INFLIGHT_LIBRARY)
    assert isinstance(free, Plan)
    assert [(s.kind, s.procedure) for s in free.steps] == [("start", "user"), ("act", "user"), ("finish", "user")]
    journal = WRITER_IN_FLIGHT
    inflight = _plan(states, reaction=WRITES_SENSITIVE, procedures=INFLIGHT_LIBRARY, journal=journal)
    assert isinstance(inflight, NoPlan)
    assert inflight.unsolved == (Unsolved(SignalLiteral("coordination-needed"), "blocked", ()),)


# writer's Finish sets a literal no Derive here reads; direct's Derive sets not unverified whenever
# sensitive-data holds, and chain's reaches it through coordination-needed.
MOVED_WRITES = {
    "direct": f"""{_writer("(Signal coordination-needed)")}
(gc-procedure undo (Achieves (Not (Signal unverified))) (When)
  (Steps (Step d achieve (Signal sensitive-data) (After))))""",
    "chain": f"""{_writer("(Signal sensitive-data)")}
(gc-procedure link (Achieves (Signal coordination-needed)) (When)
  (Steps (Step c achieve (Signal sensitive-data) (After))))
(gc-procedure undo (Achieves (Not (Signal unverified))) (When)
  (Steps (Step d achieve (Signal coordination-needed) (After))))""",
}


# A literal the snapshot leaves unknown moves when an attempt in flight may set it: in the world where
# sensitive-data was false at the readings and writer's act lands after them, the Derive steps and the observed
# unverified fails, so no plan rests on it; through chain's Derive, coordination-needed, also unread, moves with
# sensitive-data. With nothing in flight neither has moved: where the Derive could step it already had, and
# the observed unverified holds in every surviving world (i-ev-pk-unknown-write-unmoved-1018).
# am[verifies a-ev-pk-moved-writes-join-1018@68c796] am[verifies i-ev-pk-unknown-write-unmoved-1018@b09997]
@pytest.mark.parametrize("procedures", MOVED_WRITES.values(), ids=MOVED_WRITES.keys())
def test_an_attempt_in_flight_moves_what_it_may_set_though_the_snapshot_left_it_unknown(procedures: str) -> None:
    states = {"unverified": "detected"}
    free = _plan(states, reaction=WRITES_SENSITIVE, procedures=procedures, goal="unverified")
    assert isinstance(free, Plan) and free.steps == ()
    journal = WRITER_IN_FLIGHT
    inflight = _plan(states, reaction=WRITES_SENSITIVE, procedures=procedures, goal="unverified", journal=journal)
    assert isinstance(inflight, NoPlan)
    assert inflight.unsolved == (Unsolved(SignalLiteral("unverified"), "no-way", ()),)


PROBE = "(gc-investigator data-probe (Signal sensitive-data))"
NEEDY = """(gc-procedure needy (Achieves (Signal coordination-needed)) (When (Signal sensitive-data))
  (Steps (Step n act publish_redacted_summary (After))))"""


# An inquiry asks a literal once on a path, though the settle can cancel its answer: with writer's act in
# flight setting sensitive-data, observing it false is forgotten, since the act may still land, so the False
# branch settles back to the state that asked, which asked again would inquire until the budget ran out. user,
# needing it false, still has no plan; needy, needing it true, plans in the True branch alone.
# am[verifies a-integrate-k0-inquiry-termination-1018@e862f7] am[verifies i-ev-pk-inquiry-repeats-cancelled-1018@f783c5]
def test_an_inquiry_asks_a_literal_once_though_the_settle_cancels_its_answer() -> None:
    states = {"sensitive-data": "refuted"}
    journal = WRITER_IN_FLIGHT
    blocked = _plan(states, reaction=WRITES_SENSITIVE, procedures=f"{INFLIGHT_LIBRARY}\n{PROBE}", journal=journal)
    assert isinstance(blocked, NoPlan)
    assert blocked.unsolved == (Unsolved(SignalLiteral("coordination-needed"), "blocked", ()),)
    inquired = _plan(states, reaction=WRITES_SENSITIVE, procedures=f"{_writer('(Signal unverified)')}\n{NEEDY}\n{PROBE}",
                     journal=journal)
    assert isinstance(inquired, Inquiry)
    assert (inquired.literal, inquired.investigator) == (SignalLiteral("sensitive-data"), "data-probe")
    assert isinstance(inquired.if_true, Plan)
    assert [(s.kind, s.procedure) for s in inquired.if_true.steps] == [("start", "needy"), ("act", "needy"), ("finish", "needy")]
    assert isinstance(inquired.if_false, NoPlan)


# p's Finish reads its act's Done and unverified, which an achieve step after the act asks for, and yi
# observes unverified.
FINISHING = """(gc-procedure p (Achieves (Signal coordination-needed)) (When)
  (Steps (Step p1 act hold_external_update (After)) (Step y achieve (Signal unverified) (After p1))))
(gc-investigator yi (Signal unverified))"""


# An investigator's answer is a reading. With p's act receipted and unverified unread, p may have finished in
# some completion, so the settle forgets its Done markers; read detected, unverified lets p finish at once.
# Answered true, the inquiry's branch is that reading, so p finishes there too, where observed on the settled
# state p stayed uncertain and the inquiry was dropped as useless (cortez-pereira's OBSERVATION_ENABLES_FINISH,
# c-jk-po-inquiry-branch-disagrees-replanning-a44aeba-1018).
# am[verifies a-ev-pk-inquiry-branch-as-reading-1018@9c2431] am[verifies c-jk-po-inquiry-branch-disagrees-replanning-a44aeba-1018@b8813e]
def test_an_investigators_answer_is_a_reading_so_it_can_let_an_instance_finish() -> None:
    journal = (Started("i1", "p", "j1"), Dispatched("i1", "p1", "a1", "sha256:p1-witness", AT - timedelta(minutes=2)),
               Receipt("r1", "i1", "p1", "a1", True))
    read = _plan({"unverified": "detected"}, procedures=FINISHING, journal=journal)
    assert isinstance(read, Plan) and [(s.kind, s.procedure, s.instance_id) for s in read.steps] == [("finish", "p", "i1")]
    inquired = _plan({}, procedures=FINISHING, journal=journal)
    assert isinstance(inquired, Inquiry)
    assert (inquired.literal, inquired.investigator) == (SignalLiteral("unverified"), "yi")
    assert isinstance(inquired.if_true, Plan)
    assert [(s.kind, s.procedure, s.instance_id) for s in inquired.if_true.steps] == [("finish", "p", "i1")]
    assert isinstance(inquired.if_false, NoPlan)


# --- the soundness contract: one rest per closure, admission, the journal's done instances ---------------

# first's act f1 turns not sensitive-data into sensitive-data by WRITES_SENSITIVE, setting not
# coordination-needed when it finishes; second's Finish waits for sensitive-data after its act b and sets
# coordination-needed.
FIRST = """(gc-procedure first (Achieves (Not (Signal coordination-needed))) (When)
  (Steps (Step f1 act hold_external_update (After) (Bind (I incident)))))"""
SECOND = """(gc-procedure second (Achieves (Signal coordination-needed)) (When)
  (Steps (Step b act publish_redacted_summary (After)) (Step c achieve (Signal sensitive-data) (After b))))"""


# A world, not the plan, orders Finishes enabled together, so no plan passes a state from which they rest two
# ways: with b done before f1, f1's reaction enables both Finishes, which write coordination-needed opposite ways,
# so the least plan of 410fc76a, second's start and b, then first's start, f1 and both Finishes, is refused there
# and the plan takes b only after first has finished (a-jk-pc-r1-closure-1019, c-jk-pf-cx-simultaneous-1019's shape).
# am[verifies a-ev-pc-r1-guard-1019@c59bcf] am[verifies a-jk-pc-r1-closure-1019@f9b888]
def test_a_plan_never_passes_a_state_whose_finishes_rest_two_ways() -> None:
    answer = _plan({"sensitive-data": "refuted"}, reaction=WRITES_SENSITIVE, procedures=f"{SECOND}\n{FIRST}")
    assert isinstance(answer, Plan)
    assert [(s.kind, s.procedure, s.step) for s in answer.steps] == [
        ("start", "second", None), ("start", "first", None), ("act", "first", "f1"), ("finish", "first", None),
        ("act", "second", "b"), ("finish", "second", None)]


# LAW sets not coordination-needed whenever sensitive-data holds, and CLEARED whenever it does not.
CLEARED = """(gc-procedure cleared (Achieves (Not (Signal coordination-needed))) (When)
  (Steps (Step l achieve (Not (Signal sensitive-data)) (After))))"""


# Readings observe the world at rest, so readings no world settles to are contradictory evidence and refused,
# by plan and by admit, naming what they say of the literals Derives touch: coordination-needed read beside
# sensitive-data, which LAW would undo, and coordination-needed read beside LAW and CLEARED, one of which
# undoes it whatever sensitive-data is, a contradiction no Derive the model enables shows
# (a-jk-pc-c1-admitted-1019, c-integrate-planner-empty-world-plan-1019's shape). Read refuted, coordination-needed
# admits a world.
# am[verifies a-ev-pc-c1-admission-1019@92a093] am[verifies a-jk-pc-c1-admitted-1019@321a3b]
@pytest.mark.parametrize("states, derives", [
    ({"sensitive-data": "detected", "coordination-needed": "detected"}, LAW),
    ({"coordination-needed": "detected"}, f"{LAW}\n{CLEARED}"),
], ids=["a-derive-overrules-it", "by-cases"])
def test_readings_no_world_settles_to_are_refused_by_plan_and_admit(states: dict[str, str], derives: str) -> None:
    procedures = f"{HOLD}\n{derives}"
    with pytest.raises(PlanningRefused, match=r"Contradicted .*\(Signal coordination-needed\) incident \(Via\)\) True"):
        _plan(states, procedures=procedures)
    start = _plan({}, procedures=HOLD).steps[0]
    domain, library, readings = _inputs(states, procedures=procedures)
    with pytest.raises(PlanningRefused, match="Contradicted"):
        admit(start, instance_id=None, domain=domain, library=library, readings=readings, journal=(), rows=(),
              at=AT, budget=budget())
    assert isinstance(_plan({**states, "coordination-needed": "refuted"}, procedures=procedures), (Plan, NoPlan, Inquiry))


# verify needs not sensitive-data, which data-probe can observe, to reach unverified.
VERIFY = """(gc-procedure verify (Achieves (Signal unverified)) (When (Not (Signal sensitive-data)))
  (Steps (Step v act publish_redacted_summary (After))))
(gc-investigator data-probe (Signal sensitive-data))"""


# An inquiry branch is the snapshot with the answer as a reading, so one no world settles to is an answer no
# investigator can give: with coordination-needed read and LAW declared, sensitive-data observed true admits no
# world and answers NoPlan with unverified contradicted, while observed false plans verify.
# am[verifies a-ev-pc-c1-admission-1019@92a093] am[verifies a-jk-pc-c1-admitted-1019@321a3b]
def test_an_inquiry_branch_no_world_settles_to_answers_its_goal_contradicted() -> None:
    answer = _plan({"coordination-needed": "detected"}, procedures=f"{LAW}\n{VERIFY}", goal="unverified")
    assert isinstance(answer, Inquiry)
    assert (answer.literal, answer.investigator) == (SignalLiteral("sensitive-data"), "data-probe")
    assert answer.if_true == NoPlan((Unsolved(SignalLiteral("unverified"), "contradicted", ()),), None)
    assert isinstance(answer.if_false, Plan)
    assert [(s.kind, s.procedure) for s in answer.if_false.steps] == [("start", "verify"), ("act", "verify"), ("finish", "verify")]


# HOLD's act h, dispatched two minutes before the plan and receipted.
HOLD_RECEIPTED = (Started("i1", "hold", "j1"), Dispatched("i1", "h", "a1", "sha256:h-witness", AT - timedelta(minutes=2)),
                  Receipt("r1", "i1", "h", "a1", True))


# Once h's receipt lands every world finishes hold before the readings, its Finish reading only h's Done, so with
# coordination-needed read the plan is hold's journal Finish alone, which writes nothing over the reading and
# commits to no record, so the plan stays established though no track holds; read refuted, coordination-needed is a
# reading taken before the act, which no world settles to (a-jk-pc-r3-exact-amend-1019, a-ev-pc-completion-u-1019).
# am[verifies a-ev-pc-r3-classify-1019@314db6] am[verifies a-ev-pc-r3-journal-finish-1019@ea2ea1] am[verifies a-ev-pc-completion-u-1019@9471f3]
def test_an_instance_every_world_finished_takes_a_journal_finish_that_commits_to_nothing() -> None:
    answer = _plan({"coordination-needed": "detected"}, procedures=HOLD, journal=HOLD_RECEIPTED)
    assert isinstance(answer, Plan) and answer.established is True
    assert [(s.kind, s.procedure, s.instance_id) for s in answer.steps] == [("finish", "hold", "i1")]
    domain, library, readings = _inputs({"coordination-needed": "detected"}, procedures=HOLD)
    assert isinstance(admit(answer.steps[0], instance_id="i1", domain=domain, library=library, readings=readings,
                            journal=HOLD_RECEIPTED, rows=(), at=AT, budget=budget()), Admitted)
    with pytest.raises(PlanningRefused, match="Contradicted"):
        _plan({"coordination-needed": "refuted"}, procedures=HOLD, journal=HOLD_RECEIPTED)


# p's act p1, dispatched two minutes before the plan and receipted; verify-u achieves unverified.
P_RECEIPTED = (Started("i1", "p", "j1"), Dispatched("i1", "p1", "a1", "sha256:p1-witness", AT - timedelta(minutes=2)),
               Receipt("r1", "i1", "p1", "a1", True))
VERIFY_U = """(gc-procedure verify-u (Achieves (Signal unverified)) (When)
  (Steps (Step v act publish_redacted_summary (After))))"""


# A done instance is classified by the worlds that settle to the readings (a-jk-pc-r3-exact-amend-1019): with
# unverified refuted, a world where it held when p1 landed would have finished p and kept it, so every world
# leaves p open, waiting, and the plan makes unverified true for p's Finish to apply, where R3's syntactic rule
# made p uncertain and found nothing (c-ev-pc-r3-syntactic-overcautious-1019).
# am[verifies a-jk-pc-r3-exact-amend-1019@9a3391] am[verifies c-ev-pc-r3-syntactic-overcautious-1019@d007da]
def test_a_done_instance_every_world_leaves_open_still_finishes_in_the_plan() -> None:
    answer = _plan({"unverified": "refuted"}, procedures=f"{FINISHING}\n{VERIFY_U}", journal=P_RECEIPTED)
    assert isinstance(answer, Plan)
    assert [(s.kind, s.procedure, s.step, s.instance_id) for s in answer.steps] == [
        ("start", "verify-u", None, None), ("act", "verify-u", "v", None), ("finish", "verify-u", None, None),
        ("finish", "p", None, "i1")]


# p2's Finish waits for unverified and turns it back off; noted sets unverified whenever sensitive-data holds.
RESETTING = """(gc-procedure p2 (Achieves (Signal coordination-needed) (Not (Signal unverified))) (When)
  (Steps (Step p1 act hold_external_update (After)) (Step y achieve (Signal unverified) (After p1))))
(gc-procedure noted (Achieves (Signal unverified)) (When)
  (Steps (Step d achieve (Signal sensitive-data) (After))))"""
P2_RECEIPTED = (Started("i1", "p2", "j1"), Dispatched("i1", "p1", "a1", "sha256:p1-witness", AT - timedelta(minutes=2)),
                Receipt("r1", "i1", "p1", "a1", True))


# With unverified refuted and sensitive-data unread, a world where sensitive-data holds lets noted set unverified,
# p2 finishes and turns it off again, resting as the reading says with p2 closed and coordination-needed set,
# while one where it does not leaves p2 open: p2 is uncertain, and no plan rests on coordination-needed, which
# only p2's Finish could set where it is open (c-jk-pf-cx-transient-finish-1019's shape).
# am[verifies a-jk-pc-r3-exact-amend-1019@9a3391]
def test_a_done_instance_some_world_finished_is_uncertain() -> None:
    answer = _plan({"unverified": "refuted"}, procedures=RESETTING, journal=P2_RECEIPTED)
    assert isinstance(answer, NoPlan)
    assert [unsolved.literal for unsolved in answer.unsolved] == [SignalLiteral("coordination-needed")]


# hold_external_update's reaction reading sensitive-data on the incident and rewriting it to its witness.
CLEARS_SENSITIVE = ("(gc-brs-reaction hold_external_update"
                    f" (Redex {_term(1, '(N I Incident) (N s (Signal sensitive-data))', '(In I (Root 0)) (In s I) (In (Site 0) I)')})"
                    f" (Reactum {_term(1, '(N I Incident) (N w (Not (Signal sensitive-data)))', '(In I (Root 0)) (In w I) (In (Site 0) I)')})"
                    " (Eta (0 0)) (Conditions))")
# The incident's one port links the occupancy edge and sensitive-data is anchored through it, so its node's port
# links occupancy too; VIA_CLEARS is CLEARS_SENSITIVE over that port, reaching the link by its outer name occ.
VIA_SECTION = "\n".join([
    "(gc-brs-control Incident (Ports occ) active)",
    "(gc-brs-entity incident Incident)",
    "(gc-brs-in incident (Root 0))",
    "(gc-brs-link incident occ (Edge occupancy))",
    "(gc-brs-literal (Signal coordination-needed) (On incident))",
    "(gc-brs-literal (Signal sensitive-data) (On incident) (Via occupancy))",
    "(gc-brs-literal (Signal unverified) (On incident))",
])
VIA_CLEARS = ("(gc-brs-reaction hold_external_update"
              " (Redex (Bigraph (Inner 1 ()) (Outer 1 (occ)) (Nodes (N I Incident) (N s (Signal sensitive-data)))"
              " (Place (In I (Root 0)) (In s I) (In (Site 0) I)) (Link (P I 0 (Name occ)) (P s 0 (Name occ)))))"
              " (Reactum (Bigraph (Inner 1 ()) (Outer 1 (occ)) (Nodes (N I Incident) (N w (Not (Signal sensitive-data))))"
              " (Place (In I (Root 0)) (In w I) (In (Site 0) I)) (Link (P I 0 (Name occ)) (P w 0 (Name occ)))))"
              " (Eta (0 0)) (Conditions))")


# clear's act, k, runs CLEARS_SENSITIVE, and clear reads sensitive-data or its absence by When, as `when` says.
# am[verifies a-ev-pk-act-reads-once-1018@514fd9]
def _clear(when: str) -> str:
    return f"""(gc-procedure clear (Achieves (Signal coordination-needed)) (When {when})
  (Steps (Step k act hold_external_update (After) (Bind (I incident)))))"""


# An act reads once what its procedure and its reaction both read: clear's When needs sensitive-data, which k's
# reaction reads and rewrites, so k matches the one node a state holds and clear finishes, where two nodes of one
# literal never matched (cortez-pereira's REACTION_READS_ITS_WHEN, c-jk-po-act-reads-when-twice-568231d-1018); so
# too when sensitive-data is anchored through a link the reaction reaches by its own name.
# am[verifies a-ev-pk-act-reads-once-1018@514fd9] am[verifies i-jk-po-act-reads-twice-1018@8b13c2]
@pytest.mark.parametrize("reaction, section", [(CLEARS_SENSITIVE, ""), (VIA_CLEARS, VIA_SECTION)], ids=["plain", "via"])
def test_an_act_reads_once_a_literal_its_reaction_also_reads(reaction: str, section: str) -> None:
    answer = _plan({"sensitive-data": "detected"}, reaction=reaction, procedures=_clear("(Signal sensitive-data)"),
                   section=section)
    assert isinstance(answer, Plan)
    assert [(s.kind, s.procedure) for s in answer.steps] == [("start", "clear"), ("act", "clear"), ("finish", "clear")]


# A read of the opposite polarity keeps its own node: clear's When needs sensitive-data absent while k's reaction
# needs it, so even once raise sets it, k never matches and nothing reaches coordination-needed, where reading the
# When through the reaction's node would let k run against its procedure's When.
# am[verifies a-ev-pk-act-reads-once-1018@514fd9]
def test_an_act_never_runs_when_its_when_contradicts_its_reactions_read() -> None:
    raise_ = """(gc-procedure raise (Achieves (Signal sensitive-data)) (When)
  (Steps (Step r act publish_redacted_summary (After))))"""
    answer = _plan({"sensitive-data": "refuted"}, reaction=CLEARS_SENSITIVE,
                   procedures=f"{_clear('(Not (Signal sensitive-data))')}\n{raise_}")
    assert isinstance(answer, NoPlan)


# The planner names its own nodes and controls where no plain name reaches: its agenda node is (Agenda)
# of control (Agenda), the executor's instances (Inst "ID") of control (Instance "P") hold (Done "S")
# markers, fresh nodes are (new ...), a rule's entity nodes (Ent ID), and every literal control its exact
# term, so an entity or a control may be named after any of their heads and plans as any other; the Finish
# binds the entity alone (c-jk-po-entity-name-collisions-b3c52ef-1018, c-jk-po-control-named-not-b3c52ef-1018).
# am[verifies i-ev-pk-entity-name-collisions-1018@b3416a] am[verifies a-ev-pk-projection-1018@e5d57e]
# am[verifies a-ev-pk-exact-controls-1018@0f428d] am[verifies i-ev-pk-control-name-collisions-1018@00f38e]
@pytest.mark.parametrize("entity, control", [
    *((name, "Incident") for name in ("agenda", "Agenda", "Inst", "new", "Ent")),
    *(("incident", name) for name in ("Agenda", "Instance", "Done", "Not", "Signal", "Statement")),
])
def test_a_domain_may_name_an_entity_or_a_control_after_the_planner_s_own_terms(entity: str, control: str) -> None:
    answer = _plan({}, entity=entity, control=control)
    assert isinstance(answer, Plan)
    assert [(s.kind, s.step) for s in answer.steps] == [("start", None), ("act", "hold"), ("finish", None)]
    assert answer.steps[-1].binding == ((f"(Ent {entity})", entity),)


# A literal the snapshot accepts but has not checked is an assumption the planner explains with, never acts
# on: with the When literal sensitive-data read as deterministic the procedure plans with no assumption,
# and read only as model-proposed the goal is blocked, the same plan offered as NoPlan's explanatory
# alternative naming sensitive-data as what it assumes.
# am[verifies a-ev-brs-unchecked-assumable-1018@044f3c] am[verifies i-ev-brs-unchecked-as-structure-1018@c49fa0]
def test_an_unchecked_when_literal_is_an_assumption_the_plan_names_and_never_acts_on() -> None:
    steps = [("start", "hold-for-coordination", None), ("act", "hold-for-coordination", "hold"),
             ("finish", "hold-for-coordination", None)]
    states = {"coordination-needed": "refuted", "sensitive-data": "detected"}
    checked = _plan(states, when="(Signal sensitive-data)")
    assert isinstance(checked, Plan) and checked.assumptions == ()
    assert [(s.kind, s.procedure, s.step) for s in checked.steps] == steps
    assumed = _plan(states, when="(Signal sensitive-data)", unchecked=("sensitive-data",))
    assert isinstance(assumed, NoPlan)
    assert assumed.unsolved == (Unsolved(SignalLiteral("coordination-needed"), "blocked", ()),)
    assert assumed.alternative.assumptions == (SignalLiteral("sensitive-data"),)
    assert [(s.kind, s.procedure, s.step) for s in assumed.alternative.steps] == steps


# A domain's reaction is merged into the act that runs its action, and the planner reads a literal in its
# terms written either as the library grammar writes it, (Signal sensitive-data), or in its own term
# spelling, (Signal "sensitive-data"), so both are the anchored literal. A reaction whose redex closes the
# incident, reading the absence of every unknown child, whose reactum writes the signal its redex never
# read, or whose condition reads the signal's absence, is refused for the rule it makes.
# am[verifies a-ev-brs-refuse-closed-evidential-redex-1018@39b0cd] am[verifies i-ev-brs-closed-evidential-redex-1018@6d09e6]
# am[verifies a-ev-pk-reaction-literals-read-1018@23bd20] am[verifies i-ev-pk-reaction-literal-spelling-1018@7cbbbf]
# am[verifies i-ev-brs-blind-write-1018@a2a238] am[verifies i-jk-absence-not-evidence-1018@be354d]
@pytest.mark.parametrize("redex, reactum, conditions, fault", [
    (_term(0, "(N I Incident)", "(In I (Root 0))"), _term(0, "(N I Incident)", "(In I (Root 0))"), "(Conditions)",
     "ClosedEvidentialNode"),
    (_term(1, "(N I Incident)", "(In I (Root 0)) (In (Site 0) I)"),
     _term(1, "(N I Incident) (N s (Signal sensitive-data))", "(In I (Root 0)) (In s I) (In (Site 0) I)"), "(Conditions)",
     "UnreadPolarity"),
    (_term(1, "(N I Incident)", "(In I (Root 0)) (In (Site 0) I)"),
     _term(1, '(N I Incident) (N s (Signal "sensitive-data"))', "(In I (Root 0)) (In s I) (In (Site 0) I)"), "(Conditions)",
     "UnreadPolarity"),
    (_term(1, "(N I Incident)", "(In I (Root 0)) (In (Site 0) I)"), _term(1, "(N I Incident)", "(In I (Root 0)) (In (Site 0) I)"),
     f'(Conditions (Absent (Parameter 0) {_term(0, "(N k (Signal sensitive-data))", "(In k (Root 0))")}))', "StructuralAbsent"),
], ids=["closed", "blind-write", "blind-write-term-spelling", "absence"])
def test_a_domain_reaction_reading_evidence_by_absence_or_writing_blind_is_refused(redex: str, reactum: str, conditions: str,
                                                                                    fault: str) -> None:
    eta = "(Eta (0 0))" if "Site" in redex else "(Eta)"
    reaction = f"(gc-brs-reaction hold_external_update (Redex {redex}) (Reactum {reactum}) {eta} {conditions})"
    with pytest.raises(PlanningRefused, match=fault):
        _plan({"coordination-needed": "refuted"}, reaction=reaction, bind="(Bind (I incident))")


# The planner reads knowledge only through anchors, so a reaction's node of a literal no gc-brs-literal
# anchors, a declared signal or one the domain never declares, is refused when the library is read
# against the domain, naming the reaction and the literal.
# am[verifies a-ev-pk-reaction-literals-anchored-1018@d38431] am[verifies i-ev-brs-reaction-literal-unanchored-1018@2da49c]
@pytest.mark.parametrize("control", ["(Signal public-data)", "(Not (Signal ghost))"])
def test_a_reaction_node_of_a_literal_no_anchor_declares_is_refused(control: str) -> None:
    redex = _term(1, "(N I Incident)", "(In I (Root 0)) (In (Site 0) I)")
    reactum = _term(1, f"(N I Incident) (N s {control})", "(In I (Root 0)) (In s I) (In (Site 0) I)")
    reaction = f"(gc-brs-reaction hold_external_update (Redex {redex}) (Reactum {reactum}) (Eta (0 0)) (Conditions))"
    with pytest.raises(ProcedureError, match=r"reaction of hold_external_update has a node of .* no gc-brs-literal anchors"):
        _plan({"coordination-needed": "refuted"}, reaction=reaction, bind="(Bind (I incident))")


# An Atom-typed parameter hands its argument over unevaluated, so an internal caller's computed argument
# would arrive as an expression (c-ev-pk-typed-entry-wrapper-1018): the planner types exactly the entries
# Python evaluates and its warm-up, and each entry's body calls a function the space declares no type for.
# am[verifies a-ev-pk-rb-group-1018@ba3846] am[rests-on c-ev-pk-typed-entry-wrapper-1018@ef5a23]
def test_every_planner_entry_python_evaluates_is_a_typed_wrapper_over_an_untyped_worker() -> None:
    sources = "".join(path.read_text(encoding="utf-8") for path in sorted(Path(projection.__file__).parent.glob("*.py")))
    evaluated = {name for name in re.findall(r'evaluate\(PLANNING, "([a-z-]+)"', sources)
                 if name.startswith(("gc-pk-", "gc-procedure"))}
    assert {"gc-pk-run-plan", "gc-pk-run-admit", "gc-procedures-run-check"} <= evaluated
    prepare(group.PLANNING, budget=budget())
    with metta_engine(None) as engine:
        atoms = list(engine.space(group.PLANNING.space).atoms())
    typed = {str(atom.children[1]) for atom in atoms if str(atom.children[0]) == ":"}
    planner = {name for name in typed if name.startswith(("gc-pk-", "gc-procedure"))}
    assert planner == evaluated | {"gc-pk-warm-up"}
    equations = [atom for atom in atoms if str(atom.children[0]) == "=" and getattr(atom.children[1], "children", None)]
    for name in evaluated:
        [body] = [atom.children[2] for atom in equations if str(atom.children[1].children[0]) == name]
        # (let VARIABLE VALUE BODY) calls its worker in VALUE.
        called = body.children[2].children[0] if str(body.children[0]) == "let" else body.children[0]
        assert str(called) not in typed, (name, str(called))

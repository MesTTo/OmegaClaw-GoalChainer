"""Purpose: verify goal_chainer.planning.projection's plan and admit on the task-control library over a
synthetic bigraph section. The pause route runs reach-safe-point before release-by-pause pauses, every
step witnessed, and tracks its receipts make hold class it established. Admission follows the journal through start,
dispatch, failed, superseded and applied receipts, refusing a reading taken before the act that the finished
procedure's effect contradicts; a When literal contradicted after Start blocks the
act naming it; an edit to the library or the section makes a planned step Stale. An unknown literal an
investigator covers is inquired, and an unreachable goal is NoPlan with its reason. The parent's prefix
cases are classed unestablished until receipts make the procedure's track hold, and an instance the journal started
is charged at its first step. Refusals name their problems, and no planner function is memoized, calls
an undefined function or binds a pattern variable twice in one scope."""

from __future__ import annotations

import dataclasses
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from goal_chainer.domains.bigraph import read_section
from goal_chainer.domains.forms import parsed_forms
from goal_chainer.domains.loader import packaged_domain, read_domain
from goal_chainer.errors import InvalidInputError
from goal_chainer.planning import group
from goal_chainer.planning.procedures import (
    AchieveStep,
    NegatedLiteral,
    Procedure,
    ProcedureError,
    ProcedureLibrary,
    SignalLiteral,
    StatementLiteral,
    literal_text,
    literal_term,
    packaged_procedures,
    read_procedures,
)
from goal_chainer.planning.projection import (
    Admitted,
    Blocked,
    Dispatched,
    Inquiry,
    NoPlan,
    Plan,
    PlanningRefused,
    Progress,
    Receipt,
    Stale,
    Started,
    Superseded,
    Unsolved,
    admit,
    plan,
)
from goal_chainer.relevance.instants import microseconds
from goal_chainer.relevance.signals import SignalReading
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.evaluator import plain_value, prepare
from metta_scope_lint import rebound_variables
from planning_support import (
    HANDOFF_REACTION,
    PROMOTION,
    RESTORES,
    parsed,
    promoting_task_library,
    receipted_history,
    task_domain,
    task_section_text,
)
from policy_support import group_answers
from request_support import budget

DOMAIN = task_domain()
AT = datetime(2026, 10, 18, 6, 0, tzinfo=timezone.utc)
RELEASED = NegatedLiteral(SignalLiteral("resource_contention"))
PAUSE_ROUTE = {"resource_contention": "detected", "state_preservation_route": "detected",
               "safe_point_reachable": "refuted", "owner_mismatch": "refuted", "receiving_owner_accepts": "refuted"}


# am[verifies a-ev-pk-python-api-1018@db9b94]
@pytest.fixture(scope="module")
def library() -> ProcedureLibrary:
    return packaged_procedures(DOMAIN, budget=budget())


# am[verifies a-ev-pk-python-api-1018@db9b94]
def _readings(states: dict[str, str]) -> list[SignalReading]:
    return [SignalReading(signal, state, "test", "deterministic", observed_at=AT - timedelta(minutes=1))
            for signal, state in states.items()]


# The restore drill's observation that the checkpoint store restores task state, a statement row whose
# observation is the drill's own kind, never a reading's.
# am[verifies a-ev-pk-python-api-1018@db9b94]
def _restores(library: ProcedureLibrary) -> list:
    from metta import S, Symbol

    statement = library.procedures[0].when[2]
    assert isinstance(statement, StatementLiteral)
    return [S.From(literal_term(statement), S.Observation(S.Drill("drill", "deterministic", Symbol("Forever"))))]


# am[verifies a-ev-pk-python-api-1018@db9b94]
def _plan(library, goal=(RELEASED,), states=PAUSE_ROUTE, journal=(), receipts=None, domain=DOMAIN):
    return plan(goal, domain=domain, library=library, readings=_readings(states), journal=journal,
                rows=_restores(library), receipts={} if receipts is None else receipts, at=AT, budget=budget())


# am[verifies a-ev-pk-python-api-1018@db9b94]
def _admit(step, instance_id, library, journal=(), states=PAUSE_ROUTE, domain=DOMAIN):
    return admit(step, instance_id=instance_id, domain=domain, library=library, readings=_readings(states),
                 journal=journal, rows=_restores(library), at=AT, budget=budget())


# am[verifies a-ev-pk-python-api-1018@db9b94] am[verifies a-ev-pk-projection-1018@e5d57e]
def test_the_pause_route_reaches_a_safe_point_before_it_pauses(library) -> None:
    answer = _plan(library)

    assert isinstance(answer, Plan)
    assert [(s.application, s.kind, s.procedure, s.step) for s in answer.steps] == [
        (0, "start", "release-by-pause", None),
        (1, "start", "reach-safe-point", None),
        (1, "act", "reach-safe-point", "run"),
        (1, "finish", "reach-safe-point", None),
        (0, "act", "release-by-pause", "pause"),
        (0, "finish", "release-by-pause", None),
    ]
    assert answer.established is False and answer.assumptions == ()
    pause = answer.steps[4]
    assert dict(pause.binding) == {"(Ent task)": "task", "(Ent checkpoint)": "checkpoint"}
    assert pause.witness.rule == '(Step 0 "release-by-pause" "pause")'
    assert ("(Agenda)", "(Agenda)") in pause.witness.images
    assert all(step.instance_id is None for step in answer.steps)
    assert len({step.witness.digest for step in answer.steps}) == len(answer.steps)


# Three confirmed attempts of each procedure on the pause route, receipted under the library's promotion, make
# both records hold and the plan established; with reach-safe-point's documents withheld its record is
# incomplete, holds nothing, and the plan is unestablished.
# am[verifies a-ev-pk-commitment-cost-1018@c9673e] am[verifies a-ev-fb-promotion-1018@2ae86c]
def test_tracks_receipts_make_hold_for_every_achieves_literal_class_the_plan_established() -> None:
    library = promoting_task_library()
    start = AT - timedelta(hours=2)
    pauses, paused = receipted_history("release-by-pause", "pause", "pause_recoverably", literal_text(RELEASED),
                                       ["confirmed"] * 3, start=start, tag="pause")
    runs, ran = receipted_history("reach-safe-point", "run", "continue_task",
                                  literal_text(SignalLiteral("safe_point_reachable")), ["confirmed"] * 3,
                                  start=start + timedelta(minutes=5), tag="run")
    answer = _plan(library, journal=(*pauses, *runs), receipts=parsed(paused | ran))
    assert isinstance(answer, Plan) and answer.established is True
    half = _plan(library, journal=(*pauses, *runs), receipts=parsed(paused))
    assert isinstance(half, Plan) and half.established is False


# Once run's receipt lands, every world finished reach-safe-point before the readings, since its Finish reads
# only run's Done, and wrote safe_point_reachable: a reading taken before the act that still refutes it admits
# no world and is refused, naming it, while a reading taken after the receipt admits the Finish, the journal
# Finish of a completed instance (a-ev-pc-c1-strict-1019, a-jk-pc-r3-exact-amend-1019).
# am[verifies a-ev-pk-python-api-1018@db9b94] am[verifies c-ev-pk-typed-rows-1018@15e680]
# am[verifies a-ev-pc-c1-strict-1019@2a8668] am[verifies a-ev-pc-r3-journal-finish-1019@ea2ea1]
def test_admission_follows_the_journal_through_start_dispatch_and_receipts(library) -> None:
    start, run, finish = _plan(library).steps[1:4]
    assert isinstance(_admit(start, None, library), Admitted)

    journal = [Started("i1", "reach-safe-point", "j1")]
    assert isinstance(_admit(run, "i1", library, journal), Admitted)
    assert _admit(finish, "i1", library, journal) == Blocked((Progress("i1", "run", True),))

    journal.append(Dispatched("i1", "run", "a1", "sha256:run-witness", AT - timedelta(minutes=2)))
    assert _admit(run, "i1", library, journal) == Blocked((Progress("i1", "run", False),))
    assert _admit(finish, "i1", library, journal) == Blocked((Progress("i1", "run", True),))

    failed = [*journal, Receipt("r0", "i1", "run", "a1", False)]
    assert isinstance(_admit(run, "i1", library, failed), Admitted)
    assert _admit(finish, "i1", library, failed) == Blocked((Progress("i1", "run", True),))

    superseded = [*failed, Receipt("r1", "i1", "run", "a1", True), Superseded("r0", "r1")]
    with pytest.raises(PlanningRefused, match=r"Contradicted .*\(Signal safe_point_reachable\) task \(Via\)\) False"):
        _admit(finish, "i1", library, superseded)
    observed = {**PAUSE_ROUTE, "safe_point_reachable": "detected"}
    assert isinstance(_admit(finish, "i1", library, superseded, observed), Admitted)
    assert _admit(run, "i1", library, superseded, observed) == Blocked((Progress("i1", "run", False),))


# When holds over the whole application, so an act after its When literal stops holding is no act.
# am[verifies a-ev-pk-projection-1018@e5d57e] am[verifies c-ev-pk-when-invariant-1018@0182c1]
def test_a_when_literal_contradicted_after_start_blocks_the_act_naming_it(library) -> None:
    run = _plan(library).steps[2]
    journal = [Started("i1", "reach-safe-point", "j1")]
    contradicted = {**PAUSE_ROUTE, "state_preservation_route": "refuted"}
    assert _admit(run, "i1", library, journal, contradicted) == Blocked((SignalLiteral("state_preservation_route"),))


# am[verifies a-ev-pk-python-api-1018@db9b94]
def test_an_edit_to_the_library_or_the_section_makes_a_planned_step_stale(library) -> None:
    run = _plan(library).steps[2]
    journal = [Started("i1", "reach-safe-point", "j1")]

    text = (resources.files("goal_chainer.planning") / "library" / "task_control.metta").read_text(encoding="utf-8")
    original = "(When (Signal state_preservation_route))\n  (Steps (Step run act continue_task (After))))"
    assert text.count(original) == 1
    edited = read_procedures(text.replace(original, original.replace("route))", "route) (Not (Signal review_open)))")),
                             "edited.metta", DOMAIN, budget=budget())
    verdict = _admit(run, "i1", edited, journal, {**PAUSE_ROUTE, "review_open": "refuted"})
    assert isinstance(verdict, Stale) and verdict.expected == run.witness.digest != verdict.found

    # A renamed occupancy edge changes the world every compiled rule links the task into, while the
    # handoff reaction, which links through its outer name, stays the same.
    section = task_section_text(DOMAIN.signal_ids).replace("(Edge occupancy)", "(Edge holding)")
    assert section != task_section_text(DOMAIN.signal_ids)
    moved = dataclasses.replace(DOMAIN, bigraph=read_section(parsed_forms(section, budget=None), "moved.metta"))
    assert isinstance(_admit(run, "i1", library, journal, domain=moved), Stale)


# am[verifies a-ev-pk-search-1018@f96ce8]
def test_an_unknown_literal_an_investigator_covers_is_inquired(library) -> None:
    states = {**PAUSE_ROUTE, "state_preservation_route": "refuted"}
    del states["owner_mismatch"]
    answer = _plan(library, states=states)

    assert isinstance(answer, Inquiry)
    assert (answer.literal, answer.investigator) == (SignalLiteral("owner_mismatch"), "owner-registry")
    assert isinstance(answer.if_true, Plan)
    assert [f"{s.procedure}.{s.step}" for s in answer.if_true.steps if s.kind == "act"] == [
        "ask-receiving-owner.ask", "release-by-handoff.hand"]
    assert answer.if_false == NoPlan((Unsolved(RELEASED, "blocked"),), None)


# am[verifies a-ev-pk-search-1018@f96ce8]
def test_an_unreachable_goal_is_noplan_with_its_reason(library) -> None:
    kept = {**PAUSE_ROUTE, "owner_mismatch": "detected"}
    no_way = _plan(library, goal=(NegatedLiteral(SignalLiteral("owner_mismatch")),), states=kept)
    assert no_way == NoPlan((Unsolved(NegatedLiteral(SignalLiteral("owner_mismatch")), "no-way"),), None)

    derive = ("(gc-procedures task-control-v1)\n"
              "(gc-procedure open-review (Achieves (Signal review_open)) (When (Signal stale_parent_goal))"
              " (Steps (Step parent achieve (Signal active_parent_path) (After))))")
    deriving = read_procedures(derive, "derive.metta", DOMAIN, budget=budget())
    states = {"review_open": "refuted", "active_parent_path": "detected"}
    unknowable = plan((SignalLiteral("review_open"),), domain=DOMAIN, library=deriving, readings=_readings(states),
                      journal=(), rows=(), receipts={}, at=AT, budget=budget())
    assert unknowable == NoPlan(
        (Unsolved(SignalLiteral("review_open"), "unknowable", (SignalLiteral("stale_parent_goal"),)),), None)


PREFIX_SECTION = """
(gc-brs-control Thing (Ports) active)
(gc-brs-entity thing Thing)
(gc-brs-in thing (Root 0))
(gc-brs-literal (Signal review_open) (On thing))
(gc-brs-reaction escalate
  (Redex (Bigraph (Inner 1 ()) (Outer 1 ()) (Nodes (N T Thing) (N W (Not (Signal "review_open"))))
                  (Place (In T (Root 0)) (In W T) (In (Site 0) T)) (Link)))
  (Reactum (Bigraph (Inner 1 ()) (Outer 1 ()) (Nodes (N T Thing) (N G (Signal "review_open")))
                    (Place (In T (Root 0)) (In G T) (In (Site 0) T)) (Link)))
  (Eta (0 0)) (Conditions))
"""
PREFIX_LIBRARY = """(gc-procedures task-control-v1)
(gc-procedure first (Achieves (Signal review_open)) (When)
  (Steps (Step a1 act escalate (After) (Bind (T thing))) (Step a2 act defer (After a1))))
(gc-procedure last (Achieves (Signal review_open)) (When)
  (Steps (Step a1 act defer (After)) (Step a2 act escalate (After a1) (Bind (T thing)))))
"""


# The parent's query c-integrate-plan-prefix-underpriced-1018: an act's merged reaction can reach the
# goal before its procedure's Finish, and the plan still rests on the unestablished procedure.
# am[verifies a-ev-pk-commitment-cost-1018@c9673e] am[verifies i-ev-pk-prefix-underpriced-1018@7fdbf7]
def test_a_plan_reaching_the_goal_before_finish_is_classed_by_its_procedure() -> None:
    domain = dataclasses.replace(DOMAIN, bigraph=read_section(parsed_forms(PREFIX_SECTION, budget=None), "prefix.metta"))
    both = read_procedures(f"{PREFIX_LIBRARY}\n{PROMOTION}", "prefix.metta", domain, budget=budget())
    states = {"review_open": "refuted"}
    goal = (SignalLiteral("review_open"),)
    for name, executed, action in (("first", ["a1"], "escalate"), ("last", ["a1", "a2"], "defer")):
        alone = dataclasses.replace(both, procedures=tuple(p for p in both.procedures if p.name == name))
        answer = plan(goal, domain=domain, library=alone, readings=_readings(states), journal=(), rows=(),
                      receipts={}, at=AT, budget=budget())
        assert isinstance(answer, Plan) and answer.established is False, name
        assert [s.step for s in answer.steps if s.kind == "act"] == executed, name
        history, documents = receipted_history(name, "a1", action, literal_text(goal[0]), ["confirmed"] * 3,
                                               start=AT - timedelta(hours=1), tag=name)
        held = plan(goal, domain=domain, library=alone, readings=_readings(states), journal=tuple(history), rows=(),
                    receipts=parsed(documents), at=AT, budget=budget())
        assert isinstance(held, Plan) and held.established is True, name

    started = plan(goal, domain=domain, library=both, readings=_readings(states), journal=(Started("i7", "first", "j7"),),
                   rows=(), receipts={}, at=AT, budget=budget())
    assert isinstance(started, Plan) and started.established is False
    assert [(s.kind, s.step, s.instance_id, s.application) for s in started.steps] == [("act", "a1", "i7", 0)]


# am[verifies a-ev-pk-python-api-1018@db9b94] am[verifies a-ev-pk-acceptance-anchors-1018@cb1e61]
def test_the_planner_refuses_what_its_input_does_not_declare(library) -> None:
    with pytest.raises(PlanningRefused, match="UnknownProcedure"):
        _plan(library, journal=(Started("i9", "nonexistent", "j9"),))

    section = task_section_text(DOMAIN.signal_ids) + "\n(gc-brs-link task serves (Edge elsewhere))"
    loose = dataclasses.replace(DOMAIN, bigraph=read_section(parsed_forms(section, budget=None), "loose.metta"))
    with pytest.raises(PlanningRefused, match="UndeclaredPort"):
        _plan(library, domain=loose)

    doubled = task_section_text(DOMAIN.signal_ids) + "\n(gc-brs-literal (Signal owner_mismatch) (On seat))"
    twice = dataclasses.replace(DOMAIN, bigraph=read_section(parsed_forms(doubled, budget=None), "twice.metta"))
    with pytest.raises(PlanningRefused, match=r"DuplicateAnchor \(Signal owner_mismatch\)"):
        _plan(library, domain=twice)

    unanchored = Procedure("lone", (SignalLiteral("sunk_cost_argument"),), (),
                           (AchieveStep("x", SignalLiteral("review_open"), ()),))
    built = dataclasses.replace(library, procedures=(*library.procedures, unanchored))
    with pytest.raises(PlanningRefused, match=r"unanchored-literal \(lone \(Signal sunk_cost_argument\)\)"):
        _plan(built)


HANDOFF_SECTION = f"""
(gc-brs-control Task (Ports occupies) active)
(gc-brs-control Seat (Ports) active)
(gc-brs-entity owner-seat Seat) (gc-brs-entity receiving-seat Seat) (gc-brs-entity task Task)
(gc-brs-in owner-seat (Root 0)) (gc-brs-in receiving-seat (Root 0)) (gc-brs-in task owner-seat)
(gc-brs-link task occupies (Edge occupancy))
(gc-brs-literal (Signal resource_contention) (On task) (Via occupancy))
(gc-brs-literal (Signal owner_mismatch) (On task))
(gc-brs-literal (Signal receiving_owner_accepts) (On task))
{HANDOFF_REACTION}
"""
HANDOFF_LIBRARY = """(gc-procedures task-control-v1)
(gc-procedure release-by-handoff
  (Achieves (Not (Signal resource_contention)))
  (When (Signal resource_contention) (Signal owner_mismatch))
  (Steps (Step accept achieve (Signal receiving_owner_accepts) (After))
         (Step hand act handoff (After accept) (Bind (T task) (A owner-seat) (B receiving-seat)))))
"""


# The act merges the domain's handoff reaction, whose task node links its occupies port, with the
# step's reads of the task's literals, one of them anchored Via that same occupancy link.
# am[verifies a-ev-pk-compile-1018@4d30e0] am[verifies a-ev-pk-python-api-1018@db9b94]
def test_a_merged_handoff_moves_the_linked_task_and_reads_contention_via_occupancy() -> None:
    domain = dataclasses.replace(DOMAIN, bigraph=read_section(parsed_forms(HANDOFF_SECTION, budget=None), "handoff.metta"))
    library = read_procedures(HANDOFF_LIBRARY, "handoff.metta", domain, budget=budget())
    states = {"resource_contention": "detected", "owner_mismatch": "detected", "receiving_owner_accepts": "detected"}
    answer = plan((RELEASED,), domain=domain, library=library, readings=_readings(states), journal=(), rows=(),
                  receipts={}, at=AT, budget=budget())

    assert isinstance(answer, Plan)
    assert [(s.kind, s.step) for s in answer.steps] == [("start", None), ("act", "hand"), ("finish", None)]
    hand = answer.steps[1]
    assert dict(hand.binding) == {"(Acted T)": "task", "(Acted A)": "owner-seat", "(Acted B)": "receiving-seat"}
    verdict = admit(hand, instance_id="i1", domain=domain, library=library, readings=_readings(states),
                    journal=(Started("i1", "release-by-handoff", "j1"),), rows=(), at=AT, budget=budget())
    assert isinstance(verdict, Admitted) and "(Image occ (Edge occupancy))" in verdict.occurrence


# An act's binds and its action's reaction agree both ways, or acceptance names the disagreement. An
# entity node left unbound could only match an entity the step does not read, the matcher's choice, or
# none (c-ev-pk-unbound-node-wrong-target-1018), and a bind no redex node meets leaves the act unable to
# apply, each of which planned before as a silent NoPlan or a handoff to a seat that never accepted.
# am[verifies a-ev-pk-bind-table-1018@761a0f] am[verifies c-ev-pk-unbound-node-wrong-target-1018@bf7b36]
@pytest.mark.parametrize("binds, problem", [
    ("(Bind (T task) (A owner-seat))", "unbound-node (release-by-handoff hand B)"),
    ("(Bind (T task) (A owner-seat) (B receiving-seat) (Z owner-seat))", "unknown-bind (release-by-handoff hand Z)"),
    ("(Bind (T ghost) (A owner-seat) (B receiving-seat))", "undeclared-bind-entity (release-by-handoff hand ghost)"),
    ("(Bind (T receiving-seat) (A owner-seat) (B receiving-seat))",
     "mistyped-bind (release-by-handoff hand T receiving-seat)"),
])
def test_an_acts_binds_and_its_actions_reaction_agree_both_ways(binds: str, problem: str) -> None:
    domain = dataclasses.replace(DOMAIN, bigraph=read_section(parsed_forms(HANDOFF_SECTION, budget=None), "handoff.metta"))
    text = HANDOFF_LIBRARY.replace("(Bind (T task) (A owner-seat) (B receiving-seat))", binds)
    assert text != HANDOFF_LIBRARY
    with pytest.raises(ProcedureError) as refused:
        read_procedures(text, "handoff.metta", domain, budget=budget())
    assert str(refused.value).count(" (release-by-handoff hand ") == 1
    assert problem in str(refused.value)


# An action the section gives no reaction has no node to bind.
# am[verifies a-ev-pk-bind-table-1018@761a0f]
def test_an_act_binds_nothing_when_its_action_has_no_reaction() -> None:
    text = (resources.files("goal_chainer.planning") / "library" / "task_control.metta").read_text(encoding="utf-8")
    bound = text.replace("(Step pause act pause_recoverably (After reach))",
                         "(Step pause act pause_recoverably (After reach) (Bind (T task)))")
    assert bound != text
    with pytest.raises(ProcedureError, match=r"unknown-bind \(release-by-pause pause T\)"):
        read_procedures(bound, "bound.metta", DOMAIN, budget=budget())


# A witness is the planner's own answer handed back, so a field that is not exactly one ground MeTTa
# term, a field that is not text, images of another shape, a rule of another shape or naming another
# step, and an image naming a node none of the step's rules has are each the caller's malformed input,
# refused naming what is wrong and never an engine error or a Blocked on nothing; a witness naming a
# function is data and never runs; the same step with its witness intact is admitted.
# am[verifies a-integrate-planner-input-failures-1018@b84418] am[verifies c-integrate-request-input-leaks-762662a-1018@380521]
def test_a_malformed_witness_is_refused_naming_its_field(library, capfd) -> None:
    start = _plan(library).steps[0]
    witness = start.witness
    node, image = witness.images[0]
    injected = '(println! "INJECTED")'
    broken = {
        "witness rule is not one MeTTa term": dataclasses.replace(witness, rule="("),
        "witness rule is not one MeTTa term: '(Step 0) (Step 1)'": dataclasses.replace(witness, rule="(Step 0) (Step 1)"),
        "witness image 0 node is not one MeTTa term": dataclasses.replace(witness, images=(("(", image), *witness.images[1:])),
        "witness image 0 is not one MeTTa term": dataclasses.replace(witness, images=((node, "("), *witness.images[1:])),
        "witness rule must be text, not NoneType": dataclasses.replace(witness, rule=None),
        "witness images must be (node, image) pairs": dataclasses.replace(witness, images=((node,),)),
        "witness rule is not ground data": dataclasses.replace(witness, rule=witness.rule.replace("0", "$n", 1)),
        "witness image 0 node is not ground data": dataclasses.replace(witness, images=(("$x", image), *witness.images[1:])),
        "witness image 0 is not ground data": dataclasses.replace(witness, images=((node, "(Ent $y)"), *witness.images[1:])),
        'witness rule must be (Step INDEX "PROCEDURE" PART)': dataclasses.replace(witness, rule=injected),
        "witness rule names another step": dataclasses.replace(
            witness, rule=witness.rule.replace("release-by-pause", "reach-safe-point")),
    }
    for message, wrong in broken.items():
        with pytest.raises(InvalidInputError) as refused:
            _admit(dataclasses.replace(start, witness=wrong), None, library)
        assert message in str(refused.value) and not isinstance(refused.value, PlanningRefused), message
    for wrong in (dataclasses.replace(witness, images=((injected, image), *witness.images[1:])),
                  dataclasses.replace(witness, images=(("(Ent nowhere)", image), *witness.images[1:]))):
        with pytest.raises(PlanningRefused, match=r"UnknownImage \(Bound "):
            _admit(dataclasses.replace(start, witness=wrong), None, library)
    assert "INJECTED" not in "".join(capfd.readouterr())
    assert isinstance(_admit(start, None, library), Admitted)


# am[verifies a-ev-pk-python-api-1018@db9b94]
def test_admission_takes_an_instance_exactly_when_the_step_reads_one(library) -> None:
    start, run = _plan(library).steps[1:3]
    with pytest.raises(InvalidInputError, match="start step is admitted without"):
        _admit(start, "i1", library)
    with pytest.raises(InvalidInputError, match="act step is admitted with"):
        _admit(run, None, library)


# A step's own fields are what its unchanged witness determines: an act relabelled investigate, or a
# binding moved to another declared entity, is refused, while a step whose rules are gone stays Stale
# whatever its fields say, and its report-only application number is never read.
# am[verifies a-integrate-planner-step-consistency-1018@fc6d64]
def test_a_step_whose_fields_disagree_with_its_witness_is_refused(library) -> None:
    run = _plan(library).steps[2]
    journal = [Started("i1", "reach-safe-point", "j1")]
    assert run.kind == "act" and isinstance(_admit(run, "i1", library, journal), Admitted)
    assert isinstance(_admit(dataclasses.replace(run, application=run.application + 7), "i1", library, journal), Admitted)

    with pytest.raises(InvalidInputError, match="kind investigate is not its declared step's, act"):
        _admit(dataclasses.replace(run, kind="investigate"), "i1", library, journal)
    node, entity = run.binding[0]
    other = next(e.id for e in DOMAIN.bigraph.entities if e.id != entity)
    moved = dataclasses.replace(run, binding=((node, other), *run.binding[1:]))
    with pytest.raises(InvalidInputError, match="binding is not the declared entities"):
        _admit(moved, "i1", library, journal)

    text = (resources.files("goal_chainer.planning") / "library" / "task_control.metta").read_text(encoding="utf-8")
    original = "(When (Signal state_preservation_route))\n  (Steps (Step run act continue_task (After))))"
    edited = read_procedures(text.replace(original, original.replace("route))", "route) (Not (Signal review_open)))")),
                             "edited.metta", DOMAIN, budget=budget())
    assert isinstance(_admit(moved, "i1", edited, journal, {**PAUSE_ROUTE, "review_open": "refuted"}), Stale)


# Signal evidence has one owner, the readings, and extra rows reach the planner's own evidence only
# through claims: an extra row claims only a statement or its negation, withdraws only such a row, and
# cites no Reading, Journal or Receipt observation and no row but a statement row. So asserting a signal,
# or a signal on an entity, which only an entity reading a binding places may claim, either way round,
# withdrawing a reading's row, laundering a statement through a reading no packet holds, and withdrawing
# for a reading's, journal's or receipt's row are each refused naming the row, while a statement resting
# on a signal's claim, or withdrawn for another statement's row, plans.
# am[verifies a-ev-pk-signal-evidence-one-owner-1018@bda917] am[verifies c-rel-pk-reading-observation-launders-1018@11309c]
# am[verifies c-rel-pk-reading-row-reason-launders-1018@0fd564] am[verifies a-bnd-proof-1019@85b4cd]
def test_an_extra_row_argues_about_statements_alone(library) -> None:
    from metta import S, Symbol

    forever = Symbol("Forever")
    contention = S.Signal("resource_contention")
    reading_row = S.From(contention, S.Observation(S.Reading(_readings(PAUSE_ROUTE)[0].observation_id(),
                                                             "deterministic", forever)))
    done = S.On(S.Done("pause"), S.Inst("i1"))
    statement = literal_term(StatementLiteral('(sn c "elsewhere")'))
    drilled = S.From(statement, S.Observation(S.Drill("d1", "measured", forever)))
    nearby = S.From(literal_term(StatementLiteral('(sn c "nearby")')), S.Observation(S.Drill("d4", "measured", forever)))
    refused = {
        "asserts a signal": S.From(contention, S.Observation(S.Drill("d2", "measured", forever))),
        "refutes a signal": S.From(S.Not(contention), S.Observation(S.Drill("d3", "measured", forever))),
        "asserts a signal on an entity": S.From(S.On(contention, Symbol("task")),
                                                S.Observation(S.Drill("d5", "measured", forever))),
        "refutes a signal on an entity": S.From(S.Not(S.On(contention, Symbol("task"))),
                                                S.Observation(S.Drill("d6", "measured", forever))),
        "withdraws a reading's row": S.Withdrawn(reading_row, S.Stated(S.Overruled())),
        "rests on a reading's observation": S.From(statement, S.Observation(S.Reading("r1", "model-proposed", forever))),
        "withdraws for a reading's observation": S.Withdrawn(drilled, S.Observation(S.Reading("r9", "measured", forever))),
        "rests on a receipt": S.From(statement, S.Observation(S.Receipt("x1", "deterministic", forever))),
        "rests on a journal entry": S.From(statement, S.Observation(S.Journal("j1", "deterministic", forever))),
        "withdraws for a reading's row": S.Withdrawn(drilled, S.Row(reading_row)),
        "withdraws for a journal row": S.Withdrawn(
            drilled, S.Row(S.From(S.Not(done), S.Observation(S.Journal("j1", "deterministic", forever))))),
        "withdraws for a receipt row": S.Withdrawn(
            drilled, S.Row(S.From(done, S.Observation(S.Receipt("x1", "deterministic", forever))))),
        "withdraws for a statement resting on a reading": S.Withdrawn(
            drilled, S.Row(S.From(statement, S.Observation(S.Reading("r1", "measured", forever))))),
    }
    for case, row in refused.items():
        with pytest.raises(PlanningRefused, match=r"ExtraRow \((From|Withdrawn) ") as caught:
            plan((RELEASED,), domain=DOMAIN, library=library, readings=_readings(PAUSE_ROUTE), journal=(),
                 rows=[*_restores(library), drilled, row], receipts={}, at=AT, budget=budget())
        assert len(caught.value.problems) == 1, case

    reads = S.From(statement, S.Claim(contention))
    answer = plan((RELEASED,), domain=DOMAIN, library=library, readings=_readings(PAUSE_ROUTE), journal=(),
                  rows=[*_restores(library), drilled, reads, nearby, S.Withdrawn(drilled, S.Claim(contention)),
                        S.Withdrawn(reads, S.Row(nearby))], receipts={}, at=AT, budget=budget())
    assert isinstance(answer, Plan)


# A caller's row may name a statement as the library writes it or as literal_term does, and both name the
# library's literal: the restore drill's row in the library's spelling lets the pause route plan as the text
# spelling does, where without the drill the route inquires it, measured at eeda1b0
# (c-integrate-statement-row-boundary-confirmed-1018). Negated, either spelling refutes it; a withdrawal naming
# the text row in the library's spelling withdraws it, as one resting on a Claim of another statement so
# spelled does; admission reads rows the same way; a statement SNARS cannot parse in a planner position is
# refused naming its row; and a Statement term outside the planner's positions stays as written, so a
# withdrawal stated as (Stated (Statement (if a b))), which no SNARS parse accepts, stands as justification's
# generic stated reason.
# am[verifies a-ev-pk-row-statement-positions-1018@9c3a50] am[verifies i-dd-statement-row-spelling-1018@37f754]
def test_a_row_names_a_statement_as_the_library_does(library) -> None:
    from metta import S, forms

    drill = '(Observation (Drill "drill" "deterministic" Forever))'
    text = _restores(library)[0]
    tree = forms(f"(From (Statement {RESTORES}) {drill})")[0]

    def planned(*rows):
        return plan((RELEASED,), domain=DOMAIN, library=library, readings=_readings(PAUSE_ROUTE), journal=(),
                    rows=list(rows), receipts={}, at=AT, budget=budget())

    def shape(answer):
        return [(s.kind, s.procedure, s.step) for s in answer.steps] if isinstance(answer, Plan) else type(answer)

    assert shape(planned()) is Inquiry
    assert isinstance(planned(text), Plan) and shape(planned(tree)) == shape(planned(text))
    refuted = forms(f"(From (Not (Statement {RESTORES})) {drill})")[0]
    assert shape(planned(refuted)) == shape(planned(S.From(S.Not(text.children[1]), text.children[2])))
    assert shape(planned(text, S.Withdrawn(tree, S.Stated(S.Overruled())))) is Inquiry
    elsewhere = forms('(From (Statement (sn c "elsewhere")) (Observation (Drill "d2" "measured" Forever)))')[0]
    by_claim = S.Withdrawn(text, S.Claim(forms('(Statement (sn c "elsewhere"))')[0]))
    assert shape(planned(text, elsewhere, by_claim)) is Inquiry
    assert shape(planned(text, S.Withdrawn(text, forms("(Stated (Statement (if a b)))")[0]))) is Inquiry
    with pytest.raises(InvalidInputError, match=r"rows\[1\].*is not a SNARS statement"):
        planned(text, forms(f"(From (Statement (if a b)) {drill})")[0])
    start = planned(text).steps[0]

    def admitted(*rows):
        return admit(start, instance_id=None, domain=DOMAIN, library=library, readings=_readings(PAUSE_ROUTE),
                     journal=(), rows=list(rows), at=AT, budget=budget())

    assert isinstance(admitted(tree), Admitted) and not isinstance(admitted(), Admitted)


# The path c-rel-pk-reading-row-reason-launders-1018 measured: an expired reading's row is still an
# accepted row, only its link withdrawn, so a withdrawal naming that row would stand on a reading that
# has lapsed, while the same withdrawal naming the signal's claim lapses with it. The planner refuses the
# first and plans with the second, and the justification kernel shows what the refusal prevents.
# am[verifies a-ev-pk-signal-evidence-one-owner-1018@bda917] am[verifies c-rel-pk-reading-row-reason-launders-1018@0fd564]
def test_a_withdrawal_reads_a_reading_through_its_signals_claim_never_its_row(library) -> None:
    from metta import S, Symbol

    from goal_chainer.planning import justification as jk

    expired = SignalReading("review_open", "detected", "test", "measured",
                            observed_at=AT - timedelta(hours=2), valid_until=AT - timedelta(hours=1))
    signal = S.Signal("review_open")
    # The expired reading's row as the shared row rule writes it.
    reading_row = S.From(signal, S.Observation(S.Reading(expired.observation_id(), "measured",
                                                         S.Until(microseconds(expired.valid_until)))))
    claim = literal_term(StatementLiteral('(sn c "elsewhere")'))
    statement = S.From(claim, S.Observation(S.Drill("d1", "measured", Symbol("Forever"))))
    by_row, by_claim = S.Withdrawn(statement, S.Row(reading_row)), S.Withdrawn(statement, S.Claim(signal))

    def planned(withdrawal):
        return plan((RELEASED,), domain=DOMAIN, library=library, readings=[*_readings(PAUSE_ROUTE), expired],
                    journal=(), rows=[*_restores(library), statement, withdrawal], receipts={}, at=AT, budget=budget())

    with pytest.raises(PlanningRefused, match=r"ExtraRow \(Withdrawn ") as caught:
        planned(by_row)
    assert len(caught.value.problems) == 1
    assert isinstance(planned(by_claim), Plan)

    def label(withdrawal) -> tuple[str, str]:
        justification = jk.justify([reading_row, statement, withdrawal], at=microseconds(AT), budget=budget())
        return next((found.status, found.check) for found in justification.labels
                    if found.argument == plain_value(S.Claim(claim)))

    assert label(by_row)[0] == "Unsupported"
    assert label(by_claim) == ("Accepted", "Checked")


SIGNALS = ("owner_mismatch", "resource_contention", "review_open")
AS_OF = 1_800_000_000_000_000
# An observation of a kind the planner builds rows for itself, as its text spells it.
OWNED = re.compile(r"\((Reading|Journal|Receipt) ")


# The rows the planner builds, written twice under two names, then extra rows of every shape a caller
# can write: a statement row from a drill for each of three statements, and probe rows whose sources
# and withdrawal reasons are drawn from every REF kind: a claim the owned or drill rows make, a stated
# reason, a drill, an observation the owned rows hold, an observation of an owned kind nobody holds, an
# owned row, and a drill or probe row. The owned rows are readings over three signals, some expired at
# AS_OF, and a journal's not-done rows, each perhaps dispatched or receipted.
# am[verifies c-ev-pk-signal-standing-from-signal-rows-1018@d2fc3b] am[verifies c-rel-pk-reading-row-reason-launders-1018@0fd564]
@st.composite
def _snapshots(draw):
    from metta import S, Symbol

    forever = Symbol("Forever")
    classes = st.sampled_from(("measured", "model-proposed"))
    readings = draw(st.lists(st.tuples(st.sampled_from(SIGNALS), st.booleans(), classes, st.sampled_from((None, -1, 1))),
                             min_size=1, max_size=4))
    steps = draw(st.lists(st.tuples(st.booleans(), st.booleans()), max_size=2))

    def owned(prefix: str) -> tuple[list, list]:
        froms = [S.From(S.Signal(s) if held else S.Not(S.Signal(s)),
                        S.Observation(S.Reading(f"{prefix}r{n}", cls, forever if lapse is None else S.Until(AS_OF + lapse))))
                 for n, (s, held, cls, lapse) in enumerate(readings)]
        withdrawals = []
        for n, (dispatched, received) in enumerate(steps):
            done = S.On(S.Done(f"s{n}"), S.Inst("i1"))
            froms.append(S.From(S.Not(done), S.Observation(S.Journal(f"{prefix}j{n}", "deterministic", forever))))
            if dispatched:
                withdrawals.append(S.Withdrawn(froms[-1], S.Stated(S.Dispatched(S.Inst("i1"), f"s{n}", "t"))))
            if received:
                froms.append(S.From(done, S.Observation(S.Receipt(f"{prefix}x{n}", "deterministic", forever))))
        return froms, withdrawals

    owned_froms, owned_withdrawals = owned("")
    statements = [literal_term(StatementLiteral(f'(sn c "{name}")')) for name in ("a", "b", "c", "d")]
    drilled = [S.From(claim, S.Observation(S.Drill(f"d{n}", draw(classes), forever)))
               for n, claim in enumerate(statements[:3])]
    # Every claim a reference names is one some owned or drill row makes, since the kernel refuses a
    # dangling one; a probe's own claim may be any statement or its negation.
    claims = [row.children[1] for row in [*owned_froms, *drilled]]

    def reference(n: int, kinds: tuple[str, ...], rows: list):
        kind = draw(st.sampled_from(kinds))
        if kind == "claim":
            return S.Claim(draw(st.sampled_from(claims)))
        if kind == "stated":
            return S.Stated(S.Dropped())
        if kind == "drill":
            return S.Observation(S.Drill(f"p{n}", draw(classes), forever))
        if kind == "held":
            return draw(st.sampled_from(owned_froms)).children[2]
        if kind == "forged":
            return S.Observation(S[draw(st.sampled_from(("Reading", "Journal", "Receipt")))](f"z{n}", "deterministic", forever))
        return S.Row(draw(st.sampled_from(owned_froms if kind == "owned row" else rows)))

    froms, withdrawals = [], []
    for n in range(draw(st.integers(min_value=0, max_value=3))):
        claim = draw(st.sampled_from(statements))
        froms.append(S.From(S.Not(claim) if draw(st.booleans()) else claim,
                            reference(n, ("claim", "drill", "held", "forged"), [])))
    for n in range(draw(st.integers(min_value=0, max_value=3))):
        withdrawn = draw(st.sampled_from([*drilled, *froms]))
        reason = reference(10 + n, ("claim", "stated", "drill", "held", "forged", "owned row", "extra row"), [*drilled, *froms])
        withdrawals.append(S.Withdrawn(withdrawn, reason))
    extra = list({str(row): row for row in [*drilled, *froms, *withdrawals]}.values())
    renamed = owned("q")
    return [*owned_froms, *owned_withdrawals], [*renamed[0], *renamed[1]], extra, sorted({s for s, *_ in readings})


# The extra rows the planner's own admission rule refuses, as plain values counted by how often each is
# refused: gc-pk-extra-row-problems run in the planning group's space, outside any plan, on rows whose
# heads name no function.
# am[verifies a-ev-pk-signal-evidence-one-owner-1018@bda917] am[verifies a-ev-pk-refused-on-group-answers-1018@07fbb3]
def _refused(rows: list) -> Counter:
    from metta import Expression

    [problems] = group_answers(group.PLANNING, "(gc-pk-extra-row-problems {rows})", rows=Expression(tuple(rows)))
    return Counter(problem[2] for problem in problems)


# The claims the owner rule rests on, as properties of the justification kernel over what the planner
# admits. The planner refuses exactly the extra rows citing an observation of a kind it builds rows for,
# directly or through a row. The rows it admits change no signal's label or knowledge
# (c-ev-pk-signal-standing-from-signal-rows-1018), and they reach the owned evidence only through
# claims, so writing the same owned evidence under other names changes no claim's label: a reference
# to an owned row would dangle (c-rel-pk-reading-row-reason-launders-1018).
# am[verifies c-ev-pk-signal-standing-from-signal-rows-1018@d2fc3b] am[verifies a-ev-pk-signal-evidence-one-owner-1018@bda917]
# am[verifies c-rel-pk-reading-row-reason-launders-1018@0fd564]
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(_snapshots())
def test_admitted_extra_rows_reach_owned_evidence_only_through_claims(snapshot) -> None:
    from metta import S

    from goal_chainer.planning import justification as jk

    owned, renamed, extra, signals = snapshot
    refused = _refused(extra)
    assert refused == Counter(plain_value(row) for row in extra if OWNED.search(str(row)))
    admitted = [row for row in extra if plain_value(row) not in refused]
    alone = jk.justify(owned, at=AS_OF, budget=budget())
    joined = jk.justify([*owned, *admitted], at=AS_OF, budget=budget())
    moved = jk.justify([*renamed, *admitted], at=AS_OF, budget=budget())

    # A label's argument is the plain value of its REF, (S.Claim, CLAIM) for a claim, so the selection
    # compares symbols, never text.
    def claim_labels(justification, *, signals: bool = False) -> dict[str, tuple[str, str]]:
        def selected(argument) -> bool:
            if argument[0] != S.Claim:
                return False
            literal = argument[1][1] if argument[1][0] == S.Not else argument[1]
            return not signals or literal[0] == S.Signal

        return {str(label.argument): (label.status, label.check) for label in justification.labels
                if selected(label.argument)}

    assert claim_labels(alone, signals=True)
    assert claim_labels(joined, signals=True) == claim_labels(alone, signals=True)
    for signal in signals:
        assert (jk.knowledge(S.Signal(signal), joined, budget=budget())
                == jk.knowledge(S.Signal(signal), alone, budget=budget()))
    assert len(claim_labels(joined)) > len(claim_labels(alone))
    assert claim_labels(moved) == claim_labels(joined)


# A witness pins every named image, and with one anchor per literal every anonymous node a rule can
# match is unique, so no admission today meets two transitions; Ambiguous guards the day a reading
# binds knowledge among several entities (a-dr-brs-readings-1018). The grouping is checked on a built
# state holding one signal's anonymous node under each of two tasks, which a rule consumes from a root:
# two non-isomorphic successors are Ambiguous, and with one task's node the occurrence is admitted.
# The admission runs speculatively in the planning group's space under a request budget.
# am[verifies a-ev-pk-projection-1018@e5d57e] am[verifies a-ev-pk-admit-on-group-answers-1018@dc60a9]
@pytest.mark.parametrize("tasks, ambiguous", [(("task", "task2"), True), (("task",), False)])
def test_admission_refuses_to_choose_between_transitions_its_witness_leaves_open(tasks, ambiguous: bool) -> None:
    from metta import S

    rule = ('(Rule (Step 0 "prune" "move") (Bigraph (Inner 0 ()) (Outer 1 ()) (Nodes (N K (Signal "x"))) '
            "(Place (In K (Root 0))) (Link)) (Bigraph (Inner 0 ()) (Outer 1 ()) (Nodes) (Place) (Link)) "
            "(Eta) (Conditions) (Priority 0))")
    place = " ".join([*(f"(In {task} (Root 0))" for task in ("task", "task2")),
                      *(f'(In (new build (Signal "x") {task} 0) {task})' for task in tasks)])
    nodes = " ".join(f"(N {task} Task)" for task in ("task", "task2")) + " " + " ".join(
        f'(N (new build (Signal "x") {task} 0) (Signal "x"))' for task in tasks)
    state = f"(Bigraph (Inner 0 ()) (Outer 1 ()) (Nodes {nodes}) (Place {place}) (Link))"
    sig = "(Signature (Control Task 0 active) (Control Signal 0 atomic))"
    [answer] = group_answers(group.PLANNING, f'(gc-pk-admit-on {sig} (Domain (Anchors) (Reactions) (Ports)) '
                             f'(Library () ()) ({rule}) (Step 0 "prune" "move") None () {state})')
    if ambiguous:
        assert answer == (S.Ambiguous, 2)
    else:
        assert answer[0] == S.Admitted and answer[1][0] == S.Occurrence


# A condition no clause of bg-holds-condition decides is the kernel's Error, and admission refuses the step
# naming it, never admitting it or taking it as Ambiguous.
# am[verifies a-ev-pk-admit-react-outcome-1018@061b1d]
def test_admission_refuses_a_rule_whose_condition_no_clause_decides() -> None:
    from metta import S

    rule = ('(Rule (Step 0 "prune" "move") (Bigraph (Inner 0 ()) (Outer 1 ()) (Nodes (N K Thing)) (Place (In K (Root 0))) '
            "(Link)) (Bigraph (Inner 0 ()) (Outer 1 ()) (Nodes) (Place) (Link)) (Eta) (Conditions (Mystery K)) (Priority 0))")
    state = "(Bigraph (Inner 0 ()) (Outer 1 ()) (Nodes (N k Thing)) (Place (In k (Root 0))) (Link))"
    [answer] = group_answers(group.PLANNING, f'(gc-pk-admit-on (Signature (Control Thing 0 atomic)) '
                             f'(Domain (Anchors) (Reactions) (Ports)) (Library () ()) ({rule}) (Step 0 "prune" "move") '
                             f'None () {state})')
    assert answer == (S.Refused, (S.Problem, S.Kernel, (S.Error, (S.Mystery, S.K), (S.UnhandledCondition, ()))))


# am[verifies a-ev-pk-python-api-1018@db9b94]
def test_a_reading_observed_after_the_plans_time_is_refused(library) -> None:
    late = SignalReading("resource_contention", "detected", "test", "deterministic", observed_at=AT + timedelta(seconds=1))
    with pytest.raises(InvalidInputError, match="observed after"):
        plan((RELEASED,), domain=DOMAIN, library=library, readings=[late], journal=(), rows=(), receipts={}, at=AT,
             budget=budget())


# An attempt dispatched after the plan's time would let the plan rest on the future, as a later reading would,
# and a dispatch time without an offset names no instant, so both are refused.
# am[verifies a-ev-fb-request-receipts-1018@4c8f23]
@pytest.mark.parametrize("dispatched, message", [
    (AT + timedelta(seconds=1), "dispatched after the plan's time"),
    (datetime(2026, 10, 18, 5, 0), "timezone offset"),
], ids=["after-the-plan", "no-offset"])
def test_an_attempt_dispatched_after_the_plans_time_is_refused(library, dispatched: datetime, message: str) -> None:
    journal = (Started("i1", "release-by-pause", "j1"), Dispatched("i1", "pause", "a1", "sha256:pause-witness", dispatched))
    with pytest.raises(InvalidInputError, match=message):
        _plan(library, journal=journal)


INCIDENT_SECTION = "\n".join([
    "(gc-brs-control Incident (Ports) active)",
    "(gc-brs-entity incident Incident)",
    "(gc-brs-in incident (Root 0))",
    *(f"(gc-brs-literal (Signal {signal}) (On incident))" for signal in ("coordination-needed", "sensitive-data", "unverified")),
])
INCIDENT_LIBRARY = """
(gc-procedures incident-v1)
(gc-procedure brief-responders
  (Achieves (Not (Signal coordination-needed)))
  (When (Signal coordination-needed) (Signal sensitive-data))
  (Steps (Step checked achieve (Not (Signal unverified)) (After))
         (Step brief act publish_redacted_summary (After checked))))
(gc-investigator fact-check (Signal unverified))
"""


# Nothing in the planner is task-control's: the packaged incident domain, with a section and a library
# its caller supplies, has the library accepted, a plan through its own action once the facts are
# verified, an inquiry for its own investigator while they are unknown, and its first step admitted.
# am[verifies a-ev-pk-python-api-1018@db9b94] am[verifies a-ev-pk-projection-1018@e5d57e]
def test_a_second_domain_with_a_supplied_section_and_library_plans_and_admits() -> None:
    text = (resources.files("goal_chainer.domains") / "data" / "incident.metta").read_text(encoding="utf-8")
    domain = read_domain(f"{text}\n{INCIDENT_SECTION}", "incident", budget=budget())
    library = read_procedures(INCIDENT_LIBRARY, "incident-procedures.metta", domain, budget=budget())
    goal = (NegatedLiteral(SignalLiteral("coordination-needed")),)
    states = {"coordination-needed": "detected", "sensitive-data": "detected", "unverified": "refuted"}

    def readings(states: dict[str, str]) -> list[SignalReading]:
        return [SignalReading(signal, state, "test", "deterministic", observed_at=AT - timedelta(minutes=1))
                for signal, state in states.items()]

    answer = plan(goal, domain=domain, library=library, readings=readings(states), journal=(), rows=(), receipts={},
                  at=AT, budget=budget())
    assert isinstance(answer, Plan)
    assert [(s.kind, s.procedure, s.step) for s in answer.steps] == [
        ("start", "brief-responders", None), ("act", "brief-responders", "brief"), ("finish", "brief-responders", None)]
    assert isinstance(admit(answer.steps[0], instance_id=None, domain=domain, library=library, readings=readings(states),
                            journal=(), rows=(), at=AT, budget=budget()), Admitted)

    del states["unverified"]
    inquiry = plan(goal, domain=domain, library=library, readings=readings(states), journal=(), rows=(), receipts={},
                   at=AT, budget=budget())
    assert isinstance(inquiry, Inquiry)
    assert (inquiry.literal, inquiry.investigator) == (SignalLiteral("unverified"), "fact-check")


# The packaged task-control domain declares the paper's world as its bigraph section, so its packaged
# library is accepted against the domain as shipped, and each release route plans on that world from the
# readings and the restore drill's row alone, its first step admitted, with no caller-supplied topology.
# The pause route runs on to a safe point first; the handoff route, with no state-preservation route and
# the work belonging elsewhere, asks the receiving owner before it hands off, and its hand step is the
# domain's handoff reaction, moving the task from its seat to the receiving seat.
# am[verifies a-ev-pk-packaged-topology-1018@440efe] am[verifies a-ev-pk-python-api-1018@db9b94]
# am[verifies a-ev-pk-bind-table-1018@761a0f]
@pytest.mark.parametrize("states, steps, acted", [
    (PAUSE_ROUTE, [("start", "release-by-pause", None), ("start", "reach-safe-point", None),
                   ("act", "reach-safe-point", "run"), ("finish", "reach-safe-point", None),
                   ("act", "release-by-pause", "pause"), ("finish", "release-by-pause", None)], {}),
    ({**PAUSE_ROUTE, "state_preservation_route": "refuted", "owner_mismatch": "detected"},
     [("start", "release-by-handoff", None), ("start", "ask-receiving-owner", None),
      ("act", "ask-receiving-owner", "ask"), ("finish", "ask-receiving-owner", None),
      ("act", "release-by-handoff", "hand"), ("finish", "release-by-handoff", None)],
     {"(Acted T)": "task", "(Acted A)": "seat", "(Acted B)": "receiving_seat"}),
], ids=["pause", "handoff"])
def test_the_packaged_domain_plans_each_release_route_on_its_own_section(states, steps, acted) -> None:
    domain = packaged_domain("task-control", budget=budget())
    assert domain.bigraph is not None
    library = packaged_procedures(domain, budget=budget())
    answer = plan((RELEASED,), domain=domain, library=library, readings=_readings(states), journal=(),
                  rows=_restores(library), receipts={}, at=AT, budget=budget())

    assert isinstance(answer, Plan)
    assert [(s.kind, s.procedure, s.step) for s in answer.steps] == steps
    reacting = {key: value for step in answer.steps for key, value in step.binding if key.startswith("(Acted ")}
    assert reacting == acted
    assert isinstance(admit(answer.steps[0], instance_id=None, domain=domain, library=library,
                            readings=_readings(states), journal=(), rows=_restores(library), at=AT,
                            budget=budget()), Admitted)


# am[verifies a-ev-pk-no-auto-memo-1018@7bf95a] am[verifies a-ev-pk-defined-calls-guard-1018@e785c4]
def _planner_functions(space) -> set[str]:
    return {str(atom.children[1].children[0]) for atom in space.atoms()
            if str(atom.children[0]) == "=" and getattr(atom.children[1], "children", None)}


# pymetta memoizes a recursive group that one equation body calls twice, keying each call by its whole
# arguments; a memoized function's compiled clauses call cache_call.
# am[verifies a-ev-pk-no-auto-memo-1018@7bf95a] am[rests-on c-brs-k-auto-memo-1018@9c39b3]
def test_the_engine_memoizes_no_planner_function() -> None:
    assert prepare(group.PLANNING, budget=budget()).startswith("sha256:")
    with metta_engine(None) as engine:
        space = engine.space(group.PLANNING.space)
        names = {n for n in _planner_functions(space) if n.startswith(("gc-pk-", "gc-procedure"))}
        memoized = sorted(n for n in names if "cache_call" in space.fn[n].compiled)
    assert {"gc-pk-search", "gc-pk-walk", "gc-pk-answer", "gc-pk-plan-worker"} <= names
    assert memoized == []


# am[verifies a-ev-pk-defined-calls-guard-1018@e785c4]
def _called(atom) -> set[str]:
    from metta import Expression, Symbol

    if not isinstance(atom, Expression) or not atom.children:
        return set()
    head = atom.children[0]
    found = {str(head)} if isinstance(head, Symbol) and str(head).startswith(("gc-", "bg-")) \
        and not str(head).startswith("gc-brs-") else set()
    return found.union(*(_called(child) for child in atom.children))


# pymetta leaves a call to a function no module defines as data, so a misspelled or removed kernel
# function fails silently (c-ev-pk-undefined-call-silent-1018); every call the planner's modules make
# must name a function the planning group's space defines.
# am[verifies a-ev-pk-defined-calls-guard-1018@e785c4] am[rests-on c-ev-pk-undefined-call-silent-1018@a83d7b]
def test_every_planner_call_names_a_defined_function() -> None:
    from metta import forms

    prepare(group.PLANNING, budget=budget())
    with metta_engine(None) as engine:
        defined = _planner_functions(engine.space(group.PLANNING.space))
    planner = [m for m in group.MODULES if m.parent.name in ("planning", "policy") and m.name != "justification.metta"]
    called: set[str] = set()
    for module in planner:
        for atom in forms(module.read_text(encoding="utf-8")):
            if str(atom.children[0]) == "=":
                called |= _called(atom.children[2])
    assert called and sorted(called - defined) == []


# am[verifies a-ev-pk-scope-lint-planner-1018@37d570] am[rests-on c-brs-k-case-vars-clause-scoped-1018@de7554]
def test_no_planner_equation_binds_a_pattern_variable_twice_in_one_scope() -> None:
    planner = [Path(m) for m in group.MODULES if m.parent.name in ("planning", "policy") and m.name != "justification.metta"]
    assert sorted(m.name for m in planner) == ["compile.metta", "feedback.metta", "goalchainer_procedure.metta",
                                                "knowledge.metta", "projection.metta", "search.metta"]
    assert [found for module in planner for found in rebound_variables(module)] == []


# lib_functional's is-member answers True once per occurrence, so a list holding an element twice
# multiplies every answer that tests it; the planner's modules test membership through the shared
# vocabulary's gc-has, which answers once and which the planning group loads first, and keep no
# membership of their own. A doubled anchor once made a plan answer eight times.
# am[verifies a-ev-pk-membership-gc-has-1018@f2f7e4] am[rests-on c-ev-pk-is-member-per-occurrence-1018@c8243c]
def test_no_planner_module_tests_membership_with_is_member() -> None:
    from metta import Expression, forms

    planner = [m for m in group.MODULES if m.parent.name in ("planning", "policy") and m.name != "justification.metta"]
    heads: set[str] = set()

    def visit(atom) -> None:
        if isinstance(atom, Expression) and atom.children:
            heads.add(str(atom.children[0]))
            for child in atom.children:
                visit(child)

    for module in planner:
        for atom in forms(module.read_text(encoding="utf-8")):
            visit(atom)
    assert "is-member" not in heads and "gc-has" in heads
    assert not heads & {"gc-pk-member?", "gc-procedure-member?"}

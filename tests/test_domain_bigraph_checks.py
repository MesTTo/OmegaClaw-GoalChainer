"""Purpose: verify the bigraph section's relational checks in the domain checks' own module group:
goal_chainer.domains.bigraph.FACTS answers the section's facts in the validation runner's shape, a
consistent section has no fault, each way a section can name what it does not declare, or declare one
thing twice, is the fault its table row names, every fault reported at once, and the domain loader
runs the tables and renders their faults when it reads a domain."""

from __future__ import annotations

import pytest

from goal_chainer.domains import bigraph
from goal_chainer.domains.forms import parsed_forms
from goal_chainer.domains.loader import CHECKS_GROUP, _packaged_directory, read_domain
from goal_chainer.domains.model import DomainError
from goal_chainer.runtime.evaluator import evaluate, plain_value
from request_support import budget

CORE = (("Declared", "signal", "owner_mismatch"), ("Declared", "signal", "resource_contention"),
        ("Declared", "action", "handoff"))
REACTION = """(gc-brs-reaction handoff
  (Redex (Bigraph (Inner 1 ()) (Outer 2 ()) (Nodes (N A Seat) (N T Task)) (Place (In A (Root 0)) (In T A) (In (Site 0) T)) (Link)))
  (Reactum (Bigraph (Inner 1 ()) (Outer 2 ()) (Nodes (N A Seat) (N T Task)) (Place (In A (Root 1)) (In T A) (In (Site 0) T)) (Link)))
  (Eta (0 0)) (Conditions))"""
BASE = [
    "(gc-brs-control Task (Ports occupies) active)",
    "(gc-brs-control Seat (Ports) active)",
    "(gc-brs-entity seat Seat)",
    "(gc-brs-entity task Task)",
    "(gc-brs-in seat (Root 0))",
    "(gc-brs-in task seat)",
    "(gc-brs-link task occupies (Edge occupancy))",
    "(gc-brs-literal (Signal owner_mismatch) (On task))",
    "(gc-brs-literal (Signal resource_contention) (On task) (Via occupancy))",
    REACTION,
]


# The validation runner's term for a fact: each head a symbol, each string argument a string.
# am[verifies a-rel-nd-validation-runner-1018]
def _fact_atom(fact: tuple):
    from metta import S

    return S[fact[0]](*(_fact_atom(argument) if isinstance(argument, tuple) else argument for argument in fact[1:]))


# The (reason, failing fact's head) of each fault the section's tables find over its facts and the core's.
# am[verifies a-rel-nd-validation-runner-1018]
def _faults(forms: list[str]) -> list[tuple[str, str]]:
    section = bigraph.read_section(parsed_forms("\n".join(forms), budget=None), "checks.metta")
    answer = plain_value(evaluate(CHECKS_GROUP, bigraph.ENTRY, _fact_atom(("Domain", *CORE, *bigraph.FACTS(section))),
                                  budget=budget()))
    assert all(str(fault[0]) == "Fault" for fault in answer), answer
    return sorted((fault[1], str(fault[2][0])) for fault in answer)


# am[verifies a-rel-nd-validation-runner-1018] am[verifies a-rel-brs-section-1018@b63f59]
def test_a_consistent_section_has_no_fault() -> None:
    assert _faults(BASE) == []


# Each row of the section's tables, by the forms that break it: an added form, a replaced one, or both.
@pytest.mark.parametrize(
    "replace, add, expected",
    [
        ({}, ["(gc-brs-control Seat (Ports) passive)"], [("duplicate-control", "Control")] * 2),
        ({"(gc-brs-entity seat Seat)": "(gc-brs-entity seat Bench)"}, [], [("undeclared-control", "Entity")]),
        ({}, ["(gc-brs-entity task Task)"], [("duplicate-entity", "Entity")] * 2),
        ({"(gc-brs-in task seat)": ""}, [], [("unplaced-entity", "Entity")]),
        ({}, ["(gc-brs-in task (Root 1))"], [("entity-placed-twice", "Entity")]),
        ({}, ["(gc-brs-in ghost (Root 0))"], [("undeclared-placed-entity", "Placed")]),
        ({"(gc-brs-in task seat)": "(gc-brs-in task nowhere)"}, [], [("undeclared-parent", "Placed")]),
        ({"(gc-brs-in seat (Root 0))": "(gc-brs-in seat task)"}, [], [("cyclic-placement", "Placed")] * 2),
        ({}, ["(gc-brs-link ghost occupies (Edge e))"], [("undeclared-linked-entity", "PortLink")]),
        ({}, ["(gc-brs-link task serves (Edge e))"], [("undeclared-port", "PortLink")]),
        ({}, ["(gc-brs-link task occupies (Name y))"], [("port-linked-twice", "PortLink")] * 2),
        ({}, ["(gc-brs-literal (Reading owner_mismatch) (On task))"], [("malformed-literal", "Anchor")]),
        ({}, ["(gc-brs-literal (Signal review_open) (On seat))"], [("undeclared-signal", "Anchor")]),
        ({"(gc-brs-literal (Signal owner_mismatch) (On task))": "(gc-brs-literal (Signal owner_mismatch) (On ghost))"},
         [], [("undeclared-anchor-entity", "Anchor")]),
        ({"(Via occupancy)": "(Via elsewhere)"}, [], [("undeclared-via", "Anchor")]),
        ({}, ["(gc-brs-literal (Signal owner_mismatch) (On seat))"], [("anchored-twice", "Anchor")] * 2),
        ({"gc-brs-reaction handoff": "gc-brs-reaction fly"}, [], [("undeclared-action", "Reaction")]),
        ({"(N A Seat) (N T Task)) (Place (In A (Root 1))": "(N A Bench) (N T Task)) (Place (In A (Root 1))"}, [],
         [("undeclared-node-control", "Reaction")]),
        ({}, [REACTION], [("duplicate-reaction", "Reaction")] * 2),
    ],
)
# am[verifies a-rel-nd-validation-runner-1018] am[verifies a-rel-brs-section-1018@b63f59]
def test_each_inconsistency_is_the_fault_its_row_names(replace: dict[str, str], add: list[str], expected) -> None:
    forms = []
    for form in BASE:
        for old, new in replace.items():
            form = form.replace(old, new)
        if form:
            forms.append(form)
    assert len(forms) + sum(1 for old, new in replace.items() if not new) == len(BASE)
    assert _faults([*forms, *add]) == sorted(expected)


# Every fact is (HEAD, ARG, ...), every ARG a string or a tuple of that shape, and every list headed;
# an entity declared with a description is also (Described ID), and one without is not.
# am[verifies a-rel-nd-validation-runner-1018] am[related a-dr-readings-facts-1018]
# am[verifies a-bnd-faults-1019@b5dc70]
def test_the_facts_take_the_runners_shape() -> None:
    def shaped(value) -> bool:
        return isinstance(value, str) or (isinstance(value, tuple) and len(value) >= 1 and isinstance(value[0], str)
                                          and all(shaped(argument) for argument in value[1:]))

    facts = bigraph.FACTS(bigraph.read_section(parsed_forms("\n".join(BASE), budget=None), "checks.metta"))
    assert all(isinstance(fact, tuple) and shaped(fact) for fact in facts)
    assert ("Placed", "seat", ("Root", "0")) in facts
    assert ("Anchor", ("Signal", "resource_contention"), "task", ("Via", "occupancy")) in facts
    assert ("Reaction", "handoff", ("Controls", "Seat", "Task", "Seat", "Task")) in facts
    assert not [fact for fact in facts if fact[0] == "Described"]
    described = [form.replace("(gc-brs-entity seat Seat)", '(gc-brs-entity seat Seat "the seat that owns the task")')
                 for form in BASE]
    facts = bigraph.FACTS(bigraph.read_section(parsed_forms("\n".join(described), budget=None), "checks.metta"))
    assert [fact for fact in facts if fact[0] == "Described"] == [("Described", "seat")]


# The loader runs the section's tables among the domain's checks: the packaged task-control domain reads
# into Domain.bigraph through its own section, and with one more entity no gc-brs-in places it fails
# with that one fault, its fact written whole before the row's message.
# am[verifies a-rel-nd-validation-runner-1018] am[verifies a-rel-nd-section-warm-ups-1018]
def test_the_loader_runs_the_sections_tables_among_the_domains_checks() -> None:
    text = (_packaged_directory() / "task_control.metta").read_text(encoding="utf-8")

    domain = read_domain(text, "task-control", budget=budget())
    assert domain.bigraph is not None and "task" in [entity.id for entity in domain.bigraph.entities]
    with pytest.raises(DomainError) as raised:
        read_domain(f"{text}\n(gc-brs-entity ghost Seat)", "task-control", budget=budget())
    assert raised.value.faults == ('(Entity "ghost" "Seat") has no gc-brs-in placing it',)

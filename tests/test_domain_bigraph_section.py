"""Purpose: verify goal_chainer.domains.bigraph reads a domain's gc-brs-* forms into its records,
keeps literals and reaction terms as the atoms pymetta parsed, and refuses any form of the wrong
shape naming the file and the form."""

from __future__ import annotations

import pytest

from goal_chainer.domains.bigraph import (
    Anchor,
    BigraphSection,
    Control,
    Edge,
    Entity,
    Name,
    Placement,
    PortLink,
    Root,
    read_section,
)
from goal_chainer.domains.forms import parsed_forms
from goal_chainer.domains.model import DomainError

SECTION = """
(gc-brs-control Task (Ports occupies serves) active)
(gc-brs-control Seat (Ports) passive)
(gc-brs-control Flag (Ports) atomic)
(gc-brs-entity owner-seat Seat "the current owner's seat")
(gc-brs-entity task Task)
(gc-brs-in owner-seat (Root 0))
(gc-brs-in task owner-seat)
(gc-brs-link task occupies (Edge occupancy))
(gc-brs-link task serves (Name parent-goal))
(gc-brs-literal (Signal owner_mismatch) (On task))
(gc-brs-literal (Signal resource_contention) (On task) (Via occupancy))
(gc-brs-reaction handoff
  (Redex (Bigraph (Inner 1 ()) (Outer 1 ()) (Nodes (N T Task)) (Place (In T (Root 0)) (In (Site 0) T)) (Link)))
  (Reactum (Bigraph (Inner 1 ()) (Outer 1 ()) (Nodes (N T Task)) (Place (In T (Root 0)) (In (Site 0) T)) (Link)))
  (Eta (0 0))
  (Conditions))
"""


# am[verifies a-rel-brs-section-1018@b63f59]
def _read(text: str) -> BigraphSection:
    return read_section(parsed_forms(text, budget=None), "domains/data/example.metta")


# am[verifies a-rel-brs-section-1018@b63f59]
def test_a_section_reads_into_its_records_in_declared_order() -> None:
    section = _read(SECTION)

    assert section.controls == (
        Control("Task", ("occupies", "serves"), "active"),
        Control("Seat", (), "passive"),
        Control("Flag", (), "atomic"),
    )
    assert section.entities == (Entity("owner-seat", "Seat", "the current owner's seat"), Entity("task", "Task"))
    assert section.placements == (Placement("owner-seat", Root(0)), Placement("task", "owner-seat"))
    assert section.links == (
        PortLink("task", "occupies", Edge("occupancy")),
        PortLink("task", "serves", Name("parent-goal")),
    )
    assert [(anchor.entity, anchor.via) for anchor in section.anchors] == [("task", ()), ("task", ("occupancy",))]
    assert [str(anchor.literal) for anchor in section.anchors] == ["(Signal owner_mismatch)", "(Signal resource_contention)"]
    (reaction,) = section.reactions
    assert reaction.action == "handoff"
    assert str(reaction.redex).startswith("(Bigraph (Inner 1 ()) (Outer 1 ())")
    assert (str(reaction.eta), str(reaction.conditions)) == ("(Eta (0 0))", "(Conditions)")


# Literals and terms stay the atoms pymetta parsed, so reading the same text twice gives equal records.
# am[verifies a-rel-brs-section-1018@b63f59]
def test_reading_the_same_text_twice_gives_equal_sections() -> None:
    assert _read(SECTION) == _read(SECTION)


# am[verifies a-rel-brs-section-1018@b63f59]
def test_a_domain_without_bigraph_forms_has_an_empty_section() -> None:
    assert read_section([], "domains/data/example.metta") == BigraphSection()


# Each row is a form of the wrong shape: an argument missing or extra, a string, number or
# variable where a name belongs, an unknown kind, or a wrapper with the wrong head.
@pytest.mark.parametrize(
    "form",
    [
        "(gc-brs-control Task (Ports a) sticky)",
        "(gc-brs-control Task (Ports \"a\") active)",
        "(gc-brs-control Task (Port a) active)",
        "(gc-brs-control Task active)",
        "(gc-brs-entity task)",
        "(gc-brs-entity \"task\" Task)",
        "(gc-brs-entity task Task description)",
        "(gc-brs-entity task Task \"a\" \"b\")",
        "(gc-brs-in task)",
        "(gc-brs-in task (Root -1))",
        "(gc-brs-in task (Root x))",
        "(gc-brs-in $task seat)",
        "(gc-brs-link task occupies occupancy)",
        "(gc-brs-link task occupies (Edge 7))",
        "(gc-brs-link task occupies (Link occupancy))",
        "(gc-brs-literal owner_mismatch (On task))",
        "(gc-brs-literal (Signal owner_mismatch) task)",
        "(gc-brs-literal (Signal owner_mismatch) (On task) (Via \"occupancy\"))",
        "(gc-brs-literal (Signal owner_mismatch) (On task) (Through occupancy))",
        "(gc-brs-reaction handoff (Redex R) (Reactum R) (Eta) )",
        "(gc-brs-reaction \"handoff\" (Redex R) (Reactum R) (Eta) (Conditions))",
        "(gc-brs-reaction handoff (Redex R S) (Reactum R) (Eta) (Conditions))",
        "(gc-brs-reaction handoff (Redex R) (Reactum R) (Map) (Conditions))",
    ],
)
# am[verifies a-rel-brs-section-1018@b63f59]
def test_a_form_of_the_wrong_shape_is_refused_naming_the_file_and_the_form(form: str) -> None:
    with pytest.raises(DomainError) as refused:
        _read(form)
    assert str(refused.value).startswith(f"domains/data/example.metta: {form} should be (")


# am[verifies a-rel-brs-section-1018@b63f59]
def test_a_form_outside_the_section_is_refused() -> None:
    with pytest.raises(DomainError, match="is not a bigraph section form"):
        _read("(gc-signal owner_mismatch \"a\")")

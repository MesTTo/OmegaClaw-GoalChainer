"""Purpose: check the shared fault-table reader: the Every reading reports each failing row and the First reading only the first, subject by subject under any atom as a name, and a predicate answering anything but exactly True or False is the table's defect under either reading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from goal_chainer.runtime.modules import load_metta_module
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.evaluator import plain_value
from goal_chainer.relevance.policy import FAULT_TABLES, constant, items, term

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fault_table_predicates.metta"
CONTEXT = "context"


# am[related a-rel-nd-shared-table-reader-1018@24e3dd]
def answer(function: str, *arguments: Any) -> Any:
    """The one answer of (FUNCTION ARGUMENT ...) with the reader and the test predicates loaded."""

    holes = {f"argument{index}": argument for index, argument in enumerate(arguments)}
    source = "!(" + " ".join([function, *("{" + name + "}" for name in holes)]) + ")"
    with metta_engine(None) as engine:
        load_metta_module(engine, FAULT_TABLES)
        load_metta_module(engine, FIXTURE)
        [[result]] = engine.run(source, **holes)
    return shown(plain_value(result))


# A symbol and a string both read as their text, so an answer compares with plain tuples.
# am[related a-rel-nd-shared-table-reader-1018@24e3dd]
def shown(value: Any) -> Any:
    if isinstance(value, tuple):
        return tuple(shown(item) for item in value)
    return value if isinstance(value, (bool, int, float, str)) else str(value)


# am[related a-rel-nd-shared-table-reader-1018@24e3dd]
def table(*rows: tuple[str, str]) -> Any:
    return items(term("Row", reason, constant(f"gc-ft-test-{predicate}"), f"{reason} failed") for reason, predicate in rows)


# am[related a-rel-nd-shared-table-reader-1018@24e3dd]
def subjects(*named: tuple[Any, Any]) -> Any:
    return items(term("Subject", name, value) for name, value in named)


CHECKS = table(("positive", "positive"), ("fails", "fails"), ("holds", "holds"))
NODE = term("Node", constant("r"), 1, constant("c"))
SUBJECTS = subjects((constant("a"), 5), (NODE, -1))


# am[verifies a-rel-nd-shared-table-reader-1018@24e3dd] am[verifies c-rel-nd-reader-two-readings-1018@81343b]
def test_the_every_reading_reports_each_failing_row_subject_by_subject() -> None:
    assert answer("gc-table-faults", constant("Every"), CHECKS, CONTEXT, SUBJECTS) == (
        ("Fault", "fails", "a", "fails failed"),
        ("Fault", "positive", ("Node", "r", 1, "c"), "positive failed"),
        ("Fault", "fails", ("Node", "r", 1, "c"), "fails failed"),
    )


# am[verifies a-rel-nd-shared-table-reader-1018@24e3dd] am[verifies c-rel-nd-reader-two-readings-1018@81343b]
def test_the_first_reading_reports_only_each_subjects_first_failing_row() -> None:
    assert answer("gc-table-faults", constant("First"), CHECKS, CONTEXT, SUBJECTS) == (
        ("Fault", "fails", "a", "fails failed"),
        ("Fault", "positive", ("Node", "r", 1, "c"), "positive failed"),
    )


# A later row may read what an earlier one established, so after a failure none is called: a
# misspelled predicate after it would otherwise be a defect.
# am[verifies a-rel-nd-shared-table-reader-1018@24e3dd]
def test_the_first_reading_calls_no_row_after_a_failing_one() -> None:
    rows = table(("fails", "fails"), ("typo", "misspelled"))

    assert answer("gc-table-faults", constant("First"), rows, CONTEXT, subjects((constant("x"), 1))) == (
        ("Fault", "fails", "x", "fails failed"),
    )


# The parser's condition (c-rel-nd-table-defect-1018): a predicate's other answers are the table's
# defect, carrying every answer, never the subject failing the row.
# am[verifies c-rel-nd-table-defect-1018@b4a907]
@pytest.mark.parametrize("reading", ["Every", "First"])
@pytest.mark.parametrize(
    ("predicate", "answers"),
    [
        ("misspelled", (("gc-ft-test-misspelled", "context", 1),)),
        ("silent", ()),
        ("twice", (True, False)),
    ],
)
def test_a_predicate_answering_neither_true_nor_false_is_the_tables_defect(reading: str, predicate: str, answers: tuple) -> None:
    rows = table((predicate, predicate))

    assert answer("gc-table-faults", constant(reading), rows, CONTEXT, subjects((constant("x"), 1))) == (
        ("Defect", predicate, "x", answers),
    )


# am[verifies a-rel-nd-shared-table-reader-1018@24e3dd]
def test_first_failing_answers_holds_the_failing_row_or_the_defect() -> None:
    assert answer("gc-table-first-failing", table(("holds", "holds")), CONTEXT, 1) == "Holds"
    assert answer("gc-table-first-failing", CHECKS, CONTEXT, 5) == ("Row", "fails", "gc-ft-test-fails", "fails failed")
    assert answer("gc-table-first-failing", table(("typo", "misspelled")), CONTEXT, 1) == (
        "Defect", "typo", 1, (("gc-ft-test-misspelled", "context", 1),),
    )


# am[verifies a-rel-nd-shared-table-reader-1018@24e3dd]
def test_no_rows_or_no_subjects_report_nothing() -> None:
    assert answer("gc-table-faults", constant("Every"), items(()), CONTEXT, SUBJECTS) == ()
    assert answer("gc-table-faults", constant("First"), CHECKS, CONTEXT, items(())) == ()

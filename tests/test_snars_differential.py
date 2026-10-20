"""Purpose: verify the SNARS record comparison the engine differential uses: it ignores only the
protocol's wall-clock field, fresh variable names and boolean spelling, and still tells apart quoted
text, clock-named data anywhere else, quoted booleans and variable sharing."""

from __future__ import annotations

import pytest

from snars_differential import clock_fields, equal, tree

from goal_chainer.snars_program import PROTOCOL_PATH

CLOCKS = clock_fields(PROTOCOL_PATH.read_text(encoding="utf-8"))  # am[related a-rt-snars-modules-in-package-1016@7d0afe]


# An inspect record shaped as the protocol prints it, with the clock and metadata given.
# am[verifies a-rt-snars-clock-normalize-1017@908992]
def _inspect(clock: str, metadata: str = "()") -> str:
    return (
        "(goalchainer-snars-v1 inspect ok (inspection (state s1) "
        f"(clock {clock}) (cells (14)) (metadata {metadata})))"
    )


# am[verifies a-rt-snars-clock-normalize-1017@908992]
def test_the_protocol_has_one_clock_field_the_inspect_record():
    assert CLOCKS == {("inspect", "inspection")}


# The (clock N) field is statistics(walltime) of whichever process ran the batch.
# am[verifies a-rt-snars-clock-normalize-1017@908992]
def test_the_inspect_records_wall_clock_is_ignored():
    assert equal([_inspect("2185")], [_inspect("1706")], CLOCKS)


# Each pair differs in something a run does control, so it must compare unequal.
# am[verifies a-rt-snars-clock-normalize-1017@908992]
@pytest.mark.parametrize(
    "left, right",
    [
        ('(goalchainer-snars-v1 belief ok (belief "(clock 1)"))',
         '(goalchainer-snars-v1 belief ok (belief "(clock 2)"))'),
        (_inspect("1", '("(clock 1)")'), _inspect("1", '("(clock 2)")')),
        ("(goalchainer-snars-v1 belief ok (belief (clock 1)))",
         "(goalchainer-snars-v1 belief ok (belief (clock 2)))"),
        (_inspect("1", "((clock 1))"), _inspect("1", "((clock 2))")),
        (_inspect('"1"'), _inspect('"2"')),
        ('(goalchainer-snars-v1 x ok (p "true"))', '(goalchainer-snars-v1 x ok (p "True"))'),
        ("(goalchainer-snars-v1 x ok (p $a $a))", "(goalchainer-snars-v1 x ok (p $a $b))"),
    ],
    ids=["quoted clock text", "quoted clock text in an inspect record", "another record's clock",
         "a clock nested below the field", "a quoted clock value", "quoted booleans", "variable sharing"],
)
def test_what_the_comparison_must_still_tell_apart(left, right):
    assert not equal([left], [right], CLOCKS)


# am[verifies a-rt-snars-clock-normalize-1017@908992]
@pytest.mark.parametrize(
    "left, right",
    [
        ("(goalchainer-snars-v1 x ok (p $_255540 (q $_255540)))", "(goalchainer-snars-v1 x ok (p $_9 (q $_9)))"),
        ("(goalchainer-snars-v1 x ok (p true false))", "(goalchainer-snars-v1 x ok (p True False))"),
    ],
    ids=["variable names", "boolean spelling"],
)
def test_what_no_run_controls_compares_equal(left, right):
    assert equal([left], [right], CLOCKS)


# am[verifies a-rt-snars-clock-normalize-1017@908992]
def test_a_tree_keeps_quoted_text_whole_and_refuses_unbalanced_records():
    assert tree('(a "(b \\" c)" d)') == ["a", '"(b \\" c)"', "d"]
    for broken in ("(a (b)", "(a))", "(a) (b)"):
        with pytest.raises(ValueError):
            tree(broken)

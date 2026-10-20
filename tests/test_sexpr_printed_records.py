"""Purpose: verify that a record pymetta prints reads back through GoalChainer's printed-record paths
unchanged: whatever text a record's string holds, run_snars_batch's output lines keep a SNARS record
whole and parse_protocol_output reads the text back, whether the batch answers the record or prints
it with println!; parse_directive_output reads a directive record back from the line pymetta prints
for it, keeping the line before it as the transcript; and a record holding a symbol with a quote
ends with its own line."""

from __future__ import annotations

import pytest
from hypothesis import example, given, settings, strategies as st

from goal_chainer.directive_protocol import parse_directive_output
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.sexpr.codec import SexprCodec
from goal_chainer.sexpr.syntax import StringLiteral, metta_string
from goal_chainer.snars_engine import run_snars_batch
from goal_chainer.snars_program import SnarsBatch
from goal_chainer.snars_protocol import parse_protocol_output

# Any text a pymetta string can hold: every code point but the surrogates, which UTF-8 cannot carry.
TEXT = st.text(st.characters(blacklist_categories=("Cs",)))
# The same, never empty, as a directive's text field must be.
NONEMPTY_TEXT = st.text(st.characters(blacklist_categories=("Cs",)), min_size=1)
CODEC = SexprCodec()
# The two ways a record reaches a batch's printed text: as the directive's answer, which
# run_snars_batch prints one atom a line, as it prints a protocol function's record, and through
# println!, whose output the engine captures. No rule rewrites the record, so the batch answers or
# prints it as written.
SHAPES = {"answered": "{record}", "printed": "(println! {record})"}


# Any text in a record's string reads back unchanged, however the batch prints the record. The
# first example holds the eight characters besides newline and return that str.splitlines cuts at,
# which pymetta prints raw inside a string; the second puts whitespace and two of them at both ends
# of the string, which came back as "\nedges\t\n" when the lines were cut there and trimmed.
# am[verifies a-rt-framing-split-newline-1018@c9dd95] am[verifies c-rt-framing-needs-only-newline-split-1018@bb3396]
@pytest.mark.parametrize("shape", SHAPES)
@settings(max_examples=100, deadline=None)
@given(text=TEXT)
@example(text="vt\x0bff\x0cfs\x1cgs\x1drs\x1enel\x85ls\u2028ps\u2029")
@example(text="\u2028 edges\t \x0b")
@example(text="newline\n return\r tab\t")
def test_any_text_in_a_printed_record_reads_back_unchanged(shape: str, text: str) -> None:
    record = f"(goalchainer-snars-v1 probe ok {metta_string(text)})"
    batch = SnarsBatch((), frozenset(), SHAPES[shape].format(record=record))

    lines = run_snars_batch(batch, budget=RunBudget(inference_budget=None, timeout_seconds=900)).output_lines

    assert parse_protocol_output(lines, CODEC, expected_operation="probe").payload == StringLiteral(text)


# Any text a directive's text field can hold reads back unchanged from the line pymetta prints for
# the record, str(atom), as lib_directive's answers reach parse_directive_output, and the human line
# before it stays the transcript. The example is a Markdown board holding a blank line. The engine is
# taken per example, since run_snars_batch takes it too and a holder runs alone.
# am[verifies a-dr-one-line-records-1018@d9f30d]
@settings(max_examples=100, deadline=None)
@given(text=NONEMPTY_TEXT)
@example(text="# Board\n\n| Task | State |\n| --- | --- |\n| collect | ready |")
def test_any_text_in_a_printed_directive_record_reads_back_unchanged(text: str) -> None:
    record = f"(goalchainer-directive-v1 markdown ok (markdown {metta_string(text)}))"
    with metta_engine(None) as engine:
        printed = [str(atom) for atom in engine.space("&printed-records").eval(record)]

    run = parse_directive_output(["rendering audit", *printed], CODEC, expected_operation="markdown")

    assert (run.value, run.transcript) == (text, ("rendering audit",))


# A symbol holding a quote, such as a"b, which a space's eval reads as one symbol and str(atom) prints
# raw, ends with its record's line, so the line after it stays the program's own output; a line
# joiner that took the quote for a string's start swallowed that line into the record. A batch's
# program text cannot hold the symbol, since the engine's program reader refuses it.
# am[verifies a-dr-one-line-records-1018@d9f30d] am[verifies c-dr-quote-in-symbol-opens-string-1018@0bc57a]
def test_a_record_holding_a_quoted_symbol_ends_with_its_line() -> None:
    with metta_engine(None) as engine:
        printed = [str(atom) for atom in engine.space("&printed-records").eval('(goalchainer-snars-v1 probe ok (quoted a"b))')]

    envelope = parse_protocol_output([*printed, "True"], CODEC, expected_operation="probe")

    assert printed == ['(goalchainer-snars-v1 probe ok (quoted a"b))']
    assert CODEC.emit(envelope.payload) == '(quoted a"b)'

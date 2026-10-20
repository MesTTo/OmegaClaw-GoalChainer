"""Purpose: verify that every string literal GoalChainer writes crosses into a pymetta space and back
unchanged, with pymetta itself as the oracle: a space reads metta_string's literal of any text as
that text and so does the codec's reader, the control characters json.dumps wrote as escapes
included, and for any literal the codec's reader decodes each escape as pymetta's reader does."""

from __future__ import annotations

import pytest
from hypothesis import example, given, settings, strategies as st

from goal_chainer.runtime.engine import metta_engine
from goal_chainer.sexpr.syntax import StringLiteral, emit, metta_string, parse

# Any text a pymetta string can hold: every code point but the surrogates, which UTF-8 cannot carry.
TEXT = st.text(st.characters(blacklist_categories=("Cs",)))
# A literal's body, piece by piece: a character that is neither a quote nor a backslash, or a
# backslash and any character after it, so the body never closes the literal early.
PIECES = st.one_of(
    st.characters(blacklist_categories=("Cs",), blacklist_characters='"\\'),
    st.characters(blacklist_categories=("Cs",)).map(lambda character: "\\" + character),
)


# One engine space for the module, so the examples share one boot.
# am[verifies a-dr-codec-pymetta-strings-1018@7fc480]
@pytest.fixture(scope="module")
def space():
    with metta_engine(None) as engine:
        yield engine.space("sexpr-strings")


# What a pymetta space answers for a literal: the value of each answer.
# am[verifies a-dr-codec-pymetta-strings-1018@7fc480]
def _read(space, literal: str) -> list:
    return [atom.value for atom in space.eval(literal)]


# Any text's literal, read by pymetta and by the codec alike, is the text, on one line; the five
# examples are controls json.dumps wrote as \b, \f or \u00XX, which pymetta read as bsbx, fffx,
# nulu0000x, ctlu0001x and escu001bx.
# am[verifies a-dr-codec-pymetta-strings-1018@7fc480] am[verifies c-dr-codec-escapes-diverge-pymetta-1018@af4800]
@settings(max_examples=200, deadline=None)
@given(text=TEXT)
@example(text="bs\x08x")
@example(text="ff\x0cx")
@example(text="nul\x00x")
@example(text="ctl\x01x")
@example(text="esc\x1bx")
@example(text='quote " and back \\ slash, tab\t, newline\n, return\r')
def test_any_text_crosses_into_pymetta_and_back_unchanged(space, text: str) -> None:
    literal = metta_string(text)

    assert _read(space, literal) == [text]
    assert parse(literal) == StringLiteral(text)
    assert "\n" not in literal and "\r" not in literal


# For any literal, the codec's reader decodes each escape as pymetta's reader does: \" \\ \n \r \t
# and \' decoded, the backslash of any other escape dropped, and every other character, a raw
# control character included, read as itself.
# am[verifies a-dr-codec-pymetta-strings-1018@7fc480]
@settings(max_examples=200, deadline=None)
@given(pieces=st.lists(PIECES, max_size=12))
@example(pieces=["\\b", "\\f", "\\u", "0041", "\\x", "\\0", "\x00", "\x0c"])
def test_the_codec_reads_any_literal_as_pymetta_does(space, pieces: list[str]) -> None:
    literal = '"' + "".join(pieces) + '"'

    assert [parse(literal).value] == _read(space, literal)


# Table files may put comments inside a form; quoted semicolons remain string data.
# am[verifies a-integrate-vocab-no-engine-regression-1019@0ed119]
@pytest.mark.parametrize("source", [
    '(a ; a comment containing ) and "\n b)',
    '(a; adjacent comment\n b)',
    '("a; b" ; note\n "c")',
    '; before\n(a b); after',
    '(a ; first\n ; second\n (b c))',
])
def test_comments_read_as_pymetta_reads_them(source: str) -> None:
    from metta import parse as native_parse

    with metta_engine(None):
        assert emit(parse(source)) == str(native_parse(source))

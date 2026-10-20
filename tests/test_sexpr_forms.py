"""Purpose: verify the MeTTa top-level form reader: each form's text is the exact source at its
start, a ! makes the next form a directive across whitespace and comments, parentheses, ; and !
inside strings and comments split nothing, every malformed text names its kind and place, the
SNARS modules' directives come out flagged, and generated programs round-trip form by form."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from goal_chainer.sexpr.forms import MettaTextError, top_level_forms
from goal_chainer.snars_program import SNARS_DIRECTORY


# am[verifies a-rt-metta-forms-shared-1017@db105c]
def _forms(text: str) -> list[tuple[str, int, bool]]:
    return [(form.text, form.index, form.directive) for form in top_level_forms(text)]


# am[verifies a-rt-metta-forms-shared-1017@db105c]
def test_forms_and_directives_are_the_exact_source_at_their_start() -> None:
    text = '(a "(" ;\n b)\n!(c)\n! ; note (\n (d)\n!\n(e "!")'
    forms = _forms(text)
    expected = [('(a "(" ;\n b)', False), ("!(c)", True), ("! ; note (\n (d)", True), ('!\n(e "!")', True)]
    assert forms == [(form, text.index(form), directive) for form, directive in expected]
    assert all(text[index : index + len(form)] == form for form, index, _ in forms)


# Parentheses, ; and ! inside strings and comments, and escaped quotes, open and close nothing.
# am[verifies a-rt-metta-forms-shared-1017@db105c]
def test_strings_and_comments_split_nothing() -> None:
    text = '; (! not a form\n(say "a ) b ; c ! (" "q \\" (") ; ) closes nothing\n(f)'
    assert [form for form, _, _ in _forms(text)] == ['(say "a ) b ; c ! (" "q \\" (")', "(f)"]


# am[verifies a-rt-metta-forms-shared-1017@db105c]
@pytest.mark.parametrize(
    "text, kind, index, character",
    [
        ("(a) x", "stray", 4, "x"),
        ('(a) "note" (b)', "stray", 4, '"'),
        ("!foo", "stray", 0, "!"),
        ("(a) ! x (b)", "stray", 4, "!"),
        ("(a) !", "stray", 4, "!"),
        ("(a))", "unbalanced )", 3, ")"),
        ("(a) (b (c)", "unbalanced (", 4, "("),
        ("(a)\n!(b", "unbalanced (", 4, "!"),
    ],
    ids=["stray symbol", "string outside a form", "bang symbol", "bang before a symbol", "bang at the end",
         "extra close", "unclosed form", "unclosed directive"],
)
def test_each_malformed_text_names_its_kind_and_place(text, kind, index, character) -> None:
    with pytest.raises(MettaTextError) as caught:
        list(top_level_forms(text))
    assert (caught.value.kind, caught.value.index, caught.value.character) == (kind, index, character)


# Each line of these modules that starts with ! opens one directive, so a line count is an oracle
# independent of the reader.
# am[verifies a-rt-metta-forms-shared-1017@db105c]
@pytest.mark.parametrize("module", ["snars.metta", "snars/derive.metta", "snars/kernel.metta", "snars-guard.metta"])
def test_the_snars_modules_directives_come_out_flagged(module) -> None:
    text = (SNARS_DIRECTORY / module).read_text(encoding="utf-8")
    directives = [form for form in top_level_forms(text) if form.directive]
    assert len(directives) == sum(line.startswith("!") for line in text.splitlines()) > 0
    assert all(form.text.startswith("!(") for form in directives)


_SYMBOLS = st.text(alphabet="abcxyz-!&$=:", min_size=1, max_size=4)
_STRINGS = st.text(alphabet='ab ();!"\\\n', max_size=6).map(
    lambda body: '"' + body.replace("\\", "\\\\").replace('"', '\\"') + '"'
)
_COMMENTS = st.text(alphabet="ab ();!\"", max_size=6).map(lambda body: ";" + body + "\n")
_GAPS = st.lists(st.sampled_from([" ", "\n", "\t"]) | _COMMENTS, max_size=2).map("".join)
_ATOMS = st.recursive(
    _SYMBOLS | _STRINGS,
    lambda inner: st.lists(st.tuples(inner, _GAPS), max_size=3).map(
        lambda items: "(" + " ".join(item + gap for item, gap in items) + ")"
    ),
    max_leaves=8,
)
_FORMS = st.lists(st.tuples(st.booleans(), _GAPS, _ATOMS.filter(lambda atom: atom.startswith("(")), _GAPS), max_size=5)


# Rendering generated forms, some made directives across generated whitespace and comments, and
# reading the text back gives the same forms, directives and exact texts in order.
# am[verifies a-rt-metta-forms-shared-1017@db105c]
@given(_FORMS)
def test_generated_programs_read_back_form_by_form(items) -> None:
    text, expected = "", []
    for directive, separator, form, gap in items:
        piece = ("!" + separator + form) if directive else form
        expected.append((piece, len(text), directive))
        text += piece + gap + "\n"
    assert _forms(text) == expected

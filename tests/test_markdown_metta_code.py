"""Purpose: Mettabase c079c89's tests of its metta code fences, quoted add and eval actions and
their diagnostics, run against the copy in goal_chainer.markdown_python;
markdown_library/PROVENANCE.md says what changed."""
# am[verifies a-rt-p3-markdown-vendored-1017@88745b] am[implements a-rt-p3-adopt-upstream-markdown-tests-1017@404f47]

from __future__ import annotations

from goal_chainer.markdown_python.ast import MettaAction
from goal_chainer.markdown_python.metta_code import parse_metta_fence


def test_parse_metta_fence_quotes_add_and_eval_forms() -> None:
    parsed = parse_metta_fence('(: foo Atom)\n(foo bar)\n!(foo bar)\n(* 2 21)\n"42"')

    assert parsed.actions == (
        MettaAction("add", 0, "(quote (: foo Atom))"),
        MettaAction("add", 1, "(quote (foo bar))"),
        MettaAction("eval", 2, "(quote (foo bar))"),
        MettaAction("add", 3, "(quote (* 2 21))"),
        MettaAction("add", 4, '(quote "42")'),
    )
    assert parsed.diagnostic == ""


def test_parse_metta_fence_does_not_double_quote_parse_results() -> None:
    parsed = parse_metta_fence("(quote (* 2 21))")

    assert parsed.actions == (MettaAction("add", 0, "(quote (* 2 21))"),)


def test_parse_metta_fence_reports_diagnostic_and_keeps_prior_actions() -> None:
    parsed = parse_metta_fence("A\n(: broken")

    assert parsed.actions == (MettaAction("add", 0, "(quote A)"),)
    assert "line 1" in parsed.diagnostic

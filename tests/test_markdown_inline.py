"""Purpose: Mettabase c079c89's tests of its inline Markdown parser and plain-text extraction, run
against the copy in goal_chainer.markdown_python; markdown_library/PROVENANCE.md says what changed."""
# am[verifies a-rt-p3-markdown-vendored-1017@88745b] am[implements a-rt-p3-adopt-upstream-markdown-tests-1017@404f47]

from __future__ import annotations

from goal_chainer.markdown_python.ast import Code, Link, SoftBreak, Strong, Text
from goal_chainer.markdown_python.inline import extract_plain_text, parse_inlines


def test_parse_inlines_handles_text_strong_code_and_links() -> None:
    assert parse_inlines('Mary **strongly** used `x` and [GitHub](https://github.com "code")') == (
        Text("Mary "),
        Strong((Text("strongly"),)),
        Text(" used "),
        Code("x"),
        Text(" and "),
        Link((Text("GitHub"),), "https://github.com", "code"),
    )


def test_extract_plain_text_skips_code_and_keeps_link_label() -> None:
    nodes = parse_inlines("Mary **strongly** used `x` and [GitHub](https://github.com)")

    assert extract_plain_text(nodes) == "Mary strongly used and GitHub"


def test_parse_inlines_turns_line_breaks_into_softbreaks() -> None:
    assert parse_inlines("a\nb") == (Text("a"), SoftBreak(), Text("b"))

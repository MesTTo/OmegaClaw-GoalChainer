"""Purpose: Mettabase c079c89's tests of its block Markdown parser, headings, paragraphs, fences,
task lists and tables, run against the copy in goal_chainer.markdown_python;
markdown_library/PROVENANCE.md says what changed."""
# am[verifies a-rt-p3-markdown-vendored-1017@88745b] am[implements a-rt-p3-adopt-upstream-markdown-tests-1017@404f47]

from __future__ import annotations

from goal_chainer.markdown_python.ast import FencedCode, Heading, ListBlock, Paragraph, Table
from goal_chainer.markdown_python.emit import emit_ir
from goal_chainer.markdown_python.parser import parse_markdown


def test_parse_markdown_headings_paragraphs_and_fences() -> None:
    doc = parse_markdown("# Title\n\nBody text.\n\n```sparql\nSELECT ?x WHERE { ?x ?p ?o }\n```\n")

    assert isinstance(doc.children[0], Heading)
    assert isinstance(doc.children[1], Paragraph)
    assert isinstance(doc.children[2], FencedCode)
    assert doc.children[2].language == "sparql"
    assert doc.children[2].text == "SELECT ?x WHERE { ?x ?p ?o }"


def test_parse_markdown_task_list() -> None:
    doc = parse_markdown("- [x] Check claim provenance\n- Query BRCA2\n")

    assert isinstance(doc.children[0], ListBlock)
    assert doc.children[0].kind == "unordered"
    assert doc.children[0].items[0].task == "checked"
    assert doc.children[0].items[1].task == "no-task"


def test_parse_markdown_table_is_row_shaped_when_emitted() -> None:
    doc = parse_markdown("| 1 | 2 | 3 | 4 |\n| - | - | - | - |\n| 0 | 0 | 0 | 0 |\n")

    assert isinstance(doc.children[0], Table)
    assert '(md-row\n          (md-cell (md-inlines (md-txt "1")))' in emit_ir(doc, doc_id="md1")
    assert '(md-row\n          (md-cell (md-inlines (md-txt "0")))' in emit_ir(doc, doc_id="md1")


def test_metta_fence_gets_actions_and_diagnostics() -> None:
    doc = parse_markdown("```metta\n(: foo Atom)\n!(foo bar)\n```\n")

    block = doc.children[0]
    assert isinstance(block, FencedCode)
    assert block.language == "metta"
    assert [action.kind for action in block.metta_actions] == ["add", "eval"]
    assert block.diagnostic == ""


def test_unknown_directive_is_preserved_as_paragraph_for_first_pass() -> None:
    doc = parse_markdown("::: note\ncontent\n::: style")

    assert isinstance(doc.children[0], Paragraph)
    assert "::: note" in doc.children[0].source


def test_table_requires_valid_delimiter_row() -> None:
    doc = parse_markdown("| A | B |\n| not delimiter | row |\n")

    assert isinstance(doc.children[0], Paragraph)

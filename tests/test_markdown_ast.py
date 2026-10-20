"""Purpose: Mettabase c079c89's tests of its Markdown AST, immutable and tuple-shaped, run
against the copy in goal_chainer.markdown_python; markdown_library/PROVENANCE.md says what changed."""
# am[verifies a-rt-p3-markdown-vendored-1017@88745b] am[implements a-rt-p3-adopt-upstream-markdown-tests-1017@404f47]

from __future__ import annotations

from goal_chainer.markdown_python.ast import (
    Code,
    Document,
    FencedCode,
    Heading,
    Paragraph,
    Table,
    TableCell,
    Text,
)


def test_markdown_ast_is_immutable_and_tuple_normalized() -> None:
    doc = Document(children=[Heading(level=1, children=[Text("Title")])])

    assert doc.children == (Heading(level=1, children=(Text("Title"),)),)


def test_table_ast_preserves_row_shape() -> None:
    table = Table(
        alignments=["none", "right"],
        header=[TableCell([Text("Gene")]), TableCell([Text("Score")])],
        rows=[
            [TableCell([Text("BRCA2")]), TableCell([Text("1")])],
            [TableCell([Text("TP53")]), TableCell([Text("0")])],
        ],
    )

    assert table.alignments == ("none", "right")
    assert len(table.header) == 2
    assert len(table.rows) == 2
    assert table.rows[0][0] == TableCell(children=(Text("BRCA2"),))


def test_code_span_and_fenced_code_are_distinct() -> None:
    para = Paragraph(children=[Text("use "), Code("x"), Text(" now")])
    block = FencedCode(language="python", info="python", text="print(1)")

    assert para.children[1] == Code("x")
    assert block.language == "python"
    assert block.text == "print(1)"

"""Purpose: Mettabase c079c89's tests of its Markdown emitters, the pretty, human and machine trees
and the side facts, run against the copy in goal_chainer.markdown_python;
markdown_library/PROVENANCE.md says what changed."""
# am[verifies a-rt-p3-markdown-vendored-1017@88745b] am[implements a-rt-p3-adopt-upstream-markdown-tests-1017@404f47]

from __future__ import annotations

from goal_chainer.markdown_python.ast import (
    Document,
    FencedCode,
    Heading,
    ListBlock,
    ListItem,
    Paragraph,
    Table,
    TableCell,
    Text,
)
from goal_chainer.markdown_python.emit import emit_facts, emit_human, emit_ir, emit_pretty, emit_program


def test_emit_pretty_document_omits_child_ids() -> None:
    doc = Document(
        [
            Heading(1, [Text("Title")]),
            Paragraph([Text("Body text.")]),
        ]
    )

    assert emit_pretty(doc, doc_id="md1") == "\n".join(
        [
            "(md md1",
            '  (h1 "Title")',
            '  (p "Body text."))',
        ]
    )


def test_emit_ir_table_is_row_shaped() -> None:
    doc = Document(
        [
            Table(
                alignments=["none", "none", "none", "none"],
                header=[
                    TableCell([Text("1")]),
                    TableCell([Text("2")]),
                    TableCell([Text("3")]),
                    TableCell([Text("4")]),
                ],
                rows=[
                    [
                        TableCell([Text("0")]),
                        TableCell([Text("0")]),
                        TableCell([Text("0")]),
                        TableCell([Text("0")]),
                    ]
                ],
            )
        ]
    )

    output = emit_ir(doc, doc_id="md1")

    assert '(md-row\n          (md-cell (md-inlines (md-txt "1")))' in output
    assert '(md-row\n          (md-cell (md-inlines (md-txt "0")))' in output
    assert "md1-t1-r1-c1" not in output


def test_emit_pretty_keeps_code_blocks_direct() -> None:
    doc = Document([FencedCode(language="sparql", text="SELECT ?x WHERE { ?x ?p ?o }")])

    assert '(code sparql "SELECT ?x WHERE { ?x ?p ?o }")' in emit_pretty(doc, doc_id="md1")


def test_emit_ir_lists_are_block_shaped() -> None:
    doc = Document(
        [
            ListBlock(
                "unordered",
                0,
                True,
                [ListItem([Paragraph([Text("Task")])], task="checked")],
            )
        ]
    )

    output = emit_ir(doc, doc_id="md1")

    assert "(md-list unordered 0 tight" in output
    assert "(md-item checked" in output


def test_emit_human_outputs_writeable_md_syntax() -> None:
    from goal_chainer.markdown_python.parser import parse_markdown

    doc = parse_markdown("# Claim table\n\n| Gene | Score |\n| ---- | ----: |\n| BRCA2 | 1 |\n")

    assert emit_human(doc, doc_id="doc1") == "\n".join(
        [
            "(md doc1",
            '  (h1 "Claim table")',
            "  (table",
            "    (align none right)",
            '    (head "Gene" "Score")',
            '    (row "BRCA2" "1")))',
        ]
    )


def test_emit_ir_keeps_verbose_machine_tree() -> None:
    from goal_chainer.markdown_python.parser import parse_markdown

    ir = emit_ir(parse_markdown("# Title\n"), doc_id="doc1")

    assert ir.startswith("(md-ir doc1\n")
    assert "(md-heading 1" in ir



def test_emit_facts_has_ids_paths_text_and_tree_without_polluting_pretty_tree() -> None:
    from goal_chainer.markdown_python.parser import parse_markdown

    doc = parse_markdown("# Title\n\nBody text.\n")

    facts = emit_facts(doc, doc_id="md1")

    assert "(md-node md1 document)" in facts
    assert "(md-node md1-h1 heading)" in facts
    assert "(md-child md1 0 md1-h1)" in facts
    assert "(md-path md1-h1 (md-path 0))" in facts
    assert '(md-text md1-h1 "Title")' in facts
    assert '(md-tree md1-h1 (md-heading 1 (md-inlines (md-txt "Title"))))' in facts
    assert '(md-tree md1-h1 (h1 "Title"))' not in facts


def test_emit_facts_keeps_empty_table_cells_queryable() -> None:
    from goal_chainer.markdown_python.parser import parse_markdown

    doc = parse_markdown("| Gene | Score |\n| --- | --- |\n| BRCA2 |  |\n")

    facts = emit_facts(doc, doc_id="md1")

    empty_text_cells = [
        line for line in facts if line.startswith("(md-text md1-") and line.endswith(' "")')
    ]
    assert empty_text_cells, facts


def test_emit_facts_indexes_table_cells() -> None:
    from goal_chainer.markdown_python.parser import parse_markdown

    doc = parse_markdown("| Gene | Score |\n| ---- | ----: |\n| BRCA2 | 1 |\n")

    facts = emit_facts(doc, doc_id="md1")

    assert "(md-node md1-t1 table)" in facts
    assert "(md-table-align md1-t1 1 right)" in facts
    assert "(md-row-at md1-t1 body 1 md1-t1-r1)" in facts
    assert "(md-cell-at md1-t1 body 1 1 md1-t1-r1-c1)" in facts
    assert '(md-cell-value md1-t1-r1-c1 (md-inlines (md-txt "BRCA2")))' in facts


def test_emit_program_places_pretty_tree_first() -> None:
    from goal_chainer.markdown_python.parser import parse_markdown

    program = emit_program(parse_markdown("# Title\n"), doc_id="md1")

    assert program.splitlines()[0] == "(md md1"
    assert "\n(md-node md1 document)" in program
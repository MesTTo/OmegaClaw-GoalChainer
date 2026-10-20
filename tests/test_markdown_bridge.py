"""Purpose: Mettabase c079c89's tests of its Markdown bridge, Markdown and authored source to
MeTTa trees, facts and atoms, run against the copy in goal_chainer.markdown_python;
markdown_library/PROVENANCE.md says what changed."""
# am[verifies a-rt-p3-markdown-vendored-1017@88745b] am[implements a-rt-p3-adopt-upstream-markdown-tests-1017@404f47]

from __future__ import annotations

from goal_chainer.markdown_python.bridge import (
    markdown_to_atoms,
    markdown_to_facts,
    markdown_to_metta,
    markdown_to_tree,
    parse_markdown,
)


def test_markdown_to_tree_returns_pretty_tree_only() -> None:
    tree = markdown_to_tree("# Title\n", doc_id="md1")

    assert tree.startswith("(md md1\n")
    assert "\n(md-node md1 document)" not in tree


def test_markdown_to_metta_emits_pretty_tree_before_facts() -> None:
    program = markdown_to_metta("# Title\n", doc_id="md1")

    assert program.startswith("(md md1\n")
    assert "\n(md-node md1 document)" in program


def test_markdown_to_atoms_returns_tuple_of_tree_and_facts() -> None:
    atoms = markdown_to_atoms("# Title\n", doc_id="md1")

    assert atoms.startswith("((md md1 ")
    assert "(md-node md1 document)" in atoms
    assert "(md-node md1-h1 heading)" in atoms


def test_markdown_to_facts_returns_index_facts_only() -> None:
    facts = markdown_to_facts("| A | B |\n| - | - |\n| C | D |\n", doc_id="md1")

    assert "(md-node md1-t1 table)" in facts
    assert "(md-cell-at md1-t1 body 1 2 md1-t1-r1-c2)" in facts


def test_parse_markdown_public_api_returns_document() -> None:
    doc = parse_markdown("# Title\n")

    assert len(doc.children) == 1


def test_markdown_to_tree_now_returns_human_md_layer() -> None:
    tree = markdown_to_tree("# Title\n", doc_id="doc1")

    assert tree == '(md doc1\n  (h1 "Title"))'


def test_markdown_to_ir_returns_machine_tree() -> None:
    from goal_chainer.markdown_python.bridge import markdown_to_ir

    ir = markdown_to_ir("# Title\n", doc_id="doc1")

    assert ir.startswith("(md-ir doc1")
    assert "(md-heading 1" in ir


def test_authoring_to_metta_lowers_to_query_facts() -> None:
    from goal_chainer.markdown_python.bridge import authoring_to_metta

    program = authoring_to_metta('''
    (md doc1
      (h1 "Claim table")
      (table (align none right) (head "Gene" "Score") (row BRCA2 1)))
    ''')

    assert program.startswith("(md doc1")
    assert "(md-node doc1-t1 table)" in program
    assert "(md-cell-at doc1-t1 body 1 1 doc1-t1-r1-c1)" in program


def test_markdown_to_metta_end_to_end_shape() -> None:
    source = """# Mary thinks Berlin is nice

- [x] Check claim provenance
- Query BRCA2:

```sparql
SELECT ?gene WHERE { ?gene ?p ?o }
```

| Gene  | Score |
| ----- | ----: |
| BRCA2 | 1     |
| TP53  | 0     |
"""

    program = markdown_to_metta(source, doc_id="md1")

    assert '(h1 "Mary thinks Berlin is nice")' in program
    assert "(md-list unordered 0 tight" in program
    assert '(code sparql "SELECT ?gene WHERE { ?gene ?p ?o }")' in program
    assert "(md-table-align md1-t1 1 right)" in program
    assert "(md-cell-at md1-t1 body 1 1 md1-t1-r1-c1)" in program
    assert '(md-text md1-t1-r1-c1 "BRCA2")' in program
    assert "py-call" not in program


def test_markdown_to_human_tree_outputs_compact_table() -> None:
    tree = markdown_to_tree(
        "| 1 | 2 | 3 | 4 |\n| - | - | - | - |\n| 0 | 0 | 0 | 0 |\n",
        doc_id="doc1",
    )

    assert tree == "\n".join(
        [
            "(md doc1",
            "  (table",
            "    (align none none none none)",
            '    (head "1" "2" "3" "4")',
            '    (row "0" "0" "0" "0")))',
        ]
    )

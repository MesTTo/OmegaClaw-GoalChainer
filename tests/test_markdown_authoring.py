"""Purpose: Mettabase c079c89's tests of its (md ...) authoring syntax, parsed to the Markdown AST
and lowered to facts, run against the copy in goal_chainer.markdown_python;
markdown_library/PROVENANCE.md says what changed."""
# am[verifies a-rt-p3-markdown-vendored-1017@88745b] am[implements a-rt-p3-adopt-upstream-markdown-tests-1017@404f47]

from __future__ import annotations

from goal_chainer.markdown_python.ast import FencedCode, Heading, Paragraph, Table
from goal_chainer.markdown_python.author import parse_authoring_metta


def test_parse_human_md_heading_paragraph_table_and_code() -> None:
    authored = '''
    (md doc1
      (h1 "Claim table")
      (p "Mary thinks Berlin is nice.")
      (table
        (align none right)
        (head "Gene" "Score")
        (row BRCA2 1)
        (row TP53 0))
      (code sparql "SELECT ?gene WHERE { ?gene ?p ?o }"))
    '''

    parsed = parse_authoring_metta(authored)

    assert parsed.doc_id == "doc1"
    assert isinstance(parsed.document.children[0], Heading)
    assert isinstance(parsed.document.children[1], Paragraph)
    assert isinstance(parsed.document.children[2], Table)
    assert isinstance(parsed.document.children[3], FencedCode)
    assert parsed.document.children[2].alignments == ("none", "right")


def test_parse_human_md_metta_actions_use_add_and_eval_forms() -> None:
    parsed = parse_authoring_metta('''
    (md doc1
      (metta
        (add (: gene Symbol))
        (eval (get-type gene))))
    ''')

    block = parsed.document.children[0]

    assert isinstance(block, FencedCode)
    assert block.language == "metta"
    assert [action.kind for action in block.metta_actions] == ["add", "eval"]
    assert [action.atom for action in block.metta_actions] == [
        "(quote (: gene Symbol))",
        "(quote (get-type gene))",
    ]



def test_authoring_example_stays_visually_small_but_queryable() -> None:
    from goal_chainer.markdown_python.bridge import authoring_to_metta

    program = authoring_to_metta('''
    (md doc1
      (h1 "Claim table")
      (p "Mary thinks Berlin is nice.")
      (table
        (align none right)
        (head "Gene" "Score")
        (row BRCA2 1)
        (row TP53 0))
      (code sparql "SELECT ?gene WHERE { ?gene ?p ?o }")
      (metta
        (add (: gene Symbol))
        (eval (get-type gene))))
    ''')

    assert program.startswith("(md doc1\n")
    assert '  (h1 "Claim table")' in program
    assert '    (row "BRCA2" "1")' in program
    assert "(md-cell-at doc1-t1 body 1 1 doc1-t1-r1-c1)" in program
    assert "(md-metta-code doc1-cb2" in program
    assert "py-call" not in program


def test_authoring_ids_are_preserved_and_lowered_to_name_facts() -> None:
    from goal_chainer.markdown_python.bridge import authoring_to_metta
    from goal_chainer.markdown_python.emit import emit_human

    authored = '''
    (md doc1
      (h1 (id title) "Claim table")
      (table (id genes)
        (align none right)
        (head "Gene" "Score")
        (row BRCA2 1)))
    '''

    parsed = parse_authoring_metta(authored)
    heading = parsed.document.children[0]
    table = parsed.document.children[1]

    assert isinstance(heading, Heading)
    assert isinstance(table, Table)
    assert heading.name == "title"
    assert table.name == "genes"
    assert '(h1 (id title) "Claim table")' in emit_human(parsed.document, doc_id="doc1")

    program = authoring_to_metta(authored)

    assert "(md-name doc1-h1 title)" in program
    assert "(md-name doc1-t1 genes)" in program
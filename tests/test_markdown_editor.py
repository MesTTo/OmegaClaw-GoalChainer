"""Purpose: Mettabase c079c89's tests of its Markdown editor, find, edit, update and apply queries
and the editor's sync atoms, run against the copy in goal_chainer.markdown_python;
markdown_library/PROVENANCE.md says what changed."""
# am[verifies a-rt-p3-markdown-vendored-1017@88745b] am[implements a-rt-p3-adopt-upstream-markdown-tests-1017@404f47]

from __future__ import annotations

from goal_chainer.markdown_python.editor import md_query

DOC = '''
(md doc1
  (h1 (id title) "Claim table")
  (table (id genes)
    (align none right)
    (head "Gene" "Score")
    (row BRCA2 1)
    (row TP53 0)))
'''


def test_md_query_find_returns_selection_with_path_value_and_captures() -> None:
    result = md_query(
        DOC,
        '(find (cell (name genes) (where "Gene" "BRCA2") (col "Score")))',
    )

    assert result == (
        '(md-ok ((md-selection doc1 '
        '(cell (name genes) body 1 2) '
        '"1" '
        '((table genes) (section body) (row 1) (col 2) (old "1")))))'
    )


def test_md_query_rejects_out_of_range_cell_selectors() -> None:
    for selector in (
        "(cell (name genes) body 0 1)",
        "(cell (name genes) body 99 1)",
        "(cell (name genes) body 1 99)",
        "(cell (name genes) attic 1 1)",
    ):
        result = md_query(DOC, f"(find {selector})")
        assert result.startswith("(md-error invalid-query"), (selector, result)


def test_md_query_malformed_input_returns_md_error_instead_of_raising() -> None:
    result = md_query(DOC, "(find (cell")
    assert result.startswith("(md-error invalid-query"), result


def test_md_query_edit_overwrites_found_cell() -> None:
    result = md_query(
        DOC,
        '(edit (find (cell (name genes) (where "Gene" "BRCA2") (col "Score"))) "42")',
    )

    assert result.startswith('(md-edit-ok (md doc1\n')
    assert '    (row "BRCA2" "42")' in result
    assert '(md-edit-summary replace-cell (cell (name genes) body 1 2) "1" "42")' in result


def test_md_query_update_uses_selection_captures() -> None:
    result = md_query(
        DOC,
        '(update (find (cell (name genes) body 1 2)) (template (score $old updated-at-row $row)))',
    )

    assert '    (row "BRCA2" "(score 1 updated-at-row 1)")' in result
    assert '(md-edit-summary replace-cell (cell (name genes) body 1 2) "1" "(score 1 updated-at-row 1)")' in result


def test_md_query_edit_rejects_multiple_matches_by_default() -> None:
    result = md_query(DOC, '(edit (find (col (name genes) "Score")) "x")')

    assert result == '(md-edit-error cardinality (expected 1 actual 2))'


def test_md_query_all_edit_updates_multiple_matches() -> None:
    result = md_query(DOC, '(edit (all (find (col (name genes) "Score"))) "x")')

    assert '    (row "BRCA2" "x")' in result
    assert '    (row "TP53" "x")' in result


def test_md_query_apply_binds_selection_and_edits_it() -> None:
    result = md_query(
        DOC,
        '''
        (apply
          ((find-cell $score (cell (name genes) (where "Gene" "BRCA2") (col "Score")))
           (edit $score "42")))
        ''',
    )

    assert '    (row "BRCA2" "42")' in result
    assert '(md-edit-summary replace-cell (cell (name genes) body 1 2) "1" "42")' in result


def test_md_editor_atoms_include_current_doc_and_owned_facts() -> None:
    from goal_chainer.markdown_python.editor import md_editor_atoms

    atoms = md_editor_atoms(DOC)

    assert "(md-ed-current doc1 (md doc1" in atoms
    assert "(md-ed-owned doc1 (md-node doc1 document))" in atoms
    assert "(md-ed-owned doc1 (md-name doc1-t1 genes))" in atoms

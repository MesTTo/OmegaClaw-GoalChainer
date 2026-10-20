"""Purpose: Mettabase c079c89's tests of its Markdown renderer, authored source back to GitHub
Markdown, run against the copy in goal_chainer.markdown_python; markdown_library/PROVENANCE.md
says what changed."""
# am[verifies a-rt-p3-markdown-vendored-1017@88745b] am[implements a-rt-p3-adopt-upstream-markdown-tests-1017@404f47]

from __future__ import annotations

from goal_chainer.markdown_python.bridge import authoring_to_markdown


def test_authoring_to_markdown_renders_gfm_blocks() -> None:
    rendered = authoring_to_markdown('''
    (md doc1
      (h1 (id title) "Claim table")
      (p "Mary thinks Berlin is nice.")
      (table (id genes)
        (align none right)
        (head "Gene" "Score")
        (row BRCA2 1)
        (row TP53 0))
      (code sparql "SELECT ?gene WHERE { ?gene ?p ?o }"))
    ''')

    assert rendered == """# Claim table

Mary thinks Berlin is nice.

| Gene | Score |
| --- | ---: |
| BRCA2 | 1 |
| TP53 | 0 |

```sparql
SELECT ?gene WHERE { ?gene ?p ?o }
```"""


def test_authoring_to_markdown_renders_metta_actions_as_fence() -> None:
    rendered = authoring_to_markdown('''
    (md doc1
      (metta
        (add (: gene Symbol))
        (eval (get-type gene))))
    ''')

    assert rendered == """```metta
(: gene Symbol)
!(get-type gene)
```"""

<!--
Purpose: say where GoalChainer's Markdown library comes from, what was taken and left, what changed
since and under which licence, for the files beside this one, ../markdown_python/,
src/goalchainer_markdown.py and the tests/test_markdown_*.py files taken with them.
am[implements a-rt-p3-markdown-vendored-1017@88745b] am[implements a-rt-p3-drop-hyperbase-enrichment-1017@c4ed37]
am[rests-on c-rt-p3-markdown-copy-equals-upstream-1017@1e7cdb]
-->

# Markdown library provenance

This directory is Mettabase's Markdown library: MeTTa functions that parse Markdown and the
`(md ...)` authoring syntax into MeTTa trees and side facts, render authored source as Markdown,
and query and edit documents. GoalChainer registers this directory as the MeTTa library
`markdown`, so `(library markdown markdown)` resolves to `markdown.metta` here; its thread
specifications parse Markdown through the Python package beside it, `../markdown_python/`.

| | |
|---|---|
| Source | https://github.com/MesTTo/mettabase |
| Commit | `c079c894f3d97421242299f26db76c9de89b2438` |
| Licence | MIT, `LICENSE` here, copied verbatim from the source's root |

Taken:

- `lib/mettabase/markdown.metta` as `markdown.metta`
- `src/mettabase/markdown/`, its eleven modules, as `../markdown_python/`
- the `md_*` py-call wrappers and `_md_source_text` from `src/mettabase/petta/extension.py`, as
  the top-level module `src/goalchainer_markdown.py`
- nine of its tests, `tests/test_markdown_{ast,authoring,bridge,editor,emit,inline,metta_code,parser,render}.py`,
  as the same files under GoalChainer's `tests/`

Left in the source: HyperBase, which the Markdown layer called to parse English text; the tests of
that enrichment, `tests/test_markdown_hyperbase.py` and the editor's test of HyperBase facts; and
`tests/test_markdown_bench.py`, a benchmark.

Every file was byte-identical to its source path when it was taken. GoalChainer changed these
since:

- **No HyperBase.** `normalize.py` sent the text of every English heading, paragraph and table
  cell to HyperBase's parser and added its facts, an `md-hb` link or a `hyperbase-parse-failed`
  diagnostic, unless the caller passed `enrich_hyperbase=False`. That code and the
  `enrich_hyperbase` parameters of `normalize.py`, `emit.py`, `bridge.py` and `editor.py` are gone,
  so no side fact names HyperBase. `markdown.metta` loses `md-space-hyperbase` and
  `md-space-hyperbase-tree`, which read those facts, and `md-facts` no longer documents them;
  `inline.py`'s `extract_plain_text` no longer says it serves enrichment. The tests no longer pass
  `enrich_hyperbase=False`.
- **Imports.** The modules and tests import `goal_chainer.markdown_python` where they imported
  `mettabase.markdown`, and `goal_chainer.sexpr.syntax`, the package's copy of the same
  S-expression module, where they imported `mettabase.core.sexpr`.
- **py-call module.** `markdown.metta` calls `goalchainer_markdown.md_*` where it called
  `mettabase_petta.md_*`. The wrappers import the package at the top of their module, where
  `extension.py`, which serves every Mettabase library, imported it inside each wrapper, and they
  read their arguments with `goalchainer_snars.atom_text`, which is the source's
  `mettabase.ops.fuzzy.atom_text`.
- Each test file opens with a line saying what it tests.

With these changes the package and its wrappers answer as c079c89's Markdown package does with
enrichment off, every answer and every exception equal, over 8,073 Markdown inputs, 12,000
authoring sources and 14,769 editor queries: generated documents and sources, random text, and the
Markdown files of both repositories.

Later changes appear in this repository's history.

"""Purpose: verify the Markdown layer GoalChainer carries is whole and clear of HyperBase: the
py-calls in markdown_library/markdown.metta are exactly the wrappers goalchainer_markdown defines,
the wrappers read engine strings as Mettabase's did, and English headings, paragraphs and table
cells get only md-* side facts without any import of a mettabase module being attempted."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import goalchainer_markdown
import goalchainer_snars

import goal_chainer
from goal_chainer.markdown_python import bridge, editor

LIBRARY = Path(goal_chainer.__file__).resolve().parent / "markdown_library" / "markdown.metta"


# The library calls every wrapper and only wrappers the module defines, so no MeTTa function fails
# only once a program reaches it, and no wrapper is dead.
# am[verifies a-rt-p3-markdown-vendored-1017@88745b]
def test_the_library_calls_exactly_the_wrappers_its_py_call_module_defines() -> None:
    calls = re.findall(r"\(py-call \(([\w.]+)", LIBRARY.read_text(encoding="utf-8"))
    assert {call.rsplit(".", 1)[0] for call in calls} == {"goalchainer_markdown"}
    defined = {
        name for name, value in vars(goalchainer_markdown).items()
        if callable(value) and not name.startswith("_") and value.__module__ == "goalchainer_markdown"
    }
    assert {call.rsplit(".", 1)[1] for call in calls} == defined


# py-call hands a wrapper a string as the engine holds it: quoted, it is read unquoted, and an
# authored source's escaped quotes are decoded, through the one atom_text the SNARS py-calls use.
# am[verifies a-rt-p3-markdown-vendored-1017@88745b] am[verifies a-rt-p3-md-facade-imports-snars-atom-text-1017@282ffb]
def test_wrappers_read_engine_strings_as_mettabase_did() -> None:
    authored = '(md d1 (h1 "Title") (p "Mary thinks Berlin is nice."))'
    assert goalchainer_markdown.md_author_markdown(authored) == "# Title\n\nMary thinks Berlin is nice."
    assert goalchainer_markdown.md_author_markdown('"(md d1 (h1 \\"Quoted\\"))"') == "# Quoted"
    assert goalchainer_markdown.atom_text is goalchainer_snars.atom_text


# The text Mettabase's copy sent to HyperBase, English headings, paragraphs and table cells, gets
# only md-* side facts, and with every mettabase module made unimportable each function still
# answers without a diagnostic, so none of them tries to import one.
# am[verifies a-rt-p3-drop-hyperbase-enrichment-1017@c4ed37]
def test_english_text_gets_only_markdown_facts_and_no_mettabase_import(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "mettabase", None)
    text = "# Mary thinks Berlin is nice\n\nThe cat sat on the mat.\n\n| Who | Says |\n| --- | --- |\n| Ann | Hello there |\n"
    authored = '(md d1 (h1 "Mary thinks Berlin is nice") (p "The cat sat.") (table (id t) (head "Who") (row "Ann")))'
    facts = [*bridge.markdown_to_facts(text), *bridge.authoring_to_facts(authored)]
    answers = [
        *facts,
        bridge.markdown_to_metta(text),
        bridge.markdown_to_atoms(text),
        bridge.authoring_to_metta(authored),
        bridge.authoring_to_atoms(authored),
        editor.md_editor_atoms(text),
        editor.md_editor_atoms(authored),
        goalchainer_markdown.md_atoms(text, "d1"),
        goalchainer_markdown.md_facts(text, "d1"),
        goalchainer_markdown.md_author_atoms(authored),
        goalchainer_markdown.md_author_facts(authored),
        goalchainer_markdown.md_editor_atoms(authored, "d1"),
    ]
    assert facts and all(fact.startswith("(md-") for fact in facts)
    assert [answer for answer in answers if any(mark in answer for mark in ("md-hb", "(hb ", "hyperbase", "md-diagnostic"))] == []

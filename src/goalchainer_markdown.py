"""Purpose: the Python functions GoalChainer's Markdown library calls through py-call: Markdown and
the (md ...) authoring syntax parsed into MeTTa trees and side facts, authored source rendered as
Markdown, and the editor's queries and sync atoms, over the goal_chainer.markdown_python package.

py-call resolves one dot, module.function, so these live in a top-level module, as
goalchainer_snars does; the functions are Mettabase c079c89's md_* wrappers from
mettabase/petta/extension.py with their imports pointed at goal_chainer.markdown_python."""

from __future__ import annotations

from goal_chainer.markdown_python.author import parse_authoring_metta
from goal_chainer.markdown_python.bridge import (
    authoring_to_atoms,
    authoring_to_facts,
    authoring_to_markdown,
    markdown_to_atoms,
    markdown_to_facts,
    markdown_to_ir,
    markdown_to_tree,
)
from goal_chainer.markdown_python.editor import md_editor_atoms as _md_editor_atoms
from goal_chainer.markdown_python.editor import md_query as _md_query
from goal_chainer.markdown_python.emit import emit_human

# The plain-text view of a py-call argument that every md_* wrapper read its arguments with in
# Mettabase, kept in one home with the SNARS py-calls that share it.
# am[implements a-rt-p3-md-facade-imports-snars-atom-text-1017@282ffb] am[rests-on c-rt-p3-atom-text-one-home-1017@638dca]
from goalchainer_snars import atom_text


# Authored (md ...) source with PeTTa's string escapes decoded.
# am[implements a-rt-p3-markdown-vendored-1017@88745b]
def _md_source_text(source) -> str:
    return atom_text(source).replace('\\"', '"')


# The pretty Markdown tree alone.
# am[implements a-rt-p3-markdown-vendored-1017@88745b]
def md_parse(text, doc_id="md1") -> str:
    return markdown_to_tree(atom_text(text), doc_id=atom_text(doc_id))


# One expression holding the pretty tree followed by the side facts.
# am[implements a-rt-p3-markdown-vendored-1017@88745b]
def md_atoms(text, doc_id="md1") -> str:
    return markdown_to_atoms(atom_text(text), doc_id=atom_text(doc_id))


# The side facts as newline-separated MeTTa atoms.
# am[implements a-rt-p3-markdown-vendored-1017@88745b]
def md_facts(text, doc_id="md1") -> str:
    return "\n".join(markdown_to_facts(atom_text(text), doc_id=atom_text(doc_id)))


# The verbose machine tree.
# am[implements a-rt-p3-markdown-vendored-1017@88745b]
def md_ir(text, doc_id="md1") -> str:
    return markdown_to_ir(atom_text(text), doc_id=atom_text(doc_id))


# Authored (md ...) source normalised to its human-writeable tree.
# am[implements a-rt-p3-markdown-vendored-1017@88745b]
def md_author_parse(source) -> str:
    authored = parse_authoring_metta(_md_source_text(source))
    return emit_human(authored.document, doc_id=authored.doc_id)


# Authored source lowered to one expression of its tree and side facts.
# am[implements a-rt-p3-markdown-vendored-1017@88745b]
def md_author_atoms(source) -> str:
    return authoring_to_atoms(_md_source_text(source))


# Authored source lowered to newline-separated side facts.
# am[implements a-rt-p3-markdown-vendored-1017@88745b]
def md_author_facts(source) -> str:
    return "\n".join(authoring_to_facts(_md_source_text(source)))


# Authored source rendered as GitHub-flavoured Markdown, which directive programs return.
# am[implements a-rt-p3-markdown-vendored-1017@88745b]
def md_author_markdown(source) -> str:
    return authoring_to_markdown(_md_source_text(source))


# A pure editor query, find, edit or apply, over a document.
# am[implements a-rt-p3-markdown-vendored-1017@88745b]
def md_query(source, command, doc_id="md1") -> str:
    return _md_query(_md_source_text(source), atom_text(command), doc_id=atom_text(doc_id))


# A document's editor atoms: its tree, its facts and the ownership records a sync removes.
# am[implements a-rt-p3-markdown-vendored-1017@88745b]
def md_editor_atoms(source, doc_id="md1") -> str:
    return _md_editor_atoms(_md_source_text(source), doc_id=atom_text(doc_id))

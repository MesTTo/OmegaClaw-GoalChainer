"""Public Python API for Markdown-to-MeTTa ingestion."""

from __future__ import annotations

from goal_chainer.markdown_python.ast import Document
from goal_chainer.markdown_python.author import AuthoredDocument, parse_authoring_metta
from goal_chainer.markdown_python.emit import emit_facts, emit_human, emit_ir
from goal_chainer.markdown_python.parser import parse_markdown as _parse_markdown


def parse_markdown(text: str) -> Document:
    """Parse Markdown text into the internal Markdown AST."""
    return _parse_markdown(text)


def markdown_to_tree(text: str, *, doc_id: str = "md1") -> str:
    """Return only the human-writeable Markdown MeTTa tree."""
    return emit_human(_parse_markdown(text), doc_id=doc_id)


def markdown_to_ir(text: str, *, doc_id: str = "md1") -> str:
    """Return the verbose machine Markdown IR tree."""
    return emit_ir(_parse_markdown(text), doc_id=doc_id)


def markdown_to_metta(text: str, *, doc_id: str = "md1") -> str:
    """Return human tree followed by side facts and semantic facts."""
    document = _parse_markdown(text)
    return _program(document, doc_id=doc_id)


def markdown_to_facts(text: str, *, doc_id: str = "md1") -> list[str]:
    """Return side facts for Markdown text."""
    return emit_facts(_parse_markdown(text), doc_id=doc_id)


def markdown_to_atoms(text: str, *, doc_id: str = "md1") -> str:
    """Return a MeTTa expression whose items are the human tree followed by side facts."""
    document = _parse_markdown(text)
    tree = _single_line_metta(emit_human(document, doc_id=doc_id))
    facts = emit_facts(document, doc_id=doc_id)
    return "(" + " ".join([tree, *facts]) + ")"


def authoring_to_metta(source: str) -> str:
    """Lower hand-written `(md ...)` source to human tree plus facts."""
    authored = parse_authoring_metta(source)
    return _authored_program(authored)


def authoring_to_facts(source: str) -> list[str]:
    """Lower hand-written `(md ...)` source to side facts."""
    authored = parse_authoring_metta(source)
    return emit_facts(authored.document, doc_id=authored.doc_id)


def authoring_to_atoms(source: str) -> str:
    """Lower hand-written `(md ...)` source to a tuple of human tree plus facts."""
    authored = parse_authoring_metta(source)
    tree = _single_line_metta(emit_human(authored.document, doc_id=authored.doc_id))
    facts = emit_facts(authored.document, doc_id=authored.doc_id)
    return "(" + " ".join([tree, *facts]) + ")"


def authoring_to_markdown(source: str) -> str:
    """Render hand-written `(md ...)` source as canonical GFM Markdown."""
    from goal_chainer.markdown_python.render import render_markdown

    authored = parse_authoring_metta(source)
    return render_markdown(authored.document)


def _authored_program(authored: AuthoredDocument) -> str:
    return _program(authored.document, doc_id=authored.doc_id)


def _program(document: Document, *, doc_id: str) -> str:
    return emit_human(document, doc_id=doc_id) + "\n\n" + "\n".join(emit_facts(document, doc_id=doc_id))


def _single_line_metta(text: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    pending_space = False
    for char in text:
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            if pending_space and out and out[-1] != "(":
                out.append(" ")
            pending_space = False
            in_string = True
            out.append(char)
        elif char.isspace():
            pending_space = True
        else:
            if pending_space and out and out[-1] != "(" and char != ")":
                out.append(" ")
            pending_space = False
            out.append(char)
    return "".join(out)

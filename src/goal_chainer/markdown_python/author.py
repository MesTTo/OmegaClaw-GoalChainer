"""Hand-writable `(md ...)` authoring syntax for Markdown-to-MeTTa."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from goal_chainer.sexpr.syntax import Atom, StringLiteral, Symbol, emit, parse
from goal_chainer.markdown_python.ast import (
    Document,
    FencedCode,
    Heading,
    MettaAction,
    Paragraph,
    Table,
    TableCell,
    Text,
)
from goal_chainer.markdown_python.metta_code import _quote_normalized


@dataclass(frozen=True, slots=True)
class AuthoredDocument:
    """Parsed human authoring document and its requested document id."""

    doc_id: str
    document: Document


def parse_authoring_metta(source: str) -> AuthoredDocument:
    """Parse a hand-authored `(md doc-id ...)` source expression."""
    root = parse(source)
    if not isinstance(root, list) or len(root) < 2 or _symbol(root[0]) != "md":
        raise ValueError("authoring source must start with (md <doc-id> ...)")
    doc_id = _atom_text(root[1])
    blocks = [_block(node) for node in root[2:]]
    return AuthoredDocument(doc_id=doc_id, document=Document(blocks, source=source.strip()))


def _split_id(items: list[Atom]) -> tuple[str | None, list[Atom]]:
    if not items:
        return None, items
    first = items[0]
    if (
        isinstance(first, list)
        and len(first) == 2
        and _symbol(first[0]) == "id"
    ):
        return _atom_text(first[1]), items[1:]
    return None, items


def _block(node: Atom):
    if not isinstance(node, list) or not node:
        raise ValueError(f"unsupported md block: {emit(node)}")
    head = _symbol(node[0])
    body_name, body = _split_id(list(node[1:]))
    if head.startswith("h") and head[1:].isdigit():
        level = int(head[1:])
        if not 1 <= level <= 6:
            raise ValueError(f"heading level out of range: {head}")
        return Heading(level, [Text(_join_text(body))], source=emit(node), name=body_name)
    if head == "p":
        return Paragraph([Text(_join_text(node[1:]))], source=emit(node))
    if head == "table":
        return _table(node[1:])
    if head == "code":
        if len(node) != 3:
            raise ValueError("(code <language> <text>) expects exactly two arguments")
        language = _atom_text(node[1])
        return FencedCode(
            language=language,
            text=_atom_text(node[2]),
            info=language,
            source=emit(node),
        )
    if head == "metta":
        return _metta_block(node[1:])
    raise ValueError(f"unsupported md block head: {head}")


def _table(items: Iterable[Atom]) -> Table:
    name, body = _split_id(list(items))
    alignments: list[str] = []
    header: list[TableCell] = []
    rows: list[list[TableCell]] = []
    source_items: list[str] = []
    for item in body:
        if not isinstance(item, list) or not item:
            raise ValueError(f"unsupported table item: {emit(item)}")
        source_items.append(emit(item))
        head = _symbol(item[0])
        if head == "align":
            alignments = [_atom_text(value) for value in item[1:]]
        elif head == "head":
            header = [TableCell([Text(_atom_text(value))], source=emit(value)) for value in item[1:]]
        elif head == "row":
            rows.append([TableCell([Text(_atom_text(value))], source=emit(value)) for value in item[1:]])
        else:
            raise ValueError(f"unsupported table item head: {head}")
    if not header:
        raise ValueError("table requires a (head ...) row")
    if not alignments:
        alignments = ["none"] * len(header)
    source_prefix = f"(table (id {name})" if name is not None else "(table"
    return Table(
        alignments=alignments,
        header=header,
        rows=rows,
        source=source_prefix + " " + " ".join(source_items) + ")",
        name=name,
    )


def _metta_block(actions: Iterable[Atom]) -> FencedCode:
    metta_actions: list[MettaAction] = []
    text_lines: list[str] = []
    source_lines: list[str] = []
    for index, action in enumerate(actions):
        if not isinstance(action, list) or len(action) != 2:
            raise ValueError("metta actions must be (add <atom>) or (eval <atom>)")
        kind = _symbol(action[0])
        if kind not in {"add", "eval"}:
            raise ValueError("metta actions must be (add <atom>) or (eval <atom>)")
        atom_text = emit(action[1])
        text_lines.append(("!" if kind == "eval" else "") + atom_text)
        source_lines.append(emit(action))
        metta_actions.append(MettaAction(kind, index, _quote_normalized(atom_text)))
    return FencedCode(
        language="metta",
        text="\n".join(text_lines),
        info="metta",
        metta_actions=metta_actions,
        source="(metta " + " ".join(source_lines) + ")",
    )


def _join_text(items: Iterable[Atom]) -> str:
    return " ".join(_atom_text(item) for item in items)


def _atom_text(atom: Atom) -> str:
    if isinstance(atom, StringLiteral):
        return atom.value
    if isinstance(atom, Symbol):
        return atom.text
    return emit(atom)


def _symbol(atom: Atom) -> str:
    return atom.text if isinstance(atom, Symbol) else ""

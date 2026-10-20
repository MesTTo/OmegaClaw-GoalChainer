"""Normalize Markdown AST nodes into stable IDs, paths, text, and fact records."""

from __future__ import annotations

from dataclasses import dataclass

from goal_chainer.sexpr.syntax import metta_string
from goal_chainer.markdown_python.ast import (
    Block,
    Document,
    FencedCode,
    Heading,
    ListBlock,
    Paragraph,
    Table,
    TableCell,
)
from goal_chainer.markdown_python.emit import emit_block_expr, emit_inline_expr
from goal_chainer.markdown_python.inline import extract_plain_text


@dataclass(frozen=True, slots=True)
class NormalizedDocument:
    """Side facts emitted for one Markdown document."""

    facts: tuple[str, ...]


def normalize_document(
    document: Document,
    *,
    doc_id: str = "md1",
) -> NormalizedDocument:
    """Create fixed-arity side facts for a parsed Markdown document."""
    facts: list[str] = [f"(md-node {doc_id} document)"]
    counters: dict[str, int] = {}
    for index, block in enumerate(document.children):
        block_id = _block_id(doc_id, block, counters)
        facts.append(f"(md-child {doc_id} {index} {block_id})")
        facts.extend(_block_facts(block, block_id, (index,), counters))
    return NormalizedDocument(tuple(facts))


def _block_id(doc_id: str, block: Block, counters: dict[str, int]) -> str:
    prefix = {
        Heading: "h",
        Paragraph: "p",
        ListBlock: "l",
        Table: "t",
        FencedCode: "cb",
    }.get(type(block), "b")
    counters[prefix] = counters.get(prefix, 0) + 1
    return f"{doc_id}-{prefix}{counters[prefix]}"


def _block_facts(
    block: Block,
    block_id: str,
    path: tuple[int | str, ...],
    counters: dict[str, int],
) -> list[str]:
    facts = [f"(md-node {block_id} {_node_kind(block)})", f"(md-path {block_id} {_path_expr(path)})"]
    name = getattr(block, "name", None)
    if name is not None:
        facts.append(f"(md-name {block_id} {name})")
    facts.append(f"(md-tree {block_id} {emit_block_expr(block)})")
    source = getattr(block, "source", "")
    if source:
        facts.append(f"(md-source {block_id} {metta_string(source)})")
    if isinstance(block, (Heading, Paragraph)):
        text = extract_plain_text(block.children)
        if text:
            facts.append(f"(md-text {block_id} {metta_string(text)})")
    elif isinstance(block, ListBlock):
        facts.append(f"(md-list-kind {block_id} {block.kind})")
        facts.append(f"(md-list-tight {block_id} {'tight' if block.tight else 'loose'})")
        for item_index, item in enumerate(block.items):
            item_id = f"{block_id}-i{item_index + 1}"
            facts.append(f"(md-child {block_id} {item_index} {item_id})")
            facts.append(f"(md-node {item_id} item)")
            facts.append(f"(md-path {item_id} {_path_expr((*path, item_index))})")
            facts.append(f"(md-task {item_id} {item.task})")
            for child_index, child in enumerate(item.children):
                child_id = f"{item_id}-p{child_index + 1}"
                facts.append(f"(md-child {item_id} {child_index} {child_id})")
                facts.extend(_block_facts(child, child_id, (*path, item_index, child_index), counters))
    elif isinstance(block, Table):
        facts.extend(_table_facts(block, block_id))
    elif isinstance(block, FencedCode):
        if block.language == "metta" and block.metta_actions:
            entries = " ".join(
                f"(md-{action.kind} {action.index} {action.atom})" for action in block.metta_actions
            )
            facts.append(f"(md-metta-code {block_id} (md-quoted-atoms {entries}))")
        if block.diagnostic:
            facts.append(f"(md-diagnostic {block_id} metta-parse-failed {metta_string(block.diagnostic)})")
    return facts


def _table_facts(table: Table, table_id: str) -> list[str]:
    facts: list[str] = []
    for index, alignment in enumerate(table.alignments):
        facts.append(f"(md-table-align {table_id} {index} {alignment})")
    facts.append(f"(md-row-at {table_id} head 0 {table_id}-head)")
    for col, cell in enumerate(table.header, start=1):
        cell_id = f"{table_id}-h{col}"
        facts.extend(_cell_facts(table_id, cell_id, "head", 0, col, cell))
    for row_index, row in enumerate(table.rows, start=1):
        row_id = f"{table_id}-r{row_index}"
        facts.append(f"(md-row-at {table_id} body {row_index} {row_id})")
        for col, cell in enumerate(row, start=1):
            cell_id = f"{row_id}-c{col}"
            facts.extend(_cell_facts(table_id, cell_id, "body", row_index, col, cell))
    return facts


def _cell_facts(
    table_id: str,
    cell_id: str,
    section: str,
    row: int,
    col: int,
    cell: TableCell,
) -> list[str]:
    facts = [
        f"(md-node {cell_id} cell)",
        f"(md-cell-at {table_id} {section} {row} {col} {cell_id})",
        f"(md-cell-value {cell_id} {emit_inline_expr(cell.children)})",
    ]
    text = extract_plain_text(cell.children)
    # Always emit md-text so a valid empty cell stays distinguishable from a
    # missing cell through the md-space-* helpers, which join through md-text.
    facts.append(f"(md-text {cell_id} {metta_string(text)})")
    return facts


def _node_kind(block: Block) -> str:
    if isinstance(block, Heading):
        return "heading"
    if isinstance(block, Paragraph):
        return "paragraph"
    if isinstance(block, ListBlock):
        return "list"
    if isinstance(block, Table):
        return "table"
    if isinstance(block, FencedCode):
        return "code"
    return "block"


def _path_expr(path: tuple[int | str, ...]) -> str:
    return "(md-path " + " ".join(str(part) for part in path) + ")"

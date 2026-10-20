"""Render internal Markdown AST nodes back to GFM Markdown."""

from __future__ import annotations

from goal_chainer.markdown_python.ast import Block, Document, FencedCode, Heading, Paragraph, Table
from goal_chainer.markdown_python.inline import extract_plain_text


def render_markdown(document: Document) -> str:
    """Render a parsed/authored Markdown document as canonical GFM Markdown."""
    blocks = [_render_block(block) for block in document.children]
    return "\n\n".join(block for block in blocks if block).rstrip()


def _render_block(block: Block) -> str:
    if isinstance(block, Heading):
        return f"{'#' * block.level} {extract_plain_text(block.children)}"
    if isinstance(block, Paragraph):
        return extract_plain_text(block.children)
    if isinstance(block, Table):
        return _render_table(block)
    if isinstance(block, FencedCode):
        info = block.info or block.language
        return f"```{info}\n{block.text}\n```"
    return getattr(block, "source", "")


def _render_table(table: Table) -> str:
    lines = [
        "| " + " | ".join(_cell_text(cell) for cell in table.header) + " |",
        "| " + " | ".join(_alignment_marker(alignment) for alignment in table.alignments) + " |",
    ]
    for row in table.rows:
        lines.append("| " + " | ".join(_cell_text(cell) for cell in row) + " |")
    return "\n".join(lines)


def _cell_text(cell) -> str:
    return extract_plain_text(cell.children).replace("|", "\\|")


def _alignment_marker(alignment: str) -> str:
    if alignment == "left":
        return ":---"
    if alignment == "right":
        return "---:"
    if alignment == "center":
        return ":---:"
    return "---"

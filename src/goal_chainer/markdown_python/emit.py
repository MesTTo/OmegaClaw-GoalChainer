"""Emit Markdown AST nodes as MeTTa data."""

from __future__ import annotations

from collections.abc import Iterable

from goal_chainer.sexpr.syntax import metta_string
from goal_chainer.markdown_python.ast import (
    Autolink,
    Block,
    BlockQuote,
    Code,
    Document,
    Emphasis,
    FencedCode,
    HardBreak,
    Heading,
    HtmlBlock,
    HtmlInline,
    Image,
    IndentedCode,
    Inline,
    Link,
    LinkReference,
    ListBlock,
    ListItem,
    Paragraph,
    RawInline,
    RawMarkdown,
    SoftBreak,
    Strike,
    Strong,
    Table,
    TableCell,
    Text,
    ThematicBreak,
)


def emit_pretty(document: Document, *, doc_id: str = "md1") -> str:
    """Emit the human-facing Markdown tree."""
    return emit_human(document, doc_id=doc_id)


def emit_human(document: Document, *, doc_id: str = "md1") -> str:
    """Emit hand-writable `(md ...)` syntax."""
    lines = [f"(md {doc_id}"]
    for block in document.children:
        lines.extend(_indent(_emit_human_block(block), 2))
    lines[-1] += ")"
    return "\n".join(lines)


def emit_ir(document: Document, *, doc_id: str = "md1") -> str:
    """Emit verbose machine tree used by side facts and debugging."""
    lines = [f"(md-ir {doc_id}", "  (md-blocks"]
    for block in document.children:
        lines.extend(_indent(_emit_block(block), 4))
    lines[-1] += "))"
    return "\n".join(lines)


def emit_program(document: Document, *, doc_id: str = "md1") -> str:
    """Emit pretty tree followed by side facts."""
    return emit_pretty(document, doc_id=doc_id) + "\n\n" + "\n".join(emit_facts(document, doc_id=doc_id))


def emit_facts(document: Document, *, doc_id: str = "md1") -> list[str]:
    """Emit stable side facts for a Markdown document."""
    from goal_chainer.markdown_python.normalize import normalize_document

    return list(normalize_document(document, doc_id=doc_id).facts)


def emit_block_expr(block: Block) -> str:
    """Emit one block as single-line machine IR for side facts."""
    return " ".join(part.strip() for part in _emit_block(block))


def emit_inline_expr(children: Iterable[Inline]) -> str:
    """Emit inline children as an `(md-inlines ...)` expression."""
    return _emit_inline_expr(children)



def _emit_human_block(block: Block) -> list[str]:
    if isinstance(block, Heading):
        head = f"h{block.level}"
        name = f"(id {block.name}) " if block.name is not None else ""
        return [f"({head} {name}{metta_string(_inline_plain(block.children))})"]
    if isinstance(block, Paragraph):
        return [f"(p {metta_string(_inline_plain(block.children))})"]
    if isinstance(block, Table):
        first = f"(table (id {block.name})" if block.name is not None else "(table"
        lines = [first, f"  (align {' '.join(block.alignments)})"]
        lines.append("  (head " + " ".join(_cell_text(cell) for cell in block.header) + ")")
        for row in block.rows:
            lines.append("  (row " + " ".join(_cell_text(cell) for cell in row) + ")")
        lines[-1] += ")"
        return lines
    if isinstance(block, FencedCode) and block.language == "metta" and block.metta_actions:
        lines = ["(metta"]
        for action in block.metta_actions:
            atom = action.atom.removeprefix("(quote ").removesuffix(")")
            lines.append(f"  ({action.kind} {atom})")
        lines[-1] += ")"
        return lines
    if isinstance(block, FencedCode):
        return [f"(code {block.language or 'none'} {metta_string(block.text)})"]
    return [f"(raw {metta_string(emit_block_expr(block))})"]


def _cell_text(cell: TableCell) -> str:
    return metta_string(_inline_plain(cell.children))


def _inline_plain(children: Iterable[Inline]) -> str:
    from goal_chainer.markdown_python.inline import extract_plain_text

    return extract_plain_text(children)
def _emit_block(block: Block) -> list[str]:
    if isinstance(block, Heading):
        return [f"(md-heading {block.level}", *_indent(_emit_inlines(block.children), 2, close=")")]
    if isinstance(block, Paragraph):
        return ["(md-paragraph", *_indent(_emit_inlines(block.children), 2, close=")")]
    if isinstance(block, BlockQuote):
        lines = ["(md-blockquote", "  (md-blocks"]
        for child in block.children:
            lines.extend(_indent(_emit_block(child), 4))
        lines[-1] = lines[-1] + "))"
        return lines
    if isinstance(block, ListBlock):
        tight = "tight" if block.tight else "loose"
        lines = [f"(md-list {block.kind} {block.start} {tight}", "  (md-items"]
        for item in block.items:
            lines.extend(_indent(_emit_item(item), 4))
        lines[-1] = lines[-1] + "))"
        return lines
    if isinstance(block, ThematicBreak):
        return ["(md-thematic-break)"]
    if isinstance(block, IndentedCode):
        return [f"(md-code indented {metta_string(block.text)})"]
    if isinstance(block, FencedCode):
        lang = block.language or "none"
        return [f"(md-code {lang} {metta_string(block.text)})"]
    if isinstance(block, HtmlBlock):
        return [f"(md-html {metta_string(block.text)})"]
    if isinstance(block, LinkReference):
        return [
            f"(md-reference {metta_string(block.label)} "
            f"{metta_string(block.destination)} {metta_string(block.title)})"
        ]
    if isinstance(block, Table):
        return _emit_table(block)
    if isinstance(block, RawMarkdown):
        return [f"(md-raw {block.kind} {metta_string(block.text)})"]
    raise TypeError(f"unsupported block: {block!r}")


def _emit_item(item: ListItem) -> list[str]:
    lines = [f"(md-item {item.task}", "  (md-blocks"]
    for child in item.children:
        lines.extend(_indent(_emit_block(child), 4))
    lines[-1] = lines[-1] + "))"
    return lines


def _emit_table(table: Table) -> list[str]:
    lines = ["(md-table", f"  (md-align {' '.join(table.alignments)})", "  (md-head"]
    lines.extend(_indent(_emit_row(table.header), 4, close=")"))
    lines.append("  (md-body")
    for row in table.rows:
        lines.extend(_indent(_emit_row(row), 4))
    lines[-1] = lines[-1] + "))"
    return lines


def _emit_row(cells: Iterable[TableCell], close: str = "") -> list[str]:
    lines = ["(md-row"]
    for cell in cells:
        lines.append(f"  {_emit_cell(cell)}")
    lines[-1] = lines[-1] + ")" + close
    return lines


def _emit_cell(cell: TableCell) -> str:
    return f"(md-cell {_emit_inline_expr(cell.children)})"


def _emit_inlines(children: Iterable[Inline]) -> list[str]:
    rendered = [_emit_inline(child) for child in children]
    if not rendered:
        return ["(md-inlines)"]
    lines = ["(md-inlines", *("  " + item for item in rendered)]
    lines[-1] = lines[-1] + ")"
    return lines


def _emit_inline_expr(children: Iterable[Inline]) -> str:
    rendered = " ".join(_emit_inline(child) for child in children)
    return f"(md-inlines {rendered})" if rendered else "(md-inlines)"


def _emit_inline(node: Inline) -> str:
    if isinstance(node, Text):
        return f"(md-txt {metta_string(node.value)})"
    if isinstance(node, Code):
        return f"(md-code-span {metta_string(node.value)})"
    if isinstance(node, Emphasis):
        return f"(md-em {_emit_inline_expr(node.children)})"
    if isinstance(node, Strong):
        return f"(md-strong {_emit_inline_expr(node.children)})"
    if isinstance(node, Strike):
        return f"(md-strike {_emit_inline_expr(node.children)})"
    if isinstance(node, Link):
        return (
            f"(md-link {_emit_inline_expr(node.children)} "
            f"{metta_string(node.destination)} {metta_string(node.title)})"
        )
    if isinstance(node, Image):
        return (
            f"(md-image {_emit_inline_expr(node.children)} "
            f"{metta_string(node.destination)} {metta_string(node.title)})"
        )
    if isinstance(node, Autolink):
        return f"(md-autolink {metta_string(node.destination)})"
    if isinstance(node, HtmlInline):
        return f"(md-html-inline {metta_string(node.text)})"
    if isinstance(node, SoftBreak):
        return "(md-softbreak)"
    if isinstance(node, HardBreak):
        return "(md-hardbreak)"
    if isinstance(node, RawInline):
        return f"(md-raw-inline {node.kind} {metta_string(node.text)})"
    raise TypeError(f"unsupported inline: {node!r}")


def _indent(lines: list[str], spaces: int, close: str = "") -> list[str]:
    prefix = " " * spaces
    result = [prefix + line for line in lines]
    if close:
        result[-1] = result[-1] + close
    return result

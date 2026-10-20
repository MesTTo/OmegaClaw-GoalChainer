"""Small GFM-oriented block parser for Markdown-to-MeTTa ingestion."""

from __future__ import annotations

import re

from goal_chainer.markdown_python.ast import (
    Document,
    FencedCode,
    Heading,
    ListBlock,
    ListItem,
    Paragraph,
    Table,
    TableCell,
    ThematicBreak,
)
from goal_chainer.markdown_python.inline import parse_inlines
from goal_chainer.markdown_python.metta_code import parse_metta_fence

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)(?:\s+#+\s*)?$")
_FENCE_RE = re.compile(r"^(```+|~~~+)\s*([^`]*)\s*$")
_ULIST_RE = re.compile(r"^\s*([-+*])\s+(.*)$")
_OLIST_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_THEMATIC_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")


def parse_markdown(text: str) -> Document:
    """Parse the implemented Markdown subset into an AST."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "�")
    lines = normalized.split("\n")
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if match := _HEADING_RE.match(line):
            blocks.append(Heading(len(match.group(1)), parse_inlines(match.group(2).strip()), source=line))
            i += 1
            continue
        if _THEMATIC_RE.match(line):
            blocks.append(ThematicBreak(source=line))
            i += 1
            continue
        if fence := _FENCE_RE.match(line):
            block, i = _parse_fence(lines, i, fence.group(1), fence.group(2).strip())
            blocks.append(block)
            continue
        if _is_table_start(lines, i):
            block, i = _parse_table(lines, i)
            blocks.append(block)
            continue
        if _ULIST_RE.match(line) or _OLIST_RE.match(line):
            block, i = _parse_list(lines, i)
            blocks.append(block)
            continue
        paragraph, i = _parse_paragraph(lines, i)
        blocks.append(paragraph)
    return Document(blocks, source=normalized)


def _parse_fence(lines: list[str], start: int, fence: str, info: str) -> tuple[FencedCode, int]:
    body: list[str] = []
    i = start + 1
    closer = fence[0] * len(fence)
    while i < len(lines):
        if lines[i].startswith(closer):
            i += 1
            break
        body.append(lines[i])
        i += 1
    text = "\n".join(body)
    language = info.split()[0].casefold() if info else "none"
    if language == "metta":
        parsed = parse_metta_fence(text)
        return (
            FencedCode(
                language="metta",
                text=text,
                info=info,
                fence=fence,
                metta_actions=parsed.actions,
                diagnostic=parsed.diagnostic,
                source="\n".join(lines[start:i]),
            ),
            i,
        )
    return FencedCode(language=language, text=text, info=info, fence=fence, source="\n".join(lines[start:i])), i


def _parse_list(lines: list[str], start: int) -> tuple[ListBlock, int]:
    items: list[ListItem] = []
    first = lines[start]
    ordered_match = _OLIST_RE.match(first)
    kind = "ordered" if ordered_match else "unordered"
    start_number = int(ordered_match.group(1)) if ordered_match else 0
    i = start
    while i < len(lines):
        line = lines[i]
        match = _OLIST_RE.match(line) if kind == "ordered" else _ULIST_RE.match(line)
        if not match:
            break
        content = match.group(2)
        task = "no-task"
        if kind == "unordered" and content.startswith("[x] "):
            task = "checked"
            content = content[4:]
        elif kind == "unordered" and content.startswith("[ ] "):
            task = "unchecked"
            content = content[4:]
        items.append(
            ListItem(
                [Paragraph(parse_inlines(content), source=content)],
                task=task,
                marker=match.group(1),
                source=line,
            )
        )
        i += 1
    return ListBlock(kind=kind, start=start_number, tight=True, items=items, source="\n".join(lines[start:i])), i


def _is_table_start(lines: list[str], index: int) -> bool:
    return index + 1 < len(lines) and "|" in lines[index] and _parse_delimiter(lines[index + 1]) is not None


def _parse_table(lines: list[str], start: int) -> tuple[Table, int]:
    header = _split_table_row(lines[start])
    alignments = _parse_delimiter(lines[start + 1]) or []
    width = len(alignments)
    header_cells = [TableCell(parse_inlines(value), source=value) for value in _fit_width(header, width)]
    rows = []
    i = start + 2
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
        row = _fit_width(_split_table_row(lines[i]), width)
        rows.append([TableCell(parse_inlines(value), source=value) for value in row])
        i += 1
    return Table(alignments=alignments, header=header_cells, rows=rows, source="\n".join(lines[start:i])), i


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    cells: list[str] = []
    buf: list[str] = []
    escaped = False
    for char in stripped:
        if escaped:
            buf.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(buf).strip())
            buf.clear()
        else:
            buf.append(char)
    cells.append("".join(buf).strip())
    return cells


def _parse_delimiter(line: str) -> list[str] | None:
    cells = _split_table_row(line)
    if not cells:
        return None
    alignments: list[str] = []
    for cell in cells:
        stripped = cell.strip()
        if not re.fullmatch(r":?-{1,}:?", stripped):
            return None
        left = stripped.startswith(":")
        right = stripped.endswith(":")
        alignments.append("center" if left and right else "left" if left else "right" if right else "none")
    return alignments


def _fit_width(cells: list[str], width: int) -> list[str]:
    return (cells + [""] * width)[:width]


def _parse_paragraph(lines: list[str], start: int) -> tuple[Paragraph, int]:
    parts: list[str] = []
    i = start
    while i < len(lines) and lines[i].strip():
        if i != start and (_HEADING_RE.match(lines[i]) or _FENCE_RE.match(lines[i]) or _is_table_start(lines, i)):
            break
        if i != start and (_ULIST_RE.match(lines[i]) or _OLIST_RE.match(lines[i]) or _THEMATIC_RE.match(lines[i])):
            break
        parts.append(lines[i].strip())
        i += 1
    text = "\n".join(parts)
    return Paragraph(parse_inlines(text), source=text), i

"""Conservative inline Markdown parser for the Markdown-to-MeTTa subset."""

from __future__ import annotations

import html
import re
from collections.abc import Iterable

from goal_chainer.markdown_python.ast import (
    Code,
    Emphasis,
    HardBreak,
    HtmlInline,
    Image,
    Inline,
    Link,
    SoftBreak,
    Strike,
    Strong,
    Text,
)

_LINK_RE = re.compile(r'!?\[([^\]]*)\]\(([^\s)]+)(?:\s+"([^"]*)")?\)')
_AUTO_RE = re.compile(r"<((?:https?://|mailto:)[^>]+)>")
_HTML_RE = re.compile(r"</?[A-Za-z][^>]*>")


def parse_inlines(text: str) -> tuple[Inline, ...]:
    """Parse implemented GFM inline constructs, preserving unknown syntax as text."""
    nodes: list[Inline] = []
    i = 0
    buf: list[str] = []

    def flush() -> None:
        if buf:
            value = html.unescape("".join(buf))
            if value:
                nodes.append(Text(value))
            buf.clear()

    while i < len(text):
        if text.startswith("  \n", i) or text.startswith("\\\n", i):
            flush()
            nodes.append(HardBreak())
            i += 3 if text.startswith("  \n", i) else 2
            continue
        if text[i] == "\n":
            flush()
            nodes.append(SoftBreak())
            i += 1
            continue
        if text[i] == "`":
            end = text.find("`", i + 1)
            if end != -1:
                flush()
                nodes.append(Code(text[i + 1 : end]))
                i = end + 1
                continue
        if text.startswith("**", i):
            end = text.find("**", i + 2)
            if end != -1:
                flush()
                nodes.append(Strong(parse_inlines(text[i + 2 : end])))
                i = end + 2
                continue
        if text.startswith("~~", i):
            end = text.find("~~", i + 2)
            if end != -1:
                flush()
                nodes.append(Strike(parse_inlines(text[i + 2 : end])))
                i = end + 2
                continue
        if text[i] == "*":
            end = text.find("*", i + 1)
            if end != -1:
                flush()
                nodes.append(Emphasis(parse_inlines(text[i + 1 : end])))
                i = end + 1
                continue
        link = _LINK_RE.match(text, i)
        if link:
            flush()
            marker = link.group(0)
            label = link.group(1)
            dest = link.group(2)
            title = link.group(3) or ""
            children = parse_inlines(label)
            if marker.startswith("!"):
                nodes.append(Image(children, dest, title))
            else:
                nodes.append(Link(children, dest, title))
            i = link.end()
            continue
        auto = _AUTO_RE.match(text, i)
        if auto:
            flush()
            nodes.append(Link((Text(auto.group(1)),), auto.group(1), ""))
            i = auto.end()
            continue
        tag = _HTML_RE.match(text, i)
        if tag:
            flush()
            nodes.append(HtmlInline(tag.group(0)))
            i = tag.end()
            continue
        if text[i] == "\\" and i + 1 < len(text):
            buf.append(text[i + 1])
            i += 2
            continue
        buf.append(text[i])
        i += 1

    flush()
    return tuple(_merge_text(nodes))


def extract_plain_text(nodes: Iterable[Inline]) -> str:
    """Extract natural-language text, the words of every node but code, whitespace collapsed."""
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, Text):
            parts.append(node.value)
        elif isinstance(node, (Emphasis, Strong, Strike, Link, Image)):
            parts.append(extract_plain_text(node.children))
        elif isinstance(node, (SoftBreak, HardBreak)):
            parts.append(" ")
    return " ".join("".join(parts).split())


def _merge_text(nodes: Iterable[Inline]) -> list[Inline]:
    merged: list[Inline] = []
    for node in nodes:
        if isinstance(node, Text) and merged and isinstance(merged[-1], Text):
            merged[-1] = Text(merged[-1].value + node.value)
        else:
            merged.append(node)
    return merged

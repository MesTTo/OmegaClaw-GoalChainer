"""Internal AST nodes for Markdown-to-MeTTa ingestion."""
# ruff: noqa: D107 - constructors only normalize iterable fields on immutable nodes.

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal, TypeAlias, TypeVar

Alignment: TypeAlias = Literal["left", "right", "center", "none"]
TaskState: TypeAlias = Literal["checked", "unchecked", "no-task"]
ListKind: TypeAlias = Literal["ordered", "unordered"]

T = TypeVar("T")


def _tuple(values: Iterable[T]) -> tuple[T, ...]:
    return tuple(values)


@dataclass(frozen=True, slots=True)
class Text:
    """Plain inline text."""

    value: str


@dataclass(frozen=True, slots=True)
class Code:
    """Inline code span."""

    value: str


@dataclass(frozen=True, slots=True)
class Emphasis:
    """Emphasized inline content."""

    children: tuple[Inline, ...]

    def __init__(self, children: Iterable[Inline]):
        object.__setattr__(self, "children", _tuple(children))


@dataclass(frozen=True, slots=True)
class Strong:
    """Strong inline content."""

    children: tuple[Inline, ...]

    def __init__(self, children: Iterable[Inline]):
        object.__setattr__(self, "children", _tuple(children))


@dataclass(frozen=True, slots=True)
class Strike:
    """Strikethrough inline content."""

    children: tuple[Inline, ...]

    def __init__(self, children: Iterable[Inline]):
        object.__setattr__(self, "children", _tuple(children))


@dataclass(frozen=True, slots=True)
class Link:
    """Markdown link."""

    children: tuple[Inline, ...]
    destination: str
    title: str = ""

    def __init__(self, children: Iterable[Inline], destination: str, title: str = ""):
        object.__setattr__(self, "children", _tuple(children))
        object.__setattr__(self, "destination", destination)
        object.__setattr__(self, "title", title)


@dataclass(frozen=True, slots=True)
class Image:
    """Markdown image."""

    children: tuple[Inline, ...]
    destination: str
    title: str = ""

    def __init__(self, children: Iterable[Inline], destination: str, title: str = ""):
        object.__setattr__(self, "children", _tuple(children))
        object.__setattr__(self, "destination", destination)
        object.__setattr__(self, "title", title)


@dataclass(frozen=True, slots=True)
class Autolink:
    """Autolink inline destination."""

    destination: str


@dataclass(frozen=True, slots=True)
class HtmlInline:
    """Inline HTML fragment."""

    text: str


@dataclass(frozen=True, slots=True)
class SoftBreak:
    """Soft line break."""


@dataclass(frozen=True, slots=True)
class HardBreak:
    """Hard line break."""


@dataclass(frozen=True, slots=True)
class RawInline:
    """Opaque inline Markdown fragment."""

    kind: str
    text: str


Inline: TypeAlias = (
    Text
    | Code
    | Emphasis
    | Strong
    | Strike
    | Link
    | Image
    | Autolink
    | HtmlInline
    | SoftBreak
    | HardBreak
    | RawInline
)


@dataclass(frozen=True, slots=True)
class Paragraph:
    """Paragraph block."""

    children: tuple[Inline, ...]
    source: str = ""

    def __init__(self, children: Iterable[Inline], source: str = ""):
        object.__setattr__(self, "children", _tuple(children))
        object.__setattr__(self, "source", source)


@dataclass(frozen=True, slots=True)
class Heading:
    """ATX heading block."""

    level: int
    children: tuple[Inline, ...]
    source: str = ""
    name: str | None = None

    def __init__(
        self,
        level: int,
        children: Iterable[Inline],
        source: str = "",
        name: str | None = None,
    ):
        object.__setattr__(self, "level", level)
        object.__setattr__(self, "children", _tuple(children))
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "name", name)


@dataclass(frozen=True, slots=True)
class BlockQuote:
    """Block quote containing block children."""

    children: tuple[Block, ...]
    source: str = ""

    def __init__(self, children: Iterable[Block], source: str = ""):
        object.__setattr__(self, "children", _tuple(children))
        object.__setattr__(self, "source", source)


@dataclass(frozen=True, slots=True)
class ListItem:
    """Markdown list item."""

    children: tuple[Block, ...]
    task: TaskState = "no-task"
    marker: str = ""
    source: str = ""

    def __init__(
        self,
        children: Iterable[Block],
        task: TaskState = "no-task",
        marker: str = "",
        source: str = "",
    ):
        object.__setattr__(self, "children", _tuple(children))
        object.__setattr__(self, "task", task)
        object.__setattr__(self, "marker", marker)
        object.__setattr__(self, "source", source)


@dataclass(frozen=True, slots=True)
class ListBlock:
    """Ordered or unordered Markdown list."""

    kind: ListKind
    start: int
    tight: bool
    items: tuple[ListItem, ...]
    source: str = ""

    def __init__(
        self,
        kind: ListKind,
        start: int,
        tight: bool,
        items: Iterable[ListItem],
        source: str = "",
    ):
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "tight", tight)
        object.__setattr__(self, "items", _tuple(items))
        object.__setattr__(self, "source", source)


@dataclass(frozen=True, slots=True)
class ThematicBreak:
    """Thematic break block."""

    source: str = ""


@dataclass(frozen=True, slots=True)
class IndentedCode:
    """Indented code block."""

    text: str
    source: str = ""


@dataclass(frozen=True, slots=True)
class MettaAction:
    """Quoted MeTTa source action extracted from a metta fence."""

    kind: Literal["add", "eval"]
    index: int
    atom: str


@dataclass(frozen=True, slots=True)
class FencedCode:
    """Fenced code block."""

    language: str
    text: str
    info: str = ""
    fence: str = "```"
    metta_actions: tuple[MettaAction, ...] = field(default_factory=tuple)
    diagnostic: str = ""
    source: str = ""

    def __init__(
        self,
        language: str,
        text: str,
        info: str = "",
        fence: str = "```",
        metta_actions: Iterable[MettaAction] = (),
        diagnostic: str = "",
        source: str = "",
    ):
        object.__setattr__(self, "language", language)
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "info", info)
        object.__setattr__(self, "fence", fence)
        object.__setattr__(self, "metta_actions", _tuple(metta_actions))
        object.__setattr__(self, "diagnostic", diagnostic)
        object.__setattr__(self, "source", source)


@dataclass(frozen=True, slots=True)
class HtmlBlock:
    """HTML block preserved as opaque Markdown content."""

    text: str
    source: str = ""


@dataclass(frozen=True, slots=True)
class LinkReference:
    """Link reference definition."""

    label: str
    destination: str
    title: str = ""
    source: str = ""


@dataclass(frozen=True, slots=True)
class TableCell:
    """GFM table cell."""

    children: tuple[Inline, ...]
    source: str = ""

    def __init__(self, children: Iterable[Inline], source: str = ""):
        object.__setattr__(self, "children", _tuple(children))
        object.__setattr__(self, "source", source)


@dataclass(frozen=True, slots=True)
class Table:
    """GFM table block."""

    alignments: tuple[Alignment, ...]
    header: tuple[TableCell, ...]
    rows: tuple[tuple[TableCell, ...], ...]
    source: str = ""
    name: str | None = None

    def __init__(
        self,
        alignments: Iterable[Alignment],
        header: Iterable[TableCell],
        rows: Iterable[Iterable[TableCell]],
        source: str = "",
        name: str | None = None,
    ):
        object.__setattr__(self, "alignments", _tuple(alignments))
        object.__setattr__(self, "header", _tuple(header))
        object.__setattr__(self, "rows", tuple(tuple(row) for row in rows))
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "name", name)


@dataclass(frozen=True, slots=True)
class RawMarkdown:
    """Opaque block-level Markdown fragment."""

    kind: str
    text: str
    source: str = ""


Block: TypeAlias = (
    Paragraph
    | Heading
    | BlockQuote
    | ListBlock
    | ThematicBreak
    | IndentedCode
    | FencedCode
    | HtmlBlock
    | LinkReference
    | Table
    | RawMarkdown
)


@dataclass(frozen=True, slots=True)
class Document:
    """Parsed Markdown document root."""

    children: tuple[Block, ...]
    source: str = ""

    def __init__(self, children: Iterable[Block], source: str = ""):
        object.__setattr__(self, "children", _tuple(children))
        object.__setattr__(self, "source", source)

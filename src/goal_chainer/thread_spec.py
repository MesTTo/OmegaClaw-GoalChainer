"""Parse ThreadKeeper specifications through Mettabase MeTTa Markdown."""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any

from .snars_program import SexprCodec
from .snars_runtime import SnarsRuntime
from .thread_models import (
    ParsedThreadMarkdown,
    ThreadFact,
    ThreadSpecificationError,
)

MAX_THREAD_SPEC_BYTES = 1024 * 1024
_ALLOWED_FACT_HEADS = frozenset(
    {
        "thread-budget",
        "thread-depends",
        "thread-merge-policy",
        "thread-mcp-profile",
        "thread-not-before",
        "thread-owner",
        "thread-role",
        "thread-spec-v1",
        "thread-supervision",
        "thread-task",
        "thread-title",
        "thread-workflow",
        "thread-workflow-step",
    }
)


def parse_thread_markdown(
    source: str,
    *,
    runtime: SnarsRuntime | None = None,
    source_path: str | None = None,
) -> ParsedThreadMarkdown:
    """Return normalized, non-executable orchestration facts from Markdown."""

    if not isinstance(source, str):
        raise ThreadSpecificationError("Thread specification must be text.")
    encoded = source.encode("utf-8")
    if len(encoded) > MAX_THREAD_SPEC_BYTES:
        raise ThreadSpecificationError(
            "Thread specification exceeds the size limit.",
            details={
                "size_bytes": len(encoded),
                "limit_bytes": MAX_THREAD_SPEC_BYTES,
            },
        )
    if "\0" in source:
        raise ThreadSpecificationError(
            "Thread specification must not contain null bytes."
        )

    engine = runtime or SnarsRuntime(require_text_ingestion=False)
    atoms_source = _mettabase_markdown_atoms(engine, source)
    from .thread_runtime import ThreadRuntime

    result = ThreadRuntime(engine).parse_markdown_atoms(
        atoms_source,
        source_path=source_path,
    ).value
    if not isinstance(result, dict):
        raise ThreadSpecificationError(
            "Mettabase returned the wrong Markdown result shape."
        )
    sources = result.get("sources")
    if not isinstance(sources, dict) or not all(
        isinstance(block, str) and isinstance(block_source, str)
        for block, block_source in sources.items()
    ):
        raise ThreadSpecificationError(
            "Mettabase returned malformed Markdown block sources."
        )
    block_lines = _block_source_lines(source, sources)
    actions = result.get("actions")
    if not isinstance(actions, tuple):
        raise ThreadSpecificationError("Mettabase returned malformed Markdown actions.")
    diagnostics = result.get("diagnostics")
    if not isinstance(diagnostics, tuple):
        raise ThreadSpecificationError(
            "Mettabase returned malformed Markdown diagnostics."
        )
    semantic_blocks: set[object] = set()
    for value in (*actions, *diagnostics):
        if isinstance(value, dict) and isinstance(value.get("block"), str):
            semantic_blocks.add(value["block"])
    _require_closed_metta_blocks(
        sources,
        block_lines=block_lines,
        semantic_blocks=semantic_blocks,
    )
    if diagnostics:
        first = diagnostics[0]
        block = first.get("block")
        line = _diagnostic_line(
            first.get("message"),
            block_lines.get(block),
        )
        raise ThreadSpecificationError(
            f"Invalid MeTTa Markdown at line {line}: "
            f"{first.get('message', 'unknown parse error')}.",
            details={"diagnostics": diagnostics},
        )

    codec = SexprCodec(engine)
    facts = tuple(
        _normalized_fact(action, codec, block_lines=block_lines) for action in actions
    )
    if not facts:
        raise ThreadSpecificationError(
            "Thread specification contains no semantic MeTTa facts."
        )
    digest_source = "\n".join(sorted(fact.atom for fact in facts)) + "\n"
    semantic_digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
    return ParsedThreadMarkdown(
        facts=facts,
        semantic_digest=semantic_digest,
        source_path=source_path,
    )


def read_thread_markdown(
    path: str | os.PathLike[str],
    *,
    runtime: SnarsRuntime | None = None,
) -> ParsedThreadMarkdown:
    """Read a regular Markdown file without following symbolic links."""

    source, source_path = read_thread_markdown_source(path)
    return parse_thread_markdown(
        source,
        runtime=runtime,
        source_path=str(source_path),
    )


def read_thread_markdown_source(
    path: str | os.PathLike[str],
) -> tuple[str, Path]:
    """Read UTF-8 Markdown source without following symbolic links."""

    source_path = Path(path).expanduser().absolute()
    if source_path.suffix.casefold() not in {".md", ".markdown"}:
        raise ThreadSpecificationError(
            "Thread specification path must end in .md or .markdown.",
            details={"path": str(source_path)},
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source_path, flags)
    except OSError as exc:
        raise ThreadSpecificationError(
            "Thread specification could not be opened safely.",
            details={"path": str(source_path), "error": str(exc)},
        ) from exc
    with os.fdopen(descriptor, "rb") as handle:
        data = handle.read(MAX_THREAD_SPEC_BYTES + 1)
    if len(data) > MAX_THREAD_SPEC_BYTES:
        raise ThreadSpecificationError(
            "Thread specification exceeds the size limit.",
            details={
                "path": str(source_path),
                "limit_bytes": MAX_THREAD_SPEC_BYTES,
            },
        )
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ThreadSpecificationError(
            "Thread specification must be valid UTF-8.",
            details={"path": str(source_path), "error": str(exc)},
        ) from exc
    return source, source_path


def _normalized_fact(
    action: Any,
    codec: SexprCodec,
    *,
    block_lines: dict[str, int],
) -> ThreadFact:
    if not isinstance(action, dict):
        raise ThreadSpecificationError("Mettabase Markdown action is malformed.")
    kind = action.get("kind")
    relative_line = action.get("line")
    block = action.get("block")
    block_line = block_lines.get(block) if isinstance(block, str) else None
    line = (
        block_line + relative_line
        if isinstance(relative_line, int) and block_line is not None
        else relative_line
    )
    source = action.get("atom")
    if kind != "add":
        raise ThreadSpecificationError(
            f"MeTTa evaluation actions are forbidden at line {line}.",
            details={"line": line, "kind": kind},
        )
    if not isinstance(source, str):
        raise ThreadSpecificationError(
            f"MeTTa fact is malformed at line {line}.",
            details={"line": line},
        )
    try:
        quoted = codec.parse(source)
    except Exception as exc:
        raise ThreadSpecificationError(
            f"MeTTa fact is malformed at line {line}.",
            details={"line": line, "error": str(exc)},
        ) from exc
    if (
        not isinstance(quoted, list)
        or len(quoted) != 2
        or not isinstance(quoted[0], codec.Symbol)
        or quoted[0].text != "quote"
        or not isinstance(quoted[1], list)
        or not quoted[1]
        or not isinstance(quoted[1][0], codec.Symbol)
    ):
        raise ThreadSpecificationError(
            f"MeTTa semantic entry must be one data expression at line {line}.",
            details={"line": line},
        )
    head = quoted[1][0].text
    if head not in _ALLOWED_FACT_HEADS:
        raise ThreadSpecificationError(
            f"MeTTa fact head {head} is not allowed at line {line}.",
            details={"line": line, "head": head},
        )
    if isinstance(line, bool) or not isinstance(line, int) or line <= 0:
        raise ThreadSpecificationError(
            "Mettabase returned an invalid source line.",
            details={"line": line},
        )
    return ThreadFact(atom=codec.emit(quoted[1]), line=line)


def _mettabase_markdown_atoms(runtime: SnarsRuntime, source: str) -> str:
    source_root = str(runtime.diagnostics.mettabase_dir / "src")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    try:
        from mettabase.markdown.bridge import markdown_to_atoms

        atoms = markdown_to_atoms(source, doc_id="thread-spec")
    except Exception as exc:
        raise ThreadSpecificationError(
            "Mettabase could not parse the Markdown specification.",
            details={
                "path": source_root,
                "error": f"{type(exc).__name__}: {exc}",
            },
        ) from exc
    if not isinstance(atoms, str) or not atoms:
        raise ThreadSpecificationError(
            "Mettabase returned no Markdown atoms."
        )
    codec = SexprCodec(runtime)
    try:
        document_atoms = codec.parse(atoms)
        projected = _project_markdown_atoms(document_atoms, codec)
    except ThreadSpecificationError:
        raise
    except Exception as exc:
        raise ThreadSpecificationError(
            "Mettabase returned malformed Markdown atoms.",
            details={"error": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return codec.emit(projected)


def _project_markdown_atoms(document_atoms: Any, codec: SexprCodec) -> list[Any]:
    if not isinstance(document_atoms, list) or not document_atoms:
        raise ThreadSpecificationError(
            "Mettabase Markdown atom tuple is malformed."
        )
    projected = []
    for row in document_atoms[1:]:
        if (
            not isinstance(row, list)
            or not row
            or not isinstance(row[0], codec.Symbol)
        ):
            continue
        head = row[0].text
        if head in {"md-source", "md-diagnostic"}:
            projected.append(row)
            continue
        if head != "md-metta-code" or len(row) != 3:
            continue
        block = row[1]
        quoted = row[2]
        if (
            not isinstance(quoted, list)
            or not quoted
            or not isinstance(quoted[0], codec.Symbol)
            or quoted[0].text != "md-quoted-atoms"
        ):
            raise ThreadSpecificationError(
                "Mettabase MeTTa code block is malformed."
            )
        for entry in quoted[1:]:
            if (
                not isinstance(entry, list)
                or len(entry) != 3
                or not isinstance(entry[0], codec.Symbol)
                or entry[0].text not in {"md-add", "md-eval"}
                or not isinstance(entry[1], codec.Symbol)
                or not entry[1].text.isdecimal()
            ):
                raise ThreadSpecificationError(
                    "Mettabase MeTTa action is malformed."
                )
            projected.append(
                codec.expression(
                    "md-action",
                    block,
                    codec.symbol(
                        "add" if entry[0].text == "md-add" else "eval"
                    ),
                    codec.symbol(entry[1].text),
                    codec.string(codec.emit(entry[2])),
                )
            )
    return projected


def _block_source_lines(
    source: str,
    sources: dict[str, str],
) -> dict[str, int]:
    positions: dict[str, int] = {}
    cursor = 0
    for block, block_source in sources.items():
        position = source.find(block_source, cursor)
        if position < 0:
            position = source.find(block_source)
        if position < 0:
            raise ThreadSpecificationError(
                "Mettabase Markdown block could not be located in its source.",
                details={"block": block},
            )
        positions[block] = source.count("\n", 0, position) + 1
        cursor = position + len(block_source)
    return positions


def _diagnostic_line(message: object, block_line: int | None) -> int:
    if block_line is None or not isinstance(message, str):
        return 1
    match = re.match(r"line (\d+):", message)
    relative = int(match.group(1)) if match else 0
    return block_line + relative + 1


def _require_closed_metta_blocks(
    sources: dict[str, str],
    *,
    block_lines: dict[str, int],
    semantic_blocks: set[object],
) -> None:
    for block in semantic_blocks:
        if not isinstance(block, str):
            continue
        lines = sources[block].splitlines()
        opener = lines[0].lstrip() if lines else ""
        fence = re.match(r"(`{3,}|~{3,})", opener)
        closed = (
            fence is not None
            and len(lines) >= 2
            and lines[-1].lstrip().startswith(fence.group(1))
        )
        if not closed:
            raise ThreadSpecificationError(
                f"Invalid MeTTa Markdown at line {block_lines[block]}: "
                "unclosed metta code fence.",
                details={"block": block},
            )


__all__ = [
    "MAX_THREAD_SPEC_BYTES",
    "parse_thread_markdown",
    "read_thread_markdown",
    "read_thread_markdown_source",
]

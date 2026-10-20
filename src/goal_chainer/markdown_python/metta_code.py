"""Parse `metta` fenced code into quoted source actions."""

from __future__ import annotations

from dataclasses import dataclass

from goal_chainer.sexpr.syntax import emit, parse
from goal_chainer.markdown_python.ast import MettaAction


@dataclass(frozen=True, slots=True)
class ParsedMettaFence:
    """Quoted actions and diagnostic extracted from one metta fence."""

    actions: tuple[MettaAction, ...]
    diagnostic: str = ""


def parse_metta_fence(text: str) -> ParsedMettaFence:
    """Parse line-oriented MeTTa code fence content into quoted add/eval actions."""
    actions: list[MettaAction] = []
    for index, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        kind = "eval" if line.startswith("!") else "add"
        atom_text = line[1:].strip() if kind == "eval" else line
        try:
            quoted = _quote_normalized(atom_text)
        except ValueError as exc:
            return ParsedMettaFence(tuple(actions), f"line {index}: {exc}")
        actions.append(MettaAction(kind, index, quoted))
    return ParsedMettaFence(tuple(actions), "")


def _quote_normalized(atom_text: str) -> str:
    parsed = parse(atom_text)
    emitted = emit(parsed)
    if isinstance(parsed, list) and len(parsed) == 2 and emit(parsed[0]) == "quote":
        return emitted
    return f"(quote {emitted})"

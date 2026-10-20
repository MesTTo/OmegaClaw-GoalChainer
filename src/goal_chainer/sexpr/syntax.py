"""Purpose: parse and emit the small MeTTa S-expression trees GoalChainer writes and reads, with every
string literal written and read exactly as pymetta's reader reads it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class Symbol:
    """Symbol atom in a small MeTTa S-expression tree."""

    text: str


@dataclass(frozen=True, slots=True)
class StringLiteral:
    """String literal atom in a small MeTTa S-expression tree."""

    value: str


Atom: TypeAlias = Symbol | StringLiteral | list["Atom"]

__all__ = [
    "Atom",
    "StringLiteral",
    "Symbol",
    "atom_text",
    "emit",
    "emit_list",
    "metta_string",
    "parse",
    "recursive_list",
]


# pymetta's reader decodes only \" \\ \n \r \t and \', drops the backslash of any other escape, and
# reads every other character as itself, the C0 controls included; json.dumps wrote \b, \f and
# \u00XX for those controls, which pymetta reads as the letters b, f and uXXXX
# (c-dr-codec-escapes-diverge-pymetta-1018). So a literal escapes the backslash and the quote, and
# tab, newline and return, which keeps an emitted form on one line, and writes the rest raw.
# am[implements a-dr-codec-pymetta-strings-1018@7fc480] am[rests-on c-dr-codec-escapes-diverge-pymetta-1018@af4800]
_ESCAPED = str.maketrans({"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"})
_DECODED = {'"': '"', "\\": "\\", "n": "\n", "r": "\r", "t": "\t", "'": "'"}


# Time: one pass over the value's characters.
# am[implements a-dr-codec-pymetta-strings-1018@7fc480]
def metta_string(value: str) -> str:
    """Quote a Python string as a MeTTa string literal that pymetta reads back as the same string."""
    return '"' + value.translate(_ESCAPED) + '"'


def atom_text(atom) -> str:
    """Render an atom as MeTTa source text.

    Symbols return their bare text; strings and StringLiterals return a
    *quoted* MeTTa string literal (escaped, with surrounding quotes);
    expressions emit recursively. Use ``StringLiteral.value`` when the
    unquoted payload is needed.
    """
    if isinstance(atom, Symbol):
        return atom.text
    if isinstance(atom, StringLiteral):
        return metta_string(atom.value)
    if isinstance(atom, str):
        return metta_string(atom)
    return emit(atom)


def emit(node) -> str:
    """Render an atom tree back to MeTTa text."""
    if isinstance(node, Symbol):
        return node.text
    if isinstance(node, StringLiteral):
        return metta_string(node.value)
    if isinstance(node, str):
        return metta_string(node)
    if isinstance(node, list | tuple):
        return emit_list(node)
    return str(node)


def emit_list(items: Sequence) -> str:
    """Render a sequence of atoms as a MeTTa expression."""
    if not items:
        return "()"
    return "(" + " ".join(emit(item) for item in items) + ")"


def recursive_list(items: Sequence[Atom]) -> Atom:
    """Render atoms into the PeTTa ::/() recursive list shape."""
    result: Atom = []
    for item in reversed(items):
        result = [Symbol("::"), item, result]
    return result


def parse(text: str) -> Atom:
    """Parse one MeTTa atom or expression from text."""
    tokens = _tokenize(text.strip())
    if not tokens:
        return []
    node, index = _parse_at(tokens, 0)
    if index == len(tokens):
        return node

    nodes = [node]
    while index < len(tokens):
        node, index = _parse_at(tokens, index)
        nodes.append(node)
    return nodes


def _parse_at(tokens: list[Atom | str], index: int) -> tuple[Atom, int]:
    token = tokens[index]
    if token == "(":
        index += 1
        items: list[Atom] = []
        while index < len(tokens) and tokens[index] != ")":
            item, index = _parse_at(tokens, index)
            items.append(item)
        if index >= len(tokens):
            raise ValueError("unclosed expression")
        return items, index + 1
    if token == ")":
        raise ValueError("unexpected close paren")
    return token, index + 1


# A semicolon ends a symbol and comments through the next newline, unless inside a string.
# Time: one pass over N characters. Space: at most N token characters.
# am[implements a-integrate-vocab-pure-read-1019@745f98]
def _tokenize(text: str) -> list[Atom | str]:
    tokens: list[Atom | str] = []
    index = 0
    end = len(text)
    while index < end:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char == ";":
            newline = text.find("\n", index)
            index = end if newline < 0 else newline + 1
            continue
        if char == "(" or char == ")":
            tokens.append(char)
            index += 1
            continue
        if char == '"':
            value, index = _read_string(text, index + 1)
            tokens.append(StringLiteral(value))
            continue

        start = index
        while index < end and not text[index].isspace() and text[index] not in "();":
            index += 1
        tokens.append(Symbol(text[start:index]))
    return tokens


# A string literal from just after its opening quote, read as pymetta reads it: each of pymetta's
# escapes decoded, the backslash of any other dropped, and every other character, a raw control
# character or a raw newline included, kept as itself. Answers the string and the index after its
# closing quote.
# Time: one pass over the literal's characters.
# am[implements a-dr-codec-pymetta-strings-1018@7fc480] am[rests-on c-dr-codec-escapes-diverge-pymetta-1018@af4800]
def _read_string(text: str, index: int) -> tuple[str, int]:
    chars: list[str] = []
    end = len(text)
    while index < end:
        char = text[index]
        if char == "\\" and index + 1 < end:
            following = text[index + 1]
            chars.append(_DECODED.get(following, following))
            index += 2
            continue
        if char == '"':
            return "".join(chars), index + 1
        chars.append(char)
        index += 1
    raise ValueError("unclosed string")

"""Purpose: compare SNARS protocol records from two runs or two engines up to what no run controls:
the protocol's own wall-clock field, the names engines give fresh variables, and the spelling of
booleans, reading each record as an S-expression tree so quoted text is compared as written."""

from __future__ import annotations

import re
from collections.abc import Iterable

PREFIX = "(goalchainer-snars-v1"

_TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))', re.S)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_BOOLEANS = {"true": "True", "false": "False"}


# A record's tree: a nested list per expression and a str per token, a quoted string kept with its
# quotes, so "(clock 1)" stays one token and is never read as an expression.
# Time: linear in the text's length.
# am[implements a-rt-snars-clock-normalize-1017@908992]
def tree(text: str) -> list | str:
    stack: list[list] = [[]]
    position = 0
    while position < len(text):
        match = _TOKEN.match(text, position)
        if match is None:
            if text[position:].strip():
                raise ValueError(f"not an S-expression at offset {position}: {text[position:position + 40]!r}")
            break
        opening, closing, string, atom = match.groups()
        if opening:
            stack.append([])
        elif closing:
            if len(stack) == 1:
                raise ValueError(f"unbalanced ')' at offset {match.start()}")
            finished = stack.pop()
            stack[-1].append(finished)
        else:
            stack[-1].append(string or atom)
        position = match.end()
    if len(stack) != 1 or len(stack[0]) != 1:
        raise ValueError("an S-expression record has one balanced top-level form")
    return stack[0][0]


# The (operation, payload head) pairs whose payload carries the protocol's clock: in the protocol
# source, a (goalchainer-snars-v1 OP STATUS PAYLOAD) expression whose PAYLOAD has the direct child
# (clock (sn clock)). Today that is only the inspect record's (inspection ...).
# Time: linear in the protocol's size.
# am[implements a-rt-snars-clock-normalize-1017@908992] am[rests-on c-rt-snars-clock-walltime-1017@a40166]
def clock_fields(protocol: str) -> frozenset[tuple[str, str]]:
    found: set[tuple[str, str]] = set()

    def walk(node: list | str) -> None:
        if not isinstance(node, list):
            return
        if len(node) >= 4 and node[0] == "goalchainer-snars-v1" and isinstance(node[3], list) and node[3]:
            if any(child == ["clock", ["sn", "clock"]] for child in node[3][1:]):
                found.add((node[1], node[3][0]))
        for child in node:
            walk(child)

    for form in _top_level(protocol):
        walk(form)
    return frozenset(found)


# The protocol's top-level forms as trees, its comments dropped and strings kept.
# Time: linear in the source's length.
# am[implements a-rt-snars-clock-normalize-1017@908992]
def _top_level(source: str) -> Iterable[list | str]:
    text = re.sub(r'("(?:[^"\\]|\\.)*")|;[^\n]*', lambda match: match.group(1) or "", source)
    depth, start = 0, None
    for index, character in enumerate(_masked_strings(text)):
        if character == "(":
            if depth == 0:
                start = index
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0 and start is not None:
                yield tree(text[start:index + 1])


# The text with every string literal's characters masked, so parentheses inside strings do not
# count toward a form's depth. Time: linear in the text's length.
# am[implements a-rt-snars-clock-normalize-1017@908992]
def _masked_strings(text: str) -> str:
    return re.sub(r'"(?:[^"\\]|\\.)*"', lambda match: '"' + "_" * (len(match.group(0)) - 2) + '"', text)


# One record's canonical text: its protocol clock field masked, its variables renamed in order of
# first occurrence, its bare booleans spelled True and False, and single spaces between tokens.
# Time: linear in the record's length.
# am[implements a-rt-snars-clock-normalize-1017@908992] am[rests-on c-rt-boolean-spelling-only-1017@4633c5]
def canonical(record: str, clocks: frozenset[tuple[str, str]]) -> str:
    root = tree(record)
    names: dict[str, str] = {}
    if (isinstance(root, list) and len(root) >= 4 and root[0] == "goalchainer-snars-v1"
            and isinstance(root[3], list) and root[3] and (root[1], root[3][0]) in clocks):
        root[3] = [root[3][0]] + [
            ["clock", "_"] if isinstance(child, list) and len(child) == 2 and child[0] == "clock"
            and isinstance(child[1], str) and _NUMBER.fullmatch(child[1]) else child
            for child in root[3][1:]
        ]

    def emit(node: list | str) -> str:
        if isinstance(node, list):
            return "(" + " ".join(emit(child) for child in node) + ")"
        if node.startswith("$"):
            return names.setdefault(node, f"$v{len(names)}")
        return _BOOLEANS.get(node, node)

    return emit(root)


# The protocol records among a run's printed lines, in order.
# am[implements a-rt-snars-differential-tests-1017@7b8936]
def records(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines() if line.startswith(PREFIX)]


# am[implements a-rt-snars-differential-tests-1017@7b8936]
def equal(expected: list[str], actual: list[str], clocks: frozenset[tuple[str, str]]) -> bool:
    return [canonical(record, clocks) for record in expected] == [canonical(record, clocks) for record in actual]

"""Purpose: read MeTTa program text into its top-level forms, each with its exact text, where it
starts and whether a ! makes it a directive, honouring string literals, their escapes and ;
comments, and naming the kind and place of any text that breaks the grammar."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

__all__ = ["MettaTextError", "TopLevelForm", "top_level_forms"]


# am[implements a-rt-metta-forms-shared-1017@db105c]
@dataclass(frozen=True, slots=True)
class TopLevelForm:
    """One top-level form. `text` is the exact source from `index` to the form's closing ), so
    a directive's text begins with its ! and whatever whitespace and comments follow it."""

    text: str
    index: int
    directive: bool


# am[implements a-rt-metta-forms-shared-1017@db105c]
class MettaTextError(ValueError):
    """Text a reader cannot split into forms. `kind` is "stray" for text outside every form,
    "unbalanced )" or "unbalanced ("; `index` is where it starts, and `character` the character
    there, a ! when the stray text or the unclosed form is a directive."""

    def __init__(self, kind: str, index: int, character: str) -> None:
        super().__init__(f"{kind} at character {index}: {character!r}")
        self.kind = kind
        self.index = index
        self.character = character


# A ! makes the next form a directive across any whitespace and ; comments, as pymetta reads
# "! (f)" and "! ; note\n(f)"; anything else after it, as in !foo, is stray text at the !. A
# string literal inside a form hides parentheses and ; from the scan, and a backslash escapes
# the character after it inside one; outside every form a string literal is stray text, as in
# (a) "note" (b). A ; outside a string comments to the end of the line.
# Time: one pass over the characters of the text.
# am[implements a-rt-metta-forms-shared-1017@db105c]
def top_level_forms(text: str) -> Iterator[TopLevelForm]:
    """Yield each top-level form in order. Raises MettaTextError for unbalanced parentheses and
    for any text outside a form other than whitespace, comments and a directive's !."""

    depth = 0
    start = 0
    directive = False
    pending = -1
    in_string = False
    escaped = False
    in_comment = False
    for index, character in enumerate(text):
        if in_comment:
            in_comment = character != "\n"
            continue
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        # A ! waits for its form only at depth 0, until the ( that opens it.
        if pending >= 0 and character != "(":
            if character == ";":
                in_comment = True
            elif not character.isspace():
                raise MettaTextError("stray", pending, "!")
            continue
        if character == '"':
            if depth == 0:
                raise MettaTextError("stray", index, character)
            in_string = True
        elif character == ";":
            in_comment = True
        elif character == "(":
            if depth == 0:
                start, directive, pending = (pending, True, -1) if pending >= 0 else (index, False, -1)
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                yield TopLevelForm(text[start : index + 1], start, directive)
            elif depth < 0:
                raise MettaTextError("unbalanced )", index, character)
        elif depth == 0 and character == "!":
            pending = index
        elif depth == 0 and not character.isspace():
            raise MettaTextError("stray", index, character)
    if depth:
        raise MettaTextError("unbalanced (", start, text[start])
    if pending >= 0:
        raise MettaTextError("stray", pending, "!")

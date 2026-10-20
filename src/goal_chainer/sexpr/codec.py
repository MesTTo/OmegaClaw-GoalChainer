"""Purpose: GoalChainer's MeTTa text codec: parse and emit through goal_chainer.sexpr.syntax, and build
symbols, string literals and expressions only from values MeTTa reads back as the same atoms."""

from __future__ import annotations

import re
from typing import Any

from ..errors import InvalidInputError
from . import syntax

# A symbol is one token: no whitespace, parenthesis, quote or comment start.
_SYMBOL_RE = re.compile(r"^[^\s()\";]+$")


# One home for reading and writing MeTTa text, the S-expression module SNARS's helpers run, so the
# protocol readers compare against the Symbol and StringLiteral classes the helpers emit.
# am[implements a-rt-sexpr-codec-packaged-1017@608f80] am[implements a-rt-pymetta-deontic-1016@61a4b6]
# am[implements a-rt-rb-codec-1018@e3e552] am[rests-on c-rt-codec-decision-kept-1018@5b65d4]
class SexprCodec:
    """GoalChainer's MeTTa text codec, over goal_chainer.sexpr.syntax's parser and emitter."""

    Symbol = syntax.Symbol
    StringLiteral = syntax.StringLiteral

    def parse(self, source: str) -> Any:
        if not isinstance(source, str):
            raise InvalidInputError("S-expression source must be text.")
        try:
            return syntax.parse(source)
        except (TypeError, ValueError) as exc:
            raise InvalidInputError(
                "Invalid MeTTa S-expression.",
                details={"error": str(exc)},
            ) from exc

    def emit(self, atom: Any) -> str:
        return syntax.emit(atom)

    def symbol(self, value: str) -> Any:
        if not isinstance(value, str) or not _SYMBOL_RE.fullmatch(value):
            raise InvalidInputError(
                "MeTTa symbol contains whitespace, syntax, or is empty.",
                details={"symbol": value},
            )
        return self.Symbol(value)

    def string(self, value: str) -> Any:
        if not isinstance(value, str):
            raise InvalidInputError("MeTTa string literal value must be text.")
        return self.StringLiteral(value)

    def expression(self, head: str, *arguments: Any) -> list[Any]:
        return [self.symbol(head), *arguments]


__all__ = ["SexprCodec"]

"""English rendering helpers for typed HyperBase MeTTa atoms."""

from __future__ import annotations

__all__ = ["hb_en", "hb_en_result"]


class _Quoted(str):
    pass


class _Parser:
    def __init__(self, text: str) -> None:
        self._text = text
        self._position = 0

    def parse(self):
        self._skip_space()
        if self._position >= len(self._text):
            return None
        value = self._parse_expr()
        if value is None:
            return None
        self._skip_space()
        if self._position != len(self._text):
            return None
        return value

    def _parse_expr(self):
        self._skip_space()
        if self._position >= len(self._text):
            return None
        char = self._text[self._position]
        if char == "(":
            return self._parse_list()
        if char == '"':
            return self._parse_string()
        return self._parse_symbol()

    def _parse_list(self):
        self._position += 1
        values = []
        while True:
            self._skip_space()
            if self._position >= len(self._text):
                return None
            if self._text[self._position] == ")":
                self._position += 1
                return values
            value = self._parse_expr()
            if value is None:
                return None
            values.append(value)

    def _parse_string(self):
        self._position += 1
        chars: list[str] = []
        while self._position < len(self._text):
            char = self._text[self._position]
            self._position += 1
            if char == '"':
                return _Quoted("".join(chars))
            if char == "\\":
                if self._position >= len(self._text):
                    return None
                escaped = self._text[self._position]
                self._position += 1
                if escaped == "n":
                    chars.append("\n")
                elif escaped == "t":
                    chars.append("\t")
                else:
                    chars.append(escaped)
            else:
                chars.append(char)
        return None

    def _parse_symbol(self):
        start = self._position
        while self._position < len(self._text):
            char = self._text[self._position]
            if char.isspace() or char in '()"':
                break
            self._position += 1
        if self._position == start:
            return None
        return self._text[start : self._position]

    def _skip_space(self) -> None:
        while self._position < len(self._text) and self._text[self._position].isspace():
            self._position += 1


def hb_en(atom) -> str:
    """Render a typed HyperBase atom as a compact English sentence."""
    node = atom if isinstance(atom, list) else _Parser(_atom_text(atom)).parse()
    rendered = _render_fragment(node)
    if rendered is None:
        return _atom_text(atom)
    return _sentence(rendered)


def hb_en_result(atom) -> str:
    """Compatibility wrapper that returns the English rendering result."""
    return hb_en(atom)


def _atom_text(atom) -> str:
    get_object = getattr(atom, "get_object", None)
    if get_object is not None:
        try:
            value = get_object()
        except TypeError:
            value = None
        if isinstance(value, str):
            return value
    get_name = getattr(atom, "get_name", None)
    if get_name is not None:
        return get_name()
    text = str(atom)
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


def _render_fragment(node) -> str | None:
    if not isinstance(node, list) or not node:
        return None

    head = node[0]
    if head == "sh-atom":
        if len(node) != 3 or not isinstance(node[2], (_Quoted, str)):
            return None
        return str(node[2])

    if head == "sh":
        if len(node) != 4 or not isinstance(node[2], (_Quoted, str)):
            return None
        args = _args(node[3])
        if args is None:
            return None
        return _render_predicate(str(node[2]), args)

    if head == "sh-conn":
        if len(node) != 3:
            return None
        label = _render_fragment(node[1])
        args = _args(node[2])
        if label is None or args is None:
            return None
        return _render_predicate(label, args)

    return None


def _args(node) -> list[tuple[str, str]] | None:
    if not isinstance(node, list) or not node or node[0] != "args":
        return None
    if len(node) == 2 and isinstance(node[1], list) and not _is_arg(node[1]):
        raw_args = node[1]
    else:
        raw_args = node[1:]

    rendered_args: list[tuple[str, str]] = []
    for raw_arg in raw_args:
        if not _is_arg(raw_arg):
            return None
        rendered = _render_fragment(raw_arg[2])
        if rendered is None:
            return None
        rendered_args.append((str(raw_arg[1]), rendered))
    return rendered_args


def _is_arg(node) -> bool:
    return isinstance(node, list) and len(node) == 3 and node[0] == "arg"


def _render_predicate(label: str, args: list[tuple[str, str]]) -> str:
    roles: dict[str, str] = {}
    for role, value in args:
        roles.setdefault(role, value)

    subject = roles.get("s")
    complement = roles.get("r") or roles.get("o")
    if subject is not None and complement is not None:
        return _join(subject, label, complement)

    return _join(label, *(value for _, value in args))


def _join(*parts: str) -> str:
    return " ".join(part for part in parts if part)


def _sentence(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped
    if stripped[-1] in ".!?":
        return stripped
    return stripped + "."

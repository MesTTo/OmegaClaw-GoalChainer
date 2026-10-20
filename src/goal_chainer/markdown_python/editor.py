"""Pure MeTTa query/editor helpers for authored Markdown documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from goal_chainer.sexpr.syntax import Atom, StringLiteral, Symbol, emit, metta_string, parse
from goal_chainer.markdown_python.ast import Document, Table, TableCell, Text
from goal_chainer.markdown_python.author import AuthoredDocument, parse_authoring_metta
from goal_chainer.markdown_python.emit import emit_facts, emit_human
from goal_chainer.markdown_python.inline import extract_plain_text
from goal_chainer.markdown_python.parser import parse_markdown

SelectionKind = Literal["cell"]


@dataclass(frozen=True, slots=True)
class Selection:
    """Resolved editable location returned by an `md-query` find command."""

    doc_id: str
    kind: SelectionKind
    table_index: int
    table_name: str | None
    section: str
    row: int
    col: int
    value: str

    @property
    def path(self) -> str:
        """Return the canonical selector for this selection."""
        table = f"(name {self.table_name})" if self.table_name is not None else f"(table {self.table_index})"
        return f"(cell {table} {self.section} {self.row} {self.col})"

    @property
    def captures(self) -> dict[str, str | int]:
        """Return template captures exposed while editing this selection."""
        return {
            "table": self.table_name if self.table_name is not None else self.table_index,
            "section": self.section,
            "row": self.row,
            "col": self.col,
            "old": self.value,
        }


def md_query(doc_source: str, command_source: str, *, doc_id: str = "md1") -> str:
    """Run a pure editor query against a Markdown or authored `(md ...)` document."""
    try:
        authored = _parse_document(doc_source, doc_id=doc_id)
        command = parse(command_source)
        return _run_query(authored, command)
    except ValueError as exc:
        message = str(exc)
        if message.startswith("__CARDINALITY__ "):
            _, expected, actual = message.split()
            return f"(md-edit-error cardinality (expected {expected} actual {actual}))"
        return f"(md-error invalid-query {metta_string(message)})"


def md_find(doc_source: str, query_source: str, *, doc_id: str = "md1") -> str:
    """Find editor selections in a document."""
    return md_query(doc_source, f"(find {query_source})", doc_id=doc_id)


def md_editor_atoms(doc_source: str, *, doc_id: str = "md1") -> str:
    """Return source doc, direct facts, and ownership records for editor sync."""
    authored = _parse_document(doc_source, doc_id=doc_id)
    pretty = emit_human(authored.document, doc_id=authored.doc_id)
    facts = emit_facts(authored.document, doc_id=authored.doc_id)
    owned = [f"(md-ed-owned {authored.doc_id} {pretty})"]
    owned.extend(f"(md-ed-owned {authored.doc_id} {fact})" for fact in facts)
    return "(" + " ".join([pretty, *facts, *owned, f"(md-ed-current {authored.doc_id} {pretty})"]) + ")"


def _parse_document(source: str, *, doc_id: str) -> AuthoredDocument:
    text = source.strip()
    if text.startswith("(md"):
        return parse_authoring_metta(text)
    return AuthoredDocument(doc_id=doc_id, document=parse_markdown(source))


def _run_query(authored: AuthoredDocument, command: Atom) -> str:
    head = _head(command)
    if head == "find":
        selections = _find(authored, _arg(command, 1))
        return f"(md-ok ({' '.join(_emit_selection(selection) for selection in selections)}))"
    if head == "edit":
        selections = _resolve_selection_expr(authored, _arg(command, 1), default_cardinality="one")
        replacement = _replacement_text(_arg(command, 2), selections[0])
        return _edit(authored, selections, replacement)
    if head == "update":
        selections = _resolve_selection_expr(authored, _arg(command, 1), default_cardinality="one")
        replacements = [_replacement_text(_arg(command, 2), selection) for selection in selections]
        return _edit_many(authored, list(zip(selections, replacements, strict=True)))
    if head == "apply":
        return _apply(authored, _arg(command, 1))
    raise ValueError(f"unsupported md-query command: {head}")


def _resolve_selection_expr(
    authored: AuthoredDocument,
    expr: Atom,
    *,
    default_cardinality: Literal["one", "many"],
) -> list[Selection]:
    head = _head(expr)
    if head == "find":
        selections = _find(authored, _arg(expr, 1))
        if default_cardinality == "one" and len(selections) != 1:
            raise _cardinality_error(1, len(selections))
        return selections
    if head == "all":
        inner = _arg(expr, 1)
        if _head(inner) != "find":
            raise ValueError("(all ...) expects a find expression")
        return _find(authored, _arg(inner, 1))
    if head == "first":
        inner = _arg(expr, 1)
        if _head(inner) != "find":
            raise ValueError("(first ...) expects a find expression")
        return _find(authored, _arg(inner, 1))[:1]
    if head == "md-selection":
        return [_parse_selection(expr)]
    raise ValueError(f"unsupported selection expression: {emit(expr)}")


def _find(authored: AuthoredDocument, query: Atom) -> list[Selection]:
    head = _head(query)
    if head == "cell":
        return [_find_cell(authored, query)]
    if head == "col":
        return _find_col(authored, query)
    raise ValueError(f"unsupported find query: {head}")


def _find_cell(authored: AuthoredDocument, query: Atom) -> Selection:
    table_ref = _arg(query, 1)
    table_index, table = _resolve_table(authored.document, table_ref)
    if len(query) == 5:
        section = _symbol_text(_arg(query, 2))
        row = _int_atom(_arg(query, 3))
        col = _int_atom(_arg(query, 4))
        return _cell_selection(authored.doc_id, table_index, table, section, row, col)
    if len(query) == 4 and _head(_arg(query, 2)) == "where" and _head(_arg(query, 3)) == "col":
        row = _find_row_by_where(table, _arg(query, 2))
        col = _find_col_index(table, _atom_plain(_arg(_arg(query, 3), 1)))
        return _cell_selection(authored.doc_id, table_index, table, "body", row, col)
    raise ValueError(f"unsupported cell query: {emit(query)}")


def _find_col(authored: AuthoredDocument, query: Atom) -> list[Selection]:
    table_index, table = _resolve_table(authored.document, _arg(query, 1))
    col = _find_col_index(table, _atom_plain(_arg(query, 2)))
    return [
        _cell_selection(authored.doc_id, table_index, table, "body", row_index, col)
        for row_index in range(1, len(table.rows) + 1)
    ]


def _find_row_by_where(table: Table, where: Atom) -> int:
    header = _atom_plain(_arg(where, 1))
    expected = _atom_plain(_arg(where, 2))
    col = _find_col_index(table, header)
    for row_index, row in enumerate(table.rows, start=1):
        if _cell_plain(row[col - 1]) == expected:
            return row_index
    raise ValueError(f"no table row where {header} is {expected}")


def _find_col_index(table: Table, header: str) -> int:
    for index, cell in enumerate(table.header, start=1):
        if _cell_plain(cell) == header:
            return index
    raise ValueError(f"no table column named {header}")


def _resolve_table(document: Document, table_ref: Atom) -> tuple[int, Table]:
    head = _head(table_ref)
    tables = [(index, block) for index, block in enumerate(document.children) if isinstance(block, Table)]
    if head == "name":
        name = _symbol_text(_arg(table_ref, 1))
        for table_index, (_, table) in enumerate(tables):
            if table.name == name:
                return table_index, table
        raise ValueError(f"no table named {name}")
    if head == "table":
        table_index = _int_atom(_arg(table_ref, 1))
        try:
            return table_index, tables[table_index][1]
        except IndexError as exc:
            raise ValueError(f"no table at index {table_index}") from exc
    raise ValueError(f"unsupported table reference: {emit(table_ref)}")


def _cell_selection(
    doc_id: str,
    table_index: int,
    table: Table,
    section: str,
    row: int,
    col: int,
) -> Selection:
    if section not in ("head", "body"):
        raise ValueError(f"unknown table section {section!r}")
    if section == "head":
        cells = table.header
    else:
        if not 1 <= row <= len(table.rows):
            raise ValueError(f"row {row} out of range 1..{len(table.rows)}")
        cells = table.rows[row - 1]
    if not 1 <= col <= len(cells):
        raise ValueError(f"col {col} out of range 1..{len(cells)}")
    cell = cells[col - 1]
    return Selection(
        doc_id=doc_id,
        kind="cell",
        table_index=table_index,
        table_name=table.name,
        section=section,
        row=row,
        col=col,
        value=_cell_plain(cell),
    )


def _edit(authored: AuthoredDocument, selections: list[Selection], replacement: str) -> str:
    return _edit_many(authored, [(selection, replacement) for selection in selections])


def _edit_many(authored: AuthoredDocument, edits: list[tuple[Selection, str]]) -> str:
    document = authored.document
    summaries: list[str] = []
    for selection, replacement in edits:
        current = _current_selection_value(document, selection)
        if current != selection.value:
            return f"(md-edit-error stale-selection (expected {metta_string(selection.value)} actual {metta_string(current)}))"
        document = _replace_cell(document, selection, replacement)
        summaries.append(
            f"(md-edit-summary replace-cell {selection.path} {metta_string(selection.value)} {metta_string(replacement)})"
        )
    return f"(md-edit-ok {emit_human(document, doc_id=authored.doc_id)} ({' '.join(summaries)}))"


def _apply(authored: AuthoredDocument, ops: Atom) -> str:
    if not isinstance(ops, list):
        raise ValueError("apply expects a list of operations")
    current = authored
    env: dict[str, list[Selection]] = {}
    summaries: list[str] = []
    for op in ops:
        head = _head(op)
        if head == "find-cell":
            var = _symbol_text(_arg(op, 1))
            env[var] = [_find_cell(current, _arg(op, 2))]
        elif head == "edit":
            target = _arg(op, 1)
            if isinstance(target, Symbol) and target.text in env:
                selections = env[target.text]
            else:
                selections = _resolve_selection_expr(current, target, default_cardinality="one")
            replacement = _replacement_text(_arg(op, 2), selections[0])
            result = _edit(current, selections, replacement)
            if result.startswith("(md-edit-error"):
                return result
            current = _parse_edit_result(result)
            summaries.append(
                f"(md-edit-summary replace-cell {selections[0].path} {metta_string(selections[0].value)} {metta_string(replacement)})"
            )
        else:
            raise ValueError(f"unsupported apply op: {head}")
    return f"(md-edit-ok {emit_human(current.document, doc_id=current.doc_id)} ({' '.join(summaries)}))"


def _parse_edit_result(result: str) -> AuthoredDocument:
    parsed = parse(result)
    if not isinstance(parsed, list) or len(parsed) < 2:
        raise ValueError("invalid edit result")
    return parse_authoring_metta(emit(parsed[1]))


def _current_selection_value(document: Document, selection: Selection) -> str:
    table = _table_by_selection(document, selection)
    cells = table.header if selection.section == "head" else table.rows[selection.row - 1]
    return _cell_plain(cells[selection.col - 1])


def _replace_cell(document: Document, selection: Selection, value: str) -> Document:
    blocks = list(document.children)
    block_index, table = _table_block_by_selection(document, selection)
    header = table.header
    rows = [list(row) for row in table.rows]
    new_cell = TableCell([Text(value)])
    if selection.section == "head":
        header = tuple(new_cell if index == selection.col - 1 else cell for index, cell in enumerate(header))
    else:
        rows[selection.row - 1][selection.col - 1] = new_cell
    blocks[block_index] = Table(
        table.alignments,
        header,
        rows,
        source=table.source,
        name=table.name,
    )
    return Document(blocks, source=document.source)


def _table_by_selection(document: Document, selection: Selection) -> Table:
    return _table_block_by_selection(document, selection)[1]


def _table_block_by_selection(document: Document, selection: Selection) -> tuple[int, Table]:
    tables = [(index, block) for index, block in enumerate(document.children) if isinstance(block, Table)]
    if selection.table_name is not None:
        for block_index, table in tables:
            if table.name == selection.table_name:
                return block_index, table
    try:
        block_index, table = tables[selection.table_index]
    except IndexError as exc:
        raise ValueError(f"no table at index {selection.table_index}") from exc
    return block_index, table


def _replacement_text(atom: Atom, selection: Selection) -> str:
    if isinstance(atom, list) and _head(atom) == "template":
        return emit(_substitute(_arg(atom, 1), selection))
    return _atom_plain(atom)


def _substitute(atom: Atom, selection: Selection) -> Atom:
    if isinstance(atom, Symbol) and atom.text.startswith("$"):
        key = atom.text[1:]
        if key in selection.captures:
            return _capture_atom(selection.captures[key])
        return atom
    if isinstance(atom, list):
        return [_substitute(item, selection) for item in atom]
    return atom


def _capture_atom(value: str | int) -> Atom:
    if isinstance(value, int):
        return Symbol(str(value))
    if value and all(not char.isspace() for char in value):
        return parse(value)
    return StringLiteral(value)


def _parse_selection(atom: Atom) -> Selection:
    if not isinstance(atom, list) or len(atom) != 5:
        raise ValueError(f"invalid md-selection: {emit(atom)}")
    doc_id = _symbol_text(atom[1])
    path = atom[2]
    if _head(path) != "cell":
        raise ValueError(f"unsupported md-selection path: {emit(path)}")
    table_ref = _arg(path, 1)
    table_name = _symbol_text(_arg(table_ref, 1)) if _head(table_ref) == "name" else None
    table_index = _int_atom(_arg(table_ref, 1)) if _head(table_ref) == "table" else 0
    return Selection(
        doc_id=doc_id,
        kind="cell",
        table_index=table_index,
        table_name=table_name,
        section=_symbol_text(_arg(path, 2)),
        row=_int_atom(_arg(path, 3)),
        col=_int_atom(_arg(path, 4)),
        value=_atom_plain(atom[3]),
    )


def _emit_selection(selection: Selection) -> str:
    capture_parts = []
    for key, value in selection.captures.items():
        rendered = metta_string(str(value)) if key == "old" else _capture_text(value)
        capture_parts.append(f"({key} {rendered})")
    captures = " ".join(capture_parts)
    return (
        f"(md-selection {selection.doc_id} {selection.path} "
        f"{metta_string(selection.value)} ({captures}))"
    )


def _capture_text(value: str | int) -> str:
    if isinstance(value, int):
        return str(value)
    if value in {"body", "head"}:
        return value
    if value and all(not char.isspace() for char in value) and not value.startswith("("):
        return value
    return metta_string(value)


def _cell_plain(cell: TableCell) -> str:
    return extract_plain_text(cell.children)


def _head(atom: Atom) -> str:
    if not isinstance(atom, list) or not atom:
        raise ValueError(f"expected expression, got {emit(atom)}")
    return _symbol_text(atom[0])


def _arg(atom: Atom, index: int) -> Atom:
    if not isinstance(atom, list) or len(atom) <= index:
        raise ValueError(f"missing argument {index} in {emit(atom)}")
    return atom[index]


def _symbol_text(atom: Atom) -> str:
    if isinstance(atom, Symbol):
        return atom.text
    if isinstance(atom, StringLiteral):
        return atom.value
    return emit(atom)


def _atom_plain(atom: Atom) -> str:
    if isinstance(atom, StringLiteral):
        return atom.value
    if isinstance(atom, Symbol):
        return atom.text
    return emit(atom)


def _int_atom(atom: Atom) -> int:
    text = _symbol_text(atom)
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"expected integer atom, got {text}") from exc


def _cardinality_error(expected: int, actual: int) -> ValueError:
    return ValueError(f"__CARDINALITY__ {expected} {actual}")

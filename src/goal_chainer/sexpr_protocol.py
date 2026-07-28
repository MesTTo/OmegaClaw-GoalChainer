"""Shared parsing for GoalChainer's versioned S-expression protocols."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable

_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def nonempty_output_lines(stdout: str) -> tuple[str, ...]:
    """Return trimmed nonempty lines from one MeTTa runtime transcript."""

    return tuple(line.strip() for line in stdout.splitlines() if line.strip())


@dataclass(frozen=True, slots=True)
class ProtocolEnvelope:
    operation: str
    status: str
    payload: Any
    raw: Any


def parse_versioned_output(
    lines: Iterable[str],
    codec: Any,
    *,
    version: str,
    record_prefix: str,
    protocol_name: str,
    protocol_error: type[Exception],
    execution_error: type[Exception],
    expected_operation: str | None = None,
) -> ProtocolEnvelope:
    """Parse the only matching machine record while retaining human output."""

    records: list[Any] = []
    parse_errors: list[str] = []
    record_sources, _ = partition_protocol_output(lines, record_prefix)
    for source in record_sources:
        try:
            atom = codec.parse(_escape_string_newlines(source))
        except Exception as exc:
            parse_errors.append(str(exc))
            continue
        if _is_record(atom, codec, record_prefix):
            records.append(atom)
    if len(records) != 1:
        raise protocol_error(
            f"MeTTa runtime output must contain exactly one GoalChainer {protocol_name} record.",
            details={"record_count": len(records), "parse_errors": parse_errors},
        )

    record = records[0]
    received_version = symbol_text(
        record[0],
        codec,
        protocol_error,
    )
    if received_version != version:
        raise protocol_error(
            f"Unsupported {protocol_name} protocol version: {received_version}",
            details={"expected": version, "received": received_version},
        )
    operation = symbol_text(record[1], codec, protocol_error)
    status = symbol_text(record[2], codec, protocol_error)
    if expected_operation is not None and operation != expected_operation:
        raise protocol_error(
            f"{protocol_name} protocol operation does not match the request.",
            details={"expected": expected_operation, "received": operation},
        )
    payload = record[3]
    if status == "error":
        code, message = _parse_error(payload, codec, protocol_error)
        raise execution_error(
            message,
            details={"runtime_code": code, "operation": operation},
        )
    if status != "ok":
        raise protocol_error(
            f"Unsupported {protocol_name} protocol status: {status}",
            details={"operation": operation},
        )
    return ProtocolEnvelope(operation, status, payload, record)


def partition_protocol_output(
    lines: Iterable[str],
    record_prefix: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Separate balanced, possibly multiline records from human output."""

    records: list[str] = []
    transcript: list[str] = []
    buffer: list[str] = []
    depth = 0
    in_string = False
    escaped = False
    marker = f"({record_prefix}"
    for line in lines:
        if not buffer and not line.lstrip().startswith(marker):
            transcript.append(line)
            continue
        buffer.append(line)
        depth, in_string, escaped = _scan_balance(
            line,
            depth=depth,
            in_string=in_string,
            escaped=escaped,
        )
        if depth == 0 and not in_string:
            records.append("\n".join(buffer))
            buffer = []
            escaped = False
    if buffer:
        records.append("\n".join(buffer))
    return tuple(records), tuple(transcript)


def atom_text(atom: Any, codec: Any) -> str:
    if isinstance(atom, codec.StringLiteral):
        return atom.value
    if isinstance(atom, codec.Symbol):
        return atom.text
    return codec.emit(atom)


def atom_to_python(atom: Any, codec: Any) -> Any:
    if isinstance(atom, codec.StringLiteral):
        return atom.value
    if isinstance(atom, codec.Symbol):
        if _NUMBER_RE.fullmatch(atom.text):
            return _number(atom.text)
        return atom.text
    if isinstance(atom, list):
        return [atom_to_python(item, codec) for item in atom]
    return atom


def symbol_text(
    atom: Any,
    codec: Any,
    protocol_error: Callable[..., Exception],
) -> str:
    if not isinstance(atom, codec.Symbol):
        raise protocol_error("Protocol tag must be a symbol.")
    return atom.text


def _is_record(
    atom: Any,
    codec: Any,
    record_prefix: str,
) -> bool:
    return (
        isinstance(atom, list)
        and len(atom) == 4
        and isinstance(atom[0], codec.Symbol)
        and atom[0].text.startswith(record_prefix)
    )


def _parse_error(
    payload: Any,
    codec: Any,
    protocol_error: Callable[..., Exception],
) -> tuple[str, str]:
    if (
        not isinstance(payload, list)
        or len(payload) != 3
        or symbol_text(payload[0], codec, protocol_error) != "error"
    ):
        raise protocol_error("Protocol error record has the wrong shape.")
    return atom_text(payload[1], codec), atom_text(payload[2], codec)


def _number(text: str) -> int | float:
    if "." not in text and "e" not in text.lower():
        return int(text)
    return float(text)


def _scan_balance(
    source: str,
    *,
    depth: int,
    in_string: bool,
    escaped: bool,
) -> tuple[int, bool, bool]:
    for character in source:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
    return depth, in_string, escaped


def _escape_string_newlines(source: str) -> str:
    """Make PeTTa's literal multiline string rendering JSON-decodable."""

    output: list[str] = []
    in_string = False
    escaped = False
    for character in source:
        if in_string:
            if escaped:
                escaped = False
                output.append(character)
            elif character == "\\":
                escaped = True
                output.append(character)
            elif character == '"':
                in_string = False
                output.append(character)
            elif character == "\n":
                output.append("\\n")
            else:
                output.append(character)
            continue
        output.append(character)
        if character == '"':
            in_string = True
    return "".join(output)


__all__ = [
    "ProtocolEnvelope",
    "atom_text",
    "atom_to_python",
    "nonempty_output_lines",
    "parse_versioned_output",
    "partition_protocol_output",
    "symbol_text",
]

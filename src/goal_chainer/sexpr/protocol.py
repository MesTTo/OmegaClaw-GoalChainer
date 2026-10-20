"""Purpose: shared parsing for GoalChainer's versioned S-expression protocols: split an engine's
printed lines into records, read a record's envelope, and turn atoms into Python values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable

_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


# Lines end at "\n" alone: pymetta prints a string's newline and return as escapes, so a line's ends
# fall between printed atoms and trimming never reaches a string, while str.splitlines also cut at
# \v, \f, \x1c, \x1d, \x1e, \x85, U+2028 and U+2029, which pymetta prints raw inside one: the string
# "\u2028 edges" came back as "\nedges".
# am[implements a-rt-framing-split-newline-1018@c9dd95] am[rests-on c-rt-framing-needs-only-newline-split-1018@bb3396]
def nonempty_output_lines(stdout: str) -> tuple[str, ...]:
    """Return trimmed nonempty lines from one MeTTa runtime transcript."""

    return tuple(line.strip() for line in stdout.split("\n") if line.strip())


@dataclass(frozen=True, slots=True)
class ProtocolEnvelope:
    operation: str
    status: str
    payload: Any
    raw: Any


# Every line beginning with the record marker is accounted for before an envelope is accepted: each
# must read as one four-part record, so a malformed candidate beside a valid one fails the output
# closed rather than being dropped, and exactly one record must then remain. Lines without the
# marker are the program's own output.
# am[implements a-dr-one-line-records-1018@d9f30d] am[implements a-integrate-protocol-candidates-strict-1018@0c6030]
# am[rests-on c-integrate-protocol-malformed-record-hidden-1018@7eca87]
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
    """Parse the only machine record, refusing any malformed candidate beside it, while retaining
    human output."""

    records: list[Any] = []
    malformed: list[dict[str, str]] = []
    record_sources, _ = partition_protocol_output(lines, record_prefix)
    for source in record_sources:
        try:
            atom = codec.parse(source)
        except Exception as exc:
            # The codec's error carries the reader's own reason, such as "unclosed expression", in
            # its details, which then name the error.
            malformed.append({"line": source, "error": str(exc), **dict(getattr(exc, "details", {}))})
            continue
        if _is_record(atom, codec, record_prefix):
            records.append(atom)
        else:
            malformed.append({"line": source, "error": "not a four-part record"})
    if malformed:
        raise protocol_error(
            f"MeTTa runtime output holds a malformed GoalChainer {protocol_name} record.",
            details={"malformed": malformed, "record_count": len(records)},
        )
    if len(records) != 1:
        raise protocol_error(
            f"MeTTa runtime output must contain exactly one GoalChainer {protocol_name} record.",
            details={"record_count": len(records)},
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


# A record is one line beginning with its marker: pymetta prints a record, as it prints any atom, on
# one line with a string's newlines escaped, so no record continues onto the next line and every
# other line is the program's own output. A scanner joining lines took any quote for a string's
# start, so a symbol such as a"b, which pymetta prints raw, made a record swallow the lines after it.
# am[implements a-dr-one-line-records-1018@d9f30d] am[rests-on c-rt-framing-needs-only-newline-split-1018@bb3396]
# am[related c-dr-quote-in-symbol-opens-string-1018@0bc57a]
def partition_protocol_output(
    lines: Iterable[str],
    record_prefix: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Separate the record lines, each beginning with `(record_prefix`, from human output."""

    marker = f"({record_prefix}"
    records: list[str] = []
    transcript: list[str] = []
    for line in lines:
        (records if line.lstrip().startswith(marker) else transcript).append(line)
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


__all__ = [
    "ProtocolEnvelope",
    "atom_text",
    "atom_to_python",
    "nonempty_output_lines",
    "parse_versioned_output",
    "partition_protocol_output",
    "symbol_text",
]

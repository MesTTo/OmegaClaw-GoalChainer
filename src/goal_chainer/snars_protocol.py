"""Parse GoalChainer's versioned SNARS S-expression protocol."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Iterable

from .snars_models import (
    EvidenceCounts,
    EvidenceReceipt,
    SnarsBelief,
    SnarsPettaExecutionError,
    SnarsProof,
    SnarsProtocolError,
    SubjectiveOpinion,
)
from .snars_program import SexprCodec

PROTOCOL_VERSION = "goalchainer-snars-v1"
_NUMBER_RE = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
)


@dataclass(frozen=True, slots=True)
class ProtocolEnvelope:
    operation: str
    status: str
    payload: Any
    raw: Any


def parse_protocol_output(
    lines: Iterable[str],
    codec: SexprCodec,
    *,
    expected_operation: str | None = None,
) -> ProtocolEnvelope:
    records: list[Any] = []
    parse_errors: list[str] = []
    for line in lines:
        try:
            atom = codec.parse(line)
        except Exception as exc:
            parse_errors.append(str(exc))
            continue
        if _is_record(atom, codec):
            records.append(atom)
    if len(records) != 1:
        raise SnarsProtocolError(
            "PeTTa output must contain exactly one GoalChainer SNARS record.",
            details={"record_count": len(records), "parse_errors": parse_errors},
        )

    record = records[0]
    version = _symbol(record[0], codec)
    if version != PROTOCOL_VERSION:
        raise SnarsProtocolError(
            f"Unsupported SNARS protocol version: {version}",
            details={"expected": PROTOCOL_VERSION, "received": version},
        )
    operation = _symbol(record[1], codec)
    status = _symbol(record[2], codec)
    if expected_operation is not None and operation != expected_operation:
        raise SnarsProtocolError(
            "SNARS protocol operation does not match the request.",
            details={"expected": expected_operation, "received": operation},
        )
    payload = record[3]
    if status == "error":
        code, message = _parse_error(payload, codec)
        raise SnarsPettaExecutionError(
            message,
            details={"runtime_code": code, "operation": operation},
        )
    if status != "ok":
        raise SnarsProtocolError(
            f"Unsupported SNARS protocol status: {status}",
            details={"operation": operation},
        )
    return ProtocolEnvelope(operation, status, payload, record)


def parse_belief(payload: Any, codec: SexprCodec) -> SnarsBelief:
    row = _expect_tag(payload, "belief", codec)
    if len(row) != 8:
        raise SnarsProtocolError("Belief record has the wrong arity.")
    statement_id = _atom_text(row[1], codec)
    canonical = codec.emit(row[2])
    opinion = _parse_opinion(row[3], codec)
    evidence = _parse_evidence(row[4], codec)

    receipts_row = _expect_tag(row[5], "receipts", codec)
    receipts = tuple(
        _parse_receipt(item, codec, statement_id)
        for item in _list_payload(receipts_row, 1)
    )
    proofs_row = _expect_tag(row[6], "proofs", codec)
    proofs = tuple(
        _parse_proof(item, codec)
        for item in _list_payload(proofs_row, 1)
    )
    sources = tuple(dict.fromkeys(receipt.source for receipt in receipts))
    return SnarsBelief(
        statement_id=statement_id,
        canonical_statement=canonical,
        opinion=opinion,
        evidence=evidence,
        receipts=receipts,
        proofs=proofs,
        sources=sources,
    )


def parse_opinion(atom: Any, codec: SexprCodec) -> SubjectiveOpinion:
    return _parse_opinion(atom, codec)


def atom_to_python(atom: Any, codec: SexprCodec) -> Any:
    if isinstance(atom, codec.StringLiteral):
        return atom.value
    if isinstance(atom, codec.Symbol):
        if _NUMBER_RE.fullmatch(atom.text):
            return _number(atom.text)
        return atom.text
    if isinstance(atom, list):
        return [atom_to_python(item, codec) for item in atom]
    return atom


def state_digest(atom: Any, codec: SexprCodec) -> str:
    return hashlib.sha256(codec.emit(atom).encode("utf-8")).hexdigest()


def _is_record(atom: Any, codec: SexprCodec) -> bool:
    if not isinstance(atom, list) or len(atom) != 4:
        return False
    if not isinstance(atom[0], codec.Symbol):
        return False
    return atom[0].text.startswith("goalchainer-snars-")


def _parse_error(payload: Any, codec: SexprCodec) -> tuple[str, str]:
    row = _expect_tag(payload, "error", codec)
    if len(row) != 3:
        raise SnarsProtocolError("SNARS error record has the wrong arity.")
    return _atom_text(row[1], codec), _atom_text(row[2], codec)


def _parse_opinion(atom: Any, codec: SexprCodec) -> SubjectiveOpinion:
    row = _expect_tag(atom, "opinion", codec, aliases=("Opinion",))
    if len(row) != 5:
        raise SnarsProtocolError("Opinion record has the wrong arity.")
    return SubjectiveOpinion(*(_float(item, codec) for item in row[1:]))


def _parse_evidence(atom: Any, codec: SexprCodec) -> EvidenceCounts:
    row = _expect_tag(atom, "evidence", codec, aliases=("Ev",))
    if len(row) != 4:
        raise SnarsProtocolError("Evidence record has the wrong arity.")
    return EvidenceCounts(*(_float(item, codec) for item in row[1:]))


def _parse_receipt(
    atom: Any,
    codec: SexprCodec,
    expected_statement_id: str,
) -> EvidenceReceipt:
    row = _expect_tag(atom, "receipt", codec)
    if len(row) != 5:
        raise SnarsProtocolError("Receipt record has the wrong arity.")
    statement_id = _atom_text(row[3], codec)
    if statement_id != expected_statement_id:
        raise SnarsProtocolError(
            "Receipt statement ID does not match its belief.",
            details={
                "belief_statement_id": expected_statement_id,
                "receipt_statement_id": statement_id,
            },
        )
    return EvidenceReceipt(
        receipt_id=_atom_text(row[1], codec),
        source=_atom_text(row[2], codec),
        statement_id=statement_id,
        trust=_float(row[4], codec),
    )


def _parse_proof(atom: Any, codec: SexprCodec) -> SnarsProof:
    row = _expect_tag(atom, "proof", codec)
    if len(row) != 5:
        raise SnarsProtocolError("Proof record has the wrong arity.")
    proof_term = row[2]
    conclusion = codec.emit(row[3])
    stamps_row = _expect_tag(row[4], "stamps", codec)
    stamps = tuple(
        _atom_text(item, codec) for item in _list_payload(stamps_row, 1)
    )
    return _proof_tree(proof_term, conclusion, stamps, codec)


def _proof_tree(
    term: Any,
    conclusion: str,
    root_stamps: tuple[str, ...],
    codec: SexprCodec,
) -> SnarsProof:
    if isinstance(term, list) and term:
        kind = _atom_text(term[0], codec)
        premises = tuple(
            _proof_tree(child, conclusion, (), codec) for child in term[1:]
        )
        return SnarsProof(kind, conclusion, premises, root_stamps)
    label = _atom_text(term, codec)
    return SnarsProof("axiom", label, (), root_stamps or (label,))


def _list_payload(row: list[Any], index: int) -> list[Any]:
    value = row[index]
    if not isinstance(value, list):
        raise SnarsProtocolError("Protocol collection payload must be a list.")
    return value


def _expect_tag(
    atom: Any,
    expected: str,
    codec: SexprCodec,
    *,
    aliases: tuple[str, ...] = (),
) -> list[Any]:
    if not isinstance(atom, list) or not atom:
        raise SnarsProtocolError(f"Expected a {expected} expression.")
    tag = _symbol(atom[0], codec)
    if tag not in (expected, *aliases):
        raise SnarsProtocolError(
            f"Expected {expected}, received {tag}.",
            details={"expected": expected, "received": tag},
        )
    return atom


def _symbol(atom: Any, codec: SexprCodec) -> str:
    if not isinstance(atom, codec.Symbol):
        raise SnarsProtocolError("Protocol tag must be a symbol.")
    return atom.text


def _atom_text(atom: Any, codec: SexprCodec) -> str:
    if isinstance(atom, codec.StringLiteral):
        return atom.value
    if isinstance(atom, codec.Symbol):
        return atom.text
    return codec.emit(atom)


def _float(atom: Any, codec: SexprCodec) -> float:
    text = _atom_text(atom, codec)
    if not _NUMBER_RE.fullmatch(text):
        raise SnarsProtocolError(
            "Protocol numeric field is not a finite decimal.",
            details={"value": text},
        )
    try:
        return float(text)
    except ValueError as exc:
        raise SnarsProtocolError(
            "Protocol numeric field cannot be parsed.",
            details={"value": text},
        ) from exc


def _number(text: str) -> int | float:
    if "." not in text and "e" not in text.lower():
        return int(text)
    return float(text)


__all__ = [
    "PROTOCOL_VERSION",
    "ProtocolEnvelope",
    "atom_to_python",
    "parse_belief",
    "parse_opinion",
    "parse_protocol_output",
    "state_digest",
]

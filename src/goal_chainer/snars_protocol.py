"""Parse GoalChainer's versioned SNARS S-expression protocol."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

from .snars_models import (
    EvidenceCounts,
    EvidenceReceipt,
    SnarsActionAssessment,
    SnarsBelief,
    SnarsCounterfactual,
    SnarsPettaExecutionError,
    SnarsProof,
    SnarsProtocolError,
    SnarsRequestContext,
    SubjectiveOpinion,
)
from .snars_program import SexprCodec
from .sexpr_protocol import (
    ProtocolEnvelope,
    atom_to_python,
    parse_versioned_output,
)

PROTOCOL_VERSION = "goalchainer-snars-v1"
_NUMBER_RE = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
)


def parse_protocol_output(
    lines: Iterable[str],
    codec: SexprCodec,
    *,
    expected_operation: str | None = None,
) -> ProtocolEnvelope:
    return parse_versioned_output(
        lines,
        codec,
        version=PROTOCOL_VERSION,
        record_prefix="goalchainer-snars-",
        protocol_name="SNARS",
        protocol_error=SnarsProtocolError,
        execution_error=SnarsPettaExecutionError,
        expected_operation=expected_operation,
    )


def parse_belief(payload: Any, codec: SexprCodec) -> SnarsBelief:
    row = _expect_tag(payload, "belief", codec)
    if len(row) != 8:
        raise SnarsProtocolError("Belief record has the wrong arity.")
    statement_id = _atom_text(row[1], codec)
    canonical = codec.emit(row[2])
    opinion = _parse_opinion(row[3], codec)
    evidence = _parse_evidence(row[4], codec)

    receipts_row = _expect_tag(row[5], "receipts", codec)
    receipts = _unique_receipts(
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


def parse_assessment(
    payload: Any,
    codec: SexprCodec,
) -> tuple[SnarsActionAssessment, ...]:
    row = _expect_tag(payload, "assessment", codec)
    assessments: list[SnarsActionAssessment] = []
    for item in row[1:]:
        action = _expect_tag(item, "action", codec)
        if len(action) != 6:
            raise SnarsProtocolError("Action assessment has the wrong arity.")
        values = {}
        for field_name, field in zip(
            ("acceptable", "risky", "forbidden"),
            action[2:5],
            strict=True,
        ):
            tagged = _expect_tag(field, field_name, codec)
            if len(tagged) != 2:
                raise SnarsProtocolError(
                    f"{field_name} action belief has the wrong arity."
                )
            values[field_name] = parse_belief(tagged[1], codec)
        assessments.append(
            SnarsActionAssessment(
                action_id=_atom_text(action[1], codec),
                acceptable=values["acceptable"],
                risky=values["risky"],
                forbidden=values["forbidden"],
                conflict_degree=_float(
                    _single_tag_value(action[5], "conflict", codec),
                    codec,
                ),
            )
        )
    if not assessments:
        raise SnarsProtocolError("Assessment record contains no actions.")
    return tuple(assessments)


def parse_counterfactual(payload: Any, codec: SexprCodec) -> SnarsCounterfactual:
    row = _expect_tag(payload, "counterfactual", codec)
    if len(row) != 7:
        raise SnarsProtocolError("Counterfactual record has the wrong arity.")
    hypothesis = _single_tag_value(row[1], "hypothesis", codec)
    query = _single_tag_value(row[2], "query", codec)
    opinion = _parse_opinion(_single_tag_value(row[3], "opinion", codec), codec)
    proof_atoms = _single_tag_value(row[4], "proofs", codec)
    if not isinstance(proof_atoms, list):
        raise SnarsProtocolError("Counterfactual proofs must be a list.")
    proofs = tuple(_parse_proof(item, codec) for item in proof_atoms)
    before = _single_tag_value(row[5], "state-before", codec)
    after = _single_tag_value(row[6], "state-after", codec)
    before_text = codec.emit(before)
    after_text = codec.emit(after)
    try:
        return SnarsCounterfactual(
            hypothesis=codec.emit(hypothesis),
            query=codec.emit(query),
            opinion=opinion,
            proofs=proofs,
            state_before=before_text,
            state_after=after_text,
            digest_before=state_digest(before, codec),
            digest_after=state_digest(after, codec),
        )
    except ValueError as exc:
        raise SnarsProtocolError(
            "SNARS counterfactual did not roll back its state.",
            details={"error": str(exc)},
        ) from exc


def parse_request_context(payload: Any, codec: SexprCodec) -> SnarsRequestContext:
    row = _expect_tag(payload, "context", codec)
    if len(row) != 5:
        raise SnarsProtocolError("Request context has the wrong arity.")
    values: dict[str, SnarsBelief] = {}
    for field_name, field in zip(
        ("sensitive", "public", "unverified", "coordination"),
        row[1:],
        strict=True,
    ):
        tagged = _expect_tag(field, field_name, codec)
        if len(tagged) != 2:
            raise SnarsProtocolError(
                f"{field_name} request belief has the wrong arity."
            )
        values[field_name] = parse_belief(tagged[1], codec)
    return SnarsRequestContext(**values)


def state_digest(atom: Any, codec: SexprCodec) -> str:
    return hashlib.sha256(codec.emit(atom).encode("utf-8")).hexdigest()


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
    # Direct beliefs use the conclusion ID. Derived beliefs retain the premise
    # statement IDs that appear in their proof stamps.
    if not statement_id:
        raise SnarsProtocolError(
            "Receipt statement ID is empty.",
            details={"belief_statement_id": expected_statement_id},
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


def _unique_receipts(receipts: Iterable[EvidenceReceipt]) -> tuple[EvidenceReceipt, ...]:
    unique: dict[tuple[str, str], EvidenceReceipt] = {}
    for receipt in receipts:
        unique[(receipt.receipt_id, receipt.statement_id)] = receipt
    return tuple(unique.values())


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


def _single_tag_value(atom: Any, tag: str, codec: SexprCodec) -> Any:
    row = _expect_tag(atom, tag, codec)
    if len(row) != 2:
        raise SnarsProtocolError(f"{tag} record has the wrong arity.")
    return row[1]


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


__all__ = [
    "PROTOCOL_VERSION",
    "ProtocolEnvelope",
    "atom_to_python",
    "parse_assessment",
    "parse_belief",
    "parse_counterfactual",
    "parse_opinion",
    "parse_protocol_output",
    "parse_request_context",
    "state_digest",
]

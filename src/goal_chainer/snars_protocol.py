"""Purpose: parse GoalChainer's versioned SNARS S-expression protocol into typed values."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

from .snars_models import (
    EvidenceCounts,
    EvidenceReceipt,
    ObligationLeaf,
    ObligationRoute,
    SnarsBelief,
    SnarsCondition,
    SnarsCounterfactual,
    SnarsObligations,
    SnarsProof,
    SnarsTrack,
    SubjectiveOpinion,
)
from .errors import MettaEngineError, ProtocolError
from .sexpr.codec import SexprCodec
from .sexpr.protocol import ProtocolEnvelope, atom_to_python, parse_versioned_output

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
        protocol_error=ProtocolError,
        execution_error=MettaEngineError,
        expected_operation=expected_operation,
    )


# am[implements a-v2-receipt-conflict-refusal-1020@051877]
def parse_belief(payload: Any, codec: SexprCodec) -> SnarsBelief:
    """Parse one response, collapsing identical supporting receipts.

    A repeated (receipt_id, statement_id) with a different source or trust raises
    ProtocolError. This check is local to the response; trust may change between queries.
    """
    row = _expect_tag(payload, "belief", codec)
    if len(row) != 8:
        raise ProtocolError("Belief record has the wrong arity.")
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


def parse_counterfactual(payload: Any, codec: SexprCodec) -> SnarsCounterfactual:
    row = _expect_tag(payload, "counterfactual", codec)
    if len(row) != 7:
        raise ProtocolError("Counterfactual record has the wrong arity.")
    hypothesis = _single_tag_value(row[1], "hypothesis", codec)
    query = _single_tag_value(row[2], "query", codec)
    opinion = _parse_opinion(_single_tag_value(row[3], "opinion", codec), codec)
    proof_atoms = _single_tag_value(row[4], "proofs", codec)
    if not isinstance(proof_atoms, list):
        raise ProtocolError("Counterfactual proofs must be a list.")
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
        raise ProtocolError(
            "SNARS counterfactual did not roll back its state.",
            details={"error": str(exc)},
        ) from exc


# The record (obligations (statement S) (threshold T) (hypothesis O) (routes R...)) that
# gc obligations-record answers; SNARS's route order is kept as it came.
# am[implements a-rt-ob-session-1017@f1468f]
def parse_obligations(payload: Any, codec: SexprCodec) -> SnarsObligations:
    row = _expect_tag(payload, "obligations", codec)
    if len(row) != 5:
        raise ProtocolError("Obligations record has the wrong arity.")
    statement = codec.emit(_single_tag_value(row[1], "statement", codec))
    threshold = _float(_single_tag_value(row[2], "threshold", codec), codec)
    hypothesis = _parse_opinion(_single_tag_value(row[3], "hypothesis", codec), codec)
    routes = _single_tag_value(row[4], "routes", codec)
    if not isinstance(routes, list):
        raise ProtocolError("Obligations routes must be a list.")
    try:
        return SnarsObligations(
            statement=statement,
            threshold=threshold,
            hypothesis=hypothesis,
            routes=tuple(_parse_route(item, codec) for item in routes),
        )
    except (TypeError, ValueError) as exc:
        raise ProtocolError("Obligations record is not well formed.", details={"error": str(exc)}) from exc


# The record (condition (statement S) (sid X) (threshold T) (search W) (steps N) (status C)
# (opinion O)) that gc condition-record answers in the attention world.
# am[implements a-rt-ob-session-1017@f1468f]
def parse_condition(payload: Any, codec: SexprCodec) -> SnarsCondition:
    row = _expect_tag(payload, "condition", codec)
    if len(row) != 9:
        raise ProtocolError("Condition record has the wrong arity.")
    polarity = _symbol(_single_tag_value(row[3], "polarity", codec), codec)
    if polarity not in ("pos", "neg"):
        raise ProtocolError("Condition polarity must be pos or neg.", details={"polarity": polarity})
    try:
        return SnarsCondition(
            statement=codec.emit(_single_tag_value(row[1], "statement", codec)),
            statement_id=_atom_text(_single_tag_value(row[2], "sid", codec), codec),
            threshold=_float(_single_tag_value(row[4], "threshold", codec), codec),
            negated=polarity == "neg",
            search=_symbol(_single_tag_value(row[5], "search", codec), codec),
            steps=_count(_single_tag_value(row[6], "steps", codec), codec),
            status=_symbol(_single_tag_value(row[7], "status", codec), codec),
            opinion=_parse_opinion(_single_tag_value(row[8], "opinion", codec), codec),
        )
    except (TypeError, ValueError) as exc:
        raise ProtocolError("Condition record is not well formed.", details={"error": str(exc)}) from exc


# The record (track (positive R) (negative S) (threshold T) (opinion O) (status C)) that
# gc track-record answers.
# am[implements a-rt-ob-negation-track-1017@a1a80d]
def parse_track(payload: Any, codec: SexprCodec) -> SnarsTrack:
    row = _expect_tag(payload, "track", codec)
    if len(row) != 6:
        raise ProtocolError("Track record has the wrong arity.")
    try:
        return SnarsTrack(
            positive=_float(_single_tag_value(row[1], "positive", codec), codec),
            negative=_float(_single_tag_value(row[2], "negative", codec), codec),
            threshold=_float(_single_tag_value(row[3], "threshold", codec), codec),
            opinion=_parse_opinion(_single_tag_value(row[4], "opinion", codec), codec),
            status=_symbol(_single_tag_value(row[5], "status", codec), codec),
        )
    except (TypeError, ValueError) as exc:
        raise ProtocolError("Track record is not well formed.", details={"error": str(exc)}) from exc


def state_digest(atom: Any, codec: SexprCodec) -> str:
    return hashlib.sha256(codec.emit(atom).encode("utf-8")).hexdigest()


def _parse_opinion(atom: Any, codec: SexprCodec) -> SubjectiveOpinion:
    row = _expect_tag(atom, "opinion", codec, aliases=("Opinion",))
    if len(row) != 5:
        raise ProtocolError("Opinion record has the wrong arity.")
    return SubjectiveOpinion(*(_float(item, codec) for item in row[1:]))


# (route (leaves L...) (scenario (hypothesis H) (opinion O) (status C)) (proof P) (size N))
# am[implements a-rt-ob-session-1017@f1468f]
def _parse_route(atom: Any, codec: SexprCodec) -> ObligationRoute:
    row = _expect_tag(atom, "route", codec)
    if len(row) != 5:
        raise ProtocolError("Route record has the wrong arity.")
    leaves_row = _expect_tag(row[1], "leaves", codec)
    if len(leaves_row) != 2:
        raise ProtocolError("Route leaves record has the wrong arity.")
    scenario = _expect_tag(row[2], "scenario", codec)
    if len(scenario) != 4:
        raise ProtocolError("Route scenario record has the wrong arity.")
    _parse_opinion(_single_tag_value(scenario[1], "hypothesis", codec), codec)
    return ObligationRoute(
        leaves=tuple(_parse_leaf(item, codec) for item in _list_payload(leaves_row, 1)),
        scenario=_parse_opinion(_single_tag_value(scenario[2], "opinion", codec), codec),
        scenario_status=_symbol(_single_tag_value(scenario[3], "status", codec), codec),
        proof=codec.emit(_single_tag_value(row[3], "proof", codec)),
        size=_count(_single_tag_value(row[4], "size", codec), codec),
    )


# (leaf open TREE Open) for an open premise; (leaf SID TREE STATUS OPINION) for a held one.
# am[implements a-rt-ob-session-1017@f1468f]
def _parse_leaf(atom: Any, codec: SexprCodec) -> ObligationLeaf:
    row = _expect_tag(atom, "leaf", codec)
    if len(row) == 4 and _symbol(row[3], codec) == "Open":
        return ObligationLeaf(statement=codec.emit(row[2]), status="Open")
    if len(row) != 5:
        raise ProtocolError("Leaf record has the wrong arity.")
    return ObligationLeaf(
        statement=codec.emit(row[2]),
        status=_symbol(row[3], codec),
        statement_id=_atom_text(row[1], codec),
        opinion=_parse_opinion(row[4], codec),
    )


# A count the protocol writes as a number, such as a route's size or a search's steps.
# am[implements a-rt-ob-session-1017@f1468f]
def _count(atom: Any, codec: SexprCodec) -> int:
    value = _float(atom, codec)
    if not value.is_integer():
        raise ProtocolError("Protocol count is not an integer.", details={"value": value})
    return int(value)


def _parse_evidence(atom: Any, codec: SexprCodec) -> EvidenceCounts:
    row = _expect_tag(atom, "evidence", codec, aliases=("Ev",))
    if len(row) != 4:
        raise ProtocolError("Evidence record has the wrong arity.")
    return EvidenceCounts(*(_float(item, codec) for item in row[1:]))


def _parse_receipt(
    atom: Any,
    codec: SexprCodec,
    expected_statement_id: str,
) -> EvidenceReceipt:
    row = _expect_tag(atom, "receipt", codec)
    if len(row) != 5:
        raise ProtocolError("Receipt record has the wrong arity.")
    statement_id = _atom_text(row[3], codec)
    # Direct beliefs use the conclusion ID. Derived beliefs retain the premise
    # statement IDs that appear in their proof stamps.
    if not statement_id:
        raise ProtocolError(
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
        raise ProtocolError("Proof record has the wrong arity.")
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


# A receipt identity has one payload within a response; later queries may update trust.
# Time: O(r) expected lookups, r = receipt occurrences. Space: O(u), u = identities.
# am[implements a-v2-receipt-conflict-refusal-1020@051877]
def _unique_receipts(receipts: Iterable[EvidenceReceipt]) -> tuple[EvidenceReceipt, ...]:
    unique: dict[tuple[str, str], EvidenceReceipt] = {}
    for receipt in receipts:
        key = (receipt.receipt_id, receipt.statement_id)
        previous = unique.get(key)
        if previous is not None and previous != receipt:
            raise ProtocolError(
                "Receipt identity has conflicting payloads within one belief response.",
                details={"receipt_id": receipt.receipt_id, "statement_id": receipt.statement_id},
            )
        unique[key] = receipt
    return tuple(unique.values())


def _list_payload(row: list[Any], index: int) -> list[Any]:
    value = row[index]
    if not isinstance(value, list):
        raise ProtocolError("Protocol collection payload must be a list.")
    return value


def _expect_tag(
    atom: Any,
    expected: str,
    codec: SexprCodec,
    *,
    aliases: tuple[str, ...] = (),
) -> list[Any]:
    if not isinstance(atom, list) or not atom:
        raise ProtocolError(f"Expected a {expected} expression.")
    tag = _symbol(atom[0], codec)
    if tag not in (expected, *aliases):
        raise ProtocolError(
            f"Expected {expected}, received {tag}.",
            details={"expected": expected, "received": tag},
        )
    return atom


def _single_tag_value(atom: Any, tag: str, codec: SexprCodec) -> Any:
    row = _expect_tag(atom, tag, codec)
    if len(row) != 2:
        raise ProtocolError(f"{tag} record has the wrong arity.")
    return row[1]


def _symbol(atom: Any, codec: SexprCodec) -> str:
    if not isinstance(atom, codec.Symbol):
        raise ProtocolError("Protocol tag must be a symbol.")
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
        raise ProtocolError(
            "Protocol numeric field is not a finite decimal.",
            details={"value": text},
        )
    try:
        return float(text)
    except ValueError as exc:
        raise ProtocolError(
            "Protocol numeric field cannot be parsed.",
            details={"value": text},
        ) from exc


__all__ = [
    "PROTOCOL_VERSION",
    "ProtocolEnvelope",
    "atom_to_python",
    "parse_belief",
    "parse_condition",
    "parse_counterfactual",
    "parse_obligations",
    "parse_opinion",
    "parse_protocol_output",
    "parse_track",
    "state_digest",
]

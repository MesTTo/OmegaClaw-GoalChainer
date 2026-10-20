"""Purpose: read caller-supplied memory items at the decision boundary and admit them through the MeTTa memory policy.

Python checks what an item is made of: a mapping, a text slot, an atom it can decode, finite
numbers, well-formed provenance and text content, and it digests the item's content. Everything
the items mean is decided by policy/goalchainer_memory.metta: which slots are read, the ranges
evidence must lie in, its weight, whose evidence it is, which one item of each identity is fused
or read, and which reader failures leave a memory text unread.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

from metta import Expression, Grounded, S

from . import evidence_policy
from .runtime.budget import RunBudget
from .runtime.numbers import finite_float
from .sexpr.protocol import atom_to_python
from .snars_models import Evidence
from .errors import InvalidInputError, ProtocolError

Encoding = Literal["stv", "ec"]
DispositionStatus = Literal["admitted", "text", "duplicate", "ignored", "empty"]
PROVENANCE_FIELDS = ("belief_id", "cluster_id", "promotion_event", "promotion_domain")


# am[implements a-ev-memory-admission@56c9f7]
class MemoryEvidenceError(InvalidInputError):
    """A memory item GoalChainer consumes is malformed, so the decision does not run."""


# am[implements a-ev-memory-admission@56c9f7]
@dataclass(frozen=True, slots=True)
class MemoryIdentity:
    """Who asserted a memory item: one promoted belief, one promotion, or its content.

    Two items with one identity are one piece of evidence however many times the
    cache emits them, so only one of them is fused.
    """

    kind: Literal["belief", "promotion", "content"]
    values: tuple[str, ...]

    @property
    def source(self) -> str:
        """The SNARS receipt source, e.g. ``memory:["belief","b-7"]``."""

        return "memory:" + json.dumps([self.kind, *self.values], separators=(",", ":"))


# am[implements a-ev-memory-admission@56c9f7]
# am[implements a-ev-br-callers-1017@1261b7] am[rests-on c-ev-offline-reads-no-rate-1017@e18e6a]
@dataclass(frozen=True, slots=True)
class MemoryEvidence:
    """One admitted item: evidence counts about one action's acceptability, and the opinion
    the memory policy reads them as. The counts give SNARS no base rate, so it reads them at
    its configured default; no offline grader reads a rate."""

    index: int
    action_id: str
    encoding: Encoding
    counts: Evidence
    strength: float
    confidence: float
    identity: MemoryIdentity
    provenance: tuple[tuple[str, str], ...]
    atom: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "action_id": self.action_id,
            "encoding": self.encoding,
            "identity": self.identity.source,
            "evidence": {
                "positive": round(self.counts.positive, 6),
                "negative": round(self.counts.negative, 6),
                "strength": round(self.strength, 6),
                "confidence": round(self.confidence, 6),
            },
            "provenance": dict(self.provenance),
            "atom": self.atom,
        }


# A memory text the policy admitted, to be read as part of the request's own context.
# am[implements a-ev-wt-host-1017@2731e9]
@dataclass(frozen=True, slots=True)
class MemoryText:
    """One admitted memory text: its item index, its content identity and the text itself."""

    index: int
    identity: MemoryIdentity
    text: str


# am[implements a-ev-memory-admission@56c9f7]
@dataclass(frozen=True, slots=True)
class MemoryDisposition:
    """What the boundary did with one received item, and why."""

    index: int
    status: DispositionStatus
    reason: str
    message: str
    identity: str | None = None
    representative: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "status": self.status,
            "reason": self.reason,
            "message": self.message,
            "identity": self.identity,
            "representative": self.representative,
        }


# am[implements a-ev-memory-admission@56c9f7]
# am[implements a-ev-wt-host-1017@2731e9]
@dataclass(frozen=True, slots=True)
class MemoryAdmission:
    """Every received item's disposition, the evidence a decision may fuse and the texts it reads."""

    received: int
    admitted: tuple[MemoryEvidence, ...]
    dispositions: tuple[MemoryDisposition, ...]
    texts: tuple[MemoryText, ...] = ()

    def for_action(self, action_id: str) -> tuple[MemoryEvidence, ...]:
        return tuple(item for item in self.admitted if item.action_id == action_id)

    @property
    def digest(self) -> str:
        """SHA-256 over the admitted evidence and texts, the memory part of a decision's readset.

        Admission with no texts digests as it did before texts were read.
        """

        canonical = json.dumps(
            [
                *(
                    [item.identity.source, item.action_id, item.counts.positive, item.counts.negative]
                    for item in self.admitted
                ),
                *([text.identity.source, "text"] for text in self.texts),
            ],
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        counts = {status: 0 for status in ("admitted", "text", "duplicate", "ignored", "empty")}
        for disposition in self.dispositions:
            counts[disposition.status] += 1
        return {
            "received": self.received,
            "counts": counts,
            "digest": self.digest,
            "admitted": [item.to_dict() for item in self.admitted],
            "dispositions": [disposition.to_dict() for disposition in self.dispositions],
        }


NO_MEMORY = MemoryAdmission(received=0, admitted=(), dispositions=())

# The memory policy's two input-independent tables, each read once per process under the budget of
# the request that first needs it: the loader pins the policy's bytes, so a second read could only
# repeat the first.
# am[implements a-ev-rb-pipeline-budget-1018@988a39]
_TABLES: dict[str, Any] = {}


# am[implements a-ev-mr-python@f08ebd]
# am[implements a-ev-rb-pipeline-budget-1018@988a39]
def consumed_slots(*, budget: RunBudget) -> Mapping[str, Encoding]:
    """The slots the memory policy reads and the encoding each carries, asked once per process."""

    if "slots" not in _TABLES:
        answer = evidence_policy.evaluate("gc-memory-slots", budget=budget)
        _TABLES["slots"] = MappingProxyType({slot: str(encoding) for slot, encoding in answer})
    return _TABLES["slots"]


# am[implements a-ev-wt-omission-1017@4177f4]
# am[implements a-ev-rb-pipeline-budget-1018@988a39]
def memory_text_omissions(*, budget: RunBudget) -> frozenset[str]:
    """The reader failure reasons that leave a memory text unread, asked once per process; every
    other reader failure is the decision's."""

    if "omissions" not in _TABLES:
        answer = evidence_policy.evaluate("gc-memory-text-omissions", budget=budget)
        _TABLES["omissions"] = frozenset(str(reason) for reason in answer)
    return _TABLES["omissions"]


# A content digest in the form the memory policy compares: a text's, and the request's.
# am[implements a-ev-wt-host-1017@2731e9]
def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# am[implements a-ev-mr-python@f08ebd]
@dataclass(frozen=True, slots=True)
class _Read:
    """A consumed item as decoded here, before the policy has judged it."""

    index: int
    slot: str
    encoding: Encoding
    action_id: str
    first: float
    second: float
    provenance: Mapping[str, str]
    atom: str

    @property
    def digest(self) -> str:
        canonical = json.dumps(
            [self.encoding, self.action_id, self.first, self.second], separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def term(self) -> Any:
        provenance = [
            S["None"] if self.provenance.get(name) is None else Grounded(self.provenance[name])
            for name in PROVENANCE_FIELDS
        ]
        return S.Item(
            self.index,
            S.Slot(self.slot),
            S.Read(
                S[self.encoding],
                self.action_id,
                self.first,
                self.second,
                S.Provenance(*provenance),
                self.digest,
            ),
        )


# Time: O(total atom length) decoding plus one policy call, whose rules take n * g identity
# comparisons for n items and g identities, and n * t digest comparisons for t texts. Space: O(n).
# am[implements a-ev-mr-python@f08ebd]
# am[addresses i-ev-memory-dropped-silently@e6ebd2]
# am[addresses i-ev-dedup-identity-gaps@4f9730]
# am[implements a-ev-wt-host-1017@2731e9]
# am[implements a-ev-rb-pipeline-budget-1018@988a39]
def admit_memory_evidence(
    items: Sequence[Any] | None,
    candidate_actions: Iterable[str],
    *,
    codec: Callable[[], Any],
    request: str,
    budget: RunBudget,
) -> MemoryAdmission:
    """Read memory items, have the memory policy dispose of each one, and keep what it fuses.

    ``codec`` returns the MeTTa S-expression codec. It is called only when an
    item sits in a consumed slot, so items GoalChainer ignores need no runtime.
    An unslotted item's ``content``, as WMTM's ``{id, content, sti}`` items carry,
    is a memory text the policy may admit for reading into the context of
    ``request``. Malformed items raise MemoryEvidenceError naming their index.
    The policy's work is charged to ``budget``, the request's.
    """

    if items is None:
        return NO_MEMORY
    if isinstance(items, (str, bytes)) or not isinstance(items, Sequence):
        raise MemoryEvidenceError(
            "memory_items must be a list of mappings.",
            details={"type": type(items).__name__},
        )
    candidates = tuple(dict.fromkeys(candidate_actions))
    slots = consumed_slots(budget=budget)
    reads: dict[int, _Read] = {}
    unread: dict[int, str] = {}
    contents: dict[int, str] = {}
    terms: list[Any] = []
    resolved_codec = None
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise MemoryEvidenceError(
                "Each memory item must be a mapping.",
                details={"index": index, "type": type(item).__name__},
            )
        slot = item.get("goalchainer_slot")
        if slot is None:
            terms.append(_unslotted(index, item, contents))
            continue
        if not isinstance(slot, str):
            raise MemoryEvidenceError(
                "Memory item goalchainer_slot must be text.",
                details={"index": index, "type": type(slot).__name__},
            )
        encoding = slots.get(slot)
        if encoding is None:
            unread[index] = slot
            terms.append(S.Item(index, S.Slot(slot), S.Unread))
            continue
        if resolved_codec is None:
            resolved_codec = codec()
        read = _read_consumed(index, item, slot, encoding, resolved_codec)
        reads[index] = read
        terms.append(read.term())

    answer = evidence_policy.evaluate(
        "gc-memory-admit",
        Expression(*terms),
        Expression(*(Grounded(action) for action in candidates)),
        text_digest(request),
        budget=budget,
    )
    return _admission(answer, len(items), reads, unread, contents, candidates, slots)


# An unslotted item is a memory text when it carries content; blank content says nothing, and the
# policy disposes of each case. Content of another type is malformed.
# am[implements a-ev-wt-host-1017@2731e9]
def _unslotted(index: int, item: Mapping[str, Any], contents: dict[int, str]) -> Any:
    content = item.get("content")
    if content is None:
        return S.Item(index, S.NoSlot)
    if not isinstance(content, str):
        raise MemoryEvidenceError(
            "Memory item content must be text.",
            details={"index": index, "type": type(content).__name__},
        )
    if not content.strip():
        return S.Item(index, S.BlankText)
    contents[index] = content
    return S.Item(index, S.Text(text_digest(content)))


# am[implements a-ev-mr-python@f08ebd]
# am[implements a-ev-wt-host-1017@2731e9]
def _admission(
    answer: Any,
    received: int,
    reads: Mapping[int, _Read],
    unread: Mapping[int, str],
    contents: Mapping[int, str],
    candidates: Sequence[str],
    slots: Mapping[str, Encoding],
) -> MemoryAdmission:
    if not (isinstance(answer, tuple) and len(answer) == 4 and answer[:2] == (S["goalchainer-memory-v1"], S.admit)):
        raise ProtocolError("The memory policy answered an unknown record.", details={"answer": str(answer)})
    if answer[2] == S.rejected:
        raise _rejection(answer[3], reads)
    if answer[2] != S.ok or len(answer[3]) != received:
        raise ProtocolError("The memory policy must dispose of every item once.", details={"answer": str(answer)})
    admitted: list[MemoryEvidence] = []
    texts: list[MemoryText] = []
    dispositions: list[MemoryDisposition] = []
    for row in answer[3]:
        _, index, status, reason, identity_term, detail = row
        identity = None if identity_term == S["None"] else _identity(identity_term)
        source = None if identity is None else identity.source
        status, reason = str(status), str(reason)
        if status == "admitted":
            read = reads[index]
            _, (_, positive, negative), (_, strength, confidence) = detail
            admitted.append(
                MemoryEvidence(
                    index=index,
                    action_id=read.action_id,
                    encoding=read.encoding,
                    counts=Evidence(float(positive), float(negative)),
                    strength=float(strength),
                    confidence=float(confidence),
                    identity=identity,
                    provenance=tuple(sorted(read.provenance.items())),
                    atom=read.atom,
                )
            )
            message = f"Evidence about {read.action_id} from {source}."
        elif status == "text":
            texts.append(MemoryText(index, identity, contents[index]))
            message = "The text is read into the request's context, whose readings are believed once."
        elif reason == "SameAsRequest":
            message = "The text is the request itself, which is read already."
        elif status == "duplicate":
            message = f"Item {detail} already carries {source}; one identity is one piece of evidence."
        elif reason == "NoGoalChainerSlot":
            message = "The item carries neither a goalchainer_slot nor text, so it is no evidence."
        elif reason == "BlankText":
            message = "The item's text is blank, so it says nothing."
        elif reason == "SlotNotConsumed":
            message = (
                f"GoalChainer consumes only {sorted(slots)}; slot {unread[index]!r} belongs to another consumer."
            )
        elif reason == "NotACandidateAction":
            message = (
                f"{reads[index].action_id} is not among this decision's candidate actions {sorted(candidates)}."
            )
        else:
            message = "The item carries zero evidence weight, so fusing it would change nothing."
        dispositions.append(
            MemoryDisposition(
                index,
                status,
                reason,
                message,
                identity=source,
                representative=detail if reason == "SameIdentity" else None,
            )
        )
    return MemoryAdmission(
        received=received,
        admitted=tuple(admitted),
        dispositions=tuple(dispositions),
        texts=tuple(texts),
    )


# am[implements a-ev-mr-python@f08ebd]
def _identity(term: Any) -> MemoryIdentity:
    _, kind, (_, *values) = term
    return MemoryIdentity(str(kind), tuple(values))


# The policy names what is wrong; this words it for the caller, with the values it judged.
# am[implements a-ev-mr-python@f08ebd]
def _rejection(term: Any, reads: Mapping[int, _Read]) -> MemoryEvidenceError:
    _, reason, subject, detail = term
    reason = str(reason)
    if reason == "IdentityNamesTwoActions":
        _, actions, indexes = detail
        return MemoryEvidenceError(
            "One memory identity carries evidence about different actions.",
            details={
                "identity": _identity(subject).source,
                "actions": sorted(actions),
                "indexes": sorted(indexes),
            },
        )
    read = reads[subject[1]]
    if reason == "StrengthOutOfRange":
        return MemoryEvidenceError(
            "Memory STV strength must lie in [0, 1].",
            details={"index": read.index, "strength": read.first},
        )
    if reason == "ConfidenceOutOfRange":
        # Confidence 1 would mean unbounded evidence, which testimony never carries.
        return MemoryEvidenceError(
            "Memory STV confidence must lie in [0, 1).",
            details={"index": read.index, "confidence": read.second},
        )
    if reason == "NegativeCount":
        return MemoryEvidenceError(
            "Memory EC support and opposition must be nonnegative.",
            details={"index": read.index, "support": read.first, "opposition": read.second},
        )
    raise ProtocolError("The memory policy rejected an item for an unknown reason.", details={"reason": reason})


# am[implements a-ev-mr-python@f08ebd] am[implements a-ev-nr-finite-float-1018@6fcba4]
def _read_consumed(
    index: int,
    item: Mapping[str, Any],
    slot: str,
    encoding: Encoding,
    codec: Any,
) -> _Read:
    atom = item.get("atom")
    if not isinstance(atom, str) or not atom.strip():
        raise MemoryEvidenceError(
            "Memory item atom must be nonempty text.",
            details={"index": index, "slot": slot},
        )
    try:
        value = atom_to_python(codec.parse(atom), codec)
    except InvalidInputError as exc:
        raise MemoryEvidenceError(
            "Memory item atom is not a MeTTa expression.",
            details={"index": index, "slot": slot, "error": exc.message},
        ) from exc
    shape = _stv_shape(value) if encoding == "stv" else _ec_shape(value)
    if shape is None:
        expected = (
            "(Acceptable <action>) (STV <strength> <confidence>)"
            if encoding == "stv"
            else "(EvidencePacket (Acceptable <action>) (EC <support> <opposition>) ...)"
        )
        raise MemoryEvidenceError(
            f"Memory item atom does not encode {expected}.",
            details={"index": index, "slot": slot, "atom": atom},
        )
    action_id, first, second = shape
    names = ("strength", "confidence") if encoding == "stv" else ("support", "opposition")
    # The codec reads a digit string as a Python int of any size, and float() of one beyond the float range
    # raises OverflowError, so each number is read through finite_float, which answers None there as for NaN,
    # infinity and anything not a number (a-ev-nr-finite-float-1018).
    values: list[float] = []
    for name, number in zip(names, (first, second)):
        value = finite_float(number)
        if value is None:
            raise MemoryEvidenceError(
                f"Memory {encoding.upper()} {name} must be a finite number.",
                details={"index": index, name: number},
            )
        values.append(value)
    first_value, second_value = values
    # Each count can be finite while their sum overflows, which would make the item's
    # confidence inf / inf; finiteness is representation, so it is checked here.
    if encoding == "ec" and not math.isfinite(first_value + second_value):
        raise MemoryEvidenceError(
            "Memory EC evidence weight must be finite.",
            details={"index": index, "support": first, "opposition": second},
        )
    return _Read(index, slot, encoding, action_id, first_value, second_value, _provenance(index, item), atom)


# am[implements a-ev-memory-admission@56c9f7]
def _stv_shape(value: Any) -> tuple[str, Any, Any] | None:
    """Match ``(: name (Acceptable a) (STV s c))`` or the bare pair of forms."""

    if isinstance(value, list) and len(value) == 4 and value[0] == ":":
        value = value[2:]
    if (
        isinstance(value, list)
        and len(value) == 2
        and _is_form(value[0], "Acceptable", 2)
        and _is_form(value[1], "STV", 3)
        and isinstance(value[0][1], str)
    ):
        return value[0][1], value[1][1], value[1][2]
    return None


# am[implements a-ev-memory-admission@56c9f7]
def _ec_shape(value: Any) -> tuple[str, Any, Any] | None:
    """Match ``(EvidencePacket (Acceptable a) (EC support opposition) ...)``."""

    if (
        isinstance(value, list)
        and len(value) >= 3
        and value[0] == "EvidencePacket"
        and _is_form(value[1], "Acceptable", 2)
        and _is_form(value[2], "EC", 3)
        and isinstance(value[1][1], str)
    ):
        return value[1][1], value[2][1], value[2][2]
    return None


# am[implements a-ev-memory-admission@56c9f7]
def _is_form(value: Any, head: str, length: int) -> bool:
    return isinstance(value, list) and len(value) == length and value[0] == head


# am[implements a-ev-memory-admission@56c9f7]
def _provenance(index: int, item: Mapping[str, Any]) -> dict[str, str]:
    provenance: dict[str, str] = {}
    for field_name in PROVENANCE_FIELDS:
        value = item.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str) or not value or value != value.strip():
            raise MemoryEvidenceError(
                f"Memory item {field_name} must be nonempty text without surrounding whitespace.",
                details={"index": index, "field": field_name},
            )
        provenance[field_name] = value
    return provenance


__all__ = [
    "MemoryAdmission",
    "MemoryDisposition",
    "MemoryEvidence",
    "MemoryEvidenceError",
    "MemoryIdentity",
    "MemoryText",
    "NO_MEMORY",
    "PROVENANCE_FIELDS",
    "admit_memory_evidence",
    "consumed_slots",
]

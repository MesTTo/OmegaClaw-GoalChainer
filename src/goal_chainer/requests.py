"""Purpose: compose a selected domain's readings, review and planning under one caller budget.

The wire request names an operation (review, plan or admit), a domain selected by `path` or
`packaged`, and `context`: the review packet's fields except its protocol and budget. Optional
`reading` contains the original text, observed_at and valid_until. It adds model-proposed
readings from that domain's declaration to the context's attributed readings, and, for each of the
declaration's bindings whose answer chose an entity, an entity reading that planning and admission
take beside them and the review never sees.

Planning requests carry goals, journal events and steps in planning.transport's tagged JSON format,
and `receipts`, an object mapping each journal Receipt id to its receipt-v2 document, which the
planner's tracks come from alone: no request asserts a track. Further justification rows are inert
MeTTa forms, whose statements the planner reads as a procedures file writes them. A file domain must name its
procedures file; an explicitly packaged domain can use its packaged procedures. Review, planning
and current-step admission consume the same evidence snapshot and budget. None performs an
action or supplies host authorization.

A request for a domain that declares needs may name its motivation stream, `motivation`:
{"store": PATH, "stream": ID}. The review then ranks by that stream's snapshot at context.as_of,
and by an empty stream's when the request names none; the result's review carries the snapshot.
The request only reads the stream, and refuses a path holding no store without creating one, so a
host reviews before its first record by leaving the field out; recording an attempt or an
observation is the host's, through goal_chainer.motivation.requests.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from .domains.forms import FormsUnreadable, parsed_forms
from .domains.loader import selected_domain
from .domains.model import Domain, DomainError
from .errors import InvalidInputError
from .motivation.requests import stream_selection, stream_snapshot
from .planning.procedures import ProcedureLiteral, load_procedures, packaged_procedures
from .planning.projection import JournalEvent, PlanStep, admit, plan
from .planning.transport import decode, encode
from .reading_projection import EntityReading, entity_readings, signal_readings
from .relevance.errors import RelevanceError
from .relevance.instants import parse_instant
from .relevance.packet import PACKET_PROTOCOL, ReviewPacket, parse_packet
from .relevance.receipt import Receipt, parse_receipt
from .relevance.review import review
from .runtime.budget import RunBudget, caller_budget
from .semantic_reader import domain_reader

REQUEST_PROTOCOL = "goalchainer-request-v1"


# The operation only selects existing public functions; their MeTTa modules own every judgement.
# Planning and admission read the packet's readings and the reading's entity readings as one sequence,
# which plan and admit take by each element's type; the review reads the packet alone.
# Time: input conversion plus the chosen engine stages, each charged to the same budget.
# Space: the decoded request and the stages' returned records.
# am[implements a-integrate-domain-composition-1018@ac7260] am[implements a-bnd-requests-1019@ec32de]
# am[rests-on c-ev-bnd-readings-one-sequence-1019@0927b4]
# am[implements a-v2-motivation-input-order-1020@d40cf5]
def run_request(payload: object, *, budget: RunBudget) -> dict[str, Any]:
    """Review, plan or check a step for the explicitly selected domain.

    Limits belong to the CLI or skill envelope that constructed `budget`. The packet records
    those original limits without constructing another deadline. A failure returns no partial
    result; budget exhaustion is an error, never an inferred NoPlan.
    """

    budget = caller_budget(budget, "a domain request")
    budget.remaining()
    before = budget.spent
    request = _object(payload, "request")
    operation = request.get("operation")
    fields = {
        "review": ({"operation", "domain", "context"}, {"reading", "motivation"}),
        "plan": ({"operation", "domain", "context", "goal"},
                 {"reading", "procedures", "journal", "rows", "receipts", "motivation"}),
        "admit": ({"operation", "domain", "context", "step", "instance_id"},
                  {"reading", "procedures", "journal", "rows", "motivation"}),
    }
    if not isinstance(operation, str) or operation not in fields:
        raise InvalidInputError("operation must be review, plan or admit.")
    _fields(request, *fields[operation], "request")
    if "motivation" in request:
        stream_selection(request["motivation"])
    packet = _packet(request["context"], budget)
    domain, packaged = _domain(request["domain"], budget)
    packet.check_against(domain)

    library = None
    journal: tuple[JournalEvent, ...] = ()
    rows: tuple[Any, ...] = ()
    receipts: dict[str, Receipt] = {}
    goal: tuple[ProcedureLiteral, ...] = ()
    step = None
    instance_id = None
    if operation != "review":
        path = request.get("procedures")
        if path is not None:
            library = load_procedures(_text(path, "procedures"), domain, budget=budget)
        elif packaged:
            library = packaged_procedures(domain, budget=budget)
        else:
            raise InvalidInputError("A planning request for a file domain must name its procedures file.")
        journal = decode(request.get("journal", []), tuple[JournalEvent, ...])
        rows = _rows(request.get("rows", []), budget)
        if operation == "plan":
            goal = decode(request["goal"], tuple[ProcedureLiteral, ...])
            receipts = _receipts(request.get("receipts", {}), budget)
        else:
            step = decode(request["step"], PlanStep)
            instance_id = request["instance_id"]
            if instance_id is not None:
                instance_id = _text(instance_id, "instance_id")

    motivation = (stream_snapshot(request["motivation"], domain, as_of=packet.as_of, budget=budget)
                  if "motivation" in request else None)
    reading = None
    placed: tuple[EntityReading, ...] = ()
    if "reading" in request:
        packet, reading, placed = _read(request["reading"], domain, packet, budget)
    reviewed = review(domain, packet, budget=budget, motivation=motivation)
    result: dict[str, Any] = {
        "protocol": REQUEST_PROTOCOL,
        "operation": operation,
        "review": reviewed.to_dict(),
        "authorization": "unresolved",
        "applies_effects": False,
    }
    if reading is not None:
        result["reading"] = reading.to_dict()
    readings = (*packet.readings, *placed)
    if operation == "plan":
        result["planning"] = encode(plan(
            goal, domain=domain, library=library, readings=readings,
            journal=journal, rows=rows, receipts=receipts, at=packet.as_of, budget=budget,
        ))
    elif operation == "admit":
        result["admission"] = encode(admit(
            step, instance_id=instance_id, domain=domain, library=library,
            readings=readings, journal=journal, rows=rows, at=packet.as_of, budget=budget,
        ))
    budget.remaining()
    result["inferences"] = budget.spent - before
    return result


# am[implements a-integrate-domain-composition-1018@ac7260] am[implements a-ie-sr-select-domain-1018@577734]
def _domain(value: object, budget: RunBudget) -> tuple[Domain, bool]:
    selection = domain_selection(value)
    try:
        return selected_domain(**selection, budget=budget), "packaged" in selection
    except (DomainError, OSError) as error:
        raise InvalidInputError(str(error), details={"domain": dict(selection)}) from error


# The domain a JSON request's `domain` object selects, read as every request reads one; the
# motivation request reads its domain through it.
# am[implements a-v2m-request-cycle-1019@abb37d] am[implements a-ie-sr-select-domain-1018@577734]
def domain_for(value: object, budget: RunBudget) -> Domain:
    """The selected domain under `budget`; InvalidInputError for any selection that cannot be read."""

    return _domain(value, budget)[0]


# The domain a JSON request selects: an object with exactly one of path or packaged, naming text,
# answered as the keyword loader.selected_domain takes. The SNARS dispatch takes its domain the
# same way.
# am[implements a-integrate-domain-composition-1018@ac7260] am[implements a-ie-sr-select-domain-1018@577734]
def domain_selection(value: object) -> dict[str, str]:
    """The selection keyword of a JSON domain object; InvalidInputError for any other value."""

    selection = _object(value, "domain")
    if set(selection) not in ({"path"}, {"packaged"}):
        raise InvalidInputError("domain must select exactly one path or packaged name.")
    ((key, name),) = selection.items()
    return {key: _text(name, f"domain.{key}")}


# Packet parsing remains the one validator of context and attributed signal readings.
# am[implements a-integrate-domain-composition-1018@ac7260]
def _packet(value: object, budget: RunBudget) -> ReviewPacket:
    context = _object(value, "context")
    _fields(context, {"review_id", "subject", "trigger", "as_of", "authority", "readings"},
            {"policy_version"}, "context")
    if budget.inference_budget is None:
        raise InvalidInputError("A domain request requires an inference bound as well as a deadline.")
    return parse_packet({
        **context,
        "protocol": PACKET_PROTOCOL,
        "budget": {"inferences": budget.inference_budget, "timeout_seconds": budget.timeout_seconds},
    })


# A model reading adds evidence with its own provenance; it never overwrites the supplied readings.
# The shared justification rules resolve contrary readings when the consumers evaluate them. The
# domain's reader is the process's one reader of its declaration, so requests share its loaded model.
# Its entity readings, under the same instants, are returned apart from the packet: the review folds
# every SignalReading of a signal into the signal's one belief, and an entity reading is evidence about
# its entity's qualified literal, not about the signal.
# am[implements a-integrate-domain-composition-1018@ac7260] am[implements a-integrate-domain-reader-reuse-1018@bffd2b]
# am[implements a-bnd-requests-1019@ec32de] am[rests-on c-bnd-relevance-folds-signal-readings-1019@0c12a0]
def _read(value: object, domain: Domain, packet: ReviewPacket,
          budget: RunBudget) -> tuple[ReviewPacket, Any, tuple[EntityReading, ...]]:
    payload = _object(value, "reading")
    _fields(payload, {"text", "observed_at", "valid_until"}, set(), "reading")
    text = _text(payload["text"], "reading.text")
    reader = domain_reader(domain)
    try:
        observed_at = parse_instant(_text(payload["observed_at"], "reading.observed_at"))
        valid_until = (None if payload["valid_until"] is None
                       else parse_instant(_text(payload["valid_until"], "reading.valid_until")))
    except ValueError as error:
        raise InvalidInputError(f"Invalid reading time: {error}") from error
    if observed_at > packet.as_of:
        raise InvalidInputError("reading.observed_at must not be after context.as_of.")
    if valid_until is not None and valid_until < observed_at:
        raise InvalidInputError("reading.valid_until must not be before reading.observed_at.")
    budget.remaining()
    reading = reader.read(text, budget=budget)
    additions = signal_readings(reading, domain.readings, observed_at=observed_at, valid_until=valid_until)
    placed = entity_readings(reading, domain.readings, observed_at=observed_at, valid_until=valid_until)
    return replace(packet, readings=(*packet.readings, *additions)), reading, placed


# Parsing never evaluates the supplied forms; the justification kernel validates their grammar.
# Time and space: proportional to the supplied rows' total text and resulting atoms.
# am[implements a-integrate-domain-composition-1018@ac7260]
def _rows(value: object, budget: RunBudget) -> tuple[Any, ...]:
    if not isinstance(value, list):
        raise InvalidInputError("rows must be a list of MeTTa data forms.")
    result = []
    for index, text in enumerate(value):
        budget.remaining()
        try:
            forms = parsed_forms(_text(text, f"rows[{index}]"), budget=budget)
        except FormsUnreadable as error:
            raise InvalidInputError(f"rows[{index}]: {error}") from error
        if len(forms) != 1:
            raise InvalidInputError(f"rows[{index}] must contain exactly one MeTTa data form.")
        result.append(forms[0][1])
    budget.remaining()
    return tuple(result)


# The request's receipts: an object mapping each journal Receipt id to its receipt-v2 document, each read by
# parse_receipt under the request's budget, so a malformed or incoherent document is refused before planning.
# A malformed receipt becomes InvalidInputError naming its request key; the underlying relevance
# code and message remain in the details so the host can inspect both levels of the refusal.
# Time: one receipt check per document.
# am[implements a-ev-fb-request-receipts-1018@4c8f23] am[rests-on c-ev-fb-refusals-1018@e097ef]
# am[implements a-v2-unified-error-family-1020@c7807b]
def _receipts(value: object, budget: RunBudget) -> dict[str, Receipt]:
    receipts = {}
    for key, document in _object(value, "receipts").items():
        name = _text(key, "a receipts key")
        try:
            receipts[name] = parse_receipt(document, budget=budget)
        except RelevanceError as error:
            raise InvalidInputError(f"receipts[{key!r}]: {error.message}",
                                    details={"receipt": key, "relevance": error.to_dict()}) from error
    return receipts


# am[implements a-integrate-domain-composition-1018@ac7260]
def _object(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise InvalidInputError(f"{where} must be a JSON object with text keys.")
    return value


# am[implements a-integrate-domain-composition-1018@ac7260]
def _fields(value: Mapping[str, Any], required: set[str], optional: set[str], where: str) -> None:
    missing, unknown = required - value.keys(), value.keys() - required - optional
    if missing or unknown:
        raise InvalidInputError(f"Invalid fields in {where}.",
                                details={"missing": sorted(missing), "unknown": sorted(unknown)})


# am[implements a-integrate-domain-composition-1018@ac7260]
def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"{where} must be nonempty text.")
    return value

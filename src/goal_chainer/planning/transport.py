"""Purpose: carry the planner's public records across JSON as tagged objects whose keys are the records'
own dataclass fields, and refuse every payload those fields' annotations do not admit.

    encode(value) -> a JSON value
    decode(payload, expected) -> a value of type `expected`

A record is a JSON object whose "@type" holds its class name and whose other keys are exactly its
fields. A tuple is a JSON array, of the annotation's length where the annotation fixes one, and str,
int, bool and None are JSON's string, integer, true or false, and null. A Literal is one of its own
values. A datetime is an instant as ISO-8601 text with a timezone offset, the receipts' one
representation of wire time (goal_chainer.relevance.instants): it is written in UTC, so one instant
is one text, and read back as that instant in UTC. The records are the planner API's own: every
frozen dataclass that its answers, verdicts, steps, journal events and goal literals reach
through their field annotations (RECORDS), so a record added under them is carried with no change
here.

    encode(Plan(steps=(), established=True))
      -> {"@type": "Plan", "steps": [], "established": true, "assumptions": []}

Decoding builds only those records, each chosen by its tag among the records the expected type
admits, through the record's own constructor, so a check such as NegatedLiteral's still runs. It
refuses an unknown or misplaced tag, an unknown or missing key (a field with a default included), a
JSON true or false where an integer is declared, a number where a boolean is, a tuple of the wrong
length, a value outside its Literal, and a time with no offset, finer than a microsecond or with no
UTC time in the years 1 to 9999, each as TransportRefused naming the JSON path. Encoding checks a
value against the same annotations, a datetime with no offset included, so it never writes what
decoding would refuse.
"""

from __future__ import annotations

import dataclasses
import types
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from ..errors import InvalidInputError
from ..relevance.instants import parse_instant, utc_text
from .procedures import ProcedureLiteral
from .projection import Answer, JournalEvent, PlanStep, Verdict

# The key that carries a record's class name. "kind", the repository's usual discriminator, is a
# field of PlanStep; a key that is no Python identifier can never be a field name.
# am[implements a-jk-wire-impl-1018@c09e04] am[rests-on c-jk-wire-kind-collides-1018@f29356]
TAG = "@type"

# What the planner API returns (answers, verdicts) and what the CLI and skill hand it (the step to
# admit, the journal and goal literals), as Oliver agreed (a-jk-wire-interface-1018). Tracks come from
# receipts alone, so none crosses the wire (a-ev-fb-request-receipts-1018).
# am[implements a-jk-wire-impl-1018@c09e04] am[rests-on c-jk-wire-records-a6883b5-1018@9f27df]
# am[implements a-ev-fb-request-receipts-1018@4c8f23]
ROOTS = (Answer, Verdict, PlanStep, JournalEvent, ProcedureLiteral)

_UNIONS = (Union, types.UnionType)
_JSON_TYPES = {dict: "an object", list: "an array", str: "a string", int: "an integer", float: "a number",
               bool: "a boolean", type(None): "null"}
_SCALARS = {str: "a string", int: "an integer", bool: "a boolean", type(None): "null"}
# What a datetime is on the wire, for a refusal's reason.
# am[implements a-jk-wire-datetime-1018@918fa0]
_INSTANT = "an ISO-8601 time with a timezone offset"


# A payload or value the records' annotations do not admit; `path` is where, in JSONPath's dotted form
# ($ is the whole payload), and `reason` is what was found there.
# am[implements a-jk-wire-impl-1018@c09e04]
class TransportRefused(InvalidInputError):
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"the planner transport refused {path}: {reason}", details={"path": path, "reason": reason})
        self.path = path
        self.reason = reason


# Every record the roots reach through their field annotations, by class name, with its fields and
# their resolved annotations in declaration order. Built once projection and procedures are wholly
# imported, since Inquiry names the Answer alias their module defines after it. A union holding a
# datetime and a string or a string Literal is refused: both are JSON strings, so a time would decode
# as whichever member came first.
# Time: one get_type_hints per record + one visit per annotation node, r records, a annotation nodes.
# am[implements a-jk-wire-impl-1018@c09e04] am[rests-on c-jk-wire-no-typed-json-dependency-1018@e5429f]
# am[implements a-jk-wire-datetime-1018@918fa0]
def _schema(roots: tuple[Any, ...]) -> dict[str, tuple[type, tuple[tuple[str, Any], ...]]]:
    records: dict[str, tuple[type, tuple[tuple[str, Any], ...]]] = {}
    pending = list(roots)
    while pending:
        annotation = pending.pop()
        origin, args = get_origin(annotation), get_args(annotation)
        if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
            name = annotation.__name__
            if name in records:
                if records[name][0] is not annotation:
                    raise TypeError(f"two planner records are named {name}, so a tag could not tell them apart")
                continue
            if not annotation.__dataclass_params__.frozen:
                raise TypeError(f"{name} is not frozen, so it is no planner record")
            hints = get_type_hints(annotation)
            fields = tuple((field.name, hints[field.name]) for field in dataclasses.fields(annotation))
            if any(not field.init for field in dataclasses.fields(annotation)):
                raise TypeError(f"{name} has a field its constructor does not take")
            records[name] = (annotation, fields)
            pending.extend(hint for _, hint in fields)
        elif origin in _UNIONS:
            if datetime in args and any(arg is str or (get_origin(arg) is Literal and any(type(value) is str for value in get_args(arg)))
                                        for arg in args):
                raise TypeError(f"the planner transport cannot tell a datetime from a string in {annotation!r}: both are JSON strings")
            pending.extend(args)
        elif origin is tuple:
            pending.extend(arg for arg in args if arg is not Ellipsis)
        elif origin is Literal:
            if not all(type(arg) in (str, int, bool) for arg in args):
                raise TypeError(f"the planner transport carries only string, integer and boolean literals: {annotation!r}")
        elif annotation not in _SCALARS and annotation is not datetime:
            raise TypeError(f"the planner transport cannot carry {annotation!r}")
    return records


# The planner's records by tag, the closed set decode builds from, and each one's fields.
# am[implements a-jk-wire-impl-1018@c09e04]
_SCHEMA = _schema(ROOTS)
RECORDS: Mapping[str, type] = types.MappingProxyType({name: cls for name, (cls, _) in _SCHEMA.items()})
_FIELDS = {cls: fields for cls, fields in _SCHEMA.values()}


# Whether `annotation` is one of the planner's records.
# am[implements a-jk-wire-impl-1018@c09e04]
def _is_record(annotation: Any) -> bool:
    return isinstance(annotation, type) and RECORDS.get(annotation.__name__) is annotation


# An annotation as a reader would write it, for a refusal's reason: "Plan, Inquiry or NoPlan".
# am[implements a-jk-wire-impl-1018@c09e04] am[implements a-jk-wire-datetime-1018@918fa0]
def _describe(annotation: Any) -> str:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in _UNIONS:
        names = [_describe(arg) for arg in args]
        return ", ".join(names[:-1]) + " or " + names[-1]
    if origin is Literal:
        return "one of " + ", ".join(repr(arg) for arg in args)
    if origin is tuple:
        return "an array" if Ellipsis in args else f"an array of {len(args)}"
    if annotation in _SCALARS:
        return _SCALARS[annotation]
    if annotation is datetime:
        return _INSTANT
    return annotation.__name__ if isinstance(annotation, type) else repr(annotation)


# Whether a Literal admits `value` as one of its own values, so True never stands for 1.
# am[implements a-jk-wire-impl-1018@c09e04]
def _literal_admits(args: tuple[Any, ...], value: Any) -> bool:
    return any(type(value) is type(arg) and value == arg for arg in args)


# --- encode ---------------------------------------------------------------------------------------


# `value` as a JSON value: a planner record as its tagged object, a tuple as an array of its items'
# encodings, a datetime as its UTC text, and a string, integer, boolean or None as itself; anything
# else is refused.
# am[implements a-jk-wire-impl-1018@c09e04]
def encode(value: Any) -> Any:
    return _encode_own(value, "$")


# Time: one visit per node of the value.
# am[implements a-jk-wire-impl-1018@c09e04] am[implements a-jk-wire-datetime-1018@918fa0]
def _encode_own(value: Any, path: str) -> Any:
    if type(value) is tuple:
        return [_encode_own(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if _is_record(type(value)) or type(value) in _SCALARS or type(value) is datetime:
        return _encode(value, type(value), path)
    raise TransportRefused(path, f"{type(value).__name__} is no planner record, tuple, string, integer, boolean, datetime or None")


# Whether `value` has the shape `annotation` declares, before its contents are checked.
# am[implements a-jk-wire-impl-1018@c09e04]
def _value_fits(annotation: Any, value: Any) -> bool:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Literal:
        return _literal_admits(args, value)
    if origin is tuple:
        return type(value) is tuple
    return type(value) is annotation


# `value`, checked against `annotation`, as a JSON value.
# Time: one visit per node of the value, plus, at a union, one shape test per member.
# am[implements a-jk-wire-impl-1018@c09e04] am[implements a-jk-wire-datetime-1018@918fa0]
def _encode(value: Any, annotation: Any, path: str) -> Any:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in _UNIONS:
        return _first(path, value, annotation, [arg for arg in args if _value_fits(arg, value)], _encode)
    if not _value_fits(annotation, value):
        raise TransportRefused(path, f"{_describe(annotation)} is declared, not {type(value).__name__} {value!r}")
    if annotation is datetime:
        return _instant_text(value, path)
    if _is_record(annotation):
        encoded = {TAG: annotation.__name__}
        for name, hint in _FIELDS[annotation]:
            encoded[name] = _encode(getattr(value, name), hint, f"{path}.{name}")
        return encoded
    if origin is tuple:
        return [_encode(item, hint, f"{path}[{index}]") for index, (item, hint) in enumerate(_items(args, value, path))]
    return value


# A datetime as the receipts' UTC text. A naive one names no instant, and one whose UTC time falls
# outside the years 1 to 9999 has no text, so each is refused rather than written.
# am[implements a-jk-wire-datetime-1018@918fa0] am[rests-on c-jk-wire-instant-edges-1018@ac2aec]
def _instant_text(value: datetime, path: str) -> str:
    if value.utcoffset() is None:
        raise TransportRefused(path, f"{_INSTANT} is declared, not the naive datetime {value.isoformat()}")
    try:
        return utc_text(value)
    except OverflowError:
        raise TransportRefused(path, f"{value.isoformat()} has no UTC time in the years 1 to 9999") from None


# --- decode ---------------------------------------------------------------------------------------


# The value of type `expected` that `payload`, a JSON value, encodes; a payload `expected` does not
# admit is refused. `expected` is a planner record, a union of them such as Answer or Verdict, a
# tuple, a Literal or a scalar.
# am[implements a-jk-wire-impl-1018@c09e04]
def decode(payload: Any, expected: Any) -> Any:
    try:
        return _decode(payload, expected, "$")
    except RecursionError:
        raise TransportRefused("$", "nested deeper than the interpreter's recursion limit") from None


# Whether `payload` has the JSON shape `annotation` declares, a record by its tag and a datetime as
# a string, whose text _instant then reads.
# am[implements a-jk-wire-impl-1018@c09e04] am[implements a-jk-wire-datetime-1018@918fa0]
def _payload_fits(annotation: Any, payload: Any) -> bool:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Literal:
        return _literal_admits(args, payload)
    if origin is tuple:
        return type(payload) is list
    if _is_record(annotation):
        return type(payload) is dict and payload.get(TAG) == annotation.__name__
    if annotation is datetime:
        return type(payload) is str
    return type(payload) is annotation


# Time: one visit per node of the payload, plus, at a union, one shape test per member.
# am[implements a-jk-wire-impl-1018@c09e04] am[implements a-jk-wire-datetime-1018@918fa0]
def _decode(payload: Any, annotation: Any, path: str) -> Any:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in _UNIONS:
        return _first(path, payload, annotation, [arg for arg in args if _payload_fits(arg, payload)], _decode)
    if _is_record(annotation):
        return _record(payload, annotation, path)
    if origin is tuple:
        if type(payload) is not list:
            raise TransportRefused(path, f"{_describe(annotation)} is declared, not {_JSON_TYPES.get(type(payload), repr(payload))}")
        return tuple(_decode(item, hint, f"{path}[{index}]") for index, (item, hint) in enumerate(_items(args, payload, path)))
    if origin is Literal or annotation in _SCALARS or annotation is datetime:
        if not _payload_fits(annotation, payload):
            raise TransportRefused(path, f"{_describe(annotation)} is declared, not {_JSON_TYPES.get(type(payload), 'a ' + type(payload).__name__)} {payload!r}")
        return _instant(payload, path) if annotation is datetime else payload
    raise TypeError(f"the planner transport cannot decode to {annotation!r}")


# The instant ISO-8601 text names, in UTC, read by the receipts' own parser, which refuses a time
# with no offset or finer than a microsecond; text whose instant has no UTC time in the years 1 to
# 9999 is refused too, so every decoded datetime encodes.
# am[implements a-jk-wire-datetime-1018@918fa0] am[rests-on c-jk-wire-instant-edges-1018@ac2aec]
# am[rests-on c-rel-fromisoformat-truncates-1017@616584]
def _instant(text: str, path: str) -> datetime:
    try:
        return parse_instant(text).astimezone(timezone.utc)
    except ValueError as error:
        raise TransportRefused(path, f"{_INSTANT} is declared, and {text!r} {error}") from None
    except OverflowError:
        raise TransportRefused(path, f"{text!r} has no UTC time in the years 1 to 9999") from None


# A record from its tagged object: exactly its fields, each decoded against its annotation, then its
# own constructor, whose refusal is the transport's.
# am[implements a-jk-wire-impl-1018@c09e04]
def _record(payload: Any, cls: type, path: str) -> Any:
    if type(payload) is not dict:
        raise TransportRefused(path, f"{cls.__name__} is declared, not {_JSON_TYPES.get(type(payload), repr(payload))}")
    if payload.get(TAG) != cls.__name__:
        raise TransportRefused(path, f"{cls.__name__} is declared, not the tag {payload.get(TAG)!r}")
    fields = _FIELDS[cls]
    names = {name for name, _ in fields}
    unknown = sorted((key for key in payload if key != TAG and key not in names), key=repr)
    if unknown:
        raise TransportRefused(path, f"{cls.__name__} has no field {unknown[0]!r}")
    missing = [name for name, _ in fields if name not in payload]
    if missing:
        raise TransportRefused(path, f"{cls.__name__} lacks its field {missing[0]!r}")
    values = {name: _decode(payload[name], hint, f"{path}.{name}") for name, hint in fields}
    try:
        return cls(**values)
    except (TypeError, ValueError) as error:
        raise TransportRefused(path, f"{cls.__name__} refused its fields: {error}") from None


# --- shared ---------------------------------------------------------------------------------------


# A tuple annotation's items paired with their annotations: every item with X for tuple[X, ...], and
# for a fixed tuple exactly as many items as it declares.
# am[implements a-jk-wire-impl-1018@c09e04]
def _items(args: tuple[Any, ...], items: Any, path: str) -> list[tuple[Any, Any]]:
    if len(args) == 2 and args[1] is Ellipsis:
        return [(item, args[0]) for item in items]
    if len(items) != len(args):
        raise TransportRefused(path, f"an array of {len(args)} is declared, not of {len(items)}")
    return list(zip(items, args))


# At a union, the members whose shape fits: none is a refusal, and of several the first whose
# contents also fit wins, so a refusal inside the only fitting member keeps its own path.
# am[implements a-jk-wire-impl-1018@c09e04]
def _first(path: str, value: Any, annotation: Any, fitting: list[Any], step: Any) -> Any:
    if not fitting:
        found = f"the tag {value.get(TAG)!r}" if type(value) is dict else _JSON_TYPES.get(type(value), type(value).__name__)
        raise TransportRefused(path, f"{_describe(annotation)} is declared, not {found}")
    for member in fitting[:-1]:
        try:
            return step(value, member, path)
        except TransportRefused:
            continue
    return step(value, fitting[-1], path)

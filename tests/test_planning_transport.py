"""Purpose: test the planner's JSON transport, planning/transport.py: every planner record, nested
inquiries included, survives encode, JSON text and decode with its classes and exact scalars, and every
single-site corruption of a valid encoding (a tag, a key, a value's JSON type, an array's length) is
refused at that site's path. Instants survive as themselves in UTC under every ISO-8601 spelling with an
offset, and a time naming no instant UTC holds is refused at its path either way. The tests start no
engine and call no service."""

from __future__ import annotations

import dataclasses
import json
import types
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from goal_chainer.planning import transport
from goal_chainer.planning.procedures import NegatedLiteral, ProcedureLibrary, ProcedureLiteral, SignalLiteral, StatementLiteral
from goal_chainer.planning.projection import (
    Answer,
    Inquiry,
    JournalEvent,
    NoPlan,
    Plan,
    PlanStep,
    Receipt,
    Unsolved,
    Verdict,
    Witness,
)

SETTINGS = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
UNIONS = (Union, types.UnionType)
ALIASES = (Answer, Verdict, JournalEvent, ProcedureLiteral)
# JSON values of every JSON type, from which a corruption takes one its site does not admit.
JSON_VALUES = (True, False, 0, 1, -7, 2**70, 1.5, "", "not-a-declared-literal", None, [], {})

# Any instant in a fixed offset of up to a day either side whose UTC time stays inside the years 1 to
# 9999. from_type draws naive datetimes, which name no instant and which the transport refuses to
# write, so every planner datetime the records' strategies draw is one of these.
# am[verifies a-jk-wire-datetime-1018@918fa0]
INSTANTS = st.datetimes(
    min_value=datetime(1, 1, 2), max_value=datetime(9999, 12, 30),
    timezones=st.builds(timezone, st.timedeltas(min_value=timedelta(hours=-23, minutes=-59),
                                                max_value=timedelta(hours=23, minutes=59))),
)
st.register_type_strategy(datetime, INSTANTS)

# Answers nest through Inquiry; Hypothesis builds every other record from its own annotations, so the
# values the transport carries come from a reading of the annotations independent of transport.py.
# am[implements a-jk-wire-tests-1018@dbe611]
ANSWERS = st.recursive(
    st.one_of(st.from_type(Plan), st.from_type(NoPlan)),
    lambda inner: st.builds(Inquiry, literal=st.from_type(ProcedureLiteral), investigator=st.text(),
                            if_true=inner, if_false=inner),
    max_leaves=6,
)
# am[implements a-jk-wire-tests-1018@dbe611]
RECORDS = st.one_of([ANSWERS] + [st.from_type(cls) for _, cls in sorted(transport.RECORDS.items()) if cls is not Inquiry])


# A union's members, or the annotation alone.
# am[implements a-jk-wire-tests-1018@dbe611]
def members(annotation: Any) -> tuple[Any, ...]:
    return get_args(annotation) if get_origin(annotation) in UNIONS else (annotation,)


# Whether the annotation admits a JSON value by its shape: a record admits any object, a tuple any
# array, and a datetime a string the standard library reads as a time with an offset.
# am[implements a-jk-wire-tests-1018@dbe611] am[verifies a-jk-wire-datetime-1018@918fa0]
def admits(annotation: Any, value: Any) -> bool:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in UNIONS:
        return any(admits(arg, value) for arg in args)
    if origin is Literal:
        return any(type(value) is type(arg) and value == arg for arg in args)
    if origin is tuple:
        return type(value) is list
    if dataclasses.is_dataclass(annotation):
        return type(value) is dict
    if annotation is datetime:
        return type(value) is str and names_an_instant(value)
    return type(value) is annotation


# Whether text is ISO-8601 with a timezone offset, read by datetime.fromisoformat alone.
# am[verifies a-jk-wire-datetime-1018@918fa0]
def names_an_instant(text: str) -> bool:
    try:
        return datetime.fromisoformat(text).utcoffset() is not None
    except ValueError:
        return False


# A place in an encoding: its JSONPath text, the keys that reach it, and the annotation declared there.
# am[implements a-jk-wire-tests-1018@dbe611]
@dataclasses.dataclass(frozen=True)
class Site:
    path: str
    keys: tuple[Any, ...]
    annotation: Any


# Every site of `payload`, an encoding of `annotation`, read with the records' own field annotations.
# am[implements a-jk-wire-tests-1018@dbe611]
def sites(payload: Any, annotation: Any, path: str = "$", keys: tuple[Any, ...] = ()):
    yield Site(path, keys, annotation)
    if type(payload) is dict:
        cls = next(m for m in members(annotation) if dataclasses.is_dataclass(m) and m.__name__ == payload["@type"])
        hints = get_type_hints(cls)
        for field in dataclasses.fields(cls):
            yield from sites(payload[field.name], hints[field.name], f"{path}.{field.name}", keys + (field.name,))
    elif type(payload) is list:
        items = get_args(next(m for m in members(annotation) if get_origin(m) is tuple))
        for index, item in enumerate(payload):
            hint = items[0] if items[-1] is Ellipsis else items[index]
            yield from sites(item, hint, f"{path}[{index}]", keys + (index,))


# The value at `keys` in the payload.
# am[implements a-jk-wire-tests-1018@dbe611]
def at(payload: Any, keys: tuple[Any, ...]) -> Any:
    for key in keys:
        payload = payload[key]
    return payload


# The payload with the value at `keys` replaced by what `change` makes of it.
# am[implements a-jk-wire-tests-1018@dbe611]
def replaced(payload: Any, keys: tuple[Any, ...], change) -> Any:
    if not keys:
        return change(payload)
    head, rest = keys[0], keys[1:]
    if type(payload) is dict:
        return {**payload, head: replaced(payload[head], rest, change)}
    return [replaced(item, rest, change) if index == head else item for index, item in enumerate(payload)]


# The corruptions a site's value admits, each one the transport must refuse at the site: a record
# retagged, given an unknown key or missing a field; an array replaced or, where its length is fixed,
# lengthened; any value replaced by a JSON value of a type or Literal the site does not declare.
# am[implements a-jk-wire-tests-1018@dbe611]
def corruptions(site: Site, node: Any) -> list:
    found = []
    if type(node) is dict:
        found += [lambda d, tag=tag: {**d, "@type": tag} for tag in [*transport.RECORDS, "NoSuchRecord", "builtins.object"]
                  if tag != node["@type"]]
        found.append(lambda d: {**d, "unknown_field": 0})
        found += [lambda d, key=key: {k: v for k, v in d.items() if k != key} for key in node if key != "@type"]
    if type(node) is list:
        items = get_args(next(m for m in members(site.annotation) if get_origin(m) is tuple))
        if items[-1] is not Ellipsis:
            found.append(lambda d: [*d, d[0] if d else ""])
    found += [lambda d, value=value: value for value in JSON_VALUES if not admits(site.annotation, value)]
    return found


# --- round trip -------------------------------------------------------------------------------------


# Every record survives encode, JSON text and decode: decoded against its own class or any union alias
# that holds it, it equals the original, classes included at every level, and encodes back to the same
# JSON text, so no integer came back a boolean and no string changed.
# am[verifies a-jk-wire-impl-1018@c09e04] am[verifies a-integrate-domain-wire-1018@43a558]
@SETTINGS
@given(RECORDS)
def test_every_record_survives_json_text_unchanged(value) -> None:
    text = json.dumps(transport.encode(value))
    for expected in (type(value), *(alias for alias in ALIASES if type(value) in get_args(alias))):
        decoded = transport.decode(json.loads(text), expected)
        assert decoded == value
        assert json.dumps(transport.encode(decoded)) == text


# Inquiries nested at least twice keep every branch's class and value through JSON.
# am[verifies a-jk-wire-impl-1018@c09e04] am[verifies a-integrate-domain-wire-1018@43a558]
@SETTINGS
@given(st.builds(Inquiry, literal=st.from_type(ProcedureLiteral), investigator=st.text(),
                 if_true=st.builds(Inquiry, literal=st.from_type(ProcedureLiteral), investigator=st.text(),
                                   if_true=ANSWERS, if_false=ANSWERS),
                 if_false=ANSWERS))
def test_nested_inquiries_survive_json_text(inquiry) -> None:
    assert transport.decode(json.loads(json.dumps(transport.encode(inquiry))), Answer) == inquiry


# --- refusals ---------------------------------------------------------------------------------------


# Any one corruption of a valid encoding, anywhere in it, is refused, and the refusal names that site.
# am[verifies a-jk-wire-impl-1018@c09e04] am[verifies a-integrate-domain-wire-1018@43a558]
@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(RECORDS, st.data())
def test_every_single_site_corruption_is_refused_at_its_path(value, data) -> None:
    payload = transport.encode(value)
    site = data.draw(st.sampled_from(list(sites(payload, type(value)))))
    corrupt = data.draw(st.sampled_from(corruptions(site, at(payload, site.keys))))
    with pytest.raises(transport.TransportRefused) as refused:
        transport.decode(replaced(payload, site.keys, corrupt), type(value))
    assert refused.value.path == site.path, refused.value.reason


# A plan step the refusal cases corrupt one field of.
# am[implements a-jk-wire-tests-1018@dbe611]
A_STEP = PlanStep("save", None, "start", 0, None, (("n0", "h1"),), Witness("save", "sha256:0", (("n0", "(N h1 Host)"),)))


# A boolean never stands for an integer, nor a number for a boolean or a Literal string.
# am[verifies a-jk-wire-impl-1018@c09e04]
@pytest.mark.parametrize(("payload", "expected", "path"), [
    ({"@type": "Ambiguous", "classes": True}, Verdict, "$.classes"),
    ({"@type": "Ambiguous", "classes": 2.0}, Verdict, "$.classes"),
    ({**transport.encode(Receipt("r1", "i1", "s1", "a1", True)), "applied": 1}, JournalEvent, "$.applied"),
    ({**transport.encode(A_STEP), "application": False}, PlanStep, "$.application"),
    ({**transport.encode(A_STEP), "kind": True}, PlanStep, "$.kind"),
    ({**transport.encode(A_STEP), "kind": "launch"}, PlanStep, "$.kind"),
])
def test_scalars_keep_their_declared_json_type(payload, expected, path) -> None:
    with pytest.raises(transport.TransportRefused) as refused:
        transport.decode(payload, expected)
    assert refused.value.path == path


# A field with a default is still required: decoding never fills one in.
# am[verifies a-jk-wire-impl-1018@c09e04]
@pytest.mark.parametrize(("payload", "expected"), [
    ({"@type": "Plan", "steps": [], "established": True}, Answer),
    ({"@type": "Unsolved", "literal": {"@type": "SignalLiteral", "name": "x"}, "reason": "no-way"}, Unsolved),
])
def test_a_default_is_never_filled_in(payload, expected) -> None:
    with pytest.raises(transport.TransportRefused, match="lacks its field"):
        transport.decode(payload, expected)


# Decoding builds only the planner's records, and only those the expected type admits: a planner class
# outside the closed set, an import path, or another record's tag is refused, and a negation of a
# negation is refused at its inner literal.
# am[verifies a-jk-wire-impl-1018@c09e04]
@pytest.mark.parametrize(("payload", "expected", "path"), [
    ({"@type": "ProcedureLibrary"}, Answer, "$"),
    ({"@type": "goal_chainer.planning.projection.Plan", "steps": [], "established": True, "assumptions": []}, Answer, "$"),
    ({"@type": "Admitted", "occurrence": "(o)"}, Answer, "$"),
    ({"@type": "NegatedLiteral", "literal": {"@type": "NegatedLiteral", "literal": {"@type": "SignalLiteral", "name": "x"}}},
     ProcedureLiteral, "$.literal"),
])
def test_decode_builds_no_record_the_expected_type_does_not_admit(payload, expected, path) -> None:
    with pytest.raises(transport.TransportRefused) as refused:
        transport.decode(payload, expected)
    assert refused.value.path == path


# An expected type outside the planner's records is the caller's error, not the payload's.
# am[verifies a-jk-wire-impl-1018@c09e04]
def test_decoding_to_a_type_outside_the_records_is_a_type_error() -> None:
    with pytest.raises(TypeError):
        transport.decode({"@type": "ProcedureLibrary"}, ProcedureLibrary)


# Integers of any size and strings of any characters come back exactly, deep inside an inquiry, and a
# corruption there is refused at its full path.
# am[verifies a-jk-wire-impl-1018@c09e04]
def test_exact_scalars_and_deep_paths() -> None:
    odd = "quote \" backslash \\ newline \n tab \t nul \x00 emoji \U0001F600 rtl ‮"
    step = dataclasses.replace(A_STEP, procedure=odd, application=2**100)
    inner = Plan((step,), False, (NegatedLiteral(StatementLiteral(odd)),))
    answer = Inquiry(SignalLiteral(odd), odd, Inquiry(SignalLiteral("y"), "look", inner, NoPlan((), None)), NoPlan((), inner))
    text = json.dumps(transport.encode(answer))
    assert transport.decode(json.loads(text), Answer) == answer
    payload = json.loads(text)
    payload["if_true"]["if_true"]["steps"][0]["application"] = True
    with pytest.raises(transport.TransportRefused) as refused:
        transport.decode(payload, Answer)
    assert refused.value.path == "$.if_true.if_true.steps[0].application"


# Encoding checks values against the same annotations, so it never writes what decoding refuses.
# am[verifies a-jk-wire-impl-1018@c09e04]
@pytest.mark.parametrize(("value", "path"), [
    (dataclasses.replace(A_STEP, application=True), "$.application"),
    (dataclasses.replace(A_STEP, binding=(("n0",),)), "$.binding[0]"),
    (Receipt("r1", "i1", "s1", "a1", 1), "$.applied"),
    ((A_STEP, 1.5), "$[1]"),
    ([A_STEP], "$"),
])
def test_encode_refuses_what_the_annotations_do_not_admit(value, path) -> None:
    with pytest.raises(transport.TransportRefused) as refused:
        transport.encode(value)
    assert refused.value.path == path


# --- instants ---------------------------------------------------------------------------------------


# An instant survives encode, JSON text and decode alone, in an array and in an optional field's union
# as the same instant, decoded in UTC and written as its one UTC text.
# am[verifies a-jk-wire-datetime-1018@918fa0]
@SETTINGS
@given(INSTANTS)
def test_every_instant_survives_json_text_as_itself_in_utc(moment) -> None:
    text = moment.astimezone(timezone.utc).isoformat()
    for value, expected, payload in ((moment, datetime, text), ((moment, moment), tuple[datetime, ...], [text, text]),
                                     (moment, datetime | None, text)):
        assert transport.encode(value) == payload
        decoded = transport.decode(json.loads(json.dumps(payload)), expected)
        assert decoded == value
        assert all(item.utcoffset() == timedelta(0) for item in (decoded if type(decoded) is tuple else (decoded,)))
    assert transport.decode(None, datetime | None) is None


# Every spelling of one instant the receipts' parser reads, a Z, another offset, an offset with
# seconds or with a fraction of a second, the basic format or trailing zero digits past the
# microsecond, decodes to that instant and encodes to its one text. An offset under one second moves
# the instant too: "+00:00:00.5" on 02:34:00.5 is 02:34:00 in UTC, not 02:34:00.5.
# am[verifies a-jk-wire-datetime-1018@918fa0] am[verifies a-jk-wire-subsecond-regression-1018@744226]
@pytest.mark.parametrize("text", [
    "2026-10-18T02:34:00+00:00",
    "2026-10-18T02:34:00Z",
    "2026-10-18T13:34:00+11:00",
    "2026-10-17T21:34:00-05:00",
    "2026-10-18T02:34:01+00:00:01",
    "2026-10-18T02:34:00.5+00:00:00.5",
    "2026-10-18T02:33:59.500000-00:00:00.500000",
    "20261018T023400+0000",
    "20261018T023400.5+000000.5",
    "2026-10-18T02:34:00.000000+00:00",
    "2026-10-18T02:34:00.0000000+00:00",
])
def test_every_spelling_of_one_instant_decodes_to_it_and_encodes_to_one_text(text) -> None:
    decoded = transport.decode(text, datetime)
    assert decoded == datetime(2026, 10, 18, 2, 34, tzinfo=timezone.utc)
    assert decoded.utcoffset() == timedelta(0)
    assert transport.encode(decoded) == "2026-10-18T02:34:00+00:00"


# Where a datetime is declared, anything but text naming an instant UTC holds is refused at its path:
# another JSON type, text that is no ISO-8601 time, one with no offset, a digit finer than a
# microsecond, and a time at either end of the years whose UTC time falls outside them, by hours or
# by an offset under one second.
# am[verifies a-jk-wire-datetime-1018@918fa0] am[verifies a-jk-wire-subsecond-regression-1018@744226]
@pytest.mark.parametrize(("payload", "reason"), [
    (0, "not an integer"),
    (1.5, "not a number"),
    (True, "not a boolean"),
    (None, "not null"),
    ([], "not an array"),
    ({}, "not an object"),
    ("", "must be an ISO-8601 time"),
    ("not-a-time", "must be an ISO-8601 time"),
    ("2026-10-18T02:34:00", "must carry a timezone offset"),
    ("2026-10-18", "must carry a timezone offset"),
    ("2026-10-18T02:34:00.1234567+00:00", "must not be finer than a microsecond"),
    ("0001-01-01T00:00:00+05:00", "has no UTC time"),
    ("9999-12-31T23:59:59-05:00", "has no UTC time"),
    ("0001-01-01T00:00:00.1+00:00:00.5", "has no UTC time"),
    ("9999-12-31T23:59:59.9-00:00:00.5", "has no UTC time"),
])
def test_a_time_naming_no_instant_utc_holds_is_refused_at_its_path(payload, reason) -> None:
    with pytest.raises(transport.TransportRefused) as refused:
        transport.decode(["2026-10-18T02:34:00+00:00", payload], tuple[datetime, ...])
    assert refused.value.path == "$[1]"
    assert reason in refused.value.reason


# Encoding refuses a datetime naming no instant, a naive one, and one whose UTC time falls outside the
# years 1 to 9999, at its path, and a date, which is no planner value.
# am[verifies a-jk-wire-datetime-1018@918fa0]
@pytest.mark.parametrize(("value", "path", "reason"), [
    (datetime(2026, 10, 18, 2, 34), "$", "naive"),
    ((datetime(2026, 10, 18, 2, 34, tzinfo=timezone.utc), datetime(2026, 10, 18, 2, 34)), "$[1]", "naive"),
    (datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=5))), "$", "has no UTC time"),
    (datetime(9999, 12, 31, 23, 59, tzinfo=timezone(timedelta(hours=-5))), "$", "has no UTC time"),
    (date(2026, 10, 18), "$", "is no planner record"),
])
def test_encode_refuses_a_datetime_naming_no_instant_utc_holds(value, path, reason) -> None:
    with pytest.raises(transport.TransportRefused) as refused:
        transport.encode(value)
    assert refused.value.path == path
    assert reason in refused.value.reason


# Any one corruption of an array of instants, the array or an item, is refused at that site's path.
# am[verifies a-jk-wire-datetime-1018@918fa0]
@SETTINGS
@given(st.lists(INSTANTS, min_size=1, max_size=3), st.data())
def test_every_single_site_corruption_of_instants_is_refused_at_its_path(moments, data) -> None:
    payload = transport.encode(tuple(moments))
    site = data.draw(st.sampled_from(list(sites(payload, tuple[datetime, ...]))))
    corrupt = data.draw(st.sampled_from(corruptions(site, at(payload, site.keys))))
    with pytest.raises(transport.TransportRefused) as refused:
        transport.decode(replaced(payload, site.keys, corrupt), tuple[datetime, ...])
    assert refused.value.path == site.path, refused.value.reason


# A datetime builds its schema beside null, an integer Literal and inside an array, whose JSON types
# tell them apart.
# am[verifies a-jk-wire-datetime-1018@918fa0]
def test_a_datetime_builds_its_schema_beside_other_json_types() -> None:
    assert transport._schema((datetime | None, tuple[datetime, ...], Literal[1] | datetime)) == {}


# A union holding a datetime beside a string or a string Literal fails when the schema is built: both
# are JSON strings, so a time would decode as whichever member came first.
# am[verifies a-jk-wire-datetime-1018@918fa0]
@pytest.mark.parametrize("root", [str | datetime, datetime | Literal["2026-10-18T02:34:00+00:00"],
                                  tuple[datetime | str | None, ...]])
def test_a_datetime_beside_a_string_fails_when_the_schema_is_built(root) -> None:
    with pytest.raises(TypeError, match="cannot tell a datetime from a string"):
        transport._schema((root,))


# --- the closed set ---------------------------------------------------------------------------------


# The records are exactly what the API's roots reach through field annotations: every root member is
# one, every record a record's annotations name is one, and each is a frozen dataclass of the planner.
# am[verifies a-jk-wire-impl-1018@c09e04]
def test_the_records_are_what_the_roots_reach() -> None:
    def named(annotation):
        origin, args = get_origin(annotation), get_args(annotation)
        if dataclasses.is_dataclass(annotation):
            return {annotation}
        return set().union(*(named(arg) for arg in args if arg is not Ellipsis)) if args else set()

    reached, pending = set(), [*transport.ROOTS]
    while pending:
        for cls in named(pending.pop()) - reached:
            reached.add(cls)
            pending.extend(get_type_hints(cls).values())
    assert set(transport.RECORDS.values()) == reached
    assert {name for name in transport.RECORDS} == {cls.__name__ for cls in reached}
    assert all(cls.__dataclass_params__.frozen for cls in reached)
    assert {cls.__module__ for cls in reached} == {"goal_chainer.planning.projection", "goal_chainer.planning.procedures"}


# Record shapes the transport cannot carry: a float field, a mutable record, a field outside the
# constructor.
# am[implements a-jk-wire-tests-1018@dbe611]
@dataclasses.dataclass(frozen=True)
class _Gauge:
    reading: float


# am[implements a-jk-wire-tests-1018@dbe611]
@dataclasses.dataclass
class _Mutable:
    name: str


# am[implements a-jk-wire-tests-1018@dbe611]
@dataclasses.dataclass(frozen=True)
class _Derived:
    name: str
    size: int = dataclasses.field(init=False, default=0)


# A record the transport could not carry faithfully fails when the schema is built, never silently.
# am[verifies a-jk-wire-impl-1018@c09e04]
@pytest.mark.parametrize("root", [_Gauge, _Mutable, _Derived, tuple[_Gauge, ...], float | None])
def test_a_record_the_transport_cannot_carry_fails_when_the_schema_is_built(root) -> None:
    with pytest.raises(TypeError):
        transport._schema((root,))

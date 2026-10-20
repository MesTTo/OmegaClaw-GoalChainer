"""Purpose: verify the shared reading of a versioned protocol's printed output through both of its
consumers, the SNARS and directive parsers: every line beginning with a record's marker must read as
one four-part record, so a malformed candidate beside a valid record fails the output closed wherever
it stands, while lines without the marker around the one record are the program's own output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pytest
from hypothesis import example, given, settings, strategies as st

from goal_chainer.directive_models import DirectiveProtocolError
from goal_chainer.directive_protocol import parse_directive_output
from goal_chainer.errors import ProtocolError
from goal_chainer.sexpr.codec import SexprCodec
from goal_chainer.snars_protocol import parse_protocol_output

CODEC = SexprCodec()


# One consumer of the shared parser: how it reads printed lines, the record it accepts, and the
# error it raises for output it refuses.
# am[verifies a-integrate-protocol-candidates-strict-1018@0c6030]
@dataclass(frozen=True)
class Consumer:
    read: Callable[[list[str]], Any]
    version: str
    operation: str
    payload: str
    error: type[Exception]

    @property
    def record(self) -> str:
        return f"({self.version} {self.operation} ok {self.payload})"


CONSUMERS = {
    "snars": Consumer(lambda lines: parse_protocol_output(lines, CODEC, expected_operation="ask"),
                      "goalchainer-snars-v1", "ask", "(answers ())", ProtocolError),
    "directive": Consumer(lambda lines: parse_directive_output(lines, CODEC, expected_operation="task-state"),
                          "goalchainer-directive-v1", "task-state", "(task-state collect ready)",
                          DirectiveProtocolError),
}
# The program's own output: lines of any text that do not begin with a record marker.
HUMAN = st.lists(st.text(st.characters(blacklist_categories=("Cs",), blacklist_characters="\n"), max_size=30)
                 .filter(lambda line: not line.lstrip().startswith("(goalchainer-")), max_size=3)
# How a candidate breaks: its head left open, as a record continued onto later lines starts; cut
# short anywhere after its marker; a field short; a field over; or a second form after it.
FLAWS = ("open", "cut", "short", "over", "trailing")


# The candidate a flaw makes of a consumer's record; `n` is how many characters a cut drops.
# am[verifies a-integrate-protocol-candidates-strict-1018@0c6030]
def _malformed(consumer: Consumer, flaw: str, n: int) -> str:
    record, head = consumer.record, f"({consumer.version} {consumer.operation} ok"
    return {
        "open": head,
        "cut": record[: len(record) - min(n, len(record) - len(f"({consumer.version}"))],
        "short": f"{head})",
        "over": f"{head} {consumer.payload} extra)",
        "trailing": f"{record} (extra)",
    }[flaw]


# A malformed candidate fails the output closed beside a valid record, before or after it, whatever
# the program prints around and between them. The examples are the measured probe's three
# candidates, left open, a field short and a field over, each before and after the record.
# am[verifies a-integrate-protocol-candidates-strict-1018@0c6030] am[verifies c-integrate-protocol-malformed-record-hidden-1018@7eca87]
@pytest.mark.parametrize("consumer", CONSUMERS.values(), ids=CONSUMERS)
@settings(max_examples=150, deadline=None)
@given(flaw=st.sampled_from(FLAWS), n=st.integers(1, 80), first=st.booleans(), before=HUMAN, between=HUMAN,
       after=HUMAN)
@example(flaw="open", n=1, first=True, before=[], between=[], after=[])
@example(flaw="open", n=1, first=False, before=[], between=[], after=[])
@example(flaw="short", n=1, first=True, before=[], between=[], after=[])
@example(flaw="short", n=1, first=False, before=[], between=[], after=[])
@example(flaw="over", n=1, first=True, before=[], between=[], after=[])
@example(flaw="over", n=1, first=False, before=[], between=[], after=[])
def test_a_malformed_candidate_beside_a_valid_record_fails_closed(
    consumer: Consumer, flaw: str, n: int, first: bool, before: list[str], between: list[str], after: list[str]
) -> None:
    bad = _malformed(consumer, flaw, n)
    one, two = (bad, consumer.record) if first else (consumer.record, bad)

    with pytest.raises(consumer.error, match="malformed") as raised:
        consumer.read([*before, one, *between, two, *after])

    assert [entry["line"] for entry in raised.value.details["malformed"]] == [bad]


# Lines without a marker around the one valid record are the program's own output and change nothing.
# am[verifies a-integrate-protocol-candidates-strict-1018@0c6030]
@pytest.mark.parametrize("consumer", CONSUMERS.values(), ids=CONSUMERS)
@settings(max_examples=100, deadline=None)
@given(before=HUMAN, after=HUMAN)
@example(before=["Starting the engine"], after=["Finished"])
def test_the_program_output_around_one_record_is_kept_apart(
    consumer: Consumer, before: list[str], after: list[str]
) -> None:
    assert consumer.read([*before, consumer.record, *after]).operation == consumer.operation

"""Purpose: hold the relevance records' one representation of time to its rules: every offset spelling the reader accepts names the instant it says, whichever interpreter's fromisoformat reads it, and a digit finer than a microsecond is refused, in a time or in an offset."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from goal_chainer.relevance.instants import microseconds, parse_instant, utc_text

MICROSECOND = timedelta(microseconds=1)
LOCAL = datetime(2026, 10, 18, 2, 34)
# Every offset a timezone can hold: strictly inside a day, to the microsecond.
OFFSETS = st.timedeltas(min_value=timedelta(days=-1) + MICROSECOND, max_value=timedelta(days=1) - MICROSECOND)


# What isoformat writes for any offset reads back as the same instant with the same offset, the
# round trip fromisoformat is documented to give and CPython's C reader broke before gh-152079 for
# an offset under one second, the measured cases among the examples.
# am[verifies a-integrate-instant-offset-preservation-1018@439390] am[verifies c-rel-cpython-subsecond-offset-1018@db4d26]
@settings(max_examples=300)
@given(moment=st.datetimes(min_value=datetime(1900, 1, 2), max_value=datetime(2200, 12, 30),
                           timezones=st.builds(timezone, OFFSETS)))
@example(moment=LOCAL.replace(tzinfo=timezone(timedelta(milliseconds=500))))
@example(moment=LOCAL.replace(tzinfo=timezone(timedelta(milliseconds=-500))))
@example(moment=LOCAL.replace(tzinfo=timezone(MICROSECOND)))
@example(moment=LOCAL.replace(tzinfo=timezone(-MICROSECOND)))
@example(moment=LOCAL.replace(tzinfo=timezone(timedelta(milliseconds=1500))))
def test_every_offset_isoformat_writes_reads_back_as_its_own_instant(moment: datetime) -> None:
    read = parse_instant(moment.isoformat())

    assert (read, read.utcoffset()) == (moment, moment.utcoffset())
    assert (microseconds(read), utc_text(read)) == (microseconds(moment), utc_text(moment))


# An offset as fromisoformat reads it: two-digit hours, then optional minutes, seconds and a
# fraction, with colons or without, a point or a comma, and a fraction of any length whose digits
# past the sixth are zeros; answered with the offset it names.
# am[related a-integrate-instant-offset-preservation-1018@439390]
@st.composite
def spelled_offsets(draw) -> tuple[str, timedelta]:
    sign = draw(st.sampled_from(["+", "-"]))
    hours, minutes, seconds = draw(st.integers(0, 23)), draw(st.integers(0, 59)), draw(st.integers(0, 59))
    parts = draw(st.integers(1, 4))
    colon, point = draw(st.sampled_from([":", ""])), draw(st.sampled_from([".", ","]))
    digits = draw(st.integers(1, 9))
    fraction = draw(st.integers(0, 10 ** min(digits, 6) - 1))
    written = f"{hours:02d}" + (f"{colon}{minutes:02d}" if parts > 1 else "") + (
        f"{colon}{seconds:02d}" if parts > 2 else "") + (
        f"{point}{fraction:0{min(digits, 6)}d}{'0' * max(digits - 6, 0)}" if parts > 3 else "")
    offset = timedelta(hours=hours, minutes=minutes if parts > 1 else 0, seconds=seconds if parts > 2 else 0,
                       microseconds=fraction * 10 ** (6 - min(digits, 6)) if parts > 3 else 0)
    return sign + written, -offset if sign == "-" else offset


# Every offset spelling the reader accepts names the instant its local time less its offset,
# whatever fromisoformat makes of it.
# am[verifies a-integrate-instant-offset-preservation-1018@439390] am[verifies c-rel-offset-read-from-text-1018@95fbdf]
@settings(max_examples=300)
@given(spelled=spelled_offsets())
@example(spelled=("+00:00:00.500000", timedelta(milliseconds=500)))
@example(spelled=("-00:00:00.000001", -MICROSECOND))
@example(spelled=("+000000,5", timedelta(milliseconds=500)))
@example(spelled=("-00:00:00.5000000", timedelta(milliseconds=-500)))
def test_every_accepted_offset_spelling_names_its_own_instant(spelled: tuple[str, timedelta]) -> None:
    written, offset = spelled

    read = parse_instant(f"2026-10-18T02:34:00{written}")

    assert read.utcoffset() == offset
    assert read == (LOCAL - offset).replace(tzinfo=timezone.utc)


# The offset is the text's last sign through its end whatever comes before it: a sign as the
# separator, a week date, the basic format.
# am[verifies a-integrate-instant-offset-preservation-1018@439390] am[verifies c-rel-offset-read-from-text-1018@95fbdf]
@pytest.mark.parametrize(
    "written, offset",
    [
        ("2026-10-18+02:34:00-00:00:00.5", timedelta(milliseconds=-500)),
        ("2026-10-18-02:34:00+00:00:00.5", timedelta(milliseconds=500)),
        ("2026-W42-7T02:34:00-00:00:00.5", timedelta(milliseconds=-500)),
        ("20261018T023400+000000.5", timedelta(milliseconds=500)),
        ("2026-10-18 02:34+05", timedelta(hours=5)),
    ],
    ids=["a plus separator", "a minus separator", "a week date", "the basic format", "hours alone"],
)
def test_the_offset_is_read_after_the_last_sign_whatever_comes_before_it(written: str, offset: timedelta) -> None:
    read = parse_instant(written)

    assert read.utcoffset() == offset
    assert read == (LOCAL - offset).replace(tzinfo=timezone.utc)


# Z and both signs of a zero offset name UTC.
# am[verifies a-integrate-instant-offset-preservation-1018@439390]
@pytest.mark.parametrize("written", ["Z", "+00:00", "-00:00"])
def test_a_zero_offset_reads_as_utc(written: str) -> None:
    assert parse_instant(f"2026-10-18T02:34:00{written}").utcoffset() == timedelta(0)


# An offset's fraction is held to the microsecond as a time's is.
# am[verifies a-integrate-instant-offset-preservation-1018@439390] am[verifies c-rel-fromisoformat-truncates-1017@616584]
@pytest.mark.parametrize("written", ["2026-10-18T02:34:00+00:00:00.0000001", "2026-10-18T02:34:00-05:30:00.1234567",
                                     "2026-10-18T02:34:00.0000001+05:30"])
def test_a_digit_finer_than_a_microsecond_is_refused_in_an_offset_or_a_time(written: str) -> None:
    with pytest.raises(ValueError, match="must not be finer than a microsecond"):
        parse_instant(written)

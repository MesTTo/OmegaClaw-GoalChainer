"""Purpose: the relevance records' one representation of time: read an exact timezone-aware instant from wire text, whatever offset it is written in, write it back as UTC text, and give the MeTTa policy its exact integer microseconds."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
# A decimal fraction anywhere in the text: the seconds' fraction, or one in an offset with seconds.
_FRACTION = re.compile(r"[.,](\d+)")
# An offset after its sign as fromisoformat reads it: two-digit hours, then optional minutes,
# seconds and a fraction, each but the fraction after an optional colon.
_OFFSET = re.compile(r"([+-])([0-9]{2})(?::?([0-9]{2})(?::?([0-9]{2})(?:[.,]([0-9]+))?)?)?")


# fromisoformat drops fraction digits past the sixth without an error, which would move an
# observation made 0.4 microseconds after an application onto it, so such a digit is refused.
# am[implements a-rel-rcpt-v2-instants-1017@3a3b0d] am[rests-on c-rel-fromisoformat-truncates-1017@616584]
# am[rests-on c-rel-rcpt-exact-instants-1017@c56a05] am[implements a-integrate-instant-offset-preservation-1018@439390]
def parse_instant(text: str) -> datetime:
    """The instant `text` names: ISO-8601 with a timezone offset, exact to the microsecond.

    Raises ValueError saying what is wrong: not an ISO-8601 time, no offset, or a digit finer than
    a microsecond (`09:02:00.1234567`). `09:02:00.1234560` names a whole microsecond and is read.
    Every offset fromisoformat accepts is read as written, `+00:00:00.5` included.
    """

    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError("must be an ISO-8601 time") from None
    if moment.tzinfo is None:
        raise ValueError("must carry a timezone offset")
    if any(digits[6:].strip("0") for digits in _FRACTION.findall(text)):
        raise ValueError("must not be finer than a microsecond")
    return moment.replace(tzinfo=_zone(text))


# The zone a time fromisoformat accepted names. CPython's C fromisoformat reads an offset whose
# hours, minutes and seconds are zero as UTC whatever its fraction (gh-152079, fixed in 3.14.7, still
# in 3.12 and every 3.13 release through 3.13.11), so "+00:00:00.5" named an instant half a second
# late. The value is read from the text instead, which ends in Z or in the offset after its last
# sign; fromisoformat still decides what is accepted and the local time.
# am[implements a-integrate-instant-offset-preservation-1018@439390] am[addresses i-integrate-instant-small-offset-lost-1018@bf8fdc]
# am[rests-on c-rel-cpython-subsecond-offset-1018@db4d26] am[rests-on c-rel-offset-read-from-text-1018@95fbdf]
def _zone(text: str) -> timezone:
    if text.endswith("Z"):
        return timezone.utc
    sign, hours, minutes, seconds, fraction = _OFFSET.fullmatch(text, max(text.rfind("+"), text.rfind("-"))).groups()
    offset = timedelta(hours=int(hours), minutes=int(minutes or 0), seconds=int(seconds or 0),
                       microseconds=int(f"{fraction or ''}000000"[:6]))
    if not offset:
        return timezone.utc
    return timezone(-offset if sign == "-" else offset)


# am[implements a-rel-rcpt-v2-instants-1017@3a3b0d] am[implements a-rel-signals-1016@16b33a]
def microseconds(moment: datetime) -> int:
    """A timezone-aware time as exact integer microseconds since the epoch, the policy's instants."""

    return (moment - _EPOCH) // timedelta(microseconds=1)


# am[implements a-rel-rcpt-v2-instants-1017@3a3b0d]
def utc_text(moment: datetime) -> str:
    """The instant as ISO-8601 in UTC, so every spelling of one instant is one text."""

    return moment.astimezone(timezone.utc).isoformat()

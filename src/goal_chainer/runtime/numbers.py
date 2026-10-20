"""Purpose: read a public number as the float it stands for, answering None for anything a finite
float cannot hold, so each validator of budgets and SNARS values refuses it with its own error."""

from __future__ import annotations

from math import isfinite


# A JSON integer can have any number of digits, and float() raises OverflowError for one beyond
# the float range, so a validator that converts or calls isfinite() before it compares let
# timeout_seconds, trust, positive, base_rate and now escape as untyped OverflowErrors.
# am[implements a-rt-nr-repair-1018@72901e] am[rests-on c-rt-nr-probe-bfd71102-1018@029356]
def finite_float(value: object) -> float | None:
    """`value` as a float when it is an int or a float, not a bool, whose float is finite; None
    for every other value, an int beyond the float range, infinity and NaN included."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except OverflowError:
        return None
    return result if isfinite(result) else None

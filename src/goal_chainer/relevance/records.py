"""Purpose: check that an external review record has the shape a consumer is about to read, failing as invalid-record.

A stored review record comes back from a host as plain JSON, so before the freshness check or
the receipt assessment reads a field, the field must exist with the right type, nested all the
way down. A shape is written the way the record looks:

    str                       text
    OPTIONAL_TEXT             text or null
    [shape]                   a list whose every item has `shape`
    {"key": shape, ...}       an object with at least these keys (others are ignored)
    {ANY_KEY: shape}          an object whose every value has `shape`

Each consumer declares only the fields it reads, so a record can grow without breaking an
older reader, and nothing it reads can fail later with a KeyError or TypeError.
"""

from __future__ import annotations

from typing import Any, Mapping

from .errors import RelevanceError

OPTIONAL_TEXT = (str, type(None))
ANY_KEY = "*"


# am[implements a-rel-review-contract-1016@d0bea9]
def check_record(value: Any, shape: Any, what: str) -> Any:
    """Return `value` unchanged when it has `shape`, else raise invalid-record naming the path."""

    _check(value, shape, what)
    return value


# Time: linear in the size of the checked part of the record.
# am[implements a-rel-review-contract-1016@d0bea9]
def _check(value: Any, shape: Any, path: str) -> None:
    if isinstance(shape, list):
        if not isinstance(value, list):
            raise _invalid(path, "a list")
        for index, item in enumerate(value):
            _check(item, shape[0], f"{path}[{index}]")
    elif isinstance(shape, dict):
        if not isinstance(value, Mapping):
            raise _invalid(path, "an object")
        if ANY_KEY in shape:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise _invalid(path, "an object with text keys")
                _check(item, shape[ANY_KEY], f"{path}.{key}")
        for key, item_shape in shape.items():
            if key == ANY_KEY:
                continue
            if key not in value:
                raise RelevanceError("invalid-record", f"{path} has no {key}")
            _check(value[key], item_shape, f"{path}.{key}")
    elif not isinstance(value, shape):
        raise _invalid(path, _describe(shape))


# am[implements a-rel-review-contract-1016@d0bea9]
def _describe(shape: Any) -> str:
    names = {str: "text", type(None): "null"}
    kinds = shape if isinstance(shape, tuple) else (shape,)
    return " or ".join(names.get(kind, kind.__name__) for kind in kinds)


# am[implements a-rel-review-contract-1016@d0bea9]
def _invalid(path: str, expected: str) -> RelevanceError:
    return RelevanceError("invalid-record", f"{path} must be {expected}")

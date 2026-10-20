"""Purpose: decode public JSON input with unique object names and finite floating-point numbers."""

import json
import math
from typing import Any


# The stdlib hooks inspect decoded names, so escaped and literal spellings are the same key.
# Time and space: linear in input length, with one dictionary per decoded object.
# am[implements a-v2-json-input-1020@b37a9e]
def loads(text: str) -> Any:
    """Read JSON or raise the stdlib's input errors; callers supply their own wire error code."""

    return json.loads(text, object_pairs_hook=_object, parse_float=_finite, parse_constant=_nonfinite)


# am[implements a-v2-json-input-1020@b37a9e]
def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key!r}")
        result[key] = value
    return result


# A legal exponent such as 1e999 also exceeds the runtime's finite float range.
# am[implements a-v2-json-input-1020@b37a9e]
def _finite(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        _nonfinite(text)
    return value


# am[implements a-v2-json-input-1020@b37a9e]
def _nonfinite(text: str) -> Any:
    raise ValueError(f"JSON number is not finite: {text}")

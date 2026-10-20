"""Purpose: the one serialization the relevance review's identities are computed over, and the SHA-256 identity of a payload under it, for the review fingerprint, the receipt's identities and a reading's observation id.

It sits below the review and the signals, so a reading can name its own observation without
importing the review that reads it (c-rel-agrees-dr-pj-observation-id-1018).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


# am[implements a-rel-review-contract-1016@d0bea9]
def canonical_json(payload: Mapping[str, Any]) -> str:
    """The one serialization fingerprints are computed over: sorted keys, no spaces, no NaN."""

    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


# am[implements a-rel-review-contract-1016@d0bea9]
def fingerprint_of(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

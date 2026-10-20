"""Purpose: the one typed failure every relevance operation raises, with a stable code for hosts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from ..errors import GoalChainerError

ErrorCode = Literal[
    "invalid-packet",
    "invalid-domain",
    "policy-version-mismatch",
    "subject-mismatch",
    "runtime-unavailable",
    "engine-failed",
    "review-budget-exceeded",
    "review-timeout",
    "engine-output-invalid",
    "theory-defect",
    "invalid-record",
    # A motivation snapshot that is not this review's: for a domain without needs, another domain
    # or another instant, or missing for a domain with needs.
    "invalid-motivation",
]

ERROR_CODES: frozenset[str] = frozenset(ErrorCode.__args__)  # type: ignore[attr-defined]


# am[implements a-rel-review-contract-1016@d0bea9]
# am[implements a-v2-unified-error-family-1020@c7807b]
class RelevanceError(GoalChainerError):
    """A relevance review, freshness check or receipt assessment that cannot produce a result.

    `code` is the wire contract: a host branches on it, never on the message.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown relevance error code: {code}")
        self.code = code
        super().__init__(message, details=details)

"""Purpose: GoalChainer's cross-encoder scoring of (question, passage) pairs, PassageRanker in the
scoring module, with the identity of the code that scores. Importing the package pins scoring with
goal_chainer.pinned, so whichever module imports it first, its compile reads one copy of the file and
never a bytecode cache, and scoring_identity() names that copy by its SHA-256: a reading's revision
digests it, so a change to how pairs are scored is a new reader revision even when the model's
weights stay the same."""

from pathlib import Path

from .. import pinned

# am[implements a-rpc-reading-scoring-identity-1019@452cee] am[rests-on c-rpc-pinned-module-identity-1019@b8dd99]
pinned.pin({f"{__name__}.scoring": Path(__file__).resolve().parent / "scoring.py"})

from .scoring import PassageRanker  # noqa: E402 (compiled by the pinned loader)

__all__ = ["PassageRanker", "scoring_identity"]


# A lookup of the digest the pinned compile took, so no read hashes anything.
# am[implements a-rpc-reading-scoring-identity-1019@452cee] am[addresses i-rpc-reader-scoring-identity-1019@ea56eb]
def scoring_identity() -> str:
    """The SHA-256 of the bytes this process compiled the scoring module from. Raises ImportError
    when the module Python holds under its name is not the one the pinned loader compiled."""

    return pinned.loaded([f"{__name__}.scoring"])[0][1]

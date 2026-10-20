"""Purpose: GoalChainer's machine-readable failures: GoalChainerError carries a message, read-only
details and a stable code, and its subclasses are the failure kinds every layer raises, so no layer
imports another's models to fail, and safe_repr writes the value a refusal rejected into its details
without failing. docs/errors.md lists each code."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType


# A failure's message, its read-only details and its code. The code is part of the CLI's and the
# OmegaClaw skill's JSON (to_dict), so a subclass keeps its code whatever its class is called.
# am[implements a-rt-rb-errors-sexpr-1018@f482e5] am[implements a-rt-runtime-boundary-1017@8c9cd8]
class GoalChainerError(Exception):
    """Base class for stable, machine-readable GoalChainer failures."""

    code = "goalchainer_error"

    def __init__(self, message: str, *, details: Mapping[str, object] | None = None) -> None:
        if not isinstance(message, str):
            raise TypeError("message must be a string")
        if not message.strip():
            raise ValueError("message must be nonempty")
        if details is not None and not isinstance(details, Mapping):
            raise TypeError("details must be a mapping")
        self.message = message
        self.details: Mapping[str, object] = MappingProxyType(dict(details or {}))
        super().__init__(message)

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}


# am[implements a-rt-rb-errors-sexpr-1018@f482e5]
class DependencyUnavailableError(GoalChainerError):
    code = "dependency_unavailable"


# A text the semantic reader could not read because Jev gave no answer. details["reason"] names
# which of seven: not_cached, the answer is not in the replay cache, and refused, Jev refused the
# text, as when it is too long, describe the text or its cache; no_key, unauthorized,
# rate_limited, unreachable and service_error are failures of the service. A caller may report a
# text unread only for the first two, the memory policy's (gc-memory-text-omissions), and every
# other reason, like every other error, fails the decision.
# am[implements a-jev-client-1016@62f0db]
# am[rests-on c-mind-answer-cache-1016@095076]
# am[rests-on c-ev-missing-answer-reasons-1017@e499af]
class MissingAnswerError(DependencyUnavailableError):
    code = "missing_answer"


# am[implements a-rt-rb-errors-sexpr-1018@f482e5]
class InvalidInputError(GoalChainerError):
    code = "invalid_input"


# am[implements a-rt-rb-errors-sexpr-1018@f482e5]
class ProtocolError(GoalChainerError):
    code = "protocol_error"


# The MeTTa engine refused a program or answered it malformed. Its code was petta_execution_error
# while PeTTa ran GoalChainer's programs; pymetta raises its own EngineError, so this class takes
# another name (c-rt-engineerror-name-taken-1018).
# am[implements a-rt-rb-errors-sexpr-1018@f482e5] am[rests-on c-rt-engineerror-name-taken-1018@522074]
class MettaEngineError(GoalChainerError):
    code = "engine_error"


# am[implements a-rt-rb-errors-sexpr-1018@f482e5]
class PersistenceError(GoalChainerError):
    code = "persistence_error"


# A module's bytes on disk are not the bytes this process loaded from it: raised by the engine's
# module loader and by the pinned compile of Python helpers, both of which name what they run by
# the digest of what they loaded.
# am[implements a-rt-loaded-identity-1016@e4ffa3] am[implements a-rt-rb-codec-1018@e3e552]
class ModuleChanged(GoalChainerError):
    """A module's bytes on disk are not the bytes this process loaded from it: `loaded` is the
    digest of what was loaded, `current` of what is there now."""

    code = "module_changed"

    def __init__(self, path: Path, loaded: str, current: str, *, while_importing: bool = False) -> None:
        if while_importing:
            message = (
                f"{path} changed while it was being imported, so it was not recorded; the next "
                "load imports it again."
            )
        else:
            message = (
                f"{path} changed after this process imported it. The engine still runs what it "
                "imported, so the new bytes need a fresh process."
            )
        super().__init__(message, details={"path": str(path), "loaded": loaded, "current": current})
        self.path = path
        self.loaded = loaded
        self.current = current


# A refusal writes the value it rejected into its details and must still be its own typed error
# whatever that value is, while repr can raise: ValueError for an int of more digits than
# sys.get_int_max_str_digits() or a container holding one (c-sn-overflow-and-digit-limits-1018),
# RecursionError for a value nested past the C stack, and whatever a value's own __repr__ raises.
# pytest's saferepr and the traceback module write such a value as a placeholder naming it
# (c-rt-rr-safe-repr-prior-art-1018); this one carries no address, so the same value gets the same
# details in every process. KeyboardInterrupt and SystemExit are not Exceptions and still propagate.
# am[implements a-rt-rr-safe-repr-1018@ec9700] am[rests-on c-rt-rr-repro-95274904-1018@aad4b8]
# am[rests-on c-rt-rr-safe-repr-prior-art-1018@071cf0] am[rests-on c-sn-overflow-and-digit-limits-1018@0e7f7d]
def safe_repr(value: object) -> str:
    """repr(value), for a refusal's details, or a name for the value where repr raises: an int past
    the digit limit is "an integer of more than 4300 digits", "a negative integer ..." below zero,
    naming the limit in force, and any other value "a value of type list whose repr raised
    ValueError", naming its type and the exception."""

    try:
        return repr(value)
    except Exception as error:  # the value's own __repr__ runs here and may raise anything
        if type(value) is int and isinstance(error, ValueError):
            sign = "a negative" if value < 0 else "an"
            return f"{sign} integer of more than {sys.get_int_max_str_digits()} digits"
        return f"a value of type {type(value).__name__} whose repr raised {type(error).__name__}"


__all__ = [
    "DependencyUnavailableError",
    "GoalChainerError",
    "InvalidInputError",
    "MettaEngineError",
    "MissingAnswerError",
    "ModuleChanged",
    "PersistenceError",
    "ProtocolError",
    "safe_repr",
]

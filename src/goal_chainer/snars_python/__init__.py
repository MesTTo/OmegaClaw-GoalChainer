"""Purpose: the Python half of GoalChainer's SNARS library: Mettabase c079c89's term-normal-form
(tnf) and SH-term English (english) modules, and the top-level goalchainer_snars py-call module that
serves them to the MeTTa library. Importing this package pins all three with goal_chainer.pinned, so
each compiles from one read of its file, never from a bytecode cache, whichever of them Python
imports first, and every later compile of one, a reload included, must read those same bytes or
raises ModuleChanged before any of its code runs. loaded() pairs each file SNARS's py-calls run,
goal_chainer.sexpr.syntax's included, with the SHA-256 of the bytes this process compiled it from.
tnf and english are under Mettabase's MIT licence, ../snars_library/LICENSE;
../snars_library/PROVENANCE.md says what was taken and changed."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from .. import pinned, sexpr

__all__ = ["english", "loaded", "tnf"]

# goalchainer_snars is found where a plain import finds it, or where an earlier pin of it serves it.
# am[implements a-rt-helpers-compiled-from-read-1017@11c85b] am[implements a-rt-rb-codec-1018@e3e552]
_PY_CALLS = importlib.util.find_spec("goalchainer_snars")
if _PY_CALLS is None or _PY_CALLS.origin is None:
    raise ModuleNotFoundError("No module named 'goalchainer_snars'", name="goalchainer_snars")
pinned.pin({
    "goalchainer_snars": Path(_PY_CALLS.origin),
    **{f"{__name__}.{stem}": Path(__file__).resolve().parent / f"{stem}.py" for stem in ("english", "tnf")},
})

from . import english, tnf  # noqa: E402 (compiled by the pinned loader)
import goalchainer_snars  # noqa: E402,F401 (compiled by the pinned loader)

# Every module SNARS's py-calls run, the py-call module first, in the order the world identity
# digests them; the syntax module is pinned by goal_chainer.sexpr, which this package imports first.
# am[implements a-rt-helpers-compiled-from-read-1017@11c85b] am[implements a-rt-rb-codec-1018@e3e552]
_RUN_BY_PY_CALLS = ("goalchainer_snars", f"{__name__}.english", f"{sexpr.__name__}.syntax", f"{__name__}.tnf")


# am[implements a-rt-helpers-compiled-from-read-1017@11c85b] am[implements a-rt-helper-compiles-pinned-1017@b73a33]
def loaded() -> tuple[tuple[Path, str], ...]:
    """Each file SNARS's py-calls run, goalchainer_snars.py first, with the SHA-256 of the bytes this
    process compiled its module from. Raises ImportError when the module Python holds under one of
    their names is not the one the pinned loader compiled and ran, as when another import hook or a
    hand edit of sys.modules put a module in its place."""

    return pinned.loaded(_RUN_BY_PY_CALLS)

"""Purpose: read a domain's optional needs section, its gc-need and gc-need-expectation forms, into
one data-only NeedSection, and answer the section's facts, which the domain loader's validation
runner checks against the fault tables in needs.metta.

    (gc-need NEED GOAL (scale LO HI) (band LOW HIGH) (drive K) (need-source SOURCE))
    (gc-need-expectation ACTION NEED CHANGE ESTIMATOR (expectation-source SOURCE))

A need is a quantity the agent regulates on a declared numeric scale toward a target band, never
maximises: its level is observed, and how far the level lies outside the band, raised to the drive
exponent K, is how urgent the need is. Each need regulates one declared goal, whose declared
priority is the need's importance; the goal's weight is read, never changed. An expectation is a
declared numeric change of a need's level when an action is applied, with the estimator class and
the source that vouch for it; measured changes replace it once an attempt has been observed.

This module reads each form's shape only, the numbers a single form must satisfy included: a finite
scale with LO < HI whose width and twice it are finite doubles, a band inside it, a finite K of at
least 1 and a finite change. What forms must
satisfy together, such as a need's goal being declared, one need per goal and a change no larger
than its need's scale, is checked by the section's fault tables (CHECKS, through the typed entry
ENTRY) over the facts FACTS answers.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .forms import TopLevelForm
from .model import DomainError

# The section's form heads; the domain loader hands every form with one of these heads to
# read_section, so it never reads the section itself.
# am[implements a-v2m-need-forms-1019@6ee59c] am[rests-on c-rel-pj-loader-imports-section-readers-1018@4e1a4e]
HEADS = frozenset({"gc-need", "gc-need-expectation"})
# The section's fault tables, their typed entry and their warm-up, loaded into the domain loader's
# domain-checks module group.
# am[implements a-v2m-need-forms-1019@6ee59c] am[related a-rel-nd-section-warm-ups-1018@df1a66]
CHECKS = Path(__file__).resolve().with_name("needs.metta")
ENTRY = "gc-need-run-faults"
WARM_UP = "gc-need-checks-warm-up"


# am[implements a-v2m-need-forms-1019@6ee59c] am[rests-on c-v2m-level-reading-1019@a7e92b]
# am[rests-on c-v2-priority-provenance-boundary-1019@575bf7]
@dataclass(frozen=True, slots=True)
class Need:
    """A regulated quantity: its scale, its target band on that scale, its drive exponent, the goal
    it regulates and who declared the band and exponent.

    A Need is well formed by construction: its four bounds and its exponent are finite numbers,
    never booleans, with LO < HI, LO <= LOW <= HIGH <= HI and K >= 1, and its scale is representable:
    the width HI - LO and twice it are finite doubles, so every difference of two quantities on the
    scale, a change or a residual against a mean change, is finite too. Anything else is a
    ValueError, which the section's reader reports as the form's shape. K >= 1 makes the urgency
    x^K convex, small gaps pressing weakly and large ones sharply as eq. 2 intends, and K-Lipschitz
    in x on [0, 1], so over the reals a level one ulp off moves the urgency by at most K ulp/D; under
    K < 1 the slope at 0 is unbounded and one ulp moves it by (ulp/D)^K (c-v2m-drive-convex-1019).
    That bounds the real urgency's sensitivity to its input, not the error of evaluating it in
    floating point, which nothing bounds."""

    id: str
    goal: str
    scale: tuple[float, float]
    band: tuple[float, float]
    drive: float
    source: str

    # am[implements a-v2m-need-forms-1019@6ee59c] am[rests-on c-v2m-reduction-formula-1019@0fcd08]
    def __post_init__(self) -> None:
        (low_end, high_end), (low, high) = self.scale, self.band
        if not all(_finite(value) for value in (low_end, high_end, low, high, self.drive)):
            raise ValueError(f"need {self.id}: its scale, band and drive must be finite numbers")
        if not (self.drive >= 1 and low_end < high_end and low_end <= low <= high <= high_end):
            raise ValueError(f"need {self.id}: requires LO < HI, LO <= LOW <= HIGH <= HI and K >= 1")
        if not math.isfinite(2.0 * (float(high_end) - float(low_end))):
            raise ValueError(f"need {self.id}: its scale's width HI - LO, and twice it, must be finite doubles")
        # Each number is kept as a float with -0.0 made 0.0: canonical JSON writes the two
        # differently although they compare equal, so equal needs would otherwise fingerprint apart.
        object.__setattr__(self, "scale", (float(low_end) + 0.0, float(high_end) + 0.0))
        object.__setattr__(self, "band", (float(low) + 0.0, float(high) + 0.0))
        object.__setattr__(self, "drive", float(self.drive))


# am[implements a-v2m-need-forms-1019@6ee59c]
@dataclass(frozen=True, slots=True)
class NeedExpectation:
    """A declared change of a need's level, in its scale's units, when an action is applied."""

    action: str
    need: str
    change: float
    estimator: str
    source: str

    # am[implements a-v2m-need-forms-1019@6ee59c]
    def __post_init__(self) -> None:
        if not _finite(self.change):
            raise ValueError(f"the expected change of {self.need} under {self.action} must be a finite number")
        object.__setattr__(self, "change", float(self.change) + 0.0)


# am[implements a-v2m-need-forms-1019@6ee59c]
@dataclass(frozen=True, slots=True)
class NeedSection:
    """A domain's needs section, each kind of form in the order the file declares it."""

    needs: tuple[Need, ...] = ()
    expectations: tuple[NeedExpectation, ...] = ()


# am[implements a-v2m-need-forms-1019@6ee59c]
_SHAPES = {
    "gc-need": "(gc-need NEED GOAL (scale LO HI) (band LOW HIGH) (drive K) (need-source SOURCE)) "
               "with finite LO < HI whose width and twice it are finite, LO <= LOW <= HIGH <= HI and finite K >= 1",
    "gc-need-expectation": "(gc-need-expectation ACTION NEED CHANGE ESTIMATOR (expectation-source SOURCE)) "
                           "with a finite CHANGE",
}


# Each form is read by its head into one record; any form of the wrong shape raises DomainError
# naming the source, the form's text and the shape it should have.
# Time: linear in the forms' atoms.
# am[implements a-v2m-need-forms-1019@6ee59c] am[rests-on c-rel-pj-loader-imports-section-readers-1018@4e1a4e]
def read_section(forms: Iterable[tuple[TopLevelForm, Any]], source: str) -> NeedSection:
    """The needs section the (form, atom) pairs of HEADS forms declare; `source` names the file."""

    needs: list[Need] = []
    expectations: list[NeedExpectation] = []
    for form, atom in forms:
        parts = _children(atom)
        head = _symbol(parts[0]) if parts else None
        if head not in HEADS:
            raise DomainError(f"{source}: {form.text} is not a needs section form ({', '.join(sorted(HEADS))})")
        record = (_need if head == "gc-need" else _expectation)(parts[1:])
        if record is None:
            raise DomainError(f"{source}: {form.text} should be {_SHAPES[head]}")
        (needs if head == "gc-need" else expectations).append(record)
    return NeedSection(needs=tuple(needs), expectations=tuple(expectations))


# Each reader answers its record, or None when the arguments do not have the form's shape.
# am[implements a-v2m-need-forms-1019@6ee59c] am[rests-on c-v2m-reduction-formula-1019@0fcd08]
def _need(args: tuple[Any, ...]) -> Need | None:
    if len(args) != 6:
        return None
    need, goal = _symbol(args[0]), _symbol(args[1])
    scale, band = _numbers(_headed(args[2], "scale")), _numbers(_headed(args[3], "band"))
    drive, source = _headed(args[4], "drive"), _headed(args[5], "need-source")
    if None in (need, goal, scale, band, drive, source) or len(scale) != 2 or len(band) != 2:
        return None
    exponent = _number(drive[0]) if len(drive) == 1 else None
    named = _symbol(source[0]) if len(source) == 1 else None
    if exponent is None or named is None:
        return None
    try:
        return Need(need, goal, (scale[0], scale[1]), (band[0], band[1]), exponent, named)
    except ValueError:
        return None


# am[implements a-v2m-need-forms-1019@6ee59c]
def _expectation(args: tuple[Any, ...]) -> NeedExpectation | None:
    if len(args) != 5:
        return None
    action, need, change, estimator = _symbol(args[0]), _symbol(args[1]), _number(args[2]), _symbol(args[3])
    source = _headed(args[4], "expectation-source")
    named = _symbol(source[0]) if source is not None and len(source) == 1 else None
    if None in (action, need, change, estimator, named):
        return None
    return NeedExpectation(action, need, change, estimator, named)


# --- facts ---------------------------------------------------------------------------------------
# The section as the plain facts the validation runner reads, every name a string and every number
# a float: (Need ID GOAL), (NeedWidth ID WIDTH) with WIDTH = HI - LO, and
# (Expectation ACTION NEED CHANGE ESTIMATOR). needs.metta's header lists them.
# Time: linear in the section's records.
# am[implements a-v2m-need-forms-1019@6ee59c] am[related a-rel-nd-validation-runner-1018@f3f0b6]
def FACTS(section: NeedSection) -> tuple[tuple[Any, ...], ...]:  # noqa: N802 (the runner's section interface)
    """The section's facts in declaration order, kind by kind."""

    return (
        *(("Need", need.id, need.goal) for need in section.needs),
        *(("NeedWidth", need.id, need.scale[1] - need.scale[0]) for need in section.needs),
        *(("Expectation", item.action, item.need, item.change, item.estimator) for item in section.expectations),
    )


# --- atoms ---------------------------------------------------------------------------------------
# A name is a symbol, never a string, a number or a variable; a number is a finite int or float
# that is not a boolean, which pymetta reads as a grounded value.


# am[implements a-v2m-need-forms-1019@6ee59c] am[related a-rel-nd-pymetta-atoms-1018@f047df]
def _children(atom: Any) -> tuple[Any, ...] | None:
    from metta import Expression  # noqa: PLC0415 (pymetta is imported once a form is parsed)

    return tuple(atom.children) if isinstance(atom, Expression) else None


# am[implements a-v2m-need-forms-1019@6ee59c]
def _symbol(atom: Any) -> str | None:
    from metta import Symbol  # noqa: PLC0415

    return str(atom) if isinstance(atom, Symbol) else None


# pymetta reads nan and inf as symbols, so a grounded number is finite unless it is an integer
# beyond the float range, which float() refuses with OverflowError.
# am[implements a-v2m-need-forms-1019@6ee59c] am[related a-rel-finite-number-1017@924176]
def _number(atom: Any) -> float | None:
    from metta import Grounded  # noqa: PLC0415

    value = atom.value if isinstance(atom, Grounded) else None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


# A number a record may hold: an int or a float, never a boolean, that is finite; math.isfinite
# raises OverflowError for an integer beyond the float range, which has no finite float either.
# am[implements a-v2m-need-forms-1019@6ee59c]
def _finite(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


# am[implements a-v2m-need-forms-1019@6ee59c]
def _numbers(atoms: tuple[Any, ...] | None) -> tuple[float, ...] | None:
    if atoms is None:
        return None
    numbers = tuple(_number(atom) for atom in atoms)
    return None if any(number is None for number in numbers) else numbers


# The arguments of an expression headed HEAD, or None for any other atom.
# am[implements a-v2m-need-forms-1019@6ee59c]
def _headed(atom: Any, head: str) -> tuple[Any, ...] | None:
    parts = _children(atom)
    return parts[1:] if parts and _symbol(parts[0]) == head else None


__all__ = [
    "CHECKS",
    "ENTRY",
    "FACTS",
    "HEADS",
    "Need",
    "NeedExpectation",
    "NeedSection",
    "WARM_UP",
    "read_section",
]

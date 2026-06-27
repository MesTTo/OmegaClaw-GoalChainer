"""Compute the decision's combined score natively, as Prolog on PeTTa.

The motivation-path score (used whenever the MetaMo consensus is available) is
defined in `integrations/prolog/gc_score.pl` and loaded into PeTTa with
`import_prolog_functions_from_file`, so the decision arithmetic runs as a Prolog
relation called from MeTTa rather than in Python. The Python `_combined_score` stays
as the offline implementation; `tests/test_native_score.py` proves they agree.
"""

from __future__ import annotations

import re
from pathlib import Path

from .petta_runtime import run_metta

PROLOG_FILE = Path(__file__).resolve().parents[2] / "integrations/prolog/gc_score.pl"
_FLOAT_RE = re.compile(r"^-?[0-9]+\.?[0-9]*(?:[eE][+-]?[0-9]+)?$")


def available() -> bool:
    return PROLOG_FILE.exists()


def score_actions(rows: list[tuple[str, float, float, float]]) -> list[float]:
    """rows: (deontic, strength, confidence, motivation) per action, in order.
    Returns the native combined score per action (one PeTTa call)."""
    if not rows:
        return []
    calls = "\n".join(
        f"!(gc_score {deontic} {strength:.6f} {confidence:.6f} {motivation:.6f})"
        for deontic, strength, confidence, motivation in rows
    )
    program = (
        "!(import! &self (library lib_import))\n"
        f'!(import_prolog_functions_from_file "{PROLOG_FILE}" (gc_score))\n'
        f"{calls}\n"
    )
    outputs = run_metta(program)
    scores = [float(line) for line in outputs if _FLOAT_RE.match(line)]
    if len(scores) != len(rows):
        raise RuntimeError(f"native scorer returned {len(scores)} of {len(rows)} scores: {outputs}")
    return scores

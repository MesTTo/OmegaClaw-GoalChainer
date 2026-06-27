"""Run MeTTa on the PeTTa runtime (MeTTa compiled to SWI-Prolog).

OmegaClaw and its deontic/NAL libraries run on PeTTa, not on the hyperon binary.
This wraps the PeTTa entrypoint so the rest of GoalChainer can hand it a MeTTa
program and get the result lines back.

How PeTTa is driven (from reading PeTTa/src):
- `swipl -q -s PeTTa/src/main.pl -- <file>.metta --silent`
- `--silent` suppresses the compile/run trace, so stdout carries only the result
  of each `!(...)` form, one per line (filereader.pl, main.pl).
- `(library X Y)` resolves under `<PeTTa>/X/Y`, so `(library OmegaClaw-Core ...)`
  finds the fork vendored inside PeTTa.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

DEFAULT_PETTA_DIR = Path("/home/user/Dev/PeTTa")
DEFAULT_PETTA_SWIPL = Path("/home/user/Dev/swipl-9.3.33/build-petta/src/swipl")


def petta_dir() -> Path:
    path = Path(os.environ.get("GOALCHAINER_PETTA_DIR", DEFAULT_PETTA_DIR))
    if not (path / "src" / "main.pl").exists():
        raise RuntimeError(f"PeTTa runtime not found at {path} (no src/main.pl)")
    return path


def petta_swipl() -> str:
    configured = os.environ.get("GOALCHAINER_PETTA_SWIPL")
    if configured:
        return configured
    if DEFAULT_PETTA_SWIPL.exists():
        return str(DEFAULT_PETTA_SWIPL)
    return "swipl"


def run_metta(program: str) -> list[str]:
    """Run a MeTTa program on PeTTa and return the non-empty stdout result lines."""

    root = petta_dir()
    main_pl = root / "src" / "main.pl"
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".metta", encoding="utf-8") as handle:
        program_path = Path(handle.name)
        handle.write(program)
    try:
        result = subprocess.run(
            [
                petta_swipl(),
                "--stack_limit=8g",
                "-q",
                "-s",
                str(main_pl),
                "--",
                str(program_path),
                "--silent",
            ],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        program_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(
            "PeTTa execution failed:\n"
            f"swipl={petta_swipl()} main={main_pl}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr[-2000:]}"
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]

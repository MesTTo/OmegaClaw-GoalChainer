"""Run MeTTa on the PeTTa runtime (MeTTa compiled to SWI-Prolog).

OmegaClaw and its deontic/NAL libraries run on PeTTa, not on the hyperon binary.
This wraps the PeTTa entrypoint so the rest of GoalChainer can hand it a MeTTa
program and get the result lines back.

How PeTTa is driven (from reading PeTTa/src):
- `swipl -q -s PeTTa/src/main.pl -- <file>.metta --silent`
- `--silent` suppresses the compile/run trace, so stdout carries only the result
  of each `!(...)` form, one per line (filereader.pl, main.pl).
- A two-argument `(library X Y)` resolves Y under a registered `library_path`
  whose directory ends in X, so `library_prelude` below registers the deontic
  plugin's own directory before any program imports through it. PeTTa resolved
  this against `<PeTTa>/X/Y` until 72a10ef, which is why programs used to need
  no prelude.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

DEFAULT_PETTA_DIR = Path("/home/user/Dev/PeTTa")
DEFAULT_PETTA_SWIPL = Path("/home/user/Dev/swipl-9.3.33/build-petta/src/swipl")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OMEGACLAW_DIR = REPO_ROOT / "external" / "OmegaClaw-Core"
DEVELOPMENT_OMEGACLAW_DIR = Path("/home/user/Dev/OmegaClaw-Core")


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


def omegaclaw_dir() -> Path:
    """The pinned OmegaClaw checkout the deontic and GoalChainer plugins live in."""

    configured = os.environ.get("GOALCHAINER_OMEGACLAW_DIR")
    if configured:
        path = Path(configured).expanduser()
    elif DEFAULT_OMEGACLAW_DIR.is_dir():
        path = DEFAULT_OMEGACLAW_DIR
    else:
        path = DEVELOPMENT_OMEGACLAW_DIR
    resolved = path.resolve()
    # The name check is a sanity guard on being pointed at the right tree, not a
    # resolution requirement: the plugins register their own directories, so
    # nothing downstream depends on what this one is called.
    if resolved.name != "OmegaClaw-Core" or not resolved.is_dir():
        raise RuntimeError(f"OmegaClaw-Core checkout not found at {resolved}")
    return resolved


def library_prelude(path: Path | None = None) -> str:
    """Register the deontic plugin so `(library deontic X)` resolves.

    The plugin registers itself when the agent loads it; a program GoalChainer
    generates has no plugin loader, so it registers the same directory here. The
    path is absolute, so the program resolves the same wherever it is written and
    whatever the process working directory is, and it goes through
    posixpath.abspath so the term is the atom the plugin would have asserted
    rather than a quoted string.

    Retract-then-asserta keeps it at one fact, because two library_path entries
    ending in the same name resolve every import twice and double every answer.
    """

    resolved = path if path is not None else omegaclaw_dir()
    plugin = resolved / "plugins" / "deontic"
    registration = f'(Predicate (library_path (py-call (posixpath.abspath "{plugin}"))))'
    return f"!(retractPredicate {registration})\n!(assertaPredicate {registration})\n"


def run_metta(program: str, work_dir: Path | None = None) -> list[str]:
    """Run a MeTTa program on PeTTa and return the non-empty stdout result lines.

    PeTTa sets its `working_dir` (used to resolve relative `import!`) to the program
    file's directory. Pass `work_dir` to place the file where a library's relative
    imports resolve, e.g. PeTTaChainer's `metta/` directory.
    """

    root = petta_dir()
    main_pl = root / "src" / "main.pl"
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        suffix=".metta",
        encoding="utf-8",
        dir=str(work_dir) if work_dir is not None else None,
    ) as handle:
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

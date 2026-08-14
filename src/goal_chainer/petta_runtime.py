"""Run MeTTa on the PeTTa runtime (MeTTa compiled to SWI-Prolog).

OmegaClaw and its deontic/NAL libraries run on PeTTa, not on the hyperon binary.
This wraps the PeTTa entrypoint so the rest of GoalChainer can hand it a MeTTa
program and get the result lines back.

How PeTTa is driven (from reading PeTTa/src):
- `swipl -q -s PeTTa/src/main.pl -- <file>.metta --silent`
- `--silent` suppresses the compile/run trace, so stdout carries only the result
  of each `!(...)` form, one per line (filereader.pl, main.pl).
- A two-argument `(library X Y)` resolves Y under a registered `library_path`
  whose directory ends in X, and `git-import!` is what registers one. On a
  directory that already exists it registers and returns without cloning, so
  `library_prelude` below points PeTTa at the pinned OmegaClaw checkout without
  touching the network. PeTTa resolved this against `<PeTTa>/X/Y` until 72a10ef,
  which is why programs used to need no prelude.
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
OMEGACLAW_REPO_URL = "https://github.com/asi-alliance/OmegaClaw-Core.git"


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
    # git-import! derives the directory name from the repository URL, so the
    # checkout has to keep its own name for the registration to find it.
    if resolved.name != "OmegaClaw-Core" or not resolved.is_dir():
        raise RuntimeError(f"OmegaClaw-Core checkout not found at {resolved}")
    return resolved


def library_prelude(path: Path | None = None) -> str:
    """Register one OmegaClaw checkout so `(library OmegaClaw-Core X)` resolves.

    The base directory is absolute, so the program resolves the same wherever it
    is written and whatever the process working directory is.
    """

    resolved = path if path is not None else omegaclaw_dir()
    return (
        "!(import! &self (library lib_import))\n"
        f'!(git-import! "{OMEGACLAW_REPO_URL}" "" "{resolved.parent}")\n'
    )


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

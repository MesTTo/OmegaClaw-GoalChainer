"""Purpose: run a script in a fresh interpreter on a copy of the GoalChainer package, for the
tests that change package files or start SNARS worlds from images without touching the tree under
test."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import goal_chainer

PACKAGE = Path(goal_chainer.__file__).resolve().parent
PY_CALLS = Path(importlib.util.find_spec("goalchainer_snars").origin).resolve()

# Every script starts by checking that it imported the copy, not the tree under test.
_PRELUDE = (
    "import sys\nfrom pathlib import Path\nimport goal_chainer\n"
    "assert Path(goal_chainer.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())\n"
)


# The package and its py-call module copied into `directory`, without bytecode caches.
# am[verifies a-rt-helper-identity-regressions-1017@0c9c7d] am[verifies a-rt-image-cache-1017@66d7ae]
def copy_package(directory: Path) -> Path:
    shutil.copytree(PACKAGE, directory / "goal_chainer", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(PY_CALLS, directory / "goalchainer_snars.py")
    return directory


# Runs `script` in a fresh interpreter importing the copy at `site`, and answers the JSON object
# it printed last.
# am[verifies a-rt-helper-identity-regressions-1017@0c9c7d] am[verifies a-rt-image-cache-1017@66d7ae]
def run_fresh(site: Path, script: str) -> dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GOALCHAINER_")}
    env["PYTHONPATH"] = str(site)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", _PRELUDE + script, str(site)], cwd=site, env=env, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.splitlines()[-1])

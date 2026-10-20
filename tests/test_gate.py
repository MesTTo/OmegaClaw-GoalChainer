"""Purpose: verify scripts/gate.sh's boundary on the Omega checkout. Run twice in a superproject whose
external/OmegaClaw-Core it did not create, the gate installs the plugin only into its own clone of the
same pin and runs the plugin suite there, both runs pass, and that checkout stays exactly as it was. A
checkout the gate cloned itself takes the install and is reset between runs. A checkout carrying an
install the gate did not make stops it before anything is installed. uv, the native wheels, the sleep
test base, the contracts and the plugin suite are stand-ins, and so is the installer, which picks its
target from OMEGACLAW_DIR as scripts/setup-omegaclaw.sh does and leaves what that installer leaves."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / "scripts" / "gate.sh"
CORE = "external/OmegaClaw-Core"
OWN = "ai-tmp/gate-omegaclaw-core"
STOCK_PLUGINS = "plugins:\n"

# uv answers its version, runs nothing for `uv run`, and for `uv sync` makes .venv/bin/python run the
# interpreter running these tests, which has pytest.
UV = """#!/bin/sh
case "$1" in
  --version) echo "uv 0.0.0-test" ;;
  run) exit 0 ;;
  sync) mkdir -p .venv/bin && printf '#!/bin/sh\\nexec "%s" "$@"\\n' "$GATE_TEST_PYTHON" > .venv/bin/python \\
          && chmod +x .venv/bin/python ;;
  *) echo "the test uv has no $1" >&2; exit 2 ;;
esac
"""

# The installer's target is OMEGACLAW_DIR, else external/OmegaClaw-Core, as scripts/setup-omegaclaw.sh
# chooses it, and it leaves there what that installer leaves: plugins/goalchainer, a record appended to
# the tracked config/plugins.yaml and the receipt. Each target goes to the record.
INSTALLER = """#!/usr/bin/env bash
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
target="${OMEGACLAW_DIR:-$repo/external/OmegaClaw-Core}"
mkdir -p "$target/plugins/goalchainer"
echo installed > "$target/plugins/goalchainer/marker"
echo "- goalchainer" >> "$target/config/plugins.yaml"
echo '{}' > "$target/.goalchainer-plugin-receipt.json"
echo "$target" >> "$GATE_TEST_RECORD/installs"
"""

# The plugin suite records the checkout it was given and passes only where the plugin is installed.
SUITE = """#!/usr/bin/env bash
echo "$OMEGACLAW_DIR" >> "$GATE_TEST_RECORD/suites"
[ -f "$OMEGACLAW_DIR/plugins/goalchainer/marker" ]
"""

# Files of the superproject other than the gate itself: each path, its text and whether it runs.
FILES = {
    "pyproject.toml": ('[project]\nname = "synthetic"\nversion = "0"\n', False),
    ".gitignore": ("ai-tmp/\n.venv/\nnative-wheels/\n", False),
    "scripts/native-wheels.py": ("import sys\nsys.exit(0)\n", False),
    "scripts/setup-omegaclaw.sh": (INSTALLER, True),
    "scripts/check-mathematical-contracts.sh": ("#!/bin/sh\nexit 0\n", True),
    "plugins/goalchainer/tests/run.sh": (SUITE, True),
    "tests/test_semantic_sleep.py": ('import pathlib, sys\nif __name__ == "__main__":\n'
                                     '    pathlib.Path(sys.argv[2]).mkdir(parents=True, exist_ok=True)\n'
                                     '    print("{}")\n', False),
    "tests/test_ok.py": ("def test_ok():\n    assert True\n", False),
}


# am[verifies a-gb-test-1018@084b14]
def _git(cwd: Path, *args: str) -> str:
    identity = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]
    return subprocess.run(["git", "-C", str(cwd), *identity, *args],
                          check=True, capture_output=True, text=True).stdout.strip()


# An Omega repository with the file setup-omegaclaw.sh looks for and a tracked config/plugins.yaml,
# and a superproject pinning it at external/OmegaClaw-Core with the committed gate and the stand-ins;
# when <pre_existing>, the Omega checkout is cloned there at its pin by hand, not by the gate.
# Answers the superproject and the pin.
# Time: two git inits and commits, and one clone when pre_existing, well under a second.
# am[verifies a-gb-test-1018@084b14]
def _superproject(root: Path, *, pre_existing: bool) -> tuple[Path, str]:
    omega = root / "omega"
    (omega / "config").mkdir(parents=True)
    (omega / "lib_omega.metta").write_text("; Omega\n")
    (omega / "config" / "plugins.yaml").write_text(STOCK_PLUGINS)
    _git(omega, "init", "-q")
    _git(omega, "add", "-A")
    _git(omega, "commit", "-q", "-m", "omega")
    pin = _git(omega, "rev-parse", "HEAD")
    repo = root / "goalchainer"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(GATE, repo / "scripts" / "gate.sh")
    (repo / "scripts" / "gate.sh").chmod(0o755)
    (repo / ".gitmodules").write_text(f'[submodule "{CORE}"]\n\tpath = {CORE}\n\turl = {omega}\n')
    for name, (text, runs) in FILES.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
        if runs:
            (repo / name).chmod(0o755)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{pin},{CORE}")
    _git(repo, "commit", "-q", "-m", "goalchainer")
    if pre_existing:
        _git(root, "clone", "-q", "--no-checkout", str(omega), str(repo / CORE))
        _git(repo / CORE, "checkout", "-q", "--detach", pin)
    return repo, pin


# One whole gate run in <repo>, with the stand-in uv first on PATH and none of the caller's
# GOALCHAINER_ settings; the stand-ins write to <record>.
# am[verifies a-gb-test-1018@084b14]
def _gate(repo: Path, record: Path) -> subprocess.CompletedProcess[str]:
    bin_dir = record / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "uv").write_text(UV)
    (bin_dir / "uv").chmod(0o755)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GOALCHAINER_")}
    environment.update({"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "GATE_TEST_PYTHON": sys.executable,
                        "GATE_TEST_RECORD": str(record)})
    return subprocess.run(["bash", str(repo / "scripts" / "gate.sh")], cwd=repo, env=environment,
                          capture_output=True, text=True, check=False)


# am[verifies a-gb-test-1018@084b14]
def _lines(path: Path) -> list[str]:
    return path.read_text().splitlines() if path.exists() else []


# A pre-existing Omega checkout at its pin is only read: both runs install into the gate's own clone of
# the same pin and run the plugin suite there, both pass, the checkout has no change and no untracked
# file after either, and the clone is reset between runs, so it holds one install record.
# am[verifies a-gb-test-1018@084b14] am[verifies a-gb-own-clone-1018@b10c8f]
def test_a_checkout_the_gate_did_not_create_is_left_as_it_was_across_runs(tmp_path):
    repo, pin = _superproject(tmp_path, pre_existing=True)
    record = tmp_path / "record"
    for _ in range(2):
        result = _gate(repo, record)

        assert result.returncode == 0, result.stdout + result.stderr
        assert _git(repo / CORE, "status", "--porcelain", "--untracked-files=all") == ""
        assert _git(repo / CORE, "rev-parse", "HEAD") == pin
    own = repo / OWN
    assert _lines(record / "installs") == [str(own)] * 2
    assert _lines(record / "suites") == [str(own)] * 2
    assert (own / "config" / "plugins.yaml").read_text() == STOCK_PLUGINS + "- goalchainer\n"
    assert _git(own, "rev-parse", "HEAD") == pin
    assert set(_lines(repo / "ai-tmp" / "gate-provisioned")) == {OWN}


# An Omega checkout the gate cloned itself takes the install, as before, and is reset to its pin
# between runs; no clone of its own is made.
# am[verifies a-gb-test-1018@084b14] am[verifies a-gb-own-clone-1018@b10c8f]
def test_a_checkout_the_gate_cloned_takes_the_install_and_is_reset_between_runs(tmp_path):
    repo, pin = _superproject(tmp_path, pre_existing=False)
    record = tmp_path / "record"
    for _ in range(2):
        result = _gate(repo, record)

        assert result.returncode == 0, result.stdout + result.stderr
    core = repo / CORE
    assert _lines(record / "installs") == [str(core)] * 2
    assert _lines(record / "suites") == [str(core)] * 2
    assert (core / "config" / "plugins.yaml").read_text() == STOCK_PLUGINS + "- goalchainer\n"
    assert _git(core, "rev-parse", "HEAD") == pin
    assert not (repo / OWN).exists()
    assert set(_lines(repo / "ai-tmp" / "gate-provisioned")) == {CORE}


# A pre-existing checkout carrying an install the gate did not make stops the gate before it installs
# anything, and the checkout keeps that install as it was.
# am[verifies a-gb-test-1018@084b14]
def test_an_install_the_gate_did_not_make_stops_it_before_it_installs_anything(tmp_path):
    repo, _ = _superproject(tmp_path, pre_existing=True)
    core = repo / CORE
    (core / ".goalchainer-plugin-receipt.json").write_text("{}\n")
    (core / "config" / "plugins.yaml").write_text(STOCK_PLUGINS + "- goalchainer\n")
    before = _git(core, "status", "--porcelain", "--untracked-files=all")
    record = tmp_path / "record"

    result = _gate(repo, record)

    assert result.returncode == 2
    assert f"{CORE} carries a plugin install this gate did not make" in result.stderr
    assert not (record / "installs").exists()
    assert _git(core, "status", "--porcelain", "--untracked-files=all") == before

"""Purpose: verify scripts/setup-omegaclaw.sh installs GoalChainer's plugin and nothing else into
OmegaClaw-Core, records the locked environment's interpreter for the plugin's skills, refuses an
interpreter that cannot run them, and that --uninstall returns a stock checkout to its exact bytes."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SETUP = REPO / "scripts" / "setup-omegaclaw.sh"
INSTALLER = REPO / "scripts" / "install_plugin.py"
CORE = REPO / "external" / "OmegaClaw-Core"


# am[verifies a-rt-skill-process-boundary-1016@a36729]
def _stock_core(destination: Path) -> Path:
    """Extract the pinned OmegaClaw-Core commit, untouched by any install, into destination."""

    pin = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD:external/OmegaClaw-Core"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    archive = subprocess.run(
        ["git", "-C", str(CORE), "archive", "--format=tar", pin],
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(destination, filter="data")
    return destination


# am[verifies a-rt-skill-process-boundary-1016@a36729]
def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# am[verifies a-rt-skill-process-boundary-1016@a36729]
def _setup(core: Path, *arguments: str) -> None:
    subprocess.run(
        ["bash", str(SETUP), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "OMEGACLAW_DIR": str(core)},
    )


# GoalChainer carries its own deontic library, so the install adds its plugin alone.
# am[verifies a-rt-skill-process-boundary-1016@a36729] am[verifies a-rt-incorporate-deontic-1016@6ea255]
def test_uninstall_returns_the_checkout_to_its_stock_bytes(tmp_path):
    core = _stock_core(tmp_path / "OmegaClaw-Core")
    stock = _files(core)

    _setup(core)
    installed = _files(core)
    added = set(installed) - set(stock)
    assert "plugins/goalchainer/goalchainer.metta" in added
    assert {path.split("/")[1] for path in added if path.startswith("plugins/")} == {"goalchainer"}
    registry = installed["config/plugins.yaml"].decode()
    assert "# >>> goalchainer" in registry
    assert "# >>> omegaclaw-deontic" not in registry

    _setup(core, "--uninstall")
    assert _files(core) == stock


# am[verifies a-rt-skill-process-boundary-1016@a36729]
def test_reinstall_after_uninstall_matches_the_first_install(tmp_path):
    core = _stock_core(tmp_path / "OmegaClaw-Core")
    _setup(core)
    first = _files(core)
    _setup(core, "--uninstall")
    _setup(core)
    second = _files(core)
    # The receipt carries an install timestamp; every other byte must match.
    receipt = ".goalchainer-plugin-receipt.json"
    assert {k: v for k, v in first.items() if k != receipt} == {
        k: v for k, v in second.items() if k != receipt
    }


# The interpreter the plugin's skills run in is the locked environment's, as uv reports it, and
# both the generated goalchainer_host.py and the receipt record it.
# am[verifies a-rt-skill-process-boundary-1016@a36729] am[verifies a-oc-plugin-host-module-1018@180dc9]
def test_install_records_the_locked_interpreter(tmp_path):
    core = _stock_core(tmp_path / "OmegaClaw-Core")
    locked = subprocess.run(
        ["uv", "run", "--frozen", "--no-sync", "python", "-c", "import sys; print(sys.executable)"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    _setup(core)

    host = (core / "plugins" / "goalchainer" / "goalchainer_host.py").read_text()
    namespace: dict[str, object] = {}
    exec(compile(host, "goalchainer_host.py", "exec"), namespace)
    assert namespace["python"]() == locked
    receipt = json.loads((core / ".goalchainer-plugin-receipt.json").read_text())
    assert receipt["python"] == locked
    assert receipt["generated_files"] == ["goalchainer_host.py"]
    assert namespace["READER"] == {} and receipt["reader"] == {}
    assert namespace["reader_default"]("goalchainerJevUrl") == ""


READER_FLAGS = ("--model-cache", "/opt/goalchainer/models", "--jev-cache", "/memory/goalchainer-jev",
                "--jev-offline", "1", "--jev-url", "http://localhost:8080/typesafe")
# The plugin loaded into Omega's registry on pymetta, as integrations/omegaclaw/omega_metta.py loads it,
# printing what its reader settings answer and what gcskill keeps for the skill processes.
LOADED = """
import json, sys
sys.path.insert(0, sys.argv[2])
import omega_metta
session = omega_metta.registry(__import__("pathlib").Path(sys.argv[1]))
import gcskill
keys = [key for key, _ in gcskill.READER_VARIABLES]
print(json.dumps({"configured": {key: str(session.m.run(f"!({key})")[0][0]) for key in keys},
                  "skill_environment": gcskill.skill_environment({})}))
"""


# An install records the reader defaults it is given, in goalchainer_host.py and the receipt, and the
# loaded plugin configures each from them while Omega's own configuration wins: an OMEGA_<key>
# variable here, as a key=value argument does in the image, overrides the recorded Jev cache.
# am[verifies a-irp-reader-keys-1018@14bc18]
def test_install_records_reader_defaults_that_omega_configuration_overrides(tmp_path):
    core = _stock_core(tmp_path / "OmegaClaw-Core")

    _setup(core, *READER_FLAGS)
    host = (core / "plugins" / "goalchainer" / "goalchainer_host.py").read_text()
    namespace: dict[str, object] = {}
    exec(compile(host, "goalchainer_host.py", "exec"), namespace)
    loaded = subprocess.run(
        [sys.executable, "-I", "-c", LOADED, str(core), str(REPO / "integrations" / "omegaclaw")],
        check=True, capture_output=True, text=True,
        env={**{k: v for k, v in os.environ.items() if k != "SWI_HOME_DIR"},
             "OMEGA_goalchainerJevCache": "/override/goalchainer-jev"},
    )

    recorded = {"goalchainerModelCache": "/opt/goalchainer/models", "goalchainerJevCache": "/memory/goalchainer-jev",
                "goalchainerJevOffline": "1", "goalchainerJevUrl": "http://localhost:8080/typesafe"}
    assert namespace["READER"] == recorded
    assert json.loads((core / ".goalchainer-plugin-receipt.json").read_text())["reader"] == recorded
    answers = json.loads(loaded.stdout.splitlines()[-1])
    assert answers["configured"] == {**recorded, "goalchainerJevCache": "/override/goalchainer-jev"}
    assert answers["skill_environment"] == {
        "GOALCHAINER_MODEL_CACHE": "/opt/goalchainer/models", "GOALCHAINER_JEV_CACHE": "/override/goalchainer-jev",
        "GOALCHAINER_JEV_OFFLINE": "1", "TYPESAFE_BASE_URL": "http://localhost:8080/typesafe",
        "TYPESAFE_API_KEY": "omega-gateway"}


# A malformed reader default is refused before anything is written.
# am[verifies a-irp-reader-keys-1018@14bc18]
@pytest.mark.parametrize("flag,value", [("--model-cache", "relative/models"), ("--jev-offline", "yes"),
                                        ("--jev-url", "ftp://gateway/typesafe")])
def test_install_refuses_a_malformed_reader_default(tmp_path, flag, value):
    core = _stock_core(tmp_path / "OmegaClaw-Core")
    stock = _files(core)

    refused = subprocess.run(["bash", str(SETUP), flag, value], capture_output=True, text=True,
                             env={**os.environ, "OMEGACLAW_DIR": str(core)})

    assert refused.returncode != 0 and flag.removeprefix("--").replace("-", "") in refused.stderr.lower()
    assert _files(core) == stock


# An interpreter whose environment cannot run GoalChainer's skills is refused before anything is
# written: here the bare interpreter uv's environment was built from, which has no goal_chainer.
# am[verifies a-rt-skill-process-boundary-1016@a36729]
@pytest.mark.parametrize("python", ["relative/python", "/nonexistent/python", sys.base_prefix + "/bin/python3"])
def test_install_refuses_an_interpreter_that_cannot_run_the_skills(tmp_path, python):
    core = _stock_core(tmp_path / "OmegaClaw-Core")
    stock = _files(core)

    refused = subprocess.run(
        [sys.executable, str(INSTALLER), str(core), "--python", python],
        capture_output=True,
        text=True,
    )

    assert refused.returncode != 0
    assert _files(core) == stock

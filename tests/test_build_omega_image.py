"""Purpose: verify scripts/build-omega-image.sh builds only from committed trees: with the working
Dockerfile and the Omega checkout's working version helper both dirtied, the docker build it runs
reads the committed Dockerfile and the version the pinned commit's own helper formats, from a
context holding the committed trees, every one of whose files and directories anyone can read
whatever the caller's umask; and that it hands the build the native wheel directory the committed
lock names only as a verified copy in the named context native-wheels, stopping before docker runs
when that directory is missing or differs from its MANIFEST."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "build-omega-image.sh"
VERIFIER = REPO / "scripts" / "native-wheels.py"

# A stand-in docker records the arguments it was given and, since the script removes its context when
# it exits, copies what the context held while the build would have read it, lists each entry of the
# context that others cannot read, or as a directory cannot enter, with its mode, lists the named
# context native-wheels with each file's sha256, notes a native-wheels/ left in the context, and
# exits with the status GOALCHAINER_TEST_DOCKER_STATUS names, 0 by default.
FAKE_DOCKER = r"""#!/bin/sh
record="$GOALCHAINER_TEST_RECORD"
printf '%s\n' "$@" > "$record/args"
previous=""
for argument in "$@"; do
  [ "$previous" = "--file" ] && cp "$argument" "$record/dockerfile"
  if [ "$previous" = "--build-context" ]; then
    cd "${argument#native-wheels=}" || exit 1
    find . -mindepth 1 -printf '%y %P\n' | LC_ALL=C sort > "$record/native-wheels-tree"
    find . -type f -exec sha256sum {} + | LC_ALL=C sort -k 2 > "$record/native-wheels-sums"
    cd - >/dev/null || exit 1
  fi
  previous="$argument"
done
cp "$previous/omega/src/helper.py" "$record/context-helper.py"
find "$previous" \( ! -perm -o+r -o \( -type d ! -perm -o+x \) \) -printf '%m %P\n' > "$record/closed"
[ ! -e "$previous/goalchainer/native-wheels" ] || echo leaked > "$record/leaked"
exit "${GOALCHAINER_TEST_DOCKER_STATUS:-0}"
"""

COMMITTED_HELPER = "def _format_omega_version(version):\n    return 'committed ' + version.strip()\n"
DIRTY_HELPER = "def _format_omega_version(version):\n    return 'dirty'\n"
WHEEL = "fakehost-1.0-py3-none-any.whl"


# am[verifies a-integrate-image-build-committed-inputs-1018@f4fcef]
def _git(cwd: Path, *args: str) -> str:
    identity = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]
    return subprocess.run(["git", "-C", str(cwd), *identity, *args],
                          check=True, capture_output=True, text=True).stdout.strip()


# am[verifies a-irp-image-native2-wheel-1018@ec11d2]
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# A wheel directory as the native builds are published: a wheel and BUILD beside a MANIFEST of their
# sha256, named for MANIFEST's digest, read-only as the store keeps it. The verifier reads no wheel's
# contents, so the wheel is any bytes.
# am[verifies a-irp-image-native2-wheel-1018@ec11d2]
def _publish(store: Path) -> Path:
    stage = store / "stage"
    stage.mkdir(parents=True)
    (stage / WHEEL).write_bytes(b"the published wheel\n")
    (stage / "BUILD").write_text(f"wheels:\n  {WHEEL}: no bundled engine\n", encoding="utf-8")
    listing = "".join(f"{_sha256(stage / name)}  {name}\n" for name in sorted(["BUILD", WHEEL]))
    (stage / "MANIFEST").write_text(listing, encoding="utf-8")
    published = store / f"fakehost-1.0-{hashlib.sha256(listing.encode()).hexdigest()[:16]}"
    stage.rename(published)
    for path in (*published.iterdir(), published):
        path.chmod(0o500 if path.is_dir() else 0o400)
    return published


# A superproject holding the script, the native wheel verifier, a lock and find-links naming
# <published> under native-wheels/ as GoalChainer's name pymetta's, and a Dockerfile, with a nested
# Omega repository its gitlink pins at a tagged commit, as external/OmegaClaw-Core is; then both
# working files the build must not read are changed without committing.
# Time: two git inits and two commits, well under a second.
# am[verifies a-integrate-image-build-committed-inputs-1018@f4fcef] am[verifies a-irp-image-native2-wheel-1018@ec11d2]
def _superproject(root: Path, published: Path) -> tuple[Path, str]:
    repo = root / "goalchainer"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / SCRIPT.name)
    shutil.copy(VERIFIER, repo / "scripts" / VERIFIER.name)
    directory = f"native-wheels/{published.name}"
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "consumer"\nversion = "0"\n\n[tool.uv]\nfind-links = ["{directory}"]\n', encoding="utf-8")
    (repo / "uv.lock").write_text(
        f'version = 1\n\n[[package]]\nname = "fakehost"\nversion = "1.0"\nsource = {{ registry = "{directory}" }}\n'
        f'wheels = [{{ path = "{WHEEL}" }}]\n', encoding="utf-8")
    dockerfile = repo / "integrations" / "omegaclaw" / "image" / "Dockerfile"
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text("FROM committed\n")
    omega = repo / "external" / "OmegaClaw-Core"
    (omega / "src").mkdir(parents=True)
    helper = omega / "src" / "helper.py"
    helper.write_text(COMMITTED_HELPER)
    _git(omega, "init", "-q")
    _git(omega, "add", "-A")
    _git(omega, "commit", "-q", "-m", "omega")
    _git(omega, "tag", "v9.9.9")
    pin = _git(omega, "rev-parse", "HEAD")
    _git(repo, "init", "-q")
    _git(repo, "add", "scripts", "integrations", "pyproject.toml", "uv.lock")
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{pin},external/OmegaClaw-Core")
    _git(repo, "commit", "-q", "-m", "goalchainer")
    dockerfile.write_text("FROM dirty\n")
    helper.write_text(DIRTY_HELPER)
    return repo, _git(repo, "rev-parse", "HEAD")


# The script run under umask 0077, so a context extracted under the caller's umask would be closed to
# others, with the stand-in docker first on PATH and none of the caller's native store; <store> is the
# GOALCHAINER_NATIVE_WHEELS it gets, if any, and <docker_status> the stand-in docker's exit status.
# uv runs the verifier with a cache of the test's own. Its files go in <root>, which this makes.
# am[verifies a-integrate-image-build-committed-inputs-1018@f4fcef] am[verifies a-irp-build-umask-022-1018@3f2c7e]
def _build(root: Path, repo: Path, store: Path | None,
           docker_status: int = 0) -> tuple[subprocess.CompletedProcess[str], Path]:
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "docker").write_text(FAKE_DOCKER)
    (bin_dir / "docker").chmod(0o755)
    record = root / "record"
    record.mkdir()
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GOALCHAINER_")}
    environment.update({"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "GOALCHAINER_TEST_RECORD": str(record),
                        "UV_CACHE_DIR": str(root / "uv-cache"), "GOALCHAINER_TEST_DOCKER_STATUS": str(docker_status)})
    if store is not None:
        environment["GOALCHAINER_NATIVE_WHEELS"] = str(store)
    built = subprocess.run(["bash", str(repo / "scripts" / SCRIPT.name)], env=environment,
                           capture_output=True, text=True, preexec_fn=lambda: os.umask(0o077))
    return built, record


# With the native directory placed in the checkout as a link, the way the README's set-up places it,
# the build reads only committed inputs, and the named context holds a copy of exactly the published
# directory, its files the published bytes and no link among them, while the context holds none.
# Time: two git inits, two commits, one verifier run and one script run, a few seconds.
# am[verifies a-integrate-image-build-committed-inputs-1018@f4fcef] am[verifies a-irp-build-umask-022-1018@3f2c7e]
# am[verifies a-irp-image-native2-wheel-1018@ec11d2]
def test_the_build_reads_only_committed_trees(tmp_path):
    published = _publish(tmp_path / "store")
    repo, revision = _superproject(tmp_path, published)
    (repo / "native-wheels").mkdir()
    (repo / "native-wheels" / published.name).symlink_to(published)

    built, record = _build(tmp_path, repo, None)

    assert built.returncode == 0, built.stderr
    arguments = (record / "args").read_text().splitlines()
    assert (record / "dockerfile").read_text() == "FROM committed\n"
    assert "OMEGA_VERSION=committed v9.9.9" in arguments
    assert f"GOALCHAINER_REVISION={revision}" in arguments
    assert arguments[arguments.index("--build-context") + 1].startswith("native-wheels=")
    assert (record / "context-helper.py").read_text() == COMMITTED_HELPER
    assert (record / "closed").read_text() == ""
    assert not (record / "leaked").exists()
    files = sorted(path.name for path in published.iterdir())
    assert (record / "native-wheels-tree").read_text().splitlines() == \
        [f"d {published.name}", *(f"f {published.name}/{name}" for name in files)]
    assert (record / "native-wheels-sums").read_text().splitlines() == \
        [f"{_sha256(published / name)}  ./{published.name}/{name}" for name in files]
    assert not list((repo / "ai-tmp").glob("omega-image-*"))


# A store whose copy of the directory has one byte changed stops the build with place's integrity
# status and its reason, and docker never runs; so does a checkout with no directory and no store.
# am[verifies a-irp-image-native2-wheel-1018@ec11d2]
def test_a_changed_or_missing_native_directory_stops_the_build_before_docker(tmp_path):
    published = _publish(tmp_path / "store")
    repo, _ = _superproject(tmp_path, published)
    wheel = published / WHEEL
    published.chmod(0o700)
    wheel.chmod(0o600)
    wheel.write_bytes(b"the published wheeL\n")

    changed, record = _build(tmp_path / "changed", repo, published.parent)

    assert changed.returncode == 3, changed.stderr
    assert f"{WHEEL} has sha256 {_sha256(wheel)}, not MANIFEST's" in changed.stderr
    assert not (record / "args").exists()
    assert not list((repo / "ai-tmp").glob("omega-image-*"))

    missing, record = _build(tmp_path / "missing", repo, None)

    assert missing.returncode == 1, missing.stderr
    assert "GOALCHAINER_NATIVE_WHEELS is unset" in missing.stderr
    assert not (record / "args").exists()
    assert not list((repo / "ai-tmp").glob("omega-image-*"))


# A build that fails after the copy, here in docker, exits with docker's status and still removes its
# work directory, whose copies keep the store's read-only modes.
# am[verifies a-irp-image-native2-wheel-1018@ec11d2]
def test_a_build_that_fails_after_the_copy_leaves_no_work_directory(tmp_path):
    published = _publish(tmp_path / "store")
    repo, _ = _superproject(tmp_path, published)

    failed, record = _build(tmp_path / "failed", repo, published.parent, docker_status=7)

    assert failed.returncode == 7, failed.stderr
    assert (record / "native-wheels-tree").read_text().splitlines()[0] == f"d {published.name}"
    assert not list((repo / "ai-tmp").glob("omega-image-*"))

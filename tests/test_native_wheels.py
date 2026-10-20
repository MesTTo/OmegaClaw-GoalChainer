"""Purpose: verify scripts/native-wheels.py against a small published wheel directory: place links
and accepts the directory the lock names, at the checkout's own path and at another one, which uv
locks and installs alike, and refuses a directory whose bytes, listing or name differ or that is
missing; check accepts the install uv made and refuses one whose files differ from the published
wheel, that carries a module the wheel does not, whose import resolves elsewhere, or whose wheel
bundles no engine."""
# am[verifies a-rt-n2ic-verifier-1018@489090]

from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "native-wheels.py"
NAME, VERSION = "fakehost", "1.0+native.1"
ENGINE = b"\x7fELF the bundled engine\n"
POOL = b"def run():\n    return 'the published pool'\n"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def publish(store: Path, *, engine: bool) -> Path:
    """Publish one py3-none-any wheel of NAME as the native artifacts are published: the wheel and BUILD
    beside a MANIFEST of their sha256, in a directory named for MANIFEST's digest."""
    stage = store / "stage"
    stage.mkdir(parents=True)
    members = {f"{NAME}/__init__.py": b"VALUE = 1\n", f"{NAME}/pool.py": POOL}
    if engine:
        members[f"{NAME}/_host/lib/libswipl.so"] = ENGINE
    info = f"{NAME}-{VERSION}.dist-info"
    members[f"{info}/METADATA"] = f"Metadata-Version: 2.1\nName: {NAME}\nVersion: {VERSION}\n".encode()
    members[f"{info}/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    rows = io.StringIO()
    writer = csv.writer(rows, lineterminator="\n")
    for path, data in members.items():
        encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([path, f"sha256={encoded}", len(data)])
    writer.writerow([f"{info}/RECORD", "", ""])
    members[f"{info}/RECORD"] = rows.getvalue().encode()
    wheel = stage / f"{NAME}-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path, data in members.items():
            archive.writestr(path, data)
    said = f"bundled libswipl.so sha256 {digest(ENGINE)}" if engine else "no bundled engine"
    (stage / "BUILD").write_text(f"version: {VERSION}\nwheels:\n  {wheel.name}: {said}\n", encoding="utf-8")
    listing = "".join(f"{digest((stage / file).read_bytes())}  {file}\n" for file in sorted(["BUILD", wheel.name]))
    (stage / "MANIFEST").write_text(listing, encoding="utf-8")
    published = store / f"{NAME}-{VERSION}-{digest(listing.encode())[:16]}"
    stage.rename(published)
    return published


def environment(tmp_path: Path, store: Path | None) -> dict[str, str]:
    """The tests' own environment: nothing of the gate's interpreter, environment or native store, and
    a uv cache of their own, since every fake wheel shares one name and version."""
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"}
           and not key.startswith("GOALCHAINER_")}
    env["UV_CACHE_DIR"] = str(tmp_path / "uv-cache")
    if store is not None:
        env["GOALCHAINER_NATIVE_WHEELS"] = str(store)
    return env


def run(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)


def consumer(at: Path, published: Path) -> Path:
    """A checkout requiring NAME from published by find-links, as GoalChainer requires pymetta, with no
    index, so uv locks and installs it offline."""
    (at / "scripts").mkdir(parents=True)
    shutil.copy2(SCRIPT, at / "scripts" / SCRIPT.name)
    (at / "pyproject.toml").write_text(
        f'[project]\nname = "consumer"\nversion = "0"\nrequires-python = ">=3.11"\n'
        f'dependencies = ["{NAME}=={VERSION}"]\n\n'
        f'[tool.uv]\nno-index = true\nfind-links = ["native-wheels/{published.name}"]\n', encoding="utf-8")
    return at


def place(checkout: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return run([sys.executable, str(checkout / "scripts" / SCRIPT.name), "place"], checkout, env)


def locked(checkout: Path, env: dict[str, str]) -> None:
    """Place the directory and lock the checkout against it."""
    placed = place(checkout, env)
    assert placed.returncode == 0, placed.stderr
    result = run(["uv", "lock", "--offline", "--python", sys.executable], checkout, env)
    assert result.returncode == 0, result.stderr


def synced(checkout: Path, env: dict[str, str]) -> Path:
    """Install the lock into the checkout's own environment and answer its interpreter."""
    result = run(["uv", "sync", "--frozen", "--offline", "--python", sys.executable], checkout, env)
    assert result.returncode == 0, result.stderr
    return checkout / ".venv" / "bin" / "python"


def check(checkout: Path, python: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return run([str(python), str(checkout / "scripts" / SCRIPT.name), "check"], checkout, env)


# The checkout as committed, moved to another path with a space in it at another depth: place links
# the same directory there, uv reads the lock as current and installs from it, and check accepts the
# result, because the lock names the directory relative to the checkout and nowhere names a path.
# am[verifies a-rt-n2ic-relocation-1018@e0167c] am[verifies a-rt-n2ic-lock-1018@dae2f5]
def test_a_moved_checkout_places_locks_and_installs_the_same_verified_directory(tmp_path):
    store = tmp_path / "store"
    published = publish(store, engine=True)
    env = environment(tmp_path, store)
    first = consumer(tmp_path / "first", published)
    locked(first, env)
    lock = (first / "uv.lock").read_text(encoding="utf-8")
    assert str(tmp_path) not in lock
    entry, = (package for package in tomllib.loads(lock)["package"] if package["name"] == NAME)
    assert entry["source"] == {"registry": f"native-wheels/{published.name}"}
    moved = tmp_path / "a moved copy" / "deeper"
    moved.mkdir(parents=True)
    for file in ("pyproject.toml", "uv.lock"):
        shutil.copy2(first / file, moved / file)
    shutil.copytree(first / "scripts", moved / "scripts")
    placed = place(moved, env)
    assert placed.returncode == 0, placed.stderr
    assert placed.stdout == f"native-wheels/{published.name}\n"
    assert (moved / "native-wheels" / published.name).resolve() == published.resolve()
    current = run(["uv", "lock", "--check", "--offline", "--python", sys.executable], moved, env)
    assert current.returncode == 0, current.stderr
    verified = check(moved, synced(moved, env), env)
    assert verified.returncode == 0, verified.stderr
    assert f"is {NAME}-{VERSION}-py3-none-any.whl" in verified.stdout
    assert f"engine libswipl.so sha256 {digest(ENGINE)}" in verified.stdout


# Each way a directory can differ from the one the lock names stops place before it links anything.
# am[verifies a-rt-n2ic-verifier-1018@489090]
@pytest.mark.parametrize(("damage", "says"), [
    ("a changed wheel byte", "not MANIFEST's"),
    ("a file MANIFEST does not list", "that MANIFEST does not list"),
    ("a MANIFEST of other bytes", "its MANIFEST's sha256 begins"),
])
def test_place_refuses_a_directory_that_differs_from_the_one_the_lock_names(tmp_path, damage, says):
    published = publish(tmp_path / "store", engine=True)
    checkout = consumer(tmp_path / "checkout", published)
    locked(checkout, environment(tmp_path, tmp_path / "store"))
    (checkout / "native-wheels" / published.name).unlink()
    other = tmp_path / "other" / published.name
    shutil.copytree(published, other)
    wheel = other / f"{NAME}-{VERSION}-py3-none-any.whl"
    if damage == "a changed wheel byte":
        data = bytearray(wheel.read_bytes())
        data[-1] ^= 1
        wheel.write_bytes(bytes(data))
    elif damage == "a file MANIFEST does not list":
        (other / "extra.whl").write_bytes(b"")
    else:
        with (other / "MANIFEST").open("a", encoding="utf-8") as listing:
            listing.write(f"{digest(b'')}  extra.whl\n")
        (other / "extra.whl").write_bytes(b"")
    refused = place(checkout, environment(tmp_path, other.parent))
    assert refused.returncode == 3, refused.stderr
    assert says in refused.stderr
    assert not (checkout / "native-wheels" / published.name).exists()


# A directory the checkout already holds, as an image's mount or copy puts it there, is verified
# where it is with no store named, and refused there when its bytes differ.
# am[verifies a-rt-n2ic-verifier-1018@489090]
def test_place_verifies_a_directory_already_in_the_checkout(tmp_path):
    published = publish(tmp_path / "store", engine=True)
    checkout = consumer(tmp_path / "checkout", published)
    locked(checkout, environment(tmp_path, tmp_path / "store"))
    target = checkout / "native-wheels" / published.name
    target.unlink()
    shutil.copytree(published, target)
    placed = place(checkout, environment(tmp_path, None))
    assert placed.returncode == 0, placed.stderr
    assert placed.stdout == f"native-wheels/{published.name}\n"
    (target / "BUILD").write_text("version: changed\n", encoding="utf-8")
    refused = place(checkout, environment(tmp_path, None))
    assert refused.returncode == 3, refused.stderr
    assert "BUILD has sha256" in refused.stderr


# A directory that is nowhere to be had names the variable that would supply it, and a relative
# store or a link to nothing is refused rather than guessed at.
# am[verifies a-rt-n2ic-verifier-1018@489090]
def test_place_names_what_is_missing(tmp_path):
    published = publish(tmp_path / "store", engine=True)
    checkout = consumer(tmp_path / "checkout", published)
    locked(checkout, environment(tmp_path, tmp_path / "store"))
    target = checkout / "native-wheels" / published.name
    target.unlink()
    unset = place(checkout, environment(tmp_path, None))
    assert unset.returncode == 1, unset.stderr
    assert "GOALCHAINER_NATIVE_WHEELS is unset" in unset.stderr
    relative = place(checkout, environment(tmp_path, Path("store")))
    assert relative.returncode == 2, relative.stderr
    elsewhere = place(checkout, environment(tmp_path, tmp_path / "empty"))
    assert elsewhere.returncode == 1, elsewhere.stderr
    target.symlink_to(tmp_path / "gone")
    dangling = place(checkout, environment(tmp_path, tmp_path / "store"))
    assert dangling.returncode == 1, dangling.stderr
    assert "which does not exist" in dangling.stderr


# A swapped module, a missing engine file and a module the wheel never shipped each fail check with
# the path named, while the caches a boot may write pass; an import found elsewhere fails it too.
# am[verifies a-rt-n2ic-verifier-1018@489090]
def test_check_refuses_an_install_that_differs_from_the_published_wheel(tmp_path):
    published = publish(tmp_path / "store", engine=True)
    env = environment(tmp_path, tmp_path / "store")
    checkout = consumer(tmp_path / "checkout", published)
    locked(checkout, env)
    python = synced(checkout, env)
    assert check(checkout, python, env).returncode == 0
    package, = (checkout / ".venv" / "lib").glob(f"python3.*/site-packages/{NAME}")
    # Replaced rather than written through, since uv links installed files to its cache.
    pool = package / "pool.py"
    pool.unlink()
    pool.write_bytes(b"def run():\n    return 'another pool'\n")
    swapped = check(checkout, python, env)
    assert swapped.returncode == 3, swapped.stderr
    assert f"{NAME}/pool.py has sha256 {digest(pool.read_bytes())}, where" in swapped.stderr
    pool.unlink()
    pool.write_bytes(POOL)
    library = package / "_host" / "lib" / "libswipl.so"
    library.rename(library.with_suffix(".moved"))
    missing = check(checkout, python, env)
    assert missing.returncode == 3, missing.stderr
    assert f"{NAME}/_host/lib/libswipl.so is missing" in missing.stderr
    library.with_suffix(".moved").rename(library)
    (package / "_runtime").mkdir()
    (package / "_runtime" / "boot.qlf").write_bytes(b"cache")
    (package / "__pycache__").mkdir(exist_ok=True)
    (package / "__pycache__" / f"pool.{sys.implementation.cache_tag}.pyc").write_bytes(b"bytecode")
    assert check(checkout, python, env).returncode == 0
    (package / "pool_patch.py").write_bytes(b"")
    extra = check(checkout, python, env)
    assert extra.returncode == 3, extra.stderr
    assert f"{NAME}/pool_patch.py is not in" in extra.stderr
    (package / "pool_patch.py").unlink()
    shadow = tmp_path / "shadow" / NAME
    shadow.mkdir(parents=True)
    (shadow / "__init__.py").write_bytes(b"")
    shadowed = check(checkout, python, {**env, "PYTHONPATH": str(shadow.parent)})
    assert shadowed.returncode == 3, shadowed.stderr
    assert f"import {NAME} finds {(shadow / '__init__.py').resolve()}" in shadowed.stderr


# A wheel BUILD records without an engine is the one an unsupported host gets, since it runs whatever
# SWI-Prolog the host has, so check refuses it with its own status.
# am[verifies a-rt-n2ic-verifier-1018@489090]
def test_check_refuses_an_install_from_a_wheel_without_the_engine(tmp_path):
    published = publish(tmp_path / "store", engine=False)
    env = environment(tmp_path, tmp_path / "store")
    checkout = consumer(tmp_path / "checkout", published)
    locked(checkout, env)
    refused = check(checkout, synced(checkout, env), env)
    assert refused.returncode == 4, refused.stderr
    assert "bundles no engine" in refused.stderr
    assert "is not supported" in refused.stderr

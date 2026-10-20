#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Purpose: verify each content-addressed wheel directory uv.lock installs a native package from,
before uv reads it and again against the environment uv sync made from it.

  uv run scripts/native-wheels.py place
  .venv/bin/python scripts/native-wheels.py check

uv.lock names each such directory as a registry under native-wheels/, relative to the checkout, by
a name that ends in the first 16 hex digits of its MANIFEST's sha256. MANIFEST lists every other
file in the directory with its sha256, and BUILD, one of those files, says for each wheel which
engine it bundles.

place covers every directory under native-wheels/ that uv.lock or pyproject.toml's find-links
names, the latter so a changed pin can be locked: uv reads find-links before anything else. It
verifies native-wheels/<name> where the checkout already has it, as a directory, a link or a
read-only mount; otherwise it verifies $GOALCHAINER_NATIVE_WHEELS/<name> and links it there. It
prints each verified directory, relative to the checkout, one per line.

check runs in the interpreter of the environment uv sync made, while the directories are still in
place, because it reads the installed wheel's RECORD from the verified directory rather than
trusting the installer's copy. For each package it requires the lock's version; the one wheel
whose tags are the installed tags; a bundled engine in that wheel, by BUILD; every file the
wheel's RECORD lists installed with those bytes, so the pool module and the engine library are
the published ones; no file outside that RECORD that Python could import in the wheel's
directories; and imports of the wheel's packages finding this install. It prints one line naming
the wheel, its digest and its engine's.

Exit status: 0 verified; 1 a directory is missing; 2 usage, or a lock this does not read; 3 a
digest, a file or the installed package differs; 4 the installed wheel bundles no engine, so this
host or interpreter is not supported. It needs only the standard library of Python 3.11 or newer,
so place runs before any environment exists.
"""
# am[implements a-rt-n2ic-verifier-1018@489090] am[implements a-rt-native2-install-contract-1018@c66146]

from __future__ import annotations

import base64
import csv
import hashlib
import importlib.machinery
import importlib.metadata
import importlib.util
import io
import os
import sys
import sysconfig
import tomllib
import zipfile
from pathlib import Path
from typing import NamedTuple

CHECKOUT = Path(__file__).resolve().parent.parent
PROJECT = CHECKOUT / "pyproject.toml"
LOCK = CHECKOUT / "uv.lock"
ROOT = "native-wheels"
VARIABLE = "GOALCHAINER_NATIVE_WHEELS"
MISSING, USAGE, INTEGRITY, UNSUPPORTED = 1, 2, 3, 4


class Refused(Exception):
    """A verification that failed, carrying the exit status that says how."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class Native(NamedTuple):
    """A package the lock installs from a directory, which it names relative to the checkout."""

    name: str
    version: str
    directory: str
    wheels: tuple[str, ...]


def read(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise Refused(USAGE, f"cannot read {path}: {error}") from error


def native_directory(path: str, named_by: str) -> str:
    """path, a directory directly in native-wheels/, or a refusal naming who named it otherwise."""
    parts = Path(path).parts
    if len(parts) != 2 or parts[0] != ROOT:
        raise Refused(USAGE, f"{named_by} names {path}, which is not a directory directly in {ROOT}/")
    return path


# The lock's own form for a flat directory: source = { registry = "<path>" } and each wheel as
# { path = "<file>" } inside it, where an index has a URL registry.
# am[rests-on c-rt-n2ic-find-links-relative-1018@e84f2c]
def natives() -> list[Native]:
    """Every package uv.lock installs from a local directory, which must sit directly in native-wheels/."""
    found = []
    for package in read(LOCK).get("package", []):
        registry = package.get("source", {}).get("registry")
        if registry is None or "://" in registry:
            continue
        name = package["name"]
        native_directory(registry, f"uv.lock's source of {name}")
        if "sdist" in package:
            raise Refused(USAGE, f"uv.lock would build {name} from a source distribution in {registry}; "
                                 f"only wheels are verified")
        wheels = []
        for wheel in package.get("wheels", []):
            file = wheel.get("path")
            if file is None or Path(file).name != file:
                raise Refused(USAGE, f"uv.lock names a wheel of {name} as {wheel}, not as a file in {registry}")
            wheels.append(file)
        found.append(Native(name, package["version"], registry, tuple(wheels)))
    return found


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


# Time: one sha256 pass over the directory's bytes, about 80 MB for pymetta's four wheels.
# Space: one entry per file.
def verified(directory: Path, name: str, wheels: tuple[str, ...]) -> dict[str, str]:
    """Verify directory as the one called name, holding the wheels the lock lists from it, and answer
    MANIFEST's sha256 for each file."""
    listing = directory / "MANIFEST"
    try:
        address = sha256(listing)
        lines = listing.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise Refused(INTEGRITY, f"{directory} has no readable MANIFEST: {error}") from error
    if not name.endswith("-" + address[:16]):
        raise Refused(INTEGRITY, f"{directory} is not {name}: its MANIFEST's sha256 begins {address[:16]}")
    # sha256sum's text form, `<64 hex>  <file>`, which is how the directory's publisher wrote it.
    digests = {}
    for line in lines:
        digest, _, file = line.partition("  ")
        if len(digest) != 64 or digest.strip("0123456789abcdef") or not file or "/" in file:
            raise Refused(INTEGRITY, f"{listing} has a line that is not `<sha256>  <file>`: {line!r}")
        digests[file] = digest
    present = {entry.name for entry in directory.iterdir()} - {"MANIFEST"}
    if present != digests.keys():
        unlisted, absent = sorted(present - digests.keys()), sorted(digests.keys() - present)
        raise Refused(INTEGRITY, f"{directory} holds {unlisted} that MANIFEST does not list "
                                 f"and lacks {absent} that it does")
    for file, digest in sorted(digests.items()):
        actual = sha256(directory / file)
        if actual != digest:
            raise Refused(INTEGRITY, f"{directory / file} has sha256 {actual}, not MANIFEST's {digest}")
    unlisted = sorted(set(wheels) - digests.keys())
    if unlisted:
        raise Refused(INTEGRITY, f"uv.lock installs {unlisted} from {name}, whose MANIFEST does not list them")
    return digests


def place() -> None:
    # A checkout about to be locked for the first time has no uv.lock yet, only find-links.
    wheels = {native.directory: native.wheels for native in natives()} if LOCK.exists() else {}
    for link in read(PROJECT).get("tool", {}).get("uv", {}).get("find-links", []):
        if Path(link).parts[:1] == (ROOT,):
            wheels.setdefault(native_directory(link, "pyproject.toml's find-links"), ())
    for directory, locked in wheels.items():
        target = CHECKOUT / directory
        name = target.name
        if target.is_dir():
            verified(target, name, locked)
        elif target.is_symlink():
            raise Refused(MISSING, f"{directory} links to {os.readlink(target)}, which does not exist; "
                                   f"remove the link and run place again with {VARIABLE} naming the directory "
                                   f"that holds {name}")
        elif target.exists():
            raise Refused(INTEGRITY, f"{directory} is not a directory")
        else:
            store = os.environ.get(VARIABLE)
            if not store:
                raise Refused(MISSING, f"{directory} is not in this checkout and {VARIABLE} is unset; "
                                       f"set it to the directory that holds {name}")
            if not Path(store).is_absolute():
                raise Refused(USAGE, f"{VARIABLE} must be an absolute path, not {store}")
            source = Path(store) / name
            if not source.is_dir():
                raise Refused(MISSING, f"{source} does not exist, so {directory} cannot be linked to it")
            verified(source, name, locked)
            # A link made under another name and renamed over the target, so a racing place, which
            # can only link the same verified bytes, never sees half a link.
            target.parent.mkdir(exist_ok=True)
            staged = target.with_name(f".{name}.{os.getpid()}")
            staged.symlink_to(source)
            os.replace(staged, target)
        print(directory)


def wheel_tags(file: str) -> set[str]:
    """The tags a wheel's file name declares, each compressed set expanded, per the wheel format's
    {distribution}-{version}(-{build})?-{python}-{abi}-{platform}.whl."""
    python, abi, platform = file.removesuffix(".whl").split("-")[-3:]
    return {f"{p}-{a}-{t}" for p in python.split(".") for a in abi.split(".") for t in platform.split(".")}


def engines(build: Path) -> dict[str, tuple[str, str] | None]:
    """What BUILD's wheels: section says each wheel bundles: its engine's file name and sha256, or None."""
    lines = build.read_text(encoding="utf-8").splitlines()
    if "wheels:" not in lines:
        raise Refused(INTEGRITY, f"{build} has no wheels: section")
    said: dict[str, tuple[str, str] | None] = {}
    for line in lines[lines.index("wheels:") + 1:]:
        if not line.startswith("  "):
            break
        wheel, _, statement = line.strip().partition(": ")
        words = statement.split()
        if words == ["no", "bundled", "engine"]:
            said[wheel] = None
        elif len(words) == 4 and words[0] == "bundled" and words[2] == "sha256" and len(words[3]) == 64:
            said[wheel] = (words[1], words[3])
        else:
            raise Refused(INTEGRITY, f"{build} says {statement!r} of {wheel}, which check does not read")
    return said


def record(wheel: Path) -> dict[str, str | None]:
    """The wheel's own RECORD: each path it installs with its sha256, None for RECORD itself."""
    with zipfile.ZipFile(wheel) as archive:
        names = [name for name in archive.namelist()
                 if name.count("/") == 1 and name.endswith(".dist-info/RECORD")]
        if len(names) != 1:
            raise Refused(INTEGRITY, f"{wheel} holds {len(names)} RECORD files, not one")
        text = archive.read(names[0]).decode("utf-8")
    rows: dict[str, str | None] = {}
    for path, digest, _size in csv.reader(io.StringIO(text)):
        if not digest and path.rpartition("/")[2] in {"RECORD", "RECORD.jws", "RECORD.p7s"}:
            rows[path] = None
            continue
        algorithm, _, value = digest.partition("=")
        if algorithm != "sha256":
            raise Refused(INTEGRITY, f"{wheel}'s RECORD gives {path} the digest {digest!r}, not a sha256")
        rows[path] = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).hex()
    return rows


def differences(site: Path, wheel: str, rows: dict[str, str | None], tops: set[str]) -> list[str]:
    """Each way the install in site differs from the wheel's RECORD, empty when it does not.

    The rule for files outside RECORD: pymetta's first boot may add the engine's .qlf cache and
    Python may add bytecode under __pycache__, and a used native.2 environment held neither, so
    only a file Python could import in place of a published module counts.
    Time: one sha256 pass over the installed distribution's bytes plus a walk of its directories.
    Space: one entry per RECORD row."""
    # am[rests-on c-rt-n2ic-boot-writes-caches-1018@da28e8] am[rests-on c-rt-n2ic-used-venv-exact-1018@677904]
    differing = []
    for path, expected in sorted(rows.items()):
        if expected is None:
            continue
        try:
            actual = sha256(site / path)
        except FileNotFoundError:
            differing.append(f"{path} is missing")
            continue
        if actual != expected:
            differing.append(f"{path} has sha256 {actual}, where {wheel} has {expected}")
    importable = tuple(importlib.machinery.all_suffixes())
    for top in sorted(tops):
        for folder, subfolders, files in os.walk(site / top):
            subfolders[:] = [sub for sub in subfolders if sub != "__pycache__"]
            for name in files:
                path = (Path(folder) / name).relative_to(site).as_posix()
                if path not in rows and name.endswith(importable):
                    differing.append(f"{path} is not in {wheel}, and Python can import it")
    return differing


def check() -> None:
    sites = list(dict.fromkeys(sysconfig.get_paths()[key] for key in ("purelib", "platlib")))
    for native in natives():
        directory = CHECKOUT / native.directory
        if not directory.is_dir():
            raise Refused(MISSING, f"{native.directory} is not in place; run place first, since check reads "
                                   f"the installed wheel's RECORD from it")
        digests = verified(directory, directory.name, native.wheels)
        installs = list(importlib.metadata.distributions(name=native.name, path=sites))
        if len(installs) != 1:
            raise Refused(INTEGRITY, f"{sys.executable}'s environment holds {len(installs)} installs of "
                                     f"{native.name} in {sites}, not one; run uv sync --frozen")
        installed = installs[0]
        if installed.version != native.version:
            raise Refused(INTEGRITY, f"{sys.executable}'s environment has {native.name} {installed.version}, "
                                     f"not the lock's {native.version}; run uv sync --frozen")
        tags = {line.partition(":")[2].strip() for line in (installed.read_text("WHEEL") or "").splitlines()
                if line.startswith("Tag:")}
        chosen = [file for file in native.wheels if wheel_tags(file) == tags]
        if len(chosen) != 1:
            raise Refused(INTEGRITY, f"{native.name}'s installed tags {sorted(tags)} match {len(chosen)} "
                                     f"of the wheels uv.lock lists, not one")
        wheel = chosen[0]
        said = engines(directory / "BUILD")
        if wheel not in said:
            raise Refused(INTEGRITY, f"{directory / 'BUILD'} does not say what {wheel} bundles")
        engine = said[wheel]
        # A wheel without the engine runs whatever SWI-Prolog the host has; native.2's engine refuses
        # one lacking the repairs at boot, but the gate and the image are verified on the bundled
        # engine only, so this stops here.
        # am[rests-on c-rt-n2ic-engine-refuses-unrepaired-host-1018@44fb07]
        if engine is None:
            carriers = sorted(file for file, bundled in said.items() if bundled is not None)
            raise Refused(UNSUPPORTED, f"{sys.executable} installed {wheel}, which bundles no engine, so "
                                       f"{native.name} would run whatever SWI-Prolog this host provides; "
                                       f"{native.name} {native.version} bundles its engine only in "
                                       f"{', '.join(carriers)}, so this host or interpreter is not supported")
        file, digest = engine
        rows = record(directory / wheel)
        if not any(path.rpartition("/")[2] == file and rows[path] == digest for path in rows):
            raise Refused(INTEGRITY, f"BUILD says {wheel} bundles {file} with sha256 {digest}, "
                                     f"and its RECORD lists no such file")
        site = Path(installed.locate_file(""))
        tops = {path.split("/")[0] for path in rows if ".dist-info/" not in path}
        outside = sorted(top for top in tops if top.endswith(".data"))
        if outside:
            raise Refused(INTEGRITY, f"{wheel} installs {outside}, outside site-packages, "
                                     f"which check does not follow")
        differing = differences(site, wheel, rows, tops)
        if differing:
            raise Refused(INTEGRITY, f"{native.name} as installed in {site} differs from {wheel}:\n  "
                                     + "\n  ".join(differing)
                                     + f"\nreinstall it with uv sync --frozen --reinstall-package {native.name}")
        for top in sorted(tops):
            if top.isidentifier() and f"{top}/__init__.py" in rows:
                spec = importlib.util.find_spec(top)
                found = Path(spec.origin).resolve() if spec is not None and spec.origin else None
                if found != (site / top / "__init__.py").resolve():
                    raise Refused(INTEGRITY, f"import {top} finds {found}, not the verified install in {site}; "
                                             f"something ahead of it on sys.path, such as PYTHONPATH, supplies it")
        compared = sum(1 for expected in rows.values() if expected is not None)
        print(f"native-wheels: {native.name} {native.version} is {wheel}, sha256 {digests[wheel]}, "
              f"from {native.directory}: its {compared} files are installed as its RECORD lists them, "
              f"engine {file} sha256 {digest}")


def main(arguments: list[str]) -> int:
    commands = {"place": place, "check": check}
    if len(arguments) != 1 or arguments[0] not in commands:
        print(__doc__, file=sys.stderr)
        return USAGE
    try:
        commands[arguments[0]]()
    except Refused as refusal:
        print(f"native-wheels: {refusal}", file=sys.stderr)
        return refusal.status
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

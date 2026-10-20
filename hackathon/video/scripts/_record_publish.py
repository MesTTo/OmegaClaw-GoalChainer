"""Purpose: publish a recording a wrapper rendered in its work directory, session.cast, session.gif and
session.mp4, as one capture: the cast and GIF in <the MP4 path's own directory under <captures>>/<sha256
of the MP4>/ and the MP4 at its published path, put there by one rename(2) that commits the capture.
record_publish in _record_lib.sh runs it as python3 -I _record_publish.py <work> <captures> <mp4>; it
exits 0 once the new capture is current and its MP4's directory synced, and 1 with the reason on
standard error when a step fails; an interrupt ends it as KeyboardInterrupt ends any Python program,
by SIGINT, with the capture the MP4 in place names whole."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import re
import secrets
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

# What a capture's directory holds beside the MP4 that names it by its digest.
# am[implements a-rfb-publish-module-1018@54117f]
PARTS = ("session.cast", "session.gif")

# The names this module writes, and so the only ones it removes: a capture is named by its MP4's
# SHA-256 in hex, and what a publication leaves to be removed carries a mark, .<name>.<token>.<kind>
# with a token of TOKEN_BYTES random bytes in hex, as moby renames a layer's folder to
# <digest>-<random>-removing: a capture set aside is .<its digest>.<token>.removing in its owner's
# directory (_set_aside), and a copy of an MP4 staged beside it is .<the MP4's name>.<token>.staged
# (_stage). A .gitkeep, notes or another MP4's files kept beside them are never touched.
# am[implements a-rfb-clear-own-names-1018@b4a658] am[rests-on c-rfb-moby-removing-1018@eb6dea]
# am[rests-on c-rfb-digest-names-captures-1018@da1132]
CAPTURE = f"[0-9a-f]{{{2 * hashlib.sha256().digest_size}}}"
# am[implements a-rfb-clear-own-names-1018@b4a658]
TOKEN_BYTES = 4


# A new name marking <name> as a publication's <kind> of leftover.
# am[implements a-rfb-clear-own-names-1018@b4a658]
def _mark(name: str, kind: str) -> str:
    return f".{name}.{secrets.token_hex(TOKEN_BYTES)}.{kind}"


# The names _mark gives a <kind> of leftover for any name <name> matches, <name> a regular expression.
# am[implements a-rfb-clear-own-names-1018@b4a658]
def _marks(name: str, kind: str) -> re.Pattern[str]:
    return re.compile(rf"\.{name}\.[0-9a-f]{{{2 * TOKEN_BYTES}}}\.{re.escape(kind)}")


# A publication that committed but could not make its commit durable.
# am[implements a-rfb-publish-module-1018@54117f] am[rests-on c-rfb-atomic-sync-raises-1018@09c67b]
class Unsynced(Exception):
    """The new capture is current, but the directory holding its MP4 could not be synced."""


# <path>, a file or a directory, fsynced through a descriptor of its own, as semantic_sleep syncs its
# store: this machine's sync(1), uutils coreutils, flushes every filesystem and fsyncs none of the
# paths it is given.
# am[implements a-rfb-publish-module-1018@54117f] am[rests-on c-rfb-uutils-sync-1018@d9cd23]
def _sync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | (os.O_DIRECTORY if path.is_dir() else 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


# <captures> held exclusively while the publication runs, by a lock on the directory's own
# descriptor, so no lock file appears among the captures; closing the descriptor releases it however
# the publication ends. Publications into one captures directory take turns.
# am[implements a-rfb-publish-module-1018@54117f] am[rests-on c-rfb-flock-directory-1018@5fbe54]
@contextlib.contextmanager
def _locked(captures: Path) -> Iterator[None]:
    fd = os.open(captures, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


# The SHA-256 of a file's bytes.
# Time: one pass over the file, a megabyte at a time.
# am[implements a-rfb-publish-module-1018@54117f]
def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


# The device and inode of a file or directory, which a rename within its filesystem keeps: the
# identity by which publish tells what its own renames did.
# am[implements a-rfb-commit-observed-1018@1435d8] am[rests-on c-rfb-rename-names-staged-inode-1018@3ebe99]
def _identity(status: os.stat_result) -> tuple[int, int]:
    return status.st_dev, status.st_ino


# Whether <path> itself, not a file a link there names, has the device and inode <identity>; a path
# that is gone has none, and one that cannot be read raises.
# am[implements a-rfb-commit-observed-1018@1435d8]
def _is(path: Path, identity: tuple[int, int]) -> bool:
    try:
        return _identity(os.lstat(path)) == identity
    except FileNotFoundError:
        return False


# Whether <capture> is a whole capture: a directory, not a link, holding the cast and the GIF as
# regular files and nothing else.
# am[implements a-rfb-publish-module-1018@54117f]
def _whole(capture: Path) -> bool:
    if capture.is_symlink() or not capture.is_dir():
        return False
    entries = sorted(os.scandir(capture), key=lambda entry: entry.name)
    return [entry.name for entry in entries] == list(PARTS) and all(entry.is_file(follow_symlinks=False)
                                                                    for entry in entries)


# The capture <path> renamed to its .removing mark beside it (_mark) and that rename synced, so its
# digest names no part of it before anything inside is removed: an interrupted removal leaves only
# the marked name, which the next publication clears, as moby renames a layer's folder to
# <digest>-<random>-removing first.
# am[implements a-rfb-publish-module-1018@54117f] am[rests-on c-rfb-moby-removing-1018@eb6dea]
# am[implements a-rfb-clear-own-names-1018@b4a658]
def _set_aside(path: Path) -> Path:
    aside = path.with_name(_mark(path.name, "removing"))
    os.rename(path, aside)
    _sync(path.parent)
    return aside


# <path> removed, a directory with everything in it; a failure is reported, and what is left keeps its
# mark for the next publication to clear.
# am[implements a-rfb-publish-module-1018@54117f]
def _remove(path: Path) -> None:
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as error:
        print(f"could not remove {path}: {error.strerror}", file=sys.stderr)


# <path> set aside and removed when it is there, reporting rather than raising a failure, for the
# steps that may not mask the failure they clean up after or undo a commit already made.
# am[implements a-rfb-publish-module-1018@54117f]
def _withdraw(path: Path) -> None:
    if not os.path.lexists(path):
        return
    try:
        aside = _set_aside(path)
    except OSError as error:
        print(f"could not set aside {path}: {error.strerror}", file=sys.stderr)
        return
    _remove(aside)


# What publications that stopped part-way left: captures set aside in <owner> and copies of <mp4>
# staged beside it, each carrying its mark (_marks). Only those are removed, the staged ones only
# under <mp4>'s own name, since another MP4 in that directory publishes under another lock and its
# copy may be live; a directory that cannot be listed, as one readable by no one, is left as it is.
# am[implements a-rfb-clear-own-names-1018@b4a658]
def _clear(owner: Path, mp4: Path) -> None:
    for directory, marks in ((owner, _marks(CAPTURE, "removing")), (mp4.parent, _marks(re.escape(mp4.name), "staged"))):
        try:
            leftovers = [entry for entry in directory.iterdir() if marks.fullmatch(entry.name)]
        except OSError:
            continue
        for entry in leftovers:
            _remove(entry)


# The directory under <captures>, the one captures root every wrapper passes, that the MP4 path <mp4>
# owns: <16 hex digits of the SHA-256 of the MP4's path, its directory resolved, relative to the
# resolved root>-<the MP4's file name>. Only that path's publications write there, whichever wrapper
# runs them, so one MP4 file has one owner directory and one lock, and the MP4 at <mp4> is the only
# one that can name a capture inside: its digest is every reference there is to those captures. The
# relative path keeps the name when the repository moves with both.
# am[implements a-rfb-owned-captures-1018@ac1c98] am[rests-on c-rfb-owned-references-1018@911156]
# am[rests-on c-rfb-shared-captures-1018@7c3c33] am[implements a-rfb-owner-key-path-only-1018@2c72ba]
# am[rests-on c-rfb-wrappers-key-captures-apart-1018@5181e4]
def owned(captures: Path, mp4: Path) -> Path:
    relative = os.path.relpath(Path(os.path.realpath(mp4.parent)) / mp4.name, os.path.realpath(captures))
    return captures / f"{hashlib.sha256(os.fsencode(relative)).hexdigest()[:16]}-{mp4.name}"


# <directory> made with every missing parent, each new entry synced in its parent before anything is
# filed below it, so a capture in a directory this publication made outlives a crash too. A directory
# another publication makes at the same moment is taken as made.
# am[implements a-rfb-owned-captures-1018@ac1c98]
def _made(directory: Path) -> None:
    missing = []
    while not directory.is_dir():
        missing.append(directory)
        directory = directory.parent
    for path in reversed(missing):
        path.mkdir(exist_ok=True)
        _sync(path.parent)


# <rendered> copied to its .staged mark in <mp4>'s directory (_mark), a name no other file has, with
# the render's mode, and synced, as semantic_sleep._atomic stages a write in a name of its own: the
# copy whose rename onto <mp4> commits a publication, one rename(2) within the directory the caller
# names whatever filesystem holds it, so <mp4> is always the old MP4 or the new one. Answers the
# copy's path and its device and inode, which <mp4> names once that rename returns. A copy that
# fails or is interrupted is removed again, and one interrupted as its open returns is left under
# its mark for the next publication to clear.
# Time: one pass over the MP4's bytes.
# am[implements a-rfb-publish-module-1018@54117f] am[implements a-rfb-commit-observed-1018@1435d8]
# am[rests-on c-rfb-atomic-stages-beside-1018@3f2842] am[rests-on c-rfb-rename-atomic-1018@6e9b0b]
# am[implements a-rfb-clear-own-names-1018@b4a658]
def _stage(rendered: Path, mp4: Path) -> tuple[Path, tuple[int, int]]:
    staged = mp4.parent / _mark(mp4.name, "staged")
    fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(fd, "wb") as copy, rendered.open("rb") as source:
            shutil.copyfileobj(source, copy, 1 << 20)
            copy.flush()
            os.fsync(copy.fileno())
            made = _identity(os.fstat(copy.fileno()))
        shutil.copymode(rendered, staged)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged, made


# <work>'s session.cast, session.gif and session.mp4 published as one capture, under the lock of the
# directory the MP4's path owns (owned). A copy of the MP4 is staged beside it (_stage), the cast and
# GIF are filed in that directory under the MP4's digest, a whole capture already there kept and
# anything else under that name set aside first, and the copy's rename onto <mp4> commits the
# capture. Before that rename everything the digest names is synced, the capture's parts and its
# directory, which a filed capture had synced in the work directory and a kept one has synced now,
# and its entry in the owner's directory, since a kept capture may be one a publication killed
# before its sync renamed in, as LevelDB syncs the directory of the files a MANIFEST names before
# flushing the MANIFEST (c-rfb-leveldb-sync-dir-manifest-1018). Once the MP4's directory is synced,
# every other capture in that directory, each a name of the digest's form (CAPTURE), is set aside
# and removed, since the MP4 just committed is the only one that names any of them, and every other
# name there is kept. A publication stopped before the commit, by a failure or an interrupt,
# removes its copy and withdraws the capture it filed, and one stopped after it keeps both. Which
# happened is read from the filesystem, <mp4> having the copy's device and
# inode once the rename returns and the digest's entry the inode the publication filed, never from a
# flag set after a call returns, which an interrupt raised as the call returns leaves unset, as a
# recovery reads the commit record rather than assuming the failure came first (086d15fb). A sync
# failing after the commit raises Unsynced with the replaced capture kept, as semantic_sleep._atomic
# fails when its sync after os.replace does, since the MP4 a crash leaves may be the replaced one.
# Captures other MP4 paths own, and any outside every owner's directory, as earlier publications
# filed them, are never touched, so a capture is removed only when every reference to it is known to
# be gone; nothing else reads the cast or GIF, so the digest is all that ties them to their MP4.
# Time: two passes over the MP4's bytes, a hash and a copy, plus one rename per step and one per
# capture the owner's directory held.
# am[implements a-rfb-publish-module-1018@54117f] am[rests-on c-rfb-atomic-sync-raises-1018@09c67b]
# am[rests-on c-rfb-shared-captures-1018@7c3c33] am[rests-on c-rfb-casts-unread-1018@1c1516]
# am[implements a-rfb-owned-captures-1018@ac1c98] am[rests-on c-integrate-recorder-shared-digest-lost-1018@f1aac2]
# am[implements a-rfb-commit-observed-1018@1435d8] am[rests-on c-rfb-rename-names-staged-inode-1018@3ebe99]
# am[rests-on c-rfb-filed-by-inode-1018@0d44e2] am[rests-on 086d15fb@dbbd16]
# am[implements a-rfb-clear-own-names-1018@b4a658]
# am[implements a-rfb-sync-owner-before-commit-1018@ad8a9f] am[rests-on c-rfb-commit-after-durable-1018@bbb3c4]
# am[rests-on c-rfb-leveldb-sync-dir-manifest-1018@93643e]
def publish(work: Path, captures: Path, mp4: Path) -> None:
    rendered = work / "session.mp4"
    digest = _digest(rendered)
    parts = work / "capture"
    parts.mkdir()
    for part in PARTS:
        os.rename(work / part, parts / part)
        _sync(parts / part)
    _sync(parts)
    filed = _identity(os.lstat(parts))
    owner = owned(captures, mp4)
    _made(owner)
    _made(mp4.parent)
    with _locked(owner):
        _clear(owner, mp4)
        copy, copied = _stage(rendered, mp4)
        capture = owner / digest
        try:
            if not _whole(capture):
                if os.path.lexists(capture):
                    _remove(_set_aside(capture))
                os.rename(parts, capture)
            else:
                for part in PARTS:
                    _sync(capture / part)
                _sync(capture)
            _sync(owner)
            os.rename(copy, mp4)
        except BaseException:
            if not _is(mp4, copied):
                copy.unlink(missing_ok=True)
                if _is(capture, filed):
                    _withdraw(capture)
            raise
        try:
            _sync(mp4.parent)
        except OSError as error:
            raise Unsynced(error.strerror) from error
        try:
            others = [other for other in owner.iterdir() if other.name != digest and re.fullmatch(CAPTURE, other.name)]
        except OSError as error:
            print(f"could not list {owner} to prune it: {error.strerror}", file=sys.stderr)
            others = []
        for other in others:
            _withdraw(other)


# The command line record_publish runs: its exit status, and on standard error what failed.
# am[implements a-rfb-publish-module-1018@54117f]
def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: _record_publish.py <work> <captures> <mp4>", file=sys.stderr)
        return 2
    work, captures, mp4 = (Path(argument) for argument in argv[1:])
    try:
        publish(work, captures, mp4)
    except Unsynced as error:
        print(f"published {mp4}, but syncing its directory failed ({error}), so the capture it replaced is kept",
              file=sys.stderr)
        return 1
    except OSError as error:
        where = f" ({error.filename})" if error.filename else ""
        print(f"could not publish {mp4}: {error.strerror}{where}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

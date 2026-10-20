"""Purpose: test the hackathon recording wrappers through the asciinema installed on this run's PATH,
with inert recorders and scripted renderers in a copy of the video's scripts, and their publisher,
_record_publish.py, where a fault or a pause has to fall inside it. A wrapper publishes a capture, an
MP4 with its cast and GIF in out/live-casts/<the directory the MP4's path owns>/<the MP4's
digest>/, committed by one rename of a copy staged beside the MP4: a recorder, a render or a
publication that fails before that rename comes back as the wrapper's own failure with every current
capture byte-identical and no work files left, one whose MP4's directory cannot be synced after it
fails with the new capture current and the replaced one kept, and a recorder that passes leaves one
capture, what asciinema recorded of it, the prior one pruned. A partial directory under the new
digest gives way to a whole capture, an MP4 published to another path keeps the other MP4's
capture, two MP4 paths holding the same bytes keep theirs apart, two publications of one MP4 take
turns, an interrupted prune leaves no digest naming part of a capture, a publication removes only
the names it writes, everything a commit names is synced before it, and a publication stopped at
any of its calls, in a process of its own as the wrappers run it, by a failure or an interrupt,
leaves a whole capture current and only marked leftovers, from which the next publication leaves
only its own. No live recorder runs: the copy's recorders are inert scripts and the wrappers see
only the resolved asciinema beside the system's own tools, so a run of older wrappers runs nothing
live either."""

from __future__ import annotations

import contextlib
import ctypes
import errno
import hashlib
import importlib.util
import itertools
import json
import os
import re
import shlex
import shutil
import struct
import subprocess
import sys
import threading
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "hackathon" / "video" / "scripts"

# The one captures root, under hackathon/video, that every wrapper passes its publisher.
# am[verifies a-rfb-owner-key-path-only-1018@2c72ba]
CAPTURES = "out/live-casts"
# What each wrapper records: every recorder it runs, in order, with the captures root it publishes
# into and the path of the MP4 it publishes.
# am[verifies a-rre-installed-recorder-tests-1018@18f24b] am[verifies a-rfb-boundary-tests-1018@ac6d70]
WRAPPERS = {
    "record-terminal-live-demo.sh": [("live-terminal-full-demo.sh", CAPTURES, "out/omegaclaw-terminal-live-demo.mp4")],
    "record-codex-omegaclaw-loop.sh": [
        ("live-codex-omegaclaw-loop.sh", CAPTURES, "public/recordings/codex-omegaclaw-loop.mp4")],
    "record-codex-omegaclaw.sh": [("live-codex-omegaclaw.sh", CAPTURES, "public/recordings/codex-omegaclaw.mp4")],
    "record-demo-clips.sh": [
        ("live-codex-selftest.sh", CAPTURES, "public/recordings/codex-auth-selftest.mp4"),
        ("live-goalchainer-audit.sh", CAPTURES, "public/recordings/goalchainer-demo.mp4")],
}
FAILURES = [(wrapper, index) for wrapper, runs in WRAPPERS.items() for index in range(len(runs))]

# An inert recorder: one line naming it, then status 3 when INERT_FAILS names it.
INERT = '#!/bin/sh\necho "inert recorder {name}"\n[ "${{INERT_FAILS:-}}" != {name} ] || exit 3\n'
# The scripted renderers: agg writes its output as "gif of " and its input, and ffmpeg its output
# as "mp4 of " and its -i file, AGG_FAILS or FFMPEG_FAILS making that one stop after the first part,
# as a render cut off mid-file would; ffprobe answers a duration.
AGG = r'''#!/bin/sh
for argument; do input="$output"; output="$argument"; done
printf 'gif of ' > "$output"
[ -z "${AGG_FAILS:-}" ] || exit 1
cat "$input" >> "$output"
'''
FFMPEG = r'''#!/bin/sh
while [ "$#" -gt 1 ]; do [ "$1" = -i ] && input="$2"; shift; done
printf 'mp4 of ' > "$1"
[ -z "${FFMPEG_FAILS:-}" ] || exit 1
cat "$input" >> "$1"
'''
FFPROBE = "#!/bin/sh\necho 1.0\n"
# An ffmpeg whose MP4 is known beforehand, as a re-render of an earlier cast's would be.
# am[verifies a-rfb-publish-regressions-1018@296511]
FIXED_FFMPEG = '#!/bin/sh\nfor argument; do output="$argument"; done\nprintf "fixed mp4" > "$output"\n'
# A python3 for the wrappers' PATH whose run of _record_publish.py is UNSYNCABLE_PUBLISH's and whose
# every other run is the system python3's.
# am[verifies a-rfb-unsyncable-by-fsync-1019@45e4fe]
UNSYNCABLE_PYTHON = ('#!/bin/sh\nif [ "$1" = -I ] && [ "$(basename -- "$2")" = _record_publish.py ]; then\n'
                     '  shift; exec {python} -I {driver} "$@"\nfi\nexec {python} "$@"\n')
# _record_publish.py run with the fsync of the MP4's own directory, told by its device and inode,
# failing with EIO, as a failing disk fails it whatever filesystem holds the directory, and every
# other call made as it is.
# am[verifies a-rfb-unsyncable-by-fsync-1019@45e4fe]
UNSYNCABLE_PUBLISH = r'''
import errno, importlib.util, os, sys
module, *arguments = sys.argv[1:]
spec = importlib.util.spec_from_file_location("record_publish", module)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
directory, fsync = os.path.dirname(os.path.abspath(arguments[-1])), os.fsync
def failing(fd):
    if os.path.samestat(os.fstat(fd), os.stat(directory)):
        raise OSError(errno.EIO, os.strerror(errno.EIO))
    fsync(fd)
os.fsync = failing
sys.exit(publisher.main([module, *arguments]))
'''
# The names a publication leaves to be removed, as the publisher marks them: a capture set aside in
# the directory its MP4's path owns, and a copy of the MP4 named <name> staged beside it.
# am[verifies a-rfb-clear-own-names-1018@b4a658]
SET_ASIDE = r"\.[0-9a-f]{64}\.[0-9a-f]{8}\.removing"


# am[verifies a-rfb-clear-own-names-1018@b4a658]
def _staged(name: str) -> str:
    return rf"\.{re.escape(name)}\.[0-9a-f]{{8}}\.staged"


# The installed recorder, resolved from this run's PATH, wherever the gate installed it.
# am[verifies a-rre-installed-recorder-tests-1018@18f24b]
ASCIINEMA = shutil.which("asciinema")
# The inotify(7) events a watched directory reports, and those that create, change or remove a name
# in place, which a name a rename puts in place never sees: IN_MODIFY, IN_ATTRIB, IN_CLOSE_WRITE,
# IN_CREATE, IN_DELETE and IN_MOVED_FROM.
# am[verifies a-rfb-publish-regressions-1018@296511]
IN_ALL_EVENTS, IN_CLOSE_WRITE, IN_MOVED_FROM, IN_MOVED_TO, IN_CREATE, IN_Q_OVERFLOW = 0xFFF, 0x8, 0x40, 0x80, 0x100, 0x4000
IN_CHANGED = 0x2 | 0x4 | IN_CLOSE_WRITE | IN_CREATE | 0x200 | IN_MOVED_FROM


# The recorder the wrappers run is the installed asciinema, never a stand-in, found on this run's PATH
# rather than in one distribution's directory: a machine without it fails these tests rather than
# skipping them.
# am[verifies a-rre-installed-recorder-tests-1018@18f24b]
@pytest.fixture(autouse=True, scope="module")
def _installed_asciinema():
    assert ASCIINEMA, "these tests drive the installed asciinema 2.4.0: put it on PATH, as apt install asciinema does"


# A copy of the video's scripts whose recorders are inert and whose renderers are scripted, each
# recorder holding a prior capture, a known MP4 with its cast and GIF under the MP4's digest;
# asciinema keeps its configuration in the tree, with its desktop notifications off. The resolved
# asciinema is linked into the tree's own bin, so the wrappers' PATH holds it, the scripted renderers
# and the system's directories and nothing else of this run's PATH, with a private HOME and no
# provider credential. Answers the environment a wrapper runs in.
# am[verifies a-rre-installed-recorder-tests-1018@18f24b] am[verifies a-rfb-boundary-tests-1018@ac6d70]
def _tree(tmp_path: Path) -> dict[str, str]:
    video = tmp_path / "hackathon" / "video"
    shutil.copytree(SCRIPTS, video / "scripts", ignore=shutil.ignore_patterns("recorders"))
    (video / "scripts" / "recorders").mkdir()
    for runs in WRAPPERS.values():
        for recorder, captures, mp4 in runs:
            (video / "scripts" / "recorders" / recorder).write_text(INERT.format(name=recorder), encoding="utf-8")
            (video / "scripts" / "recorders" / recorder).chmod(0o755)
            kept = f"kept {mp4}".encode()
            (video / mp4).parent.mkdir(parents=True, exist_ok=True)
            (video / mp4).write_bytes(kept)
            capture = video / _owner(video, captures, mp4) / hashlib.sha256(kept).hexdigest()
            capture.mkdir(parents=True)
            (capture / "session.cast").write_bytes(f"kept cast {recorder}".encode())
            (capture / "session.gif").write_bytes(f"kept gif {recorder}".encode())
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "asciinema").symlink_to(ASCIINEMA)
    for name, script in (("agg", AGG), ("ffmpeg", FFMPEG), ("ffprobe", FFPROBE)):
        (tmp_path / "bin" / name).write_text(script, encoding="utf-8")
        (tmp_path / "bin" / name).chmod(0o755)
    (tmp_path / "asciinema").mkdir()
    (tmp_path / "asciinema" / "config").write_text("[notifications]\nenabled = no\n", encoding="utf-8")
    (tmp_path / "home").mkdir()
    return {"PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin", "HOME": str(tmp_path / "home"), "TERM": "xterm",
            "ASCIINEMA_CONFIG_HOME": str(tmp_path / "asciinema")}


# A wrapper run from the copy with <arguments>, with no terminal on standard input, as a gate runs it.
# am[verifies a-rre-installed-recorder-tests-1018@18f24b]
def _record(tmp_path: Path, wrapper: str, env: dict[str, str], *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(tmp_path / "hackathon" / "video" / "scripts" / wrapper), *arguments],
                          cwd=tmp_path, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          check=False)


# Every file the video's out/ and public/ hold, by path under hackathon/video, with its bytes: all a
# wrapper may publish into, so a test sees a write beside the captures as well as among them.
# am[verifies a-rfb-boundary-tests-1018@ac6d70]
def _published(video: Path) -> dict[str, bytes]:
    return {str(path.relative_to(video)): path.read_bytes()
            for top in ("out", "public") for path in (video / top).rglob("*") if path.is_file()}


# The paths that differ between two _published views, each of which must be one of the named
# recorders' MP4 or lie in the directory that MP4's path owns.
# am[verifies a-rfb-boundary-tests-1018@ac6d70]
def _changed_only_by(video: Path, before: dict[str, bytes], after: dict[str, bytes],
                     runs: list[tuple[str, str, str]]) -> bool:
    changed = {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)}
    owners = {mp4: _owner(video, captures, mp4) for _, captures, mp4 in runs}
    return all(any(path == mp4 or path.startswith(f"{owner}/") for mp4, owner in owners.items()) for path in changed)


# The directory under hackathon/video where the MP4 <mp4> keeps its captures, as the publisher names
# it (owned).
# am[verifies a-rfb-owned-captures-1018@ac1c98]
def _owner(video: Path, captures: str, mp4: str | Path) -> str:
    return str(_publisher().owned(video / captures, video / mp4).relative_to(video))


# The capture a recorder holds now: its MP4 and the cast and GIF in the directory the MP4's digest
# names, which must be the only one in the directory its path owns.
# am[verifies a-rfb-boundary-tests-1018@ac6d70]
def _current(video: Path, captures: str, mp4: str) -> tuple[bytes, bytes, bytes]:
    published = (video / mp4).read_bytes()
    digest = hashlib.sha256(published).hexdigest()
    owner = video / _owner(video, captures, mp4)
    assert sorted(path.name for path in owner.iterdir()) == [digest]
    return published, (owner / digest / "session.cast").read_bytes(), (owner / digest / "session.gif").read_bytes()


# What a run left beside its captures: a work directory or a status file.
# am[verifies a-rre-installed-recorder-tests-1018@18f24b]
def _left(tmp_path: Path) -> list[Path]:
    return [*tmp_path.rglob(".recording.*"), *tmp_path.rglob("*.status")]


# A recorder that fails comes back as the wrapper's status, 3, publishing nothing for it or for any
# recorder after it and leaving no work files; a clip recorded before it keeps its own new capture.
# am[verifies a-rre-installed-recorder-tests-1018@18f24b] am[verifies a-rre-wrapper-status-1018@6b705b]
@pytest.mark.parametrize("wrapper,failing", FAILURES, ids=[f"{wrapper}-{index}" for wrapper, index in FAILURES])
def test_a_failed_recorder_publishes_nothing_and_its_status_comes_back(tmp_path, wrapper, failing):
    runs = WRAPPERS[wrapper]
    env = _tree(tmp_path)
    video = tmp_path / "hackathon" / "video"
    before = _published(video)
    run = _record(tmp_path, wrapper, {**env, "INERT_FAILS": runs[failing][0]})

    assert run.returncode == 3, run.stdout + run.stderr
    assert _changed_only_by(video, before, _published(video), runs[:failing])
    assert all(_current(video, captures, mp4)[0] != before[mp4] for _, captures, mp4 in runs[:failing])
    assert f"Wrote {video / runs[failing][2]}" not in run.stdout
    assert _left(tmp_path) == []


# A render that fails, agg's or ffmpeg's, partway through its file, publishes nothing at all and
# fails the wrapper, leaving no work files.
# am[verifies a-rre-installed-recorder-tests-1018@18f24b] am[verifies a-rre-wrapper-status-1018@6b705b]
@pytest.mark.parametrize("renderer", ["AGG_FAILS", "FFMPEG_FAILS"])
@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_a_failed_render_publishes_nothing(tmp_path, wrapper, renderer):
    env = _tree(tmp_path)
    video = tmp_path / "hackathon" / "video"
    before = _published(video)
    run = _record(tmp_path, wrapper, {**env, renderer: "1"})

    assert run.returncode != 0, run.stdout + run.stderr
    assert _published(video) == before
    assert "Wrote" not in run.stdout and _left(tmp_path) == []


# A publication that fails before its commit, its capture directory or its MP4's directory refusing
# writes, fails the wrapper and keeps every prior capture whole: every file in out/ and public/ the
# same, no new capture directory and no work files (c-tbr-rre-publication-partial-1018).
# am[verifies a-rfb-boundary-tests-1018@ac6d70] am[verifies a-rfb-capture-commit-1018@2741d7]
@pytest.mark.parametrize("refusing", ["captures", "mp4"])
@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_a_failed_publication_keeps_the_prior_capture_whole(tmp_path, wrapper, refusing):
    runs = WRAPPERS[wrapper]
    env = _tree(tmp_path)
    video = tmp_path / "hackathon" / "video"
    _, captures, mp4 = runs[0]
    locked = video / _owner(video, captures, mp4) if refusing == "captures" else (video / mp4).parent
    before = _published(video)
    locked.chmod(0o555)
    try:
        with pytest.raises(PermissionError):
            (locked / "probe").touch()
        run = _record(tmp_path, wrapper, env)
    finally:
        locked.chmod(0o755)

    assert run.returncode != 0, run.stdout + run.stderr
    assert _published(video) == before
    assert "Wrote" not in run.stdout and _left(tmp_path) == []


# A publication whose MP4's directory cannot be synced once the MP4's rename has committed it fails
# the wrapper: the new MP4 and the cast and GIF its digest names are current, and the capture they
# replaced is kept beside them, since the MP4 a crash leaves may still be the one naming it
# (i-rfb-prune-before-durable-1018). The fault is an EIO from that directory's fsync, raised in the
# publisher's own process through the wrappers' python3, so it falls on the publisher's sync on any
# filesystem; a directory no one may read is no such fault on SSHFS, which opens a directory without
# asking its server and answers a directory fsync with success (c-rfb-sshfs-opendir-lazy-1019,
# c-rfb-sshfs-fsyncdir-noop-1019).
# am[verifies a-rfb-durable-prune-1018@77dcb7] am[verifies a-rfb-unsyncable-by-fsync-1019@45e4fe]
# am[rests-on c-rfb-sshfs-opendir-lazy-1019@204ca2] am[rests-on c-rfb-sshfs-fsyncdir-noop-1019@7402de]
@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_a_publication_it_cannot_sync_keeps_the_capture_it_replaced(tmp_path, wrapper):
    runs = WRAPPERS[wrapper]
    env = _tree(tmp_path)
    video = tmp_path / "hackathon" / "video"
    _, captures, mp4 = runs[0]
    python = shutil.which("python3", path="/usr/bin:/bin")
    assert python, "the wrappers run their publisher with the system's python3"
    driver = tmp_path / "bin" / "unsyncable_publish.py"
    driver.write_text(UNSYNCABLE_PUBLISH, encoding="utf-8")
    shim = tmp_path / "bin" / "python3"
    shim.write_text(UNSYNCABLE_PYTHON.format(python=shlex.quote(python), driver=shlex.quote(str(driver))), encoding="utf-8")
    shim.chmod(0o755)
    before = _published(video)
    run = _record(tmp_path, wrapper, env)
    after = _published(video)
    digest = hashlib.sha256(after[mp4]).hexdigest()
    owner = _owner(video, captures, mp4)
    prior = {path: data for path, data in before.items() if path.startswith(f"{owner}/")}
    new = {path: data for path, data in after.items() if path.startswith(f"{owner}/{digest}/")}

    assert run.returncode != 0, run.stdout + run.stderr
    assert f"but syncing its directory failed ({os.strerror(errno.EIO)})" in run.stderr, run.stderr
    assert "Wrote" not in run.stdout and _left(tmp_path) == []
    assert _changed_only_by(video, before, after, runs[:1]) and after[mp4] != before[mp4]
    assert {path: data for path, data in after.items() if path.startswith(f"{owner}/")} == {**prior, **new}
    assert sorted(new) == [f"{owner}/{digest}/session.cast", f"{owner}/{digest}/session.gif"]
    cast = new[f"{owner}/{digest}/session.cast"]
    assert (new[f"{owner}/{digest}/session.gif"], after[mp4]) == (b"gif of " + cast, b"mp4 of gif of " + cast)


# A recorder that passes publishes one capture: its MP4 rendered from the GIF rendered from the
# asciicast asciinema wrote of the inert recorder's own output, the cast and GIF under the MP4's
# digest, the prior capture pruned and nothing else written, each MP4 named as written.
# am[verifies a-rre-installed-recorder-tests-1018@18f24b] am[verifies a-rfb-capture-commit-1018@2741d7]
@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_a_passing_recorder_publishes_one_capture_of_what_asciinema_recorded(tmp_path, wrapper):
    env = _tree(tmp_path)
    video = tmp_path / "hackathon" / "video"
    before = _published(video)
    run = _record(tmp_path, wrapper, env)

    assert run.returncode == 0, run.stdout + run.stderr
    assert _changed_only_by(video, before, _published(video), WRAPPERS[wrapper])
    for recorder, captures, mp4 in WRAPPERS[wrapper]:
        published, cast, gif = _current(video, captures, mp4)
        header, *events = cast.decode("utf-8").splitlines()
        assert json.loads(header)["version"] == 2
        assert any(f"inert recorder {recorder}" in json.loads(event)[2] for event in events)
        assert (gif, published) == (b"gif of " + cast, b"mp4 of " + b"gif of " + cast)
        assert f"Wrote {video / mp4}" in run.stdout
    assert _left(tmp_path) == []
    assert os.access(video / WRAPPERS[wrapper][0][2], os.R_OK)


# A directory already under the new MP4's digest that is not a whole capture, as an interrupted prune
# of an older publisher left one, gives way: it is set aside and the new capture filed in its place,
# so the published MP4's digest names its own cast and GIF (c-rfb-partial-digest-trusted-1018).
# am[verifies a-rfb-publish-regressions-1018@296511]
@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_a_partial_directory_under_the_new_digest_gives_way_to_a_whole_capture(tmp_path, wrapper):
    env = _tree(tmp_path)
    video = tmp_path / "hackathon" / "video"
    (tmp_path / "bin" / "ffmpeg").write_text(FIXED_FFMPEG, encoding="utf-8")
    for _, captures, mp4 in WRAPPERS[wrapper]:
        partial = video / _owner(video, captures, mp4) / hashlib.sha256(b"fixed mp4").hexdigest()
        partial.mkdir()
        (partial / "session.gif").write_bytes(b"gif an interrupted prune left")
    run = _record(tmp_path, wrapper, env)

    assert run.returncode == 0, run.stdout + run.stderr
    for _, captures, mp4 in WRAPPERS[wrapper]:
        published, cast, gif = _current(video, captures, mp4)
        assert (published, gif) == (b"fixed mp4", b"gif of " + cast)


# An MP4 published to another path shares its recording's captures directory with the MP4 already
# published, whichever wrapper names the path, and that MP4 keeps the capture it names: each path
# owns its own directory there (c-rfb-shared-captures-1018).
# am[verifies a-rfb-publish-regressions-1018@296511]
@pytest.mark.parametrize("wrapper,shared", [("record-terminal-live-demo.sh", "record-terminal-live-demo.sh"),
                                            ("record-cast.sh", "record-codex-omegaclaw-loop.sh")])
def test_an_mp4_published_to_another_path_keeps_the_other_mp4s_capture(tmp_path, wrapper, shared):
    env = _tree(tmp_path)
    video = tmp_path / "hackathon" / "video"
    [(recorder, captures, mp4)] = WRAPPERS[shared]
    elsewhere = tmp_path / "elsewhere" / Path(mp4).name
    recorder_arguments = [] if wrapper == shared else [str(video / "scripts" / "recorders" / recorder)]
    before = _published(video)
    run = _record(tmp_path, wrapper, env, *recorder_arguments, str(elsewhere))
    after = _published(video)
    digest = hashlib.sha256(elsewhere.read_bytes()).hexdigest()
    owner = _owner(video, captures, elsewhere)

    assert run.returncode == 0, run.stdout + run.stderr
    assert {path: data for path, data in after.items() if not path.startswith(f"{owner}/{digest}/")} == before
    assert sorted(path.name for path in (video / owner / digest).iterdir()) == ["session.cast", "session.gif"]


# The inotify events of each of <directories> while <run> runs, as (directory, mask, cookie, name),
# read through libc's inotify_init1 and inotify_add_watch and the kernel's struct inotify_event, so
# the check needs no tracer installed, which the gate hosts lack (c-rfb-gate-host-no-strace-1018); a
# queue that overflowed fails the test rather than hiding events.
# am[verifies a-rfb-publish-regressions-1018@296511]
def _watched(directories: set[Path], run):
    libc = ctypes.CDLL(None, use_errno=True)
    assert hasattr(libc, "inotify_init1"), "this test watches directories through Linux's inotify"
    fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    assert fd >= 0, os.strerror(ctypes.get_errno())
    try:
        watched = {}
        for directory in directories:
            wd = libc.inotify_add_watch(fd, os.fsencode(directory), IN_ALL_EVENTS)
            assert wd >= 0, os.strerror(ctypes.get_errno())
            watched[wd] = directory
        result = run()
        data = bytearray()
        with contextlib.suppress(BlockingIOError):
            while chunk := os.read(fd, 1 << 16):
                data += chunk
        events, offset = [], 0
        while offset < len(data):
            wd, mask, cookie, length = struct.unpack_from("iIII", data, offset)
            assert not mask & IN_Q_OVERFLOW, "the inotify queue overflowed"
            name = bytes(data[offset + 16:offset + 16 + length]).rstrip(b"\0")
            events.append((watched.get(wd), mask, cookie, os.fsdecode(name)))
            offset += 16 + length
        return result, events
    finally:
        os.close(fd)


# A wrapper puts each MP4 in place by one rename of a copy staged in the MP4's own directory and
# changes the published name no other way: inotify on that directory sees the name arrive only as
# the target of a rename whose source was created and written there earlier in the run, and never
# sees the name created, written, given new attributes or removed in place, so the publication is a
# rename on whatever filesystem holds the directory and never an unlink and a copy into its place
# (c-rfb-xdev-publication-destroys-capture-1018).
# am[verifies a-rfb-publish-regressions-1018@296511]
@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_each_mp4_is_put_in_place_only_by_renaming_a_copy_staged_beside_it(tmp_path, wrapper):
    env = _tree(tmp_path)
    video = tmp_path / "hackathon" / "video"
    published = [video / mp4 for _, _, mp4 in WRAPPERS[wrapper]]
    run, events = _watched({path.parent for path in published}, lambda: _record(tmp_path, wrapper, env))

    assert run.returncode == 0, run.stdout + run.stderr
    for path in published:
        here = [(mask, cookie, name) for directory, mask, cookie, name in events if directory == path.parent]
        arrivals = [cookie for mask, cookie, name in here if name == path.name and mask & IN_MOVED_TO]
        assert arrivals, here
        for cookie in arrivals:
            [(at, source)] = [(at, name) for at, (mask, moved, name) in enumerate(here) if mask & IN_MOVED_FROM and moved == cookie]
            staged = [mask for mask, _, name in here[:at] if name == source]
            assert any(mask & IN_CREATE for mask in staged) and any(mask & IN_CLOSE_WRITE for mask in staged), here
        assert [mask for mask, _, name in here if name == path.name and mask & IN_CHANGED] == [], here


# _record_publish.py loaded from the scripts it ships with, for the tests that drive it directly to
# put a fault or a pause where no wrapper reaches.
# am[verifies a-rfb-publish-module-1018@54117f]
def _publisher() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("record_publish", SCRIPTS / "_record_publish.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# A recording's captures directory and MP4 under <root>'s out/ and public/, holding a prior capture as
# _tree seeds each recorder's: the MP4 'kept clip' and its cast and GIF under its digest.
# am[verifies a-rfb-publish-regressions-1018@296511]
def _clip(root: Path) -> tuple[Path, Path]:
    captures, mp4 = root / "out" / "live-casts" / "clip", root / "public" / "recordings" / "clip.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"kept clip")
    capture = _publisher().owned(captures, mp4) / hashlib.sha256(b"kept clip").hexdigest()
    capture.mkdir(parents=True)
    for part in ("cast", "gif"):
        (capture / f"session.{part}").write_bytes(f"kept {part}".encode())
    return captures, mp4


# _record_publish.py's arguments for a work directory, made here, holding a cast, GIF and MP4 whose
# bytes name <label>, as a wrapper's renders leave one.
# am[verifies a-rfb-publish-regressions-1018@296511]
def _arguments(root: Path, label: str, captures: Path, mp4: Path) -> list[str]:
    work = root / f"work-{label}"
    work.mkdir()
    for part in ("cast", "gif", "mp4"):
        (work / f"session.{part}").write_bytes(f"{label} {part}".encode())
    return ["_record_publish.py", str(work), str(captures), str(mp4)]


# A staged copy of the MP4 that fails part-way, as a full disk under the MP4's directory fails it,
# fails the publication and leaves every file in out/ and public/ as it was: the published MP4, the
# capture it names, no staged copy and no new capture (c-rfb-xdev-publication-destroys-capture-1018).
# am[verifies a-rfb-publish-regressions-1018@296511]
def test_a_staged_copy_that_fails_keeps_the_published_mp4_and_its_capture(tmp_path, monkeypatch):
    publisher = _publisher()
    captures, mp4 = _clip(tmp_path)
    before = _published(tmp_path)

    def full(source, copy, length=0):
        copy.write(source.read(3))
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    monkeypatch.setattr(shutil, "copyfileobj", full)
    status = publisher.main(_arguments(tmp_path, "new", captures, mp4))

    assert status == 1
    assert _published(tmp_path) == before


# Two publications of one MP4 take turns: the second waits on the captures directory's lock while the
# first, paused after its MP4's rename and before its prune, holds it, then commits and prunes the
# first's capture, so the current MP4 names the only capture left
# (c-integrate-recorder-unlocked-prune-schedule-1018).
# am[verifies a-rfb-publish-regressions-1018@296511]
def test_two_publications_of_one_mp4_take_turns(tmp_path, monkeypatch):
    publisher = _publisher()
    captures, mp4 = _clip(tmp_path)
    paused, go, statuses = threading.Event(), threading.Event(), {}
    owner = publisher.owned(captures, mp4)
    withdraw = publisher._withdraw

    def pausing(path):
        if threading.current_thread().name == "A" and not paused.is_set():
            paused.set()
            go.wait()
        withdraw(path)

    monkeypatch.setattr(publisher, "_withdraw", pausing)
    runs = {label: threading.Thread(name=label, target=lambda label=label: statuses.__setitem__(
        label, publisher.main(_arguments(tmp_path, label, captures, mp4)))) for label in "AB"}
    runs["A"].start()
    assert paused.wait(30)
    runs["B"].start()
    runs["B"].join(1)
    held = (mp4.read_bytes(), sorted(path.name for path in owner.iterdir()))
    go.set()
    for run in runs.values():
        run.join(30)
    kept, a, b = (hashlib.sha256(data).hexdigest() for data in (b"kept clip", b"A mp4", b"B mp4"))

    assert held == (b"A mp4", sorted([kept, a]))
    assert statuses == {"A": 0, "B": 0}
    assert (mp4.read_bytes(), sorted(path.name for path in owner.iterdir())) == (b"B mp4", [b])


# A prune cut off part-way, as a killed rm -rf would cut it, leaves no digest naming part of a capture:
# the superseded capture was renamed to its .removing mark first, so only that name holds what is
# left, and the next publication clears it (c-rfb-partial-digest-trusted-1018).
# am[verifies a-rfb-publish-regressions-1018@296511] am[verifies a-rfb-clear-own-names-1018@b4a658]
def test_an_interrupted_prune_leaves_no_digest_naming_part_of_a_capture(tmp_path, monkeypatch):
    publisher = _publisher()
    captures, mp4 = _clip(tmp_path)
    rmtree = shutil.rmtree
    owner = publisher.owned(captures, mp4)

    def interrupted(path, *arguments, **keywords):
        next(Path(path).iterdir()).unlink()
        raise OSError(errno.EIO, os.strerror(errno.EIO))

    monkeypatch.setattr(shutil, "rmtree", interrupted)
    first = publisher.main(_arguments(tmp_path, "A", captures, mp4))
    left = {path.name: sorted(part.name for part in path.iterdir()) for path in owner.iterdir()}
    monkeypatch.setattr(shutil, "rmtree", rmtree)
    second = publisher.main(_arguments(tmp_path, "B", captures, mp4))
    a, b = (hashlib.sha256(data).hexdigest() for data in (b"A mp4", b"B mp4"))

    assert (first, second) == (0, 0)
    assert {name: parts for name, parts in left.items() if not name.startswith(".")} == {
        a: ["session.cast", "session.gif"]}
    assert [(bool(re.fullmatch(SET_ASIDE, name)), len(parts)) for name, parts in left.items()
            if name.startswith(".")] == [(True, 1)]
    assert (mp4.read_bytes(), sorted(path.name for path in owner.iterdir())) == (b"B mp4", [b])


# A publication removes only the names it writes: in the directory its MP4's path owns, the captures
# under digests other than its own and captures set aside as .<digest>.<token>.removing, and beside
# the MP4 the copies of that MP4 staged as .<its name>.<token>.staged. A .gitkeep, a notes directory
# and a notes file kept among the captures, and an editor's files and another MP4's staged copy
# beside the MP4, stay as they were (i-rfb-clear-any-dotname-1018, i-rfb-prune-any-name-1018).
# am[verifies a-rfb-clear-own-names-1018@b4a658]
def test_a_publication_removes_only_the_names_it_writes(tmp_path):
    publisher = _publisher()
    captures, mp4 = _clip(tmp_path)
    owner = publisher.owned(captures, mp4)
    kept, new = (hashlib.sha256(data).hexdigest() for data in (b"kept clip", b"new mp4"))
    foreign = {owner / ".gitkeep": b"", owner / ".notes" / "take-3.txt": b"take 3", owner / "notes.txt": b"notes",
               mp4.parent / ".clip.mp4.staged-draft": b"draft", mp4.parent / ".clip.mp4.swp": b"swap",
               mp4.parent / ".other.mp4.0123abcd.staged": b"another MP4's staged copy"}
    for path, data in foreign.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (owner / f".{kept}.0123abcd.removing").mkdir()
    (owner / f".{kept}.0123abcd.removing" / "session.gif").write_bytes(b"part of a capture set aside")
    (mp4.parent / ".clip.mp4.89abcdef.staged").write_bytes(b"a copy a stopped publication staged")

    assert publisher.main(_arguments(tmp_path, "new", captures, mp4)) == 0
    assert {path: path.read_bytes() if path.exists() else None for path in foreign} == foreign
    assert sorted(path.name for path in owner.iterdir()) == sorted([".gitkeep", ".notes", "notes.txt", new])
    assert sorted(path.name for path in mp4.parent.iterdir()) == sorted([
        ".clip.mp4.staged-draft", ".clip.mp4.swp", ".other.mp4.0123abcd.staged", "clip.mp4"])
    assert mp4.read_bytes() == b"new mp4"


# Before the rename that commits the new MP4, everything its digest names is synced: the capture's
# two parts, its directory, and the owner's directory after the last rename into it, whether the
# publication filed the capture or kept a whole one already under that digest, which a publication
# killed before its sync may have renamed in (i-rfb-kept-capture-unsynced-1018). Each fsync is told
# by its descriptor's device and inode, so a part synced in the work directory counts as itself.
# am[verifies a-rfb-sync-owner-before-commit-1018@ad8a9f]
@pytest.mark.parametrize("kept", [False, True], ids=["filed", "kept"])
def test_everything_a_commit_names_is_synced_before_it(tmp_path, kept):
    publisher = _publisher()
    captures, mp4 = _clip(tmp_path)
    owner = publisher.owned(captures, mp4)
    capture = owner / hashlib.sha256(b"new mp4").hexdigest()
    if kept:
        capture.mkdir()
        for part in ("cast", "gif"):
            (capture / f"session.{part}").write_bytes(f"new {part}".encode())
    events, fsync, rename = [], os.fsync, os.rename

    def synced(fd):
        fsync(fd)
        status = os.fstat(fd)
        events.append(("fsync", (status.st_dev, status.st_ino)))

    def renamed(source, target, *arguments, **keywords):
        rename(source, target, *arguments, **keywords)
        events.append(("rename", Path(target)))

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "fsync", synced)
        patch.setattr(os, "rename", renamed)
        status = publisher.main(_arguments(tmp_path, "new", captures, mp4))
    commit = events.index(("rename", mp4))
    last = max((at for at, (kind, value) in enumerate(events[:commit]) if kind == "rename" and value.parent == owner),
               default=-1)
    named = [os.lstat(path) for path in (capture / "session.cast", capture / "session.gif", capture, owner)]
    *contents, entry = [(found.st_dev, found.st_ino) for found in named]

    assert status == 0
    assert set(contents) <= {value for kind, value in events[:commit] if kind == "fsync"}
    assert entry in {value for kind, value in events[last + 1:commit] if kind == "fsync"}


# The os functions through which a publication opens, makes, renames, removes, syncs or changes the
# mode of a name: every point at which a failure or an interrupt can stop it.
# am[verifies a-rfb-commit-observed-1018@1435d8]
STEPS = ("open", "mkdir", "rename", "replace", "fsync", "unlink", "rmdir", "chmod")


# The program a stopped publication runs (_faulted): <module>'s main on <arguments> with the <at>th
# of its calls through <steps> faulted by <fault>, printing main's status, or "interrupted", and every
# call it made as its last line of JSON.
# am[verifies a-rfb-enumeration-fresh-process-1019@3e2467]
STOPPED_PUBLICATION = r'''
import errno, importlib.util, json, os, sys
module, fault, at, steps, *arguments = sys.argv[1:]
spec = importlib.util.spec_from_file_location("record_publish", module)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
calls = []
def faulty(name, call):
    def step(*args, **keywords):
        paths = (os.path.basename(os.fspath(a)) for a in args if isinstance(a, (str, os.PathLike)))
        calls.append(f"{name}({', '.join(paths)})")
        if len(calls) != int(at):
            return call(*args, **keywords)
        if fault == "failure":
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        call(*args, **keywords)
        raise KeyboardInterrupt
    return step
for name in json.loads(steps):
    setattr(os, name, faulty(name, getattr(os, name)))
try:
    status = publisher.main([module, *arguments])
except KeyboardInterrupt:
    status = "interrupted"
print(json.dumps([status, calls]))
'''


# _record_publish.py's main run on <arguments> in a fresh python -I interpreter, as record_publish
# runs it, with the <at>th of its calls through STEPS faulted: a "failure" raises EIO in place of the
# call, and an "interrupt" makes the call and then raises KeyboardInterrupt, as CPython raises the
# KeyboardInterrupt of a SIGINT delivered during a system call once the call returns (393cccf1). The
# run's process ends with it, and its end closes whatever the run left open, as an interrupted
# publication's does, so no descriptor it leaked is still open when a later publication unlinks the
# file, which on FUSE would leave a .fuse_hidden name (c-rfb-enumeration-in-process-leak-1019).
# Answers main's status, or "interrupted" when the interrupt came out of it, and every call the run
# made, by name and the base names of its path arguments.
# am[verifies a-rfb-commit-observed-1018@1435d8] am[rests-on 393cccf1@d25084]
# am[verifies a-rfb-enumeration-fresh-process-1019@3e2467] am[rests-on c-rfb-enumeration-in-process-leak-1019@8505d4]
def _faulted(arguments: list[str], fault: str, at: int) -> tuple[int | str, list[str]]:
    run = subprocess.run([sys.executable, "-I", "-c", STOPPED_PUBLICATION, str(SCRIPTS / "_record_publish.py"), fault,
                          str(at), json.dumps(STEPS), *arguments[1:]], capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr
    status, calls = json.loads(run.stdout.splitlines()[-1])
    return status, calls


# What a publication left of the clip at <mp4>: the MP4's bytes, each capture in the directory its
# path owns with its parts' bytes, the dot-names in that directory, and the names beside the MP4.
# am[verifies a-rfb-commit-observed-1018@1435d8]
def _clip_state(publisher: types.ModuleType, captures: Path, mp4: Path):
    owner = publisher.owned(captures, mp4)
    names = sorted(path.name for path in owner.iterdir())
    held = {name: {part.name: part.read_bytes() for part in (owner / name).iterdir()}
            for name in names if not name.startswith(".")}
    beside = sorted(path.name for path in mp4.parent.iterdir() if path != mp4)
    return mp4.read_bytes(), held, [name for name in names if name.startswith(".")], beside


# A publication stopped at any of its calls, by a failure in place of the call or an interrupt as it
# returns, leaves the clip's MP4 the kept one naming the only capture, or the new one naming its
# whole capture with the kept capture still beside it or pruned, and every other name it leaves
# carrying its mark, a capture set aside or a staged copy of this MP4; the next publication then
# leaves its own capture and MP4 and nothing else. The fault falls on the 1st, 2nd, ... call through
# STEPS until a publication makes fewer, as SQLite's do_ioerr_test fails its Nth I/O operation
# (c-rfb-sqlite-ioerr-loop-1018), so an interrupt as the MP4's rename returns keeps the capture the
# new MP4 names (i-rfb-post-commit-interrupt-withdraws-1018) and one as the capture's rename returns
# leaves no capture the MP4 does not name (i-rfb-placement-flag-stale-1018).
# am[verifies a-rfb-commit-observed-1018@1435d8] am[rests-on c-rfb-sqlite-ioerr-loop-1018@c676bf]
# am[verifies a-rfb-clear-own-names-1018@b4a658]
@pytest.mark.parametrize("fault", ["interrupt", "failure"])
def test_a_publication_stopped_at_any_call_leaves_a_whole_capture_current(tmp_path, fault):
    publisher = _publisher()
    parts = {label: {"session.cast": f"{label} cast".encode(), "session.gif": f"{label} gif".encode()}
             for label in ("kept", "new", "next")}
    kept, new, following = (hashlib.sha256(data).hexdigest() for data in (b"kept clip", b"new mp4", b"next mp4"))
    stopped = [(b"kept clip", {kept: parts["kept"]}), (b"new mp4", {new: parts["new"]}),
               (b"new mp4", {kept: parts["kept"], new: parts["new"]})]
    statuses = ["interrupted"] if fault == "interrupt" else [0, 1]
    wrong = []
    for at in itertools.count(1):
        root = tmp_path / str(at)
        root.mkdir()
        captures, mp4 = _clip(root)
        status, calls = _faulted(_arguments(root, "new", captures, mp4), fault, at)
        state = _clip_state(publisher, captures, mp4)
        if len(calls) < at:
            break
        if (status not in statuses or state[:2] not in stopped or (status == 0 and state[0] != b"new mp4")
                or not all(re.fullmatch(SET_ASIDE, name) for name in state[2])
                or not all(re.fullmatch(_staged(mp4.name), name) for name in state[3])):
            wrong.append((calls[at - 1], status, state))
        then = publisher.main(_arguments(root, "next", captures, mp4))
        if (then, _clip_state(publisher, captures, mp4)) != (0, (b"next mp4", {following: parts["next"]}, [], [])):
            wrong.append((calls[at - 1], "then", then, _clip_state(publisher, captures, mp4)))

    assert (status, state) == (0, (b"new mp4", {new: parts["new"]}, [], []))
    assert any(call.startswith("rename(") and call.endswith(f", {mp4.name})") for call in calls), calls
    assert wrong == [], "\n".join(map(repr, wrong))


# Two MP4 paths sharing a captures directory and the very same bytes keep their captures apart: A
# and B publish X, A then publishes Y, and each MP4 still names a whole capture, the only one in the
# directory its path owns, while a capture filed outside every owner's directory, as 97e8ff3 filed
# them, is left as it was (c-integrate-recorder-shared-digest-lost-1018).
# am[verifies a-rfb-owned-captures-1018@ac1c98]
def test_two_mp4s_holding_the_same_bytes_keep_their_captures_apart(tmp_path):
    publisher = _publisher()
    captures = tmp_path / "out" / "live-casts" / "clip"
    first, second = tmp_path / "public" / "a.mp4", tmp_path / "public" / "b.mp4"
    unowned = captures / hashlib.sha256(b"earlier mp4").hexdigest()
    unowned.mkdir(parents=True)
    for part in ("cast", "gif"):
        (unowned / f"session.{part}").write_bytes(f"earlier {part}".encode())
    for index, (mp4, payload) in enumerate(((first, "X"), (second, "X"), (first, "Y"))):
        work = tmp_path / f"work-{index}"
        work.mkdir()
        for part in ("cast", "gif", "mp4"):
            (work / f"session.{part}").write_bytes(f"{payload} {part}".encode())
        assert publisher.main(["_record_publish.py", str(work), str(captures), str(mp4)]) == 0

    for mp4, payload in ((first, "Y"), (second, "X")):
        owner, digest = publisher.owned(captures, mp4), hashlib.sha256(mp4.read_bytes()).hexdigest()
        assert mp4.read_bytes() == f"{payload} mp4".encode()
        assert sorted(path.name for path in owner.iterdir()) == [digest]
        assert [(owner / digest / part).read_bytes() for part in ("session.cast", "session.gif")] == [
            f"{payload} cast".encode(), f"{payload} gif".encode()]
    assert sorted(path.name for path in unowned.iterdir()) == ["session.cast", "session.gif"]


# One MP4 file published by two wrappers, record-terminal-live-demo.sh and then record-cast.sh, has
# one owner directory, so the second publication prunes the first's capture and holds the same lock
# as the first would: the captures root holds that MP4's one capture and nothing else new
# (c-rfb-wrappers-key-captures-apart-1018).
# am[verifies a-rfb-owner-key-path-only-1018@2c72ba]
def test_one_mp4_published_by_two_wrappers_has_one_owner_directory(tmp_path):
    env = _tree(tmp_path)
    video = tmp_path / "hackathon" / "video"
    shared = tmp_path / "elsewhere" / "demo.mp4"
    before = set(path.name for path in (video / CAPTURES).iterdir())
    first = _record(tmp_path, "record-terminal-live-demo.sh", env, str(shared))
    recorder = video / "scripts" / "recorders" / "live-terminal-full-demo.sh"
    second = _record(tmp_path, "record-cast.sh", env, str(recorder), str(shared))
    owners = set(path.name for path in (video / CAPTURES).iterdir()) - before

    assert (first.returncode, second.returncode) == (0, 0), first.stdout + first.stderr + second.stdout + second.stderr
    assert owners == {Path(_owner(video, CAPTURES, shared)).name}
    assert sorted(path.name for path in (video / _owner(video, CAPTURES, shared)).iterdir()) == [
        hashlib.sha256(shared.read_bytes()).hexdigest()]

"""Purpose: test provisioning of the semantic reader's cross-encoder: SHA-256 verification and its
ready stamp, the stamp and size checks a run relies on, a second provisioning that downloads
nothing, hard and clean failures for downloads and integrity, the CLI's exit codes, and that the
pinned reranker is ready in the provisioned model cache."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import huggingface_hub.constants
import pytest

from goal_chainer import semantic_models as sm
from goal_chainer.errors import DependencyUnavailableError


# am[verifies a-jev-provision-user-cache-1016]
def _pin(contents: dict[str, bytes], repo_id: str = "goalchainer-test/absent-repository") -> sm.ModelPin:
    return sm.ModelPin(
        repo_id=repo_id,
        revision="0" * 40,
        license="test",
        files=tuple(
            sm.PinnedFile(path, len(data), hashlib.sha256(data).hexdigest())
            for path, data in sorted(contents.items())
        ),
    )


# am[verifies a-jev-provision-user-cache-1016]
def _materialise(pin: sm.ModelPin, cache, contents: dict[str, bytes]):
    directory = sm.snapshot_dir(pin, cache)
    for path, data in contents.items():
        (directory / path).parent.mkdir(parents=True, exist_ok=True)
        (directory / path).write_bytes(data)
    return directory


CONTENTS = {"config.json": b'{"a": 1}', "sub/weights.bin": b"\x00\x01\x02weights"}


# am[verifies a-jev-provision-user-cache-1016]
def test_verify_stamps_a_matching_snapshot_and_a_changed_byte_unstamps_it(tmp_path) -> None:
    pin = _pin(CONTENTS)
    directory = _materialise(pin, tmp_path, CONTENTS)

    assert sm.verify(pin, tmp_path) == directory
    assert sm.ready_model_dir(pin, tmp_path) == directory

    weights = directory / "sub" / "weights.bin"
    weights.write_bytes(b"\x00\x01\x03weights")
    with pytest.raises(sm.ModelIntegrityError) as raised:
        sm.verify(pin, tmp_path)
    assert raised.value.details["file"] == "sub/weights.bin"
    assert not (directory / sm.READY_STAMP).exists()
    with pytest.raises(DependencyUnavailableError, match="not provisioned"):
        sm.ready_model_dir(pin, tmp_path)


# am[verifies a-jev-provision-user-cache-1016]
def test_a_run_refuses_a_stamp_for_another_pin_or_a_resized_file(tmp_path) -> None:
    pin = _pin(CONTENTS)
    directory = _materialise(pin, tmp_path, CONTENTS)
    sm.verify(pin, tmp_path)

    other = sm.ModelPin(pin.repo_id, pin.revision, "other-licence", pin.files)
    with pytest.raises(DependencyUnavailableError, match="different pin"):
        sm.ready_model_dir(other, tmp_path)

    (directory / "config.json").write_bytes(b'{"a": 10}')
    with pytest.raises(DependencyUnavailableError, match="changed size"):
        sm.ready_model_dir(pin, tmp_path)


# A pin naming a repository that does not exist proves no download happens: one would fail.
# am[verifies a-jev-provision-user-cache-1016]
def test_provisioning_a_ready_cache_downloads_nothing(tmp_path) -> None:
    pin = _pin(CONTENTS)
    directory = _materialise(pin, tmp_path, CONTENTS)

    assert sm.provision(pin, tmp_path) == directory
    assert sm.provision(pin, tmp_path) == directory
    assert (directory / sm.READY_STAMP).exists()


# A ready cache stays ready while it is provisioned or verified again: a reader in the middle of
# every hash still finds it, so one gate's setup step never fails another gate's tests on a shared
# cache. A ready cache is hashed once by provisioning, file by file, and once by verify.
# am[verifies a-jev-ready-while-verified-1016]
def test_a_ready_cache_stays_ready_while_it_is_hashed_again(tmp_path, monkeypatch) -> None:
    pin = _pin(CONTENTS)
    directory = _materialise(pin, tmp_path, CONTENTS)
    sm.verify(pin, tmp_path)
    readable = []
    hashing = sm._verify_files

    def reading_meanwhile(pinned, where):
        readable.append(sm.ready_model_dir(pin, tmp_path))
        return hashing(pinned, where)

    monkeypatch.setattr(sm, "_verify_files", reading_meanwhile)
    assert sm.provision(pin, tmp_path) == directory
    assert sm.verify(pin, tmp_path) == directory

    assert readable == [directory] * (len(pin.files) + 1)


# am[verifies a-jev-provision-user-cache-1016]
def test_a_failed_download_raises_and_stamps_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(huggingface_hub.constants, "HF_HUB_OFFLINE", True)
    pin = _pin(CONTENTS)
    directory = _materialise(pin, tmp_path, {"config.json": CONTENTS["config.json"]})

    with pytest.raises(sm.ModelDownloadError) as raised:
        sm.provision(pin, tmp_path)

    assert raised.value.details["file"] == "sub/weights.bin"
    assert not (directory / sm.READY_STAMP).exists()


# am[verifies a-jev-provision-user-cache-1016]
def test_the_command_exit_codes_name_each_failure(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv(sm.MODEL_CACHE_ENV, str(tmp_path / "empty"))
    assert sm.main(["verify"]) == 3
    monkeypatch.setattr(huggingface_hub.constants, "HF_HUB_OFFLINE", True)
    assert sm.main(["provision"]) == 1
    assert sm.main(["unpin"]) == 2
    assert "semantic-models:" in capsys.readouterr().err


# am[verifies a-jev-provision-user-cache-1016]
def test_the_pinned_reranker_is_ready_in_the_provisioned_cache() -> None:
    directory = sm.ready_model_dir()

    assert directory.name == sm.RERANKER.revision
    assert (directory / "model.safetensors").stat().st_size == 1191588280
    assert sm.RERANKER.license == "apache-2.0"


# am[verifies a-jev-provision-user-cache-1016]
# am[related i-integrate-installed-model-cache-1016]
def test_the_model_cache_is_the_users_cache_wherever_the_package_lives(tmp_path) -> None:
    assert sm.model_cache({"XDG_CACHE_HOME": str(tmp_path)}) == tmp_path / "goalchainer" / "models"
    assert sm.model_cache({}) == Path.home() / ".cache" / "goalchainer" / "models"
    assert sm.model_cache({sm.MODEL_CACHE_ENV: str(tmp_path / "pinned"), "XDG_CACHE_HOME": "/x"}) == (
        tmp_path / "pinned")
    assert Path(sm.__file__).resolve().parent not in sm.model_cache({}).parents


# With no XDG_CACHE_HOME and no home directory to find, as for a uid with no passwd entry, the cache
# root is the dependency error naming what to set, so no caller meets Path.home's bare RuntimeError;
# a cache found from its own variable needs neither.
# am[verifies a-dr-cache-home-typed-1018@63015f]
def test_with_no_home_the_cache_root_is_a_dependency_error_naming_xdg_cache_home(tmp_path, monkeypatch) -> None:
    def no_home(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", classmethod(no_home))

    with pytest.raises(DependencyUnavailableError, match="set XDG_CACHE_HOME") as raised:
        sm.cache_home({})
    assert raised.value.code == "dependency_unavailable"
    with pytest.raises(DependencyUnavailableError, match="set XDG_CACHE_HOME"):
        sm.model_cache({})
    assert sm.cache_home({"XDG_CACHE_HOME": str(tmp_path)}) == tmp_path / "goalchainer"
    assert sm.model_cache({sm.MODEL_CACHE_ENV: str(tmp_path / "pinned")}) == tmp_path / "pinned"


# A fresh interpreter outside the repository, with no override and the Hub offline, resolves the
# verified model through the user cache: what an installed wheel does, and nothing downloads.
# am[verifies a-jev-provision-user-cache-1016]
# am[related i-integrate-installed-model-cache-1016]
def test_an_installed_process_finds_the_verified_model_offline_in_the_user_cache(tmp_path) -> None:
    provisioned = sm.model_cache()
    sm.ready_model_dir()
    user_cache = tmp_path / "xdg"
    (user_cache / "goalchainer").mkdir(parents=True)
    (user_cache / "goalchainer" / "models").symlink_to(provisioned, target_is_directory=True)
    env = {k: v for k, v in os.environ.items() if k not in {sm.MODEL_CACHE_ENV, "PYTHONPATH"}}
    env.update({"XDG_CACHE_HOME": str(user_cache), "HF_HUB_OFFLINE": "1"})
    script = (
        "from goal_chainer.semantic_models import model_cache, ready_model_dir\n"
        "print(model_cache())\nprint(ready_model_dir())\n"
    )

    result = subprocess.run([sys.executable, "-I", "-c", script], cwd=tmp_path, env=env,
                            capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    cache_line, model_line = result.stdout.splitlines()
    assert Path(cache_line) == user_cache / "goalchainer" / "models"
    assert Path(model_line).name == sm.RERANKER.revision


# am[verifies a-jev-provision-user-cache-1016]
def test_a_missing_model_names_the_installed_provision_command(tmp_path) -> None:
    with pytest.raises(DependencyUnavailableError) as raised:
        sm.ready_model_dir(cache=tmp_path)
    assert "python -m goal_chainer.semantic_models provision" in raised.value.details["remedy"]


# The manifest generator records a file only when its bytes match the Hub's tree entry: the LFS
# SHA-256 for a large file, the git blob id otherwise.
# am[verifies a-jev-manifest-regeneration-1016]
def test_a_pinned_file_is_established_only_from_bytes_matching_the_hubs_tree(tmp_path) -> None:
    data = b"\x00weights\x01"
    path = tmp_path / "weights.bin"
    path.write_bytes(data)
    sha256 = hashlib.sha256(data).hexdigest()
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    expected = sm.PinnedFile("weights.bin", len(data), sha256)

    assert sm.pinned_file("weights.bin", path, "not-consulted", sha256) == expected
    assert sm.pinned_file("weights.bin", path, blob, None) == expected
    with pytest.raises(sm.ModelIntegrityError):
        sm.pinned_file("weights.bin", path, blob, "0" * 64)
    with pytest.raises(sm.ModelIntegrityError):
        sm.pinned_file("weights.bin", path, "0" * 40, None)

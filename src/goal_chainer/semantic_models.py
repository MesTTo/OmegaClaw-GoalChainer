"""Purpose: provision and locate the pinned local cross-encoder: download every file of one Hugging
Face revision anonymously into a model cache, verify each file's SHA-256, and answer the verified
snapshot directory or a hard error naming what is missing.

Run as `python -m goal_chainer.semantic_models provision` (what scripts/setup-semantic.sh calls),
`... verify`, or `... manifest`, which rebuilds the pinned file list from the Hub's tree at the
pinned revision and compares it with RERANKER. Exit codes: 0 ready or matching, 1 a download
failed, 2 usage, 3 a file failed verification or the rebuilt list differs from the pin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import DependencyUnavailableError

MODEL_CACHE_ENV = "GOALCHAINER_MODEL_CACHE"
READY_STAMP = "goalchainer-ready.json"


# am[implements a-jev-provision-user-cache-1016]
@dataclass(frozen=True, slots=True)
class PinnedFile:
    """One file of a pinned model revision with the size and SHA-256 it must have."""

    path: str
    size: int
    sha256: str


# am[implements a-jev-provision-user-cache-1016]
@dataclass(frozen=True, slots=True)
class ModelPin:
    """A model repository at one commit, with every file the reader loads from it."""

    repo_id: str
    revision: str
    license: str
    files: tuple[PinnedFile, ...]

    @property
    def identity(self) -> str:
        return f"{self.repo_id}@{self.revision}"


# Qwen3-Reranker-0.6B, the cross-encoder the operator's agentmemory chose over GTE ModernBERT by a
# labelled comparison. Provisioning checks every file against the size and SHA-256 recorded here.
# The list is generated: `python -m goal_chainer.semantic_models manifest` rebuilds it from the
# Hub's own tree at the pinned revision (derive_pin), checking LFS files against the tree's LFS
# SHA-256 and the rest against their git blob ids, and exits 3 if it differs from what is here.
# README.md and .gitattributes are left out because loading reads neither (DOCUMENTATION).
# am[implements a-jev-provision-user-cache-1016]
# am[rests-on c-operator-reranker-prior-1016]
RERANKER = ModelPin(
    repo_id="Qwen/Qwen3-Reranker-0.6B",
    revision="e61197ed45024b0ed8a2d74b80b4d909f1255473",
    license="apache-2.0",
    files=(
        PinnedFile("1_LogitScore/config.json", 57,
                   "73e3156450564d8a98b7e47bcf5aace0f29600828b51937da545571e84db3ff3"),
        PinnedFile("chat_template.jinja", 741,
                   "6f682162495ec5b39fd9005c01b6aa2a74669379fe967039f1e2cbbe8752369d"),
        PinnedFile("config.json", 727,
                   "d479c427a9ca5295218063d4f9aca4f297ab4ac27487cca7af42c84643d51ef0"),
        PinnedFile("config_sentence_transformers.json", 325,
                   "6a153d6696f78fd588c1c728967f0b773ea869d3c6028f151ce71ebe49140762"),
        PinnedFile("generation_config.json", 214,
                   "81051cd3f6e77013827148d0b8a6ead93f8ac390d5ab805f849199f0af6a08db"),
        PinnedFile("merges.txt", 1671853,
                   "8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5"),
        PinnedFile("model.safetensors", 1191588280,
                   "27cd75a405b9c1b46b59abfd88aaa209e6fed2a1972cde9b70e7659537c5e65b"),
        PinnedFile("modules.json", 280,
                   "6f13b6b4a89e577b591b2077bca40c67c26541a6740a8809267cb474f90806a9"),
        PinnedFile("sentence_bert_config.json", 362,
                   "3234ebd224d492cbe8d55d5ec80a3f408451c4db3005bafb64fe1c51c763e01e"),
        PinnedFile("tokenizer.json", 11422654,
                   "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4"),
        PinnedFile("tokenizer_config.json", 9706,
                   "253153d0738ceb4c668d2eff957714dd2bea0b56de772a9fdccd96cbf517e6a0"),
        PinnedFile("vocab.json", 2776833,
                   "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910"),
    ),
)


# am[implements a-jev-provision-user-cache-1016]
class ModelIntegrityError(DependencyUnavailableError):
    """A file in the model cache does not have the size or SHA-256 its pin records."""

    code = "model_integrity"


# am[implements a-jev-provision-user-cache-1016]
class ModelDownloadError(DependencyUnavailableError):
    """A pinned file could not be downloaded from the Hub."""

    code = "model_download"


# GoalChainer's per-user cache directory under the XDG Base Directory rule ($XDG_CACHE_HOME, else
# ~/.cache), the rule huggingface_hub applies to its own cache. It depends on the user, never on
# where the package is installed, so a wheel and a checkout resolve the same place. A process with
# neither, as a uid with no passwd entry and no HOME is, has no such place: asking for it is the
# dependency error naming what to set, never Path.home's untyped RuntimeError. A cache with its own
# variable is found from that before this is asked.
# am[addresses i-integrate-installed-model-cache-1016] am[implements a-dr-cache-home-typed-1018@63015f]
# am[addresses i-dr-no-home-untyped-1018@645d5b]
def cache_home(env: Mapping[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    base = values.get("XDG_CACHE_HOME", "").strip()
    if base:
        return Path(base) / "goalchainer"
    try:
        home = Path.home()
    except RuntimeError as error:
        raise DependencyUnavailableError(
            "GoalChainer's caches have no place: XDG_CACHE_HOME is unset and no home directory can be "
            "found, so set XDG_CACHE_HOME.",
            details={"error": str(error)},
        ) from error
    return home / ".cache" / "goalchainer"


# am[implements a-jev-provision-user-cache-1016]
# am[addresses i-integrate-installed-model-cache-1016]
def model_cache(env: Mapping[str, str] | None = None) -> Path:
    """The model cache: GOALCHAINER_MODEL_CACHE when set, else cache_home()/models."""

    values = os.environ if env is None else env
    configured = values.get(MODEL_CACHE_ENV, "").strip()
    return Path(configured).expanduser().absolute() if configured else cache_home(values) / "models"


# am[implements a-jev-provision-user-cache-1016]
def snapshot_dir(pin: ModelPin, cache: Path) -> Path:
    """Where huggingface_hub's cache layout puts the pinned revision's files."""

    organisation, name = pin.repo_id.split("/", 1)
    return cache / f"models--{organisation}--{name}" / "snapshots" / pin.revision


# am[implements a-jev-provision-user-cache-1016]
def _stamp(pin: ModelPin) -> dict[str, object]:
    return {
        "repo_id": pin.repo_id,
        "revision": pin.revision,
        "license": pin.license,
        "files": {file.path: [file.size, file.sha256] for file in pin.files},
    }


# Time: one read of every pinned file, about 1.2 GB for the reranker, at hashing speed.
# am[implements a-jev-provision-user-cache-1016]
def _verify_files(pin: ModelPin, directory: Path) -> None:
    for file in pin.files:
        path = directory / file.path
        if not path.is_file():
            raise ModelIntegrityError(
                "A pinned model file is missing from the model cache.",
                details={"model": pin.identity, "file": file.path, "path": str(path)},
            )
        size = path.stat().st_size
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                digest.update(block)
        if size != file.size or digest.hexdigest() != file.sha256:
            raise ModelIntegrityError(
                "A model file does not match its pinned size and SHA-256.",
                details={
                    "model": pin.identity,
                    "file": file.path,
                    "expected": {"size": file.size, "sha256": file.sha256},
                    "found": {"size": size, "sha256": digest.hexdigest()},
                },
            )


# am[implements a-jev-provision-user-cache-1016]
def _write_stamp(pin: ModelPin, directory: Path) -> None:
    fd, temporary = tempfile.mkstemp(dir=directory, prefix=f".{READY_STAMP}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(_stamp(pin), stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / READY_STAMP)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


# A stamp says the files were verified, so readers of a shared cache keep using it while it is
# hashed again; only a file that fails makes the snapshot unready, and then the stamp goes first.
# am[implements a-jev-provision-user-cache-1016]
# am[implements a-jev-ready-while-verified-1016]
def verify(pin: ModelPin = RERANKER, cache: Path | None = None) -> Path:
    """Hash every pinned file and stamp the snapshot ready; answer the snapshot directory. A file
    that fails removes the stamp and raises ModelIntegrityError."""

    directory = snapshot_dir(pin, model_cache() if cache is None else cache)
    try:
        _verify_files(pin, directory)
    except ModelIntegrityError:
        (directory / READY_STAMP).unlink(missing_ok=True)
        raise
    _write_stamp(pin, directory)
    return directory


# am[implements a-jev-provision-user-cache-1016]
# am[rests-on c-rt-hf-model-public-1016]
@contextmanager
def _anonymous_hub() -> Iterator[None]:
    """Hide every Hugging Face credential for the duration: the pinned model is public, and a
    stored token that has expired answers 401 for a public file (c-rt-hf-model-public-1016)."""

    hidden = {name: os.environ.pop(name) for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN") if name in os.environ}
    implicit = os.environ.get("HF_HUB_DISABLE_IMPLICIT_TOKEN")
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    try:
        yield
    finally:
        os.environ.update(hidden)
        if implicit is None:
            os.environ.pop("HF_HUB_DISABLE_IMPLICIT_TOKEN", None)
        else:
            os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = implicit


# am[implements a-jev-provision-user-cache-1016]
def _remove_cached_file(path: Path) -> None:
    """Remove a snapshot entry and the blob it links to, so a bad download is fetched again."""

    if path.is_symlink():
        target = path.resolve()
        path.unlink()
        target.unlink(missing_ok=True)
    else:
        path.unlink(missing_ok=True)


# Time: one SHA-256 pass over every pinned file, plus a download and a second pass for each file
# that failed the first; a ready cache is read once and never unstamped.
# am[implements a-jev-provision-user-cache-1016]
# am[implements a-jev-ready-while-verified-1016]
# am[rests-on c-rt-hf-model-public-1016]
def provision(pin: ModelPin = RERANKER, cache: Path | None = None) -> Path:
    """Make the pinned revision ready in the cache, downloading only files that fail verification.

    A second run on a ready cache hashes and re-stamps without touching the network, and the cache
    stays ready for its readers throughout. A missing or failing file unstamps the snapshot before
    it is fetched again; one that still fails after its download is removed and raises
    ModelIntegrityError, so a partial cache is never stamped ready.
    """

    root = model_cache() if cache is None else cache
    directory = snapshot_dir(pin, root)
    stale: list[PinnedFile] = []
    for file in pin.files:
        try:
            _verify_files(ModelPin(pin.repo_id, pin.revision, pin.license, (file,)), directory)
        except ModelIntegrityError:
            stale.append(file)
    if stale:
        (directory / READY_STAMP).unlink(missing_ok=True)
        from huggingface_hub import hf_hub_download  # noqa: PLC0415 (the semantic extra)
        from huggingface_hub.errors import HfHubHTTPError  # noqa: PLC0415

        with _anonymous_hub():
            for file in stale:
                if (directory / file.path).exists() or (directory / file.path).is_symlink():
                    _remove_cached_file(directory / file.path)
                try:
                    hf_hub_download(
                        pin.repo_id,
                        file.path,
                        revision=pin.revision,
                        cache_dir=root,
                        token=False,
                    )
                except (HfHubHTTPError, OSError) as error:
                    raise ModelDownloadError(
                        "A pinned model file could not be downloaded.",
                        details={
                            "model": pin.identity,
                            "file": file.path,
                            "error": f"{type(error).__name__}: {error}",
                        },
                    ) from error
        for file in stale:
            try:
                _verify_files(ModelPin(pin.repo_id, pin.revision, pin.license, (file,)), directory)
            except ModelIntegrityError:
                _remove_cached_file(directory / file.path)
                raise
    _write_stamp(pin, directory)
    return directory


# A run trusts the stamp and the sizes, not the bytes: that rests on only provisioning writing
# under the model cache, so an edit that keeps a file's size shows only at the next verify.
# am[implements a-jev-provision-user-cache-1016]
# am[rests-on c-model-cache-fast-check-assumed-1016]
def ready_model_dir(pin: ModelPin = RERANKER, cache: Path | None = None) -> Path:
    """The verified snapshot directory, checked against its ready stamp and file sizes.

    Hashing 1.2 GB on every process start would cost seconds, so a run reads the stamp that
    provisioning wrote after hashing and checks each file's size; `verify` re-hashes on demand.
    """

    directory = snapshot_dir(pin, model_cache() if cache is None else cache)
    remedy = (
        "Run `python -m goal_chainer.semantic_models provision` with the semantic extra installed; "
        "in a checkout, ./scripts/setup-semantic.sh installs the extra and runs it."
    )
    try:
        stamp = json.loads((directory / READY_STAMP).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise DependencyUnavailableError(
            "The semantic reader's cross-encoder is not provisioned.",
            details={"model": pin.identity, "path": str(directory), "remedy": remedy,
                     "error": f"{type(error).__name__}: {error}"},
        ) from error
    if stamp != _stamp(pin):
        raise DependencyUnavailableError(
            "The cross-encoder's ready stamp names a different pin than this checkout.",
            details={"model": pin.identity, "path": str(directory), "remedy": remedy},
        )
    for file in pin.files:
        path = directory / file.path
        if not path.is_file() or path.stat().st_size != file.size:
            raise DependencyUnavailableError(
                "A stamped cross-encoder file is missing or changed size.",
                details={"model": pin.identity, "file": file.path, "remedy": remedy},
            )
    return directory


# Files of the repository that loading never reads, left out of a pin.
DOCUMENTATION = frozenset({"README.md", ".gitattributes"})


# A pinned file established from the Hub's own tree entry: the downloaded bytes must match the
# entry's LFS SHA-256 when it has one, else its git blob id, before their SHA-256 is recorded.
# am[implements a-jev-manifest-regeneration-1016]
def pinned_file(path: str, data_file: Path, blob_id: str, lfs_sha256: str | None) -> PinnedFile:
    data = data_file.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    matches = sha256 == lfs_sha256 if lfs_sha256 else blob == blob_id
    if not matches:
        raise ModelIntegrityError(
            "A downloaded file does not match the Hub's tree at its revision.",
            details={"file": path, "sha256": sha256, "lfs_sha256": lfs_sha256,
                     "git_blob": blob, "tree_blob": blob_id},
        )
    return PinnedFile(path, len(data), sha256)


# The generator of RERANKER.files: every file of the repository at the revision except the
# documentation, each downloaded anonymously into the cache and established by pinned_file.
# am[implements a-jev-manifest-regeneration-1016]
def derive_pin(repo_id: str, revision: str, license: str, cache: Path) -> ModelPin:
    from huggingface_hub import HfApi, hf_hub_download  # noqa: PLC0415 (the semantic extra)
    from huggingface_hub.errors import HfHubHTTPError  # noqa: PLC0415

    with _anonymous_hub():
        try:
            entries: list[Any] = [
                entry
                for entry in HfApi().list_repo_tree(repo_id, revision=revision, recursive=True,
                                                    expand=True, token=False)
                if hasattr(entry, "blob_id") and entry.path not in DOCUMENTATION
            ]
            files = tuple(
                pinned_file(
                    entry.path,
                    Path(hf_hub_download(repo_id, entry.path, revision=revision, cache_dir=cache,
                                         token=False)),
                    entry.blob_id,
                    entry.lfs.sha256 if entry.lfs else None,
                )
                for entry in sorted(entries, key=lambda entry: entry.path)
            )
        except (HfHubHTTPError, OSError) as error:
            raise ModelDownloadError(
                "The Hub's tree or a file of it could not be fetched.",
                details={"model": f"{repo_id}@{revision}", "error": f"{type(error).__name__}: {error}"},
            ) from error
    return ModelPin(repo_id, revision, license, files)


# am[implements a-jev-provision-user-cache-1016]
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m goal_chainer.semantic_models")
    parser.add_argument("command", choices=("provision", "verify", "manifest"))
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_:
        return 2 if exit_.code else 0
    try:
        if args.command == "manifest":
            derived = derive_pin(RERANKER.repo_id, RERANKER.revision, RERANKER.license, model_cache())
            for file in derived.files:
                print(f'        PinnedFile("{file.path}", {file.size}, "{file.sha256}"),')
            if derived.files != RERANKER.files:
                print("semantic-models: the Hub's tree differs from RERANKER.files", file=sys.stderr)
                return 3
            print(f"semantic-models: RERANKER.files match the Hub's tree at {RERANKER.identity}")
            return 0
        directory = provision() if args.command == "provision" else verify()
    except ModelDownloadError as error:
        print(f"semantic-models: {error.message} {json.dumps(dict(error.details))}", file=sys.stderr)
        return 1
    except ModelIntegrityError as error:
        print(f"semantic-models: {error.message} {json.dumps(dict(error.details))}", file=sys.stderr)
        return 3
    print(f"semantic-models: {RERANKER.identity} ready at {directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Purpose: persist immutable semantic model artifacts and resolve exact serving identities."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any, Iterator, Mapping
import uuid

logger = logging.getLogger(__name__)
MANIFEST = "goalchainer-artifact.json"

# Artifact bytes and pointer transitions are shared by online serving and offline training.
# Admission policy and model computation belong to the sleep command.
# am[implements a-integrate-semantic-artifact-boundary-1018@0c41d7]

# am[implements a-sleep-reviewed-store-1016@b92a57]
class SleepError(ValueError):
    """Invalid review, incomplete artifact, stale evaluation or refused admission."""


# am[implements a-sleep-artifacts-1016@d2fca8]
def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


# am[implements a-sleep-artifacts-1016@d2fca8]
def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# am[implements a-sleep-artifacts-1016@d2fca8]
def _sha(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise SleepError("Expected a lowercase SHA-256 identity")
    return value


# am[implements a-sleep-artifacts-1016@d2fca8]
def _regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise SleepError(f"Missing regular file or forbidden symlink: {path}")


# am[implements a-sleep-artifacts-1016@d2fca8]
def _directory(path: Path) -> None:
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise SleepError(f"Symlink directory is forbidden: {ancestor}")
    if not path.is_dir():
        raise SleepError(f"Missing directory: {path}")


# am[implements a-sleep-artifacts-1016@d2fca8]
def _relative(value: str) -> PurePosixPath:
    part = PurePosixPath(value)
    if not part.parts or part.is_absolute() or ".." in part.parts or str(part) != value or "\\" in value or "\0" in value:
        raise SleepError(f"Unsafe artifact path: {value!r}")
    return part


# am[implements a-sleep-artifacts-1016@d2fca8]
def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SleepError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


# am[implements a-sleep-artifacts-1016@d2fca8]
def _decode(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_json_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(SleepError(f"Nonfinite JSON: {value}")))


# am[implements a-sleep-artifacts-1016@d2fca8]
def _json(path: Path) -> Any:
    _regular(path)
    try:
        return _decode(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        raise SleepError(f"Invalid JSON in {path}: {error}") from error


# am[implements a-sleep-artifacts-1016@d2fca8]
def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


# am[implements a-sleep-reviewed-store-1016@b92a57]
def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _directory(path.parent)
    if path.exists() or path.is_symlink():
        _regular(path)
    fd, temporary = tempfile.mkstemp(prefix=".sleep-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


# am[implements a-sleep-artifacts-1016@d2fca8]
@contextmanager
def _locked(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    _directory(root)
    path = root / ".lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


# am[implements a-sleep-artifacts-1016@d2fca8]
@dataclass(frozen=True)
class ActiveReference:
    artifact: str | None
    generation: str

    # am[implements a-sleep-artifacts-1016@d2fca8]
    @classmethod
    def parse(cls, row: Any) -> ActiveReference:
        if not isinstance(row, dict) or set(row) != {"artifact", "generation"}:
            raise SleepError("Invalid ACTIVE pointer")
        if row["artifact"] is not None:
            _sha(row["artifact"])
        try:
            if str(uuid.UUID(row["generation"])) != row["generation"]:
                raise ValueError("noncanonical generation")
        except (ValueError, TypeError, AttributeError) as error:
            raise SleepError("Invalid ACTIVE generation") from error
        return cls(**row)


# am[implements a-sleep-artifacts-1016@d2fca8]
@dataclass(frozen=True)
class Artifact:
    model_dir: Path
    identity: str
    manifest: dict[str, Any]


# am[implements a-sleep-artifacts-1016@d2fca8]
@dataclass(frozen=True)
class ServingReference:
    identity: str
    model_dir: Path | None
    pointer: ActiveReference | None
    manifest: Mapping[str, Any] | None = None


# am[implements a-sleep-contract-1016@7bccc5]
def artifact_root() -> Path:
    from .semantic_models import model_cache

    return model_cache() / "goalchainer-reranker"


# am[implements a-sleep-artifacts-1016@d2fca8]
def capture_active(root: Path) -> ActiveReference | None:
    if not root.exists() and not root.is_symlink():
        return None
    _directory(root)
    path = root / "ACTIVE"
    if not path.exists() and not path.is_symlink():
        return None
    return ActiveReference.parse(_json(path))


# Time: b bytes read with full_hash, else f file stats; b = artifact bytes, f = file count.
# am[implements a-sleep-artifacts-1016@d2fca8]
def _inventory(directory: Path, *, full_hash: bool = True) -> dict[str, list[Any]]:
    _directory(directory)
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise SleepError(f"Symlink in artifact: {path}")
        if path.is_dir():
            continue
        _regular(path)
        relative = path.relative_to(directory).as_posix()
        if relative == MANIFEST:
            continue
        hasher = hashlib.sha256()
        if full_hash:
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1 << 20), b""):
                    hasher.update(block)
        result[relative] = [path.stat().st_size, hasher.hexdigest() if full_hash else None]
    return result


# am[implements a-sleep-artifacts-1016@d2fca8]
def validate_artifact(root: Path, artifact_id: str, *, full_hash: bool = True) -> Artifact:
    identity = _sha(artifact_id)
    _directory(root)
    directory = root / identity
    _directory(directory)
    manifest = _json(directory / MANIFEST)
    if not isinstance(manifest, dict) or manifest.get("schema") != 1 or manifest.get("digest") != identity:
        raise SleepError("Invalid artifact manifest schema or identity")
    payload = {key: value for key, value in manifest.items() if key != "digest"}
    if digest(canonical(payload)) != identity:
        raise SleepError("Artifact manifest digest changed")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise SleepError("Artifact has no file inventory")
    for path, record in files.items():
        _relative(path)
        if not isinstance(record, list) or len(record) != 2 or type(record[0]) is not int or record[0] < 0:
            raise SleepError("Invalid file inventory record")
        _sha(record[1])
    actual = _inventory(directory, full_hash=full_hash)
    if set(actual) != set(files) or any(actual[path][0] != record[0] or (full_hash and actual[path][1] != record[1]) for path, record in files.items()):
        raise SleepError("Artifact files are missing, added, resized or changed")
    _directory(directory / "model")
    if not {"model/config.json", "model/tokenizer_config.json"} <= files.keys() or not any(path.startswith("model/") and path.endswith((".safetensors", ".bin")) for path in files):
        raise SleepError("Incomplete CrossEncoder artifact: config, tokenizer config and weights required")
    return Artifact(directory / "model", identity, manifest)


# am[implements a-sleep-artifacts-1016@d2fca8]
def resolve_active(root: Path, base_identity: str, *, full_hash: bool = False) -> ServingReference:
    pointer = capture_active(root)
    if pointer is None or pointer.artifact is None:
        return ServingReference(base_identity, None, pointer)
    artifact = validate_artifact(root, pointer.artifact, full_hash=full_hash)
    if artifact.manifest.get("base", {}).get("identity") != base_identity:
        raise SleepError("ACTIVE artifact belongs to a different configured base")
    return ServingReference(artifact.identity, artifact.model_dir, pointer, artifact.manifest)


# Time: b bytes copied and hashed; b = model plus evidence bytes. No serving file is overwritten.
# am[implements a-sleep-artifacts-1016@d2fca8]
def publish_artifact(root: Path, model_dir: Path, metadata: dict[str, Any],
                     evidence: dict[str, bytes]) -> Artifact:
    if {"schema", "files", "digest"} & metadata.keys():
        raise SleepError("Metadata may not replace manifest integrity fields")
    source = _inventory(model_dir, full_hash=False)
    if not {"config.json", "tokenizer_config.json"} <= source.keys() or not any(path.endswith((".safetensors", ".bin")) for path in source):
        raise SleepError("Incomplete CrossEncoder source: config, tokenizer config and weights required")
    root.mkdir(parents=True, exist_ok=True)
    _directory(root)
    temporary = Path(tempfile.mkdtemp(prefix=".building-", dir=root))
    try:
        shutil.copytree(model_dir, temporary / "model")
        for name, data in evidence.items():
            path = temporary / "evidence" / _relative(name)
            _atomic(path, data)
        payload = {"schema": 1, **metadata, "files": _inventory(temporary)}
        identity = digest(canonical(payload))
        _atomic(temporary / MANIFEST, canonical({**payload, "digest": identity}))
        # Sync model bytes too: a directory rename alone does not persist file contents.
        for path in temporary.rglob("*"):
            if path.is_file():
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
        for path in sorted((p for p in temporary.rglob("*") if p.is_dir()), reverse=True):
            _sync_directory(path)
        _sync_directory(temporary)
        with _locked(root):
            target = root / identity
            if target.exists():
                return validate_artifact(root, identity)
            os.rename(temporary, target)
            _sync_directory(root)
        return validate_artifact(root, identity)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


# am[implements a-sleep-artifacts-1016@d2fca8]
def _pointer(reference: ActiveReference | None) -> dict[str, Any] | None:
    return None if reference is None else asdict(reference)


# am[implements a-sleep-artifacts-1016@d2fca8]
def _switch(root: Path, target: str | None) -> ActiveReference:
    reference = ActiveReference(target, str(uuid.uuid4()))
    _atomic(root / "ACTIVE", canonical(asdict(reference)))
    logger.debug("ACTIVE transition target=%s generation=%s", target, reference.generation)
    return reference

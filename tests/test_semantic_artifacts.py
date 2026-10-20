"""Purpose: verify the shared semantic artifact boundary and its exact stored bytes."""

import json
import subprocess
import sys

import pytest

from goal_chainer import semantic_artifacts as artifacts
from goal_chainer import semantic_sleep as sleep
from goal_chainer.semantic_models import RERANKER
from semantic_sleep_support import admissible_metadata, base_pin, model_files


# am[verifies a-integrate-semantic-artifact-boundary-1018@0c41d7]
def test_serving_does_not_import_the_sleep_command(tmp_path):
    root = tmp_path / "registry"
    artifact = artifacts.publish_artifact(root, model_files(tmp_path / "model"),
                                         {"base": {"identity": RERANKER.identity},
                                          "instruction": "Rank."}, {})
    (root / "ACTIVE").write_bytes(artifacts.canonical(
        {"artifact": artifact.identity, "generation": "00000000-0000-0000-0000-000000000001"}))
    subprocess.run([
        sys.executable, "-c",
        "import sys; from pathlib import Path; "
        "from goal_chainer.semantic_reader import served_ranker; "
        "from goal_chainer.domains.readings import ReadingDeclaration; "
        "declaration = ReadingDeclaration('boundary', 'model', 'en', 'Read.', (), (), (), 'Rank.', Path('boundary.metta')); "
        "assert served_ranker(declaration, Path(sys.argv[1])).identity == sys.argv[2]; "
        "assert 'goal_chainer.semantic_sleep' not in sys.modules",
        str(root), artifact.identity,
    ], check=True)


# am[verifies a-integrate-semantic-artifact-boundary-1018@0c41d7]
def test_sleep_uses_the_same_artifact_types_and_operations():
    for name in ("ActiveReference", "Artifact", "ServingReference", "SleepError", "canonical",
                 "digest", "publish_artifact", "validate_artifact", "resolve_active"):
        assert getattr(sleep, name) is getattr(artifacts, name)


# am[verifies a-integrate-semantic-artifact-boundary-1018@0c41d7]
def test_publication_preserves_exact_canonical_manifest_and_evidence_bytes(tmp_path):
    model = model_files(tmp_path / "model")
    metadata = {"base": {"identity": "base@test"}, "instruction": "Rank café passages.",
                "parent": "base@test", "parent_ref": None}
    evidence = {"review.json": b'{"reviewer":"curator","label":1}\n'}
    artifact = artifacts.publish_artifact(tmp_path / "registry", model, metadata, evidence)
    inventory = {"model/" + path.name: [path.stat().st_size, artifacts.digest(path.read_bytes())]
                 for path in model.iterdir()}
    inventory["evidence/review.json"] = [len(evidence["review.json"]),
                                         artifacts.digest(evidence["review.json"])]
    payload = {"schema": 1, **metadata, "files": inventory}
    expected = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    assert artifact.identity == artifacts.digest(expected)
    manifest = json.dumps({**payload, "digest": artifact.identity}, sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    assert (artifact.model_dir.parent / artifacts.MANIFEST).read_bytes() == manifest
    assert (artifact.model_dir.parent / "evidence/review.json").read_bytes() == evidence["review.json"]


# am[verifies a-semantic-boundary-seal-1018@edc449]
def test_changed_artifact_implementation_requires_a_new_evaluation(tmp_path, monkeypatch):
    root = tmp_path / "registry"
    metadata, evidence = admissible_metadata()
    artifact = artifacts.publish_artifact(root, model_files(tmp_path / "model"), metadata, evidence)
    assert artifacts.validate_artifact(root, artifact.identity).identity == artifact.identity
    monkeypatch.setitem(sleep.EVALUATOR_SOURCES, "artifacts.py", evidence["artifacts.py"] + b"\n# changed\n")
    with pytest.raises(artifacts.SleepError, match="different evaluator implementation"):
        sleep.promote(root, artifact.identity, "base@test")
    assert artifacts.capture_active(root) is None


# am[verifies a-semantic-boundary-seal-1018@edc449] am[verifies a-integrate-semantic-artifact-boundary-1018@0c41d7]
def test_prior_evaluator_artifact_still_serves_and_rolls_back_without_rewriting_it(tmp_path):
    root = tmp_path / "registry"
    metadata, evidence = admissible_metadata()
    evidence.pop("artifacts.py")
    evidence["evaluation.py"] = b"prior evaluator source"
    model = model_files(tmp_path / "base")
    artifact = artifacts.publish_artifact(root, model, metadata, evidence)
    manifest_path = artifact.model_dir.parent / artifacts.MANIFEST
    original = manifest_path.read_bytes()
    pointer = artifacts.ActiveReference(artifact.identity, "00000000-0000-0000-0000-000000000001")
    (root / "ACTIVE").write_bytes(artifacts.canonical(
        {"artifact": pointer.artifact, "generation": pointer.generation}))
    assert artifacts.resolve_active(root, "base@test").identity == artifact.identity
    with pytest.raises(artifacts.SleepError, match="different evaluator implementation"):
        sleep.promote(root, artifact.identity, "base@test")
    assert sleep.rollback(root, pointer, "base@test", base_dir=model, base=base_pin()).artifact is None
    assert manifest_path.read_bytes() == original

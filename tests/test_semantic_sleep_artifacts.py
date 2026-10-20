"""Purpose: verify immutable reranker artifacts and atomic serving promotion and rollback."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
from threading import Barrier, Event

import pytest

from goal_chainer import semantic_sleep as sleep
from goal_chainer import semantic_artifacts as artifacts
from semantic_sleep_support import admissible_metadata, model_files


# am[verifies a-sleep-artifact-integrity-tests-1016@7cc8b5]
@pytest.fixture
def registry(tmp_path):
    root = tmp_path / "registry"
    model = model_files(tmp_path / "model")
    metadata, evidence = admissible_metadata()
    artifact = sleep.publish_artifact(root, model, metadata, evidence)
    return root, model, metadata, evidence, artifact


# am[verifies a-sleep-artifact-integrity-tests-1016@7cc8b5]
def test_publish_is_content_addressed_idempotent_and_does_not_activate(registry):
    root, model, metadata, evidence, artifact = registry
    assert sleep.capture_active(root) is None
    assert sleep.resolve_active(root, "base@test") == sleep.ServingReference("base@test", None, None)
    assert sleep.validate_artifact(root, artifact.identity) == artifact
    assert sleep.publish_artifact(root, model, metadata, evidence) == artifact
    manifest = json.loads((artifact.model_dir.parent / sleep.MANIFEST).read_text())
    assert manifest["files"]["model/model.safetensors"][1] == sleep.digest(b"synthetic-weights")
    assert not list(root.glob(".building-*"))


# am[verifies a-sleep-artifact-integrity-tests-1016@7cc8b5]
@pytest.mark.parametrize("identity", ["../outside", "/outside", "A" * 64, "0" * 63, "0" * 65])
def test_artifact_identity_cannot_name_a_path(registry, identity):
    with pytest.raises(sleep.SleepError):
        sleep.validate_artifact(registry[0], identity)


# am[verifies a-sleep-artifact-integrity-tests-1016@7cc8b5]
@pytest.mark.parametrize("name", ["../escape", "/escape", "./policy.metta", "a/../escape", "a\\escape", ""])
def test_evidence_paths_cannot_escape_or_alias_their_inventory(registry, name):
    root, model, metadata, _, _ = registry
    with pytest.raises(sleep.SleepError, match="Unsafe artifact path"):
        sleep.publish_artifact(root, model, metadata, {name: b"untrusted"})
    assert sleep.capture_active(root) is None
    assert not list(root.glob(".building-*"))


# am[verifies a-sleep-artifact-integrity-tests-1016@7cc8b5]
@pytest.mark.parametrize("field", ["schema", "files", "digest"])
def test_metadata_cannot_replace_integrity_fields(registry, field):
    root, model, metadata, evidence, _ = registry
    with pytest.raises(sleep.SleepError, match="integrity fields"):
        sleep.publish_artifact(root, model, {**metadata, field: "forged"}, evidence)


# am[verifies a-sleep-artifact-integrity-tests-1016@7cc8b5]
@pytest.mark.parametrize("target", ["model", "weight", "manifest", "artifact", "root"])
def test_symlinks_are_rejected_at_each_artifact_boundary(registry, tmp_path, target):
    root, model, metadata, evidence, artifact = registry
    if target == "model":
        link = tmp_path / "linked-model"
        link.symlink_to(model, target_is_directory=True)
        with pytest.raises(sleep.SleepError):
            sleep.publish_artifact(root, link, metadata, evidence)
        return
    path = {"weight": artifact.model_dir / "model.safetensors",
            "manifest": artifact.model_dir.parent / sleep.MANIFEST,
            "artifact": artifact.model_dir.parent, "root": root}[target]
    retained = tmp_path / "retained"
    path.rename(retained)
    path.symlink_to(retained, target_is_directory=retained.is_dir())
    with pytest.raises(sleep.SleepError):
        sleep.validate_artifact(root, artifact.identity)


# am[verifies a-sleep-artifact-integrity-tests-1016@7cc8b5]
@pytest.mark.parametrize("mutation", ["missing-weight", "missing-tokenizer", "missing-manifest", "extra-file", "same-size-weight", "metadata"])
def test_partial_or_changed_artifacts_are_rejected_before_activation(registry, mutation):
    root, _, _, _, artifact = registry
    directory = artifact.model_dir.parent
    weight = artifact.model_dir / "model.safetensors"
    if mutation == "missing-weight":
        weight.unlink()
    elif mutation == "missing-tokenizer":
        (artifact.model_dir / "tokenizer_config.json").unlink()
    elif mutation == "missing-manifest":
        (directory / sleep.MANIFEST).unlink()
    elif mutation == "extra-file":
        (directory / "unlisted.txt").write_text("unlisted", encoding="utf-8")
    elif mutation == "same-size-weight":
        weight.write_bytes(b"X" * weight.stat().st_size)
    else:
        manifest = json.loads((directory / sleep.MANIFEST).read_text())
        manifest["parent"] = "changed-baseline"
        (directory / sleep.MANIFEST).write_bytes(sleep.canonical(manifest))
    with pytest.raises(sleep.SleepError):
        sleep.validate_artifact(root, artifact.identity)
    with pytest.raises(sleep.SleepError):
        sleep.promote(root, artifact.identity, "base@test")
    assert sleep.capture_active(root) is None


# am[verifies a-sleep-artifact-integrity-tests-1016@7cc8b5]
@pytest.mark.parametrize("mutation", ["policy", "metrics", "baseline", "missing-policy", "evaluator", "missing-evaluator",
                                     "artifact-implementation", "missing-artifact-implementation"])
def test_integrity_alone_cannot_bypass_promotion_admission(registry, mutation):
    root, model, metadata, evidence, _ = registry
    if mutation == "policy":
        evidence["policy.metta"] += b"\n; changed admission policy\n"
    elif mutation == "metrics":
        metadata["test"]["weights_changed"] = False
        metadata["claimed_verdict"] = "admit"
    elif mutation == "baseline":
        metadata["base"]["identity"] = "another-base"
    elif mutation == "missing-policy":
        evidence = {"other.txt": b"no admission policy"}
    elif mutation == "evaluator":
        evidence["evaluation.py"] += b"\n# changed evaluator\n"
    elif mutation == "missing-evaluator":
        del evidence["evaluation.py"]
    elif mutation == "artifact-implementation":
        evidence["artifacts.py"] += b"\n# changed artifact decoder\n"
    else:
        del evidence["artifacts.py"]
    artifact = sleep.publish_artifact(root, model, metadata, evidence)
    with pytest.raises(sleep.SleepError):
        sleep.promote(root, artifact.identity, "base@test")
    assert sleep.capture_active(root) is None


# am[verifies a-sleep-serving-cas-tests-1016@f7138e]
def test_competing_promotions_have_one_winner_from_the_same_parent(registry, tmp_path):
    root, _, metadata, evidence, first = registry
    second = sleep.publish_artifact(root, model_files(tmp_path / "second", b"challenger"), metadata, evidence)
    barrier = Barrier(2)

    # am[verifies a-sleep-serving-cas-tests-1016@f7138e]
    def promote(identity):
        barrier.wait()
        try:
            return sleep.promote(root, identity, "base@test")
        except sleep.SleepError as error:
            assert "Stale" in str(error)
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(promote, (first.identity, second.identity)))
    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    assert sleep.capture_active(root) == winners[0]
    assert sleep.resolve_active(root, "base@test", full_hash=True).identity == winners[0].artifact


# am[verifies a-sleep-serving-cas-tests-1016@f7138e]
def test_rollback_generation_prevents_aba_promotion(registry, tmp_path):
    root, _, _, _, first = registry
    reference = sleep.promote(root, first.identity, "base@test")
    metadata, evidence = admissible_metadata(reference, first.identity)
    second = sleep.publish_artifact(root, model_files(tmp_path / "second", b"second"), metadata, evidence)
    stale = sleep.publish_artifact(root, model_files(tmp_path / "stale", b"stale"), metadata, evidence)
    newer = sleep.promote(root, second.identity, "base@test")
    restored = sleep.rollback(root, newer, "base@test")
    assert restored.artifact == reference.artifact
    assert restored.generation != reference.generation
    with pytest.raises(sleep.SleepError, match="Stale"):
        sleep.promote(root, stale.identity, "base@test")
    with pytest.raises(sleep.SleepError, match="exact current"):
        sleep.rollback(root, reference, "base@test")
    assert sleep.capture_active(root) == restored


# am[verifies a-sleep-serving-cas-tests-1016@f7138e]
def test_damaged_retained_parent_cannot_be_restored(registry, tmp_path):
    root, _, _, _, first = registry
    reference = sleep.promote(root, first.identity, "base@test")
    metadata, evidence = admissible_metadata(reference, first.identity)
    second = sleep.publish_artifact(root, model_files(tmp_path / "second", b"second"), metadata, evidence)
    current = sleep.promote(root, second.identity, "base@test")
    weight = first.model_dir / "model.safetensors"
    weight.write_bytes(b"X" * weight.stat().st_size)
    with pytest.raises(sleep.SleepError):
        sleep.rollback(root, current, "base@test")
    assert sleep.capture_active(root) == current


# am[verifies a-sleep-serving-cas-tests-1016@f7138e]
def test_rollback_to_base_retains_a_new_generation(registry):
    root, model, metadata, _, artifact = registry
    reference = sleep.promote(root, artifact.identity, "base@test")
    restored = sleep.rollback(root, reference, "base@test", base_dir=model, base=metadata["base"])
    assert restored.artifact is None
    assert restored.generation != reference.generation
    assert sleep.resolve_active(root, "base@test") == sleep.ServingReference("base@test", None, restored)
    with pytest.raises(sleep.SleepError):
        sleep.promote(root, artifact.identity, "base@test")


# am[verifies a-sleep-serving-cas-tests-1016@f7138e]
def test_serving_rejects_an_active_artifact_from_another_configured_base(registry):
    root, _, _, _, artifact = registry
    reference = sleep.promote(root, artifact.identity, "base@test")
    with pytest.raises(sleep.SleepError, match="base"):
        sleep.resolve_active(root, "another-base")
    assert sleep.capture_active(root) == reference


# am[verifies a-sleep-serving-cas-tests-1016@f7138e]
@pytest.mark.parametrize("mutation", ["missing-weight", "changed-weight", "changed-pin"])
def test_rollback_cannot_activate_a_missing_or_changed_base(registry, mutation):
    root, model, metadata, _, artifact = registry
    reference = sleep.promote(root, artifact.identity, "base@test")
    if mutation == "missing-weight":
        (model / "model.safetensors").unlink()
    elif mutation == "changed-weight":
        (model / "model.safetensors").write_bytes(b"X" * len(b"synthetic-weights"))
    else:
        metadata["base"]["revision"] = "untested-base"
    with pytest.raises(sleep.SleepError):
        sleep.rollback(root, reference, "base@test", base_dir=model, base=metadata["base"])
    assert sleep.capture_active(root) == reference


# am[verifies a-sleep-pointer-fault-tests-1016@290be9]
def test_failed_pointer_replace_preserves_the_current_generation(registry, monkeypatch):
    root, _, _, _, artifact = registry
    original = artifacts.os.replace

    # am[verifies a-sleep-pointer-fault-tests-1016@290be9]
    def fail_pointer(source, destination):
        if Path(destination) == root / "ACTIVE":
            raise OSError("injected ACTIVE replacement failure")
        return original(source, destination)

    monkeypatch.setattr(artifacts.os, "replace", fail_pointer)
    with pytest.raises(OSError, match="injected"):
        sleep.promote(root, artifact.identity, "base@test")
    assert sleep.capture_active(root) is None
    assert not list(root.glob(".sleep-*"))


# am[verifies a-sleep-pointer-fault-tests-1016@290be9]
def test_readers_see_complete_old_or_new_pointers_during_promotion(registry, monkeypatch):
    root, _, _, _, artifact = registry
    original = artifacts.os.replace
    before_replace, continue_replace = Event(), Event()

    # am[verifies a-sleep-pointer-fault-tests-1016@290be9]
    def pause_pointer(source, destination):
        if Path(destination) == root / "ACTIVE":
            before_replace.set()
            continue_replace.wait()
        return original(source, destination)

    monkeypatch.setattr(artifacts.os, "replace", pause_pointer)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(sleep.promote, root, artifact.identity, "base@test")
        future.add_done_callback(lambda _: before_replace.set())
        try:
            before_replace.wait()
            if future.done():
                future.result()
            assert sleep.capture_active(root) is None
            assert sleep.resolve_active(root, "base@test").identity == "base@test"
        finally:
            continue_replace.set()
        expected = future.result()
    assert sleep.capture_active(root) == expected
    assert json.loads((root / "ACTIVE").read_text()) == asdict(expected)
    assert sleep.resolve_active(root, "base@test", full_hash=True).identity == artifact.identity

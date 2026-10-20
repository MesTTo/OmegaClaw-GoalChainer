"""Purpose: verify reviewed reranker training, leakage prevention and conservative admission."""

from dataclasses import asdict, replace
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

from hypothesis import given, settings, strategies as st
import pytest

from goal_chainer import semantic_sleep as sleep
from reading_support import section
from semantic_sleep_support import admissible_metadata, model_files, paired_report as report


# am[verifies a-sleep-contract-1016@7bccc5] am[verifies a-integrate-semantic-artifact-boundary-1018@0c41d7]
def test_serving_reference_import_never_loads_model_computation():
    subprocess.run([sys.executable, "-c", "from goal_chainer.semantic_artifacts import resolve_active, artifact_root; "
                    "import sys; assert not {'torch', 'sentence_transformers', 'goal_chainer.semantic_sleep', "
                    "'goal_chainer.semantic_reader'} & sys.modules.keys()"],
                   env={**os.environ, "PYTHONPATH": str(Path(sleep.__file__).parents[1])}, check=True)


# am[verifies a-sleep-reviewed-store-1016@b92a57]
def example(index: int, label: int = 1, *, source: str | None = None) -> sleep.ReviewedExample:
    text = source or f"Reviewed source {index}. Relevant passage. Unrelated passage."
    return sleep.ReviewedExample(
        example_id=f"row-{index}-{label}", question_id="q-relevance", question="Which passage is relevant?",
        passage="Relevant passage." if label else "Unrelated passage.", label=label,
        reviewer="mechanism-test-curator", reviewed_at="2026-10-16T00:00:00+00:00",
        source_group=f"family-{index}",
        source_id=f"source-{index}", source_text=text, text_digest=hashlib.sha256(text.encode()).hexdigest(),
    )


# am[verifies a-sleep-reviewed-store-1016@b92a57]
def test_review_import_is_atomic_retained_and_deduplicated(tmp_path):
    store = tmp_path / "reviewed.json"
    first, second = example(1), example(2, 0)
    assert sleep.import_reviews(store, [asdict(first)]) == 1
    assert sleep.import_reviews(store, [asdict(first), asdict(second)]) == 1
    assert sleep.import_reviews(store, [asdict(first)]) == 0
    before = store.read_bytes()
    with pytest.raises(sleep.SleepError, match="Conflicting"):
        sleep.import_reviews(store, [asdict(replace(first, reviewer="other-reviewer"))])
    assert store.read_bytes() == before
    assert sleep.reviewed(store) == (first, second)


# am[verifies a-sleep-reviewed-store-1016@b92a57]
@pytest.mark.parametrize("changes", [
    {"label": True}, {"label": 0.5}, {"label": float("nan")}, {"label": 2},
    {"reviewer": ""}, {"reviewed_at": "yesterday"}, {"reviewed_at": "2026-10-16"},
    {"text_digest": "0" * 64}, {"passage": "not in the source"}, {"question": ""},
    {"model_score": 0.99},
])
def test_review_schema_rejects_unreviewed_or_invalid_inputs(changes):
    with pytest.raises(sleep.SleepError):
        sleep.ReviewedExample.parse({**asdict(example(0)), **changes})


# am[verifies a-sleep-reviewed-store-1016@b92a57]
def test_conflicting_question_source_and_pair_identities(tmp_path):
    first = example(1)
    for second in (replace(example(2), question="Other question"),
                   replace(example(2), source_id=first.source_id),
                   replace(first, example_id="other", reviewer="other")):
        with pytest.raises(sleep.SleepError):
            sleep.import_reviews(tmp_path / "reviewed.json", [asdict(first), asdict(second)])


# am[verifies a-sleep-reviewed-store-1016@b92a57]
def test_correlated_documents_stay_in_one_group_and_text_cannot_change_groups(tmp_path):
    first, other = example(1), replace(example(2), source_group="family-1")
    train, holdout = sleep.split_reviews((first, other))
    assert len(train) == 2 or len(holdout) == 2
    bad_alias = replace(first, example_id="renamed", source_id="alias", source_group="other-family")
    with pytest.raises(sleep.SleepError, match="different provenance groups"):
        sleep.import_reviews(tmp_path / "reviewed.json", [asdict(first), asdict(bad_alias)])


# am[verifies a-sleep-reviewed-store-1016@b92a57]
@settings(deadline=None)
@given(st.lists(st.integers(min_value=0, max_value=10000), min_size=1, max_size=40, unique=True))
def test_source_split_is_disjoint_order_independent_and_alias_safe(indices):
    rows = tuple(row for index in indices for row in (example(index), example(index, 0)))
    training, held = sleep.split_reviews(rows)
    assert not {r.text_digest for r in training} & {r.text_digest for r in held}
    reverse_train, reverse_held = sleep.split_reviews(tuple(reversed(rows)))
    assert set(training) == set(reverse_train)
    assert set(held) == set(reverse_held)
    alias = replace(rows[0], example_id="alias", source_id="alias-source")
    alias_train, alias_held = sleep.split_reviews((rows[0], alias))
    assert len(alias_train) == 2 or len(alias_held) == 2


# am[verifies a-sleep-train-evaluate-1016@998fa2]
def test_concordance_is_within_question_and_ties_get_half_credit():
    positive, negative = example(1), example(1, 0)
    group = sleep._group(positive)
    assert sleep.group_metrics((positive, negative), (0.5, 0.5))[group] == {"rank": 0.5, "brier": 0.25}
    assert sleep.group_metrics((positive, replace(negative, question_id="other")), (0.9, 0.1)) == {}
    assert sleep.group_metrics((positive, negative), (0.9, 0.1))[group]["rank"] == 1
    assert sleep.group_metrics((positive, negative), (0.1, 0.9))[group]["rank"] == 0
    with pytest.raises(sleep.SleepError, match="shape"):
        sleep.group_metrics((positive,), ())
    with pytest.raises(sleep.SleepError, match="finite"):
        sleep.group_metrics((positive,), (math.nan,))


# am[verifies a-sleep-train-evaluate-1016@998fa2]
@given(st.lists(st.floats(min_value=0, max_value=1, allow_nan=False), min_size=1, max_size=10),
       st.lists(st.floats(min_value=0, max_value=1, allow_nan=False), min_size=1, max_size=10))
def test_sorted_concordance_matches_all_reviewed_positive_negative_pairs(positive, negative):
    first = example(0)
    rows = [replace(first, example_id=f"positive-{i}") for i in range(len(positive))]
    rows += [replace(first, example_id=f"negative-{i}", label=0) for i in range(len(negative))]
    expected = sum(1 if a > b else 0.5 if a == b else 0 for a in positive for b in negative) / (len(positive) * len(negative))
    assert sleep.group_metrics(rows, positive + negative)[sleep._group(first)]["rank"] == expected


# am[verifies a-sleep-policy-1016@0dbdf0]
def test_admission_requires_fresh_meaningful_improvement_without_regression():
    assert sleep.admission(report()).verdict == "admit"
    assert sleep.admission(report(1)).verdict == "uncertain-improvement"
    assert sleep.admission(report(0)).verdict == "insufficient-fresh-holdout"
    assert sleep.admission(report(champion=0.8, challenger=0.7)).verdict == "ranking-regression"
    assert sleep.admission(report(champion=0.8, challenger=0.8)).verdict == "uncertain-improvement"
    assert sleep.admission(report(old_brier=0.1, new_brier=0.2)).verdict == "brier-regression"
    assert sleep.admission({**report(), "weights_changed": False}).verdict == "unchanged-weights"


# am[verifies a-sleep-policy-1016@0dbdf0]
def test_admission_spending_telescopes_and_rejects_malformed_reports():
    assert sum(sleep.admission({**report(0), "attempt": k}).alpha for k in range(1, 20)) < 0.05
    for bad in ({**report(), "attempt": 0}, {**report(), "fresh_groups": ["0" * 64]},
                {**report(), "weights_changed": 1}):
        with pytest.raises(sleep.SleepError):
            sleep.admission(bad)


# am[verifies a-sleep-policy-1016@0dbdf0]
def test_fresh_improvement_cannot_mask_retained_group_regression():
    value = report()
    old = next(iter(value["groups"]))
    value["fresh_groups"].remove(old)
    value["groups"][old].update(champion_rank=1.0, challenger_rank=0.0)
    assert sleep.admission(value).verdict == "ranking-regression"


# am[verifies a-sleep-policy-1016@0dbdf0]
def test_loaded_policy_cannot_be_relabelled_with_changed_resource_bytes(tmp_path, monkeypatch):
    sleep.admission(report())
    policy = tmp_path / "changed.metta"
    policy.write_bytes(sleep.POLICY.read_bytes() + b"\n; changed policy bytes\n")
    monkeypatch.setattr(sleep, "POLICY", policy)
    with pytest.raises(sleep.SleepError, match="changed after engine initialization"):
        sleep.admission(report())


# am[verifies a-sleep-train-evaluate-1016@998fa2]
def test_reservations_burn_fresh_groups_before_scores_and_never_reuse(tmp_path):
    groups = [sleep.digest(str(index).encode()) for index in range(3)]
    first = sleep._reserve(tmp_path, groups[:2], "1" * 64, None)
    second = sleep._reserve(tmp_path, groups, "2" * 64, None)
    assert first["attempt"] == 1 and second["attempt"] == 2
    assert set(first["fresh_groups"]) == set(groups[:2])
    assert second["fresh_groups"] == [groups[2]]


# am[verifies a-sleep-lineage-retention-1016@89fdcf]
def test_rejected_or_failed_attempts_also_freeze_historical_source_partitions(tmp_path):
    training, holdout = sleep.digest(b"training-family"), sleep.digest(b"holdout-family")
    sleep._reserve(tmp_path, [holdout], "0" * 64, None, train_groups=[training], holdout_groups=[holdout])
    for new_train, new_holdout in (([training, holdout], []), ([], [training, holdout])):
        with pytest.raises(sleep.SleepError, match="cannot change historical"):
            sleep._reserve(tmp_path, [], "1" * 64, None, train_groups=new_train, holdout_groups=new_holdout)
    assert len(json.loads((tmp_path / "evaluations.json").read_bytes())["attempts"]) == 1


# am[verifies a-sleep-lineage-retention-1016@89fdcf]
def test_retained_champion_history_cannot_be_dropped_relabelled_or_repartitioned(tmp_path):
    rows = tuple(row for index in range(8) for row in (example(index), example(index, 0)))
    training, holdout = sleep.split_reviews(rows)
    metadata, evidence = admissible_metadata()
    evidence.update({"reviews.json": sleep.canonical([asdict(row) for row in rows]),
                     "split.json": sleep.canonical({"train": sorted({sleep._group(r) for r in training}),
                                                    "holdout": sorted({sleep._group(r) for r in holdout})})})
    artifact = sleep.publish_artifact(tmp_path / "registry", model_files(tmp_path / "model"), metadata, evidence)
    sleep._check_retention(artifact, rows, training, holdout)
    with pytest.raises(sleep.SleepError, match="retain every champion"):
        sleep._check_retention(artifact, rows[1:], training, holdout)
    altered = (replace(rows[0], reviewer="unrecorded-replacement"), *rows[1:])
    with pytest.raises(sleep.SleepError, match="retain every champion"):
        sleep._check_retention(artifact, altered, training, holdout)
    with pytest.raises(sleep.SleepError, match="held-out provenance"):
        sleep._check_retention(artifact, rows, (*training, holdout[0]), holdout[1:])
    with pytest.raises(sleep.SleepError, match="trained provenance"):
        sleep._check_retention(artifact, rows, training[1:], (*holdout, training[0]))


# am[verifies a-sleep-train-evaluate-1016@998fa2]
def test_corrupt_reservation_history_is_a_hard_error(tmp_path):
    ledger = tmp_path / "evaluations.json"
    ledger.write_text('{"schema":1,"attempts":[{}]}', encoding="utf-8")
    with pytest.raises(sleep.SleepError, match="Corrupt"):
        sleep._reserve(tmp_path, [], "0" * 64, None)


# am[verifies a-sleep-reviewed-store-1016@b92a57]
def test_duplicate_json_fields_are_rejected_without_losing_an_identity(tmp_path):
    store = tmp_path / "reviewed.json"
    store.write_text('{"schema":1,"schema":2,"examples":[]}', encoding="utf-8")
    with pytest.raises(sleep.SleepError, match="Duplicate JSON"):
        sleep.reviewed(store)


# am[verifies a-sleep-artifacts-1016@d2fca8]
@pytest.mark.parametrize("path", [".", "a\0b"])
def test_artifact_file_names_cannot_alias_a_directory_or_contain_nul(path):
    with pytest.raises(sleep.SleepError, match="Unsafe artifact path"):
        sleep._relative(path)


# am[verifies a-sleep-train-evaluate-1016@998fa2]
def test_base_pin_verifies_hub_blob_links_and_rejects_extra_or_changed_files(tmp_path):
    source, blob = tmp_path / "snapshot", tmp_path / "blob"
    source.mkdir()
    blob.write_bytes(b"pinned-public-model-bytes")
    (source / "model.safetensors").symlink_to(blob)
    pin = {"identity": "test@revision", "repo_id": "test", "revision": "revision", "license": "test",
           "files": {"model.safetensors": [blob.stat().st_size, sleep.digest(blob.read_bytes())]}}
    sleep._verify_base(source, pin)
    (source / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(sleep.SleepError, match="unpinned extra"):
        sleep._verify_base(source, pin)
    (source / "extra.json").unlink()
    blob.write_bytes(b"changed-public-model-byte")
    with pytest.raises(sleep.SleepError, match="pin failed"):
        sleep._verify_base(source, pin)


# am[verifies a-sleep-cli-docs-1016@05a457]
def test_cli_import_status_and_hard_errors(tmp_path, capsys):
    rows = tmp_path / "reviews.jsonl"
    rows.write_text(json.dumps(asdict(example(1))) + "\n", encoding="utf-8")
    root = tmp_path / "registry"
    assert sleep.main(["--root", str(root), "import", str(rows)]) == 0
    assert json.loads(capsys.readouterr().out) == {"added": 1}
    assert sleep.main(["--root", str(root), "status"]) == 0
    assert json.loads(capsys.readouterr().out)["reviewed_count"] == 1
    assert sleep.main(["--root", str(root), "verify", "../invalid"]) == 1
    assert json.loads(capsys.readouterr().err)["error"] == "SleepError"


# am[verifies a-sleep-verify-1016@f92950] am[verifies a-sleep-train-evaluate-1016@998fa2]
def test_real_tiny_public_model_update_and_offline_replay(tmp_path, monkeypatch):
    """A pinned public tiny-BERT construction proves updates, never domain improvement."""
    fixture = os.environ.get("GOALCHAINER_SLEEP_TEST_BASE")
    assert fixture, "Provision the pinned tiny public base; set GOALCHAINER_SLEEP_TEST_BASE (docs/semantic-sleep.md)"
    fixture_path = Path(fixture)
    base = json.loads((fixture_path / "base.json").read_text(encoding="utf-8"))
    base_dir = fixture_path / "model"
    assert base["repo_id"] == "prajjwal1/bert-tiny"
    assert base["revision"] == "6f75de8b60a9f8a2fdf7b69cbd86d9e64bcb3837"
    assert base["license"] == "mit"
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    rows = tuple(row for index in range(8) for row in (example(index), example(index, 0)))
    root = tmp_path / "registry"
    store = root / "reviewed.json"
    sleep.import_reviews(store, [asdict(row) for row in rows])
    config = sleep.TrainingConfig(epochs=1, learning_rate=1e-3, batch_size=8, seed=7)
    declaration = section(
        "(gc-reading-domain relevance-probe)\n"
        '(gc-reading-model "jev-1.13.0")\n'
        '(gc-reading-language "en")\n'
        '(gc-reading-instructions "Decide whether `text` supports this proposition: ")\n'
        '(gc-reading-option supported for "The text supports it.")\n'
        '(gc-reading-proposition q-relevance "A passage is relevant." "Which passage is relevant?")\n'
        '(gc-ranking-instruction "Rank the passage for relevance to the question.")\n'
    )
    artifact = sleep.train(store, root, declaration=declaration, base_dir=base_dir, base=base, config=config)
    assert artifact.manifest["weights"]["champion"] != artifact.manifest["weights"]["challenger"]
    assert artifact.manifest["test"]["weights_changed"] is True
    assert artifact.manifest["reviewed"]["count"] == len(rows)
    assert sleep.evaluate(root, artifact.identity, base_dir=base_dir)["replayed"] is True
    # Four held-out groups cannot make this fixed Hoeffding lower bound positive, even at d=1.
    assert artifact.manifest["admission"]["fresh_count"] < 2 * math.log(1 / artifact.manifest["admission"]["alpha"])
    assert artifact.manifest["admission"]["verdict"] != "admit"
    with pytest.raises(sleep.SleepError, match="Promotion refused"):
        sleep.promote(root, artifact.identity, base["identity"])
    assert sleep.capture_active(root) is None
    assert sleep.validate_artifact(root, artifact.identity).identity == artifact.identity


# Time: one 18 MB download and one tiny-model serialization, then offline file verification.
# am[verifies a-sleep-verify-1016@f92950]
def prepare_tiny_base(destination: Path) -> None:
    """Build the repeatable test fixture from commit-pinned, hash-verified public bytes."""
    with sleep._locked(destination):
        _prepare_tiny_base_locked(destination)


# am[verifies a-sleep-verify-1016@f92950]
def _prepare_tiny_base_locked(destination: Path) -> None:
    import torch
    from sentence_transformers import CrossEncoder
    from transformers import BertConfig, BertForSequenceClassification, BertTokenizer

    revision = "6f75de8b60a9f8a2fdf7b69cbd86d9e64bcb3837"
    # Hub tree at the pinned revision: git blob IDs for regular files, LFS SHA for weights.
    files = {
        "config.json": (285, "234608c922aaf3989d6a772af31711fbbdd62e3a"),
        "vocab.txt": (231508, "fb140275c155a9c7c5a3b3e0e77a9e839594a938"),
        "pytorch_model.bin": (17756393, "dab2c2bddcfb48ea430ef63fd76d46d67d704487844d967256a50dd7d7fd0a66"),
        "README.md": (2560, "488d07a361bd823cc0fad0a6661f73ff6debc000"),
    }
    source = destination / "bert-tiny-source"
    source.mkdir(parents=True, exist_ok=True)
    for filename, (size, expected) in files.items():
        path = source / filename
        if not path.exists():
            request = urllib.request.Request(f"https://huggingface.co/prajjwal1/bert-tiny/resolve/{revision}/{filename}")
            with urllib.request.urlopen(request) as response:
                sleep._atomic(path, response.read())
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest() if filename.endswith(".bin") else hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        if len(data) != size or actual != expected:
            raise sleep.SleepError(f"Pinned public test-model file failed integrity: {filename}")
    if "mit" not in (source / "README.md").read_text().split("---")[1]:
        raise sleep.SleepError("Pinned public test-model card does not assert MIT")
    if (destination / "base.json").exists():
        base = sleep._json(destination / "base.json")
        if not isinstance(base, dict) or any(base.get(key) != expected for key, expected in {
            "repo_id": "prajjwal1/bert-tiny", "revision": revision, "license": "mit", "construction_seed": 7,
            "source_files": sleep._inventory(source),
        }.items()) or base.get("identity") != "constructed-bert-tiny:" + sleep.digest(sleep.canonical(base.get("files"))):
            raise sleep.SleepError("Existing tiny test fixture differs from the exact public construction pin")
        sleep._verify_base(destination / "model", base)
        print(sleep.canonical({"base": base["identity"], "verified": True}).decode())
        return
    if (destination / "model").exists():
        raise sleep.SleepError("Incomplete tiny fixture has no base.json pin; use an empty fixture directory")
    torch.manual_seed(7)
    construction = destination / "bert-construction"
    # The 2021 config predates model_type. The typed BERT config derives it and one output.
    config = BertConfig.from_dict(json.loads((source / "config.json").read_bytes()), num_labels=1)
    backbone = BertForSequenceClassification.from_pretrained(str(source), config=config, local_files_only=True)
    backbone.save_pretrained(str(construction))
    BertTokenizer.from_pretrained(str(source), local_files_only=True).save_pretrained(str(construction))
    model = CrossEncoder(str(construction), num_labels=1, device="cpu", local_files_only=True,
                         model_kwargs={"dtype": torch.float32}, activation_fn=torch.nn.Sigmoid())
    model.save_pretrained(str(destination / "model"))
    inventory = sleep._inventory(destination / "model")
    base = {"identity": "constructed-bert-tiny:" + sleep.digest(sleep.canonical(inventory)),
            "repo_id": "prajjwal1/bert-tiny", "revision": revision, "license": "mit", "files": inventory,
            "source_files": sleep._inventory(source), "construction_seed": 7}
    sleep._atomic(destination / "base.json", sleep.canonical(base))
    print(sleep.canonical({"base": base["identity"], "parameters": sum(p.numel() for p in model.parameters())}).decode())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prepare the pinned tiny public-model offline test fixture")
    parser.add_argument("--prepare-base", type=Path, required=True)
    prepare_tiny_base(parser.parse_args().prepare_base)

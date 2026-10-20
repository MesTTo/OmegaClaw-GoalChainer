"""Purpose: train and evaluate reviewed rerankers and govern their promotion and rollback."""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import defaultdict
from contextlib import redirect_stdout
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from importlib import metadata, resources
import json
import logging
import math
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Sequence

from .domains.readings import ReadingDeclaration
from . import semantic_artifacts
from .runtime import numbers

# The reader and sleep command share the artifact protocol, which imports neither caller.
# am[implements a-integrate-semantic-artifact-boundary-1018@0c41d7]
from .semantic_artifacts import (
    ActiveReference, Artifact, MANIFEST, ServingReference, SleepError,
    artifact_root, canonical, capture_active, digest, publish_artifact,
    resolve_active, validate_artifact,
    _atomic, _decode, _directory, _inventory, _json, _locked, _pointer,
    _regular, _relative, _sha, _switch,
)

logger = logging.getLogger(__name__)
POLICY = resources.files("goal_chainer").joinpath("sleep_policy.metta")
_LOADED_POLICY: bytes | None = None
# Shared artifact validation and finite conversion remain part of the evaluator's sealed source.
# am[implements a-semantic-boundary-seal-1018@edc449] am[implements a-integrate-sleep-number-refusal-1018@b7192f]
EVALUATOR_SOURCES = {"evaluation.py": Path(__file__).read_bytes(),
                     "artifacts.py": Path(semantic_artifacts.__file__).read_bytes(),
                     "numbers.py": Path(numbers.__file__).read_bytes()}


# am[implements a-sleep-reviewed-store-1016@b92a57]
def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SleepError(f"{name} must be nonempty text")
    return value


# am[implements a-sleep-train-evaluate-1016@998fa2]
# am[implements a-integrate-sleep-number-refusal-1018@b7192f] am[rests-on c-sleep-number-contract-1018@8ff440]
def _finite(value: Any, name: str, low: float, high: float) -> float:
    number = numbers.finite_float(value)
    if number is None or not low <= value <= high:
        raise SleepError(f"{name} must be finite in [{low}, {high}]")
    return number


# am[implements a-sleep-reviewed-store-1016@b92a57]
@dataclass(frozen=True)
class ReviewedExample:
    example_id: str
    question_id: str
    question: str
    passage: str
    label: int
    reviewer: str
    reviewed_at: str
    source_group: str
    source_id: str
    source_text: str
    text_digest: str

    # am[implements a-sleep-reviewed-store-1016@b92a57]
    @classmethod
    def parse(cls, row: Mapping[str, Any]) -> ReviewedExample:
        if not isinstance(row, dict) or set(row) != set(cls.__dataclass_fields__):
            raise SleepError("Reviewed row must contain exactly " + ", ".join(cls.__dataclass_fields__))
        for key in cls.__dataclass_fields__:
            if key != "label":
                _text(row[key], key)
        if type(row["label"]) is not int or row["label"] not in (0, 1):
            raise SleepError("Reviewed relevance label must be integer 0 or 1")
        try:
            stamp = datetime.fromisoformat(row["reviewed_at"].replace("Z", "+00:00"))
        except ValueError as error:
            raise SleepError("reviewed_at must be an ISO-8601 timestamp") from error
        if stamp.utcoffset() is None:
            raise SleepError("reviewed_at must include a timezone")
        if _sha(row["text_digest"]) != digest(row["source_text"].encode("utf-8")):
            raise SleepError("Source text does not match text_digest")
        if row["passage"] not in row["source_text"]:
            raise SleepError("Reviewed passage must occur in source_text")
        return cls(**row)


# Time: n dictionary insertions + n log(n) identity comparisons + b text bytes validated.
# Space: n retained records; n = examples, b = UTF-8 source and passage bytes.
# am[implements a-sleep-reviewed-store-1016@b92a57]
def _checked(rows: Sequence[Mapping[str, Any]]) -> tuple[ReviewedExample, ...]:
    found: dict[str, ReviewedExample] = {}
    questions: dict[str, str] = {}
    sources: dict[str, str] = {}
    pairs: dict[tuple[str, str, str], ReviewedExample] = {}
    text_groups: dict[str, str] = {}
    for row in rows:
        example = ReviewedExample.parse(row)
        previous_group = text_groups.setdefault(example.text_digest, example.source_group)
        if previous_group != example.source_group:
            raise SleepError("Identical source text cannot declare different provenance groups")
        for mapping, key, value in ((questions, example.question_id, example.question),
                                    (sources, example.source_id, example.text_digest)):
            if key in mapping and mapping[key] != value:
                raise SleepError(f"Conflicting reused identity: {key}")
            mapping[key] = value
        if example.example_id in found and found[example.example_id] != example:
            raise SleepError(f"Conflicting reused example_id: {example.example_id}")
        pair = (example.question_id, example.text_digest, example.passage)
        if pair in pairs and pairs[pair] != example:
            raise SleepError("Duplicate question/passage identity with different review metadata")
        pairs[pair] = example
        found[example.example_id] = example
    return tuple(found[key] for key in sorted(found))


# am[implements a-sleep-reviewed-store-1016@b92a57]
def reviewed(store: Path) -> tuple[ReviewedExample, ...]:
    if not store.exists() and not store.is_symlink():
        return ()
    document = _json(store)
    if not isinstance(document, dict) or set(document) != {"schema", "examples"} or document["schema"] != 1 or not isinstance(document["examples"], list):
        raise SleepError("Invalid reviewed store schema")
    return _checked(document["examples"])


# am[implements a-sleep-reviewed-store-1016@b92a57]
def import_reviews(store: Path, rows: Sequence[Mapping[str, Any]]) -> int:
    incoming = _checked(rows)
    with _locked(store.parent):
        existing = reviewed(store)
        combined = _checked([asdict(row) for row in (*existing, *incoming)])
        _atomic(store, canonical({"schema": 1, "examples": [asdict(row) for row in combined]}))
    logger.debug("Reviewed import retained=%s added=%s", len(combined), len(combined) - len(existing))
    return len(combined) - len(existing)


# am[implements a-sleep-policy-1016@0dbdf0] am[implements a-rt-loaded-identity-1016@e4ffa3]
def _policy(operation: str, *arguments: Any) -> Any:
    from .runtime.modules import load_metta_module
    from .runtime.engine import metta_engine
    from .runtime.evaluator import plain_value

    global _LOADED_POLICY
    holes = {f"value{index}": value for index, value in enumerate(arguments)}
    expression = "!(gc-sleep-" + operation + " " + " ".join("{" + key + "}" for key in holes) + ")"
    # The sleep policy partitions and scores reviewed examples offline, outside any request, so its
    # wait for the engine has no deadline.
    # am[implements a-rt-engine-budget-required-1018@e013ed]
    with metta_engine(None) as engine:
        current = POLICY.read_bytes()
        if _LOADED_POLICY is not None and _LOADED_POLICY != current:
            raise SleepError("Sleep policy changed after engine initialization; restart the process")
        load_metta_module(engine, Path(str(POLICY)))
        _LOADED_POLICY = current
        answers = engine.run(expression, **holes)
    if len(answers) != 1 or len(answers[0]) != 1:
        raise SleepError(f"Sleep MeTTa policy returned an invalid answer: {answers!r}")
    return plain_value(answers[0][0])


# am[implements a-sleep-reviewed-store-1016@b92a57]
def split_reviews(examples: Sequence[ReviewedExample]) -> tuple[tuple[ReviewedExample, ...], tuple[ReviewedExample, ...]]:
    partitions = {group: _policy("partition", int(group, 16) / (1 << 256))
                  for group in sorted({_group(row) for row in examples})}
    return (tuple(row for row in examples if partitions[_group(row)] == "train"),
            tuple(row for row in examples if partitions[_group(row)] == "holdout"))


# am[implements a-sleep-reviewed-store-1016@b92a57]
def _group(row: ReviewedExample) -> str:
    return digest(row.source_group.encode("utf-8"))


# Time: sum q log(q) score comparisons; q = candidates per question in each source group.
# Space: n scores, n = reviewed pairs. Tied positive-negative scores receive half credit.
# am[implements a-sleep-train-evaluate-1016@998fa2]
def group_metrics(examples: Sequence[ReviewedExample], scores: Sequence[float]) -> dict[str, dict[str, float]]:
    if len(examples) != len(scores):
        raise SleepError("Prediction shape differs from reviewed pairs")
    questions: dict[tuple[str, str], list[tuple[int, float]]] = defaultdict(list)
    for row, score in zip(examples, scores, strict=True):
        questions[_group(row), row.question_id].append((row.label, _finite(score, "prediction", 0, 1)))
    ranks: dict[str, list[float]] = defaultdict(list)
    briers: dict[str, list[float]] = defaultdict(list)
    for (group, _), values in questions.items():
        negatives = sorted(score for label, score in values if label == 0)
        positives = [score for label, score in values if label == 1]
        if not negatives or not positives:
            continue
        concordance = sum((bisect_left(negatives, score) + bisect_right(negatives, score)) / 2 for score in positives)
        ranks[group].append(concordance / (len(negatives) * len(positives)))
        briers[group].append(sum((score - label) ** 2 for label, score in values) / len(values))
    return {group: {"rank": sum(values) / len(values), "brier": sum(briers[group]) / len(briers[group])}
            for group, values in sorted(ranks.items())}


# am[implements a-sleep-policy-1016@0dbdf0]
@dataclass(frozen=True)
class Admission:
    verdict: str
    alpha: float
    lower: float
    fresh_count: int
    ranking_delta: float
    brier_improvement: float


# Time: n numerical comparisons, n = independent held-out source groups.
# am[implements a-sleep-policy-1016@0dbdf0] am[rests-on c-sleep-numerical-contract-1016@79a33a]
def admission(report: Mapping[str, Any]) -> Admission:
    if not isinstance(report, dict) or set(report) != {"attempt", "groups", "fresh_groups", "weights_changed"}:
        raise SleepError("Invalid paired evaluation report")
    attempt, groups, fresh = report["attempt"], report["groups"], report["fresh_groups"]
    if type(attempt) is not int or attempt < 1 or not isinstance(groups, dict) or not isinstance(fresh, list):
        raise SleepError("Invalid evaluation attempt or source groups")
    for group in fresh:
        _sha(group)
    if len(set(fresh)) != len(fresh) or not set(fresh) <= groups.keys():
        raise SleepError("Invalid evaluation attempt or source groups")
    if type(report["weights_changed"]) is not bool:
        raise SleepError("weights_changed must be a boolean")
    ranking, brier = {}, {}
    for group, row in groups.items():
        _sha(group)
        if not isinstance(row, dict) or set(row) != {"champion_rank", "challenger_rank", "champion_brier", "challenger_brier"}:
            raise SleepError("Invalid paired group metrics")
        values = {key: _finite(value, key, 0, 1) for key, value in row.items()}
        ranking[group] = values["challenger_rank"] - values["champion_rank"]
        brier[group] = values["champion_brier"] - values["challenger_brier"]
    alpha = _finite(_policy("alpha", attempt), "policy alpha", 0, 1)
    if alpha == 0:
        raise SleepError("Evaluation risk budget underflow")
    lower = sum(ranking[group] for group in fresh) / len(fresh) - math.sqrt(2 * math.log(1 / alpha) / len(fresh)) if fresh else -1.0
    rank_delta = sum(ranking.values()) / len(ranking) if ranking else 0.0
    brier_delta = sum(brier.values()) / len(brier) if brier else 0.0
    retained = sorted(groups.keys() - set(fresh))
    retained_rank = sum(ranking[group] for group in retained) / len(retained) if retained else rank_delta
    retained_brier = sum(brier[group] for group in retained) / len(retained) if retained else brier_delta
    verdict = _policy("admit", len(fresh), lower, rank_delta, brier_delta,
                      retained_rank, retained_brier, report["weights_changed"])
    if not isinstance(verdict, str):
        raise SleepError("Admission policy must return a text verdict")
    logger.debug("Admission groups=%s fresh=%s lower=%s rank_delta=%s brier_delta=%s verdict=%s",
                 len(groups), len(fresh), lower, rank_delta, brier_delta, verdict)
    return Admission(verdict, alpha, lower, len(fresh), rank_delta, brier_delta)


# am[implements a-sleep-train-evaluate-1016@998fa2]
def paired_report(examples: Sequence[ReviewedExample], champion: Sequence[float], challenger: Sequence[float],
                  *, attempt: int, fresh_groups: Sequence[str], weights_changed: bool) -> dict[str, Any]:
    before, after = group_metrics(examples, champion), group_metrics(examples, challenger)
    if before.keys() != after.keys():
        raise SleepError("Paired predictions cover different source groups")
    report = {"attempt": attempt, "fresh_groups": sorted(fresh_groups), "weights_changed": weights_changed,
              "groups": {group: {"champion_rank": before[group]["rank"], "challenger_rank": after[group]["rank"],
                                  "champion_brier": before[group]["brier"], "challenger_brier": after[group]["brier"]}
                         for group in before}}
    admission(report)
    return report


# am[implements a-sleep-train-evaluate-1016@998fa2]
def _reserve(root: Path, eligible: Sequence[str], dataset_digest: str,
             parent_ref: ActiveReference | None, *, train_groups: Sequence[str] = (),
             holdout_groups: Sequence[str] | None = None) -> dict[str, Any]:
    with _locked(root):
        path = root / "evaluations.json"
        ledger = _json(path) if path.exists() else {"schema": 1, "attempts": []}
        if not isinstance(ledger, dict) or set(ledger) != {"schema", "attempts"} or ledger["schema"] != 1 or not isinstance(ledger["attempts"], list):
            raise SleepError("Invalid evaluation reservation ledger")
        used, historical_train, historical_holdout = set(), set(), set()
        for number, item in enumerate(ledger["attempts"], 1):
            if not isinstance(item, dict) or set(item) != {"attempt", "fresh_groups", "dataset_digest", "parent_ref", "split"} or item["attempt"] != number or not isinstance(item["fresh_groups"], list):
                raise SleepError("Corrupt evaluation reservation history")
            _sha(item["dataset_digest"])
            if item["parent_ref"] is not None:
                ActiveReference.parse(item["parent_ref"])
            for group in item["fresh_groups"]:
                _sha(group)
                if group in used:
                    raise SleepError("Evaluation reservation history reused a fresh group")
                used.add(group)
            split = item["split"]
            if not isinstance(split, dict) or set(split) != {"train", "holdout"} or any(not isinstance(value, list) for value in split.values()):
                raise SleepError("Corrupt evaluation split history")
            for group in (*split["train"], *split["holdout"]):
                _sha(group)
            historical_train.update(split["train"])
            historical_holdout.update(split["holdout"])
        training = set(train_groups)
        holdout = set(eligible if holdout_groups is None else holdout_groups)
        for group in training | holdout:
            _sha(group)
        if training & holdout or historical_train & historical_holdout or training & historical_holdout or holdout & historical_train:
            raise SleepError("Provenance groups cannot change historical train/holdout partitions")
        if not set(eligible) <= holdout:
            raise SleepError("Fresh evaluation eligibility must be a subset of held-out groups")
        reservation = {"attempt": len(ledger["attempts"]) + 1, "fresh_groups": sorted(set(eligible) - used),
                       "dataset_digest": dataset_digest, "parent_ref": _pointer(parent_ref),
                       "split": {"train": sorted(training), "holdout": sorted(holdout)}}
        ledger["attempts"].append(reservation)
        _atomic(path, canonical(ledger))
    return reservation


# am[implements a-sleep-artifacts-1016@d2fca8]
def promote(root: Path, artifact_id: str, base_identity: str) -> ActiveReference:
    artifact = validate_artifact(root, artifact_id)
    manifest = artifact.manifest
    policy_path = artifact.model_dir.parent / "evidence" / "policy.metta"
    _regular(policy_path)
    policy_bytes = policy_path.read_bytes()
    if policy_bytes != POLICY.read_bytes():
        raise SleepError("Artifact was evaluated under a different admission policy")
    # am[implements a-semantic-boundary-seal-1018@edc449]
    for name, source in EVALUATOR_SOURCES.items():
        evaluation_path = artifact.model_dir.parent / "evidence" / name
        _regular(evaluation_path)
        if evaluation_path.read_bytes() != source:
            raise SleepError("Artifact was evaluated under a different evaluator implementation")
    verdict = admission(manifest.get("test"))
    if verdict.verdict != "admit":
        raise SleepError(f"Promotion refused: {verdict.verdict}")
    expected = manifest.get("parent_ref")
    if expected is not None:
        expected = _pointer(ActiveReference.parse(expected))
    expected_identity = base_identity if expected is None or expected["artifact"] is None else expected["artifact"]
    if manifest.get("parent") != expected_identity or manifest.get("base", {}).get("identity") != base_identity:
        raise SleepError("Artifact baseline identity differs from its evaluated parent")
    with _locked(root):
        if _pointer(capture_active(root)) != expected:
            raise SleepError("Stale evaluated champion: ACTIVE changed")
        # Recheck retained target under the same lock used by every cooperating writer.
        validate_artifact(root, artifact_id)
        return _switch(root, artifact.identity)


# am[implements a-sleep-artifacts-1016@d2fca8]
def rollback(root: Path, expected: ActiveReference, base_identity: str, *,
             base_dir: Path | None = None, base: dict[str, Any] | None = None) -> ActiveReference:
    if (base_dir is None) != (base is None):
        raise SleepError("Custom rollback base_dir and complete base pin must be supplied together")
    with _locked(root):
        current = capture_active(root)
        if current != expected or current.artifact is None:
            raise SleepError("Rollback requires the exact current artifact and generation")
        artifact = validate_artifact(root, current.artifact)
        parent = artifact.manifest.get("parent")
        if parent == base_identity:
            if base is None:
                base_dir, base = _base()
            assert base_dir is not None
            if base != artifact.manifest.get("base") or base.get("identity") != base_identity:
                raise SleepError("Rollback requires the exact configured base pin")
            _verify_base(base_dir, base)
            target = None
        else:
            target = validate_artifact(root, _sha(parent)).identity
        if artifact.manifest.get("base", {}).get("identity") != base_identity:
            raise SleepError("Rollback base identity differs from serving configuration")
        return _switch(root, target)


# am[implements a-sleep-train-evaluate-1016@998fa2]
@dataclass(frozen=True)
class TrainingConfig:
    epochs: float = 1.0
    learning_rate: float = 2e-5
    batch_size: int = 4
    seed: int = 0

    # am[implements a-sleep-train-evaluate-1016@998fa2]
    # am[implements a-integrate-sleep-number-refusal-1018@b7192f] am[rests-on c-sleep-number-contract-1018@8ff440]
    def validate(self) -> None:
        if numbers.finite_float(self.epochs) is None or self.epochs <= 0:
            raise SleepError("epochs must be finite and positive")
        _finite(self.learning_rate, "learning_rate", 0, 1)
        if self.learning_rate == 0 or type(self.batch_size) is not int or self.batch_size < 1 or type(self.seed) is not int or self.seed < 0:
            raise SleepError("learning_rate, batch_size and seed must define valid training")


# am[implements a-sleep-train-evaluate-1016@998fa2]
def _load_model(directory: Path, instruction: str) -> Any:
    import torch
    from sentence_transformers import CrossEncoder

    return CrossEncoder(str(directory), device="cpu", local_files_only=True,
                        model_kwargs={"dtype": torch.float32},
                        prompts={"goalchainer": instruction}, default_prompt_name="goalchainer",
                        activation_fn=torch.nn.Sigmoid())


# am[implements a-sleep-train-evaluate-1016@998fa2]
def _scores(model: Any, examples: Sequence[ReviewedExample], batch_size: int) -> tuple[float, ...]:
    values = model.predict([(row.question, row.passage) for row in examples],
                           batch_size=batch_size, show_progress_bar=False)
    return tuple(float(value) for value in values)


# am[implements a-sleep-train-evaluate-1016@998fa2]
def _base() -> tuple[Path, dict[str, Any]]:
    from .semantic_models import RERANKER, ready_model_dir

    return ready_model_dir(), {"identity": RERANKER.identity, "repo_id": RERANKER.repo_id,
                      "revision": RERANKER.revision, "license": RERANKER.license,
                      "files": {file.path: [file.size, file.sha256] for file in RERANKER.files}}


# am[implements a-sleep-train-evaluate-1016@998fa2]
def _verify_base(directory: Path, base: Mapping[str, Any]) -> None:
    for key in ("identity", "repo_id", "revision", "license"):
        _text(base.get(key), "base " + key)
    if not isinstance(base.get("files"), dict) or not base["files"]:
        raise SleepError("Base model requires a pinned file inventory")
    _directory(directory)
    # HuggingFace snapshots link files to content blobs. Pins verify these source bytes;
    # published artifacts themselves are copied regular files and reject every symlink.
    paths = {}
    for path in directory.rglob("*"):
        if path.is_dir():
            if path.is_symlink():
                raise SleepError("Base model directory symlinks are forbidden")
            continue
        paths[path.relative_to(directory).as_posix()] = path
    paths.pop("goalchainer-ready.json", None)
    if set(paths) != set(base["files"]):
        raise SleepError("Base model has missing or unpinned extra files")
    for path, expected in base["files"].items():
        _relative(path)
        actual = paths[path]
        if not actual.is_file():
            raise SleepError(f"Missing base model file: {path}")
        hasher = hashlib.sha256()
        with actual.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                hasher.update(block)
        if [actual.stat().st_size, hasher.hexdigest()] != expected:
            raise SleepError(f"Base model pin failed: {path}")


# am[implements a-sleep-train-evaluate-1016@998fa2]
def _weight_digest(model: Any) -> str:
    hasher = hashlib.sha256()
    for name, tensor in sorted(model.named_parameters()):
        hasher.update(name.encode("utf-8") + b"\0")
        hasher.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return hasher.hexdigest()


# Time: n identity lookups + g group comparisons; n = old reviews, g = old provenance groups.
# am[implements a-sleep-lineage-retention-1016@89fdcf]
def _check_retention(champion: Artifact, examples: Sequence[ReviewedExample],
                     training: Sequence[ReviewedExample], holdout: Sequence[ReviewedExample]) -> None:
    evidence = champion.model_dir.parent / "evidence"
    old = _checked(_json(evidence / "reviews.json"))
    current = {row.example_id: row for row in examples}
    if any(current.get(row.example_id) != row for row in old):
        raise SleepError("Training must retain every champion reviewed example unchanged")
    split = _json(evidence / "split.json")
    if not isinstance(split, dict) or set(split) != {"train", "holdout"} or any(not isinstance(value, list) for value in split.values()):
        raise SleepError("Invalid retained champion split")
    previous_train, previous_holdout = set(split["train"]), set(split["holdout"])
    for group in previous_train | previous_holdout:
        _sha(group)
    if previous_train & previous_holdout or previous_train | previous_holdout != {_group(row) for row in old}:
        raise SleepError("Retained champion split is incomplete or leaks across partitions")
    if previous_holdout & {_group(row) for row in training}:
        raise SleepError("Previously held-out provenance groups cannot enter training")
    if previous_train & {_group(row) for row in holdout}:
        raise SleepError("Previously trained provenance groups cannot become holdout")


# Time: E training passes over t pairs plus two inference passes over h holdout pairs.
# Space: model, gradients and optimizer tensors plus O(t+h) reviewed records.
# E = epochs, t = train pairs, h = holdout pairs; transformer cost depends on token lengths.
# The cross-encoder trains for one reading declaration, whose ranking instruction it is prompted
# with and whose questions every reviewed row must ask, word for word, so a row reviewed under
# another declaration's questions trains nothing.
# am[implements a-sleep-train-evaluate-1016@998fa2] am[rests-on c-sleep-framework-source-1016@205b6c]
# am[implements a-dr-sr-tool-budgets-1018@e4d351]
def train(store: Path, root: Path, *, declaration: ReadingDeclaration,
          config: TrainingConfig = TrainingConfig(), base_dir: Path | None = None,
          base: dict[str, Any] | None = None) -> Artifact:
    config.validate()
    try:
        from datasets import Dataset
        from sentence_transformers import CrossEncoderTrainer, CrossEncoderTrainingArguments
        from sentence_transformers.cross_encoder.losses import BinaryCrossEntropyLoss
        from transformers import set_seed
    except ImportError as error:
        raise SleepError("Install the semantic and train extras: uv sync --extra semantic --extra train") from error
    if (base_dir is None) != (base is None):
        raise SleepError("Custom base_dir and complete base pin must be supplied together")
    if base is None:
        base_dir, base = _base()
    assert base_dir is not None
    _verify_base(base_dir, base)
    examples = reviewed(store)
    instruction = declaration.ranking_instruction
    questions = {item.id: item.question for item in declaration.propositions}
    if any(questions.get(row.question_id) != row.question for row in examples):
        raise SleepError(f"Reviewed question id/text differs from the {declaration.name} reading declaration")
    _text(instruction, "ranking instruction")
    training, holdout = split_reviews(examples)
    if not training or not holdout or {row.label for row in training} != {0, 1}:
        raise SleepError("Training needs both relevance labels and separate source-group holdout")
    reference = resolve_active(root, base["identity"], full_hash=True)
    champion_dir = reference.model_dir or base_dir
    if reference.model_dir is not None:
        champion_artifact = validate_artifact(root, reference.identity)
        champion_manifest = champion_artifact.manifest
        if champion_manifest.get("base") != base or champion_manifest.get("instruction") != instruction:
            raise SleepError("ACTIVE base pin or prompt differs from this training configuration")
        _check_retention(champion_artifact, examples, training, holdout)
    dataset_bytes = canonical([asdict(row) for row in examples])
    dataset_digest = digest(dataset_bytes)
    # Eligibility depends on labels only, before either model scores the holdout.
    eligible = sorted(group_metrics(holdout, [0.5] * len(holdout)))
    reservation = _reserve(root, eligible, dataset_digest, reference.pointer,
                           train_groups=sorted({_group(row) for row in training}),
                           holdout_groups=sorted({_group(row) for row in holdout}))
    logger.debug("Training captured champion=%s parent_ref=%s train=%s holdout=%s reservation=%s",
                 reference.identity, reference.pointer, len(training), len(holdout), reservation)
    set_seed(config.seed)
    model = _load_model(champion_dir, instruction)
    before_digest = _weight_digest(model)
    champion_scores = _scores(model, holdout, config.batch_size)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".training-", dir=root) as temporary:
        work = Path(temporary)
        # Only these columns reach Trainer: reviewer/source metadata is never a model input.
        dataset = Dataset.from_dict({"question": [row.question for row in training],
                                     "passage": [row.passage for row in training],
                                     "label": [float(row.label) for row in training]})
        arguments = CrossEncoderTrainingArguments(
            output_dir=str(work / "trainer"), num_train_epochs=config.epochs,
            learning_rate=config.learning_rate, per_device_train_batch_size=config.batch_size,
            seed=config.seed, data_seed=config.seed, use_cpu=True, fp16=False, bf16=False,
            prompts=instruction,
            save_strategy="no", eval_strategy="no", report_to=[], push_to_hub=False,
            logging_strategy="no", disable_tqdm=True,
        )
        trainer = CrossEncoderTrainer(model=model, args=arguments, train_dataset=dataset,
                                      loss=BinaryCrossEntropyLoss(model))
        with redirect_stdout(sys.stderr):
            trainer.train()
        after_digest = _weight_digest(model)
        challenger_scores = _scores(model, holdout, config.batch_size)
        report = paired_report(holdout, champion_scores, challenger_scores,
                               attempt=reservation["attempt"], fresh_groups=reservation["fresh_groups"],
                               weights_changed=after_digest != before_digest)
        destination = work / "challenger"
        model.save_pretrained(str(destination))
        # Verify the serialized model produces the actual evaluated predictions.
        del trainer, model
        reloaded = _load_model(destination, instruction)
        replay = _scores(reloaded, holdout, config.batch_size)
        if replay != challenger_scores:
            raise SleepError("Saved challenger predictions differ from its evaluated weights")
        verdict = admission(report)
        evidence = {"reviews.json": dataset_bytes, "policy.metta": POLICY.read_bytes(),
                    **EVALUATOR_SOURCES,
                    "predictions.json": canonical({"example_ids": [row.example_id for row in holdout],
                                                     "champion": champion_scores, "challenger": challenger_scores}),
                    "split.json": canonical({"train": sorted({_group(r) for r in training}),
                                              "holdout": sorted({_group(r) for r in holdout})}),
                    "reservation.json": canonical(reservation)}
        document = {"base": base, "parent": reference.identity, "parent_ref": _pointer(reference.pointer),
                    "reviewed": {"digest": dataset_digest, "count": len(examples), "holdout_count": len(holdout)},
                    "config": asdict(config), "instruction": instruction,
                    "framework": {name: metadata.version(name) for name in ("sentence-transformers", "torch", "transformers", "datasets", "accelerate", "pymetta")},
                    "weights": {"champion": before_digest, "challenger": after_digest},
                    "test": report, "admission": asdict(verdict),
                    "created": datetime.now(timezone.utc).isoformat()}
        return publish_artifact(root, destination, document, evidence)


# am[implements a-sleep-train-evaluate-1016@998fa2]
def evaluate(root: Path, artifact_id: str, *, base_dir: Path | None = None) -> dict[str, Any]:
    """Recompute sealed heldout predictions offline; this never spends another admission test."""
    artifact = validate_artifact(root, artifact_id)
    manifest = artifact.manifest
    evidence = artifact.model_dir.parent / "evidence"
    examples = _checked(_json(evidence / "reviews.json"))
    split = _json(evidence / "split.json")
    holdout = tuple(row for row in examples if _group(row) in split["holdout"])
    if set(split["train"]) & set(split["holdout"]):
        raise SleepError("Stored source split leaks across training and holdout")
    parent = manifest["parent"]
    if parent == manifest["base"]["identity"]:
        if base_dir is None:
            base_dir, configured = _base()
            if configured != manifest["base"]:
                raise SleepError("Replay requires the artifact's exact pinned base")
        _verify_base(base_dir, manifest["base"])
        champion_dir = base_dir
    else:
        champion_dir = validate_artifact(root, parent).model_dir
    config = TrainingConfig(**manifest["config"])
    champion = _scores(_load_model(champion_dir, manifest["instruction"]), holdout, config.batch_size)
    challenger = _scores(_load_model(artifact.model_dir, manifest["instruction"]), holdout, config.batch_size)
    stored = _json(evidence / "predictions.json")
    if stored != {"example_ids": [r.example_id for r in holdout], "champion": list(champion), "challenger": list(challenger)}:
        raise SleepError("Offline replay differs from the sealed evaluation predictions")
    report = paired_report(holdout, champion, challenger, attempt=manifest["test"]["attempt"],
                           fresh_groups=manifest["test"]["fresh_groups"],
                           weights_changed=manifest["test"]["weights_changed"])
    if report != manifest["test"]:
        raise SleepError("Recomputed paired report differs from the sealed evaluation")
    return {"artifact": artifact.identity, "replayed": True, "admission": asdict(admission(report))}


# train reads the incident domain's declaration within the limits its command line gives; the other
# commands read no domain and ask Jev nothing, so they take none.
# am[implements a-sleep-cli-docs-1016@05a457] am[implements a-dr-sr-tool-budgets-1018@e4d351]
def main(argv: list[str] | None = None) -> int:
    from .semantic_models import RERANKER

    parser = argparse.ArgumentParser(prog="python -m goal_chainer.semantic_sleep")
    parser.add_argument("--root", type=Path, default=artifact_root())
    parser.add_argument("--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import")
    importer.add_argument("jsonl", type=Path)
    importer.add_argument("--store", type=Path)
    trainer = commands.add_parser("train")
    trainer.add_argument("--store", type=Path)
    trainer.add_argument("--epochs", type=float, default=TrainingConfig.epochs)
    trainer.add_argument("--learning-rate", type=float, default=TrainingConfig.learning_rate)
    trainer.add_argument("--batch-size", type=int, default=TrainingConfig.batch_size)
    trainer.add_argument("--seed", type=int, default=TrainingConfig.seed)
    trainer.add_argument("--inference-budget", type=int, required=True,
                         help="maximum engine inferences for reading the domain's declaration")
    trainer.add_argument("--timeout-seconds", type=float, required=True,
                         help="wall-clock limit for reading the domain's declaration")
    for name in ("evaluate", "promote", "verify"):
        commands.add_parser(name).add_argument("artifact")
    commands.add_parser("status")
    rollback_parser = commands.add_parser("rollback")
    rollback_parser.add_argument("--expected-generation", required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    try:
        root = args.root.expanduser().absolute()
        if args.command == "import":
            rows = [_decode(line) for line in args.jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
            result = {"added": import_reviews(args.store or root / "reviewed.json", rows)}
        elif args.command == "train":
            from .runtime.budget import RunBudget
            from .semantic_reader import default_reader

            budget = RunBudget(inference_budget=args.inference_budget, timeout_seconds=args.timeout_seconds)
            artifact = train(args.store or root / "reviewed.json", root,
                             declaration=default_reader(budget=budget).declaration,
                             config=TrainingConfig(args.epochs, args.learning_rate, args.batch_size, args.seed))
            result = {"artifact": artifact.identity, "admission": artifact.manifest["admission"]}
        elif args.command == "evaluate":
            result = evaluate(root, args.artifact)
        elif args.command == "verify":
            result = {"artifact": validate_artifact(root, args.artifact).identity, "verified": True}
        elif args.command == "promote":
            result = asdict(promote(root, args.artifact, RERANKER.identity))
        elif args.command == "rollback":
            current = capture_active(root)
            if current is None or current.generation != args.expected_generation:
                raise SleepError("Rollback expected generation differs from ACTIVE")
            result = asdict(rollback(root, current, RERANKER.identity))
        else:
            current = resolve_active(root, RERANKER.identity, full_hash=True)
            result = {"identity": current.identity, "pointer": _pointer(current.pointer),
                      "reviewed_count": len(reviewed(root / "reviewed.json"))}
        print(canonical(result).decode("utf-8"))
        return 0
    except Exception as error:
        logger.debug("Sleep command failed", exc_info=True)
        print(canonical({"error": type(error).__name__, "message": str(error)}).decode("utf-8"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

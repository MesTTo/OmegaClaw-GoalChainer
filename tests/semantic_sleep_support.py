"""Purpose: construct synthetic admissible artifacts for serving integrity tests."""

from dataclasses import asdict
import math
from pathlib import Path

from goal_chainer import semantic_sleep as sleep

MODEL_FILES = {"config.json": b"{}", "tokenizer_config.json": b"{}",
               "model.safetensors": b"synthetic-weights"}


# am[verifies a-sleep-artifact-integrity-tests-1016@7cc8b5]
def base_pin():
    return {"identity": "base@test", "repo_id": "synthetic-test-fixture",
            "revision": "synthetic-test-fixture", "license": "synthetic-test-data",
            "files": {name: [len(data), sleep.digest(data)] for name, data in MODEL_FILES.items()}}


# am[verifies a-sleep-artifact-integrity-tests-1016@7cc8b5]
def paired_report(count=None, *, champion=0.0, challenger=1.0, old_brier=1.0, new_brier=0.0):
    report = {"attempt": 1, "groups": {}, "fresh_groups": [], "weights_changed": True}
    if count is None:
        alpha = sleep.admission(report).alpha
        # Unit improvement has a positive Hoeffding lower bound when n > 2 log(1/alpha).
        count = math.floor(2 * math.log(1 / alpha)) + 1
    report["groups"] = {
        sleep.digest(f"synthetic-independent-group-{index}".encode()): {
            "champion_rank": champion, "challenger_rank": challenger,
            "champion_brier": old_brier, "challenger_brier": new_brier,
        }
        for index in range(count)
    }
    report["fresh_groups"] = sorted(report["groups"])
    return report


# These synthetic metrics exercise admission plumbing, not model quality.
# am[verifies a-sleep-artifact-integrity-tests-1016@7cc8b5]
def admissible_metadata(parent_ref=None, parent="base@test"):
    return {
        "parent_ref": None if parent_ref is None else asdict(parent_ref),
        "parent": parent, "base": base_pin(), "test": paired_report(),
    }, {"policy.metta": sleep.POLICY.read_bytes(), **sleep.EVALUATOR_SOURCES}


# am[verifies a-sleep-artifact-integrity-tests-1016@7cc8b5]
def model_files(directory: Path, weights=b"synthetic-weights") -> Path:
    directory.mkdir()
    for name, data in {**MODEL_FILES, "model.safetensors": weights}.items():
        (directory / name).write_bytes(data)
    return directory

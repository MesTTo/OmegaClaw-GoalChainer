"""Purpose: keep sleep numeric refusals typed without starting a model or native policy."""

from dataclasses import replace
import math
from pathlib import Path
import sys

import pytest

from goal_chainer import semantic_sleep as sleep
from goal_chainer.domains.readings import ReadingDeclaration
from semantic_sleep_support import model_files, paired_report


# am[verifies a-integrate-sleep-number-refusal-1018@b7192f]
@pytest.mark.parametrize("value", [0, 1, 0.25, -0.0, math.nextafter(0.0, 1.0)])
def test_existing_unit_values_keep_their_float_value(value):
    actual = sleep._finite(value, "score", 0, 1)
    assert type(actual) is float and actual == float(value)
    assert math.copysign(1, actual) == math.copysign(1, float(value))


# am[verifies a-integrate-sleep-number-refusal-1018@b7192f]
@pytest.mark.parametrize("value", [True, False, None, "0.5", math.nan, math.inf, -math.inf, -1, 2])
def test_existing_invalid_unit_values_keep_their_sleep_error(value):
    with pytest.raises(sleep.SleepError, match=r"score must be finite in \[0, 1\]"):
        sleep._finite(value, "score", 0, 1)


# am[verifies a-integrate-sleep-number-refusal-1018@b7192f]
def test_integer_interval_comparison_keeps_precision_before_rounding():
    boundary = 2 ** sys.float_info.mant_dig
    assert float(boundary + 1) == float(boundary)
    assert sleep._finite(boundary, "score", 0, boundary) == float(boundary)
    with pytest.raises(sleep.SleepError):
        sleep._finite(boundary + 1, "score", 0, boundary)


# am[verifies a-integrate-sleep-number-refusal-1018@b7192f]
@pytest.mark.parametrize("changes", [
    {}, {"epochs": 2}, {"epochs": math.nextafter(0.0, 1.0)},
    {"epochs": sys.float_info.max}, {"epochs": int(sys.float_info.max) + 1},
    {"learning_rate": 1}, {"learning_rate": math.nextafter(0.0, 1.0)},
    {"batch_size": 10 ** 400}, {"seed": 10 ** 400},
])
def test_existing_training_numbers_remain_accepted(changes):
    sleep.TrainingConfig(**changes).validate()


# am[verifies a-integrate-sleep-number-refusal-1018@b7192f]
@pytest.mark.parametrize("changes", [
    {"epochs": 0}, {"epochs": -1}, {"epochs": math.inf}, {"epochs": math.nan},
    {"epochs": True}, {"epochs": "1"}, {"learning_rate": 0},
    {"learning_rate": -1}, {"learning_rate": math.nan}, {"learning_rate": True},
    {"batch_size": 0}, {"batch_size": 1.0}, {"batch_size": True},
    {"seed": -1}, {"seed": 0.0}, {"seed": True},
])
def test_existing_invalid_training_numbers_keep_their_sleep_error(changes):
    with pytest.raises(sleep.SleepError):
        sleep.TrainingConfig(**changes).validate()


# am[verifies a-sleep-number-reproduce-1018@26ad64]
def test_overflowing_public_group_score_is_a_sleep_error():
    text = "Reviewed passage."
    row = sleep.ReviewedExample("example", "question", "Question?", text, 1,
                               "curator", "2026-10-18T00:00:00+00:00", "group", "source",
                               text, sleep.digest(text.encode()))
    with pytest.raises(sleep.SleepError, match="prediction must be finite"):
        sleep.group_metrics((row,), (10 ** 400,))


# am[verifies a-sleep-number-reproduce-1018@26ad64]
@pytest.mark.parametrize("field", ["champion_rank", "challenger_rank", "champion_brier", "challenger_brier"])
def test_overflowing_public_admission_metric_is_a_sleep_error(field):
    report = paired_report(count=1)
    report["groups"][report["fresh_groups"][0]][field] = 10 ** 400
    with pytest.raises(sleep.SleepError, match=field + " must be finite"):
        sleep.admission(report)


# am[verifies a-sleep-number-reproduce-1018@26ad64]
@pytest.mark.parametrize("field, message", [("epochs", "epochs must be finite and positive"),
                                          ("learning_rate", "learning_rate must be finite")])
def test_overflowing_training_config_is_refused_before_training(tmp_path, field, message):
    declaration = ReadingDeclaration("numbers", "model", "en", "Read.", (), (), (),
                                     "Rank.", Path("numbers.metta"))
    config = replace(sleep.TrainingConfig(), **{field: 10 ** 400})
    with pytest.raises(sleep.SleepError, match=message):
        sleep.train(tmp_path / "reviews.json", tmp_path / "registry",
                    declaration=declaration, config=config)


# am[verifies a-sleep-number-reproduce-1018@26ad64]
def test_overflowing_sealed_promotion_metric_is_a_sleep_error(tmp_path):
    root = tmp_path / "registry"
    report = paired_report(count=1)
    report["groups"][report["fresh_groups"][0]]["champion_rank"] = 10 ** 400
    artifact = sleep.publish_artifact(root, model_files(tmp_path / "model"),
                                     {"test": report}, {"policy.metta": sleep.POLICY.read_bytes(),
                                                        **sleep.EVALUATOR_SOURCES})
    with pytest.raises(sleep.SleepError, match="champion_rank must be finite"):
        sleep.promote(root, artifact.identity, "base@test")
    assert sleep.capture_active(root) is None


# am[verifies a-sleep-number-verify-1018@bb102f]
def test_shared_numeric_implementation_remains_in_the_evaluator_seal():
    from goal_chainer.runtime import numbers

    assert sleep.EVALUATOR_SOURCES["numbers.py"] == Path(numbers.__file__).read_bytes()


# A correctly hashed artifact still cannot replace or omit any evaluated implementation source.
# am[verifies a-sleep-number-verify-1018@bb102f]
@pytest.mark.parametrize("source", ["evaluation.py", "artifacts.py", "numbers.py"])
@pytest.mark.parametrize("mutation", ["changed", "missing"])
def test_exact_promotion_source_guards_stay_in_force(tmp_path, source, mutation):
    root = tmp_path / "registry"
    # Invalid metrics keep every failure path before native policy even if a source guard breaks.
    report = paired_report(count=1)
    report["groups"][report["fresh_groups"][0]]["champion_rank"] = 10 ** 400
    evidence = {"policy.metta": sleep.POLICY.read_bytes(), **sleep.EVALUATOR_SOURCES}
    if mutation == "changed":
        evidence[source] += b"\n# changed implementation\n"
        message = "different evaluator implementation"
    else:
        del evidence[source]
        message = "Missing regular file"
    artifact = sleep.publish_artifact(root, model_files(tmp_path / "model"), {"test": report}, evidence)
    with pytest.raises(sleep.SleepError, match=message):
        sleep.promote(root, artifact.identity, "base@test")
    assert sleep.capture_active(root) is None

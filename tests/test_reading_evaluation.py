"""Purpose: hold the reading parity corpus well formed and covered, check the evaluation's interval
and score functions against known values and SciPy, and replay the evaluation offline against the
committed report, so the report is regenerated from its source and compared."""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st
from scipy.stats import binomtest

from goal_chainer.semantic_evaluation import (
    CORPUS_PATH,
    bootstrap,
    brier,
    evaluate,
    load_corpus,
    main,
    wilson,
)
from goal_chainer.errors import InvalidInputError
from reading_support import INCIDENT as DECLARATION, INCIDENT_FILE
from request_support import CLI_LIMITS, budget

REPORT = CORPUS_PATH.parent / "report.json"


# am[verifies a-corpus-report-test-1017@b44fc7]
def test_the_corpus_labels_every_proposition_and_covers_each_decided_answer():
    corpus = load_corpus(DECLARATION)

    assert len(corpus.texts) == 40
    for proposition in DECLARATION.propositions:
        labels = [text.labels[proposition.id].answer for text in corpus.texts]
        for answer in DECLARATION.answers:
            assert labels.count(answer) >= 3, (proposition.id, answer)
    for choice in DECLARATION.choices:
        assert all(choice.id in text.choices for text in corpus.texts)


# am[verifies a-corpus-report-test-1017@b44fc7] am[verifies a-dr-evaluation-generic-1018@120a4c]
@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda text: text["labels"].update({"raw-logs": ["probably", "x"]}), "names no option"),
        (lambda text: text["labels"].update({"raw-logs": ["supported", " "]}), "no justification"),
        (lambda text: text["labels"].pop("raw-logs"), "every reading proposition"),
        (lambda text: text.update({"mood": ["question", "x"]}), "names no option"),
        (lambda text: text.pop("mood"), "an answer and its justification"),
    ],
)
def test_a_malformed_corpus_is_refused(tmp_path, change, message):
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    change(data["texts"][0])
    broken = tmp_path / "corpus.json"
    broken.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(InvalidInputError, match=message):
        load_corpus(DECLARATION, broken)


# am[verifies a-corpus-report-test-1017@b44fc7]
@given(trials=st.integers(min_value=1, max_value=200), data=st.data())
def test_the_wilson_interval_is_scipys(trials, data):
    successes = data.draw(st.integers(min_value=0, max_value=trials))
    expected = binomtest(successes, trials).proportion_ci(confidence_level=0.95, method="wilson")

    low, high = wilson(successes, trials)

    assert low == pytest.approx(expected.low, abs=1e-12)
    assert high == pytest.approx(expected.high, abs=1e-12)


# am[verifies a-corpus-report-test-1017@b44fc7]
def test_the_brier_score_runs_from_a_certain_right_answer_to_a_certain_wrong_one():
    options = ["supported", "contradicted", "unknown"]

    assert brier({"supported": 1.0, "contradicted": 0.0, "unknown": 0.0}, "supported", options) == 0
    assert brier({"supported": 0.0, "contradicted": 1.0, "unknown": 0.0}, "supported", options) == 2
    assert brier({"supported": 0.5, "contradicted": 0.5, "unknown": 0.0}, "supported", options) == 0.5


# am[verifies a-corpus-report-test-1017@b44fc7]
def test_the_bootstrap_is_seeded_and_tight_around_a_constant():
    def mean(sample):
        return sum(sample) / len(sample)

    values = [0.0, 1.0] * 20

    assert bootstrap([0.7] * 10, mean) == (pytest.approx(0.7), pytest.approx(0.7))
    assert bootstrap(values, mean) == bootstrap(values, mean)
    low, high = bootstrap(values, mean)
    assert low < 0.5 < high


# One evaluation of the whole corpus for the module's tests: each text is read once, asking Jev in
# a capture and replaying the committed answers otherwise, and grounding dominates a read's time.
# am[verifies a-corpus-report-test-1017@b44fc7]
@pytest.fixture(scope="module")
def evaluated():
    corpus = load_corpus(DECLARATION)
    return corpus, evaluate(corpus, DECLARATION, budget=budget())


# Every text was read and every label counted once, scored or abstained.
# am[verifies a-corpus-report-test-1017@b44fc7] am[verifies a-jev-reading-parity-corpus-1016@9bcdf8]
def test_every_corpus_text_reads(evaluated):
    corpus, report = evaluated

    for target, scores in report["targets"].items():
        assert scores["n"] + scores["abstained"] == len(corpus.texts), target


# The committed report is what the evaluation gives now, so it cannot drift from the reader.
# am[verifies a-corpus-report-test-1017@b44fc7]
def test_the_committed_report_regenerates_offline(evaluated):
    _, report = evaluated

    assert report == json.loads(REPORT.read_text(encoding="utf-8"))


# The command scores the declaration of the packaged incident domain, or of the domain file it is
# given, under the limits its command line gives, which it refuses to run without; a domain file
# with no reading section has nothing to score. One committed text keeps it to one replayed read.
# am[verifies a-dr-sr-tool-budgets-1018@e4d351] am[verifies a-dr-evaluation-generic-1018@120a4c]
def test_the_command_scores_a_domain_s_declaration_under_its_own_limits(tmp_path, capsys):
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    data["texts"] = data["texts"][:1]
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps(data), encoding="utf-8")
    packaged, supplied = tmp_path / "packaged.json", tmp_path / "supplied.json"

    with pytest.raises(SystemExit) as refused:
        main(["--corpus", str(corpus)])
    assert refused.value.code == 2 and "--inference-budget" in capsys.readouterr().err
    assert main(["--corpus", str(corpus), "--json", str(packaged), *CLI_LIMITS]) == 0
    assert main(["--corpus", str(corpus), "--domain-file", str(INCIDENT_FILE), "--json", str(supplied),
                 *CLI_LIMITS]) == 0

    reports = [json.loads(path.read_text(encoding="utf-8")) for path in (packaged, supplied)]
    assert reports[0] == reports[1]
    assert reports[0]["declaration"] == {"domain": "incident", "digest": DECLARATION.digest}
    assert reports[0]["corpus"]["texts"] == 1
    with pytest.raises(InvalidInputError, match="declares no reading section"):
        main(["--corpus", str(corpus), "--domain-file", str(INCIDENT_FILE.with_name("task_control.metta")),
              *CLI_LIMITS])

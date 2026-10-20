"""Purpose: check the shared vocabulary as the relevance policy loads it: Python reads the classes and bands the engine answers, each class's tier and whether it establishes, a validity's last current instant, the justification row each reading state has or lacks, membership that answers once however often an item occurs, and that the vocabulary beside the packaged domains is not listed as one."""

from __future__ import annotations

from importlib import resources
import subprocess
import sys
from typing import Any

import pytest

from goal_chainer.domains import loader
from goal_chainer.domains.loader import VOCABULARY_FILE, packaged_domain_names, vocabulary
from goal_chainer.domains.model import DomainError
from goal_chainer.relevance.policy import constant, items, symbol, term

from relevance_support import helper_answers, helper_call

# The tiers the justification kernel relies on (c-rel-rr-kernel-needs-1018).
TIERS = {"measured": 1, "deterministic": 1, "human-asserted": 1, "receipt-calibrated": 0, "model-proposed": 0}


# Each call is first in a fresh interpreter, so another constructor cannot warm its vocabulary.
# am[verifies a-integrate-vocab-no-engine-regression-1019@0ed119]
@pytest.mark.parametrize("expression", [
    "vocabulary()",
    "SignalReading('s', SignalState.DETECTED, 'test', estimator='measured')",
    "Quantity('cost', 'neutral', 'measured')",
    "_observation(dict(about='achieves', target='s', outcome='confirmed', estimator='measured', source='test'), 0)",
])
def test_vocabulary_consumers_need_no_engine(expression: str) -> None:
    script = f"""
import sys
sys.modules['metta'] = None
from goal_chainer.domains.loader import vocabulary
from goal_chainer.relevance.signals import SignalReading, SignalState
from goal_chainer.relevance.quantity import Quantity
from goal_chainer.relevance.receipt import _observation
{expression}
assert sys.modules['metta'] is None
"""
    result = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# am[verifies a-integrate-vocab-no-engine-regression-1019@0ed119]
def test_vocabulary_tables_keep_comments_and_escaped_strings(tmp_path, monkeypatch) -> None:
    source = tmp_path / "vocabulary.metta"
    source.write_text('(= (gc-bands) ("a; b" ; not a band\n "c\\nd"))\n'
                      '(= (gc-estimator-class-table) ((Class "x\\\"y" 1)))\n', encoding="utf-8")
    vocabulary.cache_clear()
    try:
        with monkeypatch.context() as changed:
            changed.setattr(loader, "VOCABULARY_FILE", source)
            assert vocabulary() == loader.Vocabulary(('x"y',), ("a; b", "c\nd"))
    finally:
        vocabulary.cache_clear()


# am[verifies a-integrate-vocab-no-engine-regression-1019@0ed119]
@pytest.mark.parametrize("source, message", [
    ('(= (gc-bands) ())', "defines no"),
    ('(= (gc-bands) (', "cannot read"),
    ('!(gc-bands)', "must only declare"),
    ('(= (gc-bands) (neutral))\n(= (gc-estimator-class-table) ())', "string literals"),
    ('(= (gc-bands) ())\n(= (gc-estimator-class-table) ((Class measured 1)))', "Class"),
    ('(= (gc-bands) ())\n(= (gc-estimator-class-table) ("measured"))', "Class"),
])
def test_malformed_vocabulary_is_a_domain_error(tmp_path, monkeypatch, source: str, message: str) -> None:
    path = tmp_path / "vocabulary.metta"
    path.write_text(source, encoding="utf-8")
    vocabulary.cache_clear()
    try:
        with monkeypatch.context() as changed:
            changed.setattr(loader, "VOCABULARY_FILE", path)
            with pytest.raises(DomainError, match=message):
                vocabulary()
    finally:
        vocabulary.cache_clear()


# am[verifies a-rel-rr-shared-module-1018@13aee9] am[verifies a-rel-nd-vocabulary-down-1018@6e6c8d]
def test_python_reads_the_classes_and_bands_the_engine_answers() -> None:
    classes, bands = vocabulary().classes, vocabulary().bands
    assert helper_call("gc-estimator-classes") == classes
    assert helper_call("gc-bands") == bands
    assert sorted(classes) == sorted(TIERS)
    assert bands[len(bands) // 2] == "neutral"


# The kernel ranks a reading by its tier and reads establishing only from gc-establishes, so every
# class that establishes must rank above every class that does not.
# am[verifies a-rel-rr-shared-module-1018@13aee9] am[verifies c-rel-rr-kernel-needs-1018@308ea7]
def test_each_class_has_its_tier_and_establishes_exactly_when_above_the_lowest_tier() -> None:
    tiers = {name: helper_call("gc-estimator-tier", name) for name in vocabulary().classes}
    establishing = {name: helper_call("gc-establishes", name) for name in vocabulary().classes}

    assert tiers == TIERS
    assert establishing == {name: tier > min(tiers.values()) for name, tier in tiers.items()}
    assert min(tiers[name] for name in tiers if establishing[name]) > max(
        tiers[name] for name in tiers if not establishing[name]
    )


# am[verifies a-rel-rr-shared-module-1018@13aee9]
def test_a_class_outside_the_table_has_no_tier() -> None:
    assert helper_answers("gc-estimator-tier", "guessed") == []


# am[verifies a-rel-rr-shared-module-1018@13aee9]
@pytest.mark.parametrize(
    ("as_of", "until", "expired"),
    [(9, 10, False), (10, 10, False), (11, 10, True), (10**18, None, False)],
)
def test_a_reading_is_current_through_the_instant_it_is_valid_until(as_of: int, until: int | None, expired: bool) -> None:
    validity = constant("Forever") if until is None else term("Until", until)

    assert helper_call("gc-reading-expired", as_of, validity) is expired


# The packaged domains are the files of domains/data/, so the shared vocabulary beside the loader
# is none of them.
# A row as plain values, each symbol by its name, so it compares with a tuple literal.
# am[related a-rel-pj-reading-row-1018@03ad71]
def named(value: Any) -> Any:
    if isinstance(value, tuple):
        return tuple(named(item) for item in value)
    return value if isinstance(value, (bool, int, float, str)) else symbol(value)


# A detected reading claims its signal and a refuted one the negation, from an observation named by
# the caller's ID; an unknown or off-vocabulary reading has no row, so a call on one answers
# nothing and the list form drops it, never reading silence as a refutation.
# am[verifies a-rel-pj-reading-row-1018@03ad71] am[verifies c-rel-pj-row-rule-unknown-refutes-1018@82c7eb]
def test_a_definite_reading_has_one_row_and_any_other_reading_none() -> None:
    detected = term("Reading", "s", "detected", "measured", constant("Forever"), 3)
    refuted = term("Reading", "s", "refuted", "model-proposed", term("Until", 9), "sha256:ab")
    unknown = term("Reading", "s", "unknown", constant("None"), constant("Forever"), 4)
    off_vocabulary = term("Reading", "s", "maybe", "measured", constant("Forever"), 5)
    rows = (
        ("From", ("Signal", "s"), ("Observation", ("Reading", 3, "measured", "Forever"))),
        ("From", ("Not", ("Signal", "s")),
         ("Observation", ("Reading", "sha256:ab", "model-proposed", ("Until", 9)))),
    )

    assert named(helper_call("gc-reading-row", detected)) == rows[0]
    assert named(helper_call("gc-reading-row", refuted)) == rows[1]
    assert [helper_call("gc-reading-definite", reading)
            for reading in (detected, refuted, unknown, off_vocabulary)] == [True, True, False, False]
    assert named(helper_call("gc-reading-rows", items([unknown, detected, off_vocabulary, refuted]))) == rows
    assert helper_call("gc-reading-rows", items([])) == ()
    for reading in (unknown, off_vocabulary):
        assert helper_answers("gc-reading-row", reading) == []


# is-member answers once per occurrence, so a rule branching on it over a list holding an item
# twice answers twice; the shared membership answers once, and so does every rule built on it,
# such as a candidate's mode test on a candidate whose modes repeat one.
# am[verifies a-rel-member-once-1018@45ebae] am[verifies c-ev-is-member-per-occurrence-1017@a98644]
def test_membership_answers_once_however_often_an_item_occurs() -> None:
    twice = items(["a", "b", "a"])
    obliged = term("Candidate", "act", "advisory", items([constant("O"), constant("O")]), 0, items([]), items([]), items([]))

    assert helper_answers("is-member", "a", twice) == [True, True]
    assert helper_call("gc-has", twice, "a") is True
    assert helper_call("gc-has", twice, "c") is False
    assert [helper_call("gc-count", twice, item) for item in ("a", "b", "c")] == [2, 1, 0]
    assert helper_call("gc-relevance-has-mode", obliged, constant("O")) is True


# Every section's tables read their facts through the vocabulary: the facts of one head, in order,
# and how many of them hold one value at one place.
# am[verifies a-rel-facts-helpers-one-home-1018@ff4910]
def test_the_facts_of_one_head_and_their_count_at_a_place() -> None:
    facts = items([term("Rank", "a", "1"), term("Tier", "x", "a"), term("Rank", "b", "1"), term("Rank", "c", "2")])

    assert symbol(helper_call("gc-of", facts, constant("Tier"))[0][0]) == "Tier"
    assert [fact[1] for fact in helper_call("gc-of", facts, constant("Rank"))] == ["a", "b", "c"]
    assert helper_call("gc-of", facts, constant("Ceiling")) == ()
    assert [helper_call("gc-count-at", facts, constant("Rank"), 2, rank) for rank in ("1", "2", "3")] == [2, 1, 0]


# am[verifies a-rel-nd-vocabulary-down-1018@6e6c8d] am[verifies a-rel-neutral-domain-1018@535314]
def test_the_packaged_domains_are_the_files_of_the_data_directory() -> None:
    data = resources.files("goal_chainer") / "domains" / "data"
    assert (resources.files("goal_chainer") / "domains" / VOCABULARY_FILE.name).is_file()
    assert packaged_domain_names() == tuple(
        sorted(entry.name.removesuffix(".metta").replace("_", "-") for entry in data.iterdir() if entry.name.endswith(".metta"))
    )
    assert VOCABULARY_FILE.stem not in packaged_domain_names()

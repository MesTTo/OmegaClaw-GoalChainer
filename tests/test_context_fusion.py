"""Purpose: test, in-process on scripted readings, how the reading policy believes a context: each
source's readings of a proposition once, from the mean of the evidence they assert, under the
source's one trust, as SnarsSession.belief of the proposition's statement reads it."""

from __future__ import annotations

import pytest

from request_support import budget as request_budget
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.snars_engine import run_snars_batch
from goal_chainer.snars_program import ProgramFragments, SnarsBatch, SnarsProgramBuilder, TextIngestion
from goal_chainer.snars_reasoner import SnarsSession
from reading_support import INCIDENT, incident_reader, reading_statement

# The options the policy believes a batch's one group with, from the units its facts assert.
OPTIONS = (
    "(gc group-options (msort (collapse (match &self (gc-reading $s $t $id $a $p $prov)"
    " (gc reading-unit $s $t $id $a $p $prov)))))"
)


# One reading of sensitive-data as a gc-reading fact.
# am[verifies a-ev-wt-tests-context-1017@16cb26]
def _fact(answer: str, p: float, key: str, *, source: str = "ctx", trust: float = 1.0) -> str:
    return (f'(gc-reading "{source}" {trust} sensitive-data {answer} {p} '
            f'(provenance "jev-1.13.0" "{key}" "a passage"))')


# The options one group of facts is believed with, as the in-process engine prints them. Each run
# takes its own budget, so no deadline starts when pytest imports the module.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[implements a-rt-fusion-budget-per-run-1018@3d8181]
# am[addresses i-rt-fusion-module-budget-1018@5cc972]
def _options(*facts: str) -> str:
    (line,) = run_snars_batch(
        SnarsBatch(tuple(facts), frozenset({"policy"}), OPTIONS, INCIDENT),
        budget=request_budget(),
    ).output_lines
    return line


# Hands each text its scripted facts instead of reading it; the batches carry the incident
# declaration those facts are read against.
# am[verifies a-ev-wt-tests-context-1017@16cb26]
class _Scripted(SnarsProgramBuilder):
    def __init__(self, script: dict[str, tuple[str, ...]]) -> None:
        super().__init__(incident_reader())
        self.script = script

    def text_ingestion(self, text: str, *, source: str, trust: float, budget: RunBudget) -> TextIngestion:
        return TextIngestion(revision="scripted", fragments=ProgramFragments(facts=self.script[text]))


# What SNARS believes of sensitive-data after a session reads the texts, each with its scripted
# facts.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ie-s7-tests-1018@5c72ce]
def _sensitive(script: dict[str, tuple[str, ...]], *texts: str):
    session = SnarsSession.ephemeral(budget=request_budget(), reader=incident_reader())
    session.builder = _Scripted(script)
    with session:
        for text in texts:
            session.ingest_text(text, source="scripted")
        return session.belief(reading_statement("sensitive-data"))


LONE = (
    '((evidence 7.2 0.0) (source "ctx") (trust 1.0) '
    '(reading sensitive-data (provenance "jev-1.13.0" "k1" "a passage")) (estimator model-proposed))'
)


# A lone reading is believed with the options one reading always had, so a request read alone
# believes what it did before groups.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ev-wt-context-mean-1017@46162f]
def test_a_lone_reading_is_believed_with_the_options_one_reading_always_had() -> None:
    assert _options(_fact("supported", 0.9, "k1")) == LONE


# A none reading asserts nothing, so it neither adds to the context's evidence nor dilutes it.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ev-wt-context-mean-1017@46162f]
def test_a_none_reading_neither_adds_nor_dilutes() -> None:
    assert _options(_fact("supported", 0.9, "k1"), _fact("unknown", 0.7, "k2")) == LONE


# Each count's mean over the asserted units: 7.2 for and 6.4 against give (3.6, 3.2), with every
# member's reading clause.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ev-wt-context-mean-1017@46162f]
def test_a_supported_and_a_contradicted_reading_give_each_count_its_mean() -> None:
    options = _options(_fact("supported", 0.9, "k1"), _fact("contradicted", 0.8, "k2"))

    assert options.startswith('((evidence 3.6 3.2) (source "ctx") (trust 1.0) ')
    assert '"k1"' in options and '"k2"' in options


# Identical readings are one reading however many texts restate it: the mean is exact for every
# group size, where a plain sum over n would drift above the strongest unit.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ev-wt-context-mean-1017@46162f]
def test_identical_readings_believe_the_lone_reading_exactly_for_every_group_size() -> None:
    for size in range(1, 21):
        options = _options(*(_fact("supported", 0.97, f"k{index}") for index in range(size)))

        assert options.startswith("((evidence 7.76 0.0) "), size


# In real arithmetic a group's two counts total no more than its strongest unit. In floating point
# each count is averaged on its own, so nine contradicted readings and one supported at p 0.6 total
# 4.8 only up to rounding, and nothing clips that (c-integrate-context-mean-roundoff-1017).
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ev-wt-context-mean-1017@46162f]
def test_a_mixed_group_totals_its_strongest_unit_up_to_rounding() -> None:
    options = _options(*(_fact("contradicted", 0.6, f"k{index}") for index in range(9)), _fact("supported", 0.6, "k9"))
    positive, negative = (float(count) for count in options.split("(evidence ")[1].split(")")[0].split())

    assert positive == pytest.approx(0.48, rel=0, abs=1e-12)
    assert negative == pytest.approx(4.32, rel=0, abs=1e-12)
    assert positive + negative == pytest.approx(8.0 * 0.6, rel=0, abs=1e-12)


# The order the facts arrive in changes neither the evidence nor the clauses.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ev-wt-context-mean-1017@46162f]
def test_the_order_of_the_facts_changes_nothing() -> None:
    facts = (_fact("supported", 0.9, "k1"), _fact("contradicted", 0.8, "k2"), _fact("supported", 0.55, "k3"))

    assert _options(*facts) == _options(*reversed(facts)) == _options(facts[1], facts[2], facts[0])


# A group keeps its source's one trust exactly, never an average of it.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ev-wt-context-mean-1017@46162f]
def test_a_group_keeps_its_one_trust_exactly() -> None:
    options = _options(*(_fact("supported", 0.9, f"k{index}", trust=0.7) for index in range(3)))

    assert '(source "ctx") (trust 0.7) ' in options


# Two sources are two bodies of evidence and still add, each with its receipt.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ev-wt-context-mean-1017@46162f]
# am[verifies a-ie-s7-tests-1018@5c72ce]
def test_two_sources_still_add() -> None:
    script = {"a": (_fact("supported", 0.9, "k1", source="s1"),), "b": (_fact("supported", 0.9, "k2", source="s2"),)}

    sensitive = _sensitive(script, "a", "b")

    assert sensitive.evidence.positive == pytest.approx(14.4)
    assert sorted(receipt.source for receipt in sensitive.receipts) == ["s1", "s2"]


# A paraphrase read into a context and reading as the request does changes nothing: the context is
# believed as the request alone.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ev-wt-context-mean-1017@46162f]
# am[verifies a-ie-s7-tests-1018@5c72ce]
def test_a_paraphrase_that_reads_alike_changes_nothing() -> None:
    script = {"request": (_fact("supported", 0.9, "k1"),), "paraphrase": (_fact("supported", 0.9, "k2"),)}

    assert _sensitive(script, "request", "paraphrase") == _sensitive(script, "request")


# Readings that assert nothing believe nothing, alone or as a group, with no division by zero.
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ev-wt-context-mean-1017@46162f]
# am[verifies a-ie-s7-tests-1018@5c72ce]
def test_readings_that_assert_nothing_believe_nothing() -> None:
    script = {"lone": (_fact("unknown", 0.7, "k1"),), "group": (_fact("unknown", 0.7, "k2"), _fact("unknown", 0.6, "k3"))}

    for texts in (("lone",), ("lone", "group")):
        sensitive = _sensitive(script, *texts)

        assert (sensitive.evidence.positive, sensitive.evidence.negative) == (0.0, 0.0)
        assert sensitive.receipts == ()

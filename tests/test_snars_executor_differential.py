"""Purpose: verify the in-process SNARS executor across every operation a session offers against
the records PeTTa answered for the same scripted session before PeTTa was retired, kept in
tests/data/snars-executor-petta.json: each batch's records equal PeTTa's up to the protocol's wall
clock, fresh variable names and boolean spelling, with the guard goal's new MeTTa notation
explicitly checked against its old Prolog spelling; replayed in a seeded permutation in the same
process, every batch answers as it did the first time; and two sessions on one store, each reading
its own text, believe only what they read."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from request_support import budget as request_budget
from snars_differential import clock_fields, equal, records, tree

from goal_chainer.runtime.budget import RunBudget
from goal_chainer.snars_engine import run_snars_batch
from goal_chainer.snars_models import Evidence, EvidenceCounts
from goal_chainer.snars_program import PROTOCOL_PATH, ProgramFragments, SnarsProgramBuilder, TextIngestion
from goal_chainer.snars_reasoner import SnarsSession, execute_in_process
from reading_support import incident_reader, reading_statement

CLOCKS = clock_fields(PROTOCOL_PATH.read_text(encoding="utf-8"))
# PeTTa's records for every batch _script runs, recorded once with the in-process engine agreeing on
# each; its provenance names the PeTTa and GoalChainer revisions and the SNARS library they ran.
# am[verifies a-rt-rp-snars-oracle-1018@b5a59d]
ORACLE = json.loads((Path(__file__).parent / "data" / "snars-executor-petta.json").read_text(encoding="utf-8"))
REQUEST = "goalchainer:request"
STATEMENT = '(sn p so "is" ((arg s (sn c "alpha")) (arg o (sn c "beta"))))'
PATTERN = '(sn p so "is" ((arg s (sn c "alpha")) (arg o $what)))'
HYPOTHESIS = '(sn p so "is" ((arg s (sn c "beta")) (arg o (sn c "gamma"))))'
QUERY = '(sn p so "is" ((arg s (sn c "alpha")) (arg o (sn c "gamma"))))'


# One hand-written reading as a gc-reading fact, so the engine reads exactly these inputs.
# am[verifies a-rt-snars-differential-tests-1017@7b8936]
def _reading(source: str, reading_id: str, answer: str, p: float) -> str:
    return (
        f'(gc-reading "{source}" 1.0 {reading_id} {answer} {p} '
        f'(provenance "jev-1.13.0" "differential-{reading_id}" "a passage"))'
    )


# Reading a text hands back its scripted facts instead of asking a reader; the batches carry the
# incident declaration those facts are read against.
# am[verifies a-rt-snars-differential-tests-1017@7b8936]
class _Builder(SnarsProgramBuilder):
    def __init__(self, script: dict[str, tuple[str, ...]]) -> None:
        super().__init__(incident_reader())
        self.script = script

    def text_ingestion(self, text: str, *, source: str, trust: float, budget: RunBudget) -> TextIngestion:
        return TextIngestion(revision="differential", fragments=ProgramFragments(facts=self.script[text]))


# Answers each batch in-process for the session, keeping each batch and its answer.
# am[verifies a-rt-snars-differential-tests-1017@7b8936]
class _Recording:
    def __init__(self) -> None:
        self.runs: list[tuple[object, tuple[str, ...]]] = []

    def __call__(self, batch, budget):
        lines = tuple(execute_in_process(batch, budget))
        self.runs.append((batch, lines))
        return lines


# am[verifies a-rt-snars-differential-tests-1017@7b8936]
def _records(lines) -> list[str]:
    return records("\n".join(lines))


# Three operations give no rate, so the records also hold what SNARS applies to a rate not given,
# and a second text read into the request's context makes every later policy batch believe a group
# of two readings, so they hold the context's mean too, which the belief of sensitive-data's
# statement reads.
# am[verifies a-rt-snars-differential-tests-1017@7b8936] am[verifies a-ev-br-tests-1017@bf0a6d]
# am[verifies a-ev-wt-tests-context-1017@16cb26] am[verifies a-ie-s7-tests-1018@5c72ce]
def _script(session: SnarsSession) -> None:
    session.ingest_text("the request", source=REQUEST)
    session.ingest_text("a memory", source=REQUEST)
    session.believe(STATEMENT, evidence=EvidenceCounts(2.0, 1.0, 0.5), source="differential", occurrence=1.0)
    session.believe(STATEMENT, evidence=Evidence(2.0, 1.0), source="differential-default")
    session.belief(STATEMENT)
    session.ask(PATTERN)
    session.prove(STATEMENT)
    session.explain(STATEMENT)
    session.discover(PATTERN)
    session.register_goal(STATEMENT, owner="differential", kind="individual", desire=0.8, required=True,
                          source="differential")
    session.subgoals(STATEMENT)
    session.what_if(HYPOTHESIS, QUERY)
    session.temporal(STATEMENT, now=2.0)
    session.record_outcome(STATEMENT, evidence=EvidenceCounts(1.0, 0.0, 0.5), source="goalchainer:execution",
                           observation_id="differential-1")
    session.record_outcome(STATEMENT, evidence=Evidence(1.0, 0.0), source="goalchainer:execution",
                           observation_id="differential-2")
    session.trust()
    session.mine(2)
    session.inspect()
    session.truth(STATEMENT)
    session.control(1)
    session.structural()
    session.transform("marginal", STATEMENT, base_rate=0.7)
    session.transform("marginal", STATEMENT)
    session.transform("disjunction", STATEMENT, other_statement=STATEMENT)
    session.compiled_prove(STATEMENT)
    # am[verifies a-integrate-guard-metta-gate-1019@1bf9e1]
    session.guard("(safe redacted)", rules=("(safe redacted)",))
    session.belief(reading_statement("sensitive-data"))


# Every operation, each with its own optional features, answers as PeTTa answered it; then the same
# batches in another order in this one process each answer as they did first, so no batch kept
# anything from another.
# am[verifies a-rt-snars-differential-tests-1017@7b8936] am[verifies a-rt-snars-batch-speculative-1017@451056]
# am[verifies a-rt-snars-worlds-by-includes-1017@54c05f] am[verifies a-rt-rp-snars-oracle-1018@b5a59d]
# am[verifies a-ie-s2c-scalar-tests-proofs-1018@5a0031]
def test_every_operation_answers_as_petta_answered_it_in_any_order() -> None:
    engines = _Recording()
    session = SnarsSession.ephemeral(execute=engines, budget=request_budget(), reader=incident_reader())
    session.builder = _Builder({"the request": (
        _reading(REQUEST, "sensitive-data", "supported", 0.9),
        _reading(REQUEST, "public-data", "contradicted", 0.8),
        _reading(REQUEST, "coordination-needed", "supported", 0.7),
    ), "a memory": (
        _reading(REQUEST, "sensitive-data", "contradicted", 0.6),
        _reading(REQUEST, "public-data", "unknown", 0.5),
    )})
    with session:
        _script(session)

    assert {frozenset(batch.includes) for batch, _ in engines.runs} == {
        frozenset({"policy"}), frozenset({"policy", "guard"})}
    assert [sorted(batch.includes) for batch, _ in engines.runs] == [row["includes"] for row in ORACLE["batches"]]
    for (batch, lines), row in zip(engines.runs, ORACLE["batches"], strict=True):
        assert len(_records(lines)) == 1, batch.directive
        expected = row["records"]
        # Preserve the captured oracle; only the guard's echoed notation changed.
        # am[verifies a-integrate-guard-metta-gate-1019@1bf9e1]
        if tree(expected[0])[1] == "guard":
            assert tree(expected[0])[3][1] == ["goal", '"safe(redacted)"']
            assert tree(_records(lines)[0])[3][1] == ["goal", ["safe", "redacted"]]
            expected = [expected[0].replace('(goal "safe(redacted)")', '(goal (safe redacted))')]
        assert equal(expected, _records(lines), CLOCKS), batch.directive

    order = list(range(len(engines.runs)))
    random.Random(1017).shuffle(order)
    for index in order:
        batch, lines = engines.runs[index]
        again = run_snars_batch(batch, budget=RunBudget(inference_budget=None, timeout_seconds=900))
        assert equal(_records(lines), _records(again.output_lines), CLOCKS), batch.directive


# Two sessions share one store, each reading its own text under the same source; a session
# believes its own text's readings and none of the other's.
# am[verifies a-rt-snars-differential-tests-1017@7b8936] am[verifies a-jev-session-reads-1017@3d73d9]
# am[verifies a-ie-s7-tests-1018@5c72ce]
def test_two_sessions_on_one_store_believe_only_their_own_text(tmp_path) -> None:
    script = {
        "sensitive text": (_reading("cli", "sensitive-data", "supported", 0.9),),
        "public text": (_reading("cli", "public-data", "supported", 0.9),),
    }
    engines = _Recording()

    def beliefs(text):
        session = SnarsSession.persistent(tmp_path / "shared.sqlite3", execute=engines, budget=request_budget(),
                                          reader=incident_reader())
        session.builder = _Builder(script)
        with session:
            session.ingest_text(text, source="cli")
            return tuple(session.belief(reading_statement(name)) for name in ("sensitive-data", "public-data"))

    (first_sensitive, first_public), (second_sensitive, second_public) = beliefs("sensitive text"), beliefs("public text")

    assert first_sensitive.evidence.positive == pytest.approx(7.2) and first_public.evidence.positive == 0
    assert second_public.evidence.positive == pytest.approx(7.2) and second_sensitive.evidence.positive == 0

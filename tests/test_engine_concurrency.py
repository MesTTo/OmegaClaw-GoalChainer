"""Purpose: verify that evaluations share the process's engine and run at once on its pool while
loads hold it alone: two evaluations meet inside the engine at the same time, each sees only what it
wrote inside its own speculation, a load waits for a running evaluation and an evaluation waits for
a load, a budget-stopped evaluation leaves the pool usable, work asking for the engine alone is
refused, a prepared evaluation, deontic review, SNARS batch, PeTTaChainer grading, justification, packaged domain
and procedures read, plan, admission, relevance review, freshness check and receipt assessment each
answer while another evaluation is inside the engine, and gradings, reviews and batches from many
threads answer what the same calls answer one at a time.
Every wait ends at its caller's deadline: each of those paths, a first preparation and an evaluation
blocked at its share raise ReviewTimeout while a load still holds the engine, work still queued
behind busy workers is cancelled and never runs, and a load that gives up lets in the evaluations it
was holding back. A SNARS report names the worlds the process compiled while a load still holds the
engine."""

from __future__ import annotations

import functools
import itertools
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import engine_meeting
import pytest
from reading_support import incident_reader
# am[verifies a-integrate-runtime-wait-deadline-1018@a74406]
from request_support import LIMITS, budget as request_budget

from goal_chainer.runtime import engine as runtime_engine
from goal_chainer.runtime.budget import InferenceBudgetExceeded, ReviewTimeout, RunBudget, run_bounded
from goal_chainer.runtime.engine import POOL_WORKERS, metta_engine, shared_evaluation
from goal_chainer.runtime.evaluator import ModuleGroup, evaluate, plain_value

# Entries that stop inside the engine where a test can see them: at a barrier only calls running
# together pass, at a hold the test opens, counting the marks their own speculation added, or
# noting that they ran.
ENTRIES = """
(: gc-cc-meet (-> Number Bool))
(= (gc-cc-meet $parties) (py-call (engine_meeting.meet $parties)))
(: gc-cc-hold (-> Atom Bool))
(= (gc-cc-hold $name) (py-call (engine_meeting.hold $name)))
(: gc-cc-mark-meet-count (-> Atom Number))
(= (gc-cc-mark-meet-count $tag)
   (let $added (add-atom &self (gc-cc-mark $tag))
     (let $met (py-call (engine_meeting.meet 2))
       (size-atom (collapse (match &self (gc-cc-mark $x) $x))))))
(: gc-cc-count (-> Number))
(= (gc-cc-count) (size-atom (collapse (match &self (gc-cc-mark $x) $x))))
(: gc-cc-spin (-> Number Number))
(= (gc-cc-spin $n) (if (== $n 0) 0 (gc-cc-spin (- $n 1))))
(: gc-cc-record (-> Atom Bool))
(= (gc-cc-record $name) (py-call (engine_meeting.record $name)))
"""
# How long a test waits to see a thread blocked before calling it blocked.
SETTLE_SECONDS = 1.0
_NUMBERS = itertools.count()


# A one-module group named for this test alone, since a process prepares each name once.
# am[verifies a-rt-cc-rw-pool-1018@5637aa]
def _group(tmp_path: Path) -> ModuleGroup:
    number = next(_NUMBERS)
    module = tmp_path / f"concurrency_{number}.metta"
    module.write_text(ENTRIES, encoding="utf-8")
    return ModuleGroup(f"test-concurrency-{number}", (module,))


# Each call on its own thread, all started before any is waited for; answers in call order.
# am[verifies a-rt-cc-rw-pool-1018@5637aa]
def _at_once(*calls):
    with ThreadPoolExecutor(max_workers=len(calls)) as threads:
        futures = [threads.submit(call) for call in calls]
        return [future.result() for future in futures]


# Two evaluations reach the barrier together, which a single shared engine, running one call at a
# time, never lets them do: the first would wait there for the second until the barrier broke.
# am[verifies a-rt-cc-rw-pool-1018@5637aa] am[verifies a-integrate-native-concurrency-contract-1017@3f9d79]
def test_two_evaluations_run_inside_the_engine_at_once(tmp_path):
    group = _group(tmp_path)

    answers = _at_once(*(lambda: evaluate(group, "gc-cc-meet", 2, budget=request_budget()) for _ in range(2)))

    assert [plain_value(answer) for answer in answers] == [True, True]


# Each evaluation adds its mark and meets the other before counting, so both marks exist at once;
# each still counts only its own, and the space keeps neither.
# am[verifies a-rt-cc-rw-pool-1018@5637aa] am[rests-on c-rt-speculative-scope-process-wide-1017@008e5b]
def test_each_evaluation_sees_only_what_it_wrote(tmp_path):
    group = _group(tmp_path)

    counts = _at_once(*(lambda tag=tag: evaluate(group, "gc-cc-mark-meet-count", tag, budget=request_budget())
                        for tag in ("first", "second")))

    assert [plain_value(count) for count in counts] == [1, 1]
    assert plain_value(evaluate(group, "gc-cc-count", budget=request_budget())) == 0


# A load waits while an evaluation runs and takes the engine as soon as it ends; an evaluation asked
# for while a load holds the engine starts only once the load lets it go.
# am[verifies a-rt-cc-rw-pool-1018@5637aa]
def test_a_load_and_an_evaluation_never_hold_the_engine_together(tmp_path):
    group = _group(tmp_path)
    evaluate(group, "gc-cc-count", budget=request_budget())
    reached, opened = engine_meeting.new_hold("load-waits")
    loaded = threading.Event()

    def load():
        with metta_engine(None):
            loaded.set()

    with ThreadPoolExecutor(max_workers=2) as threads:
        evaluation = threads.submit(evaluate, group, "gc-cc-hold", "load-waits", budget=request_budget())
        assert reached.wait(engine_meeting.WAIT_SECONDS)
        loading = threads.submit(load)
        assert not loaded.wait(SETTLE_SECONDS)
        opened.set()
        assert plain_value(evaluation.result()) is True
        loading.result()
    assert loaded.is_set()

    reached, opened = engine_meeting.new_hold("evaluation-waits")
    holding, release = threading.Event(), threading.Event()

    def hold_alone():
        with metta_engine(None):
            holding.set()
            release.wait(engine_meeting.WAIT_SECONDS)

    with ThreadPoolExecutor(max_workers=2) as threads:
        loading = threads.submit(hold_alone)
        assert holding.wait(engine_meeting.WAIT_SECONDS)
        evaluation = threads.submit(evaluate, group, "gc-cc-hold", "evaluation-waits", budget=request_budget())
        assert not reached.wait(SETTLE_SECONDS)
        release.set()
        loading.result()
        assert reached.wait(engine_meeting.WAIT_SECONDS)
        opened.set()
        assert plain_value(evaluation.result()) is True


# An evaluation its inference budget stops raises the bound on its caller's thread, and the pool
# keeps answering: as many evaluations as the pool has workers then run at once and all answer.
# am[verifies a-rt-cc-rw-pool-1018@5637aa] am[verifies a-rt-run-budget-1016@e046b0]
def test_a_stopped_evaluation_leaves_the_pool_answering(tmp_path):
    group = _group(tmp_path)

    with pytest.raises(InferenceBudgetExceeded):
        evaluate(group, "gc-cc-spin", 10**9, budget=RunBudget(inference_budget=20_000, timeout_seconds=60.0))
    answers = _at_once(*(lambda n=n: evaluate(group, "gc-cc-spin", n, budget=request_budget()) for n in range(16)))

    assert [plain_value(answer) for answer in answers] == [0] * 16


# Work that shares the engine cannot then ask for it alone, which would wait for its own share.
# am[verifies a-rt-cc-rw-pool-1018@5637aa]
def test_shared_work_asking_for_the_engine_alone_is_refused():
    def load_inside(engine):
        with metta_engine(None):
            return engine

    with pytest.raises(RuntimeError, match="prepare before evaluating"):
        shared_evaluation(load_inside, budget=None)


# Every caller names the budget it waits for the engine under, None for one outside any request,
# so a request that forgot its budget fails at the call instead of waiting for the engine unbounded.
# am[verifies a-rt-engine-budget-required-1018@e013ed]
def test_the_engine_alone_is_asked_for_with_a_budget_or_none():
    with pytest.raises(TypeError, match="budget"):
        metta_engine()


# A thread pymetta never attached, here a fresh executor thread once the engine has booted, holds
# the engine on one Prolog engine for the whole block: a global variable one call sets is there for
# the next, and a run is charged a positive count. Answered call by call on temporary engines, the
# second call finds no variable and the count falls (c-rt-bare-thread-temporary-engines-1018).
# am[verifies a-rt-cc-rw-pool-1018@5637aa] am[verifies a-rt-run-budget-1016@e046b0]
def test_one_exclusive_block_runs_on_one_engine_from_any_thread():
    with metta_engine(None):
        pass

    def block():
        with metta_engine(None) as engine:
            engine.runtime.once("nb_setval(gc_cc_attached, yes)")
            seen = engine.runtime.once("nb_getval(gc_cc_attached, V)")["V"]
            budget = RunBudget(inference_budget=10**9, timeout_seconds=60.0)
            run_bounded(engine, "!(let $x (+ 1 2) $x)", budget=budget)
        return seen, budget.spent

    with ThreadPoolExecutor(max_workers=1) as bare:
        seen, spent = bare.submit(block).result()

    assert seen == "yes"
    assert spent > 0


# One PeTTaChainer grading's outcome under `budget`: every answer the chainer gave about each target
# of one statement set recorded for the grading differential, an empty tuple where it proved nothing.
# am[verifies a-rt-cc-rw-pool-1018@5637aa] am[verifies a-hh-gp-tests-1018@33d25e]
def _grading(case: dict[str, Any], budget: RunBudget) -> Any:
    from metta import parse

    from goal_chainer.evidence_chainer import grade

    statements = [parse(text) for text in case["statements"]]
    return grade(statements, [parse(text) for text in case["targets"]], budget=budget).answers


# Every statement set recorded in data/pettachainer_petta_beliefs.json, read once.
# am[verifies a-rt-cc-rw-pool-1018@5637aa] am[verifies a-hh-gp-tests-1018@33d25e]
@functools.cache
def _recorded_sets() -> tuple[dict[str, Any], ...]:
    from record_pettachainer_petta_beliefs import RECORDED

    return tuple(json.loads(RECORDED.read_text(encoding="utf-8"))["cases"])


# PeTTaChainer's grading, a library-backed group with a warm-up, answers every recorded set the
# same from eight threads at once as one grading at a time. A budget's deadline starts when it is
# made, so each grading makes its own as a thread takes it up: the sets run in waves of eight, and
# a set queued behind earlier waves still gets its whole bound.
# am[verifies a-rt-cc-rw-pool-1018@5637aa] am[verifies a-integrate-native-concurrency-contract-1017@3f9d79]
# am[verifies a-integrate-concurrency-budget-at-start-1018@c3896d]
def test_gradings_from_many_threads_answer_as_sequential_gradings():
    cases = _recorded_sets()
    sequential = [_grading(case, request_budget()) for case in cases]

    with ThreadPoolExecutor(max_workers=8) as threads:
        concurrent = list(threads.map(lambda case: _grading(case, request_budget()), cases))

    assert concurrent == sequential


# Two theories the deontic tests also review: one decides every action, one leaves a dilemma.
DEONTIC_THEORIES = (
    "(given (risky publish_raw_log))\n(normally rRawForbid (risky publish_raw_log) (forbidden publish_raw_log))\n"
    "(given (protects publish_redacted_summary))\n"
    "(normally rRedOblige (protects publish_redacted_summary) (must publish_redacted_summary))\n",
    "(given (urgent report))\n(normally rA (urgent report) (must send_report))\n"
    "(normally rB (urgent report) (forbidden send_report))\n",
)


# Reviews from eight threads at once draw the conclusions, dilemmas and rules the same theories
# draw one review at a time, each inside its own speculation on its own worker.
# am[verifies a-rt-cc-rw-pool-1018@5637aa] am[verifies a-integrate-native-concurrency-contract-1017@3f9d79]
def test_deontic_reviews_from_many_threads_answer_as_sequential_reviews():
    from goal_chainer.deontic_engine import run_deontic_theory

    def answer(theory):
        run = run_deontic_theory(theory, budget=request_budget())
        return run.conclusions, run.dilemmas, run.rules

    theories = DEONTIC_THEORIES * 4
    sequential = [answer(theory) for theory in theories]
    with ThreadPoolExecutor(max_workers=8) as threads:
        concurrent = list(threads.map(answer, theories))

    assert concurrent == sequential


# A session's batches, each with the lines it printed when the session ran it alone, recorded once
# per process. A session reads text through its reader, which these batches never give it.
# am[verifies a-rt-cc-rw-pool-1018@5637aa]
@functools.cache
def _session_runs() -> tuple[tuple[Any, tuple[str, ...]], ...]:
    from goal_chainer.snars_models import EvidenceCounts
    from goal_chainer.snars_reasoner import SnarsSession, execute_in_process

    statement = '(sn p so "is" ((arg s (sn c "alpha")) (arg o (sn c "beta"))))'
    pattern = '(sn p so "is" ((arg s (sn c "alpha")) (arg o $what)))'
    runs = []

    def recording(batch, budget):
        lines = tuple(execute_in_process(batch, budget))
        runs.append((batch, lines))
        return lines

    with SnarsSession.ephemeral(execute=recording, budget=request_budget(), reader=incident_reader()) as session:
        session.believe(statement, evidence=EvidenceCounts(2.0, 1.0, 0.5), source="concurrency", occurrence=1.0)
        session.belief(statement)
        session.ask(pattern)
        session.prove(statement)
        session.trust()
        session.inspect()
        # Two more generic operations stand where the incident assessment and context batches stood,
        # so the replay still checks sixteen batches. am[verifies a-ie-s7-tests-1018@5c72ce]
        session.explain(statement)
        session.discover(pattern)
    return tuple(runs)


# A session's batches, recorded as it ran them one at a time, answer the same records when every
# batch runs again from its own thread at once, up to the protocol's wall clock.
# am[verifies a-rt-cc-rw-pool-1018@5637aa] am[verifies a-integrate-native-concurrency-contract-1017@3f9d79]
def test_snars_batches_from_many_threads_answer_as_sequential_batches():
    from snars_differential import clock_fields, equal, records

    from goal_chainer.snars_engine import run_snars_batch
    from goal_chainer.snars_program import PROTOCOL_PATH

    clocks = clock_fields(PROTOCOL_PATH.read_text(encoding="utf-8"))
    runs = _session_runs() * 2

    with ThreadPoolExecutor(max_workers=8) as threads:
        again = list(threads.map(lambda run: run_snars_batch(run[0], budget=request_budget()), runs))

    assert len(runs) >= 16
    for (batch, lines), rerun in zip(runs, again, strict=True):
        assert equal(records("\n".join(lines)), records("\n".join(rerun.output_lines)), clocks), batch.directive


# am[verifies a-rt-cc-rw-pool-1018@5637aa]
def _evaluation_path(group: ModuleGroup, budget: RunBudget) -> Any:
    return evaluate(group, "gc-cc-count", budget=budget)


# am[verifies a-rt-cc-rw-pool-1018@5637aa]
def _review_path(group: ModuleGroup, budget: RunBudget) -> Any:
    from goal_chainer.deontic_engine import run_deontic_theory

    return run_deontic_theory(DEONTIC_THEORIES[0], budget=budget)


# am[verifies a-rt-cc-rw-pool-1018@5637aa]
def _batch_path(group: ModuleGroup, budget: RunBudget) -> Any:
    from goal_chainer.snars_engine import run_snars_batch

    return run_snars_batch(_session_runs()[0][0], budget=budget)


# am[verifies a-rt-cc-rw-pool-1018@5637aa]
# am[verifies a-integrate-runtime-wait-deadline-1018@a74406]
def _grading_path(group: ModuleGroup, budget: RunBudget) -> Any:
    return _grading(_recorded_sets()[0], budget)


# A snapshot of two rows, one rebutting the other, through the justification kernel's own group.
# am[verifies a-rt-cc-rw-pool-1018@5637aa] am[verifies a-rt-rb-migrate-justification-1018@439e90]
def _justification_path(group: ModuleGroup, budget: RunBudget) -> Any:
    from metta import Expression, S

    from goal_chainer.planning.justification import justify

    def source(name: str, estimator: str) -> Any:
        return Expression(S.Observation, Expression(S.Obs, name, estimator, S.Forever))

    rows = (Expression(S.From, Expression(S.Signal, "a"), source("m", "measured")),
            Expression(S.From, Expression(S.Not, Expression(S.Signal, "a")), source("e", "model-proposed")))
    return justify(rows, at=10, budget=budget)


# The pause route's evidence as the planner's tests give it: each signal read a minute before the
# plan's time, and the restore drill's row for the checkpoint store's restore statement.
PAUSE_ROUTE = {"resource_contention": "detected", "state_preservation_route": "detected",
               "safe_point_reachable": "refuted", "owner_mismatch": "refuted", "receiving_owner_accepts": "refuted"}
AT = datetime(2026, 10, 18, 6, 0, tzinfo=timezone.utc)


# The packaged task-control domain with its own section and packaged library, the pause route's
# readings, rows and goal, its plan, and the safe point's act with the journal that started it,
# admitted: read, planned and admitted once per process.
# am[verifies a-integrate-admit-concurrency-1018@b0a4e3]
@functools.cache
def _packaged_planning() -> dict[str, Any]:
    from metta import S, Symbol

    from goal_chainer.domains.loader import packaged_domain
    from goal_chainer.planning.procedures import NegatedLiteral, SignalLiteral, literal_term, packaged_procedures
    from goal_chainer.planning.projection import Admitted, Plan, Started, admit, plan
    from goal_chainer.relevance.signals import SignalReading

    domain = packaged_domain("task-control", budget=request_budget())
    library = packaged_procedures(domain, budget=request_budget())
    evidence = {
        "domain": domain, "library": library, "at": AT,
        "readings": tuple(SignalReading(signal, state, "test", "deterministic", observed_at=AT - timedelta(minutes=1))
                          for signal, state in PAUSE_ROUTE.items()),
        "rows": (S.From(literal_term(library.procedures[0].when[2]),
                        S.Observation(S.Drill("drill", "deterministic", Symbol("Forever")))),),
    }
    goal = (NegatedLiteral(SignalLiteral("resource_contention")),)
    planned = plan(goal, journal=(), receipts={}, budget=request_budget(), **evidence)
    assert isinstance(planned, Plan)
    act = next(step for step in planned.steps if step.kind == "act" and step.procedure == "reach-safe-point")
    journal = (Started("i1", "reach-safe-point", "j1"),)
    admitted = admit(act, instance_id="i1", journal=journal, budget=request_budget(), **evidence)
    assert isinstance(admitted, Admitted)
    return {"evidence": evidence, "goal": goal, "plan": planned, "act": act, "journal": journal,
            "admitted": admitted}


# Each request reads its packaged domain and that domain's procedures again; both parse the shipped
# declarations through domains.forms.parsed_forms.
# am[verifies a-integrate-admit-concurrency-1018@b0a4e3]
def _domain_read_path(group: ModuleGroup, budget: RunBudget) -> Any:
    from goal_chainer.domains.loader import packaged_domain

    return packaged_domain("task-control", budget=budget)


# am[verifies a-integrate-admit-concurrency-1018@b0a4e3]
def _procedures_read_path(group: ModuleGroup, budget: RunBudget) -> Any:
    from goal_chainer.planning.procedures import packaged_procedures

    return packaged_procedures(_packaged_planning()["evidence"]["domain"], budget=budget)


# am[verifies a-integrate-admit-concurrency-1018@b0a4e3]
def _plan_path(group: ModuleGroup, budget: RunBudget) -> Any:
    from goal_chainer.planning.projection import plan

    planning = _packaged_planning()
    answer = plan(planning["goal"], journal=(), receipts={}, budget=budget, **planning["evidence"])
    assert answer == planning["plan"]
    return answer


# Admission parses the step's witness, its rule and each image, before it evaluates.
# am[verifies a-integrate-admit-concurrency-1018@b0a4e3]
def _admission_path(group: ModuleGroup, budget: RunBudget) -> Any:
    from goal_chainer.planning.projection import admit

    planning = _packaged_planning()
    verdict = admit(planning["act"], instance_id="i1", journal=planning["journal"], budget=budget,
                    **planning["evidence"])
    assert verdict == planning["admitted"]
    return verdict


# The guide's worked relevance case: the packaged task-control domain, read once per process as a
# host keeps it; the chemistry contention packet, declaring the request limits so that any budget
# this file gives a path is no looser than the packet; its review record, the engine identity a
# check compares, and the example receipt naming that review.
# am[verifies a-rel-mig-tests-1018@3b8517]
# am[verifies a-ie-host-freshness-1018@ff618a]
@functools.cache
def _relevance_case() -> dict[str, Any]:
    from dataclasses import replace

    from goal_chainer.domains.loader import packaged_domain
    from goal_chainer.relevance import ReviewBudget, engine_identity, parse_packet, review

    examples = Path(__file__).resolve().parents[1] / "examples" / "relevance"
    packet = replace(parse_packet(json.loads((examples / "chemistry-contention.packet.json").read_text(encoding="utf-8"))),
                     budget=ReviewBudget(inferences=LIMITS["inference_budget"], timeout_seconds=LIMITS["timeout_seconds"]))
    domain = packaged_domain("task-control", budget=request_budget())
    record = review(domain, packet, budget=request_budget()).to_dict()
    receipt = json.loads((examples / "chemistry-receipt.json").read_text(encoding="utf-8"))
    identity = engine_identity(budget=request_budget())
    return {"domain": domain, "packet": packet, "record": record,
            "receipt": {**receipt, "review_fingerprint": record["fingerprint"]},
            "engine": identity}


# A relevance path stopped by its budget raises the review's own error, review-timeout, from the
# runtime's ReviewTimeout; the deadline test reads the runtime's stop it was raised from.
# am[verifies a-rel-mig-tests-1018@3b8517]
@contextmanager
def _runtime_stop():
    from goal_chainer.relevance.errors import RelevanceError

    try:
        yield
    except RelevanceError as error:
        if isinstance(error.__cause__, ReviewTimeout):
            raise error.__cause__
        raise


# am[verifies a-rel-mig-tests-1018@3b8517]
def _relevance_review_path(group: ModuleGroup, budget: RunBudget) -> Any:
    from goal_chainer.relevance import review

    case = _relevance_case()
    with _runtime_stop():
        record = review(case["domain"], case["packet"], budget=budget).to_dict()
    assert record["fingerprint"] == case["record"]["fingerprint"]
    return record


# am[verifies a-rel-mig-tests-1018@3b8517]
def _freshness_path(group: ModuleGroup, budget: RunBudget) -> Any:
    from goal_chainer.relevance import check_freshness

    case = _relevance_case()
    with _runtime_stop():
        report = check_freshness(case["record"], case["domain"], case["packet"], case["engine"], budget=budget)
    assert report.status == "fresh"
    return report


# A receipt is checked and assessed under the one budget the assess command makes.
# am[verifies a-rel-mig-tests-1018@3b8517]
def _assessment_path(group: ModuleGroup, budget: RunBudget) -> Any:
    from goal_chainer.relevance import assess_receipt, parse_receipt

    case = _relevance_case()
    with _runtime_stop():
        return assess_receipt(case["record"], parse_receipt(case["receipt"], budget=budget), budget=budget)


# Every path a request reaches the engine by, keyed by the name a failure reports; each runs under
# the budget it is given.
# am[verifies a-rt-cc-rw-pool-1018@5637aa] am[verifies a-integrate-admit-concurrency-1018@b0a4e3]
# am[verifies a-integrate-runtime-wait-deadline-1018@a74406] am[verifies a-rel-mig-tests-1018@3b8517]
PREPARED_PATHS = {
    "evaluation": _evaluation_path,
    "deontic review": _review_path,
    "snars batch": _batch_path,
    "chainer grading": _grading_path,
    "packaged domain read": _domain_read_path,
    "packaged procedures read": _procedures_read_path,
    "plan": _plan_path,
    "admission": _admission_path,
    "relevance review": _relevance_review_path,
    "freshness check": _freshness_path,
    "receipt assessment": _assessment_path,
    "justification": _justification_path,
}


# Each path runs once, which prepares what it needs, and then again while another evaluation is held
# inside the engine. A path taking the engine alone on every call would wait there for that
# evaluation, which stays held until the path answers or WAIT_SECONDS pass, so it fails here
# whatever order the threads run in (c-rt-kernel-per-call-exclusive-1018).
@pytest.mark.parametrize("path", sorted(PREPARED_PATHS))
# am[verifies a-rt-cc-rw-pool-1018@5637aa] am[verifies a-integrate-native-concurrency-contract-1017@3f9d79]
def test_a_prepared_path_answers_while_an_evaluation_is_inside_the_engine(tmp_path, path):
    group = _group(tmp_path)
    run = PREPARED_PATHS[path]
    run(group, request_budget())
    hold = f"inside-{path}"
    reached, opened = engine_meeting.new_hold(hold)

    with ThreadPoolExecutor(max_workers=2) as threads:
        inside = threads.submit(evaluate, group, "gc-cc-hold", hold, budget=request_budget())
        try:
            assert reached.wait(engine_meeting.WAIT_SECONDS)
            threads.submit(run, group, request_budget()).result(timeout=engine_meeting.WAIT_SECONDS)
        finally:
            opened.set()
        assert plain_value(inside.result()) is True


# Each path, prepared, runs again while a load holds the engine alone: it raises ReviewTimeout at
# its own deadline, charged nothing, while the load still holds the engine, rather than once the
# load lets go. The load holds until the path returns, so a path whose wait outlasts its deadline
# fails here whatever order the threads run in.
@pytest.mark.parametrize("path", sorted(PREPARED_PATHS))
# am[verifies a-integrate-runtime-wait-deadline-1018@a74406]
def test_a_prepared_path_waiting_for_a_load_stops_at_its_deadline(tmp_path, path):
    group = _group(tmp_path)
    run = PREPARED_PATHS[path]
    run(group, request_budget())
    budget = engine_meeting.short_budget()

    def stopped():
        with pytest.raises(ReviewTimeout):
            run(group, budget)

    assert engine_meeting.while_held_alone(stopped)
    assert budget.spent == 0


# A group's first evaluation, waiting to prepare while a load holds the engine, stops at its
# deadline, and the group is left unprepared, so the next evaluation prepares it and answers.
# am[verifies a-integrate-runtime-wait-deadline-1018@a74406] am[verifies a-rt-initialize-once-1016@0767f5]
def test_a_first_preparation_waiting_for_a_load_stops_at_its_deadline_and_the_next_prepares(tmp_path):
    group = _group(tmp_path)

    def stopped():
        with pytest.raises(ReviewTimeout):
            evaluate(group, "gc-cc-count", budget=engine_meeting.short_budget())

    assert engine_meeting.while_held_alone(stopped)
    assert plain_value(evaluate(group, "gc-cc-count", budget=request_budget())) == 0


# An evaluation a worker took up while a load holds the engine stops at its share's deadline and
# never runs its call, the load still holding.
# am[verifies a-integrate-runtime-wait-deadline-1018@a74406]
def test_an_evaluation_blocked_at_its_share_stops_at_its_deadline_and_never_runs(tmp_path):
    group = _group(tmp_path)
    evaluate(group, "gc-cc-count", budget=request_budget())
    name = f"blocked-{group.name}"

    def stopped():
        with pytest.raises(ReviewTimeout):
            evaluate(group, "gc-cc-record", name, budget=engine_meeting.short_budget())

    assert engine_meeting.while_held_alone(stopped)
    assert plain_value(evaluate(group, "gc-cc-record", f"after-{name}", budget=request_budget())) is True
    assert name not in engine_meeting.RECORDED and f"after-{name}" in engine_meeting.RECORDED


# With every pool worker inside an evaluation, another evaluation's work waits in the pool's queue;
# at its deadline it is cancelled there, so once the workers are free it never runs, and the pool
# answers the next evaluation.
# am[verifies a-integrate-runtime-wait-deadline-1018@a74406]
def test_work_queued_behind_busy_workers_is_cancelled_at_its_deadline_and_never_runs(tmp_path):
    group = _group(tmp_path)
    evaluate(group, "gc-cc-count", budget=request_budget())
    names = [f"busy-{group.name}-{index}" for index in range(POOL_WORKERS)]
    holds = [engine_meeting.new_hold(name) for name in names]
    queued = f"queued-{group.name}"

    with ThreadPoolExecutor(max_workers=POOL_WORKERS) as threads:
        busy = [threads.submit(evaluate, group, "gc-cc-hold", name, budget=request_budget()) for name in names]
        try:
            assert all(reached.wait(engine_meeting.WAIT_SECONDS) for reached, _ in holds)
            with pytest.raises(ReviewTimeout):
                evaluate(group, "gc-cc-record", queued, budget=engine_meeting.short_budget())
            assert not any(future.done() for future in busy)
        finally:
            for _, opened in holds:
                opened.set()
        assert [plain_value(future.result()) for future in busy] == [True] * POOL_WORKERS

    assert plain_value(evaluate(group, "gc-cc-record", f"after-{queued}", budget=request_budget())) is True
    assert queued not in engine_meeting.RECORDED and f"after-{queued}" in engine_meeting.RECORDED


# A load waiting behind a running evaluation holds back new evaluations, so a stream of them cannot
# starve it; once its deadline passes it gives up, and an evaluation it held back gets in while the
# first is still running. Its wait is seen through the hold's count of waiting loads.
# am[verifies a-integrate-runtime-wait-deadline-1018@a74406] am[verifies a-rt-cc-rw-pool-1018@5637aa]
def test_a_load_that_gives_up_lets_in_the_evaluations_it_held_back(tmp_path):
    group = _group(tmp_path)
    evaluate(group, "gc-cc-count", budget=request_budget())
    first, later = f"first-{group.name}", f"later-{group.name}"
    first_reached, first_opened = engine_meeting.new_hold(first)
    later_reached, later_opened = engine_meeting.new_hold(later)
    load_budget = RunBudget(inference_budget=None,
                            timeout_seconds=SETTLE_SECONDS + engine_meeting.DEADLINE_SECONDS)

    def load():
        with pytest.raises(ReviewTimeout):
            with metta_engine(load_budget):
                pass

    with ThreadPoolExecutor(max_workers=3) as threads:
        running = threads.submit(evaluate, group, "gc-cc-hold", first, budget=request_budget())
        try:
            assert first_reached.wait(engine_meeting.WAIT_SECONDS)
            loading = threads.submit(load)
            waited = time.monotonic() + engine_meeting.WAIT_SECONDS
            while runtime_engine._HOLDS._waiting == 0 and time.monotonic() < waited:
                time.sleep(0.01)
            assert runtime_engine._HOLDS._waiting == 1
            held_back = threads.submit(evaluate, group, "gc-cc-hold", later, budget=request_budget())
            assert not later_reached.wait(SETTLE_SECONDS)
            loading.result(timeout=engine_meeting.WAIT_SECONDS)
            assert later_reached.wait(engine_meeting.WAIT_SECONDS)
            assert not first_opened.is_set()
        finally:
            first_opened.set()
            later_opened.set()
        assert plain_value(running.result()) is True
        assert plain_value(held_back.result()) is True


# A SNARS command's report names the worlds the process compiled, read after its batches ran. While
# a load holds the engine alone, the report still answers before the load lets go, naming the world
# a batch compiled as the report gives it.
# am[verifies a-integrate-snars-report-deadline-1018@5ba321]
def test_a_snars_report_names_its_worlds_while_a_load_holds_the_engine():
    from dataclasses import asdict

    from goal_chainer.snars_engine import compiled_worlds, prepare_snars_world
    from goal_chainer.snars_reasoner import runtime_payload

    world = prepare_snars_world(budget=request_budget())
    reported = {}

    def report():
        reported["worlds"] = compiled_worlds()
        reported["runtime"] = runtime_payload()

    assert engine_meeting.while_held_alone(report)
    assert world in reported["worlds"]
    assert {**asdict(world), "snars_identity": world.snars_identity} in reported["runtime"]["worlds"]

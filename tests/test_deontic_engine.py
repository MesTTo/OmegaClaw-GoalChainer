"""Purpose: verify the bounded lib_deontic review on the process's pymetta engine: typed conclusions
and dilemmas on fixed theories, both bounds of a run budget and its sharing across reviews,
isolation of every review from the one before it including a stopped one, concurrent reviewers, the
engine identity, no review charged lib_deontic's first use, a thread's first reset or a file search
cache sweep, the payload reader's refusals, and the incident decision read from the same review."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from goal_chainer.runtime import budget as runtime_budget
from goal_chainer.deontic_engine import (
    DeonticConclusion,
    DeonticEngine,
    DeonticLiteral,
    DeonticOutputError,
    InferenceBudgetExceeded,
    ReviewTimeout,
    RunBudget,
    _deontic_library,
    prepare_deontic_engine,
    read_review_payload,
    run_deontic_theory,
)
from goal_chainer.runtime.modules import tree_digest
from goal_chainer.errors import InvalidInputError, MettaEngineError
from goal_chainer.sexpr.codec import SexprCodec

SAMPLE = """(given (risky publish_raw_log))
(normally rRawForbid (risky publish_raw_log) (forbidden publish_raw_log))
(given (protects publish_redacted_summary))
(normally rRedOblige (protects publish_redacted_summary) (must publish_redacted_summary))
(given (may hold_external_update))
"""

# O send_report and F send_report (that is, O not send_report) both fire and neither defeats the
# other, so lib_deontic proves neither and reports the obligation as a dilemma.
DILEMMA = """(given (urgent report))
(normally rA (urgent report) (must send_report))
(normally rB (urgent report) (forbidden send_report))
"""

# A superiority relation settles the clash DILEMMA leaves open, and a chained rule's numeric and
# string arguments cross the engine's printer.
DEFEAT = """(given (p))
(given (q))
(normally r1 (p) (must act))
(normally r2 (q) (forbidden act))
(prefer r2 r1)
"""
CHAIN = """(given (score item 0.5 3 "label"))
(normally r1 (score item 0.5 3 "label") (ready item))
(normally r2 (ready item) (must ship))
"""

ENGINE = DeonticEngine("pymetta test", "runtime", "plugin", "10.1.17")


# am[verifies a-rt-typed-deontic-api-1016@871afb]
def _literal(mode: str, functor: str, *args: str, sign: str = "pos") -> DeonticLiteral:
    return DeonticLiteral(sign, mode, "none", functor, args)


# A fresh budget per review, generous enough that only the tests about bounds hit one.
# am[verifies a-rt-run-budget-1016@e046b0]
def _budget() -> RunBudget:
    return RunBudget(inference_budget=10_000_000, timeout_seconds=120.0)


# What two reviews of one theory must share: everything but the inferences, which a review spends a
# little differently with process history.
# am[verifies a-rt-pymetta-deontic-1016@61a4b6] am[verifies a-integrate-deontic-support-trees-1019@508ecf]
def _answer(run) -> tuple:
    return run.conclusions, run.dilemmas, run.rules, run.support


# The shared S-expression codec the review reader uses, over the packaged S-expression module.
# am[verifies a-rt-typed-deontic-api-1016@871afb] am[related a-rt-sexpr-codec-packaged-1017@608f80]
@pytest.fixture(scope="module")
def codec() -> SexprCodec:
    return SexprCodec()


# am[verifies a-rel-deontic-run-1016@be58d5] am[verifies a-rt-typed-deontic-api-1016@871afb]
# am[verifies a-ie-host-freshness-1018@ff618a]
def test_review_answers_sorted_typed_conclusions_and_its_cost():
    run = run_deontic_theory(SAMPLE, budget=_budget())

    assert DeonticConclusion("pd", _literal("F", "publish_raw_log")) in run.conclusions
    assert DeonticConclusion("pd", _literal("O", "publish_redacted_summary")) in run.conclusions
    assert DeonticConclusion("pd", _literal("none", "risky", "publish_raw_log")) in run.conclusions
    assert run.conclusions == tuple(sorted(set(run.conclusions)))
    assert run.rules == 5
    assert run.dilemmas == ()
    assert 0 < run.inferences < 10_000_000
    assert run.engine == prepare_deontic_engine(budget=_budget())
    assert run.engine.runtime == f"pymetta {importlib.metadata.version('pymetta')}"


# am[verifies a-rel-deontic-run-1016@be58d5]
def test_unresolved_obligations_are_reported_as_dilemmas():
    run = run_deontic_theory(DILEMMA, budget=_budget())

    assert run.dilemmas == (_literal("O", "send_report"),)
    provable = {c.literal for c in run.conclusions if c.is_provable}
    assert _literal("O", "send_report") not in provable
    assert _literal("F", "send_report") not in provable


# r2 is preferred to r1, so their clash on act is no dilemma: act is defeasibly forbidden and not
# obligated, and the obligation r1 would give is refuted.
# am[verifies a-rel-deontic-run-1016@be58d5] am[verifies a-rt-pymetta-deontic-1016@61a4b6]
def test_a_preference_settles_the_clash_a_dilemma_leaves_open():
    run = run_deontic_theory(DEFEAT, budget=_budget())

    assert run.rules == 4
    assert run.dilemmas == ()
    assert DeonticConclusion("pd", _literal("F", "act")) in run.conclusions
    assert DeonticConclusion("pd", _literal("O", "act", sign="neg")) in run.conclusions
    assert DeonticConclusion("nd", _literal("O", "act")) in run.conclusions
    assert DeonticConclusion("pd", _literal("O", "act")) not in run.conclusions


# A given fact's number and string arguments reach the rule that matches it as written, and the
# chain through ready concludes the obligation to ship.
# am[verifies a-rt-typed-deontic-api-1016@871afb] am[verifies a-rt-pymetta-deontic-1016@61a4b6]
def test_a_chained_rule_carries_number_and_string_arguments_to_its_conclusion():
    run = run_deontic_theory(CHAIN, budget=_budget())

    assert run.rules == 3
    assert run.dilemmas == ()
    assert DeonticConclusion("pD", _literal("none", "score", "item", "0.5", "3", '"label"')) in run.conclusions
    assert DeonticConclusion("pd", _literal("none", "ready", "item")) in run.conclusions
    assert DeonticConclusion("pd", _literal("O", "ship")) in run.conclusions


# am[verifies a-rel-deontic-run-1016@be58d5]
def test_inference_budget_stops_the_review_early():
    with pytest.raises(InferenceBudgetExceeded) as caught:
        run_deontic_theory(SAMPLE, budget=RunBudget(inference_budget=1_000, timeout_seconds=120.0))

    assert caught.value.budget == 1_000
    # call_with_inference_limit stops within a few inferences of the limit, far below a full run.
    assert 1_000 < caught.value.used < run_deontic_theory(SAMPLE, budget=_budget()).inferences
    assert caught.value.code == "inference_budget_exceeded"


# am[verifies a-rel-deontic-run-1016@be58d5]
def test_wall_budget_stops_the_review():
    with pytest.raises(ReviewTimeout) as caught:
        run_deontic_theory(SAMPLE, budget=RunBudget(inference_budget=10_000_000, timeout_seconds=0.001))

    assert caught.value.timeout_seconds == 0.001


# A / stopped B / A: neither a finished nor a budget-stopped review leaves anything for the next.
# am[verifies a-rel-deontic-run-1016@be58d5] am[verifies a-rt-pymetta-deontic-1016@61a4b6]
def test_reviews_are_isolated_from_finished_and_stopped_reviews():
    first = run_deontic_theory(SAMPLE, budget=_budget())
    run_deontic_theory(DILEMMA, budget=_budget())
    with pytest.raises(InferenceBudgetExceeded):
        run_deontic_theory(DILEMMA, budget=RunBudget(inference_budget=20_000, timeout_seconds=120.0))
    again = run_deontic_theory(SAMPLE, budget=_budget())

    assert _answer(again) == _answer(first)
    assert again.engine == first.engine
    assert not any(c.literal.functor == "send_report" for c in again.conclusions)


# The engine is one per process and this one has long loaded lib_deontic, so a fresh interpreter
# shows the first load: stopped by a deadline it cannot meet, then retried whole within one it can.
# am[verifies a-rt-bounded-preparation-1016@e7eb12]
def test_the_first_load_runs_inside_the_callers_deadline():
    script = (
        "from goal_chainer.deontic_engine import ReviewTimeout, RunBudget, prepare_deontic_engine, run_deontic_theory\n"
        "import sys\n"
        "try:\n"
        "    prepare_deontic_engine(budget=RunBudget(inference_budget=None, timeout_seconds=0.001))\n"
        "    print('not stopped')\n"
        "except ReviewTimeout as error:\n"
        "    print('stopped', error.timeout_seconds)\n"
        "run = run_deontic_theory(sys.argv[1], budget=RunBudget(inference_budget=10_000_000, timeout_seconds=120.0))\n"
        "print('conclusions', len(run.conclusions), 'rules', run.rules)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, SAMPLE], capture_output=True, text=True, check=True
    )
    reference = run_deontic_theory(SAMPLE, budget=_budget())

    assert result.stdout.splitlines() == [
        "stopped 0.001",
        f"conclusions {len(reference.conclusions)} rules {reference.rules}",
    ]


# A fresh interpreter, whose reviews are the process's first, prepared by the host at startup with no
# budget or by the first review itself. Before each theory's first review the file search cache's
# last-sweep fact is removed, as if its pace had passed, so a file search insert in that review would
# sweep the whole cache. Each theory is reviewed twice and SAMPLE then once on each pool worker and
# once more, and a theory's reviews all spend the same: none is charged lib_deontic's first use, its
# thread's first reset or a sweep.
# am[verifies a-rt-det-warmup-1018@c86a73] am[verifies a-rt-det-deontic-thread-reset-1019@3c05d5]
@pytest.mark.parametrize("prepared_by", ["host", "first-review"])
def test_a_review_is_charged_no_first_use_and_no_sweep(prepared_by):
    script = (
        "import json, sys\n"
        "from goal_chainer.deontic_engine import RunBudget, prepare_deontic_engine, run_deontic_theory\n"
        "from goal_chainer.runtime.engine import POOL_WORKERS, metta_engine\n"
        "theories = json.loads(sys.argv[1])\n"
        "if sys.argv[2] == 'host':\n"
        "    prepare_deontic_engine()\n"
        "def review(theory):\n"
        "    return run_deontic_theory(theory, budget=RunBudget(inference_budget=10_000_000, timeout_seconds=120.0)).inferences\n"
        "spends = []\n"
        "for theory in theories:\n"
        "    with metta_engine(None) as engine:\n"
        "        assert engine.runtime.once(\"predicate_property(system:'$search_path_gc_time'(_), dynamic)\")\n"
        "        engine.runtime.once(\"retractall(system:'$search_path_gc_time'(_))\")\n"
        "    spends.append([review(theory), review(theory)])\n"
        "spends.append([review(theories[0]) for _ in range(POOL_WORKERS + 1)])\n"
        "print(json.dumps(spends))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, json.dumps([SAMPLE, DILEMMA, DEFEAT, CHAIN]), prepared_by],
        capture_output=True, text=True, check=True,
    )
    *pairs, sample_on_every_worker = json.loads(result.stdout.splitlines()[-1])

    assert [first - second for first, second in pairs] == [0, 0, 0, 0]
    assert set(sample_on_every_worker) == {pairs[0][0]}


# am[verifies a-rel-deontic-run-1016@be58d5]
def test_a_theory_the_engine_cannot_see_is_refused():
    with pytest.raises(DeonticOutputError, match="no rules"):
        run_deontic_theory("; nothing here\n", budget=_budget())


# am[verifies a-rt-pymetta-deontic-1016@61a4b6]
def test_a_theory_lib_deontic_cannot_read_is_an_engine_failure():
    with pytest.raises(MettaEngineError):
        run_deontic_theory("(given (unclosed\n", budget=_budget())


# Two reviews charged to one budget: the second gets only what the first left, and its stop names
# the whole bound and the whole spend.
# am[verifies a-rt-run-budget-1016@e046b0]
def test_reviews_charged_to_one_budget_share_its_bound():
    one = run_deontic_theory(SAMPLE, budget=_budget()).inferences
    budget = RunBudget(inference_budget=one + one // 2, timeout_seconds=240.0)
    run_deontic_theory(SAMPLE, budget=budget)
    with pytest.raises(InferenceBudgetExceeded) as caught:
        run_deontic_theory(SAMPLE, budget=budget)

    assert caught.value.budget == one + one // 2
    assert caught.value.used == budget.spent > caught.value.budget


# am[verifies a-rt-run-budget-1016@e046b0]
def test_an_exhausted_budget_runs_no_review():
    budget = RunBudget(inference_budget=1_000, timeout_seconds=120.0)
    with pytest.raises(InferenceBudgetExceeded):
        run_deontic_theory(SAMPLE, budget=budget)
    spent = budget.spent
    with pytest.raises(InferenceBudgetExceeded):
        run_deontic_theory(SAMPLE, budget=budget)

    assert budget.spent == spent


# The budget errors are goal_chainer.runtime.budget's, so one except clause covers every engine
# stage.
# am[verifies a-rt-run-budget-1016@e046b0]
def test_the_review_raises_the_engine_hosts_budget_errors():
    assert InferenceBudgetExceeded is runtime_budget.InferenceBudgetExceeded
    assert ReviewTimeout is runtime_budget.ReviewTimeout
    with pytest.raises(InvalidInputError):
        run_deontic_theory(17, budget=_budget())


# Any budget either finishes the review with the reference answer or stops it with the whole
# bound named, and the next review is unaffected either way; pymetta can swallow an inference
# interrupt inside some callbacks, which only a spread of stopping points would show.
# am[verifies a-rt-pymetta-deontic-1016@61a4b6] am[verifies a-rt-run-budget-1016@e046b0]
@settings(max_examples=25, deadline=None, derandomize=True)
@given(inference_budget=st.integers(min_value=1, max_value=1_500_000))
def test_every_budget_finishes_or_stops_cleanly(inference_budget):
    reference = _answer(run_deontic_theory(SAMPLE, budget=_budget()))
    budget = RunBudget(inference_budget=inference_budget, timeout_seconds=120.0)
    try:
        run = run_deontic_theory(SAMPLE, budget=budget)
    except InferenceBudgetExceeded as stopped:
        assert stopped.budget == inference_budget
        assert stopped.used == budget.spent >= inference_budget
    else:
        assert _answer(run) == reference
        assert run.inferences == budget.spent <= inference_budget

    assert _answer(run_deontic_theory(SAMPLE, budget=_budget())) == reference


# Reviewers on several threads share the one engine under its lock; each gets its own answer.
# am[verifies a-rt-pymetta-deontic-1016@61a4b6]
def test_concurrent_reviewers_each_get_their_own_review():
    expected = {name: _answer(run_deontic_theory(theory, budget=_budget()))
                for name, theory in (("sample", SAMPLE), ("dilemma", DILEMMA))}
    results: list[tuple[str, tuple]] = []

    def review(name: str, theory: str) -> None:
        for _ in range(3):
            results.append((name, _answer(run_deontic_theory(theory, budget=_budget()))))

    threads = [
        threading.Thread(target=review, args=pair)
        for pair in (("sample", SAMPLE), ("dilemma", DILEMMA)) * 4
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 24
    assert all(answer == expected[name] for name, answer in results)


# am[verifies a-rt-pymetta-deontic-1016@61a4b6]
def test_the_in_process_identity_names_what_was_loaded():
    identity = prepare_deontic_engine()
    distribution = importlib.metadata.distribution("pymetta")

    assert prepare_deontic_engine() is identity
    assert identity.runtime == f"pymetta {distribution.version}"
    assert identity.runtime_digest == hashlib.sha256(distribution.read_text("RECORD").encode()).hexdigest()
    assert identity.plugin_digest == tree_digest(_deontic_library())


# lib_deontic's reviews on subprocess PeTTa, recorded once before PeTTa was retired, of the fixed
# theories above and of 60 generated ones, 15 from each stratum of whether the review holds a
# dilemma and whether the theory states a preference, the in-process review answering each alike.
# am[verifies a-rt-rp-deontic-subprocess-1018@b8b843]
PETTA_REVIEWS = json.loads(
    (Path(__file__).parent / "data" / "deontic-petta-reviews.json").read_text(encoding="utf-8"))["cases"]


# Each recorded theory still reviews as PeTTa reviewed it: the same rendered conclusions and
# dilemmas from the same number of rules, or the same refusal.
# am[verifies a-rt-pymetta-deontic-1016@61a4b6] am[verifies a-rt-rp-deontic-subprocess-1018@b8b843]
@pytest.mark.parametrize("case", PETTA_REVIEWS, ids=[f"{case['kind']}-{index}" for index, case in enumerate(PETTA_REVIEWS)])
def test_each_recorded_theory_reviews_as_petta_reviewed_it(case):
    try:
        run = run_deontic_theory(case["theory"], budget=_budget())
    except DeonticOutputError as refused:
        assert {"refused": str(refused).split(":")[0]} == case["review"]
        return

    assert {"conclusions": [conclusion.render() for conclusion in run.conclusions],
            "dilemmas": [literal.render() for literal in run.dilemmas], "rules": run.rules} == case["review"]


# am[verifies a-rel-deontic-run-1016@be58d5]
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("(complete 12 100117 0 () () ())", "no rules"),
        ("(complete 12 100117 3 () () ())", "drew no conclusion"),
        ("(complete 12 90400 3 ((pd (lit pos none none a ()))) () ())", "different SWI-Prolog"),
        ("(complete 12 100117 3 ((pd (lit pos none a ()))) () ())", "six-slot literal"),
        ("(complete 12 100117 3 ((pd)) () ())", "tag literal"),
        ("(complete twelve 100117 3 () () ())", "integer"),
        ("(finished 12)", "wrong shape"),
    ],
)
def test_payload_reader_fails_closed(codec, payload, message):
    with pytest.raises(DeonticOutputError, match=message):
        read_review_payload(codec.parse(payload), codec, ENGINE)


_symbols = st.from_regex(r"[a-z][a-zA-Z0-9_]{0,8}", fullmatch=True)
_literals = st.builds(
    DeonticLiteral,
    sign=st.sampled_from(("pos", "neg")),
    mode=st.sampled_from(("F", "O", "P", "none")),
    temporal=st.one_of(st.just("none"), _symbols),
    functor=_symbols,
    args=st.lists(_symbols, max_size=3).map(tuple),
)


# Reading a rendered review back gives the same conclusions and dilemmas, deduplicated and sorted.
# am[verifies a-rt-typed-deontic-api-1016@871afb] am[verifies a-integrate-deontic-support-trees-1019@508ecf]
@given(
    conclusions=st.lists(
        st.builds(DeonticConclusion, tag=st.sampled_from(("pD", "pd", "nD", "nd")), literal=_literals),
        min_size=1,
        max_size=8,
    ),
    dilemmas=st.lists(_literals, max_size=4),
)
def test_rendered_reviews_read_back_exactly(codec, conclusions, dilemmas):
    literals = {c.literal for c in conclusions} | set(dilemmas)
    payload = (
        f"(complete 7 100117 {len(conclusions)} "
        f"({' '.join(c.render() for c in conclusions)}) "
        f"({' '.join(d.render() for d in dilemmas)}) "
        f"({' '.join('(no-proof ' + lit.render() + ')' for lit in literals)}))"
    )
    run = read_review_payload(codec.parse(payload), codec, ENGINE)

    assert run.conclusions == tuple(sorted(set(conclusions)))
    assert run.dilemmas == tuple(sorted(set(dilemmas)))
    assert run.inferences == 7
    assert run.engine == ENGINE
    assert {s.literal for s in run.support} == literals

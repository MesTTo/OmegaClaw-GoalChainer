"""Purpose: check the relevance policy's host boundary: one module group prepared whole with retry and named by its identity, one shared budget across stages that every entry point requires, the review's error code for each engine failure, typed entries only, and names that stay data."""

from __future__ import annotations

from pathlib import Path

import pytest

from goal_chainer.domains.loader import read_domain
from goal_chainer.errors import DependencyUnavailableError, InvalidInputError, MettaEngineError, ModuleChanged, ProtocolError
from goal_chainer.relevance import (
    assess_attempt,
    assess_receipt,
    check_receipt,
    engine_identity,
    parse_receipt,
    prepare_service,
)
from goal_chainer.relevance.errors import RelevanceError
from goal_chainer.relevance.policy import (
    POLICY_DIRECTORY,
    POLICY_FILES,
    POLICY_MODULES,
    RELEVANCE_POLICY,
    SHARED_MODULES,
    STATUS_RULE,
    evaluate,
    items,
    prepare,
    term,
)
from goal_chainer.relevance.ranking import rank
from goal_chainer.runtime import evaluator
from goal_chainer.runtime.budget import InferenceBudgetExceeded, ReviewTimeout, RunBudget

from relevance_support import candidate, derived, fresh_process
from request_support import budget as request_budget

UNMOVED = ("Moved", False, False, False, False, False)

# A fresh process loads part of the policy, fails, then prepares again. Run as a script so that
# the process-wide preparation state starts empty. The failure is the engine refusing the third
# module the evaluator imports.
RETRY = """
import json
from metta import MettaError
from goal_chainer.runtime import evaluator
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.relevance import policy
from goal_chainer.relevance.errors import RelevanceError

real = evaluator.load_metta_module
loads = []

def failing(engine, module, **options):
    loads.append(module)
    if len(loads) > 2:
        raise MettaError("injected failure after two modules")
    return real(engine, module, **options)

def budget():
    return RunBudget(inference_budget=10**9, timeout_seconds=600)

try:
    policy.prepare(RunBudget(inference_budget=None, timeout_seconds=1e-9))
    expired = "prepared"
except RelevanceError as error:
    expired = error.code
evaluator.load_metta_module = failing
try:
    policy.prepare(budget())
    first = "prepared"
except RelevanceError as error:
    first = [error.code, str(error.details["error"])]
evaluator.load_metta_module = real
digest = policy.prepare(budget())
verdict = policy.evaluate("gc-relevance-freshness", policy.term("Moved", True, False, False, False, False, False), budget=budget())
print(json.dumps({"expired": expired, "first": first, "digest": digest, "verdict": [verdict[1], verdict[2]]}))
"""


# am[verifies a-rel-metta-policy-1016@fdaa20] am[verifies a-rt-initialize-once-1016@0767f5]
# am[verifies a-rel-mig-group-1018@28c337] am[verifies a-rel-mig-digest-1018@c0f5c0]
def test_a_preparation_that_fails_part_way_is_retried_whole_and_publishes_one_digest() -> None:
    outcome = fresh_process(RETRY)

    # A preparation past its request's deadline is a timeout that loads nothing.
    assert outcome["expired"] == "review-timeout"
    assert outcome["first"] == ["engine-failed", "injected failure after two modules"]
    # The retry imported the modules the failed attempt had not, skipped the two it had, and
    # warmed the policy: it answers, and its digest is the one an undisturbed process publishes.
    assert outcome["verdict"] == ["stale", "withdrawn"]
    assert outcome["digest"] == prepare(request_budget())


# A fresh process imports two modules of a copy of the policy and fails; one of the two then
# changes on disk. The engine still holds its first bytes, so the retry is refused instead of
# publishing a digest of bytes it never loaded (c-rel-retry-digest-mismatch-1016). With the
# change undone, the retry loads the rest and names exactly what an undisturbed process loads.
CHANGED = """
import dataclasses, json, shutil, sys
from pathlib import Path
from metta import MettaError
from goal_chainer.runtime import evaluator
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.relevance import policy
from goal_chainer.relevance.errors import RelevanceError

copy = Path(sys.argv[1]) / "policy"
shutil.copytree(policy.POLICY_DIRECTORY, copy)
policy.RELEVANCE_POLICY = dataclasses.replace(
    policy.RELEVANCE_POLICY, modules=(*sorted(copy.glob("*.metta")), *policy.SHARED_MODULES))
first = policy.RELEVANCE_POLICY.modules[0]
original = first.read_bytes()
real = evaluator.load_metta_module
loads = []

def failing(engine, module, **options):
    loads.append(module)
    if len(loads) > 2:
        raise MettaError("injected failure after two modules")
    return real(engine, module, **options)

def budget():
    return RunBudget(inference_budget=10**9, timeout_seconds=600)

evaluator.load_metta_module = failing
try:
    policy.prepare(budget())
except RelevanceError:
    pass
evaluator.load_metta_module = real
first.write_bytes(original + b'\\n(= (gc-relevance-probe-marker) "changed")\\n')
try:
    policy.prepare(budget())
    changed, details = "prepared", {}
except RelevanceError as error:
    changed, details = error.code, error.details
first.write_bytes(original)
print(json.dumps({"changed": changed, "details": sorted(details), "digest": policy.prepare(budget())}))
"""


# am[verifies a-rel-loads-test-1016@33c69e] am[verifies a-rel-loads-refuse-1016@654aad]
# am[verifies c-rel-retry-digest-mismatch-1016@dd4354] am[verifies a-rel-mig-group-1018@28c337]
def test_a_retry_refuses_a_module_that_changed_after_it_was_imported(tmp_path) -> None:
    outcome = fresh_process(CHANGED, str(tmp_path))

    assert outcome["changed"] == "engine-failed"
    assert outcome["details"] == ["current", "loaded", "path"]
    assert outcome["digest"] == prepare(request_budget())


# am[verifies a-rel-metta-policy-1016@fdaa20] am[verifies a-rel-status-module-1016@db512b]
# am[verifies a-rel-rr-shared-module-1018@13aee9] am[verifies a-rel-mig-group-1018@28c337]
def test_the_policy_is_every_metta_file_of_its_directory_and_the_shared_modules() -> None:
    assert POLICY_FILES == (*sorted(POLICY_DIRECTORY.glob("*.metta")), *SHARED_MODULES)
    assert RELEVANCE_POLICY.modules == POLICY_FILES
    assert RELEVANCE_POLICY.warm_ups == ("gc-justification-warm-up", "gc-relevance-warm-up")
    assert all(path.is_file() for path in SHARED_MODULES) and STATUS_RULE in SHARED_MODULES
    assert {f"relevance/policy/{name}.metta" for name in ("prelude", "evidence", "readset",
                                                          "ranking", "outcome", "warmup")} <= set(POLICY_MODULES)
    assert POLICY_MODULES[-4:] == ("domains/vocabulary.metta", "planning/justification.metta",
                                   "policy/goalchainer_fault_tables.metta",
                                   "policy/goalchainer_deontic.metta")
    assert len(set(POLICY_MODULES)) == len(POLICY_MODULES)


# A review record's review_policy digest is the group's identity, which names each module's bytes
# as the engine imported them, so it is one value per set of policy files.
# am[verifies a-rel-mig-digest-1018@c0f5c0]
def test_the_policys_digest_is_its_module_groups_identity() -> None:
    digest = prepare(request_budget())

    assert digest == evaluator.prepare(RELEVANCE_POLICY, budget=request_budget())
    assert digest.startswith("sha256:") and len(digest) == len("sha256:") + 64


# am[verifies a-rt-run-budget-1016@e046b0] am[verifies a-rel-metta-policy-1016@fdaa20]
def test_a_later_stage_gets_only_what_the_earlier_stages_left() -> None:
    budget = RunBudget(inference_budget=200_000, timeout_seconds=60.0)
    budget.charge(199_999)  # what an earlier stage spent

    with pytest.raises(RelevanceError) as raised:
        evaluate("gc-relevance-freshness", term(*UNMOVED), budget=budget)

    assert raised.value.code == "review-budget-exceeded"
    # The error names the whole bound and the whole spend, never the stage's share.
    assert raised.value.details["budget"] == 200_000
    assert raised.value.details["used"] > 200_000


# am[verifies a-rt-run-budget-1016@e046b0]
def test_a_spent_budget_starts_no_stage() -> None:
    budget = RunBudget(inference_budget=50_000, timeout_seconds=60.0)
    budget.charge(50_000)

    with pytest.raises(RelevanceError) as raised:
        evaluate("gc-relevance-freshness", term(*UNMOVED), budget=budget)

    assert raised.value.code == "review-budget-exceeded" and raised.value.details["used"] == 50_000


# am[verifies a-rt-run-budget-1016@e046b0]
def test_a_deadline_that_has_passed_is_a_typed_timeout() -> None:
    budget = RunBudget(inference_budget=10**9, timeout_seconds=1e-9)

    with pytest.raises(RelevanceError) as raised:
        evaluate("gc-relevance-freshness", term(*UNMOVED), budget=budget)

    assert raised.value.code == "review-timeout"


# Each failure the evaluator raises reaches a relevance caller as the review's own error code, with
# the failure as its cause and its details kept, from a call and from a preparation alike.
# am[verifies a-rel-mig-group-1018@28c337] am[verifies a-rel-review-contract-1016@d0bea9]
@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (InferenceBudgetExceeded(10, 12), "review-budget-exceeded"),
        (ReviewTimeout(1.5), "review-timeout"),
        (DependencyUnavailableError("pymetta is not importable", details={"dependency": "pymetta"}),
         "runtime-unavailable"),
        (ModuleChanged(Path("policy/ranking.metta"), "aa", "bb"), "engine-failed"),
        (MettaEngineError("the engine refused the call", details={"function": "gc-relevance-rank"}), "engine-failed"),
        (ProtocolError("gc-relevance-rank answered 2 results where one was required", details={"answers": []}),
         "engine-output-invalid"),
    ],
    ids=lambda value: value if isinstance(value, str) else type(value).__name__,
)
def test_each_engine_failure_is_the_reviews_typed_error(monkeypatch, failure, code) -> None:
    def failing(*arguments, **options):
        raise failure

    monkeypatch.setattr(evaluator, "evaluate", failing)
    monkeypatch.setattr(evaluator, "prepare", failing)
    for call in (lambda: evaluate("gc-relevance-freshness", term(*UNMOVED), budget=request_budget()),
                 lambda: prepare(request_budget())):
        with pytest.raises(RelevanceError) as raised:
            call()
        assert raised.value.code == code and raised.value.__cause__ is failure
        if code not in ("review-budget-exceeded", "review-timeout"):
            assert dict(raised.value.details) == dict(failure.details)


# A call the evaluator refuses as a defect of the call itself, a missing budget or an entry that
# declares no type, reaches the caller as that InvalidInputError, never as a review outcome.
# am[verifies a-rel-mig-group-1018@28c337] am[verifies a-rel-mig-typed-entries-1018@c150af]
# am[rests-on c-rel-mig-caller-defects-invalid-input-1018@0f439f]
def test_a_call_without_a_budget_or_of_an_untyped_helper_is_the_callers_defect() -> None:
    with pytest.raises(InvalidInputError, match="RunBudget"):
        evaluate("gc-relevance-freshness", term(*UNMOVED), budget=None)  # type: ignore[arg-type]
    with pytest.raises(InvalidInputError, match="RunBudget"):
        prepare(None)  # type: ignore[arg-type]
    with pytest.raises(InvalidInputError, match="declare an arrow type"):
        evaluate("gc-relevance-any", items([True]), budget=request_budget())


# The relevance service's preparation, the engine identity a freshness check reads, and every
# receipt entry point refuse to run without their caller's RunBudget before they do any work, so
# none of them can load or run unbounded.
# am[verifies a-rel-mig-callers-1018@da2f3e] am[verifies a-rel-mig-receipt-1018@6f384d]
# am[verifies a-ie-host-freshness-1018@ff618a] am[verifies a-rel-assess-attempt-1018@20e6ca]
# am[verifies a-rel-check-receipt-public-1018@ac8018]
@pytest.mark.parametrize(
    "call",
    [
        lambda: prepare_service(None),  # type: ignore[arg-type]
        lambda: engine_identity(budget=None),  # type: ignore[arg-type]
        lambda: parse_receipt({}, budget=None),  # type: ignore[arg-type]
        lambda: assess_receipt({}, None, budget=None),  # type: ignore[arg-type]
        lambda: assess_attempt((), None, decided_at=None, budget=None),  # type: ignore[arg-type]
        lambda: check_receipt(None, budget=None),  # type: ignore[arg-type]
    ],
    ids=["prepare_service", "engine_identity", "parse_receipt", "assess_receipt", "assess_attempt", "check_receipt"],
)
def test_the_service_preparation_and_the_receipt_entry_points_require_a_budget(call) -> None:
    with pytest.raises(InvalidInputError, match="runs only under its caller's RunBudget"):
        call()


NAMES_DOMAIN = """
(gc-domain "names")
(gc-policy-version names-v1)
(gc-authority advisory 1 "advise")
(gc-estimator-ceiling measured advisory)
(gc-estimator-ceiling deterministic advisory)
(gc-estimator-ceiling receipt-calibrated advisory)
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling human-asserted advisory)
(gc-action None "None" "an action whose name is the policy's nothing" (authority advisory))
(gc-action car-atom "car-atom" "an action whose name is a MeTTa function" (authority advisory))
(gc-goal if owner individual 0.5 "a goal whose name is a MeTTa form" (priority-source human:test))
(gc-dimension cost cost "what it costs")
(gc-signal match "a signal whose name is a MeTTa function")
(normally r1 (signal match) (candidate None))
(normally r2 (signal match) (candidate car-atom))
(normally r3 (candidate ?a) (may (do ?a)))
"""


# am[verifies c-rel-strings-inert-1016@947e27] am[verifies a-rel-metta-policy-1016@fdaa20]
def test_names_that_spell_metta_code_reach_the_policy_and_come_back_as_data() -> None:
    domain = read_domain(NAMES_DOMAIN, "names", budget=request_budget())
    nothing = candidate(domain, "None", contributions={"if": "positive"})
    head = candidate(domain, "car-atom", contributions={"if": "slightly-positive"})
    review = derived(domain, [head, nothing])

    ranking = rank(review, review.packet.budget.run_budget())

    assert review.readset == {"match"}
    assert ranking.disposition == "propose"
    assert ranking.selected is not None and ranking.selected.id == "None"
    assert [e.action for step in ranking.steps for e in step.eliminated] == ["car-atom"]
    assert [path.goal for path in ranking.appraisals["None"].paths] == ["if"]

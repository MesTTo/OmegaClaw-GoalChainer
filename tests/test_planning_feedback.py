"""Purpose: verify that the planner's tracks come from receipts alone, through planning/feedback.metta,
planning.projection's plan and the JSON request. An applied attempt's current receipt grades each Achieves
literal of its procedure once, inside the attempt's window, and is a trial only when it names the attempt
its producer; a record counts only once complete and only under the library's promotion rule, and holds
while SNARS's track-record cut does, so a promotion appears with enough confirmations and lapses with a
failure or a superseding contradiction. Receipts that disagree with the journal, are malformed or were
issued after the plan's time are refused naming what disagrees, and every stage is charged to the caller's
one budget."""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from importlib import resources

import pytest

from goal_chainer import requests, snars_reasoner
from goal_chainer.domains.loader import packaged_domain
from goal_chainer.errors import InvalidInputError
from goal_chainer.planning import group, projection
from goal_chainer.planning.procedures import SignalLiteral, library_term, literal_text, packaged_procedures
from goal_chainer.planning.projection import Answer, Plan, PlanningRefused, Receipt, Superseded, plan
from goal_chainer.planning.transport import decode, encode
from goal_chainer.relevance.signals import SignalReading
from goal_chainer.runtime.budget import InferenceBudgetExceeded, RunBudget
from planning_support import (
    PROMOTION,
    parsed,
    promoting_task_library,
    receipted_history,
    sectionless_task_control_text,
    task_domain,
    task_section_text,
)
from policy_support import group_answers
from request_support import budget

DOMAIN = task_domain()
AT = datetime(2026, 10, 18, 6, 0, tzinfo=timezone.utc)
SAFE = SignalLiteral("safe_point_reachable")
# reach-safe-point's one act reaches SAFE, and contention keeps reach-by-release's Derive from reaching it.
STATES = {"resource_contention": "detected", "state_preservation_route": "detected", "safe_point_reachable": "refuted"}
REACH = [("start", "reach-safe-point"), ("act", "reach-safe-point"), ("finish", "reach-safe-point")]


# am[verifies a-ev-fb-promotion-1018@2ae86c]
@pytest.fixture(scope="module")
def promoting():
    return promoting_task_library()


# reach-safe-point's attempts at its act run, one per outcome, from two hours before the plan.
# am[verifies a-ev-fb-trials-1018@775554]
def _history(outcomes):
    return receipted_history("reach-safe-point", "run", "continue_task", literal_text(SAFE), outcomes,
                             start=AT - timedelta(hours=2), tag="run")


# am[verifies a-ev-fb-request-receipts-1018@4c8f23]
def _plan(journal, receipts, library, allowance=None) -> Answer:
    readings = [SignalReading(signal, state, "test", "deterministic", observed_at=AT - timedelta(minutes=1))
                for signal, state in STATES.items()]
    return plan((SAFE,), domain=DOMAIN, library=library, readings=readings, journal=tuple(journal), rows=(),
                receipts=receipts, at=AT, budget=allowance or budget())


# am[verifies a-ev-fb-promotion-1018@2ae86c]
def _established(journal, documents, library) -> bool:
    answer = _plan(journal, parsed(documents), library)
    assert isinstance(answer, Plan) and [(s.kind, s.procedure) for s in answer.steps] == REACH
    return answer.established


# Under (Trials 3) (Threshold 0.5) a record counts from its third attributed trial and holds while SNARS's
# belief s / (s + f + 2) exceeds 0.5: two confirmations are too few, three hold, a failure beside them brings
# the belief to 0.5 and the record lapses, and a fourth confirmation restores it (c-ev-fb-snars-track-cut-1018).
# am[verifies a-ev-fb-promotion-1018@2ae86c] am[verifies a-ev-fb-trials-1018@775554] am[rests-on c-ev-fb-snars-track-cut-1018@920fdc]
@pytest.mark.parametrize("outcomes, holds", [
    (["confirmed"] * 2, False),
    (["confirmed"] * 3, True),
    (["confirmed"] * 3 + ["contradicted"], False),
    (["confirmed"] * 4 + ["contradicted"], True),
], ids=["two-confirmed", "three-confirmed", "three-and-a-failure", "four-and-a-failure"])
def test_a_promotion_appears_with_its_trials_and_lapses_with_a_failure(promoting, outcomes, holds: bool) -> None:
    assert _established(*_history(outcomes), promoting) is holds


# A later receipt for the same attempt supersedes the earlier one, and only the current receipt grades: the
# last attempt's second receipt contradicting the literal leaves two confirmations and a failure.
# am[verifies a-ev-fb-trials-1018@775554] am[verifies c-ev-fb-complete-record-1018@80747c]
def test_a_superseding_receipt_regrades_its_attempt(promoting) -> None:
    journal, documents = _history(["confirmed"] * 3)
    assert _established(journal, documents, promoting) is True
    first = documents["run-r2"]
    documents["run-r2b"] = {**copy.deepcopy(first), "issued_at": (datetime.fromisoformat(first["issued_at"])
                                                                   + timedelta(minutes=2)).isoformat()}
    documents["run-r2b"]["observations"][0]["outcome"] = "contradicted"
    journal += [Receipt("run-r2b", "run-i2", "run", "run-a2", True), Superseded("run-r2", "run-r2b")]
    assert _established(journal, documents, promoting) is False


# The packaged library declares no promotion rule, so no record holds however many confirmations it has.
# am[verifies a-ev-fb-promotion-1018@2ae86c]
def test_a_library_without_a_promotion_rule_holds_no_record() -> None:
    library = packaged_procedures(DOMAIN, budget=budget())
    assert library.promotion is None
    assert _established(*_history(["confirmed"] * 5), library) is False


# One trial per attempt and Achieves literal, and only an attempt's own product: two attempts each observed
# twice are two trials, not four, and a confirmation naming no producer, or none at all, grades no trial, so
# each case stays under the rule's three trials where three attributed attempts hold.
# am[verifies a-ev-fb-trials-1018@775554]
@pytest.mark.parametrize("variant", ["observed-twice", "unattributed", "unobserved"])
def test_an_attempt_is_one_trial_per_literal_and_only_as_its_own_product(promoting, variant: str) -> None:
    journal, documents = _history(["confirmed"] * (2 if variant == "observed-twice" else 3))
    if variant == "observed-twice":
        for document in documents.values():
            document["observations"].append({**document["observations"][0], "source": "probe:second-look"})
    elif variant == "unattributed":
        del documents["run-r1"]["observations"][0]["produced_by"]
    else:
        documents["run-r1"]["observations"] = []
    assert _established(journal, documents, promoting) is False


# One observation filed in two receipts grades one attempt (c-rel-rcpt-store-double-count-1017's probe): it names
# the attempt that produced it, so copied from the second attempt's receipt into the third's it is a producer
# other than the third attempt. The request refuses it naming that receipt, and plan, reading every document
# through check_receipt before grading, refuses it in a document built past parse_receipt too
# (c-rel-attempt-rechecks-built-receipts-1018, a-ev-fb-check-before-cut-1018), so no observation is counted twice.
# am[verifies a-rel-rcpt-evidence-keys-1017@40aead] am[verifies c-ev-fb-evidence-counted-once-1018@709878]
def test_an_observation_filed_in_two_receipts_grades_one_attempt(files, promoting) -> None:
    journal, documents = _history(["confirmed"] * 3)
    copied = copy.deepcopy(documents)
    copied["run-r2"]["observations"] = copy.deepcopy(documents["run-r1"]["observations"])
    with pytest.raises(InvalidInputError, match=r"receipts\['run-r2'\].*run-a1"):
        requests.run_request(_request(files, journal, copied), budget=budget())
    receipts = parsed(documents)
    receipts["run-r2"] = replace(receipts["run-r2"], observations=receipts["run-r1"].observations)
    with pytest.raises(InvalidInputError, match="The receipt run-r2 is refused: .*run-a1"):
        _plan(journal, receipts, promoting)


# An observation after the next attempt's application is of that attempt's state, so it grades nothing for
# its own: the first attempt's receipt, issued late, observes the literal after the second was applied.
# am[verifies a-ev-fb-trials-1018@775554] am[rests-on c-ev-fb-window-per-target-1018@f9404b]
def test_an_observation_after_the_next_attempt_was_applied_grades_nothing(promoting) -> None:
    journal, documents = _history(["confirmed"] * 3)
    first, second = documents["run-r0"], documents["run-r1"]
    after = datetime.fromisoformat(second["applied_at"]) + timedelta(minutes=1)
    first["observations"][0]["observed_at"] = after.isoformat()
    first["issued_at"] = (after + timedelta(minutes=1)).isoformat()
    assert _established(journal, documents, promoting) is False


# The journal and receipts are the snapshot at the plan's time, so a receipt issued after it is refused naming
# it, as a reading observed or an attempt dispatched after it is: every receipt four hours late with its
# application and observation (codex-721269e7's probe, where f14fcdd established the procedure), a superseding
# receipt issued late, or the last receipt, whose application closes the second's window, issued late. A receipt
# issued at the plan's time itself is the snapshot's, so the record still holds.
# am[verifies a-ev-fb-snapshot-refused-1018@f8ac61] am[verifies i-ev-fb-future-receipts-count-1018@0846b9]
@pytest.mark.parametrize("late, refused", [
    ("every-receipt", "run-r0"), ("superseding", "run-r2b"), ("window-closing", "run-r2"), ("at-the-plans-time", None),
])
def test_a_receipt_issued_after_the_plans_time_is_refused(promoting, late: str, refused: str | None) -> None:
    journal, documents = _history(["confirmed"] * 3)

    def shift(document, by: timedelta) -> None:
        for field in ("applied_at", "issued_at"):
            document[field] = (datetime.fromisoformat(document[field]) + by).isoformat()
        for observation in document["observations"]:
            observation["observed_at"] = (datetime.fromisoformat(observation["observed_at"]) + by).isoformat()

    if late == "every-receipt":
        for document in documents.values():
            shift(document, timedelta(hours=4))
    elif late == "superseding":
        documents["run-r2b"] = {**copy.deepcopy(documents["run-r2"]), "issued_at": (AT + timedelta(minutes=5)).isoformat()}
        journal += [Receipt("run-r2b", "run-i2", "run", "run-a2", True), Superseded("run-r2", "run-r2b")]
    elif late == "window-closing":
        shift(documents["run-r2"], timedelta(hours=4))
    else:
        documents["run-r2"]["issued_at"] = AT.isoformat()
    if refused is None:
        assert _established(journal, documents, promoting) is True
        return
    with pytest.raises(InvalidInputError, match=f"The receipt {refused} was issued after the plan's time") as error:
        _plan(journal, parsed(documents), promoting)
    assert error.value.details["receipt"] == refused and error.value.details["at"] == AT.isoformat()


# A receipt built past parse_receipt may hold a time that is no timezone-aware instant. plan reads every document
# through relevance's check_receipt before the snapshot cut or any time is compared, so such a document is
# relevance's invalid-record naming the receipt and the field, never a TypeError: a naive or textual issue time,
# none, or a naive application.
# am[verifies a-integrate-feedback-validates-before-cut-1018@914488]
@pytest.mark.parametrize("field, value", [
    ("issued_at", datetime(2026, 10, 18, 5, 0)), ("issued_at", "2026-10-18T05:00:00+00:00"), ("issued_at", None),
    ("applied_at", datetime(2026, 10, 18, 4, 21)),
], ids=["naive-issue", "text-issue", "no-issue", "naive-application"])
def test_a_built_receipt_whose_time_is_no_instant_is_refused_before_the_cut(promoting, field: str, value) -> None:
    journal, documents = _history(["confirmed"] * 3)
    receipts = parsed(documents)
    receipts["run-r2"] = replace(receipts["run-r2"], **{field: value})
    with pytest.raises(InvalidInputError, match=f"The receipt run-r2 .*receipt\\.{field}") as error:
        _plan(journal, receipts, promoting)
    assert error.value.details["receipt"] == "run-r2"
    assert error.value.details["relevance"]["code"] == "invalid-record"


# A record is complete only when every dispatched attempt has a documented current receipt, so a journal
# Receipt whose document the caller does not hold leaves three confirmations uncounted.
# am[verifies a-ev-fb-promotion-1018@2ae86c] am[verifies c-ev-fb-complete-record-1018@80747c]
def test_a_record_with_an_undocumented_receipt_holds_nothing(promoting) -> None:
    journal, documents = _history(["confirmed"] * 4)
    del documents["run-r3"]
    assert _established(journal, documents, promoting) is False


# feedback.metta's attempts directly: the first applied documented receipt's window closes at the second's
# application, as both attempts' procedure achieves the literal's subject, and the last's never; an attempt
# still in flight, dispatched with no receipt, leaves its procedure off the complete list.
# am[verifies a-ev-fb-trials-1018@775554] am[verifies c-ev-fb-complete-record-1018@80747c] am[verifies c-ev-fb-window-per-target-1018@f9404b]
def test_attempts_are_graded_in_windows_and_a_record_in_flight_is_incomplete() -> None:
    from metta import S

    library = library_term(packaged_procedures(DOMAIN, budget=budget()))
    events = ['(Started "i0" "reach-safe-point" "j0")', '(Dispatched "i0" "run" "a0" "sha256:w0" 0)',
              '(Receipt "r0" "i0" "run" "a0" True)', '(Finished "i0")',
              '(Started "i1" "reach-safe-point" "j1")', '(Dispatched "i1" "run" "a1" "sha256:w1" 600000000)',
              '(Receipt "r1" "i1" "run" "a1" True)', '(Finished "i1")']
    documents = ('((Document "r0" "a0" "continue_task" "sha256:w0" (At 60000000) 180000000)'
                 ' (Document "r1" "a1" "continue_task" "sha256:w1" (At 660000000) 780000000))')

    def attempts(journal: list[str]):
        [answer] = group_answers(group.PLANNING, f"(gc-pk-run-feedback-attempts {library} ({' '.join(journal)}) {documents})")
        return answer

    graded, complete = attempts(events)[1:]
    assert graded == ((S.Assess, "r0", "reach-safe-point", 0, (S.Until, "r1")),
                      (S.Assess, "r1", "reach-safe-point", 0, S.Forever))
    assert "reach-safe-point" in complete
    in_flight = attempts([*events, '(Started "i2" "reach-safe-point" "j2")', '(Dispatched "i2" "run" "a2" "sha256:w2" 1200000000)'])
    assert in_flight[1] == graded and "reach-safe-point" not in in_flight[2]


# feedback.metta's counts directly: under (Promotion N) a complete procedure's literal counts once it has N
# trials, each literal on its own, a trial being a confirmation or a miss attributed to the attempt; an
# unattributed grade is no trial, an incomplete procedure counts nothing, and NoPromotion counts nothing.
# am[verifies a-ev-fb-trials-1018@775554] am[verifies a-ev-fb-promotion-1018@2ae86c]
def test_counts_take_attributed_trials_per_literal_of_complete_procedures_under_a_promotion() -> None:
    from metta import S

    trials = ('((Trial "p" 0 "confirmed" "asserted") (Trial "p" 0 "missed" "asserted")'
              ' (Trial "p" 0 "confirmed" "unestablished") (Trial "p" 1 "confirmed" "asserted")'
              ' (Trial "q" 0 "confirmed" "asserted") (Trial "q" 0 "confirmed" "asserted"))')

    def counts(promotion: str, complete: str):
        [answer] = group_answers(group.PLANNING, f"(gc-pk-run-feedback-counts {promotion} {complete} {trials})")
        return answer

    assert counts('(Promotion 2)', '("p" "q")') == (S.Counts, ((S.Count, "p", 0, 1, 1), (S.Count, "q", 0, 2, 0)))
    assert counts('(Promotion 2)', '("q")') == (S.Counts, ((S.Count, "q", 0, 2, 0),))
    assert counts('(Promotion 1)', '("p")') == (S.Counts, ((S.Count, "p", 0, 1, 1), (S.Count, "p", 1, 1, 0)))
    assert counts('NoPromotion', '("p" "q")') == (S.Counts, ())


# Each disagreement between the documents and the journal is refused, naming its kind: a document no journal
# Receipt names, one naming another attempt, an application the journal does not record, another decision's
# digest or another action, two current receipts of one attempt, a supersession out of issue order, and a
# journal Receipt for an attempt never dispatched or an instance never started.
# am[verifies a-ev-fb-request-receipts-1018@4c8f23] am[verifies c-ev-fb-refusals-1018@e097ef]
@pytest.mark.parametrize("kind", ["UnknownReceipt", "AttemptMismatch", "ApplicationMismatch", "DecisionMismatch",
                                  "ActionMismatch", "AmbiguousReceipt", "SupersessionMismatch", "UndispatchedReceipt",
                                  "UnstartedInstance"])
def test_receipts_disagreeing_with_the_journal_are_refused_naming_the_disagreement(promoting, kind: str) -> None:
    journal, documents = _history(["confirmed"] * 3)
    first = documents["run-r0"]
    if kind == "UnknownReceipt":
        documents["run-ghost"] = copy.deepcopy(first)
    elif kind == "AttemptMismatch":
        first["attempt"] = first["observations"][0]["produced_by"] = "run-a9"
    elif kind == "ApplicationMismatch":
        first.update(applied_at=None, observations=[])
    elif kind == "DecisionMismatch":
        first["review_fingerprint"] = "sha256:another-decision"
    elif kind == "ActionMismatch":
        first["action"] = "pause_recoverably"
    elif kind == "AmbiguousReceipt":
        journal.append(Receipt("run-twin", "run-i0", "run", "run-a0", True))
    elif kind == "SupersessionMismatch":
        journal += [Receipt("run-early", "run-i0", "run", "run-a0", True), Superseded("run-r0", "run-early")]
        documents["run-early"] = {**first, "issued_at": first["applied_at"], "observations": []}
    elif kind == "UndispatchedReceipt":
        journal.append(Receipt("run-stray", "run-i0", "run", "run-a9", True))
    else:
        journal.append(Receipt("run-orphan", "run-i9", "run", "run-a0", True))
    with pytest.raises(PlanningRefused, match=kind):
        _plan(journal, parsed(documents), promoting)


# A receipt applied before its attempt was dispatched is relevance's refusal, which plan reports as its own
# InvalidInputError naming the receipt (c-ev-fb-relevance-error-outside-request-1018), and plan takes only
# documents parse_receipt has read.
# am[verifies a-ev-fb-request-receipts-1018@4c8f23] am[rests-on c-ev-fb-relevance-error-outside-request-1018@cfed5e]
def test_plan_refuses_a_receipt_applied_before_its_dispatch_and_unread_documents(promoting) -> None:
    journal, documents = _history(["confirmed"] * 3)
    documents["run-r0"]["applied_at"] = (AT - timedelta(hours=3)).isoformat()
    with pytest.raises(InvalidInputError, match="run-r0"):
        _plan(journal, parsed(documents), promoting)
    with pytest.raises(InvalidInputError, match="parsed receipt-v2 document"):
        _plan(*_history(["confirmed"]), promoting)


# Exhaustion is the caller's error, never an unestablished plan: a budget the plan fits in without receipts,
# but that grading three receipts and their SNARS cut overruns, raises.
# am[verifies a-ev-fb-request-receipts-1018@4c8f23] am[verifies a-rt-rb-one-budget-1018@550ffd]
def test_receipts_are_graded_on_the_callers_budget_and_exhaust_it(promoting) -> None:
    journal, documents = _history(["confirmed"] * 3)
    receipts = parsed(documents)
    _plan(journal, receipts, promoting)

    def spent(given) -> int:
        allowance = budget()
        _plan(journal, given, promoting, allowance)
        return allowance.spent

    bare, graded = spent({}), spent(receipts)
    assert graded > bare

    def tight() -> RunBudget:
        return RunBudget(inference_budget=(bare + graded) // 2, timeout_seconds=600)

    assert isinstance(_plan(journal, {}, promoting, tight()), Plan)
    with pytest.raises(InferenceBudgetExceeded):
        _plan(journal, receipts, promoting, tight())


# A caller's domain and library files, the library declaring PROMOTION, as a request names them.
# am[verifies a-ev-fb-request-receipts-1018@4c8f23]
@pytest.fixture
def files(tmp_path):
    domain = packaged_domain("task-control", budget=budget())
    domain_path = tmp_path / "caller-domain.metta"
    domain_path.write_text(sectionless_task_control_text() + "\n" + task_section_text(domain.signal_ids), encoding="utf-8")
    library_path = tmp_path / "caller-procedures.metta"
    packaged = (resources.files("goal_chainer.planning") / "library" / "task_control.metta").read_text(encoding="utf-8")
    library_path.write_text(f"{packaged}\n{PROMOTION}", encoding="utf-8")
    return domain_path, library_path


# am[verifies a-ev-fb-request-receipts-1018@4c8f23]
def _request(files, journal, receipts) -> dict:
    domain_path, library_path = files
    readings = [{"signal": signal, "state": state, "source": f"test:{signal}", "estimator": "deterministic",
                 "observed_at": AT.isoformat()} for signal, state in STATES.items()]
    return {"operation": "plan", "domain": {"path": str(domain_path)}, "procedures": str(library_path),
            "context": {"review_id": "feedback", "subject": "caller-selected-task", "trigger": "test",
                        "as_of": AT.isoformat(), "authority": "advisory", "readings": readings},
            "goal": encode((SAFE,)), "journal": encode(tuple(journal)), "receipts": receipts}


# The JSON request carries the journal and each Receipt id's receipt-v2 document: its tracks come from them
# alone, and parse_receipt, assess_attempt and SNARS's track are each charged to the caller's allowance.
# am[verifies a-ev-fb-request-receipts-1018@4c8f23] am[verifies a-rt-rb-one-budget-1018@550ffd]
def test_a_plan_request_carries_receipts_whose_records_hold_under_one_budget(files, monkeypatch) -> None:
    journal, documents = _history(["confirmed"] * 3)
    seen: list[tuple[str, object]] = []
    for module, name in ((requests, "parse_receipt"), (projection, "assess_attempt"), (snars_reasoner, "track")):
        def spy(*args, _call=getattr(module, name), _name=name, **kwargs):
            seen.append((_name, kwargs["budget"]))
            return _call(*args, **kwargs)
        monkeypatch.setattr(module, name, spy)
    allowance = budget()
    answer = decode(requests.run_request(_request(files, journal, documents), budget=allowance)["planning"], Answer)
    assert isinstance(answer, Plan) and answer.established is True
    assert {name for name, _ in seen} == {"parse_receipt", "assess_attempt", "track"}
    assert all(charged is allowance for _, charged in seen)
    bare = decode(requests.run_request(_request(files, journal, {}), budget=budget())["planning"], Answer)
    assert isinstance(bare, Plan) and bare.established is False


# A request's receipts are an object of receipt-v2 documents keyed by text: anything else, or a document
# parse_receipt refuses, is the request's own InvalidInputError, naming the receipt.
# am[verifies a-ev-fb-request-receipts-1018@4c8f23] am[rests-on c-ev-fb-relevance-error-outside-request-1018@cfed5e]
@pytest.mark.parametrize("receipts, message", [
    (["run-r0"], "receipts must be a JSON object"),
    ({"": {}}, "a receipts key must be nonempty text"),
    ({"run-r0": {"protocol": "goalchainer-relevance-receipt-v2"}}, r"receipts\['run-r0'\]"),
], ids=["not-an-object", "empty-key", "malformed-document"])
def test_a_malformed_receipt_is_the_requests_own_refusal_naming_it(files, receipts, message: str) -> None:
    journal, _ = _history(["confirmed"])
    with pytest.raises(InvalidInputError, match=message):
        requests.run_request(_request(files, journal, receipts), budget=budget())

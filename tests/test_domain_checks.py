"""Purpose: check the domain core's relational checks as the loader runs them: every fault of a domain is listed in one DomainError, a check answering neither true nor false is the checks' own ProtocolError, whether it checks faults or lists unread signals, a domain's checks run under its caller's budget, and pymetta memoizes no function of the checks' module group."""

from __future__ import annotations

import pytest

from goal_chainer.domains import loader
from goal_chainer.domains.loader import CHECKS_GROUP, read_domain
from goal_chainer.domains.model import DomainError
from goal_chainer.errors import ProtocolError
from goal_chainer.runtime.budget import InferenceBudgetExceeded, RunBudget
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.evaluator import prepare
from request_support import budget as request_budget

BROKEN = """
(gc-domain "probe")
(gc-policy-version probe-v1)
(gc-authority advisory 1 "advise")
(gc-authority shadow 1 "a second tier of rank 1")
(gc-estimator-ceiling measured advisory)
(gc-estimator-ceiling deterministic advisory)
(gc-estimator-ceiling receipt-calibrated nowhere)
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling human-asserted advisory)
(gc-estimator-ceiling human-asserted advisory)
(gc-estimator-ceiling guessed advisory)
(gc-action act "Act" "do it" (authority missing-tier))
(gc-action act "Act again" "twice" (authority advisory))
(gc-goal act owner individual 0.5 "a goal named like an action" (priority-source human:test))
(gc-goal served owner individual 0.5 "a goal" (priority-source human:test))
(gc-signal used "read")
(gc-signal dead "read by nothing")
(gc-dimension cost cost "what it costs")
(normally r1 (signal used) (candidate act))
(normally r1 (signal used) (contributes act ghost positive))
(normally r3 (signal used) (contributes act served worse))
(normally r4 (signal used) (effect act cost negative guessed))
(prefer r1 rMissing)
"""


# Each row of the core's tables finds its fault in one domain, and the one DomainError lists every
# fault, each once, in table order; its signal no rule reads is no fault.
# am[verifies a-rel-nd-validation-runner-1018@f3f0b6] am[verifies c-rel-nd-checks-as-constraints-1018@704895]
# am[verifies a-rel-nd-unread-signals-1018@f57790]
def test_every_relational_fault_of_a_domain_is_listed_in_one_domain_error() -> None:
    with pytest.raises(DomainError) as raised:
        read_domain(BROKEN, "probe", budget=request_budget())

    assert raised.value.faults == (
        'action act is declared more than once',
        'action act is also declared as a goal, so a (contributes A G) literal would be ambiguous',
        "action act's authority missing-tier names an authority tier the domain does not declare",
        "authority advisory's rank 1 shares its rank with another tier, so the tiers are not totally ordered",
        "authority shadow's rank 1 shares its rank with another tier, so the tiers are not totally ordered",
        '(gc-estimator-ceiling receipt-calibrated nowhere) names an authority tier the domain does not declare',
        "(gc-estimator-ceiling human-asserted advisory) is not the class's only gc-estimator-ceiling",
        "(gc-estimator-ceiling guessed advisory) is not one of the shared vocabulary's estimator classes",
        "the theory's (contributes act ghost positive) names something the domain does not declare",
        "the theory's (contributes act served worse) names something the domain does not declare",
        "the theory's (effect act cost negative guessed) names something the domain does not declare",
        'rule label r1 labels more than one rule',
        '(prefer r1 rMissing) must name at least two rule labels the theory declares',
    )
    assert str(raised.value).startswith("probe: 13 faults:\n  action act is declared more than once\n")


# A fact a check cannot read makes the check answer nothing, which is the checks' own mistake and
# never a fault of the domain.
# am[verifies a-rel-nd-validation-runner-1018@f3f0b6] am[verifies a-rel-nd-unread-signals-1018@f57790]
def test_a_check_that_answers_neither_true_nor_false_is_the_checks_own_protocol_error(monkeypatch) -> None:
    from metta import Expression, S

    defect = Expression(S.Defect("duplicate-id", S.Declared("action", "act"), Expression()))
    monkeypatch.setattr(loader, "evaluate", lambda *_, **__: defect)

    with pytest.raises(ProtocolError, match="a mistake in the checks"):
        loader._refuse_faults((("Declared", "action", "act"),), "probe", request_budget())
    with pytest.raises(ProtocolError, match="unread signals, which is a mistake in the checks"):
        loader._unread_signals((("Declared", "signal", "dead"),), "probe", request_budget())


# A fact of a shape the core does not read is still written whole in its fault's line.
# am[verifies a-rel-nd-validation-runner-1018@f3f0b6]
def test_a_fault_names_any_fact_whole_and_a_core_fact_in_its_own_words() -> None:
    from metta import Symbol

    assert loader._fault_line((Symbol("Declared"), "action", "act"), "is declared more than once") == "action act is declared more than once"
    assert loader._fault_line((Symbol("Tier"), "act"), "names nothing") == '(Tier "act") names nothing'


# The checks are charged to the caller's budget like any other stage of its request.
# am[verifies a-rel-nd-validation-runner-1018@f3f0b6] am[verifies c-rel-nd-validation-needs-budget-1018@1989e6]
def test_a_domains_checks_run_under_and_are_charged_to_the_callers_budget() -> None:
    text = (loader._packaged_directory() / "task_control.metta").read_text(encoding="utf-8")
    budget = request_budget()

    read_domain(text, "task-control", budget=budget)

    assert budget.spent > 0
    with pytest.raises(InferenceBudgetExceeded):
        read_domain(text, "task-control", budget=RunBudget(inference_budget=1, timeout_seconds=600))


# pymetta memoizes a recursive function one body calls twice, keyed by its whole arguments, which
# makes each call cost time linear in them (c-brs-k-auto-memo-1018); no function of the checks'
# group may compile so.
# am[verifies a-rel-nd-validation-runner-1018@f3f0b6] am[verifies c-brs-k-auto-memo-1018@9c39b3]
def test_the_engine_memoizes_no_function_of_the_domain_checks() -> None:
    prepare(CHECKS_GROUP, budget=request_budget())
    with metta_engine(None) as engine:
        space = engine.space(CHECKS_GROUP.space)
        names = {str(atom.children[1].children[0]) for atom in space.atoms()
                 if str(atom.children[0]) == "=" and atom.children[1].children}
        memoized = sorted(name for name in names if "cache_call" in space.fn[name].compiled)

    assert {"gc-dc-faults", "gc-dc-arguments-declared", "gc-table-faults"} <= names
    assert memoized == []

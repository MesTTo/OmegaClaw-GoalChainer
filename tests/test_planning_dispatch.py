"""Purpose: verify conditions and proof obligations through CLI and skill dispatch with shared budgets."""

import argparse
import json

import pytest

from goal_chainer import cli, snars_cli
# am[implements a-integrate-session-rebase-1018@73b220]
from goal_chainer.errors import InvalidInputError
from goal_chainer.omegaclaw_skill import run_skill
# am[verifies a-integrate-parent-artifacts-compose-1018@e3c6d7]
from goal_chainer.runtime.budget import InferenceBudgetExceeded, RunBudget
from goal_chainer.snars_models import (
    Evidence,
    ObligationLeaf,
    ObligationRoute,
    SnarsCondition,
    SnarsObligations,
    SubjectiveOpinion,
)
from goal_chainer.snars_reasoner import DEFAULT_HYPOTHESIS, SnarsSession
from request_support import CLI_LIMITS, LIMITS, budget as request_budget
from reading_support import incident_reader

STATEMENT = '(sn p so "is" ((arg s (sn c "service")) (arg o (sn c "healthy"))))'
OPERATIONS = (("condition", "evidence"), ("obligations", "goal-temporal"))


# am[verifies a-integrate-planning-session-surface-1017@f5132a]
# am[verifies a-integrate-parent-artifacts-compose-1018@e3c6d7]
# am[verifies a-integrate-domain-surface-1018@759698]
def through(entry, operation, group, fields=None, flags=(), limits=None):
    request = {"group": group, "operation": operation, "statement": STATEMENT, **(fields or {})}
    bounds = {"inference_budget": 1000, "timeout_seconds": 600, **(limits or {})}
    if entry == "json":
        return snars_cli.run_snars_request(request, budget=RunBudget(**bounds))
    if entry == "skill":
        return run_skill("goalchainer-snars-dispatch", json.dumps({**request, **bounds}))
    parser = argparse.ArgumentParser()
    snars_cli.add_snars_arguments(parser)
    return snars_cli.run_snars_command(parser.parse_args([
        operation, "--statement", STATEMENT, *flags,
    ]), budget=RunBudget(**bounds))


# Transport tests isolate the mocked operation from the real store report's engine work.
# am[verifies a-integrate-parent-artifacts-compose-1018@e3c6d7]
@pytest.fixture
def adapter_state(monkeypatch):
    monkeypatch.setattr(SnarsSession, "state_payload", lambda self: {})


# The adapter must transport the runtime's classification and explicit scenarios unchanged.
# am[verifies a-integrate-planning-session-surface-1017@f5132a]
@pytest.mark.parametrize("entry", ("cli", "json", "skill"))
@pytest.mark.parametrize("operation,group", OPERATIONS)
@pytest.mark.parametrize("threshold", (None, 0.0, 1.0))
def test_planning_dispatch_preserves_defaults_zero_threshold_and_charged_work(
    monkeypatch, adapter_state, entry, operation, group, threshold,
):
    observed = []
    opinion = SubjectiveOpinion(0, 0, 1, 0.5)

    # am[verifies a-integrate-planning-session-surface-1017@f5132a]
    def query(self, statement, **options):
        budget = self.budget
        observed.append((statement, budget.remaining()[0], options))
        budget.charge(23)
        cut = 0.6 if options["threshold"] is None else options["threshold"]
        if operation == "condition":
            return SnarsCondition(statement=statement, statement_id="sid:query", threshold=cut,
                                  negated=options["negated"], status="Undecided",
                                  search="Incomplete", steps=0, opinion=opinion)
        return SnarsObligations(statement, cut, opinion, (
            ObligationRoute((ObligationLeaf(statement, "Open"),), opinion, "Undecided", "(open query)", 1),
        ))

    monkeypatch.setattr(SnarsSession, operation, query)
    fields = {} if threshold is None else {"threshold": threshold}
    flags = () if threshold is None else ("--threshold", str(threshold))
    report = through(entry, operation, group, fields, flags)
    assert len(observed) == 1
    statement, remaining, options = observed[0]
    assert (statement, remaining, options["threshold"]) == (STATEMENT, 1000, threshold)
    if operation == "obligations":
        assert options["hypothesis"] == DEFAULT_HYPOTHESIS
    assert report["result"]["computation"] == {"inference_budget": 1000, "inferences": 23}
    answer = report["result"]["answer"]
    assert answer["statement"] == STATEMENT
    assert answer["threshold"] == (0.6 if threshold is None else threshold)
    if operation == "condition":
        assert (answer["status"], answer["search"]) == ("Undecided", "Incomplete")
        assert answer["negated"] is False
    else:
        assert answer["routes"][0]["leaves"][0]["status"] == "Open"
        assert answer["routes"][0]["scenario"] == answer["hypothesis"]
        assert answer["routes"][0]["scenario_status"] == "Undecided"


# am[verifies a-integrate-planning-session-surface-1017@f5132a]
@pytest.mark.parametrize("entry", ("cli", "json", "skill"))
def test_condition_negation_reaches_the_runtime_without_flipping_a_status_in_python(monkeypatch, adapter_state, entry):
    received = []

    # am[verifies a-integrate-planning-session-surface-1017@f5132a]
    def condition(self, statement, **options):
        received.append(options)
        return {"status": "Undecided", "negated": options["negated"]}

    monkeypatch.setattr(SnarsSession, "condition", condition)
    report = through(entry, "condition", "evidence", {"negated": True}, ("--negated",))
    assert received == [{"threshold": None, "negated": True}]
    assert report["result"]["answer"] == {"status": "Undecided", "negated": True}


# am[verifies a-integrate-planning-session-surface-1017@f5132a]
@pytest.mark.parametrize("entry", ("cli", "json", "skill"))
def test_obligation_hypothesis_is_explicit_and_can_have_zero_positive_evidence(monkeypatch, adapter_state, entry):
    received = []

    # am[verifies a-integrate-planning-session-surface-1017@f5132a]
    def obligations(self, statement, **options):
        received.append(options)
        return {}

    monkeypatch.setattr(SnarsSession, "obligations", obligations)
    through(entry, "obligations", "goal-temporal",
            {"positive": 0, "negative": 3, "base_rate": 0.7, "size": 5},
            ("--positive", "0", "--negative", "3", "--base-rate", "0.7", "--size", "5"))
    assert received == [{"hypothesis": Evidence(0, 3, 0.7), "threshold": None, "max_size": 5}]


# Exhaustion is not an empty route list or an undecided condition.
# am[verifies a-integrate-planning-session-surface-1017@f5132a]
@pytest.mark.parametrize("entry", ("cli", "json", "skill"))
@pytest.mark.parametrize("operation,group", OPERATIONS)
def test_planning_dispatch_propagates_budget_exhaustion(monkeypatch, adapter_state, entry, operation, group):
    # am[verifies a-integrate-planning-session-surface-1017@f5132a]
    def exhausted(self, statement, **options):
        budget = self.budget
        budget.charge(budget.inference_budget)
        budget.remaining()

    monkeypatch.setattr(SnarsSession, operation, exhausted)
    with pytest.raises(InferenceBudgetExceeded):
        through(entry, operation, group)


# am[verifies a-integrate-planning-session-surface-1017@f5132a]
@pytest.mark.parametrize("operation,group", OPERATIONS)
@pytest.mark.parametrize("entry", ("cli", "json", "skill"))
@pytest.mark.parametrize("limit", (0, -1, True, 0.5, "1000"))
def test_planning_dispatch_rejects_invalid_budget_before_querying(monkeypatch, adapter_state, entry, operation, group, limit):
    calls = []
    monkeypatch.setattr(SnarsSession, operation, lambda *args, **kwargs: calls.append(args))
    with pytest.raises(InvalidInputError):
        through(entry, operation, group, limits={"inference_budget": limit})
    assert calls == []


# am[verifies a-integrate-planning-session-surface-1017@f5132a]
# am[verifies i-integrate-dispatch-nontext-statement-1018@40d89f]
@pytest.mark.parametrize("entry", ("json", "skill"))
@pytest.mark.parametrize("operation,group", OPERATIONS)
@pytest.mark.parametrize("statement", (None, "", "   ", 3, True, [], {"term": "query"}))
def test_planning_dispatch_refuses_nontext_and_empty_statements(monkeypatch, adapter_state, entry, operation, group, statement):
    calls = []
    monkeypatch.setattr(SnarsSession, operation, lambda *args, **kwargs: calls.append(args))
    with pytest.raises(InvalidInputError):
        through(entry, operation, group, {"statement": statement})
    assert calls == []


# Omitted thresholds must reach each operation's own default; zero is never mistaken for omission.
# am[verifies a-integrate-planning-session-surface-1017@f5132a]
@pytest.mark.parametrize("entry", ("cli", "json", "skill"))
@pytest.mark.parametrize("threshold", (None, 0.0))
def test_existing_truth_threshold_default_is_preserved(monkeypatch, adapter_state, entry, threshold):
    received = []

    # am[verifies a-integrate-planning-session-surface-1017@f5132a]
    def truth(self, statement, *, threshold=0.5):
        received.append(threshold)
        return {}

    monkeypatch.setattr(SnarsSession, "truth", truth)
    through(entry, "truth", "trust-discovery",
            {} if threshold is None else {"threshold": threshold},
            () if threshold is None else ("--threshold", str(threshold)))
    assert received == [0.5 if threshold is None else threshold]


# The real entry points read a persistent observation without adding hypothetical events.
# am[verifies a-integrate-planning-session-surface-1017@f5132a]
def test_real_cli_and_skill_planning_queries_preserve_the_observed_store(tmp_path, capsys):
    database = tmp_path / "observations.sqlite3"
    with SnarsSession.persistent(database, budget=request_budget(), reader=incident_reader()) as session:
        session.believe(STATEMENT, evidence=Evidence(8, 0), source="inspection:1")
        before = session.state_payload()
    for operation, group, negated in (
        ("condition", "evidence", False), ("condition", "evidence", True),
        ("obligations", "goal-temporal", False),
    ):
        assert cli.main(["snars", *CLI_LIMITS, operation, "--database", str(database),
                         "--statement", STATEMENT, "--json", *(["--negated"] if negated else [])]) == 0
        command = json.loads(capsys.readouterr().out)
        skill = run_skill("goalchainer-snars-dispatch", json.dumps({
            "group": group, "operation": operation, "database": str(database),
            "statement": STATEMENT, "negated": negated,
            **LIMITS,
        }))
        assert command["result"]["answer"] == json.loads(json.dumps(skill["result"]["answer"]))
        answer = command["result"]["answer"]
        if operation == "condition":
            assert (answer["status"], answer["search"]) == ("Fails" if negated else "Holds", "Witness")
            assert answer["negated"] is negated
        else:
            assert any(all(leaf["status"] == "Holds" for leaf in route["leaves"])
                       for route in answer["routes"])
        assert command["result"]["computation"]["inferences"] > 0
        with SnarsSession.persistent(database, budget=request_budget(), reader=incident_reader()) as session:
            assert session.state_payload() == before

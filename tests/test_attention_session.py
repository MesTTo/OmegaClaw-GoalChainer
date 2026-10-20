"""Purpose: verify forward queries under their session's one budget through sessions, the CLI and
JSON dispatch cores and saved worlds."""

import argparse

import pytest

from request_support import budget as request_budget
from copied_package import copy_package, run_fresh
from goal_chainer import snars_cli
from goal_chainer.runtime.budget import InferenceBudgetExceeded, RunBudget
from goal_chainer.snars_models import Evidence
from goal_chainer.errors import InvalidInputError
from goal_chainer.snars_reasoner import SnarsOperation, SnarsSession
from reading_support import incident_reader

EDGE_AB = '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
EDGE_BC = '(sn p so "is" ((arg s (sn c "b")) (arg o (sn c "c"))))'
QUERY = '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "c"))))'



# am[verifies a-integrate-ecan-forward-query-interface-1017]
def _fields(operation):
    assert operation.operation == "forward-query"
    assert operation.payload[0] == "forward-query"
    return {row[0]: row[1] for row in operation.payload[1:]}


# A forward witness lives in its result; the next ordinary ask still sees only authored events,
# also after a session whose budget stopped the query.
# am[verifies a-integrate-ecan-forward-query-interface-1017] am[verifies a-rt-rbs-session-budget-1018@8c3da2]
def test_forward_query_replays_beliefs_without_committing_its_derived_support(tmp_path):
    database = tmp_path / "beliefs.sqlite3"
    with SnarsSession.persistent(database, budget=request_budget(), include_goalchainer_policy=False,
                                 reader=incident_reader()) as session:
        for index, statement in enumerate((EDGE_AB, EDGE_BC)):
            session.believe(statement, evidence=Evidence(8, 0), source=f"observation-{index}")
        before = session.state_payload()
        assert session.ask(QUERY).payload == ["answers", []]
        spent = session.budget.spent
        result = session.forward_query(QUERY)
        fields = _fields(result)
        assert fields["status"] == "Witness" and fields["steps"] > 0
        assert len(fields["answers"]) == 1 and session.budget.spent > spent
        assert session.state_payload() == before
        assert session.ask(QUERY).payload == ["answers", []]
        assert session.forward_query(QUERY).payload == result.payload
    stopped = RunBudget(inference_budget=1, timeout_seconds=900)
    with SnarsSession.persistent(database, budget=stopped, include_goalchainer_policy=False,
                                 reader=incident_reader()) as session:
        with pytest.raises(InferenceBudgetExceeded):
            session.forward_query(QUERY)
    assert stopped.spent >= 1
    with SnarsSession.persistent(database, budget=request_budget(), include_goalchainer_policy=False,
                                 reader=incident_reader()) as session:
        assert session.state_payload() == before
        assert session.ask(QUERY).payload == ["answers", []]


# Ground construction and its existing codec reject a query pattern before running a batch.
# am[verifies a-integrate-ecan-forward-query-interface-1017]
def test_forward_query_refuses_variables_before_execution():
    calls = []
    with SnarsSession.ephemeral(budget=request_budget(), execute=lambda batch, budget: calls.append(batch),
                                reader=incident_reader()) as session:
        with pytest.raises(InvalidInputError, match="variables"):
            session.forward_query('(sn p so "is" ((arg s (sn c "a")) (arg o $target)))')
    assert calls == []


# A caller shares one RunBudget across stages: the session hands every batch that same budget, so
# a batch gets what the earlier stages left and its spend comes off the caller's.
# am[verifies a-integrate-ecan-forward-query-interface-1017] am[verifies a-rt-rbs-session-budget-1018@8c3da2]
def test_a_session_passes_its_callers_budget_to_every_batch_without_restarting_it():
    budget = RunBudget(inference_budget=20, timeout_seconds=900)
    budget.charge(7)
    observed = []

    # am[verifies a-integrate-ecan-forward-query-interface-1017] am[verifies a-rt-rbs-session-budget-1018@8c3da2]
    def execute(batch, received):
        observed.append((batch.includes, received is budget, received.remaining()[0]))
        received.charge(3)
        return ('(goalchainer-snars-v1 forward-query ok '
                '(forward-query (status Incomplete) (steps 0) (answers ())))',)

    with SnarsSession.ephemeral(budget=budget, execute=execute, include_goalchainer_policy=False,
                                reader=incident_reader()) as session:
        assert _fields(session.forward_query(QUERY))["status"] == "Incomplete"
        assert _fields(session.forward_query(QUERY))["status"] == "Incomplete"
    assert observed == [(frozenset({"attention"}), True, 13), (frozenset({"attention"}), True, 10)]
    assert budget.spent == 13


# A session never runs unbounded: a missing budget is refused before any store opens, so a refused
# persistent session leaves no database file.
# am[verifies a-rt-rbs-session-budget-1018@8c3da2]
def test_a_session_without_a_budget_is_refused_before_its_store_opens(tmp_path):
    database = tmp_path / "refused.sqlite3"
    for budget in (None, 900, {"inference_budget": None, "timeout_seconds": 900}):
        with pytest.raises(InvalidInputError, match="never unbounded"):
            SnarsSession.persistent(database, budget=budget, reader=incident_reader())  # type: ignore[arg-type]
        with pytest.raises(InvalidInputError, match="never unbounded"):
            SnarsSession.ephemeral(budget=budget, reader=incident_reader())  # type: ignore[arg-type]
    assert not database.exists()


# The existing step count keeps its meaning. The CLI and JSON cores run under the budget their
# caller built from the request's limits, and a forward query reports what it charged of it; a
# dispatch request naming its own limits is refused, since they belong to the skill's envelope.
# am[verifies a-integrate-ecan-forward-query-interface-1017] am[verifies a-rt-rbr-snars-envelope-1018@920fe4]
# am[verifies a-integrate-domain-surface-1018@759698]
def test_cli_and_json_forward_queries_report_the_budget_they_charged(monkeypatch):
    observed = []

    # am[verifies a-integrate-ecan-forward-query-interface-1017] am[verifies a-rt-rbr-snars-envelope-1018@920fe4]
    def forward(self, statement):
        observed.append((statement, self.budget.inference_budget))
        self.budget.charge(19)
        return SnarsOperation("forward-query", ["forward-query", ["status", "Incomplete"]], "record")

    monkeypatch.setattr(SnarsSession, "forward_query", forward)
    request = {"group": "evidence", "operation": "forward-query", "statement": QUERY, "budget": 8}
    parser = argparse.ArgumentParser()
    snars_cli.add_snars_arguments(parser)
    cli = snars_cli.run_snars_command(parser.parse_args(["forward-query", "--statement", QUERY, "--budget", "8"]),
                                      budget=RunBudget(inference_budget=1000, timeout_seconds=900))
    dispatched = snars_cli.run_snars_request(request, budget=RunBudget(inference_budget=1000, timeout_seconds=900))
    assert observed == [(QUERY, 1000), (QUERY, 1000)]
    for report in (cli, dispatched):
        assert report["result"]["answer"]["operation"] == "forward-query"
        assert report["result"]["computation"] == {"inference_budget": 1000, "inferences": 19}
    for limit in ("inference_budget", "timeout_seconds"):
        with pytest.raises(InvalidInputError, match="unknown fields"):
            snars_cli.run_snars_request({**request, limit: 1000}, budget=request_budget())
    with pytest.raises(SystemExit):
        parser.parse_args(["forward-query", "--statement", QUERY, "--inference-budget", "1000"])
    assert len(observed) == 2


# A saved optional world replays its installers, then answers from a relocated package as before.
# am[verifies a-integrate-ecan-hook-installation-review-1017]
# am[verifies a-integrate-ecan-forward-query-interface-1017]
def test_image_rehydration_preserves_the_attention_world_and_its_query(tmp_path):
    script = f'''
import json
from goal_chainer import snars_engine
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.snars_models import Evidence
from goal_chainer.semantic_reader import default_reader
from goal_chainer.snars_reasoner import SnarsSession
snars_engine.start_worlds_from_images(Path({str(tmp_path / "images")!r}))
budget = RunBudget(inference_budget=None, timeout_seconds=900)
with SnarsSession.ephemeral(budget=budget, include_goalchainer_policy=False,
                            reader=default_reader(budget=budget)) as session:
    for index, statement in enumerate({(EDGE_AB, EDGE_BC)!r}):
        session.believe(statement, evidence=Evidence(8, 0), source=f"source-{{index}}")
    result = session.forward_query({QUERY!r})
world = next(world for world in snars_engine.compiled_worlds() if world.includes == ("attention",))
print(json.dumps({{"origin": world.origin, "modules": world.modules, "answer": result.payload}}))
'''
    first = run_fresh(copy_package(tmp_path / "first"), script)
    second = run_fresh(copy_package(tmp_path / "relocated"), script)
    assert first.pop("origin") == "compiled"
    assert second.pop("origin") == "image"
    assert first == second


# Public defaults include the incident policy and replay a persistent store before the query.
# am[verifies a-integrate-default-forward-query-entry-1017] am[verifies a-rt-rbr-snars-envelope-1018@920fe4]
def test_default_persistent_session_answers_through_the_real_json_entry(tmp_path):
    database = tmp_path / "beliefs.sqlite3"
    with SnarsSession.persistent(database, budget=request_budget(), reader=incident_reader()) as session:
        session.believe(EDGE_AB, evidence=Evidence(8, 0), source="observation")
        before = session.state_payload()
    report = snars_cli.run_snars_request({
        "group": "evidence", "operation": "forward-query", "request": "",
        "database": str(database), "statement": EDGE_AB,
    }, budget=request_budget())
    answer = report["result"]["answer"]
    assert answer["operation"] == "forward-query"
    fields = {row[0]: row[1] for row in answer["payload"][1:]}
    assert fields["status"] == "Witness" and fields["steps"] == 0
    assert len(fields["answers"]) == 1
    assert report["result"]["computation"]["inferences"] > 0
    with SnarsSession.persistent(database, budget=request_budget(), reader=incident_reader()) as session:
        assert session.state_payload() == before

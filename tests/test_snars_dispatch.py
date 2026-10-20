"""Purpose: test the OmegaClaw JSON dispatch into the SNARS CLI's operations: the groups it allows,
its defaults, the evidence it gives SNARS and the requests it refuses."""

from __future__ import annotations

import argparse

import pytest

from request_support import budget as request_budget
from goal_chainer import snars_cli
from goal_chainer.snars_models import Evidence
from goal_chainer.errors import InvalidInputError
from goal_chainer.snars_reasoner import SnarsSession

STATEMENT = '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'


def test_dispatch_validates_group_operation_and_defaults(monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(
        snars_cli,
        "run_snars_command",
        lambda args, *, budget: captured.append(args) or {"operation": args.operation},
    )

    result = snars_cli.run_snars_request(
        {
            "group": "trust-discovery",
            "operation": "mine",
            "minimum_support": 3,
        },
    budget=request_budget())

    assert result["group"] == "trust-discovery"
    assert captured[0].operation == "mine"
    assert captured[0].minimum_support == 3
    assert captured[0].source == "omegaclaw"


# A request that names no base rate gives SNARS evidence without one, from the JSON dispatch and
# from the command line alike, and one that names a rate gives that rate.
# am[verifies a-ev-br-callers-1017@1261b7]
# am[verifies a-integrate-domain-surface-1018@759698]
@pytest.mark.parametrize("rate", [None, 0.7])
def test_evidence_carries_a_base_rate_only_when_the_request_names_one(monkeypatch, rate) -> None:
    given = []
    monkeypatch.setattr(
        SnarsSession,
        "what_if",
        lambda self, hypothesis, query, **options: given.append(options["evidence"]) or {},
    )
    named = {} if rate is None else {"base_rate": rate}
    flags = [] if rate is None else ["--base-rate", str(rate)]
    parser = argparse.ArgumentParser()
    snars_cli.add_snars_arguments(parser)

    snars_cli.run_snars_request(
        {"group": "counterfactual", "operation": "what-if", "hypothesis": STATEMENT, "query": STATEMENT, **named},
    budget=request_budget())
    snars_cli.run_snars_command(
        parser.parse_args(["what-if", "--request", "", "--hypothesis", STATEMENT, "--query", STATEMENT, *flags]),
    budget=request_budget())

    assert given == [Evidence(1.0, 0.0, rate)] * 2


# Evidence the model refuses is the dispatch's typed refusal, so the skill reports it as an input
# error instead of raising the model's ValueError past its handler.
# am[verifies a-rt-nr-repair-1018@72901e]
@pytest.mark.parametrize("evidence", [{"positive": 10**400}, {"negative": -1.0}, {"base_rate": 10**400}])
def test_evidence_the_model_refuses_is_the_dispatchs_typed_refusal(monkeypatch, evidence) -> None:
    monkeypatch.setattr(SnarsSession, "what_if", lambda self, hypothesis, query, **options: {})

    with pytest.raises(InvalidInputError, match="evidence is invalid"):
        snars_cli.run_snars_request(
            {"group": "counterfactual", "operation": "what-if", "hypothesis": STATEMENT, "query": STATEMENT,
             **evidence},
        budget=request_budget())


@pytest.mark.parametrize(
    "payload",
    [
        {"group": "unknown", "operation": "inspect"},
        {"group": "counterfactual", "operation": "mine"},
        {
            "group": "trust-discovery",
            "operation": "inspect",
            "unexpected": True,
        },
    ],
)
def test_dispatch_rejects_invalid_typed_requests(payload) -> None:
    with pytest.raises(InvalidInputError):
        snars_cli.run_snars_request(payload, budget=request_budget())

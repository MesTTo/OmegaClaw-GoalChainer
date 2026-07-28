from __future__ import annotations

import pytest

from goal_chainer import snars_cli
from goal_chainer.snars_models import SnarsInvalidInputError


def test_dispatch_validates_group_operation_and_defaults(monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(
        snars_cli,
        "run_snars_command",
        lambda args: captured.append(args) or {"operation": args.operation},
    )

    result = snars_cli.run_snars_request(
        {
            "group": "trust-discovery",
            "operation": "mine",
            "minimum_support": 3,
        }
    )

    assert result["group"] == "trust-discovery"
    assert captured[0].operation == "mine"
    assert captured[0].minimum_support == 3
    assert captured[0].source == "omegaclaw"


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
    with pytest.raises(SnarsInvalidInputError):
        snars_cli.run_snars_request(payload)

from __future__ import annotations

import json

from goal_chainer import cli
from goal_chainer.snars_models import SnarsDependencyUnavailableError


def test_snars_command_emits_structured_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "run_snars_command",
        lambda args: {
            "operation": args.operation,
            "mode": "native",
            "native_snars_ran": True,
            "state": {"kind": "ephemeral"},
            "result": {"rows": []},
        },
    )

    exit_code = cli.main(["snars", "inspect", "--request", "", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["operation"] == "inspect"
    assert payload["native_snars_ran"] is True


def test_native_failure_is_nonzero_with_stable_json_error(monkeypatch, capsys) -> None:
    def fail(argv):
        raise SnarsDependencyUnavailableError(
            "Mettabase is missing.",
            details={"path": "/missing"},
        )

    monkeypatch.setattr(cli, "_main", fail)

    exit_code = cli.main(["snars", "inspect", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload == {
        "ok": False,
        "mode": "native",
        "native_snars_ran": False,
        "error": {
            "code": "dependency_unavailable",
            "message": "Mettabase is missing.",
            "details": {"path": "/missing"},
        },
    }

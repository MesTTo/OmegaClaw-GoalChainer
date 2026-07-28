from __future__ import annotations

import json

from goal_chainer import cli
from goal_chainer.directive import build_demo_plan, create_plan


def test_directive_demo_cli_reports_verified_stages(capsys) -> None:
    exit_code = cli.main(["directive", "demo", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["operation"] == "demo"
    assert all(payload["verified"].values())
    assert payload["stages"][1]["task_states"]["publish_update"] == ("upstream-blocked")


def test_directive_cli_inspects_a_durable_plan(tmp_path, capsys) -> None:
    path = create_plan(tmp_path / "cli-plan.metta", build_demo_plan())

    exit_code = cli.main(
        [
            "directive",
            "task-state",
            "--plan",
            str(path),
            "--task",
            "collect_evidence",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["operation"] == "task-state"
    assert payload["result"] == {
        "task": "collect_evidence",
        "state": "ready",
    }

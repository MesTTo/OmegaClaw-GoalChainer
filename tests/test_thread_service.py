from __future__ import annotations

import json

import pytest
from thread_spec_fixture import VALID_THREAD_SPEC

from goal_chainer import cli
from goal_chainer.thread_models import ThreadExecutionError
from goal_chainer.thread_service import run_thread_request


def paths(tmp_path):
    spec = tmp_path / "thread.md"
    spec.write_text(VALID_THREAD_SPEC)
    return {
        "spec": str(spec),
        "plan": str(tmp_path / "thread.metta"),
        "audit": str(tmp_path / "thread.jsonl"),
    }


def test_dispatch_compiles_inspects_routes_and_renders(tmp_path) -> None:
    state = paths(tmp_path)

    compiled = run_thread_request({"operation": "compile", **state})
    inspected = run_thread_request({"operation": "inspect", **state})
    routed = run_thread_request(
        {
            "operation": "route",
            **state,
            "task": "collect-evidence",
            "local_iterations": 0,
            "hard": False,
        }
    )
    rendered = run_thread_request({"operation": "render", **state})

    assert compiled["protocol"] == "goalchainer-thread-v1"
    assert inspected["result"]["snapshot"]["board"]["ready"] == ["collect-evidence"]
    assert routed["result"]["target"] == "worker"
    assert "## Board" in rendered["result"]


def test_dispatch_rejects_unknown_fields_before_runtime(tmp_path) -> None:
    with pytest.raises(ThreadExecutionError, match="unknown fields"):
        run_thread_request(
            {
                "operation": "demo",
                "directory": str(tmp_path),
                "surprise": True,
            }
        )


def test_thread_cli_registers_and_compiles_a_specification(
    tmp_path,
    capsys,
) -> None:
    state = paths(tmp_path)

    exit_code = cli.main(
        [
            "thread",
            "compile",
            "--spec",
            state["spec"],
            "--plan",
            state["plan"],
            "--audit",
            state["audit"],
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["operation"] == "compile"
    assert payload["inspection"]["snapshot"]["board"]["ready"] == ["collect-evidence"]


def test_thread_cli_help_renders(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["thread", "--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    for operation in (
        "compile",
        "inspect",
        "ui-inspect",
        "ui-sync",
        "ui-observe",
        "ui-watch",
        "dispatch-due",
        "ui-disconnect",
        "bind-session",
        "route",
        "record-usage",
        "run",
        "render",
        "demo",
    ):
        assert operation in output

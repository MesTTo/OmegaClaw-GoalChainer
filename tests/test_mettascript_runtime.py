from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from goal_chainer.mettascript_runtime import (
    MAX_SOURCE_BYTES,
    SOURCE_RUNNER_PATH,
    MeTTaScriptRuntime,
)
from goal_chainer.thread_models import ThreadExecutionError

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_runner_resolves_mettascript_from_an_explicit_module_root(
    tmp_path: Path,
) -> None:
    installed_runner = tmp_path / "share" / "integrations" / "mettascript"
    installed_runner.mkdir(parents=True)
    runner_path = installed_runner / "runner.mjs"
    shutil.copyfile(SOURCE_RUNNER_PATH, runner_path)

    runtime = MeTTaScriptRuntime(
        runner_path=runner_path,
        module_root=REPO_ROOT,
    )

    assert runtime.run_batch("!(+ 1 2)").output_lines == ("3",)


def test_runtime_rejects_a_missing_mettascript_package(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ThreadExecutionError,
        match="MeTTaScript Node package is unavailable",
    ):
        MeTTaScriptRuntime(module_root=tmp_path)


def test_runtime_rejects_oversized_source() -> None:
    runtime = MeTTaScriptRuntime(module_root=REPO_ROOT)

    with pytest.raises(ThreadExecutionError, match="source-size limit"):
        runtime.run_batch("a" * (MAX_SOURCE_BYTES + 1))


def test_runtime_rejects_malformed_runner_json(tmp_path: Path) -> None:
    runner_path = tmp_path / "runner.mjs"
    runner_path.write_text('process.stdout.write("not-json");\n', encoding="utf-8")
    runtime = MeTTaScriptRuntime(
        runner_path=runner_path,
        module_root=REPO_ROOT,
    )

    with pytest.raises(ThreadExecutionError, match="malformed runner JSON"):
        runtime.run_batch("!(+ 1 2)")


def test_runtime_surfaces_bounded_runner_error(tmp_path: Path) -> None:
    runner_path = tmp_path / "runner.mjs"
    runner_path.write_text(
        'process.stderr.write(JSON.stringify({message:"reduction failed"}));\n'
        "process.exitCode = 1;\n",
        encoding="utf-8",
    )
    runtime = MeTTaScriptRuntime(
        runner_path=runner_path,
        module_root=REPO_ROOT,
    )

    with pytest.raises(ThreadExecutionError) as raised:
        runtime.run_batch("!(+ 1 2)")

    assert raised.value.details["runtime"] == "reduction failed"

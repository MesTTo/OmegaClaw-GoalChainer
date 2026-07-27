from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

import goal_chainer.snars_runtime as snars_runtime
from goal_chainer.snars_models import (
    SnarsDependencyUnavailableError,
    SnarsInvalidInputError,
    SnarsPettaExecutionError,
    SnarsTimeoutError,
)
from goal_chainer.snars_runtime import SnarsRuntime, resolve_runtime

COMMIT = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture(autouse=True)
def fixed_mettabase_commit(monkeypatch):
    monkeypatch.setattr(snars_runtime, "_mettabase_commit", lambda _root: COMMIT)


def test_resolver_precedence_is_explicit_then_environment_then_vendored(
    tmp_path, monkeypatch
):
    explicit = _mettabase_tree(tmp_path / "explicit")
    configured = _mettabase_tree(tmp_path / "configured")
    vendored = _mettabase_tree(tmp_path / "repo" / "external" / "mettabase")
    petta = _petta_tree(tmp_path / "petta")
    swipl = _executable(tmp_path / "swipl", "print('unused')\n")
    env = {"GOALCHAINER_METTABASE_DIR": str(configured)}

    diagnostics = resolve_runtime(
        mettabase_dir=explicit,
        petta_dir=petta,
        swipl=swipl,
        env=env,
        repo_root=tmp_path / "repo",
    )
    assert diagnostics.mettabase_dir == explicit.resolve()

    diagnostics = resolve_runtime(
        petta_dir=petta,
        swipl=swipl,
        env=env,
        repo_root=tmp_path / "repo",
    )
    assert diagnostics.mettabase_dir == configured.resolve()

    diagnostics = resolve_runtime(
        petta_dir=petta,
        swipl=swipl,
        env={},
        repo_root=tmp_path / "repo",
    )
    assert diagnostics.mettabase_dir == vendored.resolve()

    development = _mettabase_tree(tmp_path / "development")
    monkeypatch.setattr(snars_runtime, "DEVELOPMENT_METTABASE_DIR", development)
    diagnostics = resolve_runtime(
        petta_dir=petta,
        swipl=swipl,
        env={},
        repo_root=tmp_path / "repo-without-vendored-checkout",
    )
    assert diagnostics.mettabase_dir == development.resolve()


def test_resolver_reports_mettabase_unavailable_after_all_candidates(
    tmp_path, monkeypatch
):
    missing_development = tmp_path / "missing-development"
    monkeypatch.setattr(
        snars_runtime,
        "DEVELOPMENT_METTABASE_DIR",
        missing_development,
    )
    petta = _petta_tree(tmp_path / "petta")
    swipl = _executable(tmp_path / "swipl", "print('unused')\n")

    with pytest.raises(SnarsDependencyUnavailableError) as caught:
        resolve_runtime(
            petta_dir=petta,
            swipl=swipl,
            env={},
            repo_root=tmp_path / "repo",
        )

    assert caught.value.details["development_path"] == str(missing_development)
    assert caught.value.code == "dependency_unavailable"


def test_invalid_explicit_override_does_not_fall_back(tmp_path):
    vendored = _mettabase_tree(tmp_path / "repo" / "external" / "mettabase")
    petta = _petta_tree(tmp_path / "petta")
    swipl = _executable(tmp_path / "swipl", "print('unused')\n")
    invalid = tmp_path / "missing"

    with pytest.raises(
        SnarsDependencyUnavailableError,
        match="explicit Mettabase checkout",
    ):
        resolve_runtime(
            mettabase_dir=invalid,
            petta_dir=petta,
            swipl=swipl,
            env={},
            repo_root=tmp_path / "repo",
        )

    assert vendored.is_dir()


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("lib/mettabase/snars.metta", "SNARS program"),
        ("lib/mettabase/snars/kernel.pl", "SNARS kernel"),
        ("lib/mettabase/hyperbase.metta", "HyperBase program"),
    ],
)
def test_missing_mettabase_dependency_is_typed(tmp_path, relative_path, message):
    mettabase = _mettabase_tree(tmp_path / "mettabase")
    (mettabase / relative_path).unlink()
    petta = _petta_tree(tmp_path / "petta")
    swipl = _executable(tmp_path / "swipl", "print('unused')\n")

    with pytest.raises(SnarsDependencyUnavailableError, match=message):
        resolve_runtime(
            mettabase_dir=mettabase,
            petta_dir=petta,
            swipl=swipl,
            env={},
        )


def test_missing_petta_and_swipl_dependencies_are_typed(tmp_path):
    mettabase = _mettabase_tree(tmp_path / "mettabase")
    missing_petta = _petta_tree(tmp_path / "petta")
    (missing_petta / "src" / "main.pl").unlink()
    swipl = _executable(tmp_path / "swipl", "print('unused')\n")

    with pytest.raises(SnarsDependencyUnavailableError, match="PeTTa entrypoint"):
        resolve_runtime(
            mettabase_dir=mettabase,
            petta_dir=missing_petta,
            swipl=swipl,
            env={},
        )

    petta = _petta_tree(tmp_path / "valid-petta")
    with pytest.raises(SnarsDependencyUnavailableError, match="SWI-Prolog"):
        resolve_runtime(
            mettabase_dir=mettabase,
            petta_dir=petta,
            swipl=tmp_path / "missing-swipl",
            env={},
        )


def test_diagnostics_record_commit_and_every_resolved_path(tmp_path):
    mettabase = _mettabase_tree(tmp_path / "mettabase")
    petta = _petta_tree(tmp_path / "petta")
    swipl = _executable(tmp_path / "swipl", "print('unused')\n")

    diagnostics = resolve_runtime(
        mettabase_dir=mettabase,
        petta_dir=petta,
        swipl=swipl,
        require_text_ingestion=True,
        env={},
    )

    assert diagnostics.mettabase_commit == COMMIT
    assert diagnostics.mettabase_dir == mettabase.resolve()
    assert (
        diagnostics.snars_program == mettabase.resolve() / "lib/mettabase/snars.metta"
    )
    assert (
        diagnostics.snars_kernel
        == mettabase.resolve() / "lib/mettabase/snars/kernel.pl"
    )
    assert (
        diagnostics.hyperbase_program
        == mettabase.resolve() / "lib/mettabase/hyperbase.metta"
    )
    assert diagnostics.python_package == mettabase.resolve() / "src/mettabase"
    assert diagnostics.petta_dir == petta.resolve()
    assert diagnostics.petta_main == petta.resolve() / "src/main.pl"
    assert diagnostics.swipl == swipl.resolve()


def test_python_package_is_only_required_for_text_ingestion(tmp_path):
    mettabase = _mettabase_tree(tmp_path / "mettabase")
    (mettabase / "src" / "mettabase" / "__init__.py").unlink()
    petta = _petta_tree(tmp_path / "petta")
    swipl = _executable(tmp_path / "swipl", "print('unused')\n")

    diagnostics = resolve_runtime(
        mettabase_dir=mettabase,
        petta_dir=petta,
        swipl=swipl,
        require_text_ingestion=False,
        env={},
    )
    assert diagnostics.python_package is None

    with pytest.raises(
        SnarsDependencyUnavailableError,
        match="Python package for text ingestion",
    ):
        resolve_runtime(
            mettabase_dir=mettabase,
            petta_dir=petta,
            swipl=swipl,
            require_text_ingestion=True,
            env={},
        )


def test_batch_runner_captures_output_and_composes_petta_environment(tmp_path):
    mettabase = _mettabase_tree(tmp_path / "mettabase")
    petta = _petta_tree(tmp_path / "petta")
    swipl = _executable(
        tmp_path / "fake-swipl",
        """
import os
import pathlib
import sys

program = pathlib.Path(sys.argv[sys.argv.index("--") + 1])
expected = [
    str(pathlib.Path.cwd() / "src"),
    str(pathlib.Path.cwd() / "lib"),
    str(pathlib.Path(os.environ["PETTA_PATH"]) / "python"),
]
assert os.environ["PYTHONPATH"].split(os.pathsep)[:3] == expected
assert program.read_text(encoding="utf-8") == "!(unit)"
assert sys.argv[-2:] == ["silent", "request=one"]
print("BatchOk")
print("trace", file=sys.stderr)
""",
    )
    runtime = SnarsRuntime(
        mettabase,
        petta_dir=petta,
        swipl=swipl,
        env={"PYTHONPATH": "/existing"},
    )

    result = runtime.run_batch("!(unit)", arguments=("request=one",))

    assert result.returncode == 0
    assert result.output_lines == ("BatchOk",)
    assert result.stderr.strip() == "trace"
    assert result.command[0] == str(swipl.resolve())
    assert not list(mettabase.glob(".goalchainer-snars-*.metta"))


def test_batch_runner_maps_nonzero_exit_with_captured_streams(tmp_path):
    mettabase = _mettabase_tree(tmp_path / "mettabase")
    petta = _petta_tree(tmp_path / "petta")
    swipl = _executable(
        tmp_path / "failing-swipl",
        """
import sys
print("partial-output")
print("specific failure", file=sys.stderr)
raise SystemExit(7)
""",
    )
    runtime = SnarsRuntime(mettabase, petta_dir=petta, swipl=swipl, env={})

    with pytest.raises(SnarsPettaExecutionError) as caught:
        runtime.run_batch("!(unit)")

    assert caught.value.details["returncode"] == 7
    assert caught.value.details["stdout"].strip() == "partial-output"
    assert caught.value.details["stderr"].strip() == "specific failure"
    assert not list(mettabase.glob(".goalchainer-snars-*.metta"))


def test_batch_runner_terminates_process_on_timeout(tmp_path):
    mettabase = _mettabase_tree(tmp_path / "mettabase")
    petta = _petta_tree(tmp_path / "petta")
    swipl = _executable(
        tmp_path / "slow-swipl",
        """
import time
print("started", flush=True)
time.sleep(60)
""",
    )
    runtime = SnarsRuntime(
        mettabase,
        petta_dir=petta,
        swipl=swipl,
        timeout_seconds=0.05,
        env={},
    )

    with pytest.raises(SnarsTimeoutError) as caught:
        runtime.run_batch("!(unit)")

    assert caught.value.details["timeout_seconds"] == 0.05
    assert "started" in caught.value.details["stdout"]
    assert not list(mettabase.glob(".goalchainer-snars-*.metta"))


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True, "bad"])
def test_runtime_rejects_invalid_timeout_as_typed_input_error(tmp_path, timeout):
    mettabase = _mettabase_tree(tmp_path / "mettabase")
    petta = _petta_tree(tmp_path / "petta")
    swipl = _executable(tmp_path / "swipl", "print('unused')\n")

    with pytest.raises(SnarsInvalidInputError, match="finite positive"):
        SnarsRuntime(
            mettabase,
            petta_dir=petta,
            swipl=swipl,
            timeout_seconds=timeout,
            env={},
        )


def _mettabase_tree(root: Path) -> Path:
    _file(root / "lib" / "mettabase" / "snars.metta")
    _file(root / "lib" / "mettabase" / "snars" / "kernel.pl")
    _file(root / "lib" / "mettabase" / "hyperbase.metta")
    _file(root / "src" / "mettabase" / "__init__.py")
    return root


def _petta_tree(root: Path) -> Path:
    _file(root / "src" / "main.pl")
    (root / "python").mkdir(parents=True)
    return root


def _file(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _executable(path: Path, body: str) -> Path:
    path.write_text(f"#!{sys.executable}\n{body.lstrip()}", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path

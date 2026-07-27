"""Resolve and run the native Mettabase SNARS stack through PeTTa."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from .snars_models import (
    RuntimeDiagnostics,
    SnarsDependencyUnavailableError,
    SnarsInvalidInputError,
    SnarsPettaExecutionError,
    SnarsTimeoutError,
)

__all__ = [
    "PettaBatchResult",
    "SnarsRuntime",
    "compose_runtime_environment",
    "resolve_runtime",
    "run_petta_batch",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT_METTABASE_DIR = Path("/home/user/Dev/mettabase")
DEFAULT_PETTA_DIR = Path("/home/user/Dev/PeTTa")
DEFAULT_PETTA_SWIPL = Path("/home/user/Dev/swipl-9.3.33/build-petta/src/swipl")
DEFAULT_TIMEOUT_SECONDS = 300.0
TERMINATION_GRACE_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class PettaBatchResult:
    """Captured output from one successful PeTTa batch."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def output_lines(self) -> tuple[str, ...]:
        return tuple(line.strip() for line in self.stdout.splitlines() if line.strip())


class SnarsRuntime:
    """Resolved SNARS dependencies and their PeTTa batch runner."""

    def __init__(
        self,
        mettabase_dir: str | os.PathLike[str] | None = None,
        *,
        petta_dir: str | os.PathLike[str] | None = None,
        swipl: str | os.PathLike[str] | None = None,
        require_text_ingestion: bool = False,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        env: Mapping[str, str] | None = None,
        repo_root: str | os.PathLike[str] | None = None,
    ) -> None:
        self.timeout_seconds = _timeout_seconds(timeout_seconds)
        self._base_env = dict(os.environ if env is None else env)
        self.diagnostics = resolve_runtime(
            mettabase_dir=mettabase_dir,
            petta_dir=petta_dir,
            swipl=swipl,
            require_text_ingestion=require_text_ingestion,
            env=self._base_env,
            repo_root=repo_root,
        )

    def run_batch(
        self,
        program: str,
        *,
        timeout_seconds: float | None = None,
        arguments: Sequence[str] = (),
        env: Mapping[str, str] | None = None,
    ) -> PettaBatchResult:
        """Execute one MeTTa program in a fresh PeTTa process."""

        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        return run_petta_batch(
            program,
            self.diagnostics,
            timeout_seconds=timeout,
            arguments=arguments,
            env=self._base_env if env is None else env,
        )


def resolve_runtime(
    *,
    mettabase_dir: str | os.PathLike[str] | None = None,
    petta_dir: str | os.PathLike[str] | None = None,
    swipl: str | os.PathLike[str] | None = None,
    require_text_ingestion: bool = False,
    env: Mapping[str, str] | None = None,
    repo_root: str | os.PathLike[str] | None = None,
) -> RuntimeDiagnostics:
    """Resolve every dependency needed for an authoritative PeTTa SNARS run."""

    values = os.environ if env is None else env
    project_root = _resolved_path(REPO_ROOT if repo_root is None else repo_root)
    mettabase_root = _resolve_mettabase_dir(mettabase_dir, values, project_root)

    snars_program = mettabase_root / "lib" / "mettabase" / "snars.metta"
    snars_kernel = mettabase_root / "lib" / "mettabase" / "snars" / "kernel.pl"
    hyperbase_program = mettabase_root / "lib" / "mettabase" / "hyperbase.metta"
    _require_file(snars_program, "Mettabase SNARS program")
    _require_file(snars_kernel, "Mettabase SNARS kernel")
    _require_file(hyperbase_program, "Mettabase HyperBase program")

    python_package: Path | None = None
    if require_text_ingestion:
        python_package = mettabase_root / "src" / "mettabase"
        _require_file(
            python_package / "__init__.py",
            "Mettabase Python package for text ingestion",
        )

    petta_root = _resolve_petta_dir(petta_dir, values)
    petta_main = petta_root / "src" / "main.pl"
    _require_file(petta_main, "PeTTa entrypoint")
    swipl_path = _resolve_swipl(swipl, values)

    return RuntimeDiagnostics(
        mettabase_dir=mettabase_root,
        mettabase_commit=_mettabase_commit(mettabase_root),
        snars_program=snars_program,
        snars_kernel=snars_kernel,
        hyperbase_program=hyperbase_program,
        petta_dir=petta_root,
        petta_main=petta_main,
        swipl=swipl_path,
        python_package=python_package,
    )


def compose_runtime_environment(
    diagnostics: RuntimeDiagnostics,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Expose the Python modules that Mettabase imports through PeTTa Janus."""

    env = dict(os.environ if base_env is None else base_env)
    required_python_paths = (
        diagnostics.mettabase_dir / "src",
        diagnostics.mettabase_dir / "lib",
        diagnostics.petta_dir / "python",
    )
    existing = env.get("PYTHONPATH", "")
    python_paths = [str(path) for path in required_python_paths]
    python_paths.extend(part for part in existing.split(os.pathsep) if part)
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(python_paths))
    env["PETTA_PATH"] = str(diagnostics.petta_dir)
    return env


def run_petta_batch(
    program: str,
    diagnostics: RuntimeDiagnostics,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    arguments: Sequence[str] = (),
    env: Mapping[str, str] | None = None,
) -> PettaBatchResult:
    """Run a complete MeTTa batch with captured output and bounded cancellation."""

    if not isinstance(program, str):
        raise SnarsInvalidInputError("PeTTa program must be text.")
    timeout = _timeout_seconds(timeout_seconds)
    try:
        command_arguments = tuple(arguments)
    except TypeError as exc:
        raise SnarsInvalidInputError(
            "PeTTa arguments must be a sequence of text."
        ) from exc
    if any(
        not isinstance(argument, str) or "\0" in argument
        for argument in command_arguments
    ):
        raise SnarsInvalidInputError(
            "PeTTa arguments must contain only text without null bytes."
        )

    program_path: Path | None = None
    process: subprocess.Popen[str] | None = None
    command: tuple[str, ...] = ()
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".metta",
            prefix=".goalchainer-snars-",
            dir=diagnostics.mettabase_dir,
            delete=False,
        ) as handle:
            handle.write(program)
            program_path = Path(handle.name)

        command = (
            str(diagnostics.swipl),
            "--stack_limit=8g",
            "-q",
            "-s",
            str(diagnostics.petta_main),
            "--",
            str(program_path),
            "silent",
            *command_arguments,
        )
        try:
            process = subprocess.Popen(
                command,
                cwd=diagnostics.mettabase_dir,
                env=compose_runtime_environment(diagnostics, env),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
            )
        except OSError as exc:
            raise SnarsPettaExecutionError(
                f"Unable to start PeTTa through {diagnostics.swipl}.",
                details={"command": command, "error": str(exc)},
            ) from exc

        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            stdout, stderr = _terminate_process(process)
            raise SnarsTimeoutError(
                f"PeTTa exceeded its {timeout:g} second timeout.",
                details={
                    "command": command,
                    "timeout_seconds": timeout,
                    "stdout": stdout,
                    "stderr": stderr,
                },
            ) from None

        if process.returncode != 0:
            raise SnarsPettaExecutionError(
                f"PeTTa exited with status {process.returncode}.",
                details={
                    "command": command,
                    "returncode": process.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                },
            )
        return PettaBatchResult(
            command=command,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    finally:
        if process is not None and process.poll() is None:
            _terminate_process(process)
        if program_path is not None:
            program_path.unlink(missing_ok=True)


def _resolve_mettabase_dir(
    explicit: str | os.PathLike[str] | None,
    env: Mapping[str, str],
    repo_root: Path,
) -> Path:
    if explicit is not None:
        return _require_directory(
            _resolved_path(explicit), "explicit Mettabase checkout"
        )

    configured = env.get("GOALCHAINER_METTABASE_DIR")
    if configured:
        return _require_directory(
            _resolved_path(configured),
            "GOALCHAINER_METTABASE_DIR checkout",
        )

    vendored = repo_root / "external" / "mettabase"
    if vendored.is_dir():
        return vendored.resolve()
    if DEVELOPMENT_METTABASE_DIR.is_dir():
        return DEVELOPMENT_METTABASE_DIR.resolve()
    raise SnarsDependencyUnavailableError(
        "Mettabase is unavailable. Initialize external/mettabase or set "
        "GOALCHAINER_METTABASE_DIR.",
        details={
            "vendored_path": str(vendored),
            "development_path": str(DEVELOPMENT_METTABASE_DIR),
        },
    )


def _resolve_petta_dir(
    explicit: str | os.PathLike[str] | None,
    env: Mapping[str, str],
) -> Path:
    if explicit is not None:
        return _require_directory(_resolved_path(explicit), "explicit PeTTa checkout")
    for variable in ("GOALCHAINER_PETTA_DIR", "PETTA_PATH"):
        configured = env.get(variable)
        if configured:
            return _require_directory(
                _resolved_path(configured), f"{variable} checkout"
            )
    return _require_directory(DEFAULT_PETTA_DIR.resolve(), "development PeTTa checkout")


def _resolve_swipl(
    explicit: str | os.PathLike[str] | None,
    env: Mapping[str, str],
) -> Path:
    selected: str | os.PathLike[str]
    if explicit is not None:
        selected = explicit
    elif env.get("GOALCHAINER_PETTA_SWIPL"):
        selected = env["GOALCHAINER_PETTA_SWIPL"]
    elif DEFAULT_PETTA_SWIPL.is_file():
        selected = DEFAULT_PETTA_SWIPL
    else:
        selected = "swipl"

    raw = os.fspath(selected)
    has_directory = Path(raw).parent != Path(".")
    resolved = _resolved_path(raw) if has_directory else None
    if resolved is None or not resolved.is_file():
        found = shutil.which(raw, path=env.get("PATH"))
        resolved = _resolved_path(found) if found else resolved
    if resolved is None or not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise SnarsDependencyUnavailableError(
            f"Selected SWI-Prolog executable is unavailable: {raw}",
            details={"dependency": "swipl", "path": raw},
        )
    return resolved


def _mettabase_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SnarsDependencyUnavailableError(
            f"Unable to resolve the Mettabase commit at {root}.",
            details={"dependency": "mettabase_commit", "path": str(root)},
        ) from exc
    commit = result.stdout.strip()
    if result.returncode != 0 or not commit:
        raise SnarsDependencyUnavailableError(
            f"Mettabase checkout has no resolvable commit at {root}.",
            details={
                "dependency": "mettabase_commit",
                "path": str(root),
                "stderr": result.stderr.strip(),
            },
        )
    return commit


def _terminate_process(process: subprocess.Popen[str]) -> tuple[str, str]:
    if process.poll() is not None:
        return process.communicate()
    try:
        process.terminate()
    except ProcessLookupError:
        return process.communicate()
    try:
        return process.communicate(timeout=TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.communicate()


def _require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise SnarsDependencyUnavailableError(
            f"{label} is unavailable at {path}.",
            details={"dependency": label, "path": str(path)},
        )
    return path


def _require_directory(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise SnarsDependencyUnavailableError(
            f"{label} is unavailable at {path}.",
            details={"dependency": label, "path": str(path)},
        )
    return path


def _resolved_path(path: str | os.PathLike[str]) -> Path:
    return Path(path).expanduser().resolve()


def _timeout_seconds(value: float) -> float:
    if isinstance(value, bool):
        raise SnarsInvalidInputError("PeTTa timeout must be a finite positive number.")
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise SnarsInvalidInputError(
            "PeTTa timeout must be a finite positive number."
        ) from exc
    if not isfinite(timeout) or timeout <= 0:
        raise SnarsInvalidInputError("PeTTa timeout must be a finite positive number.")
    return timeout

"""Run bounded MeTTaScript programs through the packaged Node adapter."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sysconfig
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .sexpr_protocol import nonempty_output_lines
from .thread_models import ThreadExecutionError

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_RUNNER_PATH = REPO_ROOT / "integrations" / "mettascript" / "runner.mjs"
INSTALLED_RUNNER_PATH = (
    Path(sysconfig.get_path("data"))
    / "integrations"
    / "mettascript"
    / "runner.mjs"
)
RUNNER_PROTOCOL = "goalchainer-mettascript-runner-v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 3 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class MeTTaScriptBatchResult:
    """Captured output from one successful MeTTaScript batch."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def output_lines(self) -> tuple[str, ...]:
        return nonempty_output_lines(self.stdout)


class MeTTaScriptRuntime:
    """Resolve Node and execute the canonical MeTTa policy with MeTTaScript."""

    def __init__(
        self,
        *,
        node: str | os.PathLike[str] | None = None,
        runner_path: str | os.PathLike[str] | None = None,
        module_root: str | os.PathLike[str] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        env: Mapping[str, str] | None = None,
        tabling: bool = True,
    ) -> None:
        self.node = _resolve_node(node, env)
        self.runner_path = _resolve_runner(runner_path)
        self.module_root = _resolve_module_root(
            module_root,
            env,
            runner_path=self.runner_path,
        )
        self.timeout_seconds = _positive_timeout(timeout_seconds)
        self.env = dict(os.environ if env is None else env)
        self.tabling = bool(tabling)

    def run_batch(
        self,
        program: str,
        *,
        timeout_seconds: float | None = None,
    ) -> MeTTaScriptBatchResult:
        """Execute one source batch and render every query result as MeTTa text."""

        if not isinstance(program, str):
            raise ThreadExecutionError("MeTTaScript program must be text.")
        encoded = program.encode("utf-8")
        if len(encoded) > MAX_SOURCE_BYTES:
            raise ThreadExecutionError(
                "MeTTaScript program exceeds the source-size limit.",
                details={
                    "size_bytes": len(encoded),
                    "limit_bytes": MAX_SOURCE_BYTES,
                },
            )
        if "\0" in program:
            raise ThreadExecutionError("MeTTaScript program contains a null byte.")
        timeout = (
            self.timeout_seconds
            if timeout_seconds is None
            else _positive_timeout(timeout_seconds)
        )
        request = json.dumps(
            {
                "protocol": RUNNER_PROTOCOL,
                "source": program,
                "tabling": self.tabling,
            },
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        command = (str(self.node), str(self.runner_path))
        try:
            completed = subprocess.run(
                command,
                cwd=self.module_root,
                env=self.env,
                input=request,
                capture_output=True,
                text=True,
                shell=False,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ThreadExecutionError(
                f"MeTTaScript exceeded its {timeout:g} second timeout.",
                details={"timeout_seconds": timeout},
            ) from exc
        except OSError as exc:
            raise ThreadExecutionError(
                "MeTTaScript could not be started.",
                details={"command": command, "error": str(exc)},
            ) from exc
        if len(completed.stdout.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise ThreadExecutionError(
                "MeTTaScript response exceeds the output-size limit."
            )
        if completed.returncode != 0:
            raise ThreadExecutionError(
                "MeTTaScript rejected the orchestration program.",
                details={
                    "returncode": completed.returncode,
                    "runtime": _runner_error(completed.stderr),
                },
            )
        try:
            response = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ThreadExecutionError(
                "MeTTaScript returned malformed runner JSON."
            ) from exc
        if (
            not isinstance(response, dict)
            or response.get("protocol") != RUNNER_PROTOCOL
            or not isinstance(response.get("rows"), list)
            or not all(isinstance(row, str) for row in response["rows"])
        ):
            raise ThreadExecutionError(
                "MeTTaScript returned the wrong runner protocol shape."
            )
        stdout = "\n".join(response["rows"])
        if stdout:
            stdout += "\n"
        return MeTTaScriptBatchResult(
            command=command,
            returncode=completed.returncode,
            stdout=stdout,
            stderr=completed.stderr,
        )


def _resolve_node(
    explicit: str | os.PathLike[str] | None,
    env: Mapping[str, str] | None,
) -> Path:
    values = os.environ if env is None else env
    selected = (
        os.fspath(explicit)
        if explicit is not None
        else values.get("GOALCHAINER_METTASCRIPT_NODE", "node")
    )
    candidate = Path(selected).expanduser()
    if candidate.parent != Path("."):
        resolved = candidate.absolute()
    else:
        found = shutil.which(selected, path=values.get("PATH"))
        resolved = Path(found).absolute() if found else candidate.absolute()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ThreadExecutionError(
            "Node.js is unavailable for MeTTaScript.",
            details={"node": str(resolved)},
        )
    return resolved


def _resolve_runner(explicit: str | os.PathLike[str] | None) -> Path:
    if explicit is not None:
        candidates = (Path(explicit).expanduser().absolute(),)
    else:
        candidates = (SOURCE_RUNNER_PATH, INSTALLED_RUNNER_PATH)
    runner = next((path for path in candidates if path.is_file()), None)
    if runner is None:
        raise ThreadExecutionError(
            "The MeTTaScript runner adapter is unavailable.",
            details={"searched": [str(path) for path in candidates]},
        )
    return runner


def _resolve_module_root(
    explicit: str | os.PathLike[str] | None,
    env: Mapping[str, str] | None,
    *,
    runner_path: Path,
) -> Path:
    values = os.environ if env is None else env
    configured = (
        os.fspath(explicit)
        if explicit is not None
        else values.get("GOALCHAINER_METTASCRIPT_ROOT")
    )
    if configured is not None:
        candidates = (Path(configured).expanduser().absolute(),)
    else:
        candidates = _module_root_candidates(runner_path)
    root = next(
        (
            candidate
            for candidate in candidates
            if (
                candidate
                / "node_modules"
                / "@mettascript"
                / "node"
                / "package.json"
            ).is_file()
        ),
        None,
    )
    if root is None:
        raise ThreadExecutionError(
            "The MeTTaScript Node package is unavailable.",
            details={
                "searched": [str(candidate) for candidate in candidates],
                "dependency": "@mettascript/node@2.7.0",
            },
        )
    return root


def _module_root_candidates(runner_path: Path) -> tuple[Path, ...]:
    roots: list[Path] = []
    for starting_point in (Path.cwd().absolute(), REPO_ROOT, runner_path.parents[2]):
        for candidate in (starting_point, *starting_point.parents):
            if candidate not in roots:
                roots.append(candidate)
    return tuple(roots)


def _positive_timeout(value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ThreadExecutionError(
            "MeTTaScript timeout must be a positive finite number."
        )
    return float(value)


def _runner_error(stderr: str) -> str:
    try:
        payload = json.loads(stderr)
    except json.JSONDecodeError:
        return stderr[-4096:]
    message = payload.get("message") if isinstance(payload, dict) else None
    return message if isinstance(message, str) else "unknown runner error"


__all__ = [
    "INSTALLED_RUNNER_PATH",
    "MeTTaScriptBatchResult",
    "MeTTaScriptRuntime",
    "RUNNER_PROTOCOL",
    "SOURCE_RUNNER_PATH",
]

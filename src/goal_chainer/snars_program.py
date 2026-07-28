"""Typed construction of PeTTa programs for the GoalChainer SNARS adapter."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Sequence

from .snars_models import SnarsInvalidInputError
from .snars_runtime import SnarsRuntime

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = REPO_ROOT / "integrations" / "snars" / "goalchainer_protocol.metta"
POLICY_PATH = REPO_ROOT / "integrations" / "snars" / "goalchainer_policy.metta"
SCORE_PATH = REPO_ROOT / "integrations" / "snars" / "goalchainer_score.metta"

_SYMBOL_RE = re.compile(r"^[^\s()\";]+$")
_FORBIDDEN_HEADS = frozenset(
    {
        "!",
        "=",
        "add-atom",
        "bind!",
        "import!",
        "py-call",
        "remove-atom",
        "transfer!",
    }
)


@dataclass(frozen=True, slots=True)
class ProgramFragments:
    """Plain facts and effect expressions generated for one operation."""

    facts: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()


class SexprCodec:
    """Adapter over Mettabase's shared S-expression parser and emitter."""

    def __init__(self, runtime: SnarsRuntime) -> None:
        self._module = _load_sexpr_module(runtime)
        self.Symbol = self._module.Symbol
        self.StringLiteral = self._module.StringLiteral

    def parse(self, source: str) -> Any:
        if not isinstance(source, str):
            raise SnarsInvalidInputError("S-expression source must be text.")
        try:
            return self._module.parse(source)
        except (TypeError, ValueError) as exc:
            raise SnarsInvalidInputError(
                "Invalid MeTTa S-expression.",
                details={"error": str(exc)},
            ) from exc

    def emit(self, atom: Any) -> str:
        return self._module.emit(atom)

    def symbol(self, value: str) -> Any:
        if not isinstance(value, str) or not _SYMBOL_RE.fullmatch(value):
            raise SnarsInvalidInputError(
                "MeTTa symbol contains whitespace, syntax, or is empty.",
                details={"symbol": value},
            )
        return self.Symbol(value)

    def string(self, value: str) -> Any:
        if not isinstance(value, str):
            raise SnarsInvalidInputError("MeTTa string literal value must be text.")
        return self.StringLiteral(value)

    def expression(self, head: str, *arguments: Any) -> list[Any]:
        return [self.symbol(head), *arguments]

    def statement(self, source: str, *, pattern: bool = False) -> Any:
        atom = self.parse(source)
        _validate_statement_atom(atom, self, pattern=pattern)
        return atom

    def binary_statement(
        self,
        relation: str,
        subject: str,
        object_: str,
    ) -> list[Any]:
        return self.expression(
            "sn",
            self.symbol("p"),
            self.symbol("so"),
            self.string(relation),
            [
                [
                    self.symbol("arg"),
                    self.symbol("s"),
                    self.expression("sn", self.symbol("c"), self.string(subject)),
                ],
                [
                    self.symbol("arg"),
                    self.symbol("o"),
                    self.expression("sn", self.symbol("c"), self.string(object_)),
                ],
            ],
        )


class SnarsProgramBuilder:
    """Build one batch whose only machine record is the requested operation."""

    def __init__(self, runtime: SnarsRuntime) -> None:
        self.runtime = runtime
        self.codec = SexprCodec(runtime)

    def belief_effect(
        self,
        statement: Any,
        *,
        positive: float,
        negative: float,
        base_rate: float,
        source: str,
        trust: float,
        occurrence: float | None = None,
    ) -> str:
        options: list[Any] = [
            [self.codec.symbol("evidence"), positive, negative],
            [self.codec.symbol("rate"), base_rate],
            [self.codec.symbol("source"), self.codec.string(source)],
            [self.codec.symbol("trust"), trust],
        ]
        if occurrence is not None:
            options.append([self.codec.symbol("occ"), occurrence])
        return self.codec.emit(
            self.codec.expression("believe!", statement, options)
        )

    def goal_effect(self, statement: Any, desire: float) -> str:
        return self.codec.emit(
            self.codec.expression(
                "goal!",
                statement,
                [[self.codec.symbol("desire"), desire]],
            )
        )

    def text_ingestion(
        self,
        text: str,
        *,
        source: str,
        trust: float,
        parser_name: str = "alphabeta",
        lang: str = "en",
    ) -> ProgramFragments:
        """Parse text with Mettabase and retain its real typed SH facts."""

        if not text.strip():
            raise SnarsInvalidInputError("Text ingestion requires nonempty text.")
        try:
            program = _text_program_in_process(
                self.runtime,
                text,
                source,
                trust=trust,
                parser_name=parser_name,
                lang=lang,
            )
        except Exception as direct_error:
            program = _text_program_in_parser_environment(
                self.runtime,
                text=text,
                source=source,
                trust=trust,
                parser_name=parser_name,
                lang=lang,
                direct_error=direct_error,
            )
        return _split_ingestion_program(program, self.codec)

    def batch(
        self,
        operation: Any,
        *,
        facts: Sequence[str] = (),
        effects: Sequence[str] = (),
        include_policy: bool = False,
        include_guard: bool = False,
    ) -> str:
        for fact in facts:
            _validate_generated_fact(fact, self.codec)
        body_effects = list(effects)
        if include_policy:
            body_effects.extend(
                (
                    "(gc init-policy!)",
                    "(gc assert-request-context!)",
                    "(sn cycles 2)",
                )
            )

        lines = [
            "!(import! &self lib/mettabase/snars)",
            *facts,
        ]
        if include_policy:
            lines.append(POLICY_PATH.read_text(encoding="utf-8"))
        lines.append(PROTOCOL_PATH.read_text(encoding="utf-8"))
        lines.append(SCORE_PATH.read_text(encoding="utf-8"))
        if include_guard:
            guard_path = (
                self.runtime.diagnostics.mettabase_dir
                / "lib"
                / "mettabase"
                / "snars-guard.metta"
            )
            if not guard_path.is_file():
                raise SnarsInvalidInputError(
                    "The optional SNARS guard module is unavailable.",
                    details={"path": str(guard_path)},
                )
            lines.append(guard_path.read_text(encoding="utf-8"))
        operation_source = self.codec.emit(operation)
        if body_effects:
            bindings = " ".join(
                f"($gc-effect-{index} {effect})"
                for index, effect in enumerate(body_effects, start=1)
            )
            lines.append(f"!(let* ({bindings}) {operation_source})")
        else:
            lines.append(f"!{operation_source}")
        return "\n".join(lines) + "\n"


def _load_sexpr_module(runtime: SnarsRuntime) -> ModuleType:
    path = runtime.diagnostics.mettabase_dir / "src" / "mettabase" / "core" / "sexpr.py"
    return _load_module("goalchainer_mettabase_sexpr", path)


def _load_ingest_module(runtime: SnarsRuntime) -> ModuleType:
    # Ingestion imports the rest of Mettabase by package name. Add only the
    # pinned checkout's source root, then import its public builder.
    import sys

    source_root = str(runtime.diagnostics.mettabase_dir / "src")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    try:
        from mettabase.snars import ingest
    except Exception as exc:
        raise SnarsInvalidInputError(
            "Mettabase text ingestion package cannot be imported.",
            details={"path": source_root, "error": f"{type(exc).__name__}: {exc}"},
        ) from exc
    return ingest


def _text_program_in_process(
    runtime: SnarsRuntime,
    text: str,
    source: str,
    *,
    trust: float,
    parser_name: str,
    lang: str,
) -> str:
    module = _load_ingest_module(runtime)
    return module.text_program(
        text,
        source,
        trust=trust,
        parser_name=parser_name,
        lang=lang,
    )


_PARSER_SCRIPT = """
import json
import sys
from mettabase.snars.ingest import text_program

request = json.load(sys.stdin)
sys.stdout.write(text_program(
    request["text"],
    request["source"],
    trust=request["trust"],
    parser_name=request["parser_name"],
    lang=request["lang"],
))
"""


def _text_program_in_parser_environment(
    runtime: SnarsRuntime,
    *,
    text: str,
    source: str,
    trust: float,
    parser_name: str,
    lang: str,
    direct_error: Exception,
) -> str:
    python = _parser_python(runtime)
    if python is None:
        raise SnarsInvalidInputError(
            "Mettabase text parser is unavailable in native mode.",
            details={
                "parser": parser_name,
                "language": lang,
                "direct_error": f"{type(direct_error).__name__}: {direct_error}",
                "remedy": (
                    "Set GOALCHAINER_METTABASE_PYTHON to a Python environment "
                    "with the Mettabase AlphaBeta parser dependencies."
                ),
            },
        ) from direct_error
    payload = json.dumps(
        {
            "text": text,
            "source": source,
            "trust": trust,
            "parser_name": parser_name,
            "lang": lang,
        },
        ensure_ascii=False,
    )
    env = dict(os.environ)
    source_root = str(runtime.diagnostics.mettabase_dir / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (source_root, existing) if part
    )
    try:
        result = subprocess.run(
            [str(python), "-c", _PARSER_SCRIPT],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
            timeout=runtime.timeout_seconds,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SnarsInvalidInputError(
            "Mettabase parser process could not complete.",
            details={
                "python": str(python),
                "error": f"{type(exc).__name__}: {exc}",
            },
        ) from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise SnarsInvalidInputError(
            "Mettabase parser process failed in native mode.",
            details={
                "python": str(python),
                "returncode": result.returncode,
                "stderr": result.stderr[-2000:],
                "direct_error": f"{type(direct_error).__name__}: {direct_error}",
            },
        )
    return result.stdout


def _parser_python(runtime: SnarsRuntime) -> Path | None:
    configured = os.environ.get("GOALCHAINER_METTABASE_PYTHON")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise SnarsInvalidInputError(
                "GOALCHAINER_METTABASE_PYTHON is not an executable file.",
                details={"path": str(path)},
            )
        return path.absolute()
    candidates = (
        runtime.diagnostics.mettabase_dir / "hyperbase" / ".venv" / "bin" / "python",
        Path("/home/user/Dev/mettabase/hyperbase/.venv/bin/python"),
    )
    return next(
        (
            candidate.absolute()
            for candidate in candidates
            if candidate.is_file() and os.access(candidate, os.X_OK)
        ),
        None,
    )


def _load_module(name: str, path: Path) -> ModuleType:
    import sys

    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SnarsInvalidInputError(
            "Mettabase S-expression module cannot be loaded.",
            details={"path": str(path)},
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _split_ingestion_program(program: str, codec: SexprCodec) -> ProgramFragments:
    facts: list[str] = []
    effects: list[str] = []
    for line in program.splitlines():
        source = line.strip()
        if not source:
            continue
        if source.startswith("!(") and source.endswith(")"):
            effect = source[2:-1]
            atom = codec.parse(effect)
            _validate_effect_atom(atom, codec)
            effects.append(codec.emit(atom))
        else:
            _validate_generated_fact(source, codec)
            facts.append(source)
    return ProgramFragments(tuple(facts), tuple(effects))


def _validate_generated_fact(source: str, codec: SexprCodec) -> None:
    atom = codec.parse(source)
    if not isinstance(atom, list) or not atom:
        raise SnarsInvalidInputError("Generated HyperBase fact must be an expression.")
    head = _symbol_text(atom[0], codec)
    if head != "hb":
        raise SnarsInvalidInputError(
            "Generated parser prelude contains a non-HyperBase fact.",
            details={"head": head},
        )


def _validate_effect_atom(atom: Any, codec: SexprCodec) -> None:
    if not isinstance(atom, list) or not atom:
        raise SnarsInvalidInputError("Generated ingestion effect must be an expression.")
    head = _symbol_text(atom[0], codec)
    if head not in {"sn"}:
        raise SnarsInvalidInputError(
            "Generated parser effect is not a SNARS operation.",
            details={"head": head},
        )


def _validate_statement_atom(atom: Any, codec: SexprCodec, *, pattern: bool) -> None:
    if not isinstance(atom, list) or not atom:
        raise SnarsInvalidInputError("SNARS statement must be a nonempty expression.")
    head = _symbol_text(atom[0], codec)
    if head in _FORBIDDEN_HEADS or head not in {"sn", "sh", "sh-atom", "sh-conn"}:
        raise SnarsInvalidInputError(
            "SNARS statement uses a disallowed constructor.",
            details={"head": head},
        )
    for node in _walk(atom):
        if isinstance(node, codec.Symbol):
            if node.text in _FORBIDDEN_HEADS:
                raise SnarsInvalidInputError(
                    "SNARS statement contains an executable form.",
                    details={"symbol": node.text},
                )
            if not pattern and node.text.startswith("$"):
                raise SnarsInvalidInputError(
                    "Ground SNARS statements cannot contain variables.",
                    details={"symbol": node.text},
                )


def _walk(atom: Any) -> Iterable[Any]:
    yield atom
    if isinstance(atom, list):
        for item in atom:
            yield from _walk(item)


def _symbol_text(atom: Any, codec: SexprCodec) -> str:
    if not isinstance(atom, codec.Symbol):
        raise SnarsInvalidInputError("Expression head must be a MeTTa symbol.")
    return atom.text


__all__ = [
    "POLICY_PATH",
    "PROTOCOL_PATH",
    "SCORE_PATH",
    "ProgramFragments",
    "SexprCodec",
    "SnarsProgramBuilder",
]

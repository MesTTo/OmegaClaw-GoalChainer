"""Purpose: bind MeTTa libraries and import MeTTa modules into the process's pymetta engine.
`initialize_once` runs a caller's whole engine setup once, recording it only after it succeeds, and
`register_metta_library` binds a library name once; each takes the engine alone only for work not
yet done, so a prepared path never waits for running evaluations, and a first call waits for the
engine only until its caller's deadline.
`load_metta_module` imports a file, keyed by its resolved path, or a module of a registered library
once per process into the engine's self space, or into a named space of the engine, which compiles
into a function namespace of its own, and answers the SHA-256 of what it imported. An engine
transaction commits the import's writes and digest verification together; a failure restores
earlier equations too. The Python digest record is published only after that commit. The engine
keeps running what it loaded, so a module whose bytes on disk later differ raises ModuleChanged
rather than being reloaded or reported under a digest it does not run. A library name stays bound
to one directory for the life of the process. Every MeTTa source file an import reaches is read
by pymetta's strict reader first; other source kinds use their own loader. The import must answer
True once, so a module that does not parse is refused instead of recorded under a digest of code
the engine never received. am[implements a-rt-loader-refuses-unparsed-1018@d138df]"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from ..errors import DependencyUnavailableError, MettaEngineError, ModuleChanged
from .budget import ReviewTimeout, RunBudget
from .engine import metta_engine


# am[implements a-rt-loaded-identity-1016@e4ffa3]
@dataclass(frozen=True, slots=True)
class MettaLibrary:
    """A module of a library that register_metta_library bound, imported as
    `(library NAME MODULE)`, e.g. MettaLibrary("deontic", "lib_deontic")."""

    name: str
    module: str

    @property
    def spec(self) -> str:
        return f"(library {self.name} {self.module})"

_LIBRARIES: dict[str, Path] = {}


# Each import's digest, keyed by the space it went into, None for the engine's self space, and the
# module.
_MODULES: dict[tuple[str | None, Path | MettaLibrary], str] = {}

# The import targets of each file the strict reader accepted, keyed by its resolved path and the
# SHA-256 of its bytes, so a file is parsed once per content in the process; what a target names is
# found again on every walk, since a file it names may appear later.
_PARSED: dict[tuple[Path, str], tuple[tuple[str, str], ...]] = {}

_SETUPS: set[str] = set()


# A binding is recorded only after the engine made it and never changes, so a thread finding the
# name bound reads the record without the engine, as std::call_once's fast path reads its flag: a
# grading that binds its library on every call then waits for no running evaluation
# (c-rt-kernel-per-call-exclusive-1018). Under CPython's GIL a dict read is atomic and ordered after
# the write that published it. Only a first binding takes the engine alone, re-entrantly for a
# caller already holding it, waiting for it only until the caller's deadline.
# am[implements a-rt-pymetta-engine-1016@296784] am[implements a-rt-cc-rw-pool-1018]
# am[implements a-integrate-runtime-wait-deadline-1018@a74406]
def register_metta_library(name: str, directory: Path, *, budget: RunBudget | None) -> None:
    """Make `(library NAME X)` resolve under directory, through the same lib_gitimport
    registration a git-imported library gets, holding the engine alone only for a new binding.

    A name already bound to another directory is refused: modules imported through it stay
    compiled from the first one, so a second binding would mix two libraries in one namespace.
    A new binding asked for inside shared evaluation work raises metta_engine's RuntimeError.
    A new binding waits for the engine until `budget`'s deadline and then raises its
    ReviewTimeout, binding nothing; None is for a caller outside any request.
    """

    resolved = directory.resolve()
    bound = _LIBRARIES.get(name)
    if bound is None:
        with metta_engine(budget) as engine:
            bound = _LIBRARIES.get(name)
            if bound is None:
                engine.runtime.once(
                    "lib_gitimport:register_git_library_path(Name, Directory)",
                    Name=name,
                    Directory=str(resolved),
                )
                _LIBRARIES[name] = bound = resolved
    if bound != resolved:
        raise DependencyUnavailableError(
            f"The in-process engine already bound library {name} to {bound}; {resolved} needs "
            "a fresh process.",
            details={"dependency": name, "path": str(resolved), "bound": str(bound)},
        )


# The import goes through source text: the atom-level import! cannot load a module that runs its
# own `(library ...)` imports, and the text form can. A file's path enters that text as a hole, one
# String atom, so no path needs quoting. pymetta reads a file again on every import! of it, so the
# digest is taken on each side of the import and the record is the only thing that stops a second.
# A named space keeps records of its own, since a module imported into one space defines nothing in
# another.
# Time: one read and SHA-256 of the module, a whole library tree for a library module, on each side
# of a first import and once on every later call; the import itself only on the first.
# am[implements a-rt-pymetta-engine-1016@296784] am[implements a-rt-loaded-identity-1016@e4ffa3]
# am[rests-on c-rt-pymetta-import-all-or-nothing-1016@a30138]
# am[rests-on c-rt-atom-import-fails-nested-1016@13e74e]
# am[implements a-rt-bounded-preparation-1016@e7eb12] am[rests-on c-rt-stopped-import-retry-safe-1016@cba696]
# am[rests-on c-rel-retry-digest-mismatch-1016@dd4354] am[rests-on c-rt-reimport-replaces-1016@4a932b]
# am[implements a-rt-load-module-per-space-1017@309625] am[rests-on c-rt-named-spaces-separate-worlds-1017@92b148]
# am[implements a-integrate-import-transaction-1017]
# am[rests-on c-integrate-import-transaction-restores-equation-1017]
def load_metta_module(
    engine: Any,
    module: Path | MettaLibrary,
    *,
    budget: RunBudget | None = None,
    space: Any = None,
) -> str:
    """Import a module into the engine's self space, or into `space`, a named space the engine
    handed out, once per process, and answer the SHA-256, as hex, of what it imported: a file's
    bytes, or tree_digest of the directory a library is bound to. Call it holding metta_engine.

    A file is keyed by its resolved path, so two spellings of one file are one module. The import
    and its final digest check run in one engine transaction, which rolls back changes to earlier
    equations as well as new definitions if either fails. Only a committed import publishes the
    Python digest record. Bytes changed during import raise ModuleChanged, unrecorded. A later call
    answers the recorded digest while the bytes still match it and raises ModuleChanged once they
    do not, because the engine keeps what it imported. A missing file, or a library no
    register_metta_library bound, is a DependencyUnavailableError, and so is a file the
    digest cannot read.

    Before importing, every file the import reaches is read by pymetta's strict reader: the module
    file and what its imports name, or a library's whole directory. A file that does not parse is a
    MettaEngineError naming it, raised before anything is imported, and so is an import that answers
    anything but True once.

    Each space has records of its own: a module the self space imported is imported again, and
    recorded again, the first time a named space asks for it, since neither space sees what the
    other defines.

    With a budget the import runs inside that budget's deadline and raises ReviewTimeout when
    the deadline stops it; its inferences are fixed startup work and are not charged. A stopped
    import leaves nothing a retry would duplicate. Without one it is a startup import, bounded
    by nothing, for callers outside any request.
    """

    module_key: Path | MettaLibrary
    hashed: Callable[[], str]
    if isinstance(module, Path):
        module_key = path = module.resolve()
        source, holes = "!(import! &self {path})", {"path": str(path)}
        if not path.is_file():
            raise DependencyUnavailableError(
                f"No MeTTa module at {path}.", details={"dependency": "metta-module", "path": str(path)}
            )
        hashed = partial(file_digest, path)
    elif isinstance(module, MettaLibrary):
        module_key = module
        source, holes = f"!(import! &self {module.spec})", {}
        bound = _LIBRARIES.get(module.name)
        if bound is None:
            raise DependencyUnavailableError(
                f"Library {module.name} is not registered in the in-process engine; "
                "register_metta_library binds it first.",
                details={"dependency": module.name, "module": module.module},
            )
        path = bound
        hashed = partial(tree_digest, bound)
    else:
        raise TypeError(f"load_metta_module takes a Path or a MettaLibrary, not {type(module).__name__}")

    def digest() -> str:
        try:
            return hashed()
        except OSError as error:
            raise DependencyUnavailableError(
                f"Cannot read the MeTTa module at {path}: {error}",
                details={"dependency": "metta-module", "path": str(path), "error": str(error)},
            ) from error

    key = (None if space is None else str(space.name), module_key)
    recorded = _MODULES.get(key)
    if recorded is not None:
        current = digest()
        if current != recorded:
            raise ModuleChanged(path, recorded, current)
        return recorded
    before = digest()
    _require_parses([path] if isinstance(module, Path) else sorted(path.rglob("*.metta")))
    target = engine if space is None else space
    import_failure: Exception | None = None

    # The transaction facade unwraps Python callback errors. Keep the load boundary's exception.
    # am[implements a-integrate-import-transaction-1017]
    # am[rests-on c-integrate-import-transaction-design-1017]
    # am[implements a-integrate-pymetta-public-errors-1019@05202a]
    def import_and_verify() -> None:
        nonlocal import_failure
        try:
            if budget is None:
                answers = target.run(source, **holes)
            else:
                from metta.errors import TimeLimitError  # noqa: PLC0415 (pymetta is imported only once an engine exists)

                _, seconds = budget.remaining()
                try:
                    answers = target.run(source, timeout=seconds, **holes)
                except TimeLimitError as error:
                    raise ReviewTimeout(budget.timeout_seconds) from error
            # import! answers no True for a module it could not read, defining nothing from it.
            # am[implements a-rt-loader-refuses-unparsed-1018@d138df]
            # am[rests-on c-rt-import-answers-nothing-unparsed-1018@389450]
            if answers != [[True]]:
                raise MettaEngineError(
                    f"Importing the MeTTa module at {path} answered "
                    f"{[[str(answer) for answer in group] for group in answers]}, not True once.",
                    details={"path": str(path), "answers": [[str(answer) for answer in group] for group in answers]},
                )
            after = digest()
            if after != before:
                raise ModuleChanged(path, before, after, while_importing=True)
        except Exception as error:
            import_failure = error
            raise

    try:
        target.transaction(import_and_verify)
    except Exception:
        if import_failure is not None:
            raise import_failure
        raise
    _MODULES[key] = before
    return before


# pymetta's import! defines nothing from a module its reader cannot read and answers no True, and
# a module importing such a file still answers True while the inner file's forms never arrive
# (c-rt-import-answers-nothing-unparsed-1018), so every MeTTa source file an import reaches is read
# here first. A file reaches what its `(import! SPACE TARGET)` forms name: a registered library's
# whole directory for `(library NAME MODULE)`, or the file a bare or quoted path names beside it.
# pymetta's own `(library NAME)` modules ship with the engine and are left to it, and so is a file
# of another kind, such as a .py module, which pymetta imports through Python's own loader.
# Time: one read and SHA-256 of each file reached on each first import into a space, and one strict
# parse of each file content once per process.
# am[implements a-rt-loader-refuses-unparsed-1018@d138df]
# am[rests-on c-rt-import-answers-nothing-unparsed-1018@389450]
def _require_parses(files: Iterable[Path]) -> None:
    from metta import MettaError, forms  # noqa: PLC0415 (pymetta is imported only once an engine exists)

    pending = [file.resolve() for file in files]
    seen: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        if path.suffix != ".metta":
            continue
        try:
            data = path.read_bytes()
        except OSError as error:
            raise DependencyUnavailableError(
                f"Cannot read the MeTTa module at {path}: {error}",
                details={"dependency": "metta-module", "path": str(path), "error": str(error)},
            ) from error
        key = (path, hashlib.sha256(data).hexdigest())
        targets = _PARSED.get(key)
        if targets is None:
            try:
                parsed = forms(data.decode("utf-8"))
            except (MettaError, UnicodeDecodeError) as error:
                raise MettaEngineError(
                    f"The MeTTa module at {path} does not parse, so importing it would define "
                    f"nothing from it: {error}",
                    details={"path": str(path), "error": str(error)},
                ) from error
            targets = _PARSED[key] = tuple(
                target for target in map(_import_target, parsed) if target is not None
            )
        for kind, named in targets:
            pending.extend(file.resolve() for file in _target_files(kind, named, path.parent))


# What one top-level form imports: ("library", NAME) for `(library NAME MODULE)`, ("path", TEXT) for
# a bare or quoted path, None for anything else, pymetta's own `(library NAME)` modules included.
# am[implements a-rt-loader-refuses-unparsed-1018@d138df]
def _import_target(form: Any) -> tuple[str, str] | None:
    parts = list(form) if type(form).__name__ == "Expression" else []
    if len(parts) != 3 or getattr(parts[0], "name", None) != "import!":
        return None
    target = parts[2]
    if type(target).__name__ == "Expression":
        names = [getattr(item, "name", None) for item in target]
        return ("library", names[1]) if len(names) == 3 and names[0] == "library" else None
    named = getattr(target, "name", None) or getattr(target, "value", None)
    return ("path", named) if isinstance(named, str) else None


# The files an import target names now: a registered library's whole directory, whose modules
# import one another by relative name, or the file a path names beside the importing file.
# am[implements a-rt-loader-refuses-unparsed-1018@d138df]
def _target_files(kind: str, named: str, directory: Path) -> list[Path]:
    if kind == "library":
        bound = _LIBRARIES.get(named)
        return [] if bound is None else sorted(bound.rglob("*.metta"))
    candidate = Path(named) if Path(named).is_absolute() else directory / named
    return [path for path in (candidate, candidate.with_name(candidate.name + ".metta")) if path.is_file()][:1]


# am[implements a-rt-loaded-identity-1016@e4ffa3]
def file_digest(path: Path) -> str:
    """The SHA-256, as hex, of a file's bytes: what load_metta_module records for a file module."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


# Time: reads every file under the roots once, b = total bytes; about 1 MB for the deontic library.
# am[implements a-rel-deontic-run-1016@be58d5] am[implements a-rt-loaded-identity-1016@e4ffa3]
def tree_digest(*roots: Path) -> str:
    """SHA-256 over every file under the roots, keyed by root name and relative path."""

    digest = hashlib.sha256()
    for root in roots:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            name = f"{root.name}/{path.relative_to(root).as_posix()}"
            digest.update(name.encode() + b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


# std::call_once semantics: a setup that raises leaves the key unrecorded and the next call
# retries it, so a group of imports and a warm-up is either complete or attempted again whole.
# The key is recorded only after its setup returned, so a thread finding it recorded returns
# without the engine, std::call_once's fast path: a prepared group, world or library then waits for
# no running evaluation (c-rt-kernel-per-call-exclusive-1018). Under CPython's GIL a set's
# membership test is atomic and ordered after the add that published it. A first call takes the
# engine alone, re-entrantly for a caller already holding it, and checks again there; it waits for
# the engine only until the caller's deadline, leaving the key unrecorded when that passes.
# am[implements a-rt-initialize-once-1016@0767f5] am[implements a-rt-cc-rw-pool-1018]
# am[rests-on c-rt-pymetta-import-all-or-nothing-1016@a30138]
# am[implements a-integrate-runtime-wait-deadline-1018@a74406]
def initialize_once(key: str, setup: Callable[[Any], None], *, budget: RunBudget | None) -> None:
    """Run `setup(engine)` holding the engine alone the first time `key` is asked for in this
    process; once it has returned, later calls return at once without taking the engine.

    The key is recorded only after setup returns. A setup that raises, a warm-up stopped by its
    budget included, runs again from the start on the next call, while each module it already
    imported through load_metta_module stays loaded and answers its recorded digest. A setup not
    yet run asked for inside shared evaluation work raises metta_engine's RuntimeError.
    A first call waits for the engine until `budget`'s deadline and then raises its ReviewTimeout
    without running setup; None is for a caller outside any request, such as a host's startup.
    """

    if key in _SETUPS:
        return
    with metta_engine(budget) as engine:
        if key in _SETUPS:
            return
        setup(engine)
        _SETUPS.add(key)

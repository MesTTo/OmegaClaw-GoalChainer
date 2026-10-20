"""Purpose: compile named Python modules from one read of their files and refuse any later compile of
other bytes under those names, so the digest of a pinned module's file names the code that runs, and
report each pinned module's file with the SHA-256 of the bytes this process compiled it from."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Iterable, Mapping
from importlib.machinery import ModuleSpec, SourceFileLoader
from pathlib import Path

from .errors import ModuleChanged

# Each pinned module's name with its file, with the SHA-256 of the bytes this process first compiled
# under it, and with the module object its code last ran in, all kept across a reload of this module,
# so a reload can only compile those bytes again and loaded() can tell a module put in their place.
# am[implements a-rt-helper-compiles-pinned-1017@b73a33] am[implements a-rt-rb-codec-1018@e3e552]
_FILES: dict[str, Path] = globals().get("_FILES", {})
_COMPILED: dict[str, str] = globals().get("_COMPILED", {})
_RAN: dict[str, object] = globals().get("_RAN", {})


# Compiles a module from one read of its file, the bytes whose SHA-256 _COMPILED holds for its name,
# and refuses bytes with any other digest before compiling them: a module importing from a reloaded
# one keeps the old objects, so a reload of other bytes would run two versions under one digest. It
# neither reads nor writes a bytecode cache: a timestamp pyc runs without its source being read
# whenever the source's mtime and size match.
# am[implements a-rt-helpers-compiled-from-read-1017@11c85b]
# am[rests-on c-rt-timestamp-pyc-skips-source-1017@1868e2] am[rests-on c-rt-verified-loader-prior-art-1017@5c8c1c]
# am[implements a-rt-helper-compiles-pinned-1017@b73a33] am[rests-on c-rt-reload-keeps-from-imports-1017@519e22]
class _CompiledFromRead(SourceFileLoader):
    def get_code(self, fullname: str):
        source = self.get_data(self.path)
        digest = hashlib.sha256(source).hexdigest()
        compiled = _COMPILED.setdefault(fullname, digest)
        if digest != compiled:
            raise ModuleChanged(Path(self.path), compiled, digest)
        return self.source_to_code(source, self.path)

    def exec_module(self, module) -> None:
        super().exec_module(module)
        _RAN[module.__name__] = module


# Serves the pinned names, and only those, with _CompiledFromRead, so an import of one from anywhere,
# a pinned module importing another or importlib.reload included, compiles it that way.
# am[implements a-rt-helpers-compiled-from-read-1017@11c85b] am[rests-on c-rt-verified-loader-prior-art-1017@5c8c1c]
# am[implements a-rt-helper-compiles-pinned-1017@b73a33]
class _PinnedFinder:
    def find_spec(self, fullname: str, path: object = None, target: object = None) -> ModuleSpec | None:
        file = _FILES.get(fullname)
        if file is None:
            return None
        return importlib.util.spec_from_file_location(fullname, file, loader=_CompiledFromRead(fullname, str(file)))


_FINDER = globals().get("_FINDER") or _PinnedFinder()
if _FINDER not in sys.meta_path:
    sys.meta_path.insert(0, _FINDER)


# A module Python holds under a newly pinned name that this process never compiled is dropped, so
# the next import compiles it here: a py-call module imported first and still running the import
# that pinned it, with a plain loader, or one a failed earlier import left. The import still running
# returns the compiled module; the plain one then finishes its body in a namespace nothing holds.
# am[implements a-rt-helpers-compiled-from-read-1017@11c85b] am[rests-on c-rt-cpython-import-binds-replacement-1017@6cab23]
# am[implements a-rt-helper-compiles-pinned-1017@b73a33] am[implements a-rt-rb-codec-1018@e3e552]
def pin(files: Mapping[str, Path]) -> None:
    """Serve each module name from its file through the pinned compile from now on. Raises
    ValueError for a name already pinned to another file."""

    for name, file in files.items():
        resolved = Path(file).resolve()
        if _FILES.setdefault(name, resolved) != resolved:
            raise ValueError(f"{name} is pinned to {_FILES[name]}, not {resolved}.")
        if name not in _COMPILED:
            sys.modules.pop(name, None)


# am[implements a-rt-helpers-compiled-from-read-1017@11c85b] am[implements a-rt-helper-compiles-pinned-1017@b73a33]
def loaded(names: Iterable[str]) -> tuple[tuple[Path, str], ...]:
    """Each named module's file with the SHA-256 of the bytes this process compiled it from. Raises
    ImportError when the module Python holds under a name is not the one the pinned loader compiled
    and ran, as when another import hook or a hand edit of sys.modules put a module in its place."""

    report = []
    for name in names:
        if name not in _RAN or sys.modules.get(name) is not _RAN[name]:
            raise ImportError(f"{name} is not the module the pinned loader compiled, so no digest names its code.",
                              name=name)
        report.append((_FILES[name], _COMPILED[name]))
    return tuple(report)


__all__ = ["loaded", "pin"]

"""Purpose: verify that GoalChainer's deontic library is whole inside its own package: every module
lib_deontic and lib_directive import resolves to a file the package ships, nothing they load comes
from outside it except pymetta's own libraries, the licence notice travels with it, and the
library's own core suites pass on GoalChainer's pymetta engine."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import metta
import pytest
from metta import S, Expression, Variable

from goal_chainer.deontic_engine import DEONTIC_DIRECTORY, DEONTIC_LIBRARY


# Every (library NAME TARGET) and (library NAME) form inside an atom, at any depth, but a template
# such as dl-path's (library deontic $rel), whose target is a variable, names no file.
# Time: linear in the atom's size.
# am[verifies a-rt-incorporate-deontic-1016@6ea255]
def _library_forms(atom: object) -> Iterator[tuple[str, ...]]:
    if isinstance(atom, Expression):
        children = atom.children
        if children and children[0] == S.library and not isinstance(children[-1], Variable):
            yield tuple(str(child) for child in children[1:])
        for child in children:
            yield from _library_forms(child)


# The library's own modules: everything but its suites, which only GoalChainer's tests load.
# am[verifies a-rt-incorporate-deontic-1016@6ea255]
def _runtime_modules() -> list[Path]:
    return sorted(
        path for path in DEONTIC_DIRECTORY.rglob("*.metta")
        if "tests" not in path.relative_to(DEONTIC_DIRECTORY).parts
    )


# am[verifies a-rt-incorporate-deontic-1016@6ea255] am[verifies c-rt-deontic-closure-1016@029061]
@pytest.mark.parametrize(
    "module", _runtime_modules(), ids=lambda path: path.relative_to(DEONTIC_DIRECTORY).as_posix()
)
def test_every_library_import_resolves_inside_the_package(module):
    for form in metta.forms(module.read_text(encoding="utf-8")):
        for reference in _library_forms(form):
            if len(reference) == 1:
                # A one-part reference names a library pymetta ships, such as lib_import.
                metta.library.card(reference[0])
                continue
            name, target = reference
            assert name == DEONTIC_LIBRARY.name, f"{module.name} imports from library {name}"
            path = DEONTIC_DIRECTORY / target
            assert path.resolve().is_relative_to(DEONTIC_DIRECTORY.resolve()), (
                f"{module.name} imports {target}, outside the library"
            )
            assert path.is_file() or path.with_name(path.name + ".metta").is_file(), (
                f"{module.name} imports {target}, which the package does not ship"
            )


# am[verifies a-rt-incorporate-deontic-1016@6ea255]
def test_both_entry_modules_and_the_licence_ship_with_the_library():
    assert (DEONTIC_DIRECTORY / "lib_deontic.metta").is_file()
    assert (DEONTIC_DIRECTORY / "lib_directive.metta").is_file()
    licence = (DEONTIC_DIRECTORY / "LICENSE").read_text(encoding="utf-8")
    assert licence.startswith("MIT License")
    assert "Copyright (c) 2026 Patrick Hammer" in licence
    assert "e5953fd3f908c8c439e1ffb6ca713571dbd0e32b" in (
        DEONTIC_DIRECTORY / "PROVENANCE.md"
    ).read_text(encoding="utf-8")


# One fresh process per suite, because pymetta keeps one engine per process and a suite defines
# and reasons over theories process-wide. The library is registered exactly as a review does it.
SUITE_DRIVER = """
import sys
from goal_chainer.deontic_engine import DEONTIC_DIRECTORY, DEONTIC_LIBRARY
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.modules import register_metta_library
with metta_engine(None) as engine:
    register_metta_library(DEONTIC_LIBRARY.name, DEONTIC_DIRECTORY, budget=None)
    engine.self.load(sys.argv[1])
"""


# A suite passes when every one of its checks prints a pass mark: pymetta's test raises at the
# first failing check, which ends the process nonzero.
# Time: one engine boot, about a second, and the suite's checks, under a second, per suite.
# am[verifies a-rt-deontic-library-suites-1016@5af2ad] am[verifies c-rt-deontic-suites-both-engines-1016@d11b3f]
# am[rests-on c-rt-pymetta-explain-shadows-1016@6d4d7a]
@pytest.mark.parametrize(
    "suite", sorted((DEONTIC_DIRECTORY / "tests" / "deontic").glob("test_*.metta")), ids=lambda path: path.name
)
def test_the_library_core_suite_passes_on_pymetta(suite):
    checks = sum(
        1 for form in metta.forms(suite.read_text(encoding="utf-8"))
        if isinstance(form, Expression) and form.children and form.children[0] == S.test
    )
    run = subprocess.run(
        [sys.executable, "-c", SUITE_DRIVER, str(suite)], capture_output=True, text=True
    )

    assert run.returncode == 0, run.stderr[-2000:]
    assert checks > 0
    assert run.stdout.count("✅") == checks
    assert "❌" not in run.stdout

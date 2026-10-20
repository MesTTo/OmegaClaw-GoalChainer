"""Purpose: verify that GoalChainer's SNARS library is whole inside its own package: every module
the aggregator imports and every Prolog file the kernel and guard load ship in it, nothing names a
Mettabase path or module, every py-call names a function goalchainer_snars defines, the guard's
sCASP copy ships inside it, the licences and provenance travel with it, no compiled or cache file
does, and the py-call helpers answer what Mettabase c079c89's answered."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import metta
import pytest
from metta import S, Expression, Variable

import goalchainer_snars
from goal_chainer.snars_program import SNARS_DIRECTORY

MODULES = sorted(SNARS_DIRECTORY.rglob("*.metta"))
CAT_IS_MAMMAL = (
    '(sh (tag P d so ()) "is" (args ((arg s (sh-atom (tag C c NoRoles ()) "cat")) '
    '(arg o (sh-atom (tag C c NoRoles ()) "mammal")))))'
)
CAT_IS_NOT_MAMMAL = (
    '(sh (tag P d so ()) "is" (args ((arg s (sh-atom (tag C c NoRoles ()) "cat")) '
    '(arg o (sh (tag M n so ()) "not" (args ((arg o (sh-atom (tag C c NoRoles ()) "mammal")))))))))'
)


# Every subexpression of an atom, the atom included. Time: linear in the atom's size.
# am[verifies a-rt-snars-adopt-library-1017@1231db]
def _expressions(atom: object) -> Iterator[Expression]:
    if isinstance(atom, Expression):
        yield atom
        for child in atom.children:
            yield from _expressions(child)


# The module's top-level forms as pymetta's reader parses them.
# am[verifies a-rt-snars-adopt-library-1017@1231db]
def _forms(module: Path) -> list[object]:
    return list(metta.forms(module.read_text(encoding="utf-8")))


# The expressions of a module whose head is the symbol named, at any depth.
# am[verifies a-rt-snars-adopt-library-1017@1231db]
def _headed(module: Path, head: str) -> list[Expression]:
    return [
        expression
        for form in _forms(module)
        for expression in _expressions(form)
        if expression.children and expression.children[0] == S[head]
    ]


# am[verifies a-rt-snars-adopt-library-1017@1231db]
def test_every_module_the_aggregator_imports_ships_beside_it():
    imported = [str(expression.children[2]) for expression in _headed(SNARS_DIRECTORY / "snars.metta", "import!")]
    assert len(imported) == 21
    for module in imported:
        assert (SNARS_DIRECTORY / f"{module}.metta").is_file(), module


# A one-part (library NAME) is a library pymetta ships; a two-part one names a file in this package.
# am[verifies a-rt-snars-adopt-library-1017@1231db]
@pytest.mark.parametrize("module", MODULES, ids=lambda path: path.relative_to(SNARS_DIRECTORY).as_posix())
def test_every_library_reference_resolves_inside_the_package(module):
    for form in _forms(module):
        for expression in _expressions(form):
            children = expression.children
            if not children or children[0] != S.library or isinstance(children[-1], Variable):
                continue
            if len(children) == 2:
                metta.library.card(str(children[1]))
                continue
            assert str(children[1]) == "snars", f"{module.name} names library {children[1]}"
            assert (SNARS_DIRECTORY / str(children[2])).is_file(), f"{module.name} imports {children[2]}"


# All nine py-calls the modules make, each naming a function goalchainer_snars defines.
# am[verifies a-rt-snars-adopt-library-1017@1231db] am[verifies a-rt-snars-python-helpers-1017@e0faec]
def test_every_py_call_names_a_goalchainer_snars_function():
    targets = [str(call.children[1].children[0]) for module in MODULES for call in _headed(module, "py-call")]
    assert len(targets) == 9
    for target in targets:
        owner, _, name = target.partition(".")
        assert owner == "goalchainer_snars", f"a module py-calls {target}"
        assert callable(getattr(goalchainer_snars, name, None)), f"goalchainer_snars has no {name}"


# am[verifies a-rt-snars-adopt-library-1017@1231db]
def test_no_shipped_file_names_a_mettabase_path_or_module():
    for path in SNARS_DIRECTORY.rglob("*"):
        if path.suffix in {".metta", ".pl"}:
            text = path.read_text(encoding="utf-8")
            assert "lib/mettabase" not in text and "mettabase_petta" not in text, path.name


# am[verifies a-rt-snars-adopt-library-1017@1231db]
def test_the_licence_and_provenance_ship_with_the_library():
    licence = (SNARS_DIRECTORY / "LICENSE").read_text(encoding="utf-8")
    assert licence.startswith("MIT License")
    assert "Copyright (c) 2026 Ahmad (MesTTo)" in licence
    assert "c079c894f3d97421242299f26db76c9de89b2438" in (SNARS_DIRECTORY / "PROVENANCE.md").read_text(
        encoding="utf-8"
    )


# The guard loads sCASP by a path relative to guard.pl, so the file it names must be the copy in
# this package, with sCASP's own licence and provenance beside it.
# am[verifies a-rt-scasp-vendor-1017@5bec02]
def test_the_guard_loads_the_scasp_copy_that_ships_inside_the_library():
    guard = SNARS_DIRECTORY / "snars" / "guard.pl"
    (imported,) = re.findall(r"^:- use_module\('([^']+)'", guard.read_text(encoding="utf-8"), re.M)
    target = (guard.parent / f"{imported}.pl").resolve()
    scasp = SNARS_DIRECTORY / "scasp"

    assert target == (scasp / "prolog" / "scasp.pl").resolve() and target.is_file()
    assert (scasp / "LICENSE").read_text(encoding="utf-8").lstrip().startswith("Apache License")
    assert "2dfbdb9cb41f8b9198f19289bab73dd72efad46a" in (scasp / "PROVENANCE.md").read_text(encoding="utf-8")


# A bytecode cache or a Prolog quick-load file depends on the interpreter that wrote it, so none
# ships, and the library's tree digest names only source.
# am[verifies a-rt-snars-adopt-library-1017@1231db] am[verifies a-rt-scasp-vendor-1017@5bec02]
def test_the_library_holds_no_compiled_or_cache_files():
    compiled = [
        path.relative_to(SNARS_DIRECTORY).as_posix()
        for path in SNARS_DIRECTORY.rglob("*")
        if path.name == "__pycache__" or path.suffix in {".pyc", ".qlf", ".py"}
    ]

    assert compiled == []


# The values Mettabase c079c89's mettabase_petta answered for the same inputs, taken from it when
# the helpers were adopted; the sid is also the one both engines computed for cat is mammal.
# am[verifies a-rt-snars-python-helpers-1017@e0faec]
@pytest.mark.parametrize(
    "helper, arguments, expected",
    [
        ("snars_sid", (CAT_IS_MAMMAL,), "s984f32de0eecc5e85a37a495fbe5ebab"),
        ("snars_canonical", (CAT_IS_MAMMAL,), CAT_IS_MAMMAL),
        ("snars_peel", (CAT_IS_MAMMAL,), f"(Peeled {CAT_IS_MAMMAL} False d)"),
        ("snars_peel", (CAT_IS_NOT_MAMMAL,), f"(Peeled {CAT_IS_MAMMAL} True d)"),
        ("snars_peel_notes", (CAT_IS_MAMMAL,), "(Notes (dets ) (aux ))"),
        ("snars_labels", (CAT_IS_MAMMAL,), "()"),
        ("snars_compounds", (CAT_IS_MAMMAL,), "()"),
        ("snars_receipt_hash", ("s984f32de0eecc5e85a37a495fbe5ebab", "probe"), "h2936dbbdc7260059"),
        (
            "snars_draw_tree",
            ('(PfNode "a cat is an animal" ded ((PfLeaf "a cat is a mammal") (PfLeaf "a mammal is an animal")))',),
            '"a cat is an animal  [ded]\\n+- a cat is a mammal  [obs]\\n\\\\- a mammal is an animal  [obs]"',
        ),
    ],
)
def test_the_helpers_answer_what_mettabase_answered(helper, arguments, expected):
    assert getattr(goalchainer_snars, helper)(*arguments) == expected


# am[verifies a-rt-snars-python-helpers-1017@e0faec]
def test_a_beta_draw_stays_inside_the_unit_interval_even_for_a_fresh_cell():
    for alpha, beta in ((0.0, 0.0), (2.0, 0.0), (10.0, 3.0)):
        assert 0.0 <= goalchainer_snars.snars_beta_sample(alpha, beta) <= 1.0

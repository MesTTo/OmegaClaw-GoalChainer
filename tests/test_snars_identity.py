"""Purpose: verify that a process names the SNARS it runs: each Python helper runs the bytes its
digest names, compiled from its file whichever module Python imports first and past a stale
bytecode cache, the py-call module's top level free of side effects a replaced copy could repeat;
a reload of a helper from changed bytes is refused before its code runs, so the py-call module
never keeps a function of another version; and a helper or library file that changes on disk
after the process took it is refused with ModuleChanged, by a world and by snars_identity()
alike. Each case runs a fresh interpreter on its own copy of the package, so no file of the tree
under test changes."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import os
import py_compile
from pathlib import Path

import pytest

from copied_package import PY_CALLS, copy_package, run_fresh

HELPERS = ["goalchainer_snars.py", "english.py", "syntax.py", "tnf.py"]


# goalchainer_snars imported first is still running the import that loads the helper package when
# the package compiles it again, so the import that started first must return the compiled module.
# The syntax module imported before any SNARS helper is compiled the same way, by its own package.
# am[verifies a-rt-helper-identity-regressions-1017@0c9c7d] am[verifies a-rt-helpers-compiled-from-read-1017@11c85b]
# am[verifies a-rt-rb-codec-1018@e3e552]
@pytest.mark.parametrize("first", ["goalchainer_snars", "goal_chainer.snars_python", "goal_chainer.sexpr.syntax"])
def test_python_holds_each_helper_compiled_from_its_file_whichever_is_imported_first(tmp_path, first) -> None:
    report = run_fresh(copy_package(tmp_path), f"""
import hashlib, importlib, json
first = importlib.import_module({first!r})
import goalchainer_snars
from goal_chainer import snars_python
from goal_chainer.sexpr import syntax
names = ("goalchainer_snars", "goal_chainer.snars_python.english", "goal_chainer.sexpr.syntax", "goal_chainer.snars_python.tnf")
print(json.dumps({{
    "copy": all(Path(sys.modules[name].__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve()) for name in names),
    "loaders": sorted({{type(sys.modules[name].__spec__.loader).__name__ for name in names}}),
    "bound": first in (goalchainer_snars, snars_python, syntax) and sys.modules["goalchainer_snars"] is goalchainer_snars,
    "one_sexpr": goalchainer_snars.parse is syntax.parse is snars_python.tnf.parse,
    "digests": [[path.name, digest, hashlib.sha256(path.read_bytes()).hexdigest()] for path, digest in snars_python.loaded()],
}}))
""")
    assert report["copy"] and report["bound"] and report["one_sexpr"]
    assert report["loaders"] == ["_CompiledFromRead"]
    assert [name for name, _, _ in report["digests"]] == HELPERS
    assert all(digest == file for _, digest, file in report["digests"])


# Imported first, goalchainer_snars finishes its plain-loaded body after the package replaced it,
# which changes nothing only while its top level does nothing but import and define.
# am[verifies a-rt-helper-identity-regressions-1017@0c9c7d] am[verifies c-rt-py-call-module-side-effect-free-1017@dfb2a8]
def test_the_py_call_modules_top_level_only_imports_and_defines() -> None:
    tree = ast.parse(PY_CALLS.read_text(encoding="utf-8"))
    docstring, *body = tree.body
    assert isinstance(docstring, ast.Expr) and isinstance(docstring.value, ast.Constant)
    assert {type(node) for node in body} <= {ast.Import, ast.ImportFrom, ast.FunctionDef}


# A timestamp pyc runs without its source being read when the source keeps the mtime and size it
# recorded, so a source changed that way runs stale code under a plain import; the helper runs
# its source, and its digest names those bytes. The change swaps the case of the module
# docstring's first character, "Purpose:" becoming "purpose:", so both docstrings come from the
# copied source's own AST whatever its wording.
# am[verifies a-rt-helper-identity-regressions-1017@0c9c7d] am[verifies a-rt-helpers-compiled-from-read-1017@11c85b]
# am[verifies a-integrate-stale-bytecode-fixture-1018@86850b]
def test_a_helper_runs_its_source_past_a_stale_bytecode_cache(tmp_path) -> None:
    site = copy_package(tmp_path)
    source = site / "goal_chainer" / "sexpr" / "syntax.py"
    py_compile.compile(
        str(source),
        cfile=importlib.util.cache_from_source(str(source)),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
    )
    stat = source.stat()
    old = source.read_bytes()
    stale = ast.get_docstring(ast.parse(old), clean=False)
    first = stale.splitlines()[0]
    new = old.replace(first.encode(), (first[0].swapcase() + first[1:]).encode(), 1)
    fresh = ast.get_docstring(ast.parse(new), clean=False)
    assert new != old and len(new) == len(old) and fresh != stale
    source.write_bytes(new)
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    report = run_fresh(site, """
import hashlib, importlib.util, json
from importlib.machinery import SourceFileLoader
from goal_chainer import snars_python
from goal_chainer.sexpr import syntax
path = Path(syntax.__file__)
plain = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("plain_sexpr", path, loader=SourceFileLoader("plain_sexpr", str(path))))
sys.modules["plain_sexpr"] = plain
plain.__spec__.loader.exec_module(plain)
print(json.dumps({"compiled": syntax.__doc__, "plain": plain.__doc__,
                  "digest": dict((p.name, d) for p, d in snars_python.loaded())["syntax.py"]}))
""")
    assert report["plain"] == stale
    assert report["compiled"] == fresh
    assert report["digest"] == hashlib.sha256(new).hexdigest()


# goalchainer_snars from-imports tnf's functions, so a reload of tnf from changed bytes would leave
# it calling the old ones under the new digest. The reload is refused before tnf runs a line, the
# identity refuses the changed file, and once the file is restored a reload of tnf or of the
# package itself compiles the same bytes and the identity is the one the process started with; a
# module put in tnf's place by hand is refused as a SNARS helper the process did not compile.
# am[verifies a-rt-helper-identity-regressions-1017@0c9c7d] am[verifies a-rt-helper-compiles-pinned-1017@b73a33]
def test_a_helper_reloaded_from_changed_bytes_is_refused_before_its_code_runs(tmp_path) -> None:
    report = run_fresh(copy_package(tmp_path), """
import hashlib, importlib, json, types
import goalchainer_snars
from goal_chainer import snars_engine, snars_python
from goal_chainer.errors import ModuleChanged
from goal_chainer.errors import DependencyUnavailableError
tnf = snars_python.tnf
identity, sid, digests = snars_engine.snars_identity(), goalchainer_snars.snars_sid("a"), snars_python.loaded()
path = Path(tnf.__file__)
original = path.read_text()
old_return = "    return SID_PREFIX + digest.hexdigest()"
assert original.count(old_return) == 1
path.write_text(original.replace(old_return, "    return 'reload-marker'"))
outcome = {"sid": sid, "path": str(path), "compiled": dict(digests)[path],
           "changed": hashlib.sha256(path.read_bytes()).hexdigest()}
for name, call in (("reload", lambda: importlib.reload(tnf)), ("identity", snars_engine.snars_identity)):
    try:
        call()
    except ModuleChanged as error:
        outcome[name] = [str(error.path), error.loaded, error.current]
outcome.update(direct=tnf.statement_sid("a"), wrapper=goalchainer_snars.snars_sid("a"),
               same_binding=goalchainer_snars.statement_sid is tnf.statement_sid,
               loaded_kept=snars_python.loaded() == digests)
path.write_text(original)
importlib.reload(tnf)
importlib.reload(snars_python)
outcome["restored"] = snars_engine.snars_identity() == identity and snars_python.loaded() == digests
held = sys.modules["goal_chainer.snars_python.tnf"]
sys.modules["goal_chainer.snars_python.tnf"] = types.ModuleType("goal_chainer.snars_python.tnf")
try:
    snars_engine.snars_identity()
except DependencyUnavailableError as error:
    outcome["replaced"] = dict(error.details)
sys.modules["goal_chainer.snars_python.tnf"] = held
outcome["put_back"] = snars_engine.snars_identity() == identity
print(json.dumps(outcome))
""")
    refused = [report["path"], report["compiled"], report["changed"]]
    assert report["reload"] == refused and report["identity"] == refused
    assert report["direct"] == report["wrapper"] == report["sid"] and report["same_binding"]
    assert report["loaded_kept"] and report["restored"]
    assert report["replaced"] == {"dependency": "SNARS helper", "module": "goal_chainer.snars_python.tnf"}
    assert report["put_back"]


# A helper changed after the process compiled it is refused before any world compiles, and the
# identity a session checks its store against is refused too: the process still runs the old code.
# am[verifies a-rt-helper-identity-regressions-1017@0c9c7d] am[verifies a-rt-snars-identity-resident-1017@3c837e]
def test_a_helper_changed_after_import_is_refused_by_a_world_and_the_identity(tmp_path) -> None:
    report = run_fresh(copy_package(tmp_path), """
import hashlib, json
from goal_chainer import snars_engine
from goal_chainer.errors import ModuleChanged
path = snars_engine.SNARS_HELPERS[0]
compiled = hashlib.sha256(path.read_bytes()).hexdigest()
path.write_text(path.read_text() + "\\n\\ndef probe_marker() -> str:\\n    return 'on disk only'\\n")
outcomes = {}
for name, call in (("world", lambda: snars_engine.prepare_snars_world(())), ("identity", snars_engine.snars_identity)):
    try:
        call()
    except ModuleChanged as error:
        outcomes[name] = [str(error.path), error.loaded, error.current]
print(json.dumps({"outcomes": outcomes, "path": str(path), "compiled": compiled,
                  "current": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "worlds": len(snars_engine.compiled_worlds())}))
""")
    assert Path(report["path"]).name == "goalchainer_snars.py"
    expected = [report["path"], report["compiled"], report["current"]]
    assert report["outcomes"] == {"world": expected, "identity": expected}
    assert report["worlds"] == 0


# Once a world has imported the library, a library changed on disk is refused by the identity and
# by every later world, so all of a process's worlds hold the one library its identity names.
# am[verifies a-rt-helper-identity-regressions-1017@0c9c7d] am[verifies a-rt-snars-identity-resident-1017@3c837e]
def test_a_process_runs_one_snars_library(tmp_path) -> None:
    report = run_fresh(copy_package(tmp_path), """
import json
from goal_chainer import snars_engine
from goal_chainer.errors import ModuleChanged
from goal_chainer.runtime.modules import tree_digest
from goal_chainer.snars_program import SNARS_DIRECTORY
pinned = snars_engine.prepare_snars_world(()).library_digest
with (SNARS_DIRECTORY / "snars" / "units.metta").open("a", encoding="utf-8") as module:
    module.write("\\n; changed after this process pinned its library\\n")
outcomes = {}
for name, call in (("identity", snars_engine.snars_identity),
                   ("guard world", lambda: snars_engine.prepare_snars_world(("guard",)))):
    try:
        call()
    except ModuleChanged as error:
        outcomes[name] = [str(error.path), error.loaded, error.current]
print(json.dumps({"outcomes": outcomes, "directory": str(SNARS_DIRECTORY), "pinned": pinned,
                  "changed": tree_digest(SNARS_DIRECTORY),
                  "worlds": [list(world.includes) for world in snars_engine.compiled_worlds()]}))
""")
    assert report["pinned"] != report["changed"]
    expected = [report["directory"], report["pinned"], report["changed"]]
    assert report["outcomes"] == {"identity": expected, "guard world": expected}
    assert report["worlds"] == [[]]

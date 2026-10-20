"""Purpose: test GoalChainer's failure classes: each keeps its stable code and read-only details,
refuses an empty message, a changed module names both digests, safe_repr writes what repr writes and
names a value repr raises for, and docs/errors.md lists exactly the classes and codes
goal_chainer.errors defines and exactly the exceptions the package's source defines outside that
family; and that the package, its tests, scripts and benchmarks reach pymetta's errors, like the
rest of pymetta, only through its public modules."""

import ast
import builtins
import math
import re
import sys
from pathlib import Path

import pytest

from goal_chainer import errors
from goal_chainer.errors import (
    DependencyUnavailableError,
    GoalChainerError,
    InvalidInputError,
    MettaEngineError,
    MissingAnswerError,
    ModuleChanged,
    PersistenceError,
    ProtocolError,
    safe_repr,
)

DOCUMENT = Path(__file__).resolve().parents[1] / "docs" / "errors.md"
BUILTIN_EXCEPTIONS = {name for name, value in vars(builtins).items()
                      if isinstance(value, type) and issubclass(value, BaseException)}
# The codes are the CLI's and the skill's contract, so the test names each one rather than reading
# it back from the class it checks.
CODES = {
    GoalChainerError: "goalchainer_error",
    DependencyUnavailableError: "dependency_unavailable",
    MissingAnswerError: "missing_answer",
    InvalidInputError: "invalid_input",
    ProtocolError: "protocol_error",
    MettaEngineError: "engine_error",
    PersistenceError: "persistence_error",
}


# am[verifies a-rt-rb-errors-sexpr-1018@f482e5]
@pytest.mark.parametrize(("error_type", "code"), CODES.items())
def test_each_failure_keeps_its_code_and_read_only_details(error_type, code):
    error = error_type("operation failed", details={"operation": "ask"})

    assert isinstance(error, GoalChainerError)
    assert str(error) == "operation failed"
    assert error.to_dict() == {"code": code, "message": "operation failed", "details": {"operation": "ask"}}
    with pytest.raises(TypeError):
        error.details["operation"] = "prove"


# am[verifies a-rt-rb-errors-sexpr-1018@f482e5]
def test_a_failure_copies_its_details_and_refuses_an_empty_message():
    details = {"path": "/missing"}
    error = DependencyUnavailableError("runtime missing", details=details)
    details["path"] = "/changed"

    assert error.details["path"] == "/missing"
    assert isinstance(MissingAnswerError("no answer"), DependencyUnavailableError)
    with pytest.raises(ValueError, match="message"):
        GoalChainerError(" ")
    with pytest.raises(TypeError, match="details"):
        InvalidInputError("bad", details=[("path", "/x")])


# A changed module names its path and both digests, whether it changed after the import or during it.
# am[verifies a-rt-rb-codec-1018@e3e552]
def test_a_changed_module_names_its_path_and_both_digests():
    after = ModuleChanged(Path("/lib/a.metta"), "old", "new")
    during = ModuleChanged(Path("/lib/a.metta"), "old", "new", while_importing=True)

    assert after.to_dict() == {"code": "module_changed", "message": after.message,
                               "details": {"path": "/lib/a.metta", "loaded": "old", "current": "new"}}
    assert "after this process imported it" in after.message
    assert "while it was being imported" in during.message


# am[verifies a-rt-rr-safe-repr-1018@ec9700]
@pytest.mark.parametrize("value", [-1, 0.5, math.nan, "it's", True, None, [1, "a"], 10**400, -(10**400)])
def test_safe_repr_writes_what_repr_writes(value):
    assert safe_repr(value) == repr(value)


# A value whose own repr raises.
# am[verifies a-rt-rr-safe-repr-1018@ec9700]
class _Unwritable:
    def __repr__(self) -> str:
        raise TypeError("no text")


# A list nested `depth` deep, built without recursion.
# am[verifies a-rt-rr-safe-repr-1018@ec9700]
def _nested(depth: int) -> list:
    value: list = []
    for _ in range(depth):
        value = [value]
    return value


# An int past the interpreter's digit limit is named by its sign and the limit in force; any other
# value whose repr raises, by its type and the exception.
# am[verifies a-rt-rr-safe-repr-1018@ec9700]
@pytest.mark.parametrize(("make", "name"), [
    (lambda: 10**5000, "an integer of more than {limit} digits"),
    (lambda: -(10**5000), "a negative integer of more than {limit} digits"),
    (lambda: [10**5000], "a value of type list whose repr raised ValueError"),
    (lambda: {"budget": (1, 10**5000)}, "a value of type dict whose repr raised ValueError"),
    (lambda: _nested(200_000), "a value of type list whose repr raised RecursionError"),
    (_Unwritable, "a value of type _Unwritable whose repr raised TypeError"),
], ids=["integer", "negative integer", "list holding one", "dict holding one", "nested too deep", "own repr raises"])
def test_safe_repr_names_a_value_repr_raises_for(make, name):
    assert safe_repr(make()) == name.format(limit=sys.get_int_max_str_digits())


# The document's first table, read back as class name to code, against every failure class the
# module defines.
# am[verifies a-rt-rb-errors-sexpr-1018@f482e5]
def test_the_error_document_lists_every_failure_class_and_code():
    table = DOCUMENT.read_text(encoding="utf-8").split("\n## ")[0]
    documented = dict(re.findall(r"^\| `(\w+)` \| `(\w+)` \|", table, re.MULTILINE))
    defined = {name: value.code for name, value in vars(errors).items()
               if isinstance(value, type) and issubclass(value, GoalChainerError)}

    assert documented == defined
    assert set(defined) == {error_type.__name__ for error_type in CODES} | {"ModuleChanged"}


# Every exception class goal_chainer's source defines whose bases reach a builtin exception without
# passing GoalChainerError, as module path and class name. Bases are matched by name, so two classes
# sharing a name pool their bases, and a base from another library is not followed.
# Time: one parse of each of the package's f files + a walk up the bases of each of its c classes.
# am[verifies a-rt-errors-doc-scope-1018@5a9e66]
def _exceptions_outside_the_family() -> set[str]:
    package = Path(errors.__file__).resolve().parent
    classes: list[tuple[str, str]] = []
    bases: dict[str, set[str]] = {}
    for path in sorted(package.rglob("*.py")):
        parts = path.relative_to(package.parent).with_suffix("").parts
        module = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                classes.append((module, node.name))
                bases.setdefault(node.name, set()).update(
                    ast.unparse(base).rsplit(".", 1)[-1] for base in node.bases)

    def reaches(name: str, targets: set[str], seen: frozenset[str] = frozenset()) -> bool:
        return name in targets or any(reaches(base, targets, seen | {name})
                                      for base in bases.get(name, ()) if base not in seen)

    return {f"{module}.{name}" for module, name in classes
            if reaches(name, BUILTIN_EXCEPTIONS) and not reaches(name, {"GoalChainerError"})}


# The document's list of exceptions raised outside the family, read back as qualified names, against
# every one the source defines.
# am[verifies a-rt-errors-doc-scope-1018@5a9e66]
def test_the_error_document_lists_every_exception_outside_the_family():
    section = DOCUMENT.read_text(encoding="utf-8").split("\n## ")[0]
    listed = set(re.findall(r"^- `(goal_chainer(?:\.\w+)+)`", section, re.MULTILINE))

    assert listed == _exceptions_outside_the_family()


# pymetta's private modules, metta._errors.errors among them, may move between builds, while
# metta.errors is the error family's public home and re-exports the same class objects
# (c-dg-public-errors-identical-1019), so every import of pymetta names public modules only.
# An import names a private module when any part after metta starts with _, the imported name of a
# from-import included, so `from metta import _lazy` is caught as `from metta._lazy import x` is.
# Time: one parse of each Python file under src, tests, scripts and benchmarks.
# am[verifies a-integrate-pymetta-public-errors-1019@05202a] am[rests-on c-dg-public-errors-identical-1019@7375e3]
def test_goalchainer_imports_no_private_pymetta_module():
    root = Path(__file__).resolve().parents[1]
    private = []
    for directory in ("src", "tests", "scripts", "benchmarks"):
        for path in sorted((root / directory).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    modules = [f"{node.module}.{alias.name}" for alias in node.names]
                elif isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                else:
                    continue
                private.extend(f"{path.relative_to(root)}:{node.lineno} {module}" for module in modules
                               if module.split(".")[0] == "metta"
                               and any(part.startswith("_") for part in module.split(".")[1:]))

    assert private == []

"""Purpose: read every text the OmegaClaw plugin's MeTTa suite hands GoalChainer's semantic reader,
found from the suite's own call sites, so semantic_capture asks for and keeps their answers and this
test proves each one replays offline."""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator

import pytest
from metta import Expression, Grounded, Symbol, forms

import gcskill
from goal_chainer import omegaclaw_skill
from goal_chainer.semantic_reader import SemanticReader, default_reader
from request_support import budget, review_request

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "goalchainer"


# am[verifies a-entry-plugin-texts-1017@5bb214]
class _Read(BaseException):
    """A call site reached the reader. A BaseException, so no `except Exception` on the skill's path
    can take it for the skill's own failure."""


# am[verifies a-entry-plugin-texts-1017@5bb214]
def _walk(atom: Any) -> Iterator[Any]:
    yield atom
    if isinstance(atom, Expression):
        for child in atom.children:
            yield from _walk(child)


# am[verifies a-entry-plugin-texts-1017@5bb214]
def _name(atom: Any) -> str | None:
    return atom.name if isinstance(atom, Symbol) else None


# am[verifies a-entry-plugin-texts-1017@5bb214]
def _suite_function(plugin: Path, name: str | None) -> str | None:
    """`module.function` when the module is one of the suite's own: run.sh puts src and the
    plugin's tests directory on the suite's Python path."""

    if name is None or name.count(".") != 1:
        return None
    module = name.split(".")[0]
    homes = (ROOT / "src", plugin / "tests")
    return name if any((home / f"{module}.py").is_file() for home in homes) else None


# am[verifies a-entry-plugin-texts-1017@5bb214]
def _skills(plugin: Path) -> dict[str, tuple[list[str], Expression]]:
    """Each skill goalchainer.metta defines as one call into the suite's Python: its parameters and
    that call, as in `(= (goalchainer-request $request) (py-call (gcskill.request
    (goalchainer-python) $request)))`."""

    skills = {}
    for form in forms((plugin / "goalchainer.metta").read_text(encoding="utf-8")):
        if not (isinstance(form, Expression) and _name(form.head) == "=" and len(form.args) == 2):
            continue
        pattern, body = form.args
        if not isinstance(pattern, Expression) or _name(pattern.head) is None:
            continue
        calls = [
            atom for atom in _walk(body)
            if isinstance(atom, Expression) and _suite_function(plugin, _name(atom.head))
        ]
        if len(calls) == 1:
            skills[_name(pattern.head)] = ([str(arg) for arg in pattern.args], calls[0])
    return skills


# am[verifies a-entry-plugin-texts-1017@5bb214]
def _argument(atom: Any, bound: dict[str, Any]) -> Any:
    """A literal argument's value: a string, the interpreter (goalchainer-python) names, or a bound
    parameter; anything else makes the call site not literal, as None."""

    if isinstance(atom, Grounded) and isinstance(atom.value, str):
        return atom.value
    if isinstance(atom, Expression) and _name(atom.head) == "goalchainer-python" and not atom.args:
        return sys.executable
    return bound.get(str(atom))


# A suite call hands GoalChainer text only through the transport its skills call, so a call counts
# when its module is that transport or imports it. The suite's helpers into Omega's own modules,
# which import Omega's files from the Omega root, hand GoalChainer nothing.
# Time: one parse of the call's module, its size in nodes.
# am[verifies a-entry-plugin-texts-1017@5bb214] am[verifies a-oc-plugin-suite-main-1018@7aee50]
def _reaches_transport(plugin: Path, function: str, transports: set[str]) -> bool:
    """Whether the suite function `module.function` can reach GoalChainer through one of the
    `transports`, the modules goalchainer.metta's skills call into."""

    module = function.split(".")[0]
    if module in transports:
        return True
    source = next(
        home / f"{module}.py" for home in (ROOT / "src", plugin / "tests") if (home / f"{module}.py").is_file()
    )
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return bool(imported & transports)


# Time: one walk of each test file's forms, each call site resolved through one skill definition.
# am[verifies a-entry-plugin-texts-1017@5bb214]
def _call_sites(plugin: Path) -> list[tuple[str, tuple[Any, ...]]]:
    """Every call the suite's test files make into its Python with literal arguments and a route to
    GoalChainer, a plugin skill resolved through its goalchainer.metta definition."""

    skills = _skills(plugin)
    transports = {_name(call.head).split(".")[0] for _, call in skills.values()}
    sites = []
    for test_file in sorted((plugin / "tests").glob("test_*.metta")):
        for form in forms(test_file.read_text(encoding="utf-8")):
            for atom in _walk(form):
                if not isinstance(atom, Expression):
                    continue
                bound: dict[str, Any] = {}
                call = atom
                if _name(atom.head) in skills:
                    parameters, call = skills[_name(atom.head)]
                    values = [_argument(arg, {}) for arg in atom.args]
                    if len(values) != len(parameters) or None in values:
                        continue
                    bound = dict(zip(parameters, values))
                function = _suite_function(plugin, _name(call.head))
                if function is None or not _reaches_transport(plugin, function, transports):
                    continue
                values = [_argument(arg, bound) for arg in call.args]
                if None not in values:
                    sites.append((function, tuple(values)))
    return sites


# am[verifies a-entry-plugin-texts-1017@5bb214]
def _module(plugin: Path, name: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The suite's module by name. skill_probe asks its host's SWI-Prolog for its home through
    janus_swi, so it is imported against a stand-in that answers
    any directory, since this process starts no child; the stand-in leaves sys.modules again at
    once, because pymetta refuses to start beside a janus_swi other than its own."""

    if name == "gcskill":
        return gcskill
    spec = importlib.util.spec_from_file_location(name, plugin / "tests" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    janus = ModuleType("janus_swi")
    janus.query_once = lambda _: {"H": str(ROOT)}  # type: ignore[attr-defined]
    with monkeypatch.context() as importing:
        importing.setitem(sys.modules, "janus_swi", janus)
        spec.loader.exec_module(module)
    return module


# Only the skill's process is served differently: gcskill.call's subprocess.run runs
# goal_chainer.omegaclaw_skill.main in this process, so gcskill turns a typed failure into
# GoalChainerSkillError exactly as it does for the child, and the first read stops the call before
# any model work. Domain requests validate their selected declaration before reading the text.
# am[verifies a-entry-plugin-texts-1017@5bb214]
def _texts_read(plugin: Path, monkeypatch: pytest.MonkeyPatch) -> set[str]:
    texts: set[str] = set()

    # am[verifies a-entry-plugin-texts-1017@5bb214]
    # am[verifies a-integrate-request-budget-surface-1018@d6882c]
    def recording_read(self: SemanticReader, text: str, *, budget) -> Any:
        texts.add(text)
        raise _Read

    # am[verifies a-entry-plugin-texts-1017@5bb214]
    def in_process(command: list[str], *, input: str, **_: Any) -> SimpleNamespace:
        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdin", io.StringIO(input))
        with contextlib.redirect_stdout(stdout):
            code = omegaclaw_skill.main(command[command.index("goal_chainer.omegaclaw_skill") + 1 :])
        return SimpleNamespace(returncode=code, stdout=stdout.getvalue(), stderr="")

    monkeypatch.setattr(SemanticReader, "read", recording_read)
    monkeypatch.setattr(gcskill, "subprocess", SimpleNamespace(run=in_process))
    # A skill that rejects its request as invalid read nothing; any other failure, a missing
    # dependency or a protocol error included, fails here rather than dropping a text unseen.
    for function, arguments in _call_sites(plugin):
        module, name = function.split(".")
        try:
            getattr(_module(plugin, module, monkeypatch), name)(*arguments)
        except _Read:
            pass
        except gcskill.GoalChainerSkillError as error:
            if error.code != "invalid_input":
                raise
    return texts


# The derivation, on a sample suite: a request's text and a probe's request text are read; a
# malformed dispatch request fails typed before any read; a comment and a print are not calls.
# am[verifies a-entry-plugin-texts-1017@5bb214]
# am[verifies a-integrate-domain-surface-1018@759698]
def test_a_call_site_counts_only_when_its_skill_reads_its_text(tmp_path, monkeypatch):
    plugin = tmp_path / "goalchainer"
    (plugin / "tests").mkdir(parents=True)
    shutil.copy(PLUGIN / "goalchainer.metta", plugin / "goalchainer.metta")
    shutil.copy(PLUGIN / "tests" / "skill_probe.py", plugin / "tests" / "skill_probe.py")
    shutil.copy(PLUGIN / "tests" / "omega_modules.py", plugin / "tests" / "omega_modules.py")
    (plugin / "tests" / "test_sample.metta").write_text(
        "; a comment holding (goalchainer-request \"not a call\")\n"
        '!(py-call (omega_modules.by_name "src/utils.py"))\n'
        f'!(test (goalchainer-request {json.dumps(review_request("Incident text the request reads."))}) True)\n'
        '!(test (goalchainer-snars-dispatch "not json") True)\n'
        '!(test (py-call (skill_probe.failure_code (goalchainer-python) '
        '"goalchainer-snars-dispatch" "also not json")) invalid_input)\n'
        '!(test (py-call (skill_probe.request_under_host_settings (goalchainer-python) '
        f'{json.dumps(review_request("Incident text the probe reads."))})) True)\n'
        '!(println! "printed, never decided")\n',
        encoding="utf-8",
    )

    assert _texts_read(plugin, monkeypatch) == {
        "Incident text the request reads.",
        "Incident text the probe reads.",
    }


# am[verifies a-entry-plugin-texts-1017@5bb214] am[verifies a-jev-entry-texts-in-pytest-1017@eb1bb6]
# am[verifies a-integrate-request-budget-surface-1018@d6882c]
def test_every_text_the_plugin_suite_reads_replays_offline(monkeypatch):
    with monkeypatch.context() as patched:
        texts = _texts_read(PLUGIN, patched)
    reader = default_reader(budget=budget())

    assert texts
    for text in sorted(texts):
        reading = reader.read(text, budget=budget())
        assert reading.text == text
        assert all(proposition.answer for proposition in reading.propositions)

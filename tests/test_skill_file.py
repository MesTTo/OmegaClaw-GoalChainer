import ast
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_FILE = REPO_ROOT / "integrations/omegaclaw/goalchainer_skill.metta"
GCSKILL = REPO_ROOT / "src/gcskill.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# The commands the agent emits and OmegaClaw dispatches by (eval $command).
COMMANDS = ("decision", "solve", "motivation", "directive", "snars")


def test_skill_file_dispatches_two_part_pycall():
    # OmegaClaw resolves a py-call as a TWO-part module.function (PeTTa cannot split
    # a three-part path). Every command must dispatch through the top-level gcskill
    # module, e.g. (py-call (gcskill.decision $request)).
    source = SKILL_FILE.read_text()
    for command in COMMANDS:
        assert f"(goalchainer-{command} $request)" in source
        assert f"(py-call (gcskill.{command} $request))" in source
    assert "(goalchainer-snars-dispatch $request)" in source
    assert "(py-call (gcskill.dispatch $request))" in source
    assert "(goalchainer-directive-dispatch $request)" in source
    assert "(py-call (gcskill.directive_dispatch $request))" in source
    assert "(goalchainer-thread-dispatch $request)" in source
    assert "(py-call (gcskill.thread_dispatch $request))" in source
    assert "(py-call (gcskill.system_prompt))" in source


def test_skill_file_advertises_skills_for_getskills():
    # getSkills reads one "- description: name arg" line per command so the agent is
    # told the commands exist.
    source = SKILL_FILE.read_text()
    assert "(goalchainer-skill-docs)" in source
    for command in COMMANDS:
        assert f"goalchainer-{command} request" in source
    assert "goalchainer-snars-dispatch json_request" in source
    assert "goalchainer-directive-dispatch json_request" in source
    assert "goalchainer-thread-dispatch json_request" in source


def test_gcskill_exposes_the_callable_surface():
    # The two-part py-call targets must be real top-level functions in gcskill.
    tree = ast.parse(GCSKILL.read_text())
    defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    for command in COMMANDS:
        assert command in defined
    assert "dispatch" in defined
    assert "directive_dispatch" in defined
    assert "thread_dispatch" in defined
    assert "system_prompt" in defined


def test_petta_top_level_atom_modules_are_packaged():
    configuration = tomllib.loads(PYPROJECT.read_text())

    assert set(configuration["tool"]["setuptools"]["py-modules"]) == {
        "gcskill",
        "goalchainer_thread_atoms",
    }
    assert configuration["tool"]["setuptools"]["data-files"][
        "integrations/threadkeeper"
    ] == ["integrations/threadkeeper/goalchainer_threadkeeper.metta"]

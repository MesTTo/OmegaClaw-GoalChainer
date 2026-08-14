import ast
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_FILE = REPO_ROOT / "plugins/goalchainer/goalchainer.metta"
GCSKILL = REPO_ROOT / "src/gcskill.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# The commands the agent emits and OmegaClaw dispatches by (eval $command).
COMMANDS = ("decision", "solve", "motivation", "directive", "snars")


def test_skill_file_dispatches_two_part_pycall():
    # py-call resolves a TWO-part module.function (PeTTa cannot split a
    # three-part path). Every command dispatches through the top-level gcskill
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


def test_plugin_registers_every_command_with_add_skill():
    # add-skill is what puts a command in helper.LLM_COMMANDS, and the loop
    # rejects anything outside that set as UNKNOWN_SKILL_CALL. A catalogue line
    # on its own is a skill the agent is told to use and then refused.
    source = SKILL_FILE.read_text()
    assert "(= (loadOmegaClawPlugin)" in source
    for command in COMMANDS:
        assert f"(add-skill goalchainer-{command}" in source
    for command in ("snars-dispatch", "directive-dispatch", "thread-dispatch"):
        assert f"(add-skill goalchainer-{command}" in source
    # the argument names the catalogue line ends with
    assert source.count("(request))") >= len(COMMANDS)
    assert source.count("(json_request))") == 3


def test_plugin_puts_the_pipeline_in_the_prompt():
    # The required pipeline is context, not a skill the agent must remember.
    source = SKILL_FILE.read_text()
    assert "(add-prompt-extension goalchainer (goalchainer-system-prompt))" in source


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


def test_runtime_atoms_and_mettascript_policy_are_packaged():
    configuration = tomllib.loads(PYPROJECT.read_text())

    assert set(configuration["tool"]["setuptools"]["py-modules"]) == {
        "gcskill",
        "goalchainer_thread_atoms",
    }
    assert configuration["tool"]["setuptools"]["data-files"][
        "integrations/threadkeeper"
    ] == [
        "integrations/threadkeeper/goalchainer_threadkeeper.metta",
        "integrations/threadkeeper/goalchainer_threadkeeper_docs.metta",
    ]
    assert configuration["tool"]["setuptools"]["data-files"][
        "integrations/mettascript"
    ] == ["integrations/mettascript/runner.mjs"]

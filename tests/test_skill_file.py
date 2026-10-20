"""Purpose: verify the OmegaClaw plugin seam's shape: two-part py-calls into gcskill that pass the
recorded interpreter, add-skill registration of exactly the skills the plugin defines, the prompt
extension, and what the wheel packages."""

import ast
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_FILE = REPO_ROOT / "plugins/goalchainer/goalchainer.metta"
GCSKILL = REPO_ROOT / "src/gcskill.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# The commands the agent emits and OmegaClaw dispatches by (eval $command), each with the gcskill
# function its definition py-calls.
# am[verifies a-integrate-domain-surface-1018@759698]
# am[verifies a-v2-cli-skill-surface-1020@6f755c]
SKILLS = {
    "goalchainer-request": "request",
    "goalchainer-directive-dispatch": "directive_dispatch",
    "goalchainer-snars-dispatch": "dispatch",
    "goalchainer-motivation-dispatch": "motivation_dispatch",
}


# am[verifies a-rt-skill-process-boundary-1016@a36729] am[verifies a-tk-entrypoints-1018@5d9a27]
# am[verifies a-oc-plugin-host-module-1018@180dc9]
def test_skill_file_dispatches_two_part_pycall():
    # The plugin calls the top-level gcskill module with the interpreter the installer recorded in
    # goalchainer_host.py, which it reads through a py-call rather than a relative import!.
    source = SKILL_FILE.read_text()
    assert "(= (goalchainer-python) (py-call (goalchainer_host.python)))" in source
    assert "!(import!" not in source
    defined = dict(re.findall(
        r"^\(= \((goalchainer-[a-z-]+) \$request\)\s+"
        r"\(py-call \(gcskill\.(\w+) \(goalchainer-python\) \$request\)\)\)",
        source,
        re.MULTILINE,
    ))
    assert defined == SKILLS
    assert "(py-call (gcskill.system_prompt (goalchainer-python)))" in source



# The reader's settings are Omega tunables: declared (empty), as PeTTa needs to compile a call to one,
# bound by configure from the install's recorded default, and handed to the transport once, in the
# transport's order, before the prompt extension starts the first skill process.
# am[verifies a-irp-reader-keys-1018@14bc18]
def test_plugin_configures_its_reader_settings_and_hands_them_to_the_transport():
    import sys  # noqa: PLC0415

    sys.path.insert(0, str(REPO_ROOT / "src"))
    import gcskill  # noqa: PLC0415

    source = SKILL_FILE.read_text()
    keys = [key for key, _ in gcskill.READER_VARIABLES]
    for key in keys:
        assert f"(= ({key}) (empty))" in source
        assert f'(configure {key} (py-call (goalchainer_host.reader_default "{key}")))' in source
    handed = re.search(r"\(py-call \(gcskill\.configure_reader((?:\s+\(\w+\))+)\)\)", source)
    assert handed is not None and re.findall(r"\((\w+)\)", handed.group(1)) == keys
    assert source.index("(configure goalchainerJevUrl") < handed.start() < source.index("(add-prompt-extension")

# am[verifies a-tk-entrypoints-1018@5d9a27]
# am[verifies a-integrate-request-budget-surface-1018@d6882c]
# am[verifies a-oc-plugin-entry-1018@3f1f44]
def test_plugin_registers_every_command_with_add_skill():
    # Omega's loader calls loadOmegaPlugin, and add-skill is what puts a command
    # among the tools the loop offers the LLM, its arguments the tool's
    # parameters. A registration without a definition is a tool the loop
    # dispatches to nothing. Every registered skill takes JSON with explicit
    # request limits; every call carries the selected operation's fields.
    source = SKILL_FILE.read_text()
    assert "(= (loadOmegaPlugin)" in source
    registered = dict(re.findall(r'\(add-skill (goalchainer-[a-z-]+)\s+"[^"]*"\s+\((\w+)\)\)', source))
    assert registered == {skill: "json_request" for skill in SKILLS}


def test_plugin_puts_the_pipeline_in_the_prompt():
    # The required pipeline is context, not a skill the agent must remember.
    source = SKILL_FILE.read_text()
    assert "(add-prompt-extension goalchainer (goalchainer-system-prompt))" in source


# am[verifies a-tk-entrypoints-1018@5d9a27]
def test_gcskill_exposes_the_callable_surface():
    # The two-part py-call targets must be real top-level functions in gcskill, and every public
    # function there is one of them, one of the halves of the child-process transport, the reader
    # settings loadOmegaPlugin hands over, or the check the installer runs on their defaults.
    tree = ast.parse(GCSKILL.read_text())
    public = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    assert public == {*SKILLS.values(), "system_prompt", "call", "child_environment", "skill_environment",
                      "configure_reader", "reader_setting"}


# The wheel installs nothing outside its packages and modules: no data-files table puts files under
# the environment's prefix.
# am[verifies a-rt-snars-python-helpers-1017@e0faec] am[verifies a-rt-p3-markdown-vendored-1017@88745b]
# am[verifies a-tk-packaging-1018@7cd2e8]
def test_py_call_modules_are_packaged():
    configuration = tomllib.loads(PYPROJECT.read_text())

    assert set(configuration["tool"]["setuptools"]["py-modules"]) == {
        "gcskill",
        "goalchainer_snars",
        "goalchainer_markdown",
    }
    assert "data-files" not in configuration["tool"]["setuptools"]

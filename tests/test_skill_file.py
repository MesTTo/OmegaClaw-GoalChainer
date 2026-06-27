import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_FILE = REPO_ROOT / "integrations/omegaclaw/goalchainer_skill.metta"
GCSKILL = REPO_ROOT / "src/gcskill.py"

# The commands the agent emits and OmegaClaw dispatches by (eval $command).
COMMANDS = ("decision", "solve", "motivation", "snars")


def test_skill_file_dispatches_two_part_pycall():
    # OmegaClaw resolves a py-call as a TWO-part module.function (PeTTa cannot split
    # a three-part path). Every command must dispatch through the top-level gcskill
    # module, e.g. (py-call (gcskill.decision $request)).
    source = SKILL_FILE.read_text()
    for command in COMMANDS:
        assert f"(goalchainer-{command} $request)" in source
        assert f"(py-call (gcskill.{command} $request))" in source
    assert "(py-call (gcskill.system_prompt))" in source


def test_skill_file_advertises_skills_for_getskills():
    # getSkills reads one "- description: name arg" line per command so the agent is
    # told the commands exist.
    source = SKILL_FILE.read_text()
    assert "(goalchainer-skill-docs)" in source
    for command in COMMANDS:
        assert f"goalchainer-{command} request" in source


def test_gcskill_exposes_the_callable_surface():
    # The two-part py-call targets must be real top-level functions in gcskill.
    tree = ast.parse(GCSKILL.read_text())
    defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    for command in COMMANDS:
        assert command in defined
    assert "system_prompt" in defined

"""Purpose: verify what GoalChainer's two command lines accept, goalchainer's commands and
goalchainer-skill's skills, read from each parser's own help, and that skill dispatch refuses a name
the command line does not offer."""

import re

import pytest

from goal_chainer import cli, omegaclaw_skill
from goal_chainer.errors import InvalidInputError


# argparse prints a positional's choices as one {a,b,...} group under "positional arguments:", so
# that group is the parser's own list of what it accepts.
# am[verifies a-tk-entrypoints-1018@5d9a27]
def _choices(main, capsys) -> set[str]:
    with pytest.raises(SystemExit) as exited:
        main(["--help"])
    assert exited.value.code == 0
    section = capsys.readouterr().out.split("positional arguments:", 1)[1]
    listed = re.search(r"\{([^}]*)\}", section)
    assert listed is not None, section
    return set(listed.group(1).split(","))


# am[verifies a-tk-entrypoints-1018@5d9a27]
# am[verifies a-integrate-domain-surface-1018@759698]
# am[verifies a-dd-show-1018@f9e4e9]
# am[verifies a-dg-cli-1019@996a1b]
def test_goalchainer_accepts_exactly_its_commands(capsys):
    assert _choices(cli.main, capsys) == {
        "request",
        "show",
        "directive",
        "snars",
        "relevance",
        "diagnose",
    }


# am[verifies a-tk-entrypoints-1018@5d9a27]
# am[verifies a-integrate-domain-surface-1018@759698]
def test_goalchainer_skill_accepts_exactly_its_skills(capsys):
    assert _choices(omegaclaw_skill.main, capsys) == {
        "goalchainer-system-prompt",
        "goalchainer-request",
        "goalchainer-directive-dispatch",
        "goalchainer-snars-dispatch",
    }


# Removed commands fail before they can invoke a reader or write a record.
# am[verifies a-tk-entrypoints-1018@5d9a27] am[verifies a-integrate-domain-surface-1018@759698]
@pytest.mark.parametrize("name", ["thread-dispatch", "decision", "solve", "codebase-demo",
                                  "proof-audit", "ontology-context", "tests", "motivation",
                                  "directive", "snars"])
def test_skill_dispatch_refuses_removed_skills(name):
    with pytest.raises(InvalidInputError, match="Unknown GoalChainer skill"):
        omegaclaw_skill.run_skill("goalchainer-" + name, "{}")

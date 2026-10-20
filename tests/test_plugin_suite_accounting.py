"""Purpose: verify that plugins/goalchainer/tests/run.sh counts a suite's checks against its declared
test forms, on the pinned engine: a complete suite passes, and a run that stopped after a passing
prefix, a failed check, a source with no test form and no suite at all each fail. Also verify the
declared-form rule on its own (directive tests count, a definition's do not, a test with one argument
counts and comments declare no tests) and that the shipped suites declare two-argument test
forms the rule counts."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "plugins" / "goalchainer" / "tests"
LIBRARY = REPO / "integrations" / "omegaclaw" / "_omega_lib.sh"

_spec = importlib.util.spec_from_file_location("suite_accounting", TESTS / "suite_accounting.py")
accounting = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(accounting)

# Inert suites for the pinned engine, each with the line run.sh must print for it.
# am[verifies a-integrate-accounting-comment-contract-1019@c974ce]
SUITES = {
    "test_complete.metta": ("!(test ; (test 0 1) is only a comment\n (+ 1 1) 2)\n!(test (+ 2 2) 4)\n",
                            "PASS  test_complete.metta  (2 checks)"),
    "test_prefix.metta": ("!(test (+ 1 1) 2)\n!(py-call (sys.exit 0))\n!(test (+ 2 2) 4)\n",
                          "FAIL  test_prefix.metta  (1 of 2 checks reported, exit 0): "
                          "the run stopped after 1 of its 2 checks"),
    "test_failed.metta": ("!(test (+ 1 1) 2)\n!(test (+ 1 1) 3)\n",
                          "FAIL  test_failed.metta  (2 of 2 checks reported, exit 1): 1 failed"),
    "test_empty.metta": ("!(println! nothing-checked)\n",
                         "FAIL  test_empty.metta  (0 of 0 checks reported, exit 0): its source declares no test"),
}


# A copy of the runner, its accounting and the drivers' library in a tree of their own holding
# <suites>, beside an Omega directory with the plugin's directory, which is all the runner checks for.
# Answers the runner.
# am[verifies a-integrate-mettaspeak-assertion-accounting-1019@905c82]
def _runner(root: Path, suites: dict[str, str]) -> Path:
    tests = root / "plugins" / "goalchainer" / "tests"
    tests.mkdir(parents=True)
    for name in ("run.sh", "suite_accounting.py"):
        shutil.copy(TESTS / name, tests / name)
    (root / "integrations" / "omegaclaw").mkdir(parents=True)
    shutil.copy(LIBRARY, root / "integrations" / "omegaclaw" / LIBRARY.name)
    (root / "omega" / "plugins" / "goalchainer").mkdir(parents=True)
    for name, text in suites.items():
        (tests / name).write_text(text)
    return tests / "run.sh"


# The runner run with this interpreter, the pinned engine's, as the plugin's recorded one.
# am[verifies a-integrate-mettaspeak-assertion-accounting-1019@905c82]
def _run(runner: Path, *suites: str) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "GOALCHAINER_PYTHON": sys.executable,
                   "OMEGACLAW_DIR": str(runner.parents[3] / "omega")}
    return subprocess.run(["bash", str(runner), *suites], env=environment, capture_output=True, text=True,
                          check=False)


# Each suite runs on the pinned engine and gets its own verdict: only the complete one passes, and
# the run fails once per other suite, a prefix that exited 0 among them.
# Time: four engine runs of a few checks each.
# am[verifies a-integrate-mettaspeak-assertion-accounting-1019@905c82]
# am[verifies a-integrate-accounting-comment-contract-1019@c974ce]
def test_only_a_suite_that_reports_every_declared_check_passes(tmp_path):
    runner = _runner(tmp_path, {name: text for name, (text, _) in SUITES.items()})

    result = _run(runner)

    shown = result.stdout.splitlines()
    for _, verdict in SUITES.values():
        assert verdict in shown, result.stdout + result.stderr
    assert "1 passed, 3 failed" in shown
    assert "ALL GOALCHAINER PLUGIN TESTS PASSED" not in result.stdout
    assert result.returncode == 3


# A named suite runs alone and a complete one passes the whole run; a name that is no file fails it.
# am[verifies a-integrate-mettaspeak-assertion-accounting-1019@905c82]
# am[verifies a-integrate-accounting-comment-contract-1019@c974ce]
def test_a_named_suite_runs_alone(tmp_path):
    runner = _runner(tmp_path, {name: text for name, (text, _) in SUITES.items()})

    complete = _run(runner, str(runner.parent / "test_complete.metta"))
    missing = _run(runner, str(runner.parent / "test_absent.metta"))

    assert complete.returncode == 0, complete.stdout + complete.stderr
    assert complete.stdout.splitlines()[0] == SUITES["test_complete.metta"][1]
    assert "ALL GOALCHAINER PLUGIN TESTS PASSED" in complete.stdout
    assert missing.returncode == 1
    assert "no suite" in missing.stderr


# With no suite to run the runner fails before it starts anything, where it used to pass.
# am[verifies a-integrate-mettaspeak-assertion-accounting-1019@905c82]
def test_no_suite_at_all_fails(tmp_path):
    result = _run(_runner(tmp_path, {}))

    assert result.returncode == 1
    assert "no test_*.metta suite" in result.stderr
    assert "PASSED" not in result.stdout


# A test in a directive counts, one inside a let directive too, one in a definition does not, and one
# with a single argument does, so that never-reported check fails the count.
# am[verifies a-integrate-mettaspeak-assertion-accounting-1019@905c82]
def test_the_declared_tests_are_those_in_directives_whatever_their_arity():
    source = "!(test (+ 1 1) 2)\n!(let $x 5 (test $x 5))\n(= (helper) (test 1 1))\n!(test (+ 2 2))\n"

    assert accounting.declared(source) == [1, 2, 4]
    passed, verdict = accounting.judge("one-argument", source, 0, "is 2, should 2. ✅ \nis 5, should 5. ✅ \n")
    assert not passed
    assert verdict.endswith("the run stopped after 2 of its 3 checks")


# Comments inside a form declare no checks; an extra reported check still fails.
# am[verifies a-integrate-mettaspeak-assertion-accounting-1019@905c82]
# am[verifies a-integrate-accounting-comment-contract-1019@c974ce]
def test_comments_are_ignored_and_extra_reports_fail():
    commented = accounting.judge("commented", "!(test ; (test 0 1)\n (+ 1 1) 2)\n", 0, "is 2, should 2. ✅ \n")
    extra = accounting.judge("extra", "!(test (+ 1 1) 2)\n", 0, "is 2, should 2. ✅ \nis 2, should 2. ✅ \n")

    assert commented == (True, "PASS  commented  (1 checks)")
    assert extra == (False, "FAIL  extra  (2 of 1 checks reported, exit 0): the run reported 2 checks for 1 test forms")


# The shipped suites hold only two-argument test forms the rule counts, as many as their runs report
# (13 and 3, with the plugin installed).
# am[verifies a-integrate-mettaspeak-assertion-accounting-1019@905c82]
def test_the_shipped_suites_declare_two_argument_tests():
    counts = {}
    for suite in sorted(TESTS.glob("test_*.metta")):
        source = suite.read_text()
        counts[suite.name] = len(accounting.declared(source))
        forms = [atom for form in accounting.top_level_forms(source) if form.directive
                 for atom in accounting._walk(accounting.parse(form.text[1:].lstrip()))
                 if isinstance(atom, list) and atom and atom[0] == accounting.Symbol("test")]
        assert {len(form) - 1 for form in forms} == {2}
    assert counts == {"test_goalchainer_plugin.metta": 13, "test_goalchainer_skill_process.metta": 3}

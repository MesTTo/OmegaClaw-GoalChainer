"""Purpose: verify that no child process GoalChainer starts inherits what booting the in-process
pymetta engine set in this process's environment: the restore rule over every way a variable can
stand against the boot, a boot that raises after setting a variable, a child environment asked for
while another thread's boot has changed the environment but not yet recorded it, a child of an
engine booted in a fresh interpreter reading no bundled SWI home, and every subprocess launch naming its
child's environment."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import metta
import pytest

import goal_chainer
from goal_chainer.runtime import engine as runtime_engine

PACKAGE = Path(goal_chainer.__file__).resolve().parent
# Each way a variable can stand against the boot's record: the record, the base environment a
# launcher starts from, and the child's environment.
RULE = {
    "set by the boot, absent before": (
        {"SWI_HOME_DIR": (None, "/bundled")}, {"SWI_HOME_DIR": "/bundled", "PATH": "/bin"}, {"PATH": "/bin"}),
    "changed by the boot": ({"SWI_HOME_DIR": ("/old", "/bundled")}, {"SWI_HOME_DIR": "/bundled"}, {"SWI_HOME_DIR": "/old"}),
    "set again by the caller since": ({"SWI_HOME_DIR": (None, "/bundled")}, {"SWI_HOME_DIR": "/mine"}, {"SWI_HOME_DIR": "/mine"}),
    "removed by the boot": ({"LEGACY": ("/old", None)}, {"PATH": "/bin"}, {"PATH": "/bin", "LEGACY": "/old"}),
    "no boot in this process": ({}, {"SWI_HOME_DIR": "/user"}, {"SWI_HOME_DIR": "/user"}),
}
LAUNCH = {"run", "Popen", "check_output", "check_call", "call"}


# am[verifies a-integrate-petta-child-engine-environment-1017@8f59bb]
def _launches(path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in LAUNCH
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"):
            yield node


# What a paused boot answers in place of pymetta's engine: the boot then warms its thread with one
# speculative run, which this engine makes without doing anything, and the block attaches its thread
# with _no_attachment, since pymetta's own engine_thread would boot the real engine and set its home
# outside any boot's record, which a later test's boot would then find set already.
# am[verifies a-integrate-petta-child-engine-environment-1017@8f59bb] am[related a-rt-det-warm-thread-1019@199c44]
class _StandInEngine:
    @contextmanager
    def speculate(self):
        yield

    def run(self, source: str, **bounds) -> list:
        return []


# am[verifies a-integrate-petta-child-engine-environment-1017@8f59bb]
@contextmanager
def _no_attachment():
    yield


# A variable the boot set or changed goes back to its value before the boot, unless the base holds
# another value for it, which is the caller's; a process that never booted keeps its own.
# am[verifies a-integrate-petta-child-engine-environment-1017@8f59bb]
@pytest.mark.parametrize("case", RULE)
def test_a_child_gets_each_variable_back_as_it_was_before_the_engine_booted(case, monkeypatch):
    record, base, expected = RULE[case]
    monkeypatch.setattr(runtime_engine, "_ENGINE_ENVIRONMENT", record)

    assert runtime_engine.child_environment(base) == expected


# A boot that sets a variable and then raises leaves it set, and a retry finds it set already and
# changes nothing: the first attempt's record still puts it back for every child.
# am[verifies a-integrate-petta-child-engine-environment-1017@8f59bb]
def test_a_variable_a_failed_boot_set_is_put_back_for_children(monkeypatch):
    def failing_boot():
        os.environ["GOALCHAINER_TEST_BOOT_HOME"] = "/bundled"
        raise RuntimeError("boot failed")

    monkeypatch.setenv("GOALCHAINER_TEST_BOOT_HOME", "restored after the test")
    monkeypatch.delenv("GOALCHAINER_TEST_BOOT_HOME")
    monkeypatch.setattr(runtime_engine, "_ENGINE", None)
    monkeypatch.setattr(runtime_engine, "_ENGINE_ENVIRONMENT", {})
    monkeypatch.setattr(metta, "MeTTa", failing_boot)
    for _attempt in range(2):
        with pytest.raises(RuntimeError, match="boot failed"), runtime_engine.metta_engine(None):
            pass

    assert os.environ["GOALCHAINER_TEST_BOOT_HOME"] == "/bundled"
    assert "GOALCHAINER_TEST_BOOT_HOME" not in runtime_engine.child_environment()


# Another thread asks for a child environment while a boot has set a variable and is paused before
# recording it; the answer waits for the record instead of carrying the half-booted value. The boot
# is held by events, so the interleaving is forced; the bounded join only limits how long the test
# watches for an early answer.
# am[verifies a-integrate-petta-child-engine-environment-1017@8f59bb] am[related i-integrate-child-env-during-boot-1017@5200fa]
def test_a_child_environment_asked_for_during_a_boot_waits_for_its_record(monkeypatch):
    changed, release = threading.Event(), threading.Event()
    taken: list[dict[str, str]] = []

    def paused_boot():
        os.environ["GOALCHAINER_TEST_BOOT_HOME"] = "/bundled"
        changed.set()
        release.wait()
        return _StandInEngine()

    def boot():
        with runtime_engine.metta_engine(None):
            pass

    monkeypatch.setenv("GOALCHAINER_TEST_BOOT_HOME", "restored after the test")
    monkeypatch.delenv("GOALCHAINER_TEST_BOOT_HOME")
    monkeypatch.setattr(runtime_engine, "_ENGINE", None)
    monkeypatch.setattr(runtime_engine, "_ENGINE_ENVIRONMENT", {})
    monkeypatch.setattr(runtime_engine, "_BOOT_THREAD", None)
    monkeypatch.setattr(metta, "MeTTa", paused_boot)
    monkeypatch.setattr(metta.parallel, "engine_thread", _no_attachment)
    booting = threading.Thread(target=boot)
    booting.start()
    changed.wait()
    asking = threading.Thread(target=lambda: taken.append(runtime_engine.child_environment()))
    asking.start()
    asking.join(timeout=1.0)
    answered_during_boot = not asking.is_alive()
    release.set()
    asking.join()
    booting.join()

    assert not answered_during_boot
    assert "GOALCHAINER_TEST_BOOT_HOME" not in taken[0]


# Booting pymetta names its bundled SWI home in SWI_HOME_DIR, and a child started after the boot
# with child_environment reads the value this process had before it. Before, a child read the
# bundled home, and a system swipl 9.2.9 aborted on its boot file's VM signature.
# A fresh interpreter owns the boot: another module's collection-time metta.parse may already
# have booted pymetta outside GoalChainer's environment capture in the pytest process.
# am[verifies a-integrate-petta-child-engine-environment-1017@8f59bb] am[verifies c-rt-pymetta-boot-sets-swi-home-1017@75b69b]
# am[verifies a-v2-baseline-child-environment-1020@b2f11a]
def test_a_child_of_a_booted_engine_reads_no_bundled_home():
    environment = runtime_engine.child_environment()
    environment.pop("SWI_HOME_DIR", None)
    script = '''
import os
import subprocess
import sys
from goal_chainer.runtime.engine import child_environment, metta_engine

assert "SWI_HOME_DIR" not in os.environ
with metta_engine(None) as engine:
    engine.run("!(+ 1 1)")
    home = str(engine.runtime.once("current_prolog_flag(home, Home)")["Home"])
environment = child_environment()
printed = subprocess.run(
    [sys.executable, "-I", "-c", "import os; print(os.getenv('SWI_HOME_DIR'))"],
    env=environment, capture_output=True, text=True, check=True,
).stdout.strip()
assert os.environ["SWI_HOME_DIR"] == home
assert "SWI_HOME_DIR" not in environment
assert printed == "None"
'''
    result = subprocess.run([sys.executable, "-c", script], env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# A child that inherited the bundled home would pass it on, its own boot then setting nothing, so
# every launch names an environment rather than inheriting this process's.
# am[verifies a-integrate-petta-child-engine-environment-1017@8f59bb] am[verifies c-rt-child-env-leak-transitive-1017@bdc403]
def test_every_subprocess_launch_names_its_childs_environment():
    sources = [*PACKAGE.rglob("*.py"), PACKAGE.parent / "gcskill.py"]
    inheriting = [f"{path.relative_to(PACKAGE.parent)}:{call.lineno}" for path in sources
                  for call in _launches(path) if not any(keyword.arg == "env" for keyword in call.keywords)]

    assert [path for path in sources if any(_launches(path))] != []
    assert inheriting == []

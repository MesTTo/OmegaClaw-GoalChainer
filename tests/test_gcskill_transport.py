"""Purpose: verify gcskill's child-process transport with real child processes of the locked
interpreter: a skill's payload, its typed failure, an untyped failure, a child environment without
the host's runtime settings, a host environment that carries them, and the plugin's configured
reader settings reaching every skill process."""

from __future__ import annotations

import json
import locale
import shlex
import sys
from pathlib import Path

import pytest

import gcskill


# am[verifies a-v2-skill-transport-errors-1020@868e22]
def test_a_missing_interpreter_is_a_typed_launch_failure(tmp_path):
    with pytest.raises(gcskill.GoalChainerSkillError) as caught:
        gcskill.call(str(tmp_path / "missing-python"), "goalchainer-system-prompt")
    assert caught.value.code == "launch"
    assert caught.value.details["errno"] == 2


# A native dependency may print bytes before the JSON result exists.
# am[verifies a-v2-skill-transport-errors-1020@868e22]
@pytest.mark.parametrize("descriptor", [1, 2])
def test_invalid_child_output_encoding_is_a_typed_protocol_failure(tmp_path, descriptor):
    python = tmp_path / "python"
    program = f"import os; os.write({descriptor}, bytes([255]))"
    python.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -I -c {shlex.quote(program)}\n",
                      encoding="utf-8")
    python.chmod(0o755)
    with pytest.raises(gcskill.GoalChainerSkillError) as caught:
        gcskill.call(str(python), "goalchainer-system-prompt")
    assert caught.value.code == "protocol"
    assert "UTF-8" in caught.value.message


# The host's default codec does not determine the wire encoding.
# am[verifies a-v2-skill-utf8-1020@3763d0]
def test_request_transport_keeps_unicode_under_an_ascii_host_locale(monkeypatch):
    monkeypatch.setattr(locale, "getencoding", lambda: "ascii")
    result = gcskill.call(sys.executable, "goalchainer-system-prompt", "requête")
    assert result["skill"] == "goalchainer-system-prompt"


# A text no UTF-8 stream can carry is refused before starting a process.
# am[verifies a-v2-skill-utf8-1020@3763d0]
def test_request_transport_refuses_a_lone_surrogate_before_launch(monkeypatch):
    # am[verifies a-v2-skill-utf8-1020@3763d0]
    def unexpected(*args, **kwargs):
        pytest.fail("invalid UTF-8 request started a child")

    monkeypatch.setattr(gcskill.subprocess, "run", unexpected)
    with pytest.raises(gcskill.GoalChainerSkillError) as caught:
        gcskill.call(sys.executable, "goalchainer-request", "\ud800")
    assert caught.value.code == "invalid_input"


# am[verifies a-rt-skill-process-boundary-1016@a36729]
def test_a_skill_answers_its_payload_from_the_child():
    payload = gcskill.call(sys.executable, "goalchainer-system-prompt")

    assert payload["skill"] == "goalchainer-system-prompt"
    assert payload["prompt"]


# am[verifies a-rt-skill-process-boundary-1016@a36729]
def test_a_typed_failure_crosses_the_boundary_typed():
    with pytest.raises(gcskill.GoalChainerSkillError) as caught:
        gcskill.call(sys.executable, "goalchainer-snars-dispatch", "not json")

    assert caught.value.code == "invalid_input"
    assert caught.value.skill == "goalchainer-snars-dispatch"
    assert "valid JSON" in caught.value.message


# The interpreter uv built the environment from has no goal_chainer, so the child dies before
# the protocol starts and only its exit status and standard error can be reported.
# am[verifies a-rt-skill-process-boundary-1016@a36729]
def test_an_untyped_failure_reports_the_exit_status_and_standard_error():
    with pytest.raises(gcskill.GoalChainerSkillError) as caught:
        gcskill.call(sys.base_prefix + "/bin/python3", "goalchainer-system-prompt")

    assert caught.value.code == "exit-1"
    assert "goal_chainer" in caught.value.message


# am[verifies a-rt-skill-process-boundary-1016@a36729]
def test_the_child_environment_drops_only_the_host_runtime_settings():
    host = {"PYTHONPATH": "/host/src", "PYTHONHOME": "/host", "SWI_HOME_DIR": "/host/swi",
            "GOALCHAINER_MODEL_CACHE": "/cache", "PATH": "/usr/bin"}

    assert gcskill.child_environment(host) == {"GOALCHAINER_MODEL_CACHE": "/cache", "PATH": "/usr/bin"}


# PYTHONHOME naming no Python would stop the child's interpreter from starting at all, and the
# host's SWI_HOME_DIR would turn pymetta away, so an answer shows neither was inherited.
# am[verifies a-rt-skill-process-boundary-1016@a36729]
def test_a_host_environment_with_runtime_settings_does_not_reach_the_child(monkeypatch):
    monkeypatch.setenv("PYTHONHOME", "/nonexistent-python-home")
    monkeypatch.setenv("SWI_HOME_DIR", "/usr/lib/swi-prolog")
    monkeypatch.setenv("PYTHONPATH", "/nonexistent-host-src")

    payload = gcskill.call(sys.executable, "goalchainer-system-prompt")

    assert payload["prompt"]


# The reader settings a skill process could carry, read back by a stand-in interpreter.
SHOWN = ("GOALCHAINER_MODEL_CACHE", "GOALCHAINER_JEV_CACHE", "GOALCHAINER_JEV_OFFLINE", "TYPESAFE_BASE_URL",
         "TYPESAFE_API_KEY")


# Every test here leaves gcskill with no configured reader settings, as a host that never loaded
# the plugin has.
# am[verifies a-irp-reader-keys-1018@14bc18]
@pytest.fixture
def reader_reset():
    yield
    gcskill.configure_reader("", "", "", "")


# A stand-in for the recorded interpreter that answers, as its payload, the reader variables its
# process was started with.
# am[verifies a-irp-reader-keys-1018@14bc18]
def _shown(tmp_path: Path) -> dict:
    python = tmp_path / "python"
    probe = f"import json, os; print(json.dumps({{k: os.environ.get(k) for k in {json.dumps(SHOWN)}}}))"
    python.write_text(f"#!/bin/sh\nexec {sys.executable} -I -c '{probe}'\n", encoding="utf-8")
    python.chmod(0o755)
    return gcskill.call(str(python), "goalchainer-system-prompt")


# The configured settings reach the skill's process under the reader's own variables, a URL bringing
# the gateway's placeholder key, while a key the host holds is kept; settings configured empty leave
# every variable to the host, which has none of them here.
# am[verifies a-irp-reader-keys-1018@14bc18]
def test_configured_reader_settings_reach_every_skill_process(tmp_path, monkeypatch, reader_reset):
    for name in SHOWN:
        monkeypatch.delenv(name, raising=False)

    gcskill.configure_reader("/opt/models", "/memory/jev", "1", "http://localhost:8080/typesafe")
    gateway = _shown(tmp_path)
    monkeypatch.setenv("TYPESAFE_API_KEY", "tk-host-not-a-key")
    host_key = _shown(tmp_path)
    gcskill.configure_reader("", "", "", "")
    unset = _shown(tmp_path)

    assert gateway == {"GOALCHAINER_MODEL_CACHE": "/opt/models", "GOALCHAINER_JEV_CACHE": "/memory/jev",
                       "GOALCHAINER_JEV_OFFLINE": "1", "TYPESAFE_BASE_URL": "http://localhost:8080/typesafe",
                       "TYPESAFE_API_KEY": gcskill.GATEWAY_KEY}
    assert host_key["TYPESAFE_API_KEY"] == "tk-host-not-a-key"
    assert unset == {**dict.fromkeys(SHOWN), "TYPESAFE_API_KEY": "tk-host-not-a-key"}


# The offline switch takes Omega's configuration answers for 1 and 0, text, number or boolean.
# am[verifies a-irp-reader-keys-1018@14bc18]
@pytest.mark.parametrize("value,expected", [("1", "1"), (1, "1"), (True, "1"), ("0", "0"), (0, "0"), (False, "0")])
def test_the_offline_switch_takes_one_or_zero_in_any_form(value, expected, reader_reset):
    gcskill.configure_reader("", "", value, "")

    assert gcskill.skill_environment({})["GOALCHAINER_JEV_OFFLINE"] == expected


# A malformed setting is refused at the plugin's load, naming its key, and replaces nothing.
# am[verifies a-irp-reader-keys-1018@14bc18]
@pytest.mark.parametrize("settings,key", [
    (("relative/models", "", "", ""), "goalchainerModelCache"),
    (("", 7, "", ""), "goalchainerJevCache"),
    (("", "", "yes", ""), "goalchainerJevOffline"),
    (("", "", "", "ftp://gateway/typesafe"), "goalchainerJevUrl"),
])
def test_a_malformed_reader_setting_is_refused_by_its_key(settings, key, reader_reset):
    gcskill.configure_reader("/opt/models", "", "", "")

    with pytest.raises(ValueError, match=key):
        gcskill.configure_reader(*settings)
    assert json.dumps(gcskill.skill_environment({})) == json.dumps({"GOALCHAINER_MODEL_CACHE": "/opt/models"})

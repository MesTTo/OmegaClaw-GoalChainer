"""Purpose: drive gcskill's child-process transport from the plugin's MeTTa suite where a check
needs Python's view of it: the code of a skill's typed failure, and a request made while the host
process carries runtime settings that would stop the child if it inherited them."""

from __future__ import annotations

import os

import gcskill
import janus_swi


# am[verifies a-rt-skill-process-boundary-1016@a36729]
def failure_code(python: str, skill: str, request: str) -> str:
    """The typed code a failing skill raised through the transport, or "no-failure"."""

    try:
        gcskill.call(python, skill, request)
    except gcskill.GoalChainerSkillError as error:
        return error.code
    return "no-failure"


# SWI_HOME_DIR is set to the SWI-Prolog hosting this Python, whose bridge pymetta refuses, and
# PYTHONHOME to a directory that holds no Python, so a child that inherited either could not
# answer at all.
# am[verifies a-rt-skill-process-boundary-1016@a36729] am[verifies a-integrate-domain-surface-1018@759698]
def request_under_host_settings(python: str, request: str) -> str:
    """gcskill.request run while this process's environment carries the host's runtime settings."""

    saved = {key: os.environ.get(key) for key in ("SWI_HOME_DIR", "PYTHONHOME")}
    os.environ["SWI_HOME_DIR"] = str(janus_swi.query_once("current_prolog_flag(home, H)")["H"])
    os.environ["PYTHONHOME"] = "/nonexistent-python-home"
    try:
        return gcskill.request(python, request)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

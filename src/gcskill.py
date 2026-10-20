"""Purpose: run GoalChainer skills in the recorded interpreter and return their structured results.

The OmegaClaw plugin calls this top-level module through py-call. Requests cross the process
boundary on standard input; typed errors return as GoalChainerSkillError. The child uses its
own installed packages and engine configuration, independent of the host interpreter, and the reader
settings the plugin configured, which it hands over once when it loads.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from typing import Any

# What the host process sets for its own runtimes and a child must not inherit: SWI_HOME_DIR
# names the host's SWI-Prolog, which makes pymetta refuse its bundled one, and PYTHONPATH or
# PYTHONHOME would put the host's packages ahead of the recorded environment's. The child also
# runs isolated (-I), so neither these nor the host's working directory reach its import path.
# am[implements a-rt-skill-process-boundary-1016@a36729] am[rests-on c-rt-pymetta-not-inside-swi-1016@304c96]
HOST_VARIABLES = frozenset({"PYTHONPATH", "PYTHONHOME", "SWI_HOME_DIR"})

# The plugin's reader settings, Omega configuration keys its loadOmegaPlugin binds with configure
# (goalchainerModelCache, goalchainerJevCache, goalchainerJevOffline, goalchainerJevUrl), each
# with the variable GoalChainer's reader takes it from in a skill's process. Omega's entrypoint starts
# the agent with an allowlisted environment that drops all four, so configuration is the one way a
# deployment's paths reach the reader; an empty setting leaves its variable to the agent's environment.
# am[implements a-irp-reader-keys-1018@14bc18] am[rests-on c-irp-scrub-drops-reader-settings-1018@78c748]
# am[rests-on c-irp-contract-1018@3ed0b0]
READER_VARIABLES = (
    ("goalchainerModelCache", "GOALCHAINER_MODEL_CACHE"),
    ("goalchainerJevCache", "GOALCHAINER_JEV_CACHE"),
    ("goalchainerJevOffline", "GOALCHAINER_JEV_OFFLINE"),
    ("goalchainerJevUrl", "TYPESAFE_BASE_URL"),
)
# The key a skill presents when its Jev requests go to a gateway that sets the real one, as Omega's
# nginx does for every service it fronts, so the key never enters the agent: typesafe-sdk sends its
# key as an Authorization bearer, which the gateway replaces, and refuses an empty one.
# am[implements a-irp-reader-keys-1018@14bc18] am[rests-on c-irp-sdk-gateway-compatible-1018@2b8203]
GATEWAY_KEY = "omega-gateway"
_reader: dict[str, str] = {}


# am[implements a-rt-skill-process-boundary-1016@a36729]
class GoalChainerSkillError(RuntimeError):
    """A skill failed in GoalChainer's process. `code`, `message` and `details` are the skill's
    own typed error when it reported one, otherwise its exit status and the end of its standard
    error."""

    def __init__(self, skill: str, code: str, message: str, details: Mapping[str, Any]) -> None:
        super().__init__(f"{skill} failed ({code}): {message}")
        self.skill = skill
        self.code = code
        self.message = message
        self.details = dict(details)


# am[implements a-rt-skill-process-boundary-1016@a36729]
def child_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """The environment a skill's process starts with: the host's, without its runtime settings."""

    return {key: value for key, value in environ.items() if key not in HOST_VARIABLES}


# The settings arrive as Omega's configuration answers them: text from a key=value argument or the
# installed default, a number or boolean from config/config.yaml or a bare argument. A cache is an
# absolute path, the offline switch 1 or 0, the URL an http(s) one; anything else is refused here, at
# the plugin's load, rather than met later as a reader error.
# am[implements a-irp-reader-keys-1018@14bc18]
def reader_setting(key: str, value: Any) -> str:
    if key == "goalchainerJevOffline":
        if value in (True, 1, "1"):
            return "1"
        if value in (False, 0, "0"):
            return "0"
        if value == "":
            return ""
        raise ValueError(f"{key} must be 1 or 0, not {value!r}")
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text, not {value!r}")
    if value and key == "goalchainerJevUrl" and not value.startswith(("http://", "https://")):
        raise ValueError(f"{key} must be an http or https URL, not {value!r}")
    if value and key != "goalchainerJevUrl" and not value.startswith("/"):
        raise ValueError(f"{key} must be an absolute path, not {value!r}")
    return value


# am[implements a-irp-reader-keys-1018@14bc18] am[rests-on c-irp-plugin-configure-supported-1018@289b90]
def configure_reader(model_cache: Any, jev_cache: Any, jev_offline: Any, jev_url: Any) -> None:
    """Keep the plugin's configured reader settings for every skill process this host starts, in
    READER_VARIABLES' order; each call replaces the last. Raises ValueError naming a setting that is
    not a well-formed value."""

    values = (model_cache, jev_cache, jev_offline, jev_url)
    settings = {variable: reader_setting(key, value) for (key, variable), value in zip(READER_VARIABLES, values)}
    _reader.clear()
    _reader.update({variable: value for variable, value in settings.items() if value})


# am[implements a-irp-reader-keys-1018@14bc18]
def skill_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """A skill process's environment: the host's without its runtime settings, then the configured
    reader settings, and the gateway's placeholder key when Jev goes through a URL and the host holds
    no key of its own."""

    environment = {**child_environment(environ), **_reader}
    if "TYPESAFE_BASE_URL" in _reader:
        environment.setdefault("TYPESAFE_API_KEY", GATEWAY_KEY)
    return environment


# Time: one start of the recorded interpreter plus the skill's own work.
# am[implements a-rt-skill-process-boundary-1016@a36729] am[implements a-irp-reader-keys-1018@14bc18]
# am[implements a-v2-skill-utf8-1020@3763d0]
# am[implements a-v2-skill-transport-errors-1020@868e22]
def call(python: str, skill: str, request: str = "") -> dict[str, Any]:
    """Run one skill in GoalChainer's process and answer its payload.

    Raises GoalChainerSkillError when the process cannot start, exits nonzero, or prints no
    UTF-8 JSON payload, carrying the skill's typed error when it printed one.
    """

    try:
        request.encode("utf-8")
    except UnicodeEncodeError as error:
        raise GoalChainerSkillError(skill, "invalid_input", "Skill request must be UTF-8 text.",
                                   {"start": error.start, "end": error.end}) from error
    try:
        completed = subprocess.run(
            [python, "-I", "-m", "goal_chainer.omegaclaw_skill", skill, "--request-file", "-"],
            input=request,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            env=skill_environment(os.environ),
        )
    except OSError as error:
        raise GoalChainerSkillError(skill, "launch", str(error), {"errno": error.errno}) from error
    except UnicodeDecodeError as error:
        raise GoalChainerSkillError(skill, "protocol", "The skill output is not UTF-8 text.",
                                   {"start": error.start, "end": error.end}) from error
    reported = _json_object(completed.stdout)
    if completed.returncode != 0:
        error = reported.get("error") if reported else None
        if isinstance(error, dict) and {"code", "message"} <= error.keys():
            raise GoalChainerSkillError(
                skill, str(error["code"]), str(error["message"]), error.get("details") or {}
            )
        raise GoalChainerSkillError(
            skill,
            f"exit-{completed.returncode}",
            "\n".join(completed.stderr.strip().splitlines()[-5:]),
            {"returncode": completed.returncode},
        )
    if reported is None:
        raise GoalChainerSkillError(
            skill, "protocol", "the skill printed no JSON payload", {"stdout": completed.stdout[-500:]}
        )
    return reported


# goalchainer-skill prints its answer as one JSON line, last; a line a dependency printed before
# it is not part of the protocol.
# am[implements a-rt-skill-process-boundary-1016@a36729]
def _json_object(text: str) -> dict[str, Any] | None:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


# am[implements a-integrate-domain-surface-1018@759698]
def system_prompt(python: str) -> str:
    return call(python, "goalchainer-system-prompt")["prompt"]


# Keep every returned distinction, including Inquiry, Stale and Ambiguous, in the host's result.
# am[implements a-integrate-domain-surface-1018@759698]
def request(python: str, request: str) -> str:
    return json.dumps(call(python, "goalchainer-request", request), sort_keys=True)


# am[implements a-integrate-domain-surface-1018@759698]
def directive_dispatch(python: str, request: str) -> str:
    return json.dumps(call(python, "goalchainer-directive-dispatch", request), sort_keys=True)


# am[implements a-v2-cli-skill-surface-1020@6f755c]
def motivation_dispatch(python: str, request: str) -> str:
    return json.dumps(call(python, "goalchainer-motivation-dispatch", request), sort_keys=True)


# am[implements a-integrate-domain-surface-1018@759698]
def dispatch(python: str, request: str) -> str:
    return json.dumps(call(python, "goalchainer-snars-dispatch", request), sort_keys=True)

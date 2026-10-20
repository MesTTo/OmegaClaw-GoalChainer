"""Purpose: give the plugin's MeTTa suite Omega's own Python modules under their own names, and the
parameters of the tools Omega's loop builds from the skill registry."""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Iterable
from typing import Any


# Omega's Python modules import one another by name (providers.py runs `import config`), and its
# PeTTa runtime imports each under that name; pymetta's import! of a .py file gives it a private name
# instead, so a later `import config` would load a second, unconfigured copy. The file's directory
# goes after the installed packages, as PeTTa put it.
# am[implements a-oc-plugin-suite-main-1018@7aee50] am[rests-on c-rt-oc-py-module-identity-1018@5e410a]
def by_name(path: str) -> bool:
    """Import the Python file at `path`, relative to the working directory, as the module its stem
    names. Answers True; an import error propagates."""

    path = os.path.abspath(str(path))
    directory = os.path.dirname(path)
    if directory not in sys.path:
        sys.path.append(directory)
    importlib.import_module(os.path.splitext(os.path.basename(path))[0])
    return True


# am[implements a-oc-plugin-suite-main-1018@7aee50] am[rests-on c-oc-tool-call-interface-1018@ac35f0]
def tool_parameters(tools: Iterable[Any], name: str) -> str:
    """The space-separated parameter names of the tool called `name`, as providers.getTools built it
    for the LLM, or "absent" when the registry offers no such tool."""

    for tool in tools:
        if str(tool.name) == str(name):
            return " ".join(str(parameter.name) for parameter in tool.parameters)
    return "absent"

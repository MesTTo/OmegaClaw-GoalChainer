"""Purpose: make every test read text from the committed Jev replay cache and never ask the hosted
service, whatever the environment the run started in holds: GOALCHAINER_JEV_CACHE defaults to
tests/data/jev, and every run reads offline with no TypeSafe key except the asking run of
python -m goal_chainer.semantic_capture, which loads that module as a pytest plugin with its cap on
live requests and sets the switch and the key itself."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# The capture points the cache at its own directory, so the committed one is only the default.
# am[implements a-jev-tests-1016]
os.environ.setdefault("GOALCHAINER_JEV_CACHE", str(Path(__file__).resolve().parent / "data" / "jev"))


# The reader asks Jev unless GOALCHAINER_JEV_OFFLINE is exactly 1, with whatever key reaches it, so a
# run sets both rather than defaulting them: an inherited empty or 0 switch and a key the shell holds
# would otherwise send a replay-cache miss to the hosted service. The capture's asking run is the one
# exempt, known by the capture module registered as a plugin and the cap it enforces from its own
# pytest_configure; a cap alone bounds nothing, so it exempts nothing.
# am[implements a-dr-suite-offline-unless-capture-1018@f388c2] am[implements a-tbr-jev-exempt-needs-capture-plugin-1018@303e5c]
# am[rests-on c-dr-capture-runs-suite-online-1018@7770c7] am[rests-on c-tbr-cap-alone-uncapped-1018@87c7cd]
def pytest_configure(config: pytest.Config) -> None:
    capture = config.pluginmanager.get_plugin("goal_chainer.semantic_capture")
    if capture is not None and os.environ.get(capture.MAX_REQUESTS_ENV):
        return
    os.environ["GOALCHAINER_JEV_OFFLINE"] = "1"
    os.environ.pop("TYPESAFE_API_KEY", None)

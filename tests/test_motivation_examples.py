"""Purpose: check both supplied motivation domains through their public host cycle: an observation
changes the proposal, an observed outcome leads to hold, review writes no events, and removing the
needs leaves the original band appraisal repeating. A forbidden large reducer remains forbidden."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest
from request_support import LIMITS, budget

from goal_chainer.domains.forms import parsed_forms
from goal_chainer.motivation import MotivationStore, run_motivation_request
from goal_chainer.request_text import account
from goal_chainer.requests import run_request

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "motivation"


# The driver generates the same request dictionaries a host sends. Its synthetic observations are
# the inputs; the MeTTa rules derive every decision and the store supplies the only learned sample.
# am[verifies a-v2-examples-1019@2d047f]
@pytest.mark.parametrize("name", ["companion", "research"])
def test_the_observed_cycle_holds_after_success_and_the_needless_control_repeats(name, tmp_path) -> None:
    example = runpy.run_path(str(EXAMPLES / "cycle.py"))
    scenario = example["SCENARIOS"][name]
    answers = example["run_cycle"](name, tmp_path, **LIMITS)
    unknown, _, before, _, _, status, after, repeated = answers
    assert unknown["review"]["disposition"] == "escalate"
    assert before["review"]["disposition"] == "propose"
    assert before["review"]["proposal"]["action"] == scenario["action"]
    assert after["review"]["disposition"] == repeated["review"]["disposition"] == "hold"
    assert after["review"]["hold"] == {"satisfied": [scenario["need"]], "unserved": []}
    change = next(item for item in status["snapshot"]["changes"]
                  if item["need"] == scenario["need"] and item["action"] == scenario["action"])
    assert change["state"] == "measured" and change["count"] == 1
    assert change["change"] == pytest.approx(scenario["after"] - scenario["before"])
    for answer in (unknown, before, after, repeated):
        assert answer["authorization"] == "unresolved" and answer["applies_effects"] is False
        text, code = account(answer)
        assert code == 0 and answer["review"]["disposition"] in text
        json.dumps(answer, allow_nan=False)
    with MotivationStore(tmp_path / f"{name}.sqlite3", stream=name, create=False) as store:
        history = store.history()
    assert len(history.observations) == 2 and len(history.attempts) == 1

    # These declarations are removed from the caller's domain, with every ordinary band
    # and norm left intact. There is no second hand-maintained control policy.
    plain = tmp_path / "without-needs.metta"
    forms = parsed_forms((EXAMPLES / f"{name}.metta").read_text(encoding="utf-8"), budget=budget())
    plain.write_text("\n".join(str(atom) for _, atom in forms
                               if str(atom.children[0]) not in {"gc-need", "gc-need-expectation"}) + "\n",
                     encoding="utf-8")
    for stage in ("03-before", "07-after"):
        request = json.loads((tmp_path / f"{stage}.request.json").read_text())
        request.pop("motivation")
        request["domain"] = {"path": str(plain)}
        control = run_request(request, budget=budget())
        assert control["review"]["disposition"] == "propose"
        assert control["review"]["proposal"]["action"] == scenario["action"]

    if name == "research":
        assert "read_private" in {item["action"] for item in before["review"]["steps"][0]["eliminated"]}

    # The exact saved observe request can be resent through the public request API without adding
    # evidence; idempotency is checked against the actual stream, not a count cached by the driver.
    resend = run_motivation_request(json.loads((tmp_path / "02-observe.request.json").read_text()), budget=budget())
    assert resend["recorded"] == [] and len(resend["already_recorded"]) == 1
    with MotivationStore(tmp_path / f"{name}.sqlite3", stream=name, create=False) as store:
        assert store.history() == history

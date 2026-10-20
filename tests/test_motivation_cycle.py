"""Purpose: verify the motivational cycle end to end through the public request surface: a host
observes a need, reviews, applies the proposal itself and records the attempt and its observed
outcome, and the next review decides differently because of that outcome; the same turns without the
needs section decide the same way each time; a need brought into its band holds instead of asking
for more; and no review applies an action or records one."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from goal_chainer.motivation import run_motivation_request
from goal_chainer.requests import run_request
from goal_chainer.runtime.budget import RunBudget
from motivation_support import CORE, at

STREAM = "student-1"
# calm is the student's agitation, comfortable inside [0.4, 0.6]; the designer expects guided
# breathing to settle it by 0.4 and empathy by 0.1.
NEEDS = """
(gc-need calm competence (scale 0 1) (band 0.4 0.6) (drive 1) (need-source human:designer))
(gc-need-expectation guide_breath calm -0.4 human-asserted (expectation-source human:designer))
(gc-need-expectation empathize calm -0.1 human-asserted (expectation-source human:designer))
(gc-need-expectation stay_silent calm 0.0 human-asserted (expectation-source human:designer))
"""


# am[verifies a-v2-end-to-end-1019@e8153c]
def _budget() -> RunBudget:
    return RunBudget(inference_budget=1_000_000_000, timeout_seconds=300)


# The domain files and the stream a host names; nothing is recorded until the host records it.
# am[verifies a-v2-end-to-end-1019@e8153c]
@pytest.fixture
def host(tmp_path: Path) -> SimpleNamespace:
    regulated, plain = tmp_path / "companion.metta", tmp_path / "companion-plain.metta"
    regulated.write_text(CORE + NEEDS, encoding="utf-8")
    plain.write_text(CORE, encoding="utf-8")
    return SimpleNamespace(regulated={"path": str(regulated)}, plain={"path": str(plain)},
                           motivation={"store": str(tmp_path / "motivation.sqlite3"), "stream": STREAM})


# am[verifies a-v2-end-to-end-1019@e8153c]
def _record(host: SimpleNamespace, operation: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return run_motivation_request({"operation": operation, "domain": host.regulated, "motivation": host.motivation,
                                   operation_field(operation): records}, budget=_budget())


# am[verifies a-v2-end-to-end-1019@e8153c]
def operation_field(operation: str) -> str:
    return "observations" if operation == "observe" else "attempts"


# am[verifies a-v2-end-to-end-1019@e8153c]
def _observe(host: SimpleNamespace, level: float, seconds: float, produced_by: str | None = None) -> None:
    _record(host, "observe", [{"need": "calm", "level": level, "scale": [0, 1], "estimator": "measured",
                               "source": "host:check-in", "observed_at": at(seconds).isoformat(),
                               "produced_by": produced_by}])


# One turn's review at `seconds`, of the regulated domain by the stream, or of the plain domain.
# am[verifies a-v2-end-to-end-1019@e8153c]
def _review(host: SimpleNamespace, seconds: float, *, needs: bool = True) -> dict[str, Any]:
    context = {"review_id": f"turn-{seconds:g}", "subject": STREAM, "trigger": "turn", "as_of": at(seconds).isoformat(),
               "authority": "advisory",
               "readings": [{"signal": "session_open", "state": "detected", "source": "host:session",
                             "estimator": "deterministic", "observed_at": at(seconds).isoformat()}]}
    request = {"operation": "review", "domain": host.regulated if needs else host.plain, "context": context}
    return run_request({**request, "motivation": host.motivation} if needs else request, budget=_budget())


# The stream's snapshot at `seconds`, of its first `through` events when that is given.
# am[verifies a-v2r-history-prefix-1020]
def _status(host: SimpleNamespace, seconds: float, through: int | None = None) -> dict[str, Any]:
    request = {"operation": "status", "domain": host.regulated, "motivation": host.motivation, "as_of": at(seconds).isoformat()}
    return run_motivation_request(request if through is None else {**request, "through": through}, budget=_budget())["snapshot"]


# am[verifies a-v2-end-to-end-1019@e8153c]
def _proposed(result: dict[str, Any]) -> str | None:
    proposal = result["review"]["proposal"]
    return None if proposal is None else proposal["action"]


# Turn 1 proposes guided breathing by its declared change; the host applies it and observes the
# student more agitated, 0.9 to 0.95, so turn 2 has learned +0.05 for it and proposes empathy;
# empathy brings calm to 0.55, inside the band, and turn 3 holds. The host's own statements are the
# only writes: no review records an attempt or applies an action.
# am[verifies a-v2-end-to-end-1019@e8153c] am[verifies a-v2m-expectations-1019@b13468] am[verifies a-v2m-hold-1019@be4f47]
# am[verifies c-gc-v2-authority-boundary-1019@5d2caf]
def test_an_observed_outcome_changes_the_next_decision_and_a_satisfied_need_holds(host) -> None:
    _observe(host, 0.9, 10)
    first = _review(host, 15)
    assert _proposed(first) == "guide_breath"
    assert (first["authorization"], first["applies_effects"]) == ("unresolved", False)
    assert first["review"]["motivation"]["history"]["event_count"] == 1
    assert "samples" not in first["review"]["motivation"]
    assert all(change["count"] == 0 for change in first["review"]["motivation"]["changes"])

    _record(host, "attempt", [{"attempt": "a1", "action": "guide_breath", "applied_at": at(20).isoformat(),
                               "review_fingerprint": first["review"]["fingerprint"]}])
    _observe(host, 0.95, 30, produced_by="a1")
    second = _review(host, 40)
    learned = next(item for item in second["review"]["motivation"]["changes"]
                   if (item["action"], item["need"]) == ("guide_breath", "calm"))
    assert (learned["state"], learned["count"]) == ("measured", 1)
    assert learned["change"] == pytest.approx(0.05)
    assert _proposed(second) == "empathize"

    _record(host, "attempt", [{"attempt": "a2", "action": "empathize", "applied_at": at(50).isoformat()}])
    _observe(host, 0.55, 60, produced_by="a2")
    third = _review(host, 70)
    assert third["review"]["disposition"] == "hold" and third["review"]["proposal"] is None
    assert third["review"]["hold"] == {"satisfied": ["calm"], "unserved": []}


# Without the needs section the same turns review the same way every time: the outcome the host
# observed has nothing to change, which is what the motivational step adds.
# am[verifies a-v2-end-to-end-1019@e8153c]
def test_without_needs_the_same_turns_decide_alike(host) -> None:
    decisions = {(result["review"]["disposition"], _proposed(result))
                 for result in (_review(host, seconds, needs=False) for seconds in (15, 40, 70))}
    assert len(decisions) == 1
    assert decisions != {("propose", "guide_breath")}


# A review records the prefix of the stream it read, and a status read through that prefix answers
# the review's own snapshot, every sample and every level's observations included, after an
# observation backdated into the attempt's window has been appended; a review of the stream as it
# now stands reads the appended outcome and decides from the new sample, so the audit takes nothing
# from the latest-state read.
# am[verifies a-v2r-record-digest-1020] am[verifies a-v2r-history-prefix-1020] am[verifies c-v2r-store-prefix-immutable-1020]
# am[verifies a-v2r-level-support-digest-1020]
def test_a_status_read_through_a_reviews_prefix_recovers_it_after_a_backdated_append(host) -> None:
    _observe(host, 0.9, 10)
    _record(host, "attempt", [{"attempt": "a1", "action": "guide_breath", "applied_at": at(20).isoformat()}])
    _observe(host, 0.95, 30, produced_by="a1")
    reviewed = _review(host, 40)["review"]
    history = reviewed["motivation"]["history"]
    assert history["event_count"] == 3 and "samples" not in reviewed["motivation"]
    replayed_before = _status(host, 40, through=3)

    _observe(host, 0.5, 35, produced_by="a1")
    replay, latest = _status(host, 40, through=3), _status(host, 40)
    assert replay == replayed_before and replay["history"] == history
    assert latest["history"]["event_count"] == 4 and latest["history"]["digest"] != history["digest"]
    shown = {"action", "need", "state", "change", "estimator", "count", "samples_digest"}
    assert [{key: change[key] for key in shown} for change in replay["changes"]] == reviewed["motivation"]["changes"]
    assert [{key: value for key, value in level.items() if key != "support"} for level in replay["levels"]] \
        == reviewed["motivation"]["levels"]
    assert replay["reductions"] == reviewed["motivation"]["reductions"]
    assert [len(level["support"]) for level in replay["levels"] if level["need"] == "calm"] == [1]
    (sample,) = replay["samples"]
    assert sample["attempt"] == "a1" and sample["change"] == pytest.approx(0.05)
    assert [item["change"] for item in latest["samples"]] == [pytest.approx(-0.4)]
    assert _review(host, 40)["review"]["fingerprint"] != reviewed["fingerprint"]
    empty = _status(host, 40, through=0)
    assert empty["history"]["event_count"] == 0 and {level["state"] for level in empty["levels"]} == {"unobserved"}

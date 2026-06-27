"""The decision feeds OmegaClaw lib_directive, classified by injected Prolog."""

from goal_chainer.directive import classify_task_states, register_directive


INCIDENT = {
    "publish_raw_log": "forbidden",
    "publish_redacted_summary": "obligated",
    "hold_external_update": "permitted",
}


def test_injected_prolog_relation_maps_deontic_to_task_state():
    states, _ = classify_task_states(INCIDENT)

    # gc_task_state/2 is a Prolog relation asserted from MeTTa and called back as a
    # MeTTa function: forbidden -> blocked, obligated -> ready, permitted -> backlog.
    assert states["publish_raw_log"] == "blocked"
    assert states["publish_redacted_summary"] == "ready"
    assert states["hold_external_update"] == "backlog"


def test_recommended_action_becomes_a_claimed_task():
    report = register_directive(INCIDENT)

    assert report["status"]["ready"] == ["publish_redacted_summary"]
    assert report["status"]["blocked"] == ["publish_raw_log"]
    assert any(nxt["task"] == "publish_redacted_summary" for nxt in report["next_actions"])
    assert report["claim"]["task"] == "publish_redacted_summary"
    assert report["claim"]["version"] == 1

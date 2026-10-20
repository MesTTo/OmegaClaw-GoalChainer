"""Purpose: give directive tests plans a caller writes for lib_directive, whose agent is the caller's own, and read a snapshot's task states."""

from __future__ import annotations

from goal_chainer.directive_models import DirectiveSnapshot

# The agent these plans declare available. It is the caller's choice, so no operation may assume it.
# am[verifies a-integrate-directive-explicit-agent-1018@54e84d]
AGENT = "triager"


# am[verifies a-ie-s6-directive-generic-1018@e69fb4]
def _meta(plan_id: str, title: str) -> str:
    return (f'(meta plan (id "{plan_id}") (title "{title}") (version "1.0.0") (status "active")'
            ' (created "2026-10-18") (author "agent:test"))\n')


# A review task gating the actions after it: the review is ready with no dependency, the redacted
# summary becomes ready once the review completes, the raw log is forbidden and so blocked, and
# holding is only a task.
# am[verifies a-ie-s6-directive-generic-1018@e69fb4]
GATED_PLAN = _meta("TEST-GATED", "A review gating its actions") + f"""\
(given agent-{AGENT}-available)
(given task-review_decision)
(given no-deps-review_decision)
(normally r-review_decision (and task-review_decision no-deps-review_decision) ready-review_decision)
(normally assign-review_decision (and ready-review_decision agent-{AGENT}-available) assign-to-review_decision-{AGENT})
(given task-publish_raw_log)
(given task-publish_redacted_summary)
(given task-hold_external_update)
(given forbid-publish_raw_log)
(normally blk-publish_raw_log forbid-publish_raw_log blocked-publish_raw_log)
(normally r-publish_redacted_summary (and task-publish_redacted_summary completed-review_decision) ready-publish_redacted_summary)
(normally assign-publish_redacted_summary (and ready-publish_redacted_summary agent-{AGENT}-available) assign-to-publish_redacted_summary-{AGENT})
"""

# The same plan with its review completed, so the redacted summary is ready.
# am[verifies a-ie-s6-directive-generic-1018@e69fb4]
READY_PLAN = GATED_PLAN + "(given completed-review_decision)\n"

# Three tasks in a chain, each ready once the one before it completes, the first with no dependency.
# am[verifies a-ie-s6-directive-generic-1018@e69fb4]
CHAIN = ("collect_evidence", "summarize_findings", "publish_update")
CHAIN_PLAN = _meta("TEST-CHAIN", "A dependency chain") + "".join(
    [f"(given agent-{AGENT}-available)\n"]
    + [f"(given task-{task})\n" for task in CHAIN]
    + [f"(given no-deps-{CHAIN[0]})\n"]
    + [f"(normally r-{task} (and task-{task} {condition}) ready-{task})\n"
       for task, condition in zip(CHAIN, (f"no-deps-{CHAIN[0]}", *(f"completed-{task}" for task in CHAIN[:-1])))]
    + [f"(normally assign-{task} (and ready-{task} agent-{AGENT}-available) assign-to-{task}-{AGENT})\n"
       for task in CHAIN]
)


# Each task's state as the snapshot's status lists give it, backlog when none names it.
# am[verifies a-ie-s6-directive-generic-1018@e69fb4]
def task_states(snapshot: DirectiveSnapshot) -> dict[str, str]:
    states = {task: "backlog" for task in snapshot.status.tasks}
    for state, tasks in (
        ("ready", snapshot.status.ready),
        ("in-progress", snapshot.status.claimed),
        ("upstream-blocked", snapshot.status.upstream_blocked),
        ("blocked", snapshot.status.blocked),
        ("done", snapshot.status.completed),
    ):
        for task in tasks:
            states[task] = state
    return states

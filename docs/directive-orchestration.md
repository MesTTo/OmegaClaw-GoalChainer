# Directive orchestration

<!-- am[implements a-ie-s6-directive-generic-1018@e69fb4] -->
GoalChainer runs a caller's durable plan through lib_directive, the directive
system it carries in its own package. The operator's MesTTo/MeTTa engine
evaluates the plan's rules in-process through pymetta; Python manages the plan
file and the typed request boundary. The adapter,
`src/goal_chainer/goalchainer_directive.metta`, packages lib_directive's answers
as versioned `goalchainer-directive-v1` records.

The caller writes the plan. GoalChainer writes no plan, chooses no task and names
no agent: each read answers what the plan says now, and each lifecycle change is
made by the task and agent the request names. A completed task says that step of
the plan was done. It authorizes nothing and confirms no effect: authorization is
the host's, and only a host receipt confirms an effect (see
[relevance review](relevance-review.md)).

## A plan

A plan is a lib_directive theory, one form a line. Names are composed from
prefixes: `task-T` declares a task, `no-deps-T` frees it, `ready-T` and
`completed-T` are its states, `assign-to-T-A` assigns it to agent `A`, and
`agent-A-available` says the agent can take work. This plan chains three tasks,
each ready once the one before it completes, all assigned to the agent `triager`:

```metta
(meta plan (id "CHAIN") (title "A dependency chain") (version "1.0.0") (status "active") (created "2026-10-18") (author "agent:operator"))
(given agent-triager-available)
(given task-collect_evidence)
(given task-summarize_findings)
(given task-publish_update)
(given no-deps-collect_evidence)
(normally r-collect_evidence (and task-collect_evidence no-deps-collect_evidence) ready-collect_evidence)
(normally r-summarize_findings (and task-summarize_findings completed-collect_evidence) ready-summarize_findings)
(normally r-publish_update (and task-publish_update completed-summarize_findings) ready-publish_update)
(normally assign-collect_evidence (and ready-collect_evidence agent-triager-available) assign-to-collect_evidence-triager)
(normally assign-summarize_findings (and ready-summarize_findings agent-triager-available) assign-to-summarize_findings-triager)
(normally assign-publish_update (and ready-publish_update agent-triager-available) assign-to-publish_update-triager)
```

A forbidden task is blocked by `(given forbid-T)` with
`(normally blk-T forbid-T blocked-T)`. Blocking a task blocks every task that
depends on it as `upstream-blocked`, and unblocking it clears the cascade.

`goal_chainer.directive.create_plan(path, text)` writes a new plan with mode
`0600` and refuses to replace a file already there. A session refuses a symbolic
link, holds a lock on the plan for each operation, and refuses a plan whose path
was replaced while it was open.

## Requests

<!-- am[implements a-integrate-request-budget-surface-1018@d6882c] -->
<!-- am[implements a-integrate-directive-explicit-agent-1018@54e84d] -->
A request is one JSON object naming an `operation` and the absolute `plan` path.
The command line reads it from a file or standard input, and requires an
inference budget and a finite timeout for the whole request:

```bash
echo '{"operation":"board","plan":"/absolute/path/chain.metta"}' \
  | goalchainer directive --inference-budget 1000000000 --timeout-seconds 600
echo '{"operation":"claim","plan":"/absolute/path/chain.metta","task":"collect_evidence","agent":"triager"}' \
  | goalchainer directive --inference-budget 1000000000 --timeout-seconds 600
```

| Operation | Fields besides `operation` and `plan` | Answers |
| --- | --- | --- |
| `snapshot` | | Every view below at once |
| `status`, `next`, `board`, `summary`, `info`, `assignments` | | One view of the snapshot |
| `task-state` | `task` | One task's state |
| `validate` | `strict` (optional boolean) | lib_directive's validation |
| `analyze`, `trace` | | Cycle analysis and the rule trace |
| `markdown` | | The audit document: board, assignments and summary tables, then the plan and its lifecycle log |
| `claim` | `task`, `agent`, `force` (optional boolean) | The lifecycle result and the new snapshot |
| `unclaim`, `complete`, `block`, `unblock` | `task`, `agent` | The lifecycle result and the new snapshot |

Every lifecycle change names the agent making it, since a caller's plan declares
its own agents. A lifecycle request without `agent` is refused before the plan is
opened, with details `{"operation": ..., "missing": ["agent"]}`. Task and agent
must be MeTTa symbols with no whitespace, parenthesis, semicolon, quote or
backslash. An unknown operation or field is refused before any engine work, with
the list of operations it accepts. Every answer carries the plan's digest before
and after the operation; a read leaves them equal.

On the chain above, blocking `collect_evidence` leaves the other two
`upstream-blocked`; unblocking it returns them to `backlog`; claiming and
completing each task makes the next one `ready`; and when all three are `done` the
summary reports 100 percent progress.

## OmegaClaw dispatch

The skill takes the same request with its limits as JSON fields:

```metta
(goalchainer-directive-dispatch
  "{\"operation\":\"board\",\"plan\":\"/absolute/path/chain.metta\",\"inference_budget\":1000000000,\"timeout_seconds\":600}")
(goalchainer-directive-dispatch
  "{\"operation\":\"claim\",\"plan\":\"/absolute/path/chain.metta\",\"task\":\"collect_evidence\",\"agent\":\"triager\",\"inference_budget\":1000000000,\"timeout_seconds\":600}")
```

## Migration

| Earlier | Now |
| --- | --- |
| The `demo` operation, which ran a fixed three-task plan through a fixed block, unblock, claim and complete sequence | Removed. Write the plan and send each operation; the chain above is the same plan. |
| `DirectiveRuntime.plan(...)`, `classify(...)`, `classify_task_states(...)` and `register_directive(...)`, which wrote an incident plan from each incident action's deontic status | Removed. A plan is the caller's; a deontic review's statuses do not become tasks. |
| `execute_with_directive(...)`, whose accepted claim was reported as GoalChainer's authorization | Removed. A claim is a plan step, never an authorization; the host authorizes and records its own attempt. |
| `agent` defaulting to `responder` | Required on `claim`, `unclaim`, `complete`, `block` and `unblock`, and on the `DirectiveSession` methods of the same names. |
| Positional operations on the command line (`goalchainer directive board --plan ...`) | One JSON request on standard input or `--input FILE`. |

## Runtime

`lib_directive` ships in GoalChainer's own package, in
`src/goal_chainer/deontic_library/`, taken from omegaclaw-deontic at `e5953fd`; that
directory's `PROVENANCE.md` lists what was taken. A directive program registers
the directory as the library path `deontic`, so a directive needs no OmegaClaw-Core
checkout or plugin. Directive programs run on the pinned pymetta package and its
bundled engine. `markdown` renders through the Markdown library GoalChainer
carries.

<!-- am[related a-ev-rb-directive-inprocess-1018@7bd2f6] -->
`DirectiveRuntime.bounded(budget)` binds the caller's existing `RunBudget`.
Every operation uses `run_bounded`; a runtime without a bound budget refuses to
execute. Reads run inside speculation, so they leave nothing in the engine.
Lifecycle changes run outside it so their append to the plan file persists, and
each reloads the plan before it reasons, so nothing one change leaves in the
engine decides a later one.

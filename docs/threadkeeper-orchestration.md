# MeTTa Markdown thread orchestration

GoalChainer can execute a task graph declared in a Markdown document. The
semantic content stays in fenced MeTTa facts. Mettabase parses those fences,
MeTTaScript validates and rewrites the graph into policy conclusions, and
OmegaClaw owns the durable task lifecycle.

Run the checked demonstration:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli thread demo --json
```

The command exits nonzero if any asserted capability fails.

## What changed

| Earlier directive bridge | Current thread orchestration |
| --- | --- |
| Incident tasks were constructed by one fixed Python path | A Markdown document declares arbitrary validated task graphs |
| Python constructed directive task and dependency clauses | MeTTa compiles task symbols, dependency conjunctions, assignments, and metadata |
| A caller manually claimed and completed tasks | MeTTaScript derives routing and outcomes while a retained grounded attempt runs worker, evaluator, and optional adjudicator effects |
| No delegation budget policy | ThreadKeeper's local-iteration, soft-threshold, hard-task, and ceiling rules route or deny work |
| No supervised worker process | Lease renewal, idle timeout, wall timeout, output bounds, PTY mode, and safe termination are enforced |
| Completion could follow the executor result directly | A separate evaluator must accept the observation before completion |
| No attempt recovery policy | Rejections retry up to the specification limit, then block the task and its dependents |
| No thread audit | Every route, claim, attempt, evaluation, lifecycle event, and integration is hash chained |
| No isolated accepted-work integration | A task can run in a detached git worktree and update only a named integration branch |
| Research tools depended on each harness's ambient setup | MeTTa selects the typed `oh-my-goals` MCP profile for every dispatched task |
| Directive Markdown covered the board | MeTTa builds a Mettabase authoring tree for board, budget, attempts, audit, and source facts |

## Specification

Only allowlisted data expressions in a `metta` fence affect orchestration.
Prose and other fence languages are explanatory.

````markdown
# Incident response

```metta
(thread-spec-v1 incident-42)
(thread-title incident-42 "Incident response")
(thread-owner incident-42 responder)
(thread-budget incident-42 120000 60000 1)
(thread-supervision incident-42 30 5 60 2)
(thread-role incident-42 control local-control)
(thread-role incident-42 worker local-worker)
(thread-role incident-42 supervisor thread-supervisor)
(thread-role incident-42 evaluator result-evaluator)
(thread-role incident-42 specialist security-specialist)
(thread-role incident-42 adjudicator security-owner)
(thread-workflow incident-42 guided-research)
(thread-workflow-step incident-42 guided-research 10 "Inspect the repository and existing evidence.")
(thread-workflow-step incident-42 guided-research 20 "Perform only the released task and verify acceptance.")
(thread-workflow-step incident-42 guided-research 30 "Report changed artifacts, checks, and uncertainty.")
(thread-mcp-profile incident-42 oh-my-goals)
(thread-task incident-42 collect-evidence local evidence-collected normal)
(thread-task incident-42 redact-summary specialist summary-redacted high)
(thread-depends incident-42 redact-summary collect-evidence)
(thread-not-before incident-42 redact-summary 2000000000)
(thread-merge-policy incident-42 none none)
```
````

`thread-budget` stores the hard token ceiling, soft threshold, and minimum local
iterations before delegation. `thread-supervision` stores lease seconds, idle
timeout, wall timeout, and retry count.

### Project agents in `thread-spec-v2`

Version two is opt-in. Existing `thread-spec-v1`, `goalchainer-thread-v1`, plan,
UI, and audit records keep their original shape. A v1 audit and a v2 audit
cannot share one JSONL file.

The checked example is
[`examples/threadkeeper-project-agents-v2.md`](../examples/threadkeeper-project-agents-v2.md).
It adds one explicit Agent Orchestrator project, a registry containing every
role owner, and logical Atomspace links:

```metta
(thread-spec-v2 project-agent-research)
(thread-project project-agent-research "research-project")
(thread-agent project-agent-research research-worker)
(thread-role project-agent-research worker research-worker)
(thread-atomspace-link project-agent-research project-shared shared project)
(thread-atomspace-link project-agent-research worker-private private research-worker)
```

Agent keys are stable MeTTa symbols. They are not Agent Orchestrator database
IDs. MeTTaScript selects the task role and agent key, then emits the project,
GoalChainer attempt key, visible logical links, workflow, and MCP profile.
GoalChainer sends `projectAgentKey` and `projectAgentRole` at the top level of
the Agent Orchestrator session request. GoalChainer never sends an agent UUID,
an Atomspace path, or a caller-selected link.

Agent Orchestrator returns a canonical UUID in `projectAgentId` and its own
positive `projectAgentAttempt`. GoalChainer validates the complete response
through MeTTa before appending any binding event. GoalChainer task attempts and
stable-agent attempts are separate counters. Two tasks can both be GoalChainer
attempt 1 while the same project agent owns Agent Orchestrator attempts 1 and
2.

The guided prompt names the project, MeTTa-selected role, and stable agent key.
It explains that session-scope Oh My Goals memory is the agent's private
persistent project Atomspace. The agent must read prior private project notes
and record sourced observations and decisions before exit. The rendered prompt
is bounded to 4096 UTF-8 bytes.

`goalchainer-ui-v2` adds the project agent registry and keeps the full session
attempt history on each task. Each attempt reports both counters, the canonical
agent UUID, session ID, current observed status, activity, and termination
state. Later audit-only observations update the projected status without
changing the immutable attempt identity or Omega lifecycle state. Atomspace
rows contain only `linkKey`, `scope`, and `owner`.

A task capability is `local`, `specialist`, or `either`. Stakes are `normal` or
`high`. A high-stakes specialist route requires the adjudicator role when that
role is declared. `thread-not-before` stores a Unix timestamp. MeTTaScript
rewrites a dependency-ready task to `scheduled` until the observed clock
reaches that value.

`thread-workflow` names the worker workflow. Each `thread-workflow-step` adds
one ordered instruction. MeTTaScript validates the graph reference, positive
and unique order, and string instruction. The typed host boundary limits the
workflow to 12 steps, 512 bytes per instruction, and 2048 instruction bytes in
total. If a version-one specification omits the workflow, MeTTaScript supplies
the checked `goalchainer-default` research workflow.

`thread-mcp-profile` selects the bounded MCP integration installed for each
released task. Version one accepts `oh-my-goals`. If the fact is omitted,
MeTTaScript supplies that profile. The compiled metagraph names all 12 tools:
`remember`, `query`, `solve`, `revise`, `forget`, `explain`, `find_papers`,
`ingest_paper`, `add_claim`, `citations`, `review`, and
`check_retractions`. Unknown or duplicate profile facts fail compilation.

Merge policy is one of:

```metta
(thread-merge-policy incident-42 none none)
(thread-merge-policy incident-42 integration-branch goalchainer-integration)
```

The compiler rejects unknown heads, executable `!` entries, malformed atoms,
mixed thread IDs, duplicate singletons, duplicate tasks, missing dependencies,
self-dependencies, cycles, duplicate role identities, invalid numeric bounds,
and inconsistent merge policies. The semantic digest is calculated from
normalized facts, not prose.

## MeTTa and host ownership

The main program is
`integrations/threadkeeper/goalchainer_threadkeeper.metta`.

MeTTaScript owns:

- Mettabase `md-atoms` traversal
- schema and dependency-cycle validation
- normalized role and task compilation
- OmegaClaw directive-plan construction
- ThreadKeeper escalation and routing
- scheduled release decisions and UI projections
- guided worker workflow compilation
- typed MCP profile and tool-set compilation
- worker-exit gating
- evaluator and adjudicator verdict composition
- retry and permanent-failure outcomes
- the Mettabase status document AST

Python owns:

- safe file opening and permissions
- typed protocol decoding
- locks, clocks, process groups, PTYs, and output limits
- JSON evaluator context
- audit persistence
- git worktrees and atomic ref updates
- CLI and OmegaClaw request validation

The two host effects called from MeTTa are
`goalchainer_thread_atoms.run_process` and
`goalchainer_thread_atoms.evaluate`. They return MeTTa observations and verdicts.
All arbitrary host text is encoded as a `b64_` URL-safe base64 symbol. Empty
output, quotes, semicolons, newlines, and evaluator error text cannot become
MeTTa syntax.

Python callable evaluators remain available to the library for compatibility
and focused tests. CLI and demo evaluator commands retain the PeTTa-native
grounded-attempt path for bounded effects. Routing, release, and outcome
conclusions still come from MeTTaScript. Each returned attempt states its
effect engine as `petta-native` or `python-callable`.

## Lifecycle

One task attempt follows this sequence:

```text
Omega ready check
  -> MeTTaScript route and release rewrites
  -> Omega claim
  -> retained grounded attempt
       -> worker py-atom
       -> evaluator py-atom
       -> optional adjudicator py-atom
       -> observation atoms
  -> MeTTaScript outcome rewrite
  -> Omega complete, unclaim for retry, or block
```

OmegaClaw derives the Kanban board from its directive plan and append-only
lifecycle claims. A blocked task produces `upstream-blocked` for direct and
transitive dependents. The vendored OmegaClaw propagation rules use distinct
labels for direct blocked rules and transitive upstream-blocked rules, so one
rule does not suppress the other.

The orchestration lock covers route, claim, attempt recording, outcome, and
lifecycle mutation for one thread. If the host process fails after a claim, the
recovery guard blocks the task instead of leaving it in progress.

## Evaluators

An evaluator is an argument array. GoalChainer writes a private temporary JSON
file and appends its path to the command. The file contains the task and worker
observation. The evaluator prints one JSON object:

```json
{"verdict": "accept", "reason": "acceptance condition observed"}
```

The verdict must be `accept` or `reject`. The output must contain exactly one
bounded JSON object. Evaluation failures become rejection reasons. A nonzero
worker status or timeout is rejected before the evaluator runs.

## Commands

Compile a document into a durable Omega plan and initialize the audit:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli thread compile \
  --spec examples/threadkeeper-demo.md \
  --plan thread.metta \
  --audit thread.jsonl \
  --json
```

Inspect routing without running a worker:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli thread route \
  --spec examples/threadkeeper-demo.md \
  --plan thread.metta \
  --audit thread.jsonl \
  --task redact-summary \
  --local-iterations 1 \
  --hard \
  --json
```

Run one task:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli thread run \
  --spec examples/threadkeeper-demo.md \
  --plan thread.metta \
  --audit thread.jsonl \
  --task collect-evidence \
  --cwd "$PWD" \
  --worker-command '["python3","-c","print(\"evidence-collected\")"]' \
  --evaluator-command '["python3","check_evidence.py"]' \
  --json
```

Render the current board:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli thread render \
  --spec examples/threadkeeper-demo.md \
  --plan thread.metta \
  --audit thread.jsonl
```

Project the board into Agent Orchestrator and dispatch released tasks:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli thread ui-sync \
  --spec thread.md --plan thread.metta --audit thread.jsonl \
  --project my-project --ao-url http://127.0.0.1:3001 --json

PYTHONPATH=src python3 -m goal_chainer.cli thread dispatch-due \
  --spec thread.md --plan thread.metta --audit thread.jsonl \
  --project my-project --ao-url http://127.0.0.1:3001 --json

PYTHONPATH=src python3 -m goal_chainer.cli thread ui-watch \
  --spec thread.md --plan thread.metta --audit thread.jsonl \
  --project my-project --ao-url http://127.0.0.1:3001 \
  --interval-seconds 5 --json
```

`ui-inspect` derives the projection without network effects. `ui-observe`
records one bounded session observation. `ui-watch` repeats observation and
dispatch until interrupted. The client accepts only an explicit HTTP loopback
origin, bounds time and response size, and never treats session state as an
Omega lifecycle mutation.

For v2, `--project` must equal the `thread-project` value. Sync, observation,
dispatch, and watch reject a mismatch before any HTTP request or audit write.

The spawned coding agent receives the compiled workflow as its initial system
instructions, followed by the released task contract, dependencies, and
acceptance condition. The prompt names the compiled MCP profile and tools and
tells the agent to use the memory and literature loops when they help. It also
tells the agent to report evidence and not to claim GoalChainer completion.
The MeTTa workflow and profile are policy. Python only renders those compiled
atoms into Agent Orchestrator's bounded request.

The OmegaClaw skill exposes the same typed service:

```metta
(goalchainer-thread-dispatch
  "{\"operation\":\"inspect\",\"spec\":\"/path/thread.md\",\"plan\":\"/path/thread.metta\",\"audit\":\"/path/thread.jsonl\"}")
```

## Demonstrated behavior

The live demo uses external evaluator commands, so its attempts pass through
the py-atoms called by `gc-thread-attempt`. It checks:

- a local task completes
- output renews the passive lease
- a hard specialist task routes after the minimum local iteration
- high-stakes specialist work requires an accepting adjudicator
- the evaluator rejects the first result and accepts the retry
- a worker failure retries three total attempts
- exhausted retries block a dependent task through OmegaClaw
- the hard budget ceiling denies work before claim
- the audit hash chain verifies
- MeTTa produces a Mettabase status document

The final demo board has three done tasks, one permanently blocked task, one
upstream-blocked child, and one ready task whose specialist route was denied by
the budget gate. The JSON report includes `before`, `now`, `verified`,
per-task attempt counts, the Omega snapshot, and the rendered Markdown.

A second checked run used the real Agent Orchestrator daemon and its fake
agent harness. Before the release time the task appeared in `scheduled`. After
the observed clock passed the constraint, GoalChainer created and linked
session `scratch-1`. The terminal progressed through active, input, blocked,
and done output. Repeating dispatch created no session, and Agent Orchestrator
stored exactly one session for the source task.

The v2 GoalChainer contract has two checked paths:

```bash
uv run --extra dev pytest -q \
  tests/test_thread_demo.py::test_project_agent_v2_example_compiles_dispatches_and_projects

uv run --extra dev pytest -q \
  tests/test_ao_ui.py::test_v2_dispatch_posts_metta_agent_and_normalizes_ao_identity \
  tests/test_ao_ui.py::test_v2_goal_attempts_are_independent_from_stable_agent_attempts \
  tests/test_ao_ui.py::test_v2_projection_overlays_latest_session_observation
```

The first command compiles the user-facing example and checks its MeTTa-selected
agent, logical links, and v2 board. The second uses a bounded HTTP transport
fixture. It checks the guided prompt, Agent Orchestrator request and response
contract, separate attempt counters, audit bindings, and current UI projection.
Agent Orchestrator's own integration suite is the authority for SQLite project
agent persistence and durable private Atomspace files.

## Git worktrees

With `integration-branch` policy, GoalChainer creates a locked detached
worktree for the attempt. Accepted changes are committed in that worktree.
`git merge-tree --write-tree` checks integration without touching the caller's
index or working tree. `git commit-tree` creates a merge commit when needed.
`git update-ref` performs a compare-and-swap update.

The integration branch must not be checked out in any worktree. A concurrent
ref change is rejected. A merge conflict happens before task completion, blocks
the claimed task through the recovery guard, and retains the worktree for
inspection. SHA-1 and SHA-256 repositories are supported.

## Files and security

The specification must be UTF-8 Markdown and at most 1 MiB. File reads use
`O_NOFOLLOW` where the platform provides it. Plan, audit, and lock identities
are checked across operations. Audit files and lock files require owner-only
permissions.

Worker processes run without a shell. Commands are argument arrays. The
supervisor bounds captured output and terminates the process group on idle,
lease, wall-time, or output-limit failures. Evaluator context files are
owner-only and removed after use.

The JSON Lines audit is append-only and stores a sequence number, UTC timestamp,
thread ID, event type, actor, payload, previous hash, and event hash. Opening a
thread verifies the complete chain and rejects a log belonging to another
thread.

Version two adds `project_id` to every record. The store rejects a protocol mix
or project change. A session binding is written as an ordered prefix:
`attempt-started`, `ao-agent-bound`, `ao-session-attempt`, then
`ao-session-bound`. If a process stops between those appends, replay validates
every existing payload and writes only the missing suffix. A replay with the
same session ID but another role, agent key, agent UUID, agent attempt, project,
or state fails before appending another event.

## Operations and recovery

Keep the Markdown specification, compiled `.metta` plan, and `.jsonl` audit
together. Back up all three. A plan cannot be paired with a specification whose
semantic digest differs. An audit cannot be paired with another thread ID.

If a worker is interrupted, inspect the board and audit before retrying:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli thread inspect \
  --spec thread.md \
  --plan thread.metta \
  --audit thread.jsonl \
  --json
```

An interrupted claimed attempt is recovered as blocked when the orchestrator
observes the exception. A retained worktree contains the attempted files and
commit. Resolve or copy them manually, then use a new specification or an
explicit Omega lifecycle operation according to the incident policy.

Do not edit hash-chained audit lines. Do not rewrite lifecycle claims in the
plan. Changes invalidate their integrity checks.

## Migration and rollback

Existing `goalchainer directive` commands remain unchanged. Adopt thread
orchestration per workflow:

1. Write the Markdown specification.
2. Run `thread compile` and inspect the generated plan.
3. Run `thread route` for specialist and high-stakes tasks.
4. Exercise evaluator rejection, retry exhaustion, and timeout behavior.
5. Enable worktree integration only after naming a dedicated branch.
6. Move automation to `thread run`.

Migrate a v1 thread to v2 by creating a new specification, plan, and audit:

1. Change the header to `thread-spec-v2`.
2. Add exactly one `thread-project`.
3. Add one `thread-agent` for each declared role owner.
4. Add exactly one shared project link and one private link per agent.
5. Compile to a new plan path and inspect `goalchainer-ui-v2`.
6. Use the same project ID for every Agent Orchestrator command.

Do not add v2 records to an existing v1 audit. Do not treat a v1 role symbol as
an Agent Orchestrator UUID.

Rollback stops new thread runs and returns callers to the existing directive
surface. Preserve the plan and audit for investigation. The thread feature does
not migrate or reinterpret an existing directive plan because its specification
digest and role policy would be missing.

To roll back only project-agent dispatch, stop v2 sync, watch, and dispatch
commands. Preserve the v2 Markdown, plan, and audit for replay. Start a separate
v1 thread with separate plan and audit paths if the old UI contract is needed.
Deleting or editing the v2 audit is not a rollback.

## Sources and future extensions

The implementation was checked against these exact local revisions:

- ThreadKeeper `a64de99e10f9f8078d25bff511b44fd71819e931`
- Hence `81b8cac24013073f9b72f8886d2538df0ee8888b`
- Mettabase `c9bbbe8d0ee52ce25b088c664c73b0de32d0cb12`
- OmegaClaw Core `feed65260eac4ef669fc7922ed8d6be1311aa79a`
- omegaclaw-deontic `02d019e7f5513c905ad2f743dba6d3f77813ae36`

ThreadKeeper supplies the escalation policy. Hence supplies the closest
Spindle-backed precedent for claims, attempt versions, supervision, retries,
activity, and integration. GoalChainer uses those protocol ideas without
running a second Spindle board.

`tests/fixtures/threadkeeper/hence-compatibility.md` contains equivalent SPL and
MeTTa plans. The differential test freezes the expected initial, claimed,
unclaimed, completed, and blocked boards. It checks the retained PeTTa
compatibility path against those states and also runs the selected Hence binary
when `HENCE_BIN`, `hence` on `PATH`, or the pinned development checkout is
available.

Clingo remains a future optimizer for assignment capacity, schedules, and
global resource constraints over a frozen Omega snapshot. It should return
recommendations, not lifecycle state.

MeTTaLingo and MettaLingua remain future projection layers for multilingual
labels and instructions. Stable task IDs and MeTTa meanings should stay
language neutral. MeTTaSpeak's EPILOG implementation informed the
MeTTaScript boundary, but it is not imported as an orchestration dependency.

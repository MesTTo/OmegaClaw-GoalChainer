# Agent Orchestrator UI integration

## Runtime correction, 2026-07-29

MeTTaScript is the primary runtime for this integration. PeTTa is no longer
the authority boundary. Keep the existing PeTTa and Python work as a
compatibility path and as source material for Prolog or host atoms.

The Agent Orchestrator website must connect to a MeTTaScript agent Atomspace.
Represent task, agent, session, schedule, dependency, assignment, observation,
and projection facts as atoms. Put orchestration and release rules in `.metta`
files. TypeScript grounded atoms may hold live Agent Orchestrator objects and
perform the bounded HTTP and UI host effects.

Use MeTTaLSP for document symbols, definitions, references, host-type
navigation, diagnostics, lint, and focused tests. Confirm evaluator-sensitive
results with the installed MeTTaScript Node runtime. The integration uses
MeTTaScript 2.7's `get-mettatype` spelling. The executable policy, MeTTa docs,
and native test document currently have no MeTTaLSP diagnostics.

Status: implemented. Final verification and local commits are tracked in
`ai-todo.md`.

## MeTTa design constraint

Treat the orchestration world as a metagraph. Tasks, dependencies, schedules,
agents, sessions, observations, and policy conclusions are atoms. Rules match
graph shapes and rewrite them into release, route, outcome, and projection
atoms.

Use `match` for facts in a space and structural patterns for values crossing a
bounded host boundary. Keep nondeterministic relations as streams until a
caller explicitly needs a collected protocol value. Use `let*` for dependent
reductions, not as a substitute for the graph model.

TypeScript and Python may validate transport limits, observe clocks and
processes, persist records, and perform UI or HTTP effects. They must not
restate a MeTTa policy conclusion.

## Selected repositories

- GoalChainer: `/home/user/Dev/OmegaClaw-GoalChainer`
- Agent Orchestrator fork: `https://github.com/MesTTo/agent-orchestrator`
- Agent Orchestrator upstream: `https://github.com/AgentWrapper/agent-orchestrator`
- Local fork checkout: `/home/user/Dev/agent-orchestrator`
- Fork baseline: `987f00e6d05fd3bddea361895281e91d6cf518ef`
- Agent Orchestrator license: Apache-2.0
- GoalChainer license: inspect and preserve the repository's current license

The user selected the original Agent Orchestrator repository and asked for the
fork to serve as a UI for part of OmegaClaw GoalChainer. Alternative
applications are no longer the implementation target.

## Authority contract

One component owns each decision.

| Concern | Authority |
|---|---|
| Human-readable task specification | Mettabase MeTTa Markdown |
| Schedule, routing, retry, and UI projection conclusions | GoalChainer MeTTaScript rules |
| Durable task claims, blocks, completions, and board state | OmegaClaw `lib_directive` |
| Thread supervision, evaluation, retry, and audit | GoalChainer ThreadKeeper layer |
| Coding-agent worktrees, processes, terminals, and session lifecycle | Agent Orchestrator |
| GoalChainer task display inside Agent Orchestrator | Read-only projection derived from the GoalChainer authorities |

Agent Orchestrator must not mutate GoalChainer task lifecycle state. Its local
database stores the last observed projection so the desktop UI can load quickly
and survive restarts. The projection carries its source digest and observation
time, so stale data is visible rather than mistaken for current truth.

GoalChainer may create an Agent Orchestrator session after the OmegaClaw
lifecycle reports the task dependency-ready and GoalChainer MeTTaScript
concludes that it is time-released, policy-allowed, and not already linked to a
session. Agent Orchestrator remains authoritative for that spawned session.
GoalChainer records the returned session identifier as correlation evidence,
not as proof that the task completed.

## UI scope

The fork keeps the existing sessions board and session detail screen. A
project-scoped GoalChainer view will show:

- scheduled tasks before their release time;
- backlog, ready, in-progress, blocked, and done tasks;
- dependencies, assigned role, schedule, and current policy reason;
- the projection digest and freshness;
- the linked Agent Orchestrator session when execution has started.

Selecting a linked task opens the existing session detail screen. The existing
terminal and inspector provide the live agent transcript and workspace state.
Task lifecycle controls remain absent from the projection view.

## Scheduling boundary

Future execution is a task release constraint, not a calendar entry. The
schedule is declared in a MeTTa Markdown fact and validated by MeTTaScript.
MeTTaScript receives the current host time as an observation and returns the
release decision. Python supplies the clock and performs the HTTP call, but it
does not reimplement the release rule.

The UI may derive a `scheduled` display state when OmegaClaw reports a task as
dependency-ready while its MeTTaScript release decision is still false. The
MeTTaScript UI projection derives that display state. It does not alter the
OmegaClaw plan.

## Integration shape

GoalChainer publishes one versioned, bounded snapshot for an Agent Orchestrator
project. The Agent Orchestrator daemon validates and atomically replaces that
project's previous snapshot. SQLite triggers append projection changes to the
existing CDC log. The desktop subscribes to the CDC event and refetches the
project projection.

The initial API contract is project-scoped:

```text
GET    /api/v1/projects/{projectId}/goalchainer
PUT    /api/v1/projects/{projectId}/goalchainer
DELETE /api/v1/projects/{projectId}/goalchainer
```

The PUT body is limited to 1 MiB. The daemon validates the complete projection
before one SQLite transaction replaces it. Migrations `0037` and `0038` add the
projection record, CDC trigger, and idempotent external source mapping. OpenAPI,
sqlc, and frontend schemas are generated from the fork's existing workflows.

Agent Orchestrator treats a projection older than two minutes as stale. The
board keeps rendering the last snapshot but labels it `source stale`.

## Implemented operations

The GoalChainer thread CLI exposes `ui-inspect`, `ui-sync`, `ui-observe`,
`ui-watch`, `dispatch-due`, `bind-session`, and `disconnect`. The sync and
watch paths accept only an explicit loopback HTTP origin. Calls have bounded
timeouts, responses are limited to 1 MiB, task prompts are capped, and source
task IDs are stable across retries.

The specification may declare one `thread-workflow` and ordered
`thread-workflow-step` facts. MeTTaScript validates and compiles that graph.
GoalChainer renders the compiled steps into the initial Agent Orchestrator
worker prompt with the task contract and evaluator boundary.

The fork renders scheduled, backlog, ready, in-progress, blocked, and done
lanes. The TypeScript Atomspace stores projection, task, session, agent, and
assignment atoms. A grounded `ao-open-session` atom navigates a linked card to
the existing session terminal. CDC invalidates the query after projection
updates.

PostHog transmission is disabled in renderer, daemon, development, and release
configuration. Local SQLite telemetry can remain enabled without a remote
sink.

## Checked live flow

A real local daemon received a two-task research graph. The first task stayed
visible in `scheduled` before its 2033 release constraint. A 2034 clock
observation caused MeTTaScript to release it and GoalChainer created Agent
Orchestrator session `scratch-1`. The board linked the task to that session.
The fake harness produced terminal activity through its done state. A repeated
dispatch returned zero new work and the daemon still contained one session.
Session observations were appended to the GoalChainer audit without changing
the Omega task lifecycle.

## Non-goals

- Agent Orchestrator will not become another dependency or policy reasoner.
- GoalChainer will not copy Agent Orchestrator terminal or worktree logic.
- The integration will not import Routa's orchestration engine.
- The integration will not expose either daemon beyond its existing loopback
  trust boundary.
- The integration will not claim that a running or exited agent session proves
  task completion. OmegaClaw completion still requires the evaluator path.

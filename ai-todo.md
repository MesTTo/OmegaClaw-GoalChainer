# SNARS GoalChainer implementation

- [x] Record the GoalChainer, Mettabase, PeTTa, and SWI baseline state.
- [x] Run the current GoalChainer test suite and live SNARS query tests.
- [x] Run every committed Mettabase Python SNARS test and PeTTa SNARS fixture.
- [x] Verify that the Mettabase remote is private and commit `5da3c47` is not on a fetched remote ref.
- [x] Inspect committed SNARS source, tests, callers, and capability signatures.
- [x] Read relevant GoalChainer and Mettabase Markdown design notes, then verify their claims against executable PeTTa source and tests.
- [x] Treat PeTTa execution as authoritative and confirm any MeTTa LSP diagnostic against the pinned runner.
- [x] Search GoalChainer and Mettabase history before each implementation slice.
- [x] Fix the shared conditional-edge proof stamp defect in Mettabase with a regression.
- [x] Add GoalChainer dependency resolution and runtime diagnostics.
- [x] Add typed SNARS result and error models.
- [x] Inspect `/home/user/Dev/oh-my-goals` and record the applicable MeTTa, ranking, persistence, and property-test patterns.
- [x] Add a versioned tagged protocol and safe MeTTa program construction.
- [x] Add deterministic SQLite event persistence and replay.
- [x] Add native ingest, belief, query, proof, and explanation APIs.
- [x] Add trust, outcome, goal, subgoal, temporal, and maintenance APIs.
- [x] Add counterfactual, discovery, mining, and guard inspection APIs.
- [x] Replace projected PeTTaChainer STV belief in the decision pipeline.
- [x] Change scoring to use native SNARS expectation once.
- [x] Add explicit native and offline modes with structured failures.
- [x] Add the structured CLI command group and JSON error contract.
- [x] Add the OmegaClaw dispatcher, skill docs, prompt payload, and tests.
- [x] Add unit, property, failure, live integration, and decision differential tests.
- [x] Update architecture, migration, persistence, privacy, and rollback docs.
- [x] Run `jscpd` after each substantial code slice and remove introduced clones.
- [x] Run formatting, lint, compile, full tests, and `git diff --check`.
- [x] Review every changed line and preserve all user-owned untracked files.
- [x] Create atomic local commits, excluding handoff and scratch files.
- [x] Produce a native end-to-end example and exact final verification report.

## OmegaClaw deontic orchestration integration

- [x] Search GoalChainer and omegaclaw-deontic source and history for existing orchestration work.
- [x] Inventory the executable `lib_directive` and deontic inspection surfaces at the pinned revisions.
- [x] Record the expanded user requirements and repository safety constraints in `ai-notes/omegaclaw-orchestration-research.md`.
- [x] Fetch and inspect the latest OmegaClaw and omegaclaw-deontic upstream revisions.
- [x] Update clean pinned OmegaClaw checkouts and reconcile GoalChainer with upstream changes.
- [x] Fix and regress the documented `blocked` to `upstream-blocked` dependency cascade.
- [x] Inspect and test Mettabase's existing MeTTa Markdown implementation.
- [x] Inspect CalDar and the Clingo Python API for Kanban and scheduling representations.
- [x] Inspect MeTTaLingo, MettaLingua, and MeTTaSpeak's TypeScript epilog system.
- [x] Re-inspect oh-my-goals for dependency, persistence, prioritization, and property-test patterns.
- [x] Define typed GoalChainer plan, lifecycle, inspection, and error contracts.
- [x] Replace regex output parsing with structured MeTTa record parsing.
- [x] Make incident plans durable when a plan path is supplied and safe when ephemeral.
- [x] Model real task dependencies and propagate blocked upstream work.
- [x] Expose status, next, board, summary, validation, analysis, trace, and task-state operations.
- [x] Expose claim, unclaim, complete, block, and unblock lifecycle operations.
- [x] Integrate claim and completion into the selected-action execution path.
- [x] Add structured CLI and OmegaClaw dispatch surfaces without breaking the existing command.
- [x] Add a live orchestration demo showing dependency gating, claim, completion, and unblock behavior.
- [x] Add unit, failure, persistence, generated-input, and non-skipped PeTTa integration tests.
- [x] Update README and architecture documentation with migration and demo guidance.
- [x] Run Ruff, compile, jscpd, GoalChainer tests, and omegaclaw-deontic tests.
- [x] Review the diff, create atomic commits, and preserve all user-owned files.

## Later: ThreadKeeper with MeTTa Markdown specifications

- [x] Record the original ThreadKeeper request as a separate implementation phase.
- [x] Inspect ThreadKeeper's current architecture and MeTTa escalation policy.
- [x] Compare the proposed specification layer with local `zetl` and Spindle.
- [x] Inspect `/home/user/Dev/hence` as the direct Spindle-backed orchestration precedent.
- [x] Write the staged design and acceptance contract in `ai-notes/threadkeeper-metta-markdown-later-plan.md`.
- [x] Recheck ThreadKeeper at `a64de99e10f9f8078d25bff511b44fd71819e931`.
- [x] Pin Hence as the orchestration reference at `81b8cac24013073f9b72f8886d2538df0ee8888b`.
- [x] Search current GoalChainer, ThreadKeeper, Hence, and OmegaClaw history before implementation.
- [x] Freeze the implementation contract in `ai-notes/threadkeeper-implementation-plan.md`.
- [x] Add immutable thread specification, route, attempt, evaluation, usage, and audit models.
- [x] Parse real MeTTa Markdown through the pinned Mettabase implementation.
- [x] Reject executable, unknown, malformed, duplicate, or incomplete semantic facts.
- [x] Preserve normalized facts, source lines, stable IDs, and semantic digests.
- [x] Add a versioned PeTTa thread compilation and policy protocol.
- [x] Implement MeTTa schema validation and normalized compilation.
- [x] Implement MeTTa escalation, role routing, adjudication, evaluator, and retry decisions.
- [x] Compile thread tasks and dependencies into OmegaClaw `lib_directive`.
- [x] Validate missing references and cycles before creating a durable plan.
- [x] Add a locked, hash-chained, mode-0600 append-only audit store.
- [x] Record usage, routing, claims, attempts, liveness, evaluation, lifecycle, and integration.
- [x] Add bounded subprocess execution with output limits and safe termination.
- [x] Add passive PTY/output and workspace activity observation.
- [x] Add lease renewal, idle timeout, wall timeout, retry, and permanent failure.
- [x] Enforce separate supervisor, worker, evaluator, specialist, and adjudicator roles.
- [x] Add optional isolated git worktrees and isolated integration-branch updates.
- [x] Keep OmegaClaw as the only task-state authority. Do not run a parallel Spindle board.
- [x] Add thread compile, inspect, route, record-usage, run, render, and demo APIs.
- [x] Add `goalchainer thread` CLI operations.
- [x] Add `goalchainer-thread-dispatch` to the OmegaClaw skill surface.
- [x] Add parser, protocol, property, round-trip, policy, supervision, failure, and git tests.
- [x] Add live PeTTa differential tests against the selected Hence behavior corpus.
- [x] Add a checked demo for local work, delegation, lease, evaluation, retry, adjudication, failure propagation, and budget denial.
- [x] Update architecture, operations, security, migration, rollback, and demo documentation.
- [x] Run jscpd after every substantial implementation slice and remove introduced clones.
- [x] Run Ruff, compileall, full GoalChainer tests, OmegaClaw deontic tests, directive tests, live demos, and `git diff --check`.
- [x] Review every changed line and preserve every user-owned file.
- [x] Create atomic local commits without pushing the public repository.

## Agent Orchestrator UI integration

- [x] Add a MeTTa Markdown workflow graph and guided Agent Orchestrator worker prompt.
- [x] Replace the PeTTa-authoritative integration boundary with MeTTaScript 2.7.
- [x] Model Agent Orchestrator tasks, agents, sessions, and observations in a MeTTaScript Atomspace.
- [x] Link the React website to that Atomspace through typed TypeScript grounded atoms.
- [x] Port scheduling, release, routing, and projection rules to MeTTaScript-compatible `.metta`.
- [x] Express orchestration as metagraph facts and rewrite relations, with host code limited to observations, bounds, persistence, and effects.
- [x] Replace host-style control flow in the MeTTa policy when a structural pattern, graph match, or rewrite relation expresses the same decision.
- [x] Use MeTTaLSP for every MeTTaScript symbol, host-atom, diagnostic, lint, and focused-test pass.
- [x] Confirm MeTTaLSP results with the installed MeTTaScript Node runtime and record any adapter mismatch.
- [x] Record the MeTTaScript computed-error deduplication mismatch and its exact reproducer.
- [x] Retain the current PeTTa, Prolog, and Python work as a compatibility layer rather than deleting it.
- [x] Reinspect `/home/user/Dev/oh-my-goals` for MeTTaScript-native goal, transition, priority, and Atomspace patterns.

- [x] Record the fork, checkout, upstream revision, licenses, and dirty-tree baselines.
- [x] Read Agent Orchestrator's AGENTS.md, architecture, status, API generation, storage, CDC, frontend board, and test patterns.
- [x] Search both repositories' current source and history for an existing external-board or scheduled-task integration.
- [x] Compare Agent Orchestrator, Routa, Paperclip, and other MIT or Apache prior art without importing a second lifecycle authority.
- [x] Freeze the cross-repository authority contract in `ai-notes/agent-orchestrator-ui-integration.md`.
- [x] Keep Mettabase MeTTa Markdown as the specification authority.
- [x] Keep GoalChainer MeTTaScript authoritative for schedule, routing, retry, and projection conclusions.
- [x] Keep OmegaClaw `lib_directive` authoritative for durable dependency and task lifecycle state.
- [x] Keep Agent Orchestrator as the session execution, terminal, transcript, and UI authority.
- [x] Define a versioned GoalChainer projection protocol with stable thread, task, source digest, plan digest, schedule, dependency, assignment, and linked-session identities.
- [x] Represent future release times in MeTTa facts and validate their references, uniqueness, and values in MeTTaScript.
- [x] Add a MeTTaScript release decision so Python does not decide whether a scheduled task is due.
- [x] Add immutable Python models and generic S-expression parsing for the projection and release records.
- [x] Add a bounded loopback Agent Orchestrator client with strict URL, timeout, response-size, and error handling.
- [x] Add idempotent snapshot synchronization to Agent Orchestrator.
- [x] Add idempotent task dispatch that creates one Agent Orchestrator session per eligible task.
- [x] Persist the GoalChainer task to Agent Orchestrator session correlation and recover it after restart.
- [x] Project Agent Orchestrator session observations back into the GoalChainer audit trail without treating them as task-state truth.
- [x] Add CLI operations for inspect, sync, dispatch-due, watch, disconnect, and checked demo flows.
- [x] Add an Agent Orchestrator migration for one atomic per-project GoalChainer snapshot projection.
- [x] Add DB-triggered CDC for GoalChainer projection changes.
- [x] Add a GoalChainer backend service and strict GET, PUT, and DELETE project routes.
- [x] Regenerate sqlc, OpenAPI, and frontend TypeScript API types.
- [x] Add a project GoalChainer board that renders scheduled, backlog, ready, in-progress, blocked, and done tasks.
- [x] Show schedule time, dependencies, assigned role, reason, source freshness, and linked agent session on each task.
- [x] Make linked task cards open the existing Agent Orchestrator session terminal and transcript view.
- [x] Keep the GoalChainer board read-only for lifecycle mutations so the UI cannot bypass MeTTa policy.
- [x] Add backend unit, validation, migration, store, controller, service, CDC, and API parity tests.
- [x] Add frontend type, query, board rendering, empty, stale, scheduled, linked-session, and SSE invalidation tests.
- [x] Add GoalChainer model, parser, MeTTaScript protocol, client, failure, property, persistence, and live integration tests.
- [x] Add a checked end-to-end demo showing future scheduling, pre-execution visibility, due release, agent session launch, live linkage, and terminal inspection.
- [x] Update architecture, operations, privacy, migration, rollback, and demo documentation in both repositories.
- [x] Disable PostHog transmission in the fork's development and release configuration.
- [x] Run jscpd after each substantial TypeScript or Python slice and remove introduced clones.
- [x] Run Ruff, basedpyright, compileall, pytest, MeTTaScript and retained PeTTa compatibility suites, Go build/test/race/vet/lint, frontend typecheck/build/tests, API drift, and `git diff --check`.
- [x] Review every changed line in both repositories and preserve every unrelated user-owned file.
- [x] Create atomic local commits in each repository without pushing the public fork.

## Oh My Goals MCP access for dispatched agents

- [x] Inspect the current twelve-tool Oh My Goals MCP server, skill, installer, and packed end-to-end proof.
- [x] Trace Agent Orchestrator workspace creation, agent configuration discovery, launch, restore, and cleanup for Claude Code, Codex, and OpenCode.
- [x] Define MeTTa facts for the MCP toolset and keep MeTTaScript authoritative over which released tasks receive it.
- [x] Compile and parse a versioned MCP-access record without reconstructing policy in Python.
- [x] Pass the selected MCP profile through the GoalChainer to Agent Orchestrator session API.
- [x] Provision an isolated Oh My Goals stdio registration and matching skill into each selected agent workspace.
- [x] Preserve all existing agent MCP servers, config comments, permissions, and unrelated project files.
- [x] Set project, session, parser, and durable-store identity so concurrent agent sessions share only the intended project memory.
- [x] Cover launch, restore, idempotency, unsupported harnesses, missing runtime, invalid paths, rollback, and cleanup.
- [x] Prove discovery and representative memory and literature tool calls through a spawned agent boundary.
- [x] Update GoalChainer and Agent Orchestrator documentation with configuration, security, migration, and rollback behavior.
- [x] Run MeTTaLSP diagnostics, hover, focused tests, deduplicate, Ruff, basedpyright, pytest, Go tests and race checks, frontend checks, jscpd, and diff review.
- [x] Create atomic local commits in both repositories without pushing.

## Project-scoped persistent agent Atomspaces

- [x] Record the project, agent identity, role, Atomspace, session, persistence, and UI requirements.
- [x] Search current source and history in GoalChainer, Agent Orchestrator, MeTTaScript, Oh My Goals, Mettabase, and related orchestration repositories.
- [x] Freeze the authority contract and versioned storage layout before editing runtime code.
- [x] Make project identity explicit in the MeTTa specification and compiled protocol.
- [x] Represent stable project agents, role assignments, task assignments, and session attempts as MeTTa facts.
- [x] Keep task-to-role and task-to-agent conclusions in MeTTaScript.
- [x] Add typed Python models and parsing without recreating assignment policy.
- [x] Pass stable agent identity and role through GoalChainer dispatch.
- [x] Add Agent Orchestrator domain records for project agents and Atomspace metadata.
- [x] Add an immutable SQLite migration and generated sqlc persistence.
- [x] Store each private agent Atomspace under the Agent Orchestrator data directory.
- [x] Serialize canonical, bounded MeTTa facts with atomic replacement and recovery.
- [x] Load the existing MeTTa file when an agent identity resumes.
- [x] Preserve agent identities and note files after sessions terminate.
- [x] Link every session attempt to one project agent and reject cross-project reuse.
- [x] Add bounded project-agent list, detail, Atomspace, and read-only note projection APIs. Keep note mutations in the typed Oh My Goals MCP.
- [x] Keep raw paths and executable MeTTa out of untrusted API requests.
- [x] Project project agents and their note summaries into the existing Agent Orchestrator UI.
- [x] Add UI navigation from a task or session to its stable agent and notes.
- [x] Add a checked demonstration covering project creation, role assignment, note persistence, session restart, and project isolation.
- [x] Add MeTTa native tests, Python tests, Go tests, migration tests, controller tests, and frontend tests.
- [x] Use MeTTaLSP diagnostics, hover, focused execution, and deduplicate on every changed MeTTa file.
- [x] Run Ruff, basedpyright, compileall, pytest, Go test/race/vet/build/lint, frontend typecheck/tests/package, generated-artifact drift checks, jscpd, and diff checks.
- [x] Review every changed line, preserve user-owned files, and create atomic local commits without pushing.

Agent Orchestrator feature commit:
`4d1e8a659b199ef586fa6462f83ff0d4f98cb60c`.
SQLite-authority validation commit:
`e459dafbab53085575840067f466d1b03196dd0a`.

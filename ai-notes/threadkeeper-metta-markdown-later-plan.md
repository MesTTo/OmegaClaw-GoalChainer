# Implemented plan: ThreadKeeper, Hence, and MeTTa Markdown orchestration

Status: implemented and verified on 2026-07-28.

The remainder of this file preserves the research-stage design. The implemented
contract is frozen in `ai-notes/threadkeeper-implementation-plan.md`. The
runtime and operator documentation is in
`docs/threadkeeper-orchestration.md`.

## Intent

Add ThreadKeeper-style governed delegation to the OmegaClaw GoalChainer stack.
Use Mettabase MeTTa Markdown as the human-readable specification language for a
thread, its goals, task graph, delegation policy, supervision policy, and audit
views.

Hence is the direct local precedent for the execution side. Its Spindle-backed
workflow combines declarative task readiness with task claims, isolated
worktrees, agent spawning, passive supervision, evaluator checks, retry, merge,
and failure propagation. The future system should preserve those useful
boundaries while keeping OmegaClaw's PeTTa directive model as the single
lifecycle authority.

The target flow is:

```text
MeTTa Markdown specification
  -> Mettabase parse and schema validation
  -> PeTTa directive, deontic, goal, and delegation facts
  -> OmegaClaw selects one ready governed task
  -> ThreadKeeper chooses local work, specialist delegation, or adjudication
  -> Hence-style supervisor runs the bounded worker
  -> evaluator records evidence and a verdict
  -> OmegaClaw completes, blocks, retries, or escalates the task
  -> Mettabase renders the board, budget, and audit views
```

## Verified source material

### ThreadKeeper

ThreadKeeper is a public fork of OmegaClaw-Core. Its `threadkeeper` branch was at
commit `a64de99e10f9f8078d25bff511b44fd71819e931` when inspected on 2026-07-28.
The repository defines four replaceable roles:

1. A persistent local control loop owns the thread, memory continuity, and the
   escalation decision.
2. A bounded local worker performs tool use and drafting.
3. On-demand specialists handle hard subproblems.
4. An optional adjudicator resolves disagreement or gates high-stakes actions.

`src/escalation.metta` owns the budget-routing policy. Python supplies spend,
ceiling, thresholds, iteration counts, and the hard-problem flag, then executes
the MeTTa verdict. Usage and escalation decisions are retained as JSON Lines
audit records.

Source: <https://github.com/hlgreenblatt/ThreadKeeper>

### Hence

The local `/home/user/Dev/hence` repository was at commit
`81b8cac24013073f9b72f8886d2538df0ee8888b` when inspected on 2026-07-28.
Relevant implementation history includes:

- `b212091`, which introduced the spawn subsystem
- `ea57621`, which made agent PTY execution non-blocking
- `3a44429`, which added the supervisor loop, liveness timers, and lease renewal
- `2332434`, which added structured NDJSON lifecycle events

Hence uses Spindle Lisp plans as a shared defeasible theory. It derives ready
tasks and assignments, then appends timestamped claims and lifecycle facts as
work progresses. Its spawn path:

1. selects and claims a ready task
2. creates a task-specific git worktree
3. assembles bounded context
4. launches the worker through a PTY
5. observes PTY and worktree activity
6. renews or revokes a time-bounded lease
7. evaluates the result separately from the worker
8. merges accepted work and records structured events

Hence separates supervisor, worker, and evaluator responsibilities. The worker
writes the worktree. The supervisor owns the claim and liveness state. The
evaluator decides whether the result satisfies the task. Its plan rules
propagate failed, stale, timed-out, and permanently failed work to downstream
tasks.

Hence already has `plan translate`, but that command asks a headless language
model to translate Markdown into SPL before parsing and checking the result.
That is useful as an authoring aid, not as an authoritative specification
compiler. The future integration must parse Mettabase's stable semantic forms
directly and reject invalid policy before any model call.

Relevant local sources:

- `/home/user/Dev/hence/README.md`
- `/home/user/Dev/hence/src/commands/spawn.rs`
- `/home/user/Dev/hence/src/container/supervisor.rs`
- `/home/user/Dev/hence/src/commands/translate.rs`
- `/home/user/Dev/hence/specs/REQ-006-supervision-b.md`

### Mettabase, zetl, and Spindle

Mettabase already supplies a MeTTa Markdown parser and authoring renderer. The
future phase must extend that implementation rather than introduce another
Markdown dialect.

`/home/user/Dev/zetl` remains useful for linked-vault ideas. It treats Markdown
as a knowledge surface, builds a theory across documents, checks syntax and
drift, and keeps proof provenance back to file and line.

`/home/user/Dev/spindle-rust` and `/home/user/Dev/spindle-racket` define the
defeasible rule vocabulary that influenced OmegaClaw's deontic and directive
layers. Hence demonstrates how that vocabulary can govern an execution loop.
The future GoalChainer integration should port the relevant semantics into
PeTTa. It should not run a Spindle board beside an OmegaClaw board.

## Authority and component boundaries

There must be one source of truth for each concern.

| Concern | Authority |
| --- | --- |
| Human-readable orchestration specification | Mettabase MeTTa Markdown |
| Parsed semantic document and source spans | Mettabase |
| Task readiness, claims, dependencies, and lifecycle conclusions | OmegaClaw `lib_directive` under PeTTa |
| Norm precedence and forbidden or required actions | OmegaClaw deontic rules under PeTTa |
| Goals, evidence, action selection, and feedback | GoalChainer and SNARS |
| Budget routing and specialist or adjudicator selection | ThreadKeeper policy evaluated under PeTTa |
| Worker process, filesystem isolation, provider call, timeout, and token meter | Host execution adapter |
| Lease, passive liveness, evaluator separation, retry, and failure protocol | Hence-derived orchestration adapter |
| Board, budget, delegation, and audit rendering | Mettabase |

ThreadKeeper should consume an already claimed directive task. It must not
maintain an independent task board. The Hence-derived adapter should report
observations and signed or attributed evidence back to the directive lifecycle.
It must not decide readiness procedurally.

## Hence compatibility map

The future design should adapt the following concepts.

| Hence concept | Future MeTTa-based equivalent |
| --- | --- |
| `plan.spl` | Versioned `thread-spec-v1` MeTTa Markdown plus a compiled directive plan |
| `plan translate spec.md` | Deterministic Mettabase parse and mostly MeTTa compilation |
| `task next` and `plan board` | `gc-directive-snapshot` and Mettabase-rendered views |
| claim, unclaim, complete, block, unblock | Existing `DirectiveSession` mutations |
| task assignment rules | PeTTa capability, norm, and delegation conclusions |
| `agent spawn` | ThreadKeeper worker or specialist execution |
| supervisor lease and passive activity checks | Host observations projected into versioned PeTTa lifecycle facts |
| stale, timeout, retry, permanent failure | Extended directive lifecycle rules and bounded host timers |
| evaluator identity and verdict | ThreadKeeper adjudicator or separate evaluator result |
| task worktree | Isolated execution workspace selected by policy |
| merge step | Evaluated, policy-gated repository integration |
| NDJSON sessions and events | Versioned audit events linked to directive and specification IDs |
| process mining | Existing directive mining plus SNARS evidence and outcome learning |
| hooks and validators | Declared task validation contracts executed before completion |

The compatibility work must include a small corpus of equivalent Hence SPL and
MeTTa Markdown plans. The tests should compare ready tasks, claims, dependency
blocking, stale recovery, retry, permanent failure, and evaluator-gated
completion. The goal is behavioral parity for the selected orchestration
semantics, not source or syntax compatibility.

## Proposed document contract

A specification document needs stable, versioned forms for:

- thread identity, title, owner, and status
- goals, required outcomes, and completion evidence
- tasks, dependencies, assignments, validators, and lifecycle policy
- control, worker, specialist, supervisor, evaluator, and adjudicator roles
- provider-neutral capability requirements
- per-thread token ceiling and escalation thresholds
- lease duration, idle timeout, wall-clock timeout, and retry limit
- delegation requests, input bounds, output contracts, and stop conditions
- deontic constraints and precedence rules
- worktree and merge policy
- evidence links, decisions, lifecycle events, and generated views

Readable headings and tables are projections. Stable MeTTa atoms are the
semantic source. Natural-language paragraphs may explain a rule, but they must
not silently become authoritative policy.

A first document could have this shape:

```metta
(md thread-spec-v1
  (h1 "Incident response thread")
  (thread
    (id incident-42)
    (owner responder)
    (budget (ceiling 120000) (soft-fraction 0.60))
    (supervision
      (lease-ttl PT30M)
      (idle-timeout PT5M)
      (wall-timeout PT60M)
      (max-retries 2))
    (roles
      (control local-control)
      (worker local-worker)
      (supervisor thread-supervisor)
      (evaluator result-evaluator)
      (specialist security-specialist)
      (adjudicator security-owner)))
  (goal restore-service required)
  (goal protect-customer-data required)
  (task collect-evidence
    (depends ())
    (accepts evidence-collected))
  (task redact-summary
    (depends (collect-evidence))
    (accepts sensitive-data-redacted))
  (task publish-update
    (depends (redact-summary))
    (accepts update-published))
  (normally escalate-security
    (and hard-security-question budget-allows)
    delegate-security-specialist))
```

The exact schema remains open. The implementation phase must check each form
against Mettabase's real Markdown AST before freezing `thread-spec-v1`.

## Compilation and execution boundary

Mettabase should parse and render the document. A mostly MeTTa compiler should
validate the semantic forms and project them into:

- OmegaClaw `lib_directive` facts and readiness rules
- OmegaClaw deontic constraints and superiority relations
- ThreadKeeper budget, capability, delegation, and adjudication facts
- GoalChainer goal, norm, evidence, and selected-action facts
- supervision, retry, and evaluator-gate facts
- Markdown board, budget, delegation, and audit views

Python should handle file permissions, descriptor-anchored locks, worktrees,
provider calls, token accounting, PTY observation, process termination, and
versioned transport. Python should not reimplement readiness, norm precedence,
escalation policy, completion policy, or failure propagation.

The plan and specification need one identity model. Every generated task, rule,
claim, attempt, evaluator result, and delegate call must retain its source
document, semantic block ID, content digest, and lifecycle version.
Re-rendering and reparsing an unchanged specification must preserve those
identities.

## Staged implementation

### 1. Pin and compare

- Recheck ThreadKeeper against the OmegaClaw Core revision selected for the
  future phase.
- Pin the Hence revision used as the orchestration reference.
- Separate ThreadKeeper changes from upstream OmegaClaw changes.
- Build the Hence SPL and MeTTa Markdown compatibility corpus.
- Freeze expected board and lifecycle results before writing adapters.

### 2. Freeze the specification

- Define `thread-spec-v1` using Mettabase's existing MeTTa Markdown AST.
- Write small valid and invalid documents before the compiler.
- Define stable IDs, imports, references, source spans, and content digests.
- Define the trust boundary for prose, links, fenced code, and imported
  documents.
- Define schema migration and rollback behavior.

### 3. Compile and reason in MeTTa

- Parse the document with Mettabase.
- Validate required forms and cross-references in MeTTa.
- Project goals and tasks into `lib_directive`.
- Project budgets and role capabilities into ThreadKeeper facts.
- Add lease, stale, timeout, retry, evaluator, and permanent-failure rules.
- Derive escalation and adjudication decisions through PeTTa.
- Emit one versioned machine record for the host.
- Differentially check the selected semantics against the Hence corpus.

### 4. Execute under governance

- Claim a directive task before local work or delegation.
- Check budget, capability, and deontic policy before specialist delegation.
- Create an isolated workspace when the task can modify a repository.
- Bound delegate turns, tools, input context, output size, and wall-clock time.
- Observe liveness without allowing the worker to renew its own lease.
- Have a separate evaluator apply the task's declared acceptance contract.
- Record usage, escalation reason, selected role, evidence, and lifecycle result.
- Complete, block, retry, or permanently fail the directive task from the
  checked result.
- Gate any repository merge on evaluator evidence and explicit merge policy.

### 5. Round-trip, audit, and learn

- Render the current board and budget into the same MeTTa Markdown document.
- Preserve user-authored semantic blocks while updating generated views.
- Detect stale generated views and semantic drift.
- Keep the exact append-only lifecycle, lease, evaluation, and delegation log.
- Feed checked outcomes into directive process mining and SNARS feedback.

### 6. Demonstrate the contribution

The demo should begin with one specification document and show:

1. The initial task board, supervision policy, and budget.
2. A cheap local task that does not delegate.
3. A hard subproblem that passes the MeTTa escalation gate.
4. A specialist running in an isolated workspace under a bounded lease.
5. An evaluator accepting the result and unlocking a dependent task.
6. A stale or timed-out attempt that is reclaimed and retried.
7. A failed prerequisite that propagates to the downstream board.
8. An optional disagreement that invokes adjudication.
9. The updated Markdown board and exact audit trail.
10. A rejected delegation after the budget ceiling.

Each displayed result must come from the actual PeTTa, ThreadKeeper, and
supervision path used by the implementation.

## Acceptance contract

- PeTTa is authoritative. MeTTa LSP findings are advisory until reproduced.
- One directive lifecycle exists. Spindle and PeTTa must not maintain competing
  task boards.
- The specification round-trips without changing semantic identity.
- Invalid references, duplicate IDs, cycles, unsafe imports, and schema-version
  mismatches fail before a provider call.
- OmegaClaw remains the lifecycle authority.
- ThreadKeeper remains the control, delegation, and budget-routing layer.
- The Hence-derived adapter owns execution supervision, not policy truth.
- Mettabase remains the Markdown parser and renderer.
- A worker cannot complete its own task or renew its own lease.
- An evaluator cannot extend a lease or bypass the merge policy.
- Every delegate call has a bounded contract and an audit record.
- Stale claims expire safely if the supervisor exits.
- Retry rules defeat prior stale or timeout conclusions without leaving an
  ambiguous task state.
- Failure propagation covers direct and transitive dependents.
- Repository integration is isolated, evaluated, and policy-gated.
- Policy parity tests compare any host fallback with the MeTTa verdict across
  every branch.
- Generated-input tests cover parser, lifecycle, escalation, supervision, and
  round-trip invariants.
- The demo proves that editing the specification changes the derived plan,
  supervision policy, and routing decision.

## Non-goals

- Do not embed Hence or Spindle as a second runtime lifecycle authority.
- Do not treat model-generated Markdown translation as executable policy.
- Do not let Python duplicate PeTTa readiness or deontic rules.
- Do not grant a worker permission to certify its own result.
- Do not merge agent work automatically without the declared evaluation and
  repository policy.
- Do not claim multilingual orchestration until stable task meanings survive
  translation and are checked under PeTTa.

## Deferred questions

- Whether the specification is one document per thread or a linked vault.
- Whether imported documents follow zetl-style wikilinks, explicit MeTTa
  imports, or both.
- Whether adjudication is a directive task, a separate norm gate, or both.
- Which facts an agent may propose and which require human approval.
- How a changed budget or policy applies to a thread already in progress.
- Whether leases are represented directly in PeTTa time forms or compiled into
  versioned active and expired facts at the host boundary.
- Which Hence validators and hook semantics should become declared task
  acceptance contracts.

# ThreadKeeper and Hence orchestration implementation plan

Status: implemented and verified on 2026-07-28.

The shipped implementation is commit `1456256`. The nested OmegaClaw fixes are
`c98a2c6` in OmegaClaw Core and `02d019e` in omegaclaw-deontic. Core commit
`feed652` also merges the current fork head `a5d1599`.

## Frozen behavior contract

The implementation extends the current durable OmegaClaw directive layer. It
does not create a second task board.

One MeTTa Markdown document contains versioned semantic facts in `metta` code
fences. Mettabase parses those fences and normalizes every fact. PeTTa validates
the schema, derives routing policy, and compiles the task graph. Python handles
files, locks, clocks, subprocesses, token counters, and git worktrees.

The implementation is complete when it supports:

1. deterministic MeTTa Markdown parsing through Mettabase
2. schema validation before plan creation or worker execution
3. stable semantic digests and source locations
4. compilation into OmegaClaw `lib_directive`
5. local-worker, specialist, and adjudicator routing through PeTTa
6. budget accounting and fail-closed escalation
7. task claims, attempt versions, leases, idle timeout, and wall timeout
8. separate worker, supervisor, and evaluator identities
9. evaluator-gated completion
10. retry and permanent failure with downstream propagation
11. optional isolated git worktrees and policy-gated integration branches
12. append-only structured audit events
13. Mettabase-rendered board, budget, attempts, and audit views
14. CLI and OmegaClaw skill dispatch
15. an executable demo covering local work, specialist routing, evaluation,
    retry, failure propagation, adjudication, and budget denial

## Specification format

The document uses one semantic fact per line inside a `metta` fence. Mettabase
already parses this form as quoted, non-executable actions.

```markdown
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
(thread-task incident-42 collect-evidence local evidence-collected normal)
(thread-task incident-42 redact-summary specialist summary-redacted high)
(thread-task incident-42 publish-update local update-published normal)
(thread-depends incident-42 redact-summary collect-evidence)
(thread-depends incident-42 publish-update redact-summary)
(thread-merge-policy incident-42 none)
```
```

Prose, headings, and non-MeTTa fences are explanatory. Only the recognized
semantic facts are executable policy. Evaluation forms beginning with `!` are
rejected.

## Runtime ownership

| Concern | Owner |
| --- | --- |
| Markdown parsing and rendering | Mettabase |
| Schema, routing, retry, and evaluator policy | PeTTa |
| Task readiness and lifecycle | OmegaClaw `lib_directive` |
| Goals, evidence, and outcomes | GoalChainer and SNARS |
| Process and filesystem observations | Python host adapter |
| Delegate selection and budget gate | ThreadKeeper policy under PeTTa |
| Claim, lease, evaluation, retry, and merge protocol | Hence-derived adapter |

## Implementation slices

### Slice A: schema and compilation

- Add immutable thread specification models.
- Load the pinned Mettabase Markdown parser.
- Extract only normalized, quoted MeTTa data facts.
- Record exact fact source lines and a semantic SHA-256 digest.
- Add a versioned MeTTa compile protocol.
- Validate required singleton facts, symbols, numbers, roles, task references,
  duplicate IDs, and unsupported facts.
- Compile tasks, dependencies, assignments, metadata, and failure rules into a
  temporary directive plan.
- Run OmegaClaw validation and cycle analysis before creating the durable plan.

### Slice B: policy and audit

- Port ThreadKeeper's escalation policy into the versioned MeTTa adapter.
- Add role routing, adjudication, and retry outcome policy.
- Keep PeTTa mandatory for every policy decision. Do not add a Python fallback.
- Add a locked mode-0600 JSON Lines audit store with per-event hash chaining.
- Record usage, route, claim, attempt, liveness, evaluation, lifecycle, and
  integration events.

### Slice C: supervised execution

- Add a bounded subprocess worker.
- Observe output and workspace modification time without worker heartbeats.
- Enforce lease renewal, idle timeout, wall timeout, output cap, and termination.
- Keep worker, supervisor, and evaluator identities distinct.
- Run a separate evaluator command or callable.
- Apply the MeTTa outcome verdict to complete, retry, or block the directive.
- Exhausted retries become a permanent failure and block downstream work.

### Slice D: isolated repository execution

- Add an optional git worktree for a task attempt.
- Use explicit branch and workspace paths derived from validated identifiers.
- Evaluate before integration.
- Support `none` and isolated integration-branch policies.
- Never update the caller's checked-out branch.
- Retain failed workspaces when requested and remove successful temporary
  workspaces safely.

### Slice E: surfaces and demonstrations

- Add `goalchainer thread` CLI commands.
- Add `goalchainer-thread-dispatch` to the OmegaClaw skill.
- Render a Mettabase Markdown status document.
- Add a live demo with checked assertions for every claimed capability.
- Document the earlier and current capability boundary.

## Verification

- Unit tests for models, parser, compiler, protocol, audit, routing, supervision,
  evaluation, retry, and git integration.
- Hypothesis tests for identifiers, facts, dependency graphs, budget boundaries,
  event chains, and malformed documents.
- Live PeTTa tests for compilation, routing, evaluator policy, retry, and the
  final demo.
- Mettabase parser and render round-trip tests.
- Existing GoalChainer, OmegaClaw deontic, and directive suites.
- Ruff, compileall, `git diff --check`, and jscpd with zero new clones.

Final results:

- GoalChainer: 292 passed, 3 environment-dependent skips
- OmegaClaw Core directive suite: 36 assertions passed
- omegaclaw-deontic directive suite: 36 assertions passed
- targeted Ruff: passed
- strict basedpyright over the new typed boundary: zero errors
- jscpd: zero clones and zero duplicated lines
- fresh PeTTa demo: all 11 asserted capabilities passed

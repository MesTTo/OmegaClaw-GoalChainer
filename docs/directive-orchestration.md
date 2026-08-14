# Directive orchestration

GoalChainer now uses OmegaClaw's directive system as the execution ledger for a
decision. PeTTa evaluates the MeTTa rules. Python keeps the file and process
boundary safe.

## What changed

| Capability | Earlier bridge | Current bridge |
| --- | --- | --- |
| Plan lifetime | Temporary only | Temporary by default, durable when a path is supplied |
| Task graph | Flat incident actions | Review gate and explicit task dependencies |
| Lifecycle | Claim only | Claim, unclaim, complete, block, and unblock |
| Failure handling | Executor ran outside the plan | Claim before execution, then complete or block |
| Views | Status and next action | Snapshot, status, next, board, summary, info, assignments, task-state |
| Checks | None exposed | Validation, trace, cycle analysis, and consistency |
| OmegaClaw skill | Directive bridge was not advertised | Natural-language creation and typed JSON dispatch |
| Audit | Parsed console fragments | Versioned S-expression records, file digests, transcript, and MeTTa Markdown |
| Dependency failure | Documented cascade was missing | Direct and transitive `upstream-blocked` rules are generated and tested |

## Live demo

Run the demo through the installed CLI:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli directive demo
```

The verified output is:

```text
initial            collect_evidence=ready summarize_findings=backlog publish_update=backlog
blocked-root       collect_evidence=blocked summarize_findings=upstream-blocked publish_update=upstream-blocked
unblocked-root     collect_evidence=ready summarize_findings=backlog publish_update=backlog
claimed-root       collect_evidence=in-progress summarize_findings=backlog publish_update=backlog
completed-root     collect_evidence=done summarize_findings=ready publish_update=backlog
claimed-summary    collect_evidence=done summarize_findings=in-progress publish_update=backlog
completed-summary  collect_evidence=done summarize_findings=done publish_update=ready
claimed-publish    collect_evidence=done summarize_findings=done publish_update=in-progress
completed-plan     collect_evidence=done summarize_findings=done publish_update=done
```

The command raises an error if any of these checks fail:

- The root task is directly blocked.
- Both dependents become `upstream-blocked`.
- Unblocking clears the cascade.
- Completing each dependency unlocks the next task.
- Every task reaches `done`.

Run the decision and real leak-checked executor under the same lifecycle:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli solve \
  --plan ./native-solve.metta \
  --json
```

The verified native run on 2026-07-28 returned:

```text
mode: native
native_snars_ran: True
decided: publish_redacted_summary
safe: True
outcome: completed
done: [publish_redacted_summary, review_decision]
blocked: [publish_raw_log]
```

SNARS made the decision before the selected action was claimed. The executor
produced the redacted artifact while the SNARS session remained open. The
directive lifecycle then completed the selected task, and SNARS recorded the
safe outcome as feedback.

Retain the plan and lifecycle log by supplying a new `.metta` path:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli directive demo \
  --plan ./demo-plan.metta \
  --json
```

GoalChainer refuses to replace an existing plan. A new durable plan is created
with mode `0600`.

## Work with a durable plan

Create an incident plan without claiming the selected action:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli directive \
  --plan ./incident.metta \
  --no-claim \
  --json
```

Inspect and mutate it:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli directive board \
  --plan ./incident.metta
PYTHONPATH=src python3 -m goal_chainer.cli directive claim \
  --plan ./incident.metta \
  --task publish_redacted_summary \
  --agent responder
PYTHONPATH=src python3 -m goal_chainer.cli directive complete \
  --plan ./incident.metta \
  --task publish_redacted_summary \
  --agent responder
PYTHONPATH=src python3 -m goal_chainer.cli directive markdown \
  --plan ./incident.metta
```

`markdown` calls Mettabase's existing `md-author-markdown` implementation. The
report contains board, assignment, and summary tables followed by the exact MeTTa
plan and lifecycle claims.

## OmegaClaw dispatch

The MeTTa skill exposes a two-part `py-call` for PeTTa:

```metta
(goalchainer-directive "incident request")
(goalchainer-directive-dispatch
  "{\"operation\":\"board\",\"plan\":\"/absolute/path/incident.metta\"}")
(goalchainer-directive-dispatch
  "{\"operation\":\"claim\",\"plan\":\"/absolute/path/incident.metta\",\"task\":\"publish_redacted_summary\",\"agent\":\"responder\"}")
(goalchainer-directive-dispatch
  "{\"operation\":\"demo\"}")
```

The dispatcher validates the operation, plan path type, task and agent symbols,
and boolean flags before evaluation. Unknown operations and malformed JSON
return the same structured GoalChainer error family as the SNARS dispatcher.

## Runtime revisions

`external/OmegaClaw-Core` is a stock upstream checkout pinned at `2cdef05`, past
`v0.1.18`, with no fork commits. `lib_directive` reaches it as a plugin:
`scripts/setup-omegaclaw.sh` installs the deontic stack from
`external/omegaclaw-deontic` (pinned at `1e78026`) into `plugins/deontic`, which
registers its own directory as the PeTTa library path `deontic`. PeTTa is pinned
at `main` (`43705f5`) and runs on SWI-Prolog 9.3.33.

The MeTTa LSP cannot resolve PeTTa's `library` imports and reports the imported
directive names as advisory unknown-symbol findings. The adapter, the lifecycle
tests, and this demo execute on PeTTa. Those executions are the acceptance
evidence.

## ASP and multilingual follow-on work

OmegaClaw remains the authority for task state. A Clingo layer can later optimize
resource assignments or schedules over an exported snapshot. It should not
derive a second lifecycle board. CalDar's grounded-once, full-assumption,
multi-shot pattern is the reference for that optional layer.

MeTTaLingo can later project stable task meanings into controlled natural
languages. MeTTaSpeak's EPILOG work belongs behind a TypeScript protocol until
its MeTTaScript semantics have a verified PeTTa equivalent. Neither capability
is claimed by the current demo.

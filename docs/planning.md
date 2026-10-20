<!-- Purpose: show how GoalChainer derives a plan from a caller's goal, attributed observations, declared capabilities and the outcomes of earlier attempts through the public request command, how changing each changes the answer, and which evidence the caller must keep current. -->
<!-- am[implements a-dd-doc-1018@da16cf] -->
# Plans from goals, evidence and capabilities

`goalchainer request` plans for a goal you give it. The answer is derived from four inputs:

- the goal, a list of literals the plan must make true;
- the attributed observations: signal readings in `context.readings`, each naming its source and how
  it was estimated, and statement rows in `rows`, each naming the observation it came from;
- the capabilities the domain and its procedure library declare: the actions, the procedures that
  bring literals about, and the investigators that can observe a literal;
- the outcomes of earlier attempts: the host's journal of what it ran and the receipts reporting
  what each attempt achieved.

No input lists the steps. The planner composes them from the procedures, so a different goal, a
different observation or a different library gives a different answer. That answer is a plan, an
inquiry asking an investigator to observe something first, or no plan with the reason.

Every command here runs from the repository root, offline: no request reads text, so no model is
asked. `goalchainer show` prints a readable account of a saved result. It evaluates nothing, and
every line it prints is read off the result. `...` below stands for digests, inference counts and
review details that this guide does not depend on.

## Plan the example

The [task-control example](../examples/planning/task-control.request.json) observes that a task
holds a contended resource, belongs with another owner, and that the receiving owner has accepted
the handoff. The checkpoint audit found no way to preserve the task's state. Its goal is that the
contention ends:

```console
$ goalchainer request --input examples/planning/task-control.request.json --inference-budget 1000000000 --timeout-seconds 600 > plan.json
$ goalchainer show --input plan.json
relevance review handoff-42 of chemistry-calibration (task-control-v1, sha256:...)
disposition: escalate
...
plan: 3 steps, not yet established
  1. start release-by-handoff, application 0, on task
  2. act release-by-handoff hand, application 0, on seat, receiving_seat, task
  3. finish release-by-handoff, application 0, on task
request: authorization unresolved, applies effects no, ... inferences
```

The account opens with the request's review, worded as `goalchainer relevance review` words it.
The review and the plan are separate findings from the same evidence. The review answers which one
lifecycle action to propose now, and here it escalates because its ranking is not decisive. The plan
answers how to reach the goal you gave. The library's only way to end the contention that this
evidence allows is `release-by-handoff`. Its `accept` step needs the receiving owner's acceptance,
which is already observed, so the plan starts that procedure, hands the task from its seat to the
receiving seat, and finishes. The plan is "not yet established" because no track record says the
procedure works.

## Admit a returned step

A plan is a scheduling answer. Before the host runs a step, it asks whether that step may run now,
on the evidence it holds then. It passes the step back exactly as the plan returned it:

```console
$ python3 -c 'import json; r = json.load(open("examples/planning/task-control.request.json")); p = json.load(open("plan.json")); del r["goal"]; r.update(operation="admit", step=p["planning"]["steps"][0], instance_id=None); json.dump(r, open("admit-start.json", "w"))'
$ goalchainer request --input admit-start.json --inference-budget 1000000000 --timeout-seconds 600 | goalchainer show
relevance review handoff-42 of chemistry-calibration (task-control-v1, sha256:...)
...
admission: admitted, occurrence (Occurrence (Step ... "release-by-handoff" Start) ...
request: authorization unresolved, applies effects no, ... inferences
```

Once the host has started the application, its journal says so, and the act step is admitted on
that instance:

```console
$ python3 -c 'import json; r = json.load(open("admit-start.json")); p = json.load(open("plan.json")); act = next(s for s in p["planning"]["steps"] if s["kind"] == "act"); r.update(step=act, instance_id="handoff-1", journal=[{"@type": "Started", "instance_id": "handoff-1", "procedure": act["procedure"], "journal": "host-journal:1"}]); json.dump(r, open("admit-act.json", "w"))'
$ goalchainer request --input admit-act.json --inference-budget 1000000000 --timeout-seconds 600 | goalchainer show
relevance review handoff-42 of chemistry-calibration (task-control-v1, sha256:...)
...
admission: admitted, occurrence (Occurrence (Step ... "release-by-handoff" "hand") ...
request: authorization unresolved, applies effects no, ... inferences
```

If the owner registry now reports that the task's owner is right after all, the same step is
blocked, naming the literal the evidence no longer establishes:

```console
$ python3 -c 'import json; r = json.load(open("admit-act.json")); [x.update(state="refuted") for x in r["context"]["readings"] if x["signal"] == "owner_mismatch"]; json.dump(r, open("admit-act-owner-right.json", "w"))'
$ goalchainer request --input admit-act-owner-right.json --inference-budget 1000000000 --timeout-seconds 600 | goalchainer show
relevance review handoff-42 of chemistry-calibration (task-control-v1, sha256:...)
...
admission: blocked, waiting on (Signal owner_mismatch)
request: authorization unresolved, applies effects no, ... inferences
```

## Change the evidence

Each file below is the example with the observations its name gives.

The receiving owner declines the handoff. The plan now asks the receiving owner first, by
escalating, and hands the task over once that owner accepts:

```console
$ goalchainer request --input examples/planning/task-control-declined.request.json --inference-budget 1000000000 --timeout-seconds 600 | goalchainer show
relevance review handoff-42 of chemistry-calibration (task-control-v1, sha256:...)
...
plan: 6 steps, not yet established
  1. start release-by-handoff, application 0, on task
  2. start ask-receiving-owner, application 1, on task
  3. act ask-receiving-owner ask, application 1, on task
  4. finish ask-receiving-owner, application 1, on receiving_seat
  5. act release-by-handoff hand, application 0, on seat, receiving_seat, task
  6. finish release-by-handoff, application 0, on task
request: authorization unresolved, applies effects no, ... inferences
```

Nobody has checked whether the task belongs with another owner. The planner asks the owner
registry, which can observe that, and gives the answer for each outcome:

```console
$ goalchainer request --input examples/planning/task-control-owner-unknown.request.json --inference-budget 1000000000 --timeout-seconds 600 | goalchainer show
relevance review handoff-42 of chemistry-calibration (task-control-v1, sha256:...)
...
inquiry: owner-registry can observe (Signal owner_mismatch)
  if it holds:
    plan: 3 steps, not yet established
      1. start release-by-handoff, application 0, on task
      2. act release-by-handoff hand, application 0, on seat, receiving_seat, task
      3. finish release-by-handoff, application 0, on task
  if it does not:
    no plan
      (Not (Signal resource_contention)): blocked
request: authorization unresolved, applies effects no, ... inferences
```

The task can preserve its state and has reached a safe point, and its owner is right. Pausing
would release the resource, but it rests on the checkpoint store restoring task state, which only
a restore drill establishes, so the planner asks for the drill:

```console
$ goalchainer request --input examples/planning/task-control-checkpoint.request.json --inference-budget 1000000000 --timeout-seconds 600 | goalchainer show
relevance review handoff-42 of chemistry-calibration (task-control-v1, sha256:...)
disposition: propose pause_recoverably (obligated, decided at deterministic lifecycle)
...
inquiry: restore-drill can observe (Statement (sn p so "restores" ((arg s (sn c "checkpoint-store")) (arg o (sn c "task-state")))))
  if it holds:
    plan: 3 steps, not yet established
      1. start release-by-pause, application 0, on task, checkpoint
      2. act release-by-pause pause, application 0, on task, checkpoint
      3. finish release-by-pause, application 0, on task
  if it does not:
    no plan
      (Not (Signal resource_contention)): blocked
request: authorization unresolved, applies effects no, ... inferences
```

<!-- am[implements a-dd-drill-row-variation-1018@0861dc] -->
The drill's result is statement evidence, which a request carries as a row naming the statement as
the procedure library spells it. With the drill's row added, the answer is the inquiry's branch
where the statement holds:

```console
$ goalchainer request --input examples/planning/task-control-checkpoint-drilled.request.json --inference-budget 1000000000 --timeout-seconds 600 | goalchainer show
relevance review handoff-42 of chemistry-calibration (task-control-v1, sha256:...)
disposition: propose pause_recoverably (obligated, decided at deterministic lifecycle)
...
plan: 3 steps, not yet established
  1. start release-by-pause, application 0, on task, checkpoint
  2. act release-by-pause pause, application 0, on task, checkpoint
  3. finish release-by-pause, application 0, on task
request: authorization unresolved, applies effects no, ... inferences
```

## Change the capabilities

This host can pause and probe, but it has no way to hand work to another owner: its
[procedure library](../examples/planning/task-control-pause-only.procedures.metta) declares only
the pause route. With the example's evidence, nothing it can do ends the contention:

```console
$ goalchainer request --input examples/planning/task-control-pause-only.request.json --inference-budget 1000000000 --timeout-seconds 600 | goalchainer show
relevance review handoff-42 of chemistry-calibration (task-control-v1, sha256:...)
...
no plan
  (Not (Signal resource_contention)): blocked
request: authorization unresolved, applies effects no, ... inferences
```

The review is the same as the example's, since the review never reads a procedure library. Only
the plan changed.

## Change the goal

The same domain and library, asked to reach a safe point instead:

```console
$ goalchainer request --input examples/planning/task-control-safe-point.request.json --inference-budget 1000000000 --timeout-seconds 600 | goalchainer show
relevance review handoff-42 of chemistry-calibration (task-control-v1, sha256:...)
...
plan: 3 steps, not yet established
  1. start reach-safe-point, application 0, on task
  2. act reach-safe-point run, application 0, on task
  3. finish reach-safe-point, application 0, on task
request: authorization unresolved, applies effects no, ... inferences
```

<!-- am[implements a-dd-receipt-variation-1018@655fcb] -->
## Revise a plan from verified outcomes

With both routes open, the planner has two ways to end the contention. The task can preserve its
state, it is at a safe point and the restore drill passed, so it can pause. It also belongs with
another owner who accepts it, so it can be handed over. Neither procedure has a track record and
each takes one action, so the planner takes the one its library declares first, the pause route:

```console
$ goalchainer request --input examples/planning/task-control-both-routes.request.json --inference-budget 1000000000 --timeout-seconds 600 | goalchainer show
relevance review handoff-42 of chemistry-calibration (task-control-v1, sha256:...)
disposition: propose pause_recoverably (obligated, decided at deterministic lifecycle)
...
plan: 3 steps, not yet established
  1. start release-by-pause, application 0, on task, checkpoint
  2. act release-by-pause pause, application 0, on task, checkpoint
  3. finish release-by-pause, application 0, on task
request: authorization unresolved, applies effects no, ... inferences
```

The host has handed this task's kind of work over three times before. Its journal records each
attempt and its receipts confirm that the contention ended each time. A
[procedure library](../examples/planning/task-control-proven.procedures.metta) that declares a
promotion rule turns those receipts into a track record for `release-by-handoff`. The planner
prefers the plan with fewer applications of procedures that lack a track record, so on the same
evidence it now chooses the handoff, and the plan is established:

```console
$ goalchainer request --input examples/planning/task-control-both-routes-proven.request.json --inference-budget 1000000000 --timeout-seconds 600 | goalchainer show
relevance review handoff-42 of chemistry-calibration (task-control-v1, sha256:...)
disposition: propose pause_recoverably (obligated, decided at deterministic lifecycle)
...
plan: 3 steps, established
  1. start release-by-handoff, application 0, on task
  2. act release-by-handoff hand, application 0, on seat, receiving_seat, task
  3. finish release-by-handoff, application 0, on task
request: authorization unresolved, applies effects no, ... inferences
```

The review is the same as before apart from its inference count, so it still proposes pausing. The
review and the plan answer different questions, and neither decides for the host. An established
plan has a track record, and it authorizes nothing: the result still says `authorization
unresolved`.

## Plan in your own domain

Nothing in the planner knows task-control's names. A caller can supply its own domain and library.
The [bench-booking domain](../examples/planning/bench-booking.metta) has its own signals, actions
and one-entity world, and its [library](../examples/planning/bench-booking.procedures.metta)
declares how a blocked bench can be freed. While nobody knows whether a spare bench is free, the
planner asks the booking calendar:

```console
$ goalchainer request --input examples/planning/bench-booking.request.json --inference-budget 1000000000 --timeout-seconds 600 | goalchainer show
relevance review bench-7 of spectrometer-run (bench-v1, sha256:...)
disposition: propose rebook (permitted, decided at deontic admissibility)
...
inquiry: bench-calendar can observe (Signal spare_bench_free)
  if it holds:
    plan: 6 steps, not yet established
      1. start free-the-bench, application 0, on bench
      2. start get-confirmation, application 1, on bench
      3. act get-confirmation ask, application 1, on bench
      4. finish get-confirmation, application 1, on bench
      5. act free-the-bench move, application 0, on bench
      6. finish free-the-bench, application 0, on bench
  if it does not:
    no plan
      (Not (Signal bench_blocked)): blocked
request: authorization unresolved, applies effects no, ... inferences
```

Once the coordinator reports a spare bench free, the answer is that branch's plan:

```console
$ goalchainer request --input examples/planning/bench-booking-spare-free.request.json --inference-budget 1000000000 --timeout-seconds 600 | goalchainer show
relevance review bench-7 of spectrometer-run (bench-v1, sha256:...)
...
plan: 6 steps, not yet established
  1. start free-the-bench, application 0, on bench
  2. start get-confirmation, application 1, on bench
  3. act get-confirmation ask, application 1, on bench
  4. finish get-confirmation, application 1, on bench
  5. act free-the-bench move, application 0, on bench
  6. finish free-the-bench, application 0, on bench
request: authorization unresolved, applies effects no, ... inferences
```

<!-- am[implements a-jk-pc-currentness-boundary-1019@542623] am[rests-on c-jk-pc-request-path-currentness-1019@7f56d8] am[rests-on c-integrate-c1-currentness-boundary-1019@4ebdc2] -->
## Keep the evidence current

The planner takes every reading a request supplies as holding at the request's time, while the
reading is valid. It refuses a reading observed after that time, and it reads one past its
`valid_until` as unknown. Neither check tells whether an act in your journal has changed what a
reading saw. A reading taken before an act ran describes the world before that act. So once a
receipt reports an act applied, refresh each reading of what the act may have changed before you
plan or admit again, or leave that reading out. What the act may have changed includes what its
procedure's Finish writes once the act is done, and what any Derive writes in turn.
A plan's own Finish and Derive steps are such changes: every world takes one as soon as it is enabled.
So before you ask to admit one, leave out the readings of what it writes, and read them again once it
is taken.

A reading describes the world once everything that follows by itself has happened: every procedure
whose needed steps have all run has finished, and every Derive whose reads hold has written its
literals. When the readings leave open whether a started procedure has finished, because some world
they allow finished it and another did not, the planner treats it as uncertain. No plan then relies
on its finish or on what its finish writes.

When no world can settle to every reading a request supplies, the planner refuses the request with
`Contradicted`, naming the readings. In task-control, `reach-safe-point` finishes as soon as its
`run` act is done, and its Finish makes the safe point reachable. Suppose a reading says the safe
point is unreachable, was taken before `run` ran, and is supplied after `run`'s receipt. It then
contradicts every world, so the planner refuses the request. That refusal only checks that the
evidence you supplied is consistent. It is not a stale-reading detector. A reading an act made
stale that some world still agrees with is taken as current, and a plan may rest on it.

## What an answer is not

A plan, an inquiry and an admission are what the model finds. None authorizes anything or applies
an effect: every result says `authorization unresolved` and `applies effects no`. The host decides
whether to act. It records what it started in its journal and what happened in receipts, and the
next request reads them as evidence.

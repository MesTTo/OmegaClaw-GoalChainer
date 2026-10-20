<!-- Purpose: explain the relevance review's inputs, policy, records, freshness, receipts and host boundary. -->
<!-- am[implements a-v2-docs-1019@6301a6] -->
# Relevance review

A relevance review asks which lifecycle intervention, if any, a persistent agent should propose
for one task it is working on: continue, pause recoverably, stop as stale, replan, hand off,
escalate and the rest of the twelve verdicts of the goal relevance governor paper
(Goertzel, `goal_relevance_governor_v3.pdf`, section 7.2). It follows the paper's outer
contract (section 7.7):

```text
committed state -> bounded review -> typed proposal -> policy gate -> receipt
```

GoalChainer owns the bounded review and the typed proposal. The review never applies an effect,
never grants authority and never certifies a goal. The policy gate, the executor and the
verifier belong to the host. Every review record says `"applies_effects": false`.
[`docs/architecture.md`](architecture.md) states the project's purpose and the contract between
policy, host and models; this page is the relevance review's runbook.

The review's policy is MeTTa, the files under `src/goal_chainer/relevance/policy/`, run
in-process on PyMeTTa, which installs with the package. The domain's theory runs in the same
engine on `lib_deontic`, which ships with the package in `src/goal_chainer/deontic_library/`
(adopted from omegaclaw-deontic; its `PROVENANCE.md` says from where). If PyMeTTa or that
library cannot load, a review fails with the error code `runtime-unavailable`; nothing falls
back to a weaker reasoner.

## Run a review

The packaged task-control domain describes the governor's own decision problem. The example
packet is the paper's section 14.2 case: a checkpointed research task holds a shared runtime
that an urgent recovery task is waiting for.

```console
$ goalchainer relevance review --packet examples/relevance/chemistry-contention.packet.json
relevance review rr-42 of chemistry-calibration (task-control-v1, sha256:...)
disposition: propose pause_recoverably (obligated, decided at deterministic lifecycle)
  action authority ceiling preauthorized; licensed ceiling advisory; authorization unresolved
    lowered by effect:irreversibility [model-proposed] to advisory
    lowered by effect:option-value [model-proposed] to advisory
  carrying path: least_commitment (priority 0.7 from policy:planning-doctrine) strongly-positive
  deontic admissibility: nothing removed
  deterministic lifecycle: continue_task (an obligation is in force: pause_recoverably); escalate (an obligation is in force: pause_recoverably)
  Pareto elimination: nothing removed
  motivational reconciliation: nothing removed
  tie-breaking projection: nothing removed
  unknown and decision-relevant: assumption_invalidated, authorized_resource_named, cost_variance_material, ethics_consilience_broken, governance_overhead_named, judgment_exceeds_evaluator, no_safe_step, owner_mismatch, scope_exceeds_stage, simpler_route_available, sunk_cost_argument
  no estimate anywhere for: expected-goal-delta, contribution-belief, contribution-confidence, urgency, hazard-severity
  engine inferences: ... of 20000000
  applies effects: no
```

The resource contention and the reachable safe point make the theory oblige the pause, so the
duty decides the review before any preference is weighed. The pause may be applied at most at
the `preauthorized` rung, but two of its predicted effects are model-proposed estimates, so the
evidence licenses only an `advisory` proposal. Whether anyone authorizes it is the host's
decision, so the record says `unresolved`.

`--json` prints the whole review record instead. `--domain-file PATH` reviews against another
domain file; `--domain NAME` picks a packaged one.

## The packet

A packet is the bounded slice of signal evidence a review reads (section 8.5).
For a domain declaring needs, the caller also supplies a motivation snapshot;
the [domain request](motivation.md#review-the-stream) can read it from a named stream.
The policy decides from these inputs, not a live clock or wider system.

| Field | Meaning |
| --- | --- |
| `protocol` | `goalchainer-relevance-packet-v1`. |
| `review_id`, `trigger` | Labels for the record. They do not affect the decision. |
| `subject` | The task or plan under review. It is part of the fingerprint. |
| `as_of` | The time every reading is judged at, with a timezone offset. |
| `authority` | The authority rung the review itself runs at, one of the domain's tiers. |
| `budget` | `inferences` and `timeout_seconds`. Both are required: how much one review may cost is the caller's decision (section 10.5). `inferences` is a positive whole number of any size, and `timeout_seconds` a positive number with a finite float, so an integer beyond the float range is an invalid packet. |
| `policy_version` | Optional. When present it must equal the domain's policy version. |
| `readings` | Explicit signal readings. |

The relevance commands read a packet, a review or a receipt as UTF-8 JSON, from a file or, given
`-`, from standard input, whatever the process's locale: bytes that are not UTF-8 make an invalid
packet or an invalid record.

A reading is `{signal, state, estimator, source, note, observed_at, valid_until}`. The state is
`detected`, `refuted` or `unknown`, and the three stay different: a refuted reading becomes the
fact `(given (not (signal X)))`, while an unknown reading becomes no fact at all. A detected or
refuted reading needs the estimator class that produced it: `measured`, `deterministic`,
`receipt-calibrated`, `model-proposed` or `human-asserted`.

At `as_of` a reading past its `valid_until` decays to unknown, never to refuted. Of a valid
detected and a valid refuted reading of the same signal, the one whose estimator class has the
higher tier is preferred: `measured`, `deterministic` and `human-asserted` rank above
`receipt-calibrated` and `model-proposed`. The preference is adopted, not a proof that the
preferred reading is true. So the signal takes the preferred state and its fact, while the
overruled reading is listed as contested and escalates the review when the signal can affect it,
and the authority ceilings still read only the supporting readings' classes. Two valid contrary
readings of one tier leave the signal `conflicted`, which emits no fact and escalates the same
way. An expired contrary is no disagreement, and once the preferred reading expires its contrary
stands alone. The justification kernel labels the readings (`planning/justification.metta`), and
the evidence policy reads the review's beliefs off its labels. There are no text cues: a phrase
missing from a request is not evidence that a condition is absent.

## How a review decides

One bounded run of `lib_deontic` derives everything conditional: which actions are candidates,
what each is permitted, obliged or forbidden to be, what it contributes to each goal, its typed
effects, which goals the review must serve, and any unresolved deontic dilemma. The ranking
then follows section 9.3:

1. **Deontic admissibility.** A candidate stays only when the theory permits it and neither
   forbids it nor leaves a duty about it in a dilemma. A defeater that withdraws a permission
   therefore removes the action.
2. **Deterministic lifecycle.** When any admissible action is obliged, only obliged actions
   stay. An action that pushes a required goal backwards leaves.
3. **Pareto elimination.** An action leaves when another is at least as good on every goal and
   dimension either of them claims and better on one. An unestimated effect spans the whole
   scale, so it can never make an action look worse than it is.
4. **Motivational reconciliation.** An action leaves when another is preferred by both the
   local motive (individual goals) and the hive motive (collective goals) under both
   aggregation rules. A remaining split stays visible as `motive_tension`.
5. **Tie-breaking projection.** One survivor is selected only when its lead over every rival
   survives the unknown and conflicting effects, under both sum-over-paths and
   max-over-parents aggregation (section 9.5). Each rule is declared once in `ranking.metta`
   as a fold of an action's signed goal-path values: sum-over-paths adds them from 0.0, and
   max-over-parents keeps the largest, starting from the first value so that a negative
   maximum such as -0.2 stays -0.2. These are the combine operations of pymetta's `bag` and
   `ranked` carriers, which a test checks the folds against. An action with no path is worth 0
   under both by the review's convention; neither carrier answers for it.

<!-- am[related a-v2m-drive-paths-1019@65a7d5] am[related a-v2m-hold-1019@be4f47] am[related a-v2m-need-authority-1019@52deb8] -->
In a domain that declares needs, the review ranks by a motivation snapshot of the host's stream at
`as_of`, which `motivation.metta` derives from the stream's need observations and host attempts. A
goal a need regulates is valued through that need: its path is the goal's priority times the
action's reduction of the need's urgency, an interval wherever the need's level or the action's
change is unknown, where every other path is a point. Steps 1 and 2 read no value, so no need
admits a forbidden action, cancels a duty or excuses harm to a required goal. One more step runs
between steps 2 and 3:

- **Motivational relevance.** With no duty in force, a candidate leaves when none of its goal
  paths could be worth more than 0, whatever its unknowns are: every need it moves is satisfied
  or made worse, and it serves no other goal.

Steps 3 to 5 compare the intervals robustly, a winner's low against a rival's high, and the
recorded projection reads their midpoints. A proposal in such a domain must also be better than
holding under every aggregation rule whatever its unknowns are, unless it discharges a duty.
The [motivation guide](motivation.md) works through a complete cycle and its numerical contract.

The record then has exactly one disposition:

| Disposition | When |
| --- | --- |
| `propose` | One candidate is selected and nothing calls for judgment. |
| `escalate` | A section 13.2 trigger holds: a deontic conflict (a dilemma, or an action both forbidden and permitted or obliged), a duty with no admissible discharge, several duties at once, conflicting evidence, estimators that disagree about a surviving candidate, aggregation rules that disagree, or a projection that unknown effects could reverse. In a domain with needs, also a review that would hold while a need's level is unobserved, expired or conflicted, since what it needs is an observation, and a selected action that is not better than holding whatever an unknown need turns out to be. |
| `blocked` | Steps 1 and 2 removed every candidate, and each blocker is named. |
| `hold` | In a domain with needs, motivational relevance removed every candidate steps 1 and 2 left. The record's `hold` lists the needs inside their bands (`satisfied`) and those outside them (`unserved`), through which no remaining candidate's path is worth more than 0: none reduces the need, or the goal it regulates has priority 0, so a reduction is worth nothing. Nothing is proposed, so an agent whose needs are met does not repeat an action for them. |
| `no-candidates` | The theory made no action a candidate. |

An underived effect on a dimension is unknown, because every action has some effect on every
dimension (section 7.4). An underived contribution to a goal means there is no path to that
goal, because contribution edges exist only where the theory derives them (section 8.1.2).
A declared need supplies its own regulated path, whose value comes from its snapshot.
Nothing normalizes across the candidate set, so adding a candidate never changes another
candidate's appraisal (section 11.10).

The rules above are MeTTa, and Python only validates what comes in, builds the policy's input
and renders its answer. The policy is the files of `src/goal_chainer/relevance/policy/` and the
modules it shares with other consumers:

| Policy file | Decides |
| --- | --- |
| `evidence.metta` | Each signal's effective reading at `as_of`, read off the justification kernel's labels, the fact it gives the theory, and whether its readings are in dispute. |
| `readset.metta` | The dependency cones of a domain's rules, and the readset of one review. |
| `ranking.metta` | The five steps and, for a domain with needs, motivational relevance; the escalation triggers, the dispositions and the authority ceilings. |
| `outcome.metta` | Whether a stored review is stale, whether an attempt's receipt coheres, which of its observations count, and each prediction's status and attribution. |
| `motivation.metta` | For a domain with needs: each need's level at `as_of`, each action's expected change of each need, learned as the mean of host-attributed measured changes, with every sample's residual, and each action's interval of reduction of each need's urgency. |
| `domains/vocabulary.metta`, shared | The seven ordinal bands and the five estimator classes of section 8.2, each class's tier and whether it establishes what happened, whether a validity has run out, and the justification row each detected or refuted reading gives, which the planner builds its reading rows by too. The domain loader reads its two tables through pymetta and the justification kernel loads it, so the vocabulary has one home. |
| `planning/justification.metta`, shared | The labels of the review's readings: which claim each supports, which the tier preference overrules, and which have expired. |
| `policy/goalchainer_fault_tables.metta`, shared | How a table of checks is read: every failing row, or only the first of a table whose later rows read what earlier ones established, and a check that answers neither true nor false reported as the policy's own defect. |
| `policy/goalchainer_deontic.metta`, shared | The deontic status rule the incident decision and the scorer also read. |

Every value the policy receives is a string, a number or a boolean, so a domain may name an
action `None` or `car-atom` and the name stays data. PeTTa evaluates a nested expression whose
head names a function, but never a string.

## The budget

A review runs under its caller's `RunBudget`, the one budget a request spends across its stages:
`review(domain, packet, budget=...)` and `check_freshness(..., budget=...)` take it, as do
`parse_receipt(payload, budget=...)`, `assess_receipt(record, receipt, budget=...)` and
`assess_attempt(predictions, receipt, decided_at=..., budget=...)`, and a missing one is refused,
never run unbounded. The packet's budget declares the most the review may cost, so a caller
budget with more inferences or seconds left than the packet declares is refused too. The
relevance CLI builds the one budget from the packet's bounds when the command
starts, with `packet.budget.run_budget()`; a receipt has no packet, so `assess` takes its bounds
on its command line, `--inference-budget` a positive whole number of any size and
`--timeout-seconds` a positive finite number. Each stage gets only what the earlier ones left of the
caller's inferences and of the caller's deadline: the domain's dependency cones, the effective
readings, the theory run, the readsets, then the ranking. The record's `engine.inferences` is
what the review itself spent. A stage the budget stops fails the review with `review-budget-exceeded` or
`review-timeout`, and the error names the whole budget and the whole spend. The engine checks
the inference bound between its steps, so a stopped stage can spend more than it had left; the
reported spend is what was measured.

Some work is fixed for the process and no input changes it: loading `lib_deontic` and compiling
the policy. Its inferences are charged to no review. A host can do
it at startup with `goal_chainer.relevance.prepare_service(budget)`, whose budget bounds only
how long the startup may take. Otherwise the first review does
it inside its deadline: loading `lib_deontic` and the policy's modules and compiling the policy
are stopped when the deadline passes, and an overrun is a `review-timeout` with no record. A
policy file that changed on disk after the process loaded it is refused with `engine-failed`:
the engine keeps what it imported, so the new bytes need a fresh process. A domain's dependency
cones are computed once per domain and cached, but they depend on the domain, so they are
charged like any stage, and a review that finds them cached spends less. A computation the
budget stops caches nothing. Once the policy is loaded, a review's calls share the engine with
every other evaluation in the process, each on a worker of the engine's pool, so reviews from
several threads run at once and answer what each answers alone.

<!-- am[implements a-rel-docs-count-variation-1019@db1267] -->
`engine.inferences` in the record is the review's measured spend. Earlier work in a process
can change it slightly, and concurrent reviews can spend different counts while returning
the same decision. The retained concurrency measurements differ in steps of about 24
inferences; that observation is not a bound for every workload. The count is never a decision
input and never part of the fingerprint.

Authority appears as two ceilings and is decided by neither. `action_authority_ceiling` is the
highest rung the domain lets the action be applied at. `licensed_authority_ceiling` lowers it
to what the weakest estimate underneath can license (section 8.2). The estimates counted are
the action's effects and the readings of every signal its conclusions can depend on, and in a
domain with needs, for each need, the observations of its level at their strongest class
(`need-level`) and the class of the action's expected change of it (`need-change`), whatever value
the reduction takes. `authority_limits` names each estimate that lowered the ceiling.

## The review record

The record's protocol is `goalchainer-relevance-review-v2`. A v1 record, written before reviews
ranked by needs, is refused by freshness and receipt assessment as `invalid-record`, never
reported stale: review the current packet again.

| Field | Meaning |
| --- | --- |
| `fingerprint` | SHA-256 over the decision inputs: domain digest, review policy digest, engine identity, review authority, subject, every signal's effective reading with the identity of its observations, and in a domain with needs the motivation snapshot's identity: the stream, each need's level state and value with the count of its supporting observations and a SHA-256 commitment to their ids, and each candidate's expected changes with their sample count and a SHA-256 commitment to the samples' keys. The history the snapshot was read from is not part of it. Notes, the review id, the trigger, `as_of`, the budget and the inferences spent are excluded. |
| `proposal` | When the disposition is `propose`: the action, its deontic status, both authority ceilings, `authorization: unresolved`, the goal path that carried it, and its `predicted_effects`, `predicted_contributions` and `predicted_need_changes`, each with `status: predicted`. A carrying band path names its `band` and a number `value`; a carrying need path names its `need` and a `value` with `low` and `high`. A predicted need change names the need's `observed_level` and `level_state` and the `predicted_level` range, `low` to `high`, the action is expected to leave. |
| `escalation`, `blockers` | The reasons and the contested candidates, or each removal that blocked the review. |
| `hold` | When the disposition is `hold`: the `satisfied` and `unserved` needs. |
| `steps` | Every ranking step with its survivors and its removals. |
| `deontic_support` | One selected support tree per conclusion or dilemma literal, sorted by literal. Each node has a `kind` and a literal in MeTTa notation. Facts and rules name their `label`; rules also hold ordered `premises`. |
| `candidates` | Each candidate's deontic status, modes, effects, contributions, goal paths, need paths, aggregates, motives, projection, unknown dimensions, ceilings and readset. Aggregates and motives are intervals with `low` and `high`. The status is `conflict`, `forbidden`, `obligated`, `permitted` or `unregulated`, by the rule in `src/goal_chainer/policy/goalchainer_deontic.metta` that the incident decision and the scorer read too. |
| `motivation` | In a domain with needs, the snapshot the review ranked by, with its identity under `snapshot`; `null` otherwise. |
| `missing_information` | Unknown, conflicted and contested signals that could change the review, readings that decayed, dimensions no rule estimates, and in a domain with needs the needs whose level is unknown or conflicted and the candidates' unknown expected changes. |
| `readset` | Every signal whose reading could change the outcome, with a snapshot of each. |
| `review_policy` | The policy's digest, the identity of its module group: SHA-256 over the group's name and the SHA-256 of each `.metta` file the engine loaded, in load order, the shared deontic status rule included; and each file's path inside the package. |
| `engine` | The runtime and its digest, the SWI-Prolog version, the digest of the package's deontic library directory (`plugin_digest`), and the inferences the whole review spent against the budget. |

The readset is computed from the domain's rules, not from the proof of the winner. It holds the
candidacy rules of every action, every duty, permission and prohibition the theory can conclude,
each candidate's appraisal, and which goals are required. A rival that was removed by a
defeater, or an action that a new observation could make a candidate, therefore stays in it.

<!-- am[implements a-integrate-deontic-support-trees-1019@508ecf] -->
For example, an obligation derived by `r2` through `r1` carries a rule node labelled `r2`,
whose premise is the `r1` rule and whose leaf names the given fact. `lib_deontic` chooses
the first applicable supporter by label at the strongest available level. The tree attributes
support; it does not enumerate defeated alternatives or explain the ranking's later choices.
A `cycle` marks a repeated literal. A `no-proof` marks the absence of positive support,
including an unresolved dilemma; it is neither a proof of negation nor permission to act.

The trees are extracted before the theory's speculative state is discarded, inside the same
inference and time budget. Exhaustion fails the review without a partial result. They are
derived output, excluded from the decision fingerprint, and do not replace the readset.
Inspect them with
`goalchainer relevance review --packet PACKET --json`; they are not execution authorization.

## Freshness

Before acting on a stored proposal, a host checks whether the evidence it rests on still holds
(sections 8.5 and 10.5). The check compiles the current packet and compares; it runs no theory.

```console
$ goalchainer relevance review --packet examples/relevance/chemistry-contention.packet.json --json > review.json
$ goalchainer relevance check --review review.json --packet examples/relevance/chemistry-at-apply.packet.json
review rr-42 is stale (sha256:...)
  safe_point_reachable: detected -> unknown
  the earlier result lost its support; review again, and read nothing into alternatives
```

By 09:15 the telemetry that showed a reachable safe point has expired, so the pause has lost
its support. A review is `stale` when a readset reading, the domain digest, the review policy's
digest, the engine identity or the review's authority rung changed, or, in a domain with needs,
when the motivation snapshot's identity at the current packet's `as_of` differs from the one the
review rested on (`motivation_changed`): a new observation stales it even when the level it gives
is unchanged, since support is the observation. The review policy's digest
is its module group's identity, so a review stored while the digest was composed file by file
reads `review_policy_changed` once and is stale. A reading replaced by
another observation with the same state still counts as a change, because support is the
observation and not only its state, and so does an opposing observation added beside unchanged
support, which leaves the signal conflicted. Stale is not refuted: the earlier result needs a new
review, and it says nothing about which alternative is right. A packet about another subject is
refused with `subject-mismatch`.

Freshness compares what a review rested on, not what it decided, so a fresh check does not vouch
for the proposal a stored record carries: a record whose proposal was edited after the review
still checks fresh. A host about to act on a stored proposal therefore runs the review again on
the current packet and acts only when the new record proposes the same action with the same
deontic status. That comparison is sound because a review's record depends only on its packet,
its domain, motivation snapshot and the engine, never on the process that produced it: the policy reads every set it
is given in sorted order, and its own orderings are stable.

## Receipts

After the host acts, its receipt records one attempt: the attempt's id, when the action was
applied (`applied_at`, or `null` when it was not), when the receipt was written (`issued_at`),
and what was observed. The assessment compares those observations with the proposal's
predictions (section 8.8). The review's fingerprint names a decision, and two applications of
one decision are two attempts.

```console
$ python3 -c 'import json; r = json.load(open("review.json")); t = json.load(open("examples/relevance/chemistry-receipt.json")); json.dump({**t, "review_fingerprint": r["fingerprint"]}, open("receipt.json", "w"))'
$ goalchainer relevance assess --review review.json --receipt receipt.json --inference-budget 5000000 --timeout-seconds 60
receipt for pause_recoverably, attempt exec-276 (applied 2026-10-16T09:02:00+00:00, issued 2026-10-16T09:10:00+00:00)
  effect direct-cost slightly-negative: predicted
  effect governance-cost slightly-negative: predicted
  effect irreversibility slightly-negative: predicted
  effect option-value strongly-positive: predicted
  effect recoverability strongly-positive: confirmed, attributed to the attempt
  contribution to least_commitment strongly-positive: predicted
  contribution to project_outcome positive: predicted
  goal least_commitment: achievement unverified
  goal project_outcome: achievement unverified
  not counted (cannot-establish): contribution project_outcome from worker-self-report
```

A decision other than a review is assessed with
`goal_chainer.relevance.assess_attempt(predictions, receipt, decided_at=..., budget=...)`, the
judgement `assess_receipt` makes with the proposal's effects and contributions as the predictions
and the review's `as_of` as `decided_at`. Each prediction is an `(about, target)` pair, `about`
being `effect`, `contribution` or `achieves`, and `decided_at` is when the decision was made,
which no reading the decision rested on may follow. The receipt's `review_fingerprint` names that
decision: a planner's receipt names the admitted step's witness digest, and the planner passes
each `Achieves` literal of the step's procedure as `("achieves", literal)` and the instant it
dispatched the step as `decided_at`. The answer gives each prediction's status, attribution and
counted observations in order, beside the attempt's times, the receipt fingerprint and the
observations not counted. No proposal predicts what a step achieves, so `assess_receipt` lists an
`achieves` observation as `unpredicted`.

Applying an action confirms nothing by itself. An observation counts toward the predictions
about its target only when every row below holds, and the first row that fails is the reason it
is listed as not counted:

| Reason | The observation counts only when |
| --- | --- |
| `cannot-establish` | its estimator is measured, deterministic or human-asserted |
| `not-applied` | the action was applied |
| `untimed` | it has a time |
| `before-application` | it was made after `applied_at` |
| `after-next-attempt` | it was made no later than the same subject's next applied attempt, given by `--next-attempt-at` |
| `unpredicted` | the decision predicts what it is about |

Section 8.2 defines a model-proposed value as an estimate with no calibration history and a
receipt-calibrated one as a predictive estimate with a track record, so neither can say what
happened. Every reading a decision rests on was made at or before its `decided_at`, a review's
`as_of`, and an application before `decided_at` is refused, so the decision's own evidence never
comes back as its outcome. A prediction is `confirmed` or `missed` when its counted observations
agree, `conflicted` when they disagree in any order, and stays `predicted` when none counts. An
action that was not applied leaves every prediction `not-attempted`.

Seeing the predicted outcome after the attempt is not the attempt causing it: a checkpoint that
existed before the pause makes the work recoverable too. A confirmed or missed prediction is
attributed to the attempt only when a counted observation names the attempt in `produced_by`,
as the checkpoint store does for the checkpoint the pause wrote. The order of the times is
checked, since a product follows the start of what produced it (W3C PROV-CONSTRAINTS, Constraint
34), and it never stands in for that statement. Goal achievement is always `unverified`: it
belongs to the host's verifier. These are the rules AgenticMind keeps for finished work, where
completed, evidenced and effect-confirmed are separate states.

A receipt is an `invalid-record` when what it states does not cohere. The policy reads the first
row below for the receipt and the next four for each observation when the receipt is read, and
the last two when it is assessed; the first row that fails for a receipt or an observation is
its fault. The error's message names the first fault, and its details list every fault with the
index of the observation it is in:

| Fault | The receipt is refused when |
| --- | --- |
| `applied-after-issue` | its `applied_at` is after its `issued_at` |
| `observed-after-issue` | an observation was made after the receipt was issued |
| `producer-not-attempt` | an observation's `produced_by` names another attempt |
| `produced-without-application` | an observation names a producer, but the attempt applied nothing |
| `produced-before-application` | an observation that names a producer has no time after `applied_at` |
| `applied-before-decision` | the attempt was applied before its decision was made: the review's `as_of`, or `assess_attempt`'s `decided_at` |
| `next-attempt-not-after-application` | `--next-attempt-at` is not after `applied_at` |

Times compare as exact instants, written back in UTC, and a time finer than a microsecond is
refused rather than rounded. Each observation carries an `id` and the assessment a
`receipt_fingerprint`, both leaving notes out, so a store counts one observation once however
many receipts carry it.

## What a review can and cannot guarantee

The review has no channel to the world, so it applies no effect, and its proposal is advice.
Keeping an agent from a forbidden act is a different property. It holds by regimentation only
when every resource and communication channel goes through a reliable entity that controls
behaviour; otherwise a norm can only be enforced after the institution recognizes a violation
([Norm enforceability in Electronic Institutions?](https://www.iiia.csic.es/media/filer_public/b1/d3/b1d3d503-7cad-44c8-97dc-f3e4e8bfb547/4547.pdf),
IIIA, sections 2.1 and 2.3). Whether every effect channel passes through the host's policy gate
is the host's property, which GoalChainer cannot check. For the same reason an approval, an
applied action or a receipt does not show that a predicted effect happened: a prediction stays
predicted until an observation of an establishing class checks it, and a violation outside what
the host observes stays unknown.

## Carrying a review through an omegahive room

An omegahive room carries the review without changing what it means (omegahive-core at
`1cd68c5`):

| Room event | Carries |
| --- | --- |
| `proposal` | The review record, as its text. The event has a title and text and no typed disposition field (`src/schema.ts` line 194), so the disposition stays in the record. |
| `decision` | The host's choice about the proposal, made by a seat the room lets decide and never by the seat that posted it (`src/kernel.ts` lines 748-772). GoalChainer never decides its own proposal. |
| `receipt` | Only that a record was read (`docs/architecture.md` lines 215-218). It is not a GoalChainer receipt. |
| `finish` or `execution` | What the host did and observed, with its verification. That is what becomes a `goalchainer-relevance-receipt-v2` for `goalchainer relevance assess`, one execution report to an attempt. The event's `at` is when it was posted, so `applied_at` is the executor's own time of acting; `already-done` applied nothing. |

Nothing is promoted on a GoalChainer receipt alone: a promotion needs a winning decision
(`src/kernel.ts` lines 780-784).

## Writing a domain

```console
$ goalchainer relevance domain --inference-budget 5000000 --timeout-seconds 60
Task control for a persistent agent's own work (task-control-v1, sha256:...)
  12 actions, 6 goals, 21 signals, 12 dimensions, 76 rules
  no rule estimates: expected-goal-delta, contribution-belief, contribution-confidence, urgency, hazard-severity
```

A domain file declares its vocabulary with `gc-domain`, `gc-policy-version`, `gc-authority`,
`gc-action`, `gc-goal`, `gc-signal`, `gc-dimension` and `gc-estimator-ceiling`. It then states
its norms as a defeasible deontic theory using `given`, `always`, `normally`, `except` and
`prefer`; `src/goal_chainer/domains/data/task_control.metta` is the worked example. The loader
rejects:

- a declaration it does not know, or a theory form the readset cannot trace, such as an
  event-calculus form;
- a reference to an undeclared action, goal, signal, dimension, band or estimator class;
- a number that is not finite, such as an authority rank or goal priority of `nan` or `inf` or
  an integer beyond the float range, and a negative goal priority: a priority multiplies into
  every path through its goal, and a NaN or infinite value could not be recorded; the sum of
  priorities in declaration order must also stay finite, as the review sums in that order;
- an integer of more digits than the interpreter writes as text, 4300 by default, anywhere in a
  form: no digest, rendering or message could write it;
- a duplicate rule label, or a `prefer` naming a label that does not exist;
- the symbol `Error` anywhere in a form: it is MeTTa's error constructor, so a list of names
  headed by it reads as an error, and the planner's kernel builds such lists; the string
  `"Error"` stays data;
- any text outside a form, such as the `!` that would make MeTTa execute it.

A declared signal that no rule body reads is no fault, since a shared domain may declare a
condition only planning or classification reads. A reading of it changes nothing a review
concludes, so the domain lists it in `unread_signals`, and both `goalchainer relevance domain` and
the review record's `domain` block show the list.

A domain may also carry a reading section, the `gc-reading-*` and `gc-ranking-instruction`
forms `goal_chainer.domains.readings` reads, each proposition declaring one of the domain's
signals, and a bigraph section, the `gc-brs-*` forms `goal_chainer.domains.bigraph` reads. The
relational checks, every reference, duplicate, rank, ceiling, label and preference, are rows of
MeTTa fault tables over the facts the core and each section contribute (`domains/checks.metta`,
and each section's own, `domains/readings.metta` and `domains/bigraph.metta`), and so is the test
that lists the unread signals. A [needs section](motivation.md#declare-a-quantity-and-its-target)
adds `gc-need` and `gc-need-expectation`, checked by `domains/needs.metta`.
They run under the caller's budget, so
`read_domain`, `load_domain` and `packaged_domain` take a `RunBudget`, and one `DomainError` lists
every fault they find.

The packaged task-control domain carries a bigraph section, the paper's own typed graph: §8.1.1's
node types and §3.4's seats are its controls, each port is named for the §8.1.2 edge type it
carries, the focal task sits in the seat that owns it, and every declared signal is anchored on
the entity it describes. The planner reads it with its procedure library, so the packaged
procedures plan on the packaged domain without a caller's topology.

A domain's digest covers what the review reads: the core's forms, the theory included, the
signals the sections declare, and the needs and expectations. A bigraph form or a reading question never
changes it, so editing a section the review does not read leaves every stored review fresh, while
adding or renaming a proposition, a signal the review lists, makes a stored review read stale with
`policy_changed`.

Two effect rules with different bands for the same action and dimension do not attack each
other, so a specific rule that overrides a default must withdraw the default with `except`, as
`rGovNotStreamline` does. A review fails with `theory-defect` when one estimator class derives
two levels for one effect. A dimension that no rule can estimate is reported, never read as
neutral.

## Limits

- No apply path. Applying a proposal, granting authority and verifying goals stay with the
  host.
- A proposal names one whole action. The paper's structured interventions (section 7.3) map
  only two of the twelve verdicts onto components, so the review makes no claim about
  partial authorization of an action's parts.
- Contribution belief, contribution confidence, expected goal delta, urgency and hazard
  severity have no estimator in the task-control domain. They need the uncertain means-ends
  layer (PLN) and are reported as unestimated.
- A wheel installs the packaged domain, so `goalchainer relevance domain` works anywhere.
  A review still needs the repository's native runtime.

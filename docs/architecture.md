# Architecture

Native GoalChainer is an event-replayed SNARS session around the Mettabase
reasoner. GoalChainer does not implement Subjective Logic formulas in Python.

## Decision flow

```text
natural-language request
  -> Mettabase AlphaBeta parse
  -> HyperBase hb facts and typed SH trees
  -> sn ingest! with source and trust
  -> GoalChainer MeTTa policy and registered rewrite rules
  -> SNARS acceptable, risky, and forbidden proofs
  -> OmegaClaw lib_deontic gate
  -> MetaMo preference
  -> goalchainer_score.metta ranking
  -> directive or execution
  -> sn outcome! feedback
```

The parser output is retained. `snars_program.py` splits the Mettabase program
into checked `(hb ...)` facts and allowlisted SNARS effects. User text is encoded
as a string or passed to the parser over JSON standard input. It is not inserted
as executable MeTTa.

`goalchainer_policy.metta` walks full `(hb tree ...)` values. It classifies
sensitive, public, unverified, and coordination labels in MeTTa. The policy then
asserts ordinary SNARS evidence and uses `sn rw` rules to derive action beliefs.
PeTTa execution decides whether those rules work. MeTTa LSP output is advisory
because the deployed language is PeTTa, not MeTTaScript.

## Component ownership

Mettabase owns:

- evidence cells and binomial opinions
- expectation, conflict, marginals, and surprise
- receipt deduplication and source trust discounting
- forward cycles, frontier steps, and compiled rules
- backward proof paths, proof stamps, and disjoint fusion
- goals, subgoals, time, discovery, mining, and forgetting
- counterfactual snapshot and rollback
- outcome grading and trust updates

GoalChainer owns:

- dependency and commit resolution
- safe program construction
- PeTTa process timeouts and captured output
- the versioned `goalchainer-snars-v1` protocol
- immutable Python result types
- append-only SQLite replay
- incident policy knowledge and score composition in MeTTa
- CLI and OmegaClaw routing

OmegaClaw-Core `lib_deontic` owns hard normative status. MetaMo owns preference
among candidate actions. PeTTaChainer remains in the offline compatibility path
and separate proof-audit tools.

## Directive orchestration

The selected deontic result becomes a native directive plan. The MeTTa adapter
owns the state transition rules and packages one
`goalchainer-directive-v1` record for the host. One snapshot call returns status,
next actions, the Kanban board, summary counts, metadata, assignments, cycles,
and consistency from the same PeTTa reasoning pass.

The plan file is the source of truth. Claim, unclaim, complete, block, and
unblock append claims to that file. GoalChainer opens durable plans with
owner-only permissions, takes shared locks for reads, takes exclusive locks for
mutations, and records SHA-256 digests before and after each operation.

`solve` claims the selected task before the executor runs. A safe authorized
result completes the task. An unsafe result or executor exception blocks it.
Blocking an upstream task produces `upstream-blocked` conclusions for its
dependents, including transitive dependents.

Mettabase owns the Markdown syntax and renderer. GoalChainer constructs a
Mettabase `(md ...)` authoring tree in MeTTa, calls `md-author-markdown` through
PeTTa, and appends the exact durable plan in a fenced `metta` block.

Python does not reimplement directive readiness, precedence, dependency
propagation, assignment, lifecycle, or board calculations. Python handles path
validation, file locks, process bounds, typed protocol decoding, JSON, and skill
routing.

## Solver and language extension boundaries

Clingo is a suitable optional optimizer for assignment capacity, scheduling,
and other global constraints over a frozen directive snapshot. It is not the
owner of lifecycle state. A future optimizer should follow the multi-shot
pattern used in CalDar: create one `Control`, ground once, solve under a complete
set of guarded assumptions, and map model literals back to stable task IDs.
Keeping that boundary prevents an ASP model and OmegaClaw from deriving
conflicting boards.

MeTTaLingo's abstract-syntax boundary is useful for localized task labels. Stable
task IDs and MeTTa meanings should remain language neutral, while a concrete
grammar projects those meanings into a selected language. Its current grammar
does not cover incident orchestration, so GoalChainer does not claim multilingual
planning yet.

MeTTaSpeak's EPILOG implementation is written for the TypeScript MeTTaScript
runtime. Its episodic proof and ownership model can inform the TypeScript port,
but it is not imported into this PeTTa package. A direct import would claim a
runtime compatibility that has not been implemented.

## Protocol

Every operation emits one four-field record:

```metta
(goalchainer-snars-v1 operation ok payload)
```

The parser accepts nested S-expressions, quoted strings, empty lists, and exponent
numbers through Mettabase's own S-expression codec. It rejects unknown versions,
wrong operations, malformed records, and more than one tagged result.

Belief records preserve:

- canonical statement and statement ID
- `(b, d, u, a)` opinion and expectation
- positive and negative evidence counts
- receipts with source, statement ID, and trust
- nested proof trees and axiom stamps
- source identities and occurrence metadata

Derived beliefs keep premise receipts from their proof stamps. The Mettabase pin
includes the shared-conditional-edge stamp fix, so proofs that share a conditional
edge are not fused as independent support.

## Sessions and replay

PeTTa processes are short-lived. `SnarsEventStore` reconstructs the world before
each operation by replaying immutable events in sequence order. Each event records
its schema version, Mettabase commit, canonical JSON payload, and content hash.

Mutating events are appended after PeTTa returns a valid protocol record.
Counterfactual hypotheses are never appended. Repeated identical text ingestion
and identical goal registration are idempotent, so replay does not inflate
confidence or change the state digest.

SQLite enables foreign keys, a busy timeout, secure deletion, WAL for file-backed
stores, and owner-only database permissions.

## Scoring

The evidence term is the native SNARS expectation:

```text
expectation = belief + base_rate * uncertainty
```

The scorer never multiplies expectation by confidence again. Forbidden and
conflicting rows receive `-1`. Candidate actions are mutually exclusive, so a
proven obligation receives a priority term that ranks above any merely permitted
row. The remaining score combines MetaMo preference when available, or goal
coverage and the individual-collective fairness floor.

`goalchainer_score.metta` returns the exact formula label, stable declaration
order, tied action IDs, and whether automatic execution is allowed. A tie within
the configured epsilon disables automatic execution.

## Goals and unverified facts

Every `GoalScenario` goal is registered with owner, individual or collective
kind, desire, required status, and source. When SNARS derives that facts are
unverified, the scenario adds a required `verify_facts` goal. Holding satisfies
that goal. Publishing does not. `lib_deontic` also marks holding obligated.

Required goals remain visible in `missing_required_goals`. They are not converted
into an unnamed penalty.

## Counterfactuals and outcomes

The default audit asks whether raw publication would be acceptable if the request
were public. Mettabase runs the hypothesis through `sn what-if!` and `sn would?!`
inside its snapshot. GoalChainer compares the exact state tree and SHA-256 digest
before and after.

`solve` executes the selected action while the SNARS session is open. It records
the leak-check result against the action's acceptable statement through
`sn outcome!`, then returns native trust views from before and after the update.

## Inspection surfaces

The session and CLI expose:

- direct belief, ask, prove, explain, why-not, and discover
- goals and licensed subgoals
- counterfactual reasoning
- temporal processing and eternal views
- source and rule trust
- mining and inactive proposals
- evidence, opinion, view, expectation, marginal, threshold, and surprise
- frontier step, focus, compiled rules, and forgetting status
- rewrite names, typed rewrite constructors, and proposals
- cells, metadata, receipts, stamps, and state fingerprints
- the separate `snars-guard.metta` s(CASP) safety query

GoalChainer does not persist or approve mined rows. A later reconstructed session
cannot use a proposal unless a separate approval path is added. The guard is
loaded only for an explicit guard operation and is not represented as part of the
SNARS aggregator.

## Design-only boundaries

GoalChainer does not claim these planned SNARS features:

- goal-aware worth in backward search
- a complete expected-free-energy worth layer
- AO-star backup in the production chainer
- learned predictive-coding control
- GNN or tree-RL control
- generalized mine, blend, and synthesize dispatch
- all planned miner families
- full context and microtheory support
- the planned self-verifying audit bundle
- multinomial or hyper opinions

Those belong in Mettabase before GoalChainer can expose them.

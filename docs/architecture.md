<!-- Purpose: describe GoalChainer's domain, reasoning, persistence and host boundaries. -->
# Architecture

GoalChainer reviews and plans against explicit domain declarations. Its runtime
is the operator's [MesTTo/MeTTa](https://github.com/MesTTo/MeTTa) engine, accessed
through pymetta. MeTTaScript and MeTTa-TS are separate implementations. MeTTa
owns reasoning and policy; Python reads files, transports typed values, calls
models and persists records.

## One request path

<!-- am[implements a-integrate-domain-composition-1018@ac7260] -->
`requests.run_request` accepts `review`, `plan` or `admit`. Each request selects
one domain by packaged name or file path, supplies attributed context, and runs
under the caller's `RunBudget`.

```text
selected domain + attributed context + optional original text
    -> domain validation and declared semantic readings
    -> justification of the current evidence snapshot
    -> normative and relevance review
    -> optional planning or current-step admission
    -> result with unresolved authorization and no applied effects
```

The CLI and OmegaClaw skill call this same function. The skill adds limits to
the JSON envelope; the CLI takes them as flags. The context records the original
limits without constructing another deadline. See the [request examples](../README.md#domains-and-readings).

<!-- am[implements a-integrate-runtime-doc-wording-1018@56334c] -->
A review explains each candidate through `paths` and `contributions`, records
rejection in `eliminated`, and reports `unknown_dimensions`, `missing_information`
and its dependency `readset`. Planning adds a `Plan`, `Inquiry` or `NoPlan`. Admission
adds `Admitted`, `Blocked`, `Ambiguous` or `Stale`. The response retains the
review and states `authorization="unresolved"` and `applies_effects=false`.

## Domain declarations

A domain declares its actions, goals, authority ceilings, signals, dimensions
and normative theory. Optional sections declare semantic readings and bigraph
structure. The loader checks what is declared; a consumer checks what its
operation requires. A domain suitable for review need not be suitable for
planning or text reading.

Python checks the grammar. MeTTa fault tables check relations between the
parsed declarations and report their faults together. The domain loader and
section readers share one form reader. A directive or stray text is refused;
loading a declaration does not execute it.

The domain's theory derives candidates, deontic modes, required goals and
predicted contributions or effects. Relevance policy computes the ranking and
any escalation. Domain names do not choose an incident-specific algorithm.
The incident and task-control files are declared domains using these same
mechanisms.

A planning library belongs to a domain and must anchor its literals in that
domain's bigraph section. A caller supplying a domain file also supplies its
procedure library.

<!-- am[implements a-integrate-architecture-digest-scope-1018@67d2ae] -->
The review's domain digest covers the core declarations and theory, plus each
section-declared signal's identifier and description. Editing only a bigraph
form or reading question leaves that digest unchanged. A reading carries its
reading declaration's identity, and a plan witness carries its compiled-rule
identity. Review freshness, reading projection and step admission check the
identities their own results depend on.

## Readings and knowledge

Jev answers the questions in the selected domain's reading section. A local
cross-encoder ranks passages against those questions. Its score is a retrieval
score, not evidence weight, truth or permission. The original request text is
passed as data. A model miss, refusal or malformed answer is a typed failure;
there is no keyword substitute.

Readings retain their source, estimator, observation time, expiry and model
provenance. The shared vocabulary constructs the same justification rows for
review and planning. The justification kernel owns contrary-reading resolution;
relevance projects its labels into effective readings.

The adopted source preference is defeasible: an establishing reading can defeat
a model-proposed contrary. That does not prove the reading true. A current
contrary still appears as a live disagreement for the review's escalation
policy. Expiry and withdrawal remove support without establishing the opposite.
Conflicting evidence and an absence of evidence remain distinct.

Argument roles are explicit in both inputs and labels: `Claim`, `Observation`,
`Row` and `Stated`. A caller term that resembles a bookkeeping term retains its
own role. A claim's checked knowledge is read from claim labels, not guessed
from another argument with the same spelling.

Only checked knowledge builds evidential structure in the planning state. An
established positive builds its subject; an established negative builds its
negative witness. Unknown knowledge builds neither. Unchecked knowledge remains
an explicit assumption. An absence test over an evidential predicate cannot
turn silence into a negative fact.

The request's attributed readings own signal evidence. Additional planner rows
may establish or withdraw statement evidence under the planner's checked
reference rules. They cannot replace a signal reading or cite a reading,
journal or receipt observation as though it were independent evidence. A
statement depending on a signal refers to that signal's claim.

See [semantic reading](semantic-reader.md) and the
[mathematical contracts](mathematical-contracts.md) for the individual rules.

## Structural planning

The bigraph kernel models containment and links explicitly. Controls, regions,
sites, indexed ports, named entities and open names retain their meanings
through matching and reaction. State identity is isomorphism with the required
named identities fixed; a hash bucket is only an index for the exact comparison.

The matcher retains embeddings through rewrite. Completed successors are
merged by isomorphism while keeping occurrence counts and a representative.
Matching the same unordered set of nodes does not justify merging occurrences:
different assignments can produce different successors. Parameter duplication
and deletion follow the reaction's instantiation map; an occurrence that would
copy a named entity is refused.

Procedures compile to reactions with agenda state separate from world state.
Executed steps wait for their declared predecessors, preserving partial order.
Procedure conditions are rechecked at each act. Predicted completion does not
become journal evidence: dispatch makes an attempt in flight, and an observed
receipt determines its resulting knowledge.
<!-- am[implements a-ev-fb-trials-1018@775554] -->
The receipts a caller documents also grade each applied attempt against what
its procedure achieves, and a procedure's track record holds only under its
library's promotion rule.

Search orders plans by its declared scheduling policy. This order is neither
a probability nor a utility estimate. An inquiry names the investigator and
its possible continuation branches. `NoPlan` means the admitted space was
exhausted. Inference or deadline exhaustion raises an error and never becomes
`NoPlan`.

## Admission and execution

A plan step carries its procedure identity, application, binding and witness.
The witness records the compiled-rule digest and selected images. Admission
rebuilds the state from current evidence, recompiles the applicable rules and
rematches the witness.

<!-- am[implements a-integrate-planner-input-failures-1018@b84418] am[implements a-integrate-planner-step-consistency-1018@fc6d64] -->
Witness fields must contain ground terms of the expected shape. Invalid fields
raise typed errors. A live step's kind and entity binding must agree with its
declared step and witness. The application number identifies the step in the
report; admission does not use it to select a rule.

A changed rule identity gives `Stale`. Missing established reads give `Blocked`.
If the witness leaves several non-isomorphic successor classes possible, the
answer is `Ambiguous`; the executor cannot silently select one. An admitted
step has a current occurrence in one successor class.

These are model checks. The host still owns authenticated permissions, norms
at execution, licensing, freshness, external effects and canonical task state.
A plan or occurrence grants no authority. The host must validate the sources
and scope of any evidence it treats as an observation.

<!-- am[implements a-ie-host-recompute-proposal-1018@898c26] -->
The incident example host checks a stored review's freshness, then re-runs the
review on the current packet under the same caller budget. It prepares an
authorized artifact only when the new review proposes the stored action and
norm status. Freshness alone compares the recorded inputs and cannot detect
an edited proposal. Recomputing checks the consumed outcome; it does not
authenticate the stored record or establish that its observations are true.

Receipt assessment keeps predicted contributions separate from observed
outcomes. A completed task does not establish an unobserved effect or achieved
goal. Repeated evidence does not become independent support merely because it
has another transport record. See [relevance reviews and receipts](relevance-review.md)
and the [execution contract](execution-contract.md).

## Runtime and budgets

`goal_chainer.runtime` supplies the engine host, budgets, module loading and
one evaluator over declared `ModuleGroup` values. Generic errors and the MeTTa
codec sit below domain and reasoning packages. A module's content identity is
recorded only after its import succeeds.

The evaluator passes data as typed arguments, requires one answer, and runs
each call inside speculation. Its inference spend is charged to the caller's
existing allowance. Composed stages retain the same monotonic deadline.
Interrupts and malformed answers are hard errors, with no partial success.

<!-- am[implements a-integrate-warmup-compose-gate-1019@8b4d00] -->
Module loading and declared warm-ups are fixed preparation work under the
caller's deadline, without charging its request inference allowance. Modules
load once per process. The deontic warm-up reviews a fixed theory inside
speculation, and each engine thread prepares its bounded execution path before
its first evaluation. A failed preparation is not recorded as a success.
Changing loaded module bytes requires a fresh process.

Speculation isolates engine state; it does not undo an external action or
supply a host authorization. The OmegaClaw plugin transports JSON over its
configured Python child process. Setup records that interpreter. The process
boundary does not choose a different GoalChainer reasoning implementation.

<!-- am[implements a-dg-amp-group-spaces-1019@9b4cf8] am[implements a-dg-docs-1019@aaf450] -->
Module group and directive spaces are named with an `&` prefix, as SNARS worlds
are. The engine recognizes a space by such a name or as a registered operand,
and these freshly named spaces need the prefix to be recognized. In a space it
does not recognize, an empty conjunctive match answers an `Error` atom instead
of nothing, and `explain` gives a match form no plan. `goal_chainer.runtime.diagnostics`
profiles, explains or matches one expression in a group's space for a developer,
on the engine held alone and under the caller's budget; the README's
"Diagnose a MeTTa operation" section says what each one runs.

## SNARS and durable state

<!-- am[implements a-integrate-runtime-doc-wording-1018@56334c] -->
The packaged SNARS library owns graded beliefs, evidence cells, proof stamps,
trust, goals, time and counterfactual reasoning. Python validates the opinion's
components and computes its projected expectation, `belief + base_rate * uncertainty`.
The MeTTa library decides conditions from the interval `[belief, belief + uncertainty]`.
Its source provenance travels with the package.

A `SnarsSession` uses the reader its caller selected. A batch carrying reading
facts also carries their declaration; a policy batch receives that declaration's
forms beside the facts. Compiled worlds do not hold a default domain. Pure
SNARS computations with no readings or reading policy need no declaration.

`SnarsEventStore` reconstructs the session by replaying immutable events in
sequence order. Events retain schema and engine identities, canonical payloads
and content hashes. Mutations are appended after a valid result; counterfactual
hypotheses are not appended. Receipt identity distinguishes a source's existing
evidence from a new observation. A different model or grounding revision alone
does not make independent support.

The SNARS protocol preserves canonical statements, opinions, evidence counts,
source receipts and proof structure. SQLite permissions and replay semantics
are documented in [persistence and privacy](snars-persistence.md).

## Directive plans

`lib_directive` supplies readiness, dependency propagation, assignment,
lifecycle and board calculations over caller-written plans. Python validates
paths and records, manages file locks, and transports the result. A directive
claim is a lifecycle operation, not GoalChainer execution authorization.

<!-- am[implements a-integrate-runtime-doc-wording-1018@56334c] -->
The caller-selected plan file holds the directive's durable state. Read operations
use shared locks; mutations use exclusive locks and record before and after digests. Blocked
prerequisites propagate to dependent tasks. The Markdown renderer uses the
same plan data. See [directive orchestration](directive-orchestration.md).

## Reviewed model adaptation

The cross-encoder's sleep cycle trains on reviewed question-passage labels.
Related documents share a provenance group, which determines their training or
holdout partition. Repeating model-generated labels does not make them reviewed.

Evaluation compares challenger and incumbent on the same held-out groups.
Statistical conclusions depend on independent provenance groups and a fixed
evaluation batch. New identifiers cannot establish independence between copied
sources. An artifact retains its model files, base pin, reviewed-data identity,
evaluation and admission policy.

Promotion checks the sealed evidence and the evaluated parent generation before
an atomic pointer selects the artifact. Rollback validates its retained target
and creates a new generation. A reading pins one serving identity, which enters
its cache and provenance. Training changes passage ranking; it does not amend
norms or confirm an action. See [the sleep workflow](semantic-sleep.md).

## Verification limits

Type and algebraic invariants are strict within their stated model. Source
accuracy, authentic host grants, independent observations and correct external
execution are defeasible premises. A source label does not authenticate them.

Generated tests, mutation checks, independent models and engine differentials
exercise the implemented contracts. They do not prove every host execution
safe or every goal reachable. Liveness also needs available executors, usable
evidence and a host that revisits blocked or stale proposals. The
[mathematical contracts](mathematical-contracts.md) identify the proved models
and their executable correspondence.

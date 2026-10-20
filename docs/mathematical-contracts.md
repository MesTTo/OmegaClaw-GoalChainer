<!-- Purpose: specify GoalChainer's mathematical model, executable correspondence and limits. -->
<!-- am[implements a-math-delivery-1016@42d527] -->
<!-- am[implements a-integrate-retired-model-docs-1018@7424a1] -->
# Mathematical contracts

GoalChainer appraises advisory candidates against declared goals and hard norms. Its scores
order candidates under a particular policy. They do not establish that an observation is true,
that a host granted authority, or that an external action achieved its intended effect.

Declarations supply the goals, required flags, priorities and norms. The proofs hold under
their stated premises. A proof of a chosen formalization does not establish that the
formalization expresses the operator's intention.

## Model and correspondence

[GoalChainer.lean](../proofs/GoalChainer.lean) proves interval-order and authority-ceiling
properties. [PlanningEvidence.lean](../proofs/PlanningEvidence.lean) proves the opinion interval
and its condition cuts. [PlanningModel.lean](../proofs/PlanningModel.lean) proves that a plan the
planner accepts holds in every world its readings admit. [Motivation.lean](../proofs/Motivation.lean)
proves bounds for a declared need's drive and signed drive reduction. The runtime correspondence checks in
[test_mathematical_contracts.py](../tests/test_mathematical_contracts.py) call the packaged
MeTTa policies and native SNARS runtime. They compare those answers with independent models;
they do not replace the policies with Python implementations.

| Model premise or operation | Actual implementation | Evidence and limits |
| --- | --- | --- |
| Normative admissibility precedes preference. | `relevance/policy/ranking.metta` and the shared deontic status rules. | Ranking tests cover obligations, forbidden and conflicting candidates, and required-goal harm. The theory and observations must be appropriate to the request. |
| Unknown effects span the entire band range; conflicts retain their interval. | `relevance/policy/ranking.metta`: `gc-relevance-interval-of`, `gc-relevance-dominates`. | Independent generated interval oracle, including order-preserving relabelings. |
| A licensed ceiling cannot exceed the action's tier or a supporting premise's ceiling. | `relevance.ranking` and `relevance.review`. | Lean proves the minimum bounds; a whole review checks the native policy's authority projection. A ceiling is not a host grant. |
| Supported condition cuts use the opinion interval [b,b+u]. | `SnarsSession.condition` and the packaged SNARS condition policy. | PlanningEvidence proves exact bounds and disjoint strict cuts; runtime tests check floating-point boundary cases. |
| A proposal is advisory until a host establishes authorization; proposed effects stay predictions. | `relevance.review`, `relevance/policy/outcome.metta`. | A whole chemistry review checks unresolved authorization and `applies_effects: false`; actual outcome policy checks non-establishing and conflicting observations. |
| A snapshot of evidence rows is labelled by the well-founded model of AgenticMind's argument rules under the adopted source preference. | `planning/justification.metta`: `gc-justify`, `gc-justify-frame`, `gc-justification-knowledge`; tiers, the establishing cut and expiry from `domains/vocabulary.metta`. | Every attack graph on up to three arguments against its enumerated grounded labelling; generated frames and snapshots against an independent reference model of AgenticMind f168fa5's rules; renamed literals against the renamed answer. The labels are conditional on the supplied rows and do not authenticate a row. |
| A plan the planner accepts takes each step in every world its readings admit, and reaches the goal in each; at least one such world exists. | `planning/search.metta`, `knowledge.metta`, `compile.metta` and `projection.py` under the agreed rules R1, R3 and C1; `planning/procedures.py`'s reader for R2. | PlanningModel.lean proves it over the finite model that [planning_oracle.py](../tests/planning_oracle.py) transcribes. Given the oracle's classification of each recorded case, its main finds the two models' settled start, enabled moves and successors equal. [test_planning_acceptance.py](../tests/test_planning_acceptance.py) compares plan and admit with the oracle on generated worlds and runs every plan in every admitted world. It holds for the one-entity sublanguage and for readings current when supplied. |

These are three different links: the operator's informal intention to a scenario/domain, that
domain to the mathematical model, and the model to the runtime. The first needs review of
concrete goals and counterexamples by the operator. The latter links have source correspondence,
kernel-checked mathematics and generated tests. None of those authenticates the outside world.

The strict steps are logical consequences within the exact models: interval bounds,
order implications and minimum bounds by induction. Runtime correspondence is defeasible:
source inspection and generated tests support it for the checked revision but cannot establish
every floating-point execution. Mapping a declared goal to the operator's intention, authenticating
an evidence source and deciding whether an observation describes the world remain separate
observational or authority judgments. A counterexample can defeat any of these links without
refuting a conditional mathematical theorem.

## Norms precede preferences

The relevance review requires explicit permission, rejects forbidden or dilemma candidates,
prioritizes obligations, and refuses to propose a candidate that harms a required goal.
These rules are checked against the actual policy in
[test_relevance_ranking.py](../tests/test_relevance_ranking.py) and
[test_relevance_engine.py](../tests/test_relevance_engine.py). A stronger preference cannot
overcome a normative exclusion. An advisory proposal still reports authorization unresolved.

<!-- am[implements a-ie-host-recompute-proposal-1018@898c26] -->
The incident example's host checks the stored review's freshness against the current packet,
then runs the review again under the same caller budget. The new review must propose the
same action and norm status before the host can prepare an authorized artifact. Freshness
alone checks the recorded inputs, so editing a stored proposal can leave it fresh. Comparing
the recomputed outcome checks the fields the host consumes; it does not authenticate the
stored record or the caller's observations.
The frozen incident norm corpus checks that extracting this example
preserves its declared policy. Neither that corpus nor the generic review chooses new norms
on the operator's behalf.

## Ordinal bands, intervals and authority

The seven relevance bands are ordered categories, with neutral in the middle. The runtime
embeds them as (index-3)/3. Robust Pareto comparison uses endpoint order: A can dominate B only
when A's low endpoint is at least B's high endpoint on each compared coordinate, with a strict
inequality on at least one. An unestimated effect is [-1,1], not [0,0]. Two different surviving
estimates retain the interval between them and an explicit conflict. A missing goal path is
represented as no derived contribution, with a zero display coordinate; that is an absence
of a licensed path, not evidence that the real effect is zero.

Any strictly increasing coordinate relabeling preserves these endpoint comparisons. It does
not preserve sums, averages, midpoints, distances or tradeoffs between coordinates. Lean checks
order transfer; generated cases check the actual MeTTa Pareto function under two embeddings.

The later projection and both path aggregations use a chosen cardinal embedding: priorities
multiply band values; sum-over-paths adds path values; max-over-parents takes their maximum;
known effect midpoints contribute to a projection. Their interpretation requires commensurable
units, meaningful gaps and suitable independence/additivity assumptions. The current embedding
is a policy convention. The implementation supplies no measurement or utility elicitation
that calibrates it as expected utility. Agreement between two aggregation rules is sensitivity
evidence within this convention, not an ordinal-invariance theorem. The review demands that a
proposed winner's least lead stay positive against every rival under both aggregations, across
the modeled unknown intervals; otherwise it escalates. That claim is conditional on the modeled
dimensions and bounds, not on every possible unmodeled consequence.

Authority tiers have an order. The licensed ceiling is no higher than the action's tier and
the ceilings of the premises it depends on. Effect estimators contribute limits; each definite
readset signal uses its strongest agreeing estimator. Taking the minimum of those ceilings
cannot increase authority. A model-only supporting premise therefore caps the relevant license
at advisory. This does not make a stronger agreeing reading authentic, and a ceiling does not
grant authority. A host must authenticate a grant and check freshness at application time.

<!-- am[implements a-v2-motivation-lean-1019@654dcc] -->
## Regulated needs

A need declares a scale `[lo, hi]`, a target band `[low, high]` inside that scale, and an
exponent `k >= 1`. The exact mathematical model allows every `k > 0`; the runtime supports
the convex family to avoid amplifying small distances through sublinear powers. Its observed
level is `n`. The model measures distance from the band as

```text
gap(n) = max(0, low - n, n - high)
margin = max(low - lo, hi - high)
distance(n) = gap(n) / margin
drive(n) = distance(n)^k
```

When the band covers the whole scale, `margin` is zero and distance and drive are defined as zero.
For a level inside the declared scale, Lean proves that distance and drive lie in `[0,1]`.
An expected change `d` gives the signed reduction

```text
reduction(n, d) = drive(n) - drive(clamp(n + d, lo, hi))
```

Lean proves that reduction lies in `[-1,1]`. Multiplying by a nonnegative declared goal weight
`w` gives `[-w,w]`. If the current level is in the target band, every immediate reduction is
nonpositive. Moving farther from the band produces a negative reduction. Crossing the band is
scored by the resulting distance from it. The model does not maximize the level of the need.

For scale `[0,1]`, band `[0.4,0.6]`, level `0.9` and `k=1`, the margin is `0.4` and drive is
`0.75`. A change of `+0.1` gives reduction `-0.25`; a change of `-0.4` gives `+0.75`.
`signed_change_counterexample` checks both values exactly. These are drive reductions before
multiplication by the goal's weight.

<!-- am[implements a-v2r-exact-sign-1020] -->
For every `k > 0` and a positive margin, Lean also proves that the reduction is positive, zero or
negative exactly as `gap(n)` is greater than, equal to or less than `gap(clamp(n + d, lo, hi))`
(`reduction_pos_iff`, `reduction_eq_zero_iff`, `reduction_neg_iff`). The sign is therefore a
comparison of two distances, whatever the exponent.

<!-- am[implements a-v2-lean-intervals-1020@35832d] -->
For a known change and an unknown level, [MotivationIntervals.lean](../proofs/MotivationIntervals.lean)
proves that the reduction's exact range is its minimum and maximum at
`{lo, low, high, hi, lo-d, low-d, high-d, hi-d}` restricted to the scale. Between consecutive
points the reduction is continuous and monotone. Both endpoints are attained, and continuity
establishes every intermediate value. The result holds for every real `k > 0`, including
fractional exponents. For the band above and `d=0.1`, `k=1`, the range is `[-0.25,0.25]`.

For runtime correspondence, the exact model takes the binary64 values read by the engine as
inputs. Converting a written decimal to binary64 can change its value before evaluation begins.

<!-- am[implements a-v2r-exact-sign-1020] am[implements a-v2r-stable-magnitude-1020] -->
The runtime decides each reduction's sign by that comparison, made exactly: it writes both gaps as
sums of the input doubles, held as exact expansions (Knuth's TwoSum and Shewchuk's Grow-Expansion),
and the sign of their difference is the sign of its largest component. Every reported reduction,
and every end of a reported range, therefore has the sign of the real value on the binary64 inputs
and is `0.0` exactly where that value is 0. The one exception is size: a nonzero value below
`2^-1022`, the least normal double, can round to `0.0`, never to the other sign.

The magnitude is evaluated from the same exact gaps. A gap `g` at most half the margin has drive
`(g / margin)^k`; above that, `exp(k log1p(-(margin - g) / margin))` with `margin - g` formed
exactly, since `g / margin` rounds to 1 while `g` is still below the margin. Two gaps `a > b` with
`b <= a / 2` give `drive(a) - drive(b)`; closer gaps give `drive(a)(1 - exp(k log1p(-(a - b) / a)))`
with `a - b` formed exactly, since the two drives agree to their last bits there. Each value is
formed inside `[0, 1]` for a drive and `[-1, 1]` for a reduction, whatever `k` is. For scale
`[0,1]`, band `[0,0]`, level `1` and change `-5e-17`, the real reduction is `5e-17` at `k = 1`,
`1 - exp(-0.5) = 0.3934693402873666` at `k = 1e16` and rounds to `1.0` at `k = 1e100`; the drives
of the rounded gaps differ by nothing, since `1 - 5e-17` rounds to `1`.

No proof bounds the magnitude's error. Generated tests over the accepted domain, with `k` up to the
largest double, scales up to `2^1022` wide and subnormal gaps and changes, compare every reported
value with an 800-digit evaluation of the real model on the same binary64 inputs, and assert its
sign, its bounds and a measured relative tolerance. Reported range endpoints approximate the real
range; they are not outward-rounded bounds certified to contain it. The theorem does not prove
that rounding preserves a close ranking comparison between two candidates.

With a known level but unknown change, `[drive(n)-1, drive(n)]` contains every reduction.
With both unknown, `[-1,1]` does. These are enclosures; their endpoints need not be attainable,
as a whole-scale band shows. Comparing a candidate's lower bound with a rival's upper bound
gives a conservative lead in the exact model even when they share an unknown level. It can leave
a choice unresolved that a joint model of that dependence would settle.

The drive-reduction idea follows [Keramati and Gutkin's homeostatic reinforcement-learning model,
equations 2 and 3](https://proceedings.neurips.cc/paper_files/paper/2011/file/9778d5d219c5080b9a6a17bef029331c-Paper.pdf).
The target band is GoalChainer's declared regulation rule. The choice of scale, band, exponent
and weight remains a domain assumption. Neither that paper nor these bounds establishes that
the chosen parameters express the operator's needs.

These theorems concern an immediate mathematical value. They do not prove causal attribution of
an observed change, empirical calibration of expectations, long-term convergence, goal preservation
or alignment. An action can have delayed effects or affect an undeclared need. Associational
pre/post observations do not resolve those possibilities. The arithmetic also grants no permission
or execution authority. Native floating-point correspondence requires separate tests; the exact-real
proof does not establish an error bound for the runtime.

## Evidence and observations

<!-- am[implements a-integrate-planning-evidence-lemma-1017@6f13e0] -->
### Planning conditions

[PlanningEvidence.lean](../proofs/PlanningEvidence.lean) models the opinion projection
`b + a*u`, where belief is `b`, uncertainty is `u`, and the base rate `a` lies in [0,1].
For nonnegative uncertainty, every projection lies in [b,b+u]. Exact simplex normalization,
`b+d+u=1`, identifies the upper endpoint with `1-d`. The projection bounds themselves do not
need that normalization premise.

A supported condition holds when its lower endpoint exceeds the chosen threshold. It fails
when its upper endpoint is below the same threshold. Otherwise it is undecided; equality at
either endpoint remains undecided. These two strict cuts cannot both hold, for any threshold.
A vacuous opinion has interval [0,1], so a large base rate alone cannot satisfy a condition.
Support records premise eligibility; it does not by itself satisfy the condition.

The computational upper endpoint is `b+u`. The runtime accepts simplex error up to 1e-9,
so substituting `1-d` would require a premise it does not enforce. For example,
`b=0.5000000000001`, `d=0.5`, `u=0` is accepted. At threshold `0.50000000000005`,
`b > threshold` and `1-d < threshold` are both true. The direct endpoints avoid that
contradiction without a tolerance or clipping rule. Lean checks the real-arithmetic bounds;
runtime tests must separately check the MeTTa implementation and floating-point boundaries.

The condition is a judgment within the evidence model. Neither its interval nor a hypothetical
proof route certifies external truth, attainable confidence, or expected value of computation.
An incomplete search remains undecided. Exhausting the caller's budget is an error, not
evidence that the condition fails.

### Observation identity and effects

Evidence identity prevents the same testimony from gaining independent weight through replay.
The native test resubmits a belief with one shared source ID and checks unchanged evidence,
opinion, receipts, event count and state digest on the real SNARS path. Identity deduplication
does not prove independence of different IDs. Two IDs copied from one observation remain
dependent testimony unless their producer preserves common provenance. Neither source IDs nor
estimator labels are cryptographic attestations.

Relevance signals distinguish detected, refuted, unknown and conflicted, read off the
justification kernel's labels for a review's readings. A claim the kernel accepts, of either
polarity and whatever its check, gives the signal that state and its fact. A valid positive and
negative reading of one estimator tier make a conflict, not a majority vote, and give no fact. A
contrary of a lower tier is overruled by the adopted source preference, not proved false: while
it is current it is contested, and the review escalates whenever the signal can affect it, while
the theory runs on the preferred polarity and the authority ceilings read only the supporting
readings' classes. Expiry withdraws support toward unknown, not toward false, and an expired
contrary is no disagreement. No positive fact follows from an unknown or conflicted signal. An
explicit negative reading is different from silence. The reading identity includes state,
estimator, source and observation/validity times; a note is excluded.

<!-- am[implements a-jk-rr-contract-doc-1018@257f7b] am[rests-on c-integrate-reading-owner-rule-1018@9de720] am[rests-on c-jk-aspic-defeat-preference-1018@f2a246] -->
The justification kernel labels each argument of one snapshot of evidence rows Accepted,
Refuted, Undecided or Unsupported. An argument is a claim `(Claim C)`, an observation
`(Observation O)`, a row `(Row R)` or a stated reason `(Stated X)`, and its role is the category
the rows give it, never its spelling. The labels are the well-founded model of AgenticMind's
argument rules, so a support cycle with no founded entry founds nothing, and an undercut that
protects its own reason stays Undecided. A row defeats each contrary row of its own or a lower
tier, and a row from an establishing source also refutes the contrary claim. The shared
vocabulary gives each estimator class its tier, and every class that establishes ranks above
every class that does not. This is GoalChainer's adopted defeasible source preference: it
decides which reading a caller proceeds on, and it does not establish that a measurement is
true. A withdrawal or an expired validity undercuts a row whatever its tier, so withdrawing the
preferred reading reinstates its contrary. These are ASPIC+'s two kinds of defeat: a rebut
succeeds unless the attacker is less preferred, and an undercut always succeeds (Definition 9
of [Modgil and Prakken](https://arxiv.org/abs/1804.06763v1)). A row's link reads Withdrawn once
the row is withdrawn or expired, while a current row that lost keeps a holding link, so a reader
tells an expired contrary from a defeated one. Two contrary readings of one tier leave both
claims Undecided. Accepted is an epistemic label and grants no authority, permission or
promotion. Checked is provenance, not confidence: an argument that is not refuted is Checked
when a standing establishing source holds it up through links that certainly hold, and a SNARS
opinion or a model-proposed reading never makes it Checked. A literal is known only from its
own or its contrary's accepted claim label, so a literal that no row claims is Unknown, never
False. Renaming a snapshot's literals injectively renames its answer and changes nothing else,
even when a literal is spelled like another argument or like the kernel's own bookkeeping.

The outcome policy keeps a completed application separate from evidence of its effects. Without
an establishing observation its predictions remain `predicted`. Model-proposed and
receipt-calibrated observations cannot establish an effect. Establishing observations that
disagree produce `conflicted`; unapplied actions leave predictions `not-attempted`. Measured,
deterministic and human-asserted observations can establish statuses only under the host's
premise that their attribution and contents are appropriate. A local simulated executor proves
its local transition, not successful delivery to an external system or overall goal achievement.

Cross-encoder scores remain rank scores. Applying a sigmoid constrains a number to [0,1] but
does not calibrate it to the truth of a proposition. Qwen's [primary model card](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)
describes a text-ranking model and its logit/sigmoid interfaces; it supplies no calibration for
GoalChainer's observations. Jev/NLI decisions and their provenance are a separate fallible
observation channel. The kernel checks conclusions conditional on supplied observations.

<!-- am[implements a-jk-pf-wire-docs-1019@78707b] am[rests-on c-jk-pc-agreed-1019@fd2f81] am[rests-on c-integrate-c1-currentness-boundary-1019@4ebdc2] -->
### Plans over the worlds the readings admit

The planner's model, [planning_oracle.py](../tests/planning_oracle.py), which
[PlanningModel.lean](../proofs/PlanningModel.lean) transcribes, holds what is known, each open
procedure instance's done steps, the instances some world may already have finished, the signals some
world may have moved since the readings, and the acts in flight. A world gives every signal a value and
holds the journal's instances. It settles by taking Finish and Derive moves, in every order, before
anything else. The worlds a snapshot admits are those whose settling, with no act landing, rests holding
every checked reading. An observed signal takes both values before that settling, since a reading sees only
the rest.

The plan theorem holds under four rules:

- R1: from the start and after each step, the model's own Finish and Derive moves must end in one rest
  state whatever their order, and no run of them may revisit a state. The planner refuses any other root.
- R2: the procedure reader refuses a library whose live undo graph has a cycle, as `cyclic-undo`. The graph
  has an edge from Derive d' to Derive d when d' writes the negation of a literal d writes without reading
  it, unless the two read opposite values of a signal no Derive writes.
- R3: the admitted rests classify each journal instance. One closed in every admitted rest is completed.
  Its Achieves literals that every rest holds join the knowledge as observations, and only a journal-only
  Finish closes it. One open in every rest stays open, and any other is uncertain.
- C1: a snapshot no world settles to is refused as `Contradicted`, naming its readings. An inquiry branch
  no world settles to is dead.

Under R1 and R3, `plan_sound` shows that every admitted world takes each step of an accepted plan at its
turn. The model's state embeds every world's at every turn, and every rest after the last step holds the
goal. With R2 and C1 added, `world_terminates` shows that every world's settling ends, and
`plan_nonvacuous` shows that every turn has a world, so the guarantee is never vacuous. The settle ends
within its measure (`settle_rounds`). Knowledge comes only from checked readings and the literals every
admitted world entails (`journal_sets_no_literal`). Every inquiry path is finite (`Answer.depth_le`).
The four counterexamples below show that each rule is needed: `r1_needed`, `r2_needed`, `r3_needed`
and `c1_needed` evaluate the model on their libraries.

<!-- am[rests-on c-jk-pf-conformance-boundary-1019@4ce337] -->
PlanningModel.lean's main checks the Lean model against
[a record of the oracle's answers](../tests/data/planning_model_conformance.json) for pinned and seeded
worlds. Each recorded case supplies a state and, as input, the oracle's classification of its instances:
which are completed, which are kept open and which literals are entailed. The Lean model observes the state
under that classification with `observeWith` and settles it. It then compares the settled start state, the
enabled moves and the state each move leaves with the oracle's. The check takes the classification as
given and does not derive or compare it. Its scope comes from elsewhere: `exactObservation_sound` proves
the exact classification sound, and the acceptance tests check the oracle's classification by running its
answers in every admitted world.
[record_planning_model_conformance.py](../tests/record_planning_model_conformance.py) writes that record,
and a test records again and diffs it. The acceptance tests compare the planner with the oracle. They also
run every plan, and the oracle's own answers, in every admitted world. The model covers one entity with no
port links, reactions that toggle one signal, and signal literals. It covers no statements, entity
bindings or track records, and the oracle refuses each where it enters. It refuses a statement or a signal
placed on an entity as a literal, and a domain that binds a proposition to an entity. It refuses an entity
reading among the readings the planner is given, and a library that declares a track promotion rule, the
only kind under which receipts can make a track hold.

The guarantee is relative to the snapshot the caller supplies. The planner and the model take every valid
checked reading as describing the world at the request's time. Refusing a reading observed after that time,
and reading one past its `valid_until` as unknown, do not establish that it postdates the acts the journal
records. C1 checks that the supplied readings are consistent, and it detects no stale reading: a reading
taken before an act changed what it saw is admitted whenever some world agrees with it, and a plan may rest
on it. Refreshing or omitting such readings before planning or admission is the caller's precondition
([planning.md](planning.md)).

## Separate PLN grading

`evidence_chainer.grade` evaluates caller-supplied named PLN statements and query targets
through PeTTaChainer's MeTTa library. Each result contains the beliefs actually proved for its
target. An empty collection means unproved; a strength-zero belief is a distinct answer.
Malformed collections raise a protocol error instead of becoming unknown evidence.

The recorded PeTTaChainer oracle and generated boundary tests compare the native provider's
answers with the library's prior engine behavior. They establish correspondence on those
inputs, not a calibration of PLN strengths and confidences as empirical probabilities.
The provider does not convert its values into SNARS evidence, review authority or host grants.

## Counterexamples that delimit the claims

| Rejected inference | Concrete counterexample |
| --- | --- |
| Ordinal order licenses arithmetic tradeoffs. | A=(2/3,2/3) beats B=(0,1) by sum. The strictly increasing relabeling 0→0, 2/3→0.1, 1→1 makes B beat A while all values stay in [0,1]. |
| Missing evidence is a neutral estimate. | If A has an unknown effect [-1,1] and B has -1/3, assigning A zero would falsely let A dominate B. |
| Priority authenticates permission. | An obligated proposal still reports authorization unresolved and applies no effects. |
| No proof means a false belief. | A PLN target with no proof returns an empty collection; a proved strength-zero belief remains a belief with its own proof. |
| A completion receipt confirms every predicted effect. | Apply an action with no observations: every outcome remains `predicted`; a model's assertion alone changes none. |
| An accepted reading is a true one. | A measured "detected" reading and a model-proposed "refuted" one: the kernel accepts the measured polarity by the adopted preference. Withdraw the measurement and the model's reading is accepted instead. Neither label observed the world. |
| Acceptance authorizes acting on the reading. | The same snapshot leaves the overruled reading contested and the review escalating when the signal can affect it, and a proposal still reports authorization unresolved. |
| An overruled reading still lends its class's authority. | In a domain that caps measured readings at advisory and receipt-calibrated ones at preauthorized, a measured "detected" reading and an overruled receipt-calibrated "refuted" one license advisory. Counting the overruled reading's class as support would license preauthorized. |
| No accepted reading of L means L is false. | With no rows for L, or with readings of L that conflict, `gc-justification-knowledge` answers `Unknown`. Only an accepted `(Claim (Not L))` gives `Known False`. |
| Successful formal checking settles the informal objective. | A scenario omitting privacy can satisfy every theorem while recommending disclosure. The operator must approve the declared goals and norms; the theorem cannot invent the missing requirement. |
| One order of the model's Finish and Derive moves shows what every world does. | SIMULTANEOUS: two Finishes enabled together write y and not-y. The planner at 1d48c6c planned the order ending in not-y, and a world taking them the other way rests holding y. R1 refuses that root. |
| A Derive cycle is harmless while the model never enters it. | SMALL_CYCLE: d1 and d2 toggle a once g holds, so every world that reaches the goal cycles and never rests. R2 refuses the library. |
| An instance the journal has open is open when the readings are taken. | TRANSIENT_FINISH: where x held, d1 fires and the instance's Finish runs before the readings, so a world rests with it closed and still agrees with every reading. R3 makes it uncertain. |
| A plan the model finds holds in some world. | MEASURED: with a detected and b refuted, derive_b makes b true, so no world rests holding the readings, yet the planner at 410fc76a planned. C1 refuses the readings. |
| `Contradicted` detects stale readings. | STALE_REACTION: a reading of not-s taken before k turned s true, supplied after k's receipt, agrees with a world where s was false all along, so it is admitted and the plan rests on it. |

## Running the checks

```sh
scripts/check-mathematical-contracts.sh
python -m pytest -q tests/test_mathematical_contracts.py
python -m pytest -q tests/test_planning_justification.py tests/test_evidence_chainer.py
python -m pytest -q tests/test_planning_acceptance.py
```

Run verification in a battery worktree with the repository's provisioned environment. The proof
checker uses `proofs/lean-toolchain` and the mathlib revision in `proofs/lakefile.toml` and its
generated Lake manifest. It fetches cached dependencies when absent and fails on missing Lean
or any checking error. `GOALCHAINER_MATHLIB_CACHE` may name an existing Lake workspace with the
same toolchain and exact mathlib commit; the checker validates both pins before using it. This
variable changes dependency reuse, not the theorem source. The full release gate includes the
proof checker as well as pytest. No proof is silently skipped.

Lean proves statements over exact real arithmetic. It uses mathlib's standard foundations and
kernel-checked tactic proof terms, with no new axioms or unfinished proofs for these contracts.
The checker prints the axioms of the principal theorems. See mathlib's [linear arithmetic tactic
source](https://github.com/leanprover-community/mathlib4/blob/d90090f647cae4f4ad4da99c0ac8bab2ca8c34ab/Mathlib/Tactic/Linarith.lean).

MeTTa and Python execute floating-point arithmetic. The correspondence tests use explicit
tolerances where exact equality is not warranted. These tests are finite correspondence evidence.
They do not prove an IEEE 754 error bound for arbitrary inputs or strict order preservation for
arbitrarily close floating-point values. Overflow or a malformed transport result is an error, not a
licensed fallback. A review budget bounds resource use and can produce a typed failure; it
does not guarantee a successful review, an available actuator or eventual goal attainment.

Normative fact lifecycles and mediated enforcement have existing precedent. [NPL](https://github.com/moise-lang/npl)
separates normative state from externally implemented sanctions. Criado et al.'s
[electronic-institution account](https://www.iiia.csic.es/media/filer_public/b1/d3/b1d3d503-7cad-44c8-97dc-f3e4e8bfb547/4547.pdf)
limits regimentation to mediated channels. The corresponding boundary here is the checked
policy and its host interface; external actors and observations remain outside that boundary.

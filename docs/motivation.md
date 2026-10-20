<!-- Purpose: teach need-based review through a recorded host cycle and explain its evidence, numerical, persistence and authority contracts. -->
<!-- am[implements a-v2-docs-1019@6301a6] am[related a-v2-examples-1019@2d047f] -->
<!-- am[implements a-v2r-guides-1020@0b367f] -->
# Review against observed needs

An action can help once and become unnecessary after it succeeds. A domain can
declare a measured quantity, a target band and the changes its actions are
expected to make. GoalChainer then reviews the reduction in distance from that
band. It reads observations from a motivation stream; the host decides whether
to act and reports what happened.

Run the Companion example from the repository root after
[installing the pinned runtime](../README.md):

```sh
uv run python examples/motivation/cycle.py companion \
  --directory ai-tmp/motivation-companion \
  --inference-budget 1000000000 --timeout-seconds 600
```

The limits are an allowance for each request in this example, not application
defaults. The driver saves every request and result beside its SQLite stream.
It uses synthetic observations and calls no model, sensor or external tool.

| Review | Input | Decision |
| --- | --- | --- |
| `01-unobserved` | No need observation | Escalate for missing evidence. |
| `03-before` | Activation is `0.9`; target band is `[0.4, 0.6]` | Propose `guide_breath`, whose declared change is `-0.4`. |
| `07-after` | The host reports activation `0.5` after its attempt | Hold: activation is in its band. |
| `08-repeat` | The same evidence | Hold again, without recording an attempt. |

Inspect the third review with the normal renderer:

```sh
uv run goalchainer show --input ai-tmp/motivation-companion/03-before.result.json
```

The action named in the demonstration's attempt is a separate, explicit host
input. The program does not execute the proposal. Every review keeps
`authorization: "unresolved"` and `applies_effects: false`.

## Declare a quantity and its target

The [Companion domain](../examples/motivation/companion.metta) includes:

```metta
(gc-goal comfort person individual 1
  "Keep reported activation in the person's chosen band."
  (priority-source human:participant))
(gc-need activation comfort
  (scale 0 1) (band 0.4 0.6) (drive 1)
  (need-source human:participant))
(gc-need-expectation guide_breath activation -0.4 human-asserted
  (expectation-source human:demo-designer))
```

`activation` regulates the declared goal `comfort`. Its importance is that
goal's existing priority, here `1`. Observations never change the priority or
its provenance. Each goal can have at most one need. Goals without a need keep
their ordinary band appraisal.
The nonnegative goal priorities, added in declaration order, must have a finite
sum, so the review can record the aggregate of an action that serves them all.

The scale and band are finite numbers with
`LO < HI` and `LO <= LOW <= HIGH <= HI`. The scale's width and twice that width
must be finite binary64 values. The drive exponent `K` is finite and at least
`1`. An expectation is a signed change in scale units, with magnitude no larger
than the scale's width, and names its estimator and source. A missing
expectation is unknown, not zero.

These declarations are part of the domain digest. The example's numbers are
illustrative; they are not evidence that a breathing exercise causes the stated
change or that the band suits a particular person.

## Record observations and host attempts

The example saves ordinary request JSON. You can send it through the CLI:

```sh
uv run goalchainer motivation \
  --input ai-tmp/motivation-companion/02-observe.request.json \
  --inference-budget 1000000000 --timeout-seconds 600
```

The request has this shape:

```json
{
  "operation": "observe",
  "domain": {"path": "examples/motivation/companion.metta"},
  "motivation": {"store": "ai-tmp/motivation-companion/companion.sqlite3", "stream": "companion"},
  "observations": [{
    "need": "activation", "level": 0.9, "scale": [0, 1],
    "estimator": "human-asserted", "source": "host:synthetic-demo",
    "observed_at": "2026-10-20T09:00:10+00:00"
  }]
}
```

`attempt` takes an `attempts` list instead. Each item names `attempt`, `action`
and `applied_at`; a null `applied_at` says the host did not apply it. An optional
`review_fingerprint` names the review the host considered. A later observation
can name that attempt with `produced_by`. Neither field proves execution or
causation: both are statements supplied by the host.

`status` takes `as_of` instead of a record list and returns the stream's
snapshot at that instant. The timestamp must carry a timezone. Its optional
`through` count limits the read to a recorded prefix for an
[audit of an earlier review](motivation-persistence.md#audit-an-earlier-review).

The Python entry is
`goal_chainer.motivation.run_motivation_request(payload, budget=budget)`.
The OmegaClaw skill is `goalchainer-motivation-dispatch`; its JSON envelope
also requires `inference_budget` and `timeout_seconds`.
<!-- am[implements a-v2-skill-utf8-1020@3763d0] am[implements a-v2-motivation-input-order-1020@d40cf5] -->
The CLI and skill read UTF-8 JSON regardless of the process locale. The store
path and stream id must be nonempty UTF-8 text. A malformed selection is
refused as `invalid_input` before loading the domain. A domain request also
checks that its selected store can be read before asking the semantic reader
to interpret text.
The [persistence guide](motivation-persistence.md) specifies the record fields,
keys, file controls and Python store methods.

## Review the stream

Add the same `motivation` object to a normal `review`, `plan` or `admit`
[domain request](planning.md). The review reads the stream at
`context.as_of`; planning and admission continue to consume their own declared
readings, procedures and receipts. A motivation observation is not a planner
fact or a receipt for a procedure.

The packet-based commands take the same selection in a JSON file:

```json
{"store": "ai-tmp/companion/companion.sqlite3", "stream": "companion"}
```

Save it as `motivation.json`, then pass `--motivation motivation.json` to
`goalchainer relevance review --packet PACKET.json` and
`goalchainer relevance check --packet PACKET.json --review REVIEW.json`.
Both commands also need the matching `--domain-file`. They read the snapshot
at the packet's `as_of`, under the packet's budget. A changed snapshot reports
`motivation_changed`; an observation later than `as_of` does not change it.
A review naming a stream must be checked with that stream. Leaving it out or
selecting another stream is refused as `invalid-motivation`.

Before the first record, omit `motivation` from a review request. The needs are
then unobserved. A `status` request or a review naming a path with no store is
refused and creates nothing. An empty observation or attempt list also creates
nothing and answers empty `recorded` and `already_recorded` lists.

The snapshot chooses the latest observation at or before `as_of` on the declared
scale. If the latest observation has expired, an older one does not revive.
Simultaneous readings with different levels are conflicted. Missing, expired
and conflicted levels remain unknown.

For an applied attempt, a sample needs a baseline valid when it was applied
and an attributed outcome observed afterwards, no later than the next applied
attempt anywhere in the same stream. The next attempt closes that window for
every need, regardless of action. An outcome must be valid at its own instant.
A `status` snapshot reports excluded observations. For attributed observations
that reach sample evaluation, `not_sampled` names the attempt, need and first
failed rule, including simultaneous attempts. Attempts with no attributed
observation and observations attributed to declined attempts do not
appear in that list. The review keeps counts and evidence digests, with the
history reference needed to recover the snapshot's details.

The expected change is the mean of the usable pre/post changes for that action
and need. Without a sample it uses the declared expectation, or remains
unknown. Sample ids prevent duplicate counting; event arrival order and
batching do not change the result. These are host-attributed associations.
Other actions, changing conditions and measurement error can confound them.

## How the review decides

Norms and duties are evaluated first. A better predicted reduction cannot
override a prohibition or harm to a required goal. A duty remains a duty when
the needs are satisfied.

For a known level `n`, define:

```text
D = max(LOW - LO, HI - HIGH)
x(n) = distance from n to [LOW, HIGH] / D
urgency(n) = x(n)^K
value(action, need) = goal priority * (urgency(n) - urgency(clamp(n + change)))
```

When the target band covers the whole scale, distance and urgency are zero.
On scale `[0, 1]`, band `[0.4, 0.6]`, `K = 1` and priority `1`, level `0.9`
has distance `0.75`. A change of `+0.1` scores `-0.25`; a change of `-0.4`
scores `+0.75`. Increasing a quantity is not inherently an improvement.

Unknown levels or changes give intervals. The review compares a candidate's
lower bound with another candidate's upper bound. Shared unknowns are treated
independently for this comparison, so it can defer a decision that a more
precise dependency model might settle.

In a domain declaring needs, with no duty in force, a discretionary candidate
whose paths all have nonpositive upper bounds is removed as unmotivated. If no
candidate remains, `hold` names satisfied needs and unserved needs outside
their bands. An unserved need may have an action that reduces it when the
goal's priority is zero: its weighted reduction is still zero. An unknown or
conflicted need turns a would-be hold into an escalation. If a selected
candidate might fail to improve its aggregate motive, the review also escalates.
An unregulated goal with a positive path can still
justify an action when the regulated needs are satisfied.

`hold` is a review disposition, not an instruction to execute `stay_silent`.
Host withdrawal is separate: this module stores no proposal lifecycle and
cannot reactivate something the host withdrew.

Need levels and expectations contribute evidence limits to the licensed
authority ceiling. A reduction of zero still depends on the level and
expectation used to compute it, so their limits remain.

Each `proposal.predicted_need_changes` entry distinguishes the observation from
the prediction:

| Field | Meaning |
| --- | --- |
| `observed_level` | The current observed level, or `null`. |
| `level_state` | `observed`, `unobserved`, `expired` or `conflicted`. |
| `expected_change` | The declared or learned change, or `null`. |
| `predicted_level` | The clamped target interval, with `low` and `high`. |
| `reduction` | The predicted reduction in urgency, with `low` and `high`. |

For the Companion proposal, observed level `0.9` and expected change `-0.4`
give predicted level `{"low": 0.5, "high": 0.5}`. An unknown current level gives
the clamped images of the scale's endpoints; an unknown change gives the whole
scale. The entry's `status` is `predicted`. Reviewing never writes its target
back as an observation. The proposal's reduction endpoints are rounded to six
decimal places for display; the snapshot retains the computed endpoints.

## Identity, bounds and retries

The review fingerprint includes the motivational evidence relevant to its
candidates when the domain declares needs. SHA-256 commitments name the level
support and sample keys. A new supporting observation can change the
fingerprint even if its level is unchanged. Freshness recomputes that evidence
for the review's instant; changed motivational support is reported as
`MOTIVATION` moving.

The review's `motivation.history` names the event count and digest used for the
decision. It is an audit reference outside the fingerprint: appending an event
that changes none of the decision's evidence leaves the review fresh. Reviews
keep compact evidence summaries; `status` returns the full support, samples
and exclusions. The [persistence guide](motivation-persistence.md#audit-an-earlier-review)
explains how to recover them after later appends, including backdated ones.

Review records use `goalchainer-relevance-review-v2`, which includes `hold` and
the motivation fields. Version 1 review records are refused as
`invalid-record`; there is no record migration. Produce a new review. Motivation
requests have their own protocol, `goalchainer-motivation-request-v1`, and their
store has schema version 1 in a separate file from a SNARS store.

A request uses one cumulative budget for domain loading, store access and
native reasoning. History reads check it while reading and validating events;
SQLite lock waits use the remaining deadline.
A write validates every record and checks the remaining budget before opening
the store. The batch then commits as a whole or rolls back. The write-lock
wait and pre-commit budget check belong to the store. After commit, the Python
request returns its keys; the surrounding CLI or skill can still detect a
deadline that passed while returning the answer. A timeout or a lost answer
therefore does not prove the batch was absent. Resend the identical batch:
`already_recorded` identifies keys that committed. A different payload under
an existing attempt id is refused.

## Numeric and empirical limits

The real formulas are checked in Lean, including the exact breakpoint range
for a known change and an unknown level. The real model uses the binary64
values read by the engine as its inputs. A decimal in a file may round when it
becomes such a value.

The runtime evaluates the candidate construction in floating point. It keeps
gap differences as floating-point expansions to distinguish an exact zero
from a small improvement or worsening. Urgencies stay in `[0, 1]` and
reductions in `[-1, 1]`. A nonzero result smaller than `2^-1022` in magnitude
may round to zero; the policy does not turn that underflow into the opposite
sign. Magnitude accuracy is checked against a high-precision reference, not
proved. The interval endpoints are not a certified outward enclosure, and
there is no proved IEEE error bound.
`K >= 1` bounds the real urgency's sensitivity by `K`; that is not a bound on
floating-point evaluation error. Interval display midpoints avoid adding two
large endpoints before halving. They are display projections, not the
comparison rule. See [mathematical contracts](mathematical-contracts.md).

The design selects need regulation and observed-outcome appraisal from
[Mikeda and Goertzel's motivational architecture](https://arxiv.org/abs/2606.05411).
It does not claim the paper's full cognitive architecture, contraction, goal
stability, emotional experience or an alignment guarantee. The example checks
decision behavior, not whether its synthetic scales or expectations predict
human outcomes.

## Use the same mechanism for research

```sh
uv run python examples/motivation/cycle.py research \
  --directory ai-tmp/motivation-research \
  --inference-budget 1000000000 --timeout-seconds 600
```

The [Research domain](../examples/motivation/research.metta) regulates evidence
coverage. It proposes gathering public evidence at coverage `0.2`, then holds
after the host reports `0.85` in the target band `[0.8, 1]`. Reading private
notes has the largest declared improvement, but a prohibition removes it
before motivational comparison. The shared driver changes only the domain and
host inputs; it contains no domain-specific decision code.

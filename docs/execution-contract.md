# Memory admission and the incident example host

<!-- am[implements a-ev-consumers-docs@5cfd14] -->
<!-- am[implements a-ie-s5-incident-host-1018@53176a] -->
A domain request reviews, plans or admits; it never authorizes a step and never
applies one ([relevance review](relevance-review.md)). What happens next is the
host's. This page describes two pieces on either side of that boundary: the
memory admission boundary, which decides what caller-supplied memory items say
before any reasoning reads them, and the incident example's host adapter, which
prepares and checks the artifact for a reviewed proposal from an incident record
its caller supplies. It ends with a migration table for callers of the retired
`solve_incident` and `decide_incident`.

GoalChainer sends nothing. A host may release an artifact whose privacy check
passed, after its own adjudication. Only the host's receipt can confirm that the
effect happened, and only an observation of a goal's state can show that the goal
was achieved.

## Memory admission

`goal_chainer.memory_evidence.admit_memory_evidence(items, candidate_actions, ...)`
is the one boundary memory items pass through. Python decodes each item and checks
its types; `src/goal_chainer/policy/goalchainer_memory.metta` decides what the
item means, from which slots are read to which copy of an identity is kept. It
reads two slots that the petta-memory handoff cache stamps on acceptability
evidence:

| `goalchainer_slot` | `atom` |
| --- | --- |
| `acceptability-belief-evidence` | `(Acceptable <action>) (STV <strength> <confidence>)`, optionally wrapped as `(: <name> (Acceptable <action>) (STV <s> <c>))` |
| `contextual-appraisal-evidence` | `(EvidencePacket (Acceptable <action>) (EC <support> <opposition>) ...)` |

An item with no `goalchainer_slot` that carries `content` text, as WMTM's
`{id, content, sti}` items do, is a memory text: the admission reports it for its
consumer to read, and `memory_text_omissions()` names the reader failures,
`not_cached` and `refused`, that leave such a text unread rather than failing the
consumer. A domain request takes no memory items today, so nothing in the request
path reads an admission yet.

Every received item gets exactly one disposition, reported under
`dispositions` with its index:

| Status | Reason | Meaning |
| --- | --- | --- |
| `admitted` | `Admitted` | The item is evidence about its action. |
| `text` | `ContextText` | The item is a memory text, for its consumer to read. |
| `duplicate` | `SameIdentity` | Another item carries the same identity; `representative` names the kept one. |
| `duplicate` | `SameAsRequest` | The item's text is the request itself, which is read already. |
| `ignored` | `NoGoalChainerSlot` | The item has neither a `goalchainer_slot` nor text, so it is no evidence. |
| `ignored` | `SlotNotConsumed` | The slot belongs to another consumer of the handoff cache. |
| `ignored` | `NotACandidateAction` | The atom is about an action the caller did not name. |
| `empty` | `ZeroEvidence` | The item carries no evidence weight. |
| `empty` | `BlankText` | The item's text is blank, so it says nothing. |

An item in a consumed slot that cannot be read raises `MemoryEvidenceError`
(error code `invalid_input`) before any reasoning runs, with the item's index in
`details`. That covers a non-mapping item, an atom of the wrong shape, a number
that is not finite, a strength outside [0, 1], a confidence outside [0, 1), and a
provenance field that is empty or padded with whitespace, and an unslotted item
whose `content` is not text. A confidence of 1 would claim unbounded evidence,
which recalled testimony never has.

An item's identity is its `belief_id`; without one, its `cluster_id` and
`promotion_event` together; without those, a digest of its parsed evidence. One
identity is one piece of evidence however often the cache repeats it, so the
boundary keeps one representative per identity: the STV value first, then the
lowest confidence. An identity that carries evidence about two different actions
is malformed and raises. A memory text's identity is a digest of its content,
which only removes copies of it: it implies no independence.

Evidence weight follows the convention PR 2 and SNARS share: confidence c is
w / (w + 2) for w units of evidence, so an STV item contributes w = 2c / (1 - c)
units split by its strength, and an EC packet contributes its counts directly.

## The incident example host

`goal_chainer.examples.incident` is the incident example's host adapter. A caller
selects it by importing it; no other GoalChainer module imports it, which
`tests/test_incident_host.py` checks. It acts on a review record's proposal, never
chooses an action, and prepares only what its caller's incident record holds:

```python
from goal_chainer.domains.loader import packaged_domain
from goal_chainer.examples.incident import Authorization, prepare_proposal
from goal_chainer.relevance import review

reviewed = review(packaged_domain("incident", budget=budget), packet, budget=budget)
stored = reviewed.to_dict()
# Later, acting on the stored review: `current` is the packet for the same subject as it reads now.
approval = Authorization(True, "HostApproved", "incident-host", "The on-call lead approved the update.")
execution = prepare_proposal(stored, record, approval, packet=current, budget=current.budget.run_budget())
```

`record` is the host's incident: `service`, `status`, `summary`, `next_update` and
a `raw_log` mapping of field names to values. `prepare_proposal` refuses a record
that is not a review record, a review that proposes nothing (its disposition is
`escalate`, `blocked` or `no-candidates`) and an authorization that is not one.
<!-- am[implements a-integrate-example-host-inputs-1018@f0d0fa] -->
Before it prepares anything it checks the four fields it reads, in the shapes a
review record carries them: `review_id` and `fingerprint` are text, the proposal
is an object whose `action` is an action this host prepares and whose `deontic`
is one of `forbidden`, `obligated`, `permitted`, `conflict` and `unregulated`.
Any other value is `InvalidInputError` naming the field, whether the step was
authorized or declined.
<!-- am[implements a-ie-host-freshness-1018@ff618a] -->
Then it checks the stored review against `current`, the review packet for the
review's subject as it reads now, with `relevance.check_freshness` under the
packaged incident domain and the engine identity the process runs
(`relevance.engine_identity`), loading lib_deontic within the budget if the
process has not yet. The budget is no looser than `current`'s bounds. A review
whose support moved is `StaleReview` (`stale_review`), whose details are the
freshness report naming what moved, granted or declined; a packet about another
subject is relevance's `subject-mismatch`, and a stopped budget or an unreachable
engine keep relevance's codes. A stale review says nothing about which outcome is
right, so the host prepares nothing and a new review decides.
<!-- am[implements a-ie-host-recompute-proposal-1018@898c26] -->
Freshness compares what the review was decided from, not what it decided, so a
fresh record can still carry a proposal the review never made. The host therefore
runs the review again, `relevance.review` on `current` under the packaged incident
domain and the same budget, and requires the stored proposal's `action` and
`deontic` to be the ones that review proposes. A stored proposal it does not
reach, including one it replaces with nothing (an `escalate`, `blocked` or
`no-candidates` disposition), is `InvalidInputError` whose details hold both
outcomes, granted or declined, and the review's own failures keep relevance's
codes. Only that review decides: the record's candidates, readset and other fields
decide nothing the host prepares. This checks that the consumed outcome agrees
with the current evidence and norms, not that the record is authentic: the
`review_id` and `fingerprint` the execution's readset names are the caller's, and
the authorization stays the host's own. The budget pays for both checks and the
artifact's policy reads. An authorized step for a `forbidden` or `conflict`
proposal is refused next, a check of the host's own settlement policy, before its
artifact exists; the review's ranking never proposes such an action.
An authorized step prepares the proposed action's artifact with
`prepare_artifact(action, record, budget=...)`: the redacted summary, the raw log,
or an internal hold note. A declined step prepares nothing and never reads the
record. The execution's `readset` names the review it acted on, by `review_id`
and `fingerprint`.

### The execution result

`execution` follows the contract `goalchainer-execution-v1`. It records a few
primitive inputs, the action, its norm, the host's authorization and the prepared
artifact, and the host's settlement policy,
`src/goal_chainer/examples/incident/settlement.metta`, derives every other facet
from them when the result is made, so the facets cannot disagree. Each facet is a
condition with a `status` of `true`, `false` or `null`, a machine `reason` and a
`message`, after Kubernetes status conditions. `null` means nothing observed
settles the facet; it is never a refutation, and a consumer testing the status for
truth reads it as not established.

| Condition | True when | Reasons |
| --- | --- | --- |
| `Admissible` | The proposal's norm is neither `forbidden` nor `conflict`, the pinned blocking cut. | The norm, e.g. `Obligated`, `Forbidden`. |
| `Authorized` | The host authorized the step. | The host's own reason, e.g. `HostApproved`, `HostDeclined`. |
| `ArtifactPrepared` | The host prepared an artifact. An artifact exists exactly when the step was authorized. | `Prepared`, `NotAttempted`. |
| `PrivacyVerified` | The containment check found none of the record's restricted raw-log values in the artifact. `null` when nothing was prepared. | `NoRestrictedValues`, `RestrictedValuesFound`, `NotAttempted`. |
| `ReleaseEligible` | The artifact may be released to its audience, which requires a passed check. | `PrivacyVerified`, `PrivacyCheckFailed`, `NotAttempted`. |
| `EffectConfirmed` | Never set by GoalChainer, which performs no host effect. | `AwaitingHostReceipt` for a releasable artifact, `NoEffectExpected` otherwise. |

An authorization for an inadmissible norm is refused when the result is made.

The privacy check is fail-closed. A withheld artifact keeps its digest and the
names of the leaked fields, never the payload: it is dropped when the check
fails, so no caller can publish it. The settlement policy keeps the values of
three diagnostic fields, `error_code`, `failure_mode` and `affected_surface`, and
restricts every other raw-log field, so a field nobody listed is redacted and
searched for. The check covers the values listed in `covered_fields`, the
restricted fields with nonempty values, searched in the artifact's JSON. A pass
says those values are absent; it is not a proof about sensitive information of
any other kind.

The check regiments only what passes through the host adapter. Regimentation
makes a violation impossible only on a channel the mediating entity controls
(Criado et al., [Norm enforceability in Electronic
Institutions?](https://www.iiia.csic.es/media/filer_public/b1/d3/b1d3d503-7cad-44c8-97dc-f3e4e8bfb547/4547.pdf),
§2.1 p.3 and §2.3 p.4). The adapter mediates its own preparation: an artifact
leaves it releasable only after its check passes. It does not mediate the host's
channels, so it can neither prevent nor observe a disclosure made elsewhere. That
is why `EffectConfirmed` stays `null`; the host records what it did and saw in a
receipt, which the review's receipt assessment checks against the proposal.

For the incident record in `tests/incident_support.py`, a review whose readings
support sensitive data and refute unverified facts proposes the obligated
redacted summary, and the host's approved step settles to:

```json
{
  "contract": "goalchainer-execution-v1",
  "action_id": "publish_redacted_summary",
  "norm_status": "obligated",
  "conditions": {
    "Admissible": {"status": true, "reason": "Obligated"},
    "Authorized": {"status": true, "reason": "HostApproved"},
    "ArtifactPrepared": {"status": true, "reason": "Prepared"},
    "PrivacyVerified": {"status": true, "reason": "NoRestrictedValues"},
    "ReleaseEligible": {"status": true, "reason": "PrivacyVerified"},
    "EffectConfirmed": {"status": null, "reason": "AwaitingHostReceipt"}
  },
  "artifact": {
    "kind": "redacted-status-update",
    "audience": "external",
    "privacy": {
      "covered_fields": ["access_token", "customer_email", "order_id", "request_payload", "stack_trace"],
      "leaked_fields": [],
      "passed": true
    }
  }
}
```

When the record's summary quotes the customer's email address, the same step
withholds the artifact: `ReleaseEligible` is `false` with reason
`PrivacyCheckFailed`, `artifact.payload` is `null`, and `leaked_fields` is
`["customer_email"]`.

## Migration from the retired solve

| Earlier | Now |
| --- | --- |
| `pipeline.solve_incident(request, ...)` and `decide_incident(...)`, with native and offline modes | A domain request (`goalchainer request`) reviews the packaged incident domain; the host acts on its proposal with `goal_chainer.examples.incident.prepare_proposal`. |
| `execute.default_incident()`, the built-in incident | Removed. The host supplies its own record. |
| `execute.execute_action(action, incident)` | `goal_chainer.examples.incident.prepare_artifact(action, record)`; an unknown action or a malformed record is `InvalidInputError`. |
| `execution_models` and `policy/goalchainer_settlement.metta` | `goal_chainer.examples.incident.execution` and `examples/incident/settlement.metta`, in a module group of their own. |
| `Authorized` from a directive claim, an automatic ranking or read memory texts | The host's own `Authorization`; a directive claim is a plan step, never an authorization. |
| `goals`, each goal's coverage and unverified achievement | The review's `required_goals` and its proposal's `predicted_contributions`, which stay predicted until a receipt's observation. |
| `feedback`, the privacy outcome believed into SNARS | Removed. A host records its observations in a receipt for the review's receipt assessment. |
| `memory_evidence.memory_unread_denial` and `MemoryTextReading` | Removed with the decision that reported them. |
| `incident`, the record's field names | Removed with the solve report. |

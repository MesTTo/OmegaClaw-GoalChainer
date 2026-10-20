# Native SNARS migration and rollback

<!-- am[implements a-ie-s7-docs-1018@83a871] -->
## What SNARS does

A SNARS session (`goal_chainer.snars_reasoner.SnarsSession`, or the
`goalchainer snars` command) keeps what its caller and its readings say as SNARS
evidence:

1. the semantic reader reads request text into supported, contradicted or
   unknown readings of the propositions a domain declares,
2. the reading policy believes each source's readings of each declared
   proposition once, as the statement `(has-property "request" ID)`, from the mean
   of the evidence they assert ([semantic reader](semantic-reader.md)),
3. the session's operations (`belief`, `ask`, `prove`, `explain`, `truth`,
   `condition`, `obligations`, `what-if` and the rest) read and derive from that
   evidence, keeping evidence counts, receipts, trust, proof stamps and proof
   trees.

SNARS holds no domain's knowledge. Its policy states no property of any action
and registers no rewrite rule, so a session believes only its readings, what its
caller believes, and what SNARS's own syllogistic rules derive from them. What a
domain allows is its review's: a domain request (`goalchainer request`) reviews,
plans or admits against the selected domain's deontic theory and runs no SNARS
session ([relevance review](relevance-review.md)).

SNARS runs in-process on pymetta from the library GoalChainer's package carries, each
batch inside a speculation that discards what it wrote. The answers PeTTa gave a
scripted session's batches before GoalChainer retired it are kept in
`tests/data/snars-executor-petta.json`, and the tests compare the in-process answers
with them.

## Migration from the incident assessment

The SNARS layer used to carry the incident example's knowledge: three action ids,
their properties and the rules that derived `acceptable`, `risky` and `forbidden`
for them from the request's readings. Those leave with the decision paths that
read them.

| Earlier | Now |
| --- | --- |
| `goalchainer solve` and `goalchainer demo`, native or `--mode offline` | Removed. `goalchainer request` reviews, plans or admits against a domain; the incident example's host acts on a review's proposal ([execution contract](execution-contract.md)). |
| `goalchainer snars assess --request TEXT`, the request context and the three incident action assessments | Removed. Read what a session believes of a declared proposition with `explain` or `truth` and the proposition's statement, for example `goalchainer snars --inference-budget 1000000000 --timeout-seconds 600 explain --domain incident --request TEXT --statement '(sn p so "has-property" ((arg s (sn c "request")) (arg o (sn c "sensitive-data"))))'`. The `assess` operation has also left the JSON dispatch's `evidence` group. |
| `goalchainer snars` reading `--request TEXT` with the incident domain's section whatever the caller asked | Text is read with the section of the domain the caller selects, `--domain NAME` or `--domain-file PATH` on the command line and `"domain": {"packaged": NAME}` or `{"path": PATH}` in the JSON dispatch. Text with no domain is refused, as is a domain that declares no reading section; an operation on statements alone needs no domain and answers as it did. |
| `SnarsSession.request_context()` and `SnarsRequestContext` | `SnarsSession.belief(statement)` of each declared proposition's statement, which answers the same belief record the context held. |
| `SnarsSession.assess_actions()`, `SnarsActionAssessment` and `SnarsActionReasoner` | Removed. A domain's review gives each candidate action its deontic standing. |
| `snars_protocol.parse_assessment` and `parse_request_context` | Removed with the records they parsed. |
| The policy's `(gc init-policy!)` action facts and its rules `gc-raw-risk`, `gc-risk-forbidden`, `gc-redacted-acceptable`, `gc-safe-coordination-acceptable`, `gc-hold-unverified-acceptable` and `gc-protection-acceptable` | Removed. The incident domain's deontic theory decides the incident norms. |
| `(gc concept-collisions)`, `(gc free-subject-concepts)` and `(gc request-reading-concepts)` | Removed: with no rewrite row in the policy, no declared id can collide with one. |
| `(gc action-property SUBJECT PROPERTY)` | `(gc has-property SUBJECT PROPERTY)`, the relation every reading is believed in. |

## Data compatibility

<!-- am[implements a-integrate-request-budget-surface-1018@d6882c] -->
Every SNARS command and session takes one request budget. CLI callers supply
`--inference-budget` and `--timeout-seconds`; reasoning skills send a JSON object
with `request`, `inference_budget` and `timeout_seconds`. Python callers construct
`goal_chainer.runtime.budget.RunBudget` once and pass it as `budget=budget`.
The original request text stays unchanged. Every batch of a session spends that
same allowance; a batch cannot reset it. Missing limits are input errors,
and exhausted limits raise the existing typed budget or timeout error.

Persistent stores record the SNARS identity, a digest of the packaged SNARS
library and its Python helpers. Opening a store under a different SNARS fails
before replay. Keep the old release available until a planned migration has been
tested against a copied database.

The current event schema is append-only version 3. There is no silent schema or
identity migration. The policy is not part of the identity, so a version 3 store
written before the incident assessment left still opens: its readings replay into
the same beliefs, and no action property is believed or derived from them.

## Rollback

To roll the code back, revert the GoalChainer commits. SNARS ships in the
package, so the revert also restores the SNARS an older store was written
against. Do not open a newer event store from the older code. Keep a copy until
the rollback has been exercised.

## Failure behavior

<!-- am[implements a-integrate-cli-typed-errors-1018@160cf8] -->
Dependency, parser, timeout, engine, protocol, and persistence failures return
`{"ok": false, "error": {"code": "...", "message": "...", "details": {}}}`
and a nonzero CLI exit. Errors can occur after engine work; this envelope makes
no claim about whether SNARS ran.

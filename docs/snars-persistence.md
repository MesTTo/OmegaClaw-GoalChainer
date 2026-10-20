<!-- Purpose: explain native query results, stored evidence, database identity and privacy controls. -->
# SNARS persistence and privacy

Persistence is opt-in. A command without `--database` uses SQLite in memory and
discards the event stream when the session closes.

## Stored data

A persistent event can contain:

- the original request, and each memory text read into its context
- the semantic reader's `gc-reading` facts for each text, one per reading proposition, each
  with the passage of the text that grounds its answer, quoted verbatim
- evidence source names and trust, and a base rate only where the caller gave one; evidence
  stored without a rate replays at SNARS's configured default, `(sn config default-rate)` in
  the packaged library's `snars/config.metta`
- authored statements
- goals and their metadata
- temporal ticks
- observed outcomes

Requests can contain personal or operational data. Choose a database path with the
same care as an incident log.

<!-- am[implements a-integrate-ecan-forward-query-interface-1017@2afce8] -->
<!-- am[implements a-integrate-parent-artifacts-compose-1018@e3c6d7] -->
## Budgeted forward queries

`SnarsSession.forward_query(statement)` searches for the first
supported answer to a ground statement. It replays the session's events, then uses
query-directed attention to order native SNARS inference work. Open the session
with the request's `RunBudget`; every operation consumes that same allowance.
Inspect its `spent` count afterwards:

```python
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.snars_reasoner import SnarsSession

budget = RunBudget(inference_budget=20_000_000, timeout_seconds=60)
statement = '(sn p so "is" ((arg s (sn c "alpha")) (arg o (sn c "gamma"))))'
with SnarsSession.persistent("observations.sqlite3", budget=budget) as session:
    answer = session.forward_query(statement)
print(answer.payload, budget.spent)
```

`Witness` means a receipt or proof supports an available opinion. That opinion
can be positive, negative or vacuous. `Incomplete` means the retained frontier
ran out of work. Neither result certifies the strongest proof or authorizes an
action. Exhausting the inference or wall-clock budget raises
`InferenceBudgetExceeded` or `ReviewTimeout`.

The query stores no event. Its generated statements, proofs, attention values and
frontier disappear when the operation returns or raises; its result contains the
witness found inside that speculative world. A later ordinary `ask` replays only
the session's stored events. A session belongs to one request; several queries
within it use what remains. The budget's inference count covers event replay
and query execution. Preparing a world is charged to its wall-clock deadline.

The CLI operation is `goalchainer snars forward-query --statement '...'`, with
`--database` for an existing store. Every SNARS command requires
`--inference-budget` and `--timeout-seconds`. JSON skill dispatch places
`forward-query` in the `evidence` group and carries those limits as
`inference_budget` and `timeout_seconds` in its request envelope. Both report the
answer and charged inferences under `result`. The existing `--budget` remains the
step count for `control` and `temporal`; it does not replace either resource limit.

<!-- am[implements a-integrate-ecan-packaged-query-1017@a510db] -->
<!-- am[rests-on c-integrate-query-attention-domain-1017@451e5e] -->
Attention is local to the query. One unit is divided among its distinct cues
already present in the graph. A simultaneous conservative transition moves 0.38
of each non-isolated node's balance equally to its incidence neighbors. The
fraction is inherited from the inspected ECAN incident allocation, not fitted to
these queries. The mean balance of a pair's premises ranks its queued work;
native priorities resolve ties. A new statement enters with zero balance, then
the graph diffuses and the retained queue is reordered. Frontier capacity can
discard work, so the search can be incomplete even when a proof exists.

This mechanism allocates computation. It does not change evidence weights,
source trust, deontic rules or execution permissions. It implements no long-term
attention retention, forgetting, learned Hebbian weights or value-of-computation
estimator. Those require their own state and validation.

<!-- am[implements a-rt-ob-session-1017@f1468f] am[implements a-rt-ob-condition-1017@dc8180] -->
<!-- am[implements a-integrate-planning-session-surface-1017@f5132a] -->
<!-- am[implements a-integrate-parent-artifacts-compose-1018@e3c6d7] -->
## Conditions and proof obligations

`SnarsSession.condition(statement)` says whether a statement meets
a threshold, after the same attention search `forward_query` runs. The search and
the classification happen in one speculative batch, so a statement the search
derives is classified before that batch discards it. The threshold defaults to
SNARS's decision threshold, `(sn config decision-threshold)`, 0.6.

The classification reads the opinion's belief `b` and uncertainty `u` as the
probability interval `[b, b + u]`. It answers `Holds` when `b` is above the
threshold, `Fails` when `b + u` is below it, and `Undecided` otherwise. A
statement with no receipt or proof is `Undecided`, and so is any statement whose
evidence leaves the threshold inside the interval. The base rate never decides:
a statement believed with no evidence at base rate 0.9 is `Undecided`. An
`Incomplete` search leaves the statement `Undecided`, never `Fails`.
An explicit threshold of zero is preserved. See the
[mathematical contract](mathematical-contracts.md#planning-conditions) for the exact
model and its floating-point limits.

```python
budget = RunBudget(inference_budget=20_000_000, timeout_seconds=60)
with SnarsSession.persistent("observations.sqlite3", budget=budget) as session:
    status = session.condition(statement)
print(status.status, status.search, status.opinion, budget.spent)
```

`negated=True` classifies the literal "not S" instead. Its opinion is the complement
of the statement's, belief and disbelief swapped, so its interval is `[d, d + u]` and
the same cut applies. At the default threshold, an opinion `(0.1, 0.8, 0.1, 0.5)`
is `Fails` plain and `Holds` negated. Negation reclassifies the opinion; it does not
simply exchange the status names for every threshold.

`goal_chainer.snars_reasoner.track(positive, negative, budget=budget)` gives the
opinion SNARS makes of evidence counts at its default rate, with the same cut. It
reads no session and believes nothing, so a caller can project a track record of
attributed trials afresh each time.

`SnarsSession.obligations(statement)` lists what each route to a
statement still needs. A route is one way the backward chainer could prove the
statement from the session's conditional edges and registered rules, within
`max_size` proof nodes, where any premise may be open. Each route reports its
leaves: an open premise as `Open`, and each premise or edge the session holds with
its own condition. Only a `Holds` leaf is discharged, so evidence that is too weak
or contrary leaves its premise `Undecided` or `Fails`, and the route still needs
it. Every route is kept, in an order that states no preference. The direct route,
observing the statement itself, is one of them.

Each route also carries a scenario: the opinion the statement would hold if every
open premise carried the hypothesis evidence, by default 8 positive units. The
result names that hypothesis. A scenario is a labelled supposition. It is not the
confidence an observation can reach, an information value or a bound, so nothing
ranks or drops a route by it. Each route also reports `scenario_status`, the cut of
its scenario at the same threshold, which holds only under that hypothesis.
Discharging every leaf does not establish that the goal holds: inference can
weaken the resulting opinion. Check the goal itself with `condition`.

A route with nothing unmet supposes nothing: its scenario is the opinion its proof
gives the statement from the session's evidence. `route.established` is true when
that scenario also `Holds`, so the route alone shows the statement meets the
condition. Leaves that all hold aren't enough, since each deduction step discounts
belief. A premise and two edges, each believed at (8, 0), give the statement belief
0.512 two steps on, which leaves threshold 0.6 `Undecided`.

```python
from goal_chainer.snars_models import Evidence

budget = RunBudget(inference_budget=20_000_000, timeout_seconds=60)
with SnarsSession.persistent("observations.sqlite3", budget=budget) as session:
    found = session.obligations(statement, hypothesis=Evidence(8, 0))
for route in found.routes:
    print([(leaf.status, leaf.statement) for leaf in route.unmet], route.scenario, route.established)
```

Both operations use the caller's `RunBudget`, required when opening the session.
That budget passes through every stage of a decision, and running out of it raises
`InferenceBudgetExceeded` or `ReviewTimeout` rather than answering no routes. Like
`forward_query`, neither stores an event or leaves derived state behind. Neither
writes an observation; turning a verified outcome into evidence is separate work.
A missing route within the size bound is not proof that the goal is impossible.

The corresponding commands are:

```bash
goalchainer snars --inference-budget 20000000 --timeout-seconds 60 \
  condition --database observations.sqlite3 \
  --statement '(sn p so "is" ((arg s (sn c "service")) (arg o (sn c "healthy"))))' --json
goalchainer snars --inference-budget 20000000 --timeout-seconds 60 \
  obligations --database observations.sqlite3 \
  --statement '(sn p so "is" ((arg s (sn c "service")) (arg o (sn c "healthy"))))' \
  --size 12 --json
```

JSON skill dispatch places `condition` in the `evidence` group and `obligations`
in `goal-temporal`. Both return `result.answer` and `result.computation`, which
names the inference limit and spend. For obligations, `--positive`, `--negative`
and `--base-rate` set the hypothetical evidence; the JSON fields use underscores.
For conditions, `--negated` or the JSON field `negated: true` asks about the
complement literal.
Neither operation stores hypotheses, changes permissions, or executes an action.
The existing `what-if` CLI keeps its prior default of one positive evidence unit;
omitted `truth` thresholds still use that method's default.

<!-- am[implements a-integrate-store-boundaries-gate-1019@cded65] -->
## File controls

<!-- am[implements a-v2m-es-docs-1019@194775] -->
These controls hold for every GoalChainer event store: the SNARS store and the
[motivation stream](motivation-persistence.md) keep their events with one
implementation, `goal_chainer.event_store`. Each store's database names its
schema version and identity in its metadata, and a store opens only a database
that is new or that its own kind and identity wrote. It reads the database
before writing to it, and refuses with a `persistence_error`, without writing to
it, a database another store or identity wrote, also when the two kinds share a
schema version number, and a database holding tables but no store metadata, such
as another application's.

<!-- am[implements a-v2m-st-open-nolock-1020@e6eca3] am[rests-on c-v2rs-kr-repro-1020@6150df] -->
Opening a store that already holds its metadata takes no write lock. A store
GoalChainer creates is a WAL database, and on one the open reads beside a writer
holding the lock. SQLite still makes a read wait while the database is recovered
after a crash, while another connection holds it exclusively, and behind a writer
on a database another tool switched to a rollback journal. Such a wait lasts at
most the store's five-second busy timeout, or until the request's deadline when a
session opens the store. Only the first open of a new store takes the write lock,
to write the store's metadata, and waits for it the same way.

<!-- am[implements a-v2rs-snars-budget-1020@5469ea] am[implements a-v2rs-kr-session-1020@53ac31] -->
A SNARS session runs under the budget of the request it serves, as the CLI and the
OmegaClaw skill open one per request, and keeps that budget's deadline in the
store too. The store reads the budget as it opens, so a request whose budget is
already spent is refused before the database file is made. Each operation that
records an event, `ingest_text`, `believe`, `register_goal`, `temporal` and
`record_outcome`, appends it within the budget: the append waits for the write
lock no longer than the deadline and reads the budget again before it commits.
An operation whose event cannot commit by then, or whose batch spent what was left
of the budget, raises the budget's own error, `review_timeout` or
`inference_budget_exceeded`, returns no answer and leaves the store as it was, so
an answer the batch computed never stands for an event that was not recorded.
Every read the session
makes of the store takes the budget as well: the events it replays before each
batch, checked against the budget before every event, an outcome's lookup of its
observation id, `has_outcome`, and the `state` report the CLI and the skill return
after the operation. A long stream stops at the deadline with the budget's own
error rather than after it, and no read waits for a lock past the deadline. The
state report reads after the operation committed its event, so a deadline passing
during it raises the budget's error although the event is recorded, as the budget
check the CLI and the skill make after every command already could. Retry behaviour
depends on the operation, as Refused events describes.

GoalChainer refuses a database path that passes through a symbolic link, whether
the link is the database's own name, dangling or not, or a directory above it,
including one a `..` after a missing directory leads to. A linked directory would
carry the store into whatever directory the link reaches, onto a store already
there. It also refuses a path the operating system cannot name, such as one
holding a NUL character, and a path it cannot check, such as one under a
directory the process may not search or under the home directory of a user the
system does not know, with the reason the operating system gave. Name the
database by its real path: on macOS, for example, `/tmp` and `/var` are links into
`/private`.

<!-- am[implements a-v2rs-opath-open-1020@5f6c09] -->
GoalChainer creates a missing database file itself, with mode `0600`, before
SQLite opens it, and an open that may create sets an empty file it finds to
`0600` the same way, since it writes that file's first bytes. SQLite gives the
WAL and shared-memory files the database's mode when it creates them, so they
are `0600` too. GoalChainer changes any other file only once it has read the
database's metadata and found its own store there. Every open that finds its own
store sets the database and its WAL and shared-memory files to `0600` before any
event is written, whatever made them: the read of a database found at another
mode, or an earlier version whose side files an open connection kept. A file it
refuses keeps its bytes and its mode, whether it is another store's database,
another application's, an empty file a read finds, or a file that is no database
at all, and so does a path that names anything but a regular file, such as a
FIFO. It refuses an existing database the process may not both read and write,
which SQLite would otherwise open read-only. SQLite then opens the database by
name without creating a file of its own, and GoalChainer refuses the store if
that name no longer holds the file it checked.

GoalChainer holds the file it checks without opening it for reading or writing. A
process that closes any descriptor it opened to read or write a file releases
every POSIX lock it holds on that file, including the lock SQLite keeps on a WAL
database for as long as a connection is open, which
[SQLite lists](https://www.sqlite.org/howtocorrupt.html) among the ways to corrupt
a database. So a second store opened on the same database in the same process
leaves the first store's locks in place, and no other SQLite connection, which
follows SQLite's locking protocol, can checkpoint and delete the WAL under it. A
process that writes the directory directly follows no such protocol; the
paragraph below says what that leaves open.

GoalChainer enables SQLite `secure_delete`, foreign keys, WAL, and a five-second
busy timeout. Each row includes a content hash, schema version, and the SNARS
identity: a digest of the SNARS library GoalChainer's package carries and of the
Python its py-calls run, so a store opens only under the SNARS it was written against.
The identity names the bytes the running process loaded. If the package's SNARS
files change on disk while a process runs, as an in-place upgrade does, that
process refuses to open a store or compile another SNARS world, with a
`module_changed` error, until it is restarted.

The schema version is 3. Version 2 stores named a Mettabase commit where version 3
names the SNARS identity, and version 1 stores held HyperBase facts in their
ingestion events, which nothing replays now. GoalChainer refuses either kind when it
opens, rather than replaying it into a different state. Start a new store.

These checks see the path as it is while the store opens. Anyone who can write to
the containing directory, or to a directory above it, can still replace the
database, its WAL and shared-memory files or a directory in its path while the
store is open. They can also swap the name and swap it back while the store
checks it. GoalChainer refuses a containing directory that every user can write
unless its sticky bit is set, and checks nothing else about who can write the
directories. Protect the containing directory and the directories above it as
well as the main file.

<!-- am[implements a-integrate-store-boundaries-gate-1019@cded65] -->
## Refused events

GoalChainer refuses an event with a `persistence_error` before its transaction
begins when its kind or key is empty, when its kind, key or payload holds text
UTF-8 cannot carry, such as a lone surrogate, or when JSON cannot encode its
payload. Asking whether an event is recorded under a key refuses the same kinds
and keys. A failure inside the transaction rolls the transaction back, and a
failure that is not SQLite's own propagates unchanged, so an interrupt stays an
interrupt. Either way the refused event writes nothing and the next append
proceeds. A store that cannot open closes its SQLite connection before it raises.

<!-- am[implements a-v2-outcome-sequential-conflict-1020@10212e] -->
An event recorded under a key keeps that key's payload. `record_outcome` keys an
outcome by its observation id: recording the same outcome again returns `None`
and changes nothing, while a different statement, evidence count, base rate,
source or trust under a recorded observation id is refused with a
`persistence_error`. Both are decided before any SNARS batch runs. When two
sessions record one observation at once, the store's keyed append decides between
them the same way.

<!-- am[implements a-v2rs-snars-keyed-dedup-1020@85653f] -->
A belief, a goal and a text reading are each recorded once by their content.
`believe`, `register_goal` and `ingest_text` key the event by the SHA-256 of its
canonical payload, so submitting the same one again, from the same session or from
another at the same time, appends nothing, while one that differs in any field is
an event of its own. An identical event an earlier version stored without a key is
found by its payload and not appended again.

<!-- am[implements a-v2-retry-guide-1020] am[rests-on c-v2-temporal-retry-contract-1020] -->
These keyed operations can be retried after an error that hid their commit.
`temporal` has no event key: each persistent call appends a tick, including a retry
after such an error. Its event count and digest can therefore change on a retry.
Inspect the recorded events before repeating a temporal request whose commit is
uncertain.

## Redaction

<!-- am[implements a-integrate-parent-artifacts-compose-1018@e3c6d7] -->
The Python API accepts a redactor when a persistent session is created:

```python
from goal_chainer.sexpr.codec import SexprCodec
from goal_chainer.snars_reasoner import SnarsSession
from goal_chainer.snars_store import text_redactor

redact = text_redactor(SexprCodec())
session = SnarsSession.persistent("state.sqlite3", redactor=redact, budget=budget)
```

The redactor receives the whole event before replay or persistence. Redacting only
the `text` field is insufficient, because every decided reading fact quotes the
passage of the request that grounds its answer. `text_redactor` replaces the text
and each fact's passage, and keeps each fact well formed, so a redacted ingestion
still replays and still gives the native decision every reading. A redactor of your
own must do the same: the native decision refuses an ingestion that no longer holds
one well-formed reading per proposition.
GoalChainer executes and appends the prepared redacted payload, so private and
replayed state cannot diverge.

## Retention and deletion

Set a retention period based on the incident-data policy. Close the session before
deleting its files. Remove the database, `-wal`, and `-shm` files together.
Filesystem deletion is the supported full-stream deletion operation because the
event table is append-only.

<!-- am[implements a-v2rs-kr-session-1020@53ac31] am[rests-on c-v2rs-what-if-appends-nothing-1020@d30172] -->
Counterfactual hypotheses are never written: a what-if appends no event, and
GoalChainer refuses a counterfactual whose SNARS state tree, once the hypothesis is
rolled back, differs from the tree before it. Another session may append to the
store while a counterfactual runs; that event is the other session's and leaves the
what-if's answer standing.

<!-- Purpose: teach GoalChainer's concepts and public interfaces through examples, setup and verification. -->
<!-- am[implements a-integrate-readme-style-edit-1019@4da4b0] -->
# OmegaClaw GoalChainer

Review goals, reason over evidence and norms, and plan the next steps in a declared domain.

## What GoalChainer does

A persistent agent has more to decide than which tool to call next. A task may
still matter but need to pause, its owner may need to hand it off, or its
original goal may no longer be supported by the evidence. GoalChainer makes
those decisions inspectable: you supply the domain and observations, and it
returns a review, a plan or inquiry, or an admission result for one current step.

The domain supplies the vocabulary, goals and rules. A procedure library supplies
the steps the planner may compose. The evidence says what is observed, who
supplied it and when it holds. A review uses those inputs to propose an action.
A plan searches for steps that achieve a goal; admission checks a returned
step again against the current situation.

For example, the incident domain distinguishes private logs from explicitly
public logs. Private logs block raw publication. Public logs make it permissible.
Unverified facts add a verification goal and rank holding first. The same
request interface also serves task control, where the question may be whether
to continue work, pause recoverably or hand it to another owner.

A proposal is not permission to execute. The host supplies authorization,
performs actions and reports what happened. A model's prediction, a current
observation and a receipt of an action remain different inputs.

## Why MeTTa

MeTTa expresses GoalChainer's domain declarations, norm rules, review policy and
planning rules. The deontic library determines obligations and prohibitions;
the bigraph kernel matches and rewrites structural states; the planner composes
the domain's procedures. Python loads dependencies, validates
and transports values, accounts for the caller's budget and exposes the CLI.

It runs on [MesTTo/MeTTa](https://github.com/MesTTo/MeTTa), the engine pymetta
depends on, through pymetta's Python interface. MeTTaScript and MeTTa-TS are
separate implementations and are not the target runtime. The pinned build and
installation checks below identify the engine this package uses.

## Installation

You need Linux x86_64, CPython 3.12–3.14 and [uv](https://docs.astral.sh/uv/).
Clone with the pinned dependencies,
Omega and PeTTaChainer, both submodules under `external/`:

```bash
git clone --branch goalchainer_v2 --recurse-submodules https://github.com/MesTTo/OmegaClaw-GoalChainer.git
cd OmegaClaw-GoalChainer
```

`goalchainer_v2` is the current version. `goalchainer_v1` preserves the previously
published version.

<!-- am[implements a-rt-n2ic-readme-1018@6223d3] am[implements a-v2-review-package-1020@940ccf] -->
The MeTTa engine is pymetta 0.9.4 as built for GoalChainer, version
`0.9.4+goalchainer.native.2`. It adds pymetta's pool start repairs, and its
SWI-Prolog host carries the clause GC and index fill repairs that concurrent
evaluation needs. The release supplies a directory of wheels named
`pymetta-0.9.4+goalchainer.native.2-f50f8272710b2d56`. The name ends in the
first 16 hex digits of the SHA-256 of the directory's `MANIFEST`, and `MANIFEST`
lists every other file there with its SHA-256.

Download the release archive, verify its checksum, and place the verified build
where the lockfile expects it:

```bash
mkdir -p ai-tmp
curl --fail --location \
  https://github.com/MesTTo/OmegaClaw-GoalChainer/releases/download/pymetta-native.2/pymetta-native2-linux-x86_64.tar.gz \
  --output ai-tmp/pymetta-native2-linux-x86_64.tar.gz
printf '%s  %s\n' \
  90ae8da8e9fee5cca181b5ddcfa212b73403e572133ec9877484c9f30b8b330c \
  ai-tmp/pymetta-native2-linux-x86_64.tar.gz | sha256sum --check -
tar -xzf ai-tmp/pymetta-native2-linux-x86_64.tar.gz -C ai-tmp
GOALCHAINER_NATIVE_WHEELS="$PWD/ai-tmp" uv run scripts/native-wheels.py place
```

`place` verifies every file against `MANIFEST`. If you already have the build,
set `GOALCHAINER_NATIVE_WHEELS` to its parent directory and run `place` to link
it into the checkout. The lock uses a relative path, so it carries no machine's
location. Until the directory is present, uv refuses to install the project.
The native wheels support the Python versions and platform above; the check
below refuses a pure-Python wheel using an unverified system engine.

Install the locked Python environment, then check what it installed:

```bash
uv sync --frozen --all-extras
.venv/bin/python scripts/native-wheels.py check
```

`check` compares every installed file of pymetta, its pool and its engine
library among them, with the RECORD of the wheel in the verified directory, and
prints the wheel and engine it found. A changed or added module fails it with
the file named, and `uv sync --frozen --reinstall-package pymetta` puts the
published one back.

The archive's `BUILD` records the source revisions, patch hashes and container
image used for these wheels. The build sources are
[MeTTa at c389011c](https://github.com/MesTTo/MeTTa/tree/c389011c9ff74cf0f04abb8679f254585db2a2af)
and [PyMeTTa at d5d18ba1](https://github.com/MesTTo/PyMeTTa/tree/d5d18ba1d0350f48e9d9a18f3ba5e1420a156752).
MeTTa's `tools/build-distributions.sh` creates the Python distributions;
`tools/pymetta-host/run.sh` runs the native build and wheel assembly stages.
The archive also includes a supplemental ISub source notice. Its LGPL text,
source and provenance already accompany the scorer inside the wheels.

Every native dependency resolves by one rule: an explicit path given in code,
then its environment variable, then its `external/` submodule. A checkout that
is missing, or lacks the file that marks it, stops with an error naming the
path and how to provide it; nothing outside the repository is searched.

| Dependency | Variable | Default |
| --- | --- | --- |
| Omega | `GOALCHAINER_OMEGACLAW_DIR` | `external/OmegaClaw-Core` |
| PeTTaChainer | `GOALCHAINER_PETTACHAINER_DIR` | `external/PeTTaChainer` |

## The surface

The CLI groups the public operations by the kind of result you need.

| Command | Input and result | Guide |
| --- | --- | --- |
| `goalchainer request` | A domain and context; a review, plan, inquiry or current-step admission | [Requests](#domains-and-readings), [planning](docs/planning.md) |
| `goalchainer show` | A saved request result; a readable account without evaluation | [Plans](#plans-from-goals) |
| `goalchainer relevance` | Domain inspection, task-review packets and receipt assessment | [Relevance](docs/relevance-review.md) |
| `goalchainer motivation` | Explicit need observations and host attempts; a durable stream and its snapshot | [Motivation](docs/motivation.md) |
| `goalchainer snars` | Statements and evidence; belief queries, proofs and counterfactuals | [SNARS sessions](#snars-sessions) |
| `goalchainer directive` | An operation and a caller-selected plan file; a view or explicit lifecycle change | [Coordination](docs/directive-orchestration.md) |
| `goalchainer diagnose` | A module group and expression; a profile, explanation or match diagnosis | [Diagnostics](#diagnose-a-metta-operation) |

`request`, `motivation`, `directive` and `show` read a JSON object from `--input FILE` or
standard input. The following sections use the installed `goalchainer` command;
`python -m goal_chainer.cli` exposes the same interface.

## Domains and readings

Reading text needs the `semantic` extra and the pinned cross-encoder, which
`./scripts/setup-semantic.sh` provisions, and a TypeSafe key for any answer the
replay cache lacks; [docs/semantic-reader.md](docs/semantic-reader.md) covers both.

<!-- am[implements a-integrate-domain-surface-1018@759698] am[implements a-integrate-cli-stdin-repair-1018@a5f985] -->
The `request` command reads JSON from stdin or `--input FILE`, as UTF-8 either
way and whatever the locale, as `directive` and `show` do. A review request
selects a domain and supplies context and attributed readings. This example also
asks the reader to interpret text. Save it as `request.json`:

```json
{
  "operation": "review",
  "domain": {"packaged": "incident"},
  "context": {
    "review_id": "incident-42", "subject": "checkout", "trigger": "incident-report",
    "as_of": "2026-10-16T09:00:00+00:00", "authority": "advisory",
    "policy_version": "incident-v1", "readings": []
  },
  "reading": {
    "text": "Raw logs include customer emails. Engineering needs the incident room.",
    "observed_at": "2026-10-16T09:00:00+00:00", "valid_until": null
  }
}
```

```bash
goalchainer request --input request.json \
  --inference-budget 1000000000 --timeout-seconds 600
```

Keep the user's text unchanged in `reading.text`; omit `reading` when supplying
only attributed observations in `context.readings`. A domain without a reading
declaration refuses text.

`domain` selects exactly one `packaged` name or `path`. Packaged names are
`incident` and `task-control`. The `plan` operation additionally accepts the
goal, procedure library, journal, the journal's receipts and statement evidence. The `admit`
operation rechecks a returned step against the current evidence and instance.
<!-- am[implements a-ev-pk-row-statement-positions-1018@9c3a50] -->
A statement row names its statement as a procedures file does,
`(Statement (sn ...))`, so a row and the library name one literal.

## Reviews and their support

A relevance review proposes which lifecycle action, if any, a persistent agent
should take on one of its tasks: continue, pause recoverably, stop as stale,
replan, hand off, escalate and the rest. It only proposes. The record never
applies an effect or grants authority, and the host decides what happens. You
can inspect the packaged task-control domain with bounded validation on pymetta:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli relevance domain --inference-budget 5000000 --timeout-seconds 60
```

A review runs the domain's theory on `lib_deontic`, so it needs the setup above:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli relevance review \
  --packet examples/relevance/chemistry-contention.packet.json
```

[docs/relevance-review.md](docs/relevance-review.md) covers the packet, how a
review decides, freshness checks before a host acts, and receipts afterwards.

<!-- am[implements a-integrate-deontic-support-trees-1019@508ecf] -->
The JSON review includes `deontic_support`: a selected support tree for each
conclusion or dilemma literal. A rule node names its rule and its premises;
a fact node names its source fact. The tree explains that support, while the
review's `steps` explain the later ranking choices. It does not enumerate every
defeated alternative or grant authority to act. The
[review-record reference](docs/relevance-review.md#the-review-record) describes
these fields, the readset and the decision fingerprint.

## Needs and observed outcomes

<!-- am[implements a-v2-docs-1019@6301a6] am[related a-v2-examples-1019@2d047f] am[related a-v2r-guides-1020@0b367f] -->
A domain can declare quantities with target bands and expected changes from
actions. The Companion example starts with activation at `0.9`, outside its
target `[0.4, 0.6]`. Its review proposes an action expected to reduce activation.
After the host reports a level of `0.5`, the next review holds instead of
repeating the action. Without an observation, it asks for evidence.

```bash
uv run python examples/motivation/cycle.py companion \
  --directory ai-tmp/motivation-companion \
  --inference-budget 1000000000 --timeout-seconds 600
```

The example uses synthetic observations and executes no action. Observations
and explicit host attempts persist in a separate motivation stream. Reviews
learn expected changes from attributed outcomes. Reviews retain evidence
summaries and a history reference; a `status` request recovers the observations
and samples behind them. Those associations do not establish causation
or override norms and authority. The [motivation guide](docs/motivation.md)
shows the declarations, the Research example and the CLI and Python interfaces.

## Plans from goals

<!-- am[implements a-integrate-public-plan-example-1018@0d33ba] -->
The [task-control example](examples/planning/task-control.request.json) supplies
observations of resource contention, a mismatched owner and the receiving
owner's acceptance. It asks for contention to be resolved, using the packaged
domain's graph and procedure library. Its goal uses tagged planner records:

```json
[{"@type":"NegatedLiteral","literal":{"@type":"SignalLiteral","name":"resource_contention"}}]
```

Run the example and save the answer:

```bash
goalchainer request --input examples/planning/task-control.request.json \
  --inference-budget 1000000000 --timeout-seconds 600 > plan.json
```

<!-- am[implements a-dd-show-1018@f9e4e9] am[implements a-sb-shape-boundary-1018@917de5] -->
`goalchainer show --input plan.json` prints a readable account of the saved
answer: the review, then the plan's steps, then the line saying the request
authorized and applied nothing. It reads any request result, from a file or
standard input, and evaluates nothing. Input that is no request result, or
holds a value of another kind than a request writes where the account reads,
is refused as invalid input before anything is printed. The plan starts the
handoff procedure, hands the task to the receiving seat and finishes.

## Current-step admission

To check the first step against the same observations, pass that step back unchanged:

```python
import json
from pathlib import Path

request = json.loads(Path("examples/planning/task-control.request.json").read_text())
planning = json.loads(Path("plan.json").read_text())["planning"]
if planning["@type"] != "Plan":
    raise SystemExit("The answer needs investigation or has no plan.")
del request["goal"]
request.update(operation="admit", step=planning["steps"][0], instance_id=None)
Path("admission.json").write_text(json.dumps(request))
```

```bash
goalchainer request --input admission.json \
  --inference-budget 1000000000 --timeout-seconds 600
```

This first step starts an application, so it has no executor instance yet.
Later steps require the executor's instance identifier and observed journal
events. In a live request, refresh the context and observations before
admission. The example's source labels illustrate inputs; they authenticate
nothing by themselves.

<!-- am[implements a-dd-doc-1018@da16cf] am[implements a-dd-receipt-variation-1018@655fcb] -->
[Plans from goals, evidence and capabilities](docs/planning.md) continues from
here. It admits the act step once the host's journal shows the application
started, then shows the same step blocked once an observation changes. It then
changes the evidence, the procedure library and the goal one at a time, revises
a plan from the receipts of earlier attempts, and plans in a domain the caller
supplies. The tests rerun every command it shows.

Results retain the review and any plan, inquiry, exhausted-space `NoPlan` or
admission outcome. A blocked, stale or ambiguous step remains such in the
output. Model validity and admission grant no execution authority, and every
response states that it applied no effect. Host authorization and receipts are
separate inputs to execution and feedback.

## Receipts and track records

<!-- am[implements a-ev-fb-request-receipts-1018@4c8f23] am[implements a-ev-fb-promotion-1018@2ae86c] -->
A plan request may add `receipts`, an object mapping each journal `Receipt` id
to its receipt-v2 document. A procedure's track record comes only from these.
Under the library's `(gc-track-promotion (Trials N) (Threshold THETA))`, the
record holds once every dispatched attempt of the procedure has a documented
receipt, at least N attempts observed what it achieves as their own product,
and SNARS's track-record belief exceeds THETA. Plans resting on procedures whose
records hold are classed established. A library without the rule holds no
record. Each journal `Dispatched` event names the dispatched step's witness
digest, which its receipt repeats as `review_fingerprint`, and when it was
dispatched. A receipt issued after the plan's time is refused, as a reading
observed or an attempt dispatched after it is, so no record rests on the future.

## Bounds and errors

The limits are caller choices. A domain request shares one inference allowance
and one deadline across domain loading, optional reading, review and planning.
Starting another stage does not reset them. Exhaustion raises a typed error;
it is not an `unknown` observation or a completed search with no plan.

| Surface | Where the limits come from |
| --- | --- |
| `request`, `motivation`, `directive`, `snars` | Required `--inference-budget` and `--timeout-seconds` arguments |
| `diagnose profile`, `diagnose explain`, `diagnose match` | The same two required arguments on the diagnostic |
| `relevance review` | The packet's `budget` object |
| `show` | No limits: it renders a saved result and evaluates nothing |

Requests, directive operations and diagnostics report a typed failure as JSON.
Commands that expose `--json` also use it for typed errors; otherwise the CLI
reports the error on stderr. Invalid command-line syntax is handled by the
argument parser. A failed command has a nonzero exit status.

## SNARS sessions

SNARS keeps evidence, beliefs and their sources in a session. A query can ask
for bindings, a proof, a counterfactual or an explanation. Without a persistent
database, each CLI invocation starts an in-memory session; the statement-only
examples below demonstrate the operation shapes, and their answers depend on
the evidence in that session.

<!-- am[implements a-integrate-request-budget-surface-1018@d6882c] -->
`goalchainer snars` requires an explicit operation. These Bash examples share a command
prefix with explicit limits; each invocation gets its own request budget:

```bash
snars=(goalchainer snars --inference-budget 1000000000 --timeout-seconds 600)
"${snars[@]}" ask --statement '(sn p so "is" ((arg s (sn c "a")) (arg o $what)))'
"${snars[@]}" prove --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
"${snars[@]}" explain --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
"${snars[@]}" why-not --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
"${snars[@]}" discover --statement '(sn p so "is" ((arg s $x) (arg o $y)))'
"${snars[@]}" goal --statement '(sn p so "goal" ((arg s (sn c "agent")) (arg o (sn c "safe"))))'
"${snars[@]}" subgoals --statement '(sn p so "goal" ((arg s (sn c "agent")) (arg o (sn c "safe"))))'
"${snars[@]}" what-if --hypothesis '(sn p so "is" ((arg s (sn c "logs")) (arg o (sn c "public"))))' --query '(sn p so "is" ((arg s (sn c "raw")) (arg o (sn c "acceptable"))))'
"${snars[@]}" temporal --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))' --now 10
"${snars[@]}" trust
"${snars[@]}" mine --minimum-support 2
"${snars[@]}" inspect
"${snars[@]}" truth --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
"${snars[@]}" control --budget 8
"${snars[@]}" structural
"${snars[@]}" transform --transform-kind marginal --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))' --base-rate 0.7
"${snars[@]}" compiled-prove --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
"${snars[@]}" guard --guard-rule '(safe redacted)' --guard-goal '(safe redacted)'
```

## Defaults and guards

<!-- am[implements a-integrate-guard-metta-build-1019@e688cb] -->
Guard clauses and goals are MeTTa expressions. s(CASP) remains the solver. A fact is
`(safe redacted)`; a rule is `(:- HEAD BODY)`. Use `(, A B)` for conjunction,
`(not GOAL)` for default negation, `(- GOAL)` for explicit negation and
`(:- BODY)` for an integrity constraint. Repeated `$variables` in one clause name
the same variable. For example:

```bash
"${snars[@]}" guard \
  --guard-rule '(isa tweety bird)' \
  --guard-rule '(ab penguin)' \
  --guard-rule '(:- (flies $x) (, (isa $x bird) (not (ab $x))))' \
  --guard-goal '(flies tweety)'
```

`SnarsSession.guard` takes the same source expressions. When calling the MeTTa
heads directly, quote the data: `(sn guard-rule! (quote (safe redacted)))` and
`(sn guard? (quote (safe redacted)))`. A query returns the first supporting stable
model as text, or `"no"`; the Boolean view means support in at least one model.
Solver errors remain errors. Rules apply only within the current speculative batch.

## Text in a SNARS session

<!-- am[implements a-ie-sr-text-needs-domain-1018@8f7f0b] -->
These operations work on statements alone and read no domain. Text given with `--request` is
read with the reading section of the domain the caller selects, a packaged one with
`--domain NAME` or a file with `--domain-file PATH`, and the session believes those readings
before the operation runs:

```bash
"${snars[@]}" truth --domain incident --request "The error dump holds no email address." \
  --statement '(sn p so "has-property" ((arg s (sn c "request")) (arg o (sn c "customer-emails"))))'
```

Text with no domain selected is refused, and so is a selected domain that declares no reading
section, such as `task-control`.

Pass `--database path/to/snars.sqlite3` to opt into persistent state. Without it,
the command uses an in-memory session.

`--base-rate` sets the base rate of a what-if hypothesis's evidence, or the prior a marginal
seeds. Without it, SNARS applies its configured default, `(sn config default-rate)` in
`src/goal_chainer/snars_library/snars/config.metta`, the prior it also gives every reading,
memory item and outcome.

## Coordination and plan files

The directive dispatcher exposes views and explicit lifecycle mutations of a
caller-selected plan. For example, put
`{"operation":"status","plan":"/path/to/work.metta"}` in `directive.json`:

```bash
goalchainer directive --input directive.json \
  --inference-budget 1000000000 --timeout-seconds 600
```

See [directive orchestration](docs/directive-orchestration.md) for lifecycle
records and their boundary with observed effects.

## Diagnose a MeTTa operation

<!-- am[implements a-dg-docs-1019@aaf450] -->
`goalchainer diagnose` looks inside one MeTTa expression in a module group's space. It prepares
the group as an evaluation does, holds the process's one engine alone, and works inside the
space's speculative scope. Both limits are required: one budget bounds the whole diagnostic and
is charged its inferences. Each diagnostic prints a JSON report, and a refusal prints the typed
error as JSON.

The profile below runs a packaged group. The other two run a group made of this file, `my.metta`:

```bash
cat > my.metta <<'EOF'
(edge a b)
(edge b c)
(node a)
EOF
```

```bash
limits=(--inference-budget 200000000 --timeout-seconds 120)
goalchainer diagnose profile --group goal_chainer.bigraph.kernel:GROUP "${limits[@]}" --top 5 '(bg-warm-up)'
goalchainer diagnose explain --module my.metta "${limits[@]}" '(match &self (, (edge $x $y) (edge $y $z)) ($x $z))'
goalchainer diagnose match --module my.metta "${limits[@]}" '(edge a $y)' '(node $y)'
```

The explain reports the plan `(plan nested-loop (order (edge $_1 $_2) (edge $_2 $_3)))`, the
variables numbered by the engine. The match reports `no-joint-binding`: each pattern matches
alone, but the only edge from `a` reaches `b`, and `b` is no node.

`--group` names a packaged `ModuleGroup` as `module:attribute`. `--module` makes a group of the
module files given, in load order.

| Diagnostic | What the engine runs | The report |
| --- | --- | --- |
| `profile` | the expression, once, under pymetta's statistical profiler | answers, inferences, sampler counters and the `--top` predicate rows |
| `explain` | the engine's `explain` of the form; the query itself never runs | the engine's items in order, and the plan of a match form |
| `match` | one bounded `once` match per stage: the query, the patterns joined without `--where`, then each pattern alone | a verdict, the patterns that match nothing alone, and each stage's query and inferences |

A profile executes the expression. Speculation discards its engine writes but cannot undo a
Python effect, such as a file a `py-call` helper wrote. The sampler takes SWI-Prolog's default
of 200 samples a second, so a short run reports few samples, while each row's call and redo
counts are exact. `explain` answers a plan only for `(match SPACE PATTERN TEMPLATE)` in a space
the engine recognizes, and any other match form is refused with `engine_error`. A `match`
verdict is `matches`, `guard-rejects-every-row`, `patterns-match-nothing` or
`no-joint-binding`; a stage runs only when the stages before it found nothing.

pymetta's `Space.why` and `explain(analyze=True)` are not offered. `why` reads every stored atom
and the function registry outside any time or inference limit. `analyze=True` walks an effect
plan no limit reaches and then runs the query a second time. `profile` on the same expression
measures one bounded run instead.

## Persistence and migration

<!-- am[implements a-integrate-readme-native-contract-1018@c0837b] -->
[SNARS persistence and privacy](docs/snars-persistence.md) describes database
permissions, redaction, retention, replay, and deletion.

<!-- am[implements a-integrate-runtime-doc-wording-1018@56334c] -->
[SNARS migration and rollback](docs/snars-migration.md) describes SNARS evidence,
the removal of incident assessment from SNARS, store compatibility and code
rollback. [Directive orchestration](docs/directive-orchestration.md) describes
caller-written plans and the required agent on each lifecycle change.

The former Prolog-text arguments are no longer accepted. The protocol now echoes
the goal as a structured expression. This library change also changes the SNARS
identity: restart existing processes and start a new store. Old stores are refused
under the new identity; schema version 3 is unchanged.

## Omega integration

Omega, formerly OmegaClaw, is one harness GoalChainer serves.
`external/OmegaClaw-Core` is a stock checkout of
[singnet/Omega](https://github.com/singnet/Omega), and GoalChainer's skill seam
is an Omega plugin, so install it there:

```bash
./scripts/setup-omegaclaw.sh
```

That copies the seam and its `gcskill.py` transport into `plugins/goalchainer`
and registers it with one record in `config/plugins.yaml`, as Omega's
[plugin API](https://github.com/singnet/Omega/blob/1a7624e2bab02be6ec6f9a262c5955f348ad1702/docs/reference-plugin-api.md)
describes. When the agent starts, Omega's loader reads that record and offers
each GoalChainer skill to the model as a tool. The skills run GoalChainer as a
child process of the locked environment's interpreter, because Omega's PeTTa
hosts its own Python through SWI-Prolog, where pymetta cannot start; the install
asks uv for that interpreter, runs one skill in it, and records it in the
plugin. No core file is edited, the install is receipt-backed, and `--uninstall`
returns the checkout to a clean `git status`. Re-run it after the plugin or the
environment changes.

To run the agent in a container, `./scripts/build-omega-image.sh` builds
upstream's Omega image with the pinned Omega source, GoalChainer's locked
environment with the `semantic` extra, pymetta's verified native build and the
pinned cross-encoder, and the plugin installed, reading text offline by default;
the build takes the native build as the gate does. The
[plugin guide](plugins/goalchainer/README.md#running-in-a-container) describes
starting it, turning Jev on through Omega's gateway, and checking it.

<!-- am[implements a-integrate-domain-surface-1018@759698] -->
<!-- am[implements a-v2-cli-skill-surface-1020@6f755c] -->
`goalchainer-request` takes the same request object as the CLI, with
`inference_budget` and `timeout_seconds` added to its JSON envelope.
`goalchainer-directive-dispatch`, `goalchainer-snars-dispatch` and
`goalchainer-motivation-dispatch` accept explicit
operations with the same limits. The [plugin guide](plugins/goalchainer/README.md)
documents the callable skills and process boundary.

The SNARS dispatcher accepts evidence, explanation, counterfactual,
goal-temporal and trust-discovery groups. Unknown fields and mismatched
group-operation pairs are refused.

## Runtime and evidence

GoalChainer's deontic library, `lib_deontic` and `lib_directive`, ships in its
own package, in `src/goal_chainer/deontic_library/`, adopted from
[omegaclaw-deontic](https://github.com/MesTTo/omegaclaw-deontic) under its MIT
licence; its `PROVENANCE.md` names the commit and what was taken. A review or a
directive needs no plugin installed anywhere.

<!-- am[implements a-integrate-readme-native-contract-1018@c0837b] -->
| Layer | Owner | Role |
| --- | --- | --- |
| Reading | Jev (TypeSafe) and a local Qwen3 cross-encoder, through `semantic_reader` | Text to supported, contradicted or unknown readings of domain-declared propositions, each grounded in a passage |
| Belief | SNARS, carried in GoalChainer's package, in-process on pymetta | Evidence cells, opinions, receipts, proofs, trust, time, and counterfactuals |
| Norms | `lib_deontic`, carried in GoalChainer's package, in-process on pymetta | Forbidden, obligated, and permitted verdicts |
| Knowledge | `planning/justification.metta` | Claim and row labels, contrary evidence, expiry and checked knowledge |
| Review | `relevance/policy/` | Domain-derived candidates, required goals, ordinal effects, licensed authority and escalation |
| Planning | `bigraph/kernel.metta` and `planning/` | Structural reactions, procedures, inquiry branches and current occurrence checks |
| Coordination | `lib_directive`, carried in GoalChainer's package | Dependencies, boards, assignment, lifecycle, validation, and analysis |
| Host | GoalChainer Python | Dependency resolution, typed transport, SQLite replay, process control, CLI, and skills |

<!-- am[implements a-integrate-runtime-doc-wording-1018@56334c] -->
SNARS batches and deontic reviews run in the GoalChainer process on pymetta,
each inside the engine's speculation scope, so none keeps anything from another.
Before GoalChainer retired PeTTa, a fresh PeTTa process answered a scripted SNARS
session's every operation, 64 deontic theories and every PeTTaChainer grading case
as the in-process engine did; the tests keep those answers in `tests/data` and
require the same. Omega owns its task records. GoalChainer's directive operations
persist changes to the caller-selected plan file.

For a separate PLN calculation, `goal_chainer.evidence_chainer.grade` takes
caller-supplied statements and query targets and runs PeTTaChainer's MeTTa
library through pymetta. Each grading consumes the caller's budget and discards
its writes after answering. An unproved target has no belief; a belief with
strength zero is a different result. PLN truth values remain distinct from
native SNARS evidence.

The incident example's host adapter is an explicit import,
`goal_chainer.examples.incident`. It checks the stored review's freshness,
then runs the review again on the caller's current packet. It prepares an
artifact only when the new review proposes the same action and norm status
and the caller has authorized it. It then checks the prepared artifact.
It does not send the artifact or confirm an effect. The
[execution contract](docs/execution-contract.md) describes that boundary.

## License

<!-- am[implements a-v2-public-license-notice-1020@fedb58] -->
GoalChainer's own files are [MIT-licensed](LICENSE). The bundled SNARS backward
chainer includes code under GPL version 3, so the combined distribution carries
GPLv3 terms as well as the retained MIT and Apache-2.0 notices. The
[SNARS provenance](src/goal_chainer/snars_library/PROVENANCE.md) identifies that
code, its upstream source and the included licence text. The repository and
source distribution contain the modified source; the wheel also includes the
MeTTa and Prolog source it executes.

## Testing

<!-- am[implements a-integrate-readme-native-contract-1018@c0837b] -->
`scripts/gate.sh` performs the steps above in whatever checkout it runs in,
then runs pytest, the mathematical-contract check and the OmegaClaw plugin's
MeTTa suite. A skipped test counts as a failure, since it did not run.
It places the native build first, so give it `GOALCHAINER_NATIVE_WHEELS`
unless the checkout already has `native-wheels/`.
It sets `HF_HUB_OFFLINE=1` so models load only from the local Hugging Face
cache, keeps temporary files in its run directory, and changes only the
submodule checkouts it cloned itself. When `external/OmegaClaw-Core` is a
checkout it did not clone, it installs the plugin into its own clone of the
same pin, `ai-tmp/gate-omegaclaw-core`, and runs the plugin suite there, so
that checkout stays as it was and later runs still accept it. Arguments after
the script go to pytest and skip the mathematical-contract check and the plugin
suite:

```bash
scripts/gate.sh                          # the whole gate
scripts/gate.sh -q tests/test_domain_requests.py
```

The last line is a verdict such as
`gate-verdict revision=<sha> pytest=0 skipped=0 plugin_metta=0 math=0`,
and the exit status is nonzero when any part failed or any test was skipped.

## Repository layout

<!-- am[implements a-integrate-readme-native-contract-1018@c0837b] am[implements a-integrate-runtime-doc-wording-1018@56334c] am[implements a-dg-docs-1019@aaf450] -->

| Path | What it owns |
| --- | --- |
| `src/goal_chainer/requests.py` | Composes domain loading, optional text readings, review, planning and current-step admission under one budget. |
| `src/goal_chainer/domains/` | Holds domain models, section readers, shared vocabulary, validation tables and packaged declarations. |
| `src/goal_chainer/relevance/` | Derives review candidates and explanations from domain rules and attributed readings, and checks freshness and receipts. |
| `src/goal_chainer/motivation/` | Validates and stores need observations and host attempts, and supplies the review's native motivation snapshot. |
| `src/goal_chainer/event_store.py` | Implements the transaction and private-file machinery shared by the separate SNARS and motivation stores. |
| `src/goal_chainer/planning/` | Holds the justification kernel, procedure compiler, search, admission and tagged JSON transport. |
| `src/goal_chainer/bigraph/` | Holds the structural matcher, reactions and state-isomorphism checks. |
| `src/goal_chainer/runtime/` | Hosts the MeTTa engine and evaluates declared module groups under caller budgets; its diagnostics profile, explain or match one expression in a group's space for `goalchainer diagnose`. |
| `src/goal_chainer/evidence_chainer.py` | Grades caller-supplied PLN statements and targets through PeTTaChainer. |
| `src/goal_chainer/examples/incident/` | Prepares and checks artifacts for a host-selected incident proposal. |
| `src/goal_chainer/policy/` | Holds shared MeTTa adapters and validation rules. |
| `src/goal_chainer/goalchainer_directive.metta` | Is the versioned directive adapter, evaluated through pymetta. |
| `src/goal_chainer/deontic_library/` | Is the deontic library, `lib_deontic` and `lib_directive` with their core suites, adopted from omegaclaw-deontic. |
| `src/goal_chainer/snars_*.py` | Contains typed host orchestration. |
| `src/goal_chainer/directive*.py` | Contains the safe plan and transport boundary. |
| `integrations/omegaclaw/` | Contains the Omega drivers, request builder and container image definition. `plugins/goalchainer/` registers the callable skills. |
| `src/goal_chainer/snars_library/` | Is SNARS, taken from Mettabase c079c89, with the sCASP copy its guard runs on; `PROVENANCE.md` there says what changed. `src/goal_chainer/markdown_library/` is Mettabase's Markdown layer, taken from the same commit without HyperBase, which the directive programs use; its `PROVENANCE.md` says what changed. |
| `tests/test_snars_native_integration.py` | Is the non-skipped native acceptance path, and `tests/test_snars_executor_differential.py` holds the in-process executor to the answers PeTTa gave, recorded in `tests/data/snars-executor-petta.json`. |
| `docs/architecture.md` | Records component ownership and execution flow. |

# Semantic reader

This runbook covers how GoalChainer reads natural-language text: what it asks, which models answer,
how to provision them, and how tests replay their answers. For where the reader sits in the
system, see [architecture.md](architecture.md).

## What it reads

The reader judges the propositions one domain declares about every text. A domain supplies them as
the reading section of its domain file, forms in the grammar
[`goal_chainer.domains.readings`](../src/goal_chainer/domains/readings.py) reads:

```
(gc-reading-domain incident)
(gc-reading-model "jev-1.13.0")
(gc-reading-language "en")
(gc-reading-instructions "Decide whether `text` supports ... Proposition: ")
(gc-reading-option supported for "The text states, or clearly implies, that the proposition is true.")
(gc-reading-proposition sensitive-data "The content ... includes ... personal or confidential data ..." "Does the content include ...?")
(gc-reading-choice mood "What does `text` mainly do?" ((query "It asks a question.") ...))
(gc-reading-binding leaked Seat "Which seat does the text say the data left? Statement: " "The text names no seat.")
(gc-ranking-instruction "Given a question about an incident, retrieve the passage ...")
```

The section is closed. A form outside this grammar, an empty text, a name that is not a plain
symbol, or a direction other than `for`, `against` and `none` is refused as the section is read.
What the forms must satisfy together is checked by the fault tables in
[`domains/readings.metta`](../src/goal_chainer/domains/readings.metta), which run with the domain's
other checks, so one `DomainError` lists every fault of the file: a repeated answer or id, a choice
sharing a proposition's id, a choice offering no option or one option twice, no option or none with
a `for` or `against` direction, no proposition or choice at all, and a binding of an undeclared
proposition, of an undeclared control or of a control no entity is declared under, a binding written
twice, or an undescribed entity under a bound control. The
declaration is identified by the SHA-256 of its content, wherever it is written, and a reading is
admitted only by the declaration it was read with. A proposition's id is its one name everywhere:
in its facts, its SNARS statement, the domain theory's literal and every report, and each
proposition is one of the domain's signals, declared nowhere else in the file. A generic request
reads with its own domain's section, and so does a SNARS command or dispatch given text: each reads
with the section of the domain its caller selects, and refuses text with no domain selected or a
domain that declares no section. The capture, evaluation and sleep tools read with the packaged
incident domain's, in
[`src/goal_chainer/domains/data/incident.metta`](../src/goal_chainer/domains/data/incident.metta),
which `default_reader(budget=...)` reads once per process within its first caller's deadline and
charges none of its inferences, being fixed startup work:

| id | proposition, shortened |
| --- | --- |
| `sensitive-data` | the content includes, or may include, personal or confidential data |
| `public-data` | the information is public and safe to share openly |
| `unverified` | the facts are not yet verified or confirmed, as the text says, not because an incident is under way |
| `coordination-needed` | responders need shared context to coordinate |
| `customer-emails` ... `raw-logs` | the content includes that kind of data |
| `mood` (a choice) | whether the text asks, directs or states |

Which of these the incident domain's theory treats as sensitive categories is that theory's own
declaration, its `(given (sensitive-category ID "label"))` facts in
`domains/data/incident.metta`, not the reading declaration's.

Jev, TypeSafe's System One model, answers each proposition as one Choice over the declared answers.
The incident declaration's three are:

| answer | means | as evidence |
| --- | --- | --- |
| `supported` | the text states or clearly implies the proposition | for it |
| `contradicted` | the text states or clearly implies its negation | against it |
| `unknown` | the text does not settle it | none: silence is not refutation |

These are natural language inference's entailment, contradiction and neutral. A Noul's single
yes-probability cannot tell "the text denies it" from "the text never mentions it", so the reader
never asks one. What an answer means is its declared direction, never its name: a domain that
calls its answers `holds`, `fails` and `open` gets the same evidence and theory facts.

A binding asks which declared entity a proposition is about. `(gc-reading-binding SIGNAL CONTROL
"instructions" "no-match description")` is one Choice over every entity the domain's bigraph section
declares under `CONTROL`, each offered by its description, and one more option, `no match`, which
the binding's own text describes. The option's name holds a space, so no entity can share it. Jev
identifies an entity only by its description, so every entity a binding offers must have one; an
entity under a control no binding names needs none. The domain loader gives each binding its
control's entities once the domain's checks pass, and the declaration's digest covers each offered
entity and its description, so the binding's cached answers belong to exactly those entities. The
domain digest, which only the review reads, does not change. With the binding above, a domain
declaring two seats asks:

```json
{"type": "choice",
 "instructions": "Which seat does the text say the data left? Statement: Customer data left a seat.",
 "criteria": {"seat": "the seat that owns the focal task",
              "receiving_seat": "the seat the work belongs with",
              "no match": "The text names no seat."}}
```

A local cross-encoder, Qwen3-Reranker-0.6B, then ranks the text's sentences against each decided
proposition's question and names the passage that answers it. The ranking grounds a reading in the
text; it never weighs evidence, because the reranker's absolute score is not calibrated as "this
passage answers the question either way".

The reranker is a causal yes-or-no judge, and every pair's prompt starts with the same system turn
and ranking instruction: 63 tokens for the incident domain. The reader encodes that shared part once
per loaded model and instruction, keeps its keys and values (14 MB for the pinned base) while a
reader of that instruction holds them, and runs only each pair's question, passage and answer prompt
through the model on them, a batch of `predict`'s size at a time. On the incident corpus's 39 reads
this took 55.5 s where sentence-transformers' `predict` took 107.1 s, on a loaded 12-thread host at 4
threads, and every read was faster. The tokens are `predict`'s own, so the template, the instruction
and truncation are unchanged. A pair truncated into the shared part is scored by `predict` whole,
and so is every pair of a cross-encoder that reads both ways, such as a BERT-style classifier.

The scores differ from `predict`'s by float32 rounding, not bit for bit. On the corpus a grounding
score's last digits moved by at most 6.6e-6, while `predict`'s own moved by up to 4.8e-6 between
batches of different pairs; on 32 of the 39 reads the cached difference was larger than that read's
own batch difference. The tests accept a difference of 1e-5, a tolerance they exercise on the corpus
and on random judges, not a bound anyone has proved for other weights or texts. Where a question's
two best passages score closer than that, the cached scores can ground it in the other one. Jev's
answers, which alone decide what a reading supports or contradicts, do not change; the passage is the
reading's explanatory excerpt. Ten questions read against eight corpus texts' nine sentences, and
against `Raw logs include customer emails. Engineering needs the incident room.`, were each grounded
in the same passage either way.

Here is the shape of one reading of `Checkout is down. Raw logs include customer emails.
Engineering needs the incident room.`, abridged (the probabilities are illustrative):

```json
{
  "model": "jev-1.13.0",
  "revision": "3755e162d895b5350e8c29a1b7d4f6e0c3a9d1f2e4b6a8c0d2f4e6a8b0c2d4e6",
  "domain": "incident",
  "declaration": "d43bc0fe604e...",
  "propositions": [
    {"id": "sensitive-data", "answer": "supported", "direction": "for", "probability": 0.93,
     "grounding": {"passage": "Raw logs include customer emails.", "score": 0.98},
     "estimator": "model-proposed"},
    {"id": "unverified", "answer": "unknown", "direction": "none", "probability": 0.88, "grounding": null}
  ],
  "choices": [{"id": "mood", "answer": "declarative"}]
}
```

`Reading.to_dict()` gives the full form. The fact a reading becomes is SNARS's, in
`goal_chainer.snars_ingestion`: `reading_facts()` turns a reading into one
`(gc-reading <source> <trust> <id> <answer> <p> (provenance <model> <answer-key> <passage>))` fact
per proposition, and `ReadingFact.parse` reads one back or rejects it, so importing SNARS imports
no reader. A fact's grammar is the same for every domain; whether its proposition and answer are
declared is the declaration's to say, by `ReadingDeclaration.admit`.

## How SNARS believes a reading

`SnarsSession.ingest_text(text, source=..., trust=...)` reads the text and stores its `gc-reading`
facts as one ingestion event, with the reader revision. A request is read under the source
`goalchainer:request`, and each memory text a decision admits is read into the request's context,
under the same source and trust, because WMTM gives no provenance that makes a memory text
independent of the request. Every batch admits a stored fact only through `ReadingFact.parse`, and
refuses one whose readings of a source carry two trusts, so a store cannot carry anything else
into a program.

When a policy batch runs, `src/goal_chainer/policy/goalchainer_policy.metta` believes each source's
readings of each declared proposition once, as the statement `(has-property "request" ID)`, from
the mean of the evidence its decided readings assert, under that source's one trust. A `none`
reading asserts nothing, so it is no argument to the mean, rather than a vacuous one that would
halve it; one reading is believed as itself. What an answer means comes from its
`gc-reading-option` row in the declaration, so the policy never names an answer. A SNARS session
reads with the reader its caller opens it with, and every batch that includes the policy carries
that reader's declaration as its section's forms beside its facts, so the policy reads the rows
the facts were admitted against and the compiled worlds hold no domain:

| option direction | belief about the proposition's statement |
| --- | --- |
| `for` | 8 × p units of evidence for it |
| `against` | 8 × p units of evidence against it |
| `none` | nothing |

Here p is the probability of the answer Jev decided. For example, `sensitive-data` read as
`supported` at 0.9 from the request is 7.2 units for "the request involves sensitive data", and a
memory text at trust 0.5 that reads `coordination-needed` as `supported` at 0.7 adds 2.8.

The weight 8 is the per-property weight of the HyperBase label scan this rule replaced. It is a
model-proposed assumption, not a calibration: a Jev probability says how likely it is that the
text states something, not how likely that thing is to be true, and the decided answer drops the
rest of the distribution. `contradicted` 0.8 with `unknown` 0.2 and `contradicted` 0.8 with
`supported` 0.2 both become 6.4 units against, although only the second gives the property any
support. Every belief carries the reading's provenance (model, answer key, grounding passage) and
`(estimator model-proposed)` in its meta channel.

<!-- am[implements a-ie-s7-docs-1018@83a871] -->
The policy holds no domain's knowledge: it registers no rewrite rule and believes no fact of its
own, so a session's world believes only its readings and what its caller believes. A caller reads
what a session believes of a proposition with `SnarsSession.belief` of its statement, for
`sensitive-data` `(sn p so "has-property" ((arg s (sn c "request")) (arg o (sn c "sensitive-data"))))`,
or from the command line with `goalchainer snars --inference-budget N --timeout-seconds S explain
--domain incident --request TEXT --statement STATEMENT`, whose `belief` is the record
`SnarsSession.belief` parses.
What a domain concludes from its readings, such as which actions it forbids, is its own review's:
the domain's deontic theory decides it, never a SNARS rule ([relevance review](relevance-review.md)).

SNARS keys a receipt by statement and source, so one text read twice under one source is one
receipt, not two, even when a promoted cross-encoder grounds it in another passage: the session
stores a second ingestion event under the new reader revision, and its grounding joins the
statement's meta channel, but the evidence does not grow. Readings from different sources fuse as
independent testimony, and SNARS learns a lower trust ratio for a source that disagrees with the
others, so a disagreeing memory text counts for less than its stated trust.

A session believes only the readings of the texts it read itself. A persistent store keeps the
readings of every text it ever read, and every batch replays them all, so a decision on one
request could otherwise believe what an earlier request said, even under the same source. So a
batch replays every stored event except the readings of texts its session did not read. To look
at a stored request again, read its text again: the same text under the same source adds no event
and no evidence, and its cached answers are replayed.

## How the review reads a reading

`goal_chainer.reading_projection.signal_readings(reading, declaration, observed_at=...,
valid_until=...)` hands a reading to the relevance review as one `SignalReading` per declared
proposition, under the proposition's own id. The declaration is the one the domain declares, and a
reading made under another is refused with `InvalidInputError`. The state comes from the direction
of the decided answer:

| option direction | review state | estimator class |
| --- | --- | --- |
| `for` | `detected` | `model-proposed` |
| `against` | `refuted` | `model-proposed` |
| `none` | `unknown` | none |

The class is `model-proposed` whatever Jev's probability, since a Jev answer is a model's estimate.
That class is the shared vocabulary's lowest tier and establishes nothing, so a measured contrary
overrules it and no claim is ever Checked on it. The source, `jev:<model>:<answer key>`, names the
Jev answer and is part of the observation's identity. The note, `supported 0.87: <passage>`,
carries the grade and grounding passage for people and takes no part in a decision. The caller
supplies `observed_at` and `valid_until`: a reading of a request's text holds for that request.
The graded reading stays whole for SNARS, as above.

## How a binding's answer becomes an entity reading

`goal_chainer.reading_projection.entity_readings(reading, declaration, observed_at=...,
valid_until=...)` places a proposition's reading on the entity its binding chose, as one
`EntityReading` per binding. The entity is the binding's and the evidence the proposition's:

| proposition's answer | binding's answer | entity reading |
| --- | --- | --- |
| `for` direction | an entity E | detected on E: the planner's claim `(On (Signal S) E)` |
| `against` direction | an entity E | refuted on E: the claim `(Not (On (Signal S) E))` |
| `none` direction | anything | none |
| anything | `no match` | none |

Choosing one entity says nothing about the others, so they stay unknown, never refuted. Every
entity reading is `model-proposed` whatever either probability, so it never makes a claim Checked.
Its observation id covers the reading's identity, the entity and the binding answer's source, so it
never equals the proposition reading's own. An `EntityReading` is its own type and never reaches the
review, which folds every `SignalReading` of a signal into that signal's one belief. It is the
planner's input: `plan` and `admit` take entity readings in their one `readings` sequence beside signal
readings, and a request's `reading` hands its entity readings to them beside the context's readings,
while the review packet keeps signal readings alone. `entity_term(reading)` writes it as
`(EntityReading SIGNAL ENTITY STATE ESTIMATOR VALIDITY ID)`, the entity a symbol as the planner's
anchors write entities, and the planner's row for it is the shared reading row with only its claim
placed on the entity.

## Set up

```bash
./scripts/setup-semantic.sh
```

It installs the locked `semantic` extra into the project environment (sentence-transformers, CPU
torch, typesafe-sdk, sentencex) without removing other extras, then downloads every file of
`Qwen/Qwen3-Reranker-0.6B` at revision `e61197ed45024b0ed8a2d74b80b4d909f1255473` (Apache-2.0,
1.19 GB of weights) and checks each against the size and SHA-256 pinned in
`src/goal_chainer/semantic_models.py`. The download is anonymous: Hugging Face tokens in the
environment are hidden for its duration, because the model is public and an expired stored token
answers 401 even for public files.

The files go to `GOALCHAINER_MODEL_CACHE` when it is set, else to your user cache,
`$XDG_CACHE_HOME/goalchainer/models` (by default `~/.cache/goalchainer/models`), the same place
whether GoalChainer runs from a checkout or an installed wheel. A process with none of these and
no home directory, as a uid with no passwd entry, is refused with `DependencyUnavailableError`
asking for `XDG_CACHE_HOME`, as it is for the answer cache below. A second run hashes the cached
files and downloads nothing. The ready stamp is written only after every file verifies, so a
partial cache is never treated as ready.

Outside a checkout, provision with `python -m goal_chainer.semantic_models provision` in an
environment that has the `semantic` extra.

| exit | meaning |
| --- | --- |
| 0 | the pinned model is ready |
| 1 | a file could not be downloaded |
| 2 | usage, or uv is missing |
| 3 | a downloaded file failed verification and was removed |

`python -m goal_chainer.semantic_models verify` re-hashes a ready cache on demand.

## Jev answers and the replay cache

Jev is a hosted service. A question the answer cache lacks is sent to it with the key in
`TYPESAFE_API_KEY`. Every answer is stored as one JSON file named by the SHA-256 of the pinned
model, the text and the question, so the same question about the same text is never asked twice
and a reading's answers replay exactly. Its grounding scores are computed again on each read, so
they can differ in their last digits under another scoring implementation, library version or batch
of pairs, and where two passages nearly tie, so can the excerpt a question is grounded in. The model
is pinned as `jev-1.13.0`, a versioned ID, because an alias such as `jev-latest` moves to new
releases.

A stored entry never changes. Jev samples its answers, so two readers that miss the same question
at the same time can get different distributions back. The first one stored stands and both
readings use it, so a reading's provenance always names the answer it used; the other answer is
dropped and counted in `JevClient.conflicts` (and in `conflicts` in the smoke report). A refusal
is stored and kept the same way. The cache links each new file into place, as git stores a loose
object, so it needs a filesystem with hard links.

| variable | effect |
| --- | --- |
| `GOALCHAINER_JEV_CACHE` | the answer cache directory, default `$XDG_CACHE_HOME/goalchainer/jev` |
| `GOALCHAINER_JEV_OFFLINE=1` | answer from the cache alone; a missing answer is an error |
| `TYPESAFE_API_KEY` | authorises questions the cache lacks |
| `TYPESAFE_BASE_URL` | where questions go, default `https://api.typesafe.ai` |

Under Omega, the plugin sets these in each skill's process from its configuration keys, and in
the container image the key stays in Omega's gateway; the
[plugin guide](../plugins/goalchainer/README.md#running-in-a-container) lists the keys.

A choice whose most probable answer is below 0.60 is asked twice more and decided on the mean of
the three draws, the rule multinetmetta's `mind.jev` uses after TypeSafe's consistency cookbook.
Each draw is its own cached answer.

Tests replay the committed cache in `tests/data/jev`, so no test calls the service:
`tests/conftest.py` sets both variables for pytest, and `plugins/goalchainer/tests/run.sh` sets them
for the OmegaClaw plugin's MeTTa suite, whose skills read in a child process that inherits them.
Every file there was captured from the live service, never written by hand. To refill it after a
question, a text or the model changes:

```bash
uv run --frozen --extra dev --extra semantic python -m goal_chainer.semantic_capture smoke \
    --inference-budget 1000000 --timeout-seconds 120
uv run --frozen --extra dev --extra semantic python -m goal_chainer.semantic_capture capture --max-requests 200
```

`smoke` sends one request (every reading question about one short incident text, 1,765 input tokens
on `jev-1.13.0`) within the limits its command line gives, and checks the answering model and every
answer's options. `capture` runs the
tests once asking Jev for what the cache lacks, then again offline, which must pass, and when those
runs covered the whole suite it deletes the answers nothing read. It runs pytest alone, so it asks
for, and keeps, only what pytest reads: a text the plugin's MeTTa suite decides has to be one a
pytest test reads as well. Both read the key from
`TYPESAFE_API_KEY` or, when that is unset, from a file of yours that no other user can read or
write (`chmod 600`) holding a `TYPESAFE_API_KEY=` line, by default `~/.config/typesafe/env`. They
never print it. Jev bills input tokens at $0.042 per million, so a full capture costs well under a
cent.

A run of the whole suite can take longer than you want one test run to take, so `capture` also
takes shards. Each `--shard` is one quoted set of pytest arguments; the shards run one after
another into the same cache, under one `--max-requests` cap shared between them, and any other
pytest arguments go to every shard:

```bash
uv run --frozen --extra dev --extra semantic python -m goal_chainer.semantic_capture capture \
    --max-requests 200 --shard "tests/test_reading_contract.py tests/test_domain_requests.py" \
    --shard "tests/test_semantic_ingest.py" -q
```

It prints how many live requests each shard made and how many of the cap are spent. A shard whose
tests fail is reported, and the shards after it still ask, so one pass gathers every answer the
cap allows; reaching the cap stops the capture. Unread answers are deleted only when every shard
passed offline and together they ran every test the suite collects. Otherwise they are kept.

## When the reader cannot read

| error | `details["reason"]` | cause |
| --- | --- | --- |
| `MissingAnswerError` | `not_cached` | offline, and the answer is not in the cache |
| | `no_key` | no TypeSafe key is configured |
| | `unauthorized` | the service refused the key |
| | `rate_limited` | the service kept answering 429 after five retries |
| | `unreachable` | the service could not be reached |
| | `service_error` | the service failed |
| | `refused` | Jev refused the text as too long |
| `DependencyUnavailableError` | | the semantic extra or the provisioned model is missing |
| `ProtocolError` | | Jev answered with another model, or without every option |
| `ReviewTimeout` | | the request's deadline passed before the reading finished |

Every read takes its caller's `RunBudget`, with no default: `SemanticReader.read(text,
budget=...)`, to which a domain request passes its request's budget and a SNARS session its own.
A read whose deadline has passed does not start. Before each Jev request
the reader checks the deadline again, so none is sent after it, and the request's attempts and
retries together get only the seconds left. A request that fails once the deadline has passed raises
`ReviewTimeout`; one that fails with time to spare keeps its reason above. Looking up a stored
answer never consults the budget, but a reading whose deadline passed while Jev answered does not
start ranking passages. Capture's smoke and the evaluation run outside any request, under the
`--inference-budget` and `--timeout-seconds` their command lines require, which bound their Jev
requests the same way, so no Jev request runs without a `RunBudget`.

None of these falls back to keywords or embeddings, and the reader never substitutes another
reading. A caller decides what an unread text means.

## How well it reads

The tests check that the reader replays its answers. They do not check that the answers are
right. A frozen, held-out corpus of 40 short incident texts does that. Each text is labelled by
hand on every proposition and on the mood, and the labels were written before any answer existed;
a proposition's label sits under `labels`, a choice's under its own id, and a binding's under
`bindings` by its signal and then its control, as an offered entity or `no match`, and a label
abstains with `null` in place of its answer, which no option's name can be mistaken for, so a
corpus for another domain names that domain's readings;
[tests/data/reading-corpus/README.md](../tests/data/reading-corpus/README.md) gives the labelling
rule. Score the replayed answers against the labels with:

```bash
uv run --frozen --extra dev --extra semantic python -m goal_chainer.semantic_evaluation \
    --inference-budget 1000000 --timeout-seconds 600 [--domain-file PATH]
```

It scores the packaged incident domain's reading section, or that of the domain file
`--domain-file` names.

It prints, for each declared proposition, choice and binding:
- the number of scored labels;
- accuracy, with a Wilson 95% interval;
- recall for each label;
- the Brier score;
- the calibration gap, mean top probability minus accuracy, so a positive gap is overconfidence.

The Brier score and the gap carry seeded bootstrap 95% intervals. The committed
`tests/data/reading-corpus/report.json` is the same report, and `tests/test_reading_evaluation.py`
regenerates it offline and compares the two, so it cannot drift from the reader. With about 40
labels per proposition, read each row's intervals before its point estimate. The report changes
neither the evidence weights nor any training data. It names the declaration it scored, by domain
and digest, and the settlement its probabilities came from: a question whose top probability is
under 0.60 is re-drawn and three draws are averaged.

The recorded answers read negated mentions as contradictions and paraphrases as support, where
words alone would read the opposite: "not a single email address" contradicts `customer-emails`,
and "a customer's phone number and home address" supports `sensitive-data`. They also read stated
removal as presence: "We stripped the order identifiers" supports `order-ids` (0.86), and
"Credentials are masked ... holds no keys or passwords" supports `tokens-or-secrets` (0.93).
`tests/test_reading_contract.py` pins the second pair against the corpus labels, so a re-captured
answer that reads the removal fails it, and the test then flips to assert the label.

## Reader revision

`Reading.revision` digests what a reading depends on besides its text: the reading declaration's
digest, which pins the Jev model and every question, the identity of the cross-encoder that served
it, the identity of the code that scored its passages and the segmenter's version. The scoring
code's identity is the SHA-256 of `goal_chainer/semantic_ranker/scoring.py` as this process compiled
it, so a change to how pairs are scored is a new revision even when the model's weights stay the
same. Jev's answer keys digest none of this but the model, so a reading under a new revision replays
the same answers. A consumer that stores readings records the revision beside them, so a stored
reading names the reader and the declaration that produced it.

## Serving a reviewed cross-encoder

Each read resolves which cross-encoder to serve. When `goal_chainer.semantic_sleep` has promoted a
reviewed artifact, its `ACTIVE` pointer under `<model cache>/goalchainer-reranker` names it and the
read uses that artifact; otherwise, or after a rollback to the base, the read uses the pinned
Qwen3-Reranker revision. A promotion or rollback takes effect on the next read. The reader refuses,
with `ProtocolError`, an artifact whose manifest records a ranking instruction other than the
reading declaration's, one built on another base, or one whose manifest changed or whose files were
added, removed or resized after publication. The instruction is part of every prompt the model was
evaluated on, so the reader never serves the same weights under a different one, and it never falls
back to the base. Serving checks sizes, not bytes, which promotion hashed in full; it assumes that
only `semantic_sleep` writes under the artifact root and that nothing edits a published artifact in
place, so an edit that keeps a file's size shows only when the artifact is validated with full
hashes again. See [semantic-sleep.md](semantic-sleep.md) for training, evaluation and promotion.

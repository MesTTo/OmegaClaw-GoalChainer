# Reviewed reranker updates

The sleep command trains a local passage reranker from explicitly reviewed relevance labels.
`semantic_artifacts` owns immutable model storage and ACTIVE resolution below both the reader
and the sleep command. The sleep command owns reviewed datasets, evaluation and promotion policy.
SentenceTransformers computes model updates and numerical comparisons. Packaged MeTTa rules
choose the holdout partition, statistical risk budget and admission decision. A reranker score
orders question/passage pairs. It never grants permission, estimates factual truth or changes
GoalChainer's norms.

Install the serving and training extras and provision the pinned serving base:

```sh
uv sync --frozen --extra semantic --extra train
uv run --frozen --extra semantic python -m goal_chainer.semantic_models provision
```

The `train` extra is SentenceTransformers' own training support, including `datasets` and
`accelerate`. Serving needs neither package. Training uses `CrossEncoderTrainer` and its
`BinaryCrossEntropyLoss`, with raw logits passed to `BCEWithLogitsLoss`. Prediction uses sigmoid
scores. The trainer receives exactly `question`, `passage` and `label` columns, in that order;
reviewer and provenance fields never become model inputs. The default reading declaration supplies
the question IDs, question text and ranking instruction. Training and serving use the same
instruction and CPU float32 model computation.

## Import reviewed examples

Prepare a UTF-8 JSONL file containing one object per reviewed pair. Every row requires:

| Field | Meaning |
| --- | --- |
| `example_id` | Stable review identity. Reusing it with different content fails. |
| `question_id`, `question` | The canonical reading-table proposition ID and its exact question. |
| `passage` | An exact substring of `source_text`. |
| `label` | Integer `1` for relevant or `0` for irrelevant, assigned by the reviewer. |
| `reviewer` | The local curator's asserted reviewer identity. |
| `reviewed_at` | ISO-8601 review time including a timezone. |
| `source_group` | Stable provenance family, including correlated documents or paraphrases. |
| `source_id` | Stable identity of the complete source document. |
| `source_text` | The complete source document containing the reviewed passage. |
| `text_digest` | SHA-256 of the exact UTF-8 `source_text` bytes. |

Obtain the canonical questions with:

```sh
uv run python -c 'from goal_chainer.runtime.budget import RunBudget; from goal_chainer.semantic_reader import default_reader; print([(p.id, p.question) for p in default_reader(budget=RunBudget(inference_budget=1000000, timeout_seconds=120)).declaration.propositions])'
```

Compute each digest from the reviewed text, for example
`hashlib.sha256(source_text.encode("utf-8")).hexdigest()`. A model's proposed answer, its score,
an unjudged mined negative or an unknown relevance label is insufficient to create a reviewed
row. The importer rejects missing or extra fields, nonbinary labels, missing reviewers, naive
timestamps, mismatched digests and passages absent from the source.

```sh
uv run python -m goal_chainer.semantic_sleep import reviews.jsonl
uv run python -m goal_chainer.semantic_sleep status
```

Imports retain history and replace the complete store atomically under a filesystem lock.
Reimporting identical review identities adds nothing. Conflicting question, source, example or
question/passage identities fail without modifying the store. Identical source text cannot
declare different provenance groups. A source ID cannot acquire different text. Correct a bad
source or review through a separately curated dataset and registry; changing an old label in
place would invalidate earlier evaluations and is deliberately refused.

`source_group` determines the split before model inputs are built. MeTTa reserves one fifth of
the SHA-256 group-name range for holdout. Every document and question in a provenance family
therefore stays together, and existing assignments remain stable as reviews are appended.
The curator must group related sources honestly. Hashes detect identical text and identity
conflicts; they cannot discover every paraphrase or shared real-world cause.

## Train, inspect and promote

```sh
uv run --extra semantic --extra train python -m goal_chainer.semantic_sleep train \
    --inference-budget 1000000 --timeout-seconds 120
uv run --extra semantic --extra train python -m goal_chainer.semantic_sleep evaluate ARTIFACT_SHA256
uv run python -m goal_chainer.semantic_sleep verify ARTIFACT_SHA256
uv run python -m goal_chainer.semantic_sleep promote ARTIFACT_SHA256
```

`train` reads the incident domain's reading declaration within its limits, whose ranking
instruction the model is prompted with and whose questions every reviewed row must ask word for
word. It uses all retained non-holdout reviews, including old and newly imported examples. It
requires both relevance labels and a separate holdout. It captures the serving identity and
generation before training and updates a separate model instance. The current serving model
is never overwritten. A saved challenger must reproduce its evaluated predictions before it
can be published. The returned artifact is retained even when admission is uncertain or fails;
training alone never changes serving.

Every new snapshot must retain all champion review rows unchanged, including when `--store`
selects another file. The sealed champion split also prevents any earlier holdout group from
entering training or an earlier training group from becoming holdout after a policy edit.
The reservation history freezes those partitions even for rejected or interrupted attempts.

`--epochs`, `--learning-rate`, `--batch-size` and `--seed` are training parameters, recorded in
the immutable manifest. Their defaults are an explicit starting recipe, not tuned domain
performance claims. No epoch selection or tuning uses holdout outcomes. The registry reserves
an evaluation attempt and the complete set of fresh eligible holdout groups before scores are
computed. Failed and interrupted attempts keep their reservations. Reusing previously observed
groups can check retention, but cannot supply fresh statistical admission evidence.

An eligible question within a source group needs at least one reviewed positive and one
reviewed negative passage. Concordance is the fraction of positive/negative score comparisons
ordered correctly; ties get half credit. Ineligible questions supply no ranking observation.
The group metric averages eligible questions equally. The aggregate then weights source groups
equally. No unreviewed positive is inserted into the candidate set.

For each fresh group, let `d` be challenger concordance minus champion concordance. Since
`d` lies in `[-1, 1]`, the one-sided Hoeffding lower bound is:

```text
lower = mean(d) - sqrt(2 * log(1 / alpha_k) / n)
alpha_k = 0.05 / (k * (k + 1))
```

Here `n` counts fresh eligible source groups, and `k` is the atomically reserved test number.
The spending sequence sums to at most `0.05`. That risk budget and the holdout fraction are
explicit conservative policy choices in `sleep_policy.metta`; neither is derived from the
concentration inequality. The lower bound's algebra is strict under its assumptions. Its use
here is conditional on independent, representative groups, a fixed candidate recipe and a
fixed batch chosen before current outcomes are disclosed. Different hashes alone do not
establish independence. Arbitrary within-attempt stopping or adapting to reused holdout results
would defeat the stated guarantee. Fresh groups and burned reservations address repeated
testing; old groups remain available for diagnostic replay only.

MeTTa admits a changed model only when the fresh lower bound is positive, aggregate heldout
concordance does not decrease, and empirical Brier loss does not increase. The retained-group
subset must independently pass both empirical regression checks, so new gains cannot mask old
losses. Brier loss averages squared error within eligible questions and then within groups.
That additional gate narrows admission; it does not prove population Brier improvement,
calibration, future-domain quality or factual truth. Small, unchanged, regressing or uncertain
comparisons receive explicit refusal reasons. Repeated training without new eligible holdout
groups cannot earn automatic admission.

`evaluate` loads the sealed reviewed snapshot and exact champion/challenger models locally,
recomputes paired predictions, and compares them with the sealed predictions and report.
It does not consume a new test or turn an old holdout into fresh evidence. Exact offline replay
assumes the recorded framework and CPU numerical behavior; a different result is a hard error,
not permission to replace the old report.

## Artifact integrity and rollback

The default registry is `model_cache()/goalchainer-reranker`, using
`GOALCHAINER_MODEL_CACHE` or the platform cache selected by `semantic_models.model_cache()`.
An explicit `--root PATH` selects another registry; use a separate root for experiments.

```text
goalchainer-reranker/
  reviewed.json
  evaluations.json
  ACTIVE
  .lock
  <manifest-sha256>/
    goalchainer-artifact.json
    model/                         CrossEncoder.save_pretrained output
    evidence/                      reviews, split, predictions, policy, evaluator, reservation
```

The manifest records the exact base revision, licence and file digests; reviewed dataset digest
and counts; training configuration and framework versions; prompt; weight identities; paired
metrics and admission; timestamp; and previous serving identity and pointer. Its identity is
SHA-256 of canonical JSON with only its own `digest` field excluded. The file inventory hashes
model and evidence bytes, including tokenizer, prompt/preprocessing configuration, evaluation
code and policy. Evaluator evidence contains `evaluation.py` for the sleep implementation and
`artifacts.py` for its artifact validation and storage dependency, and `numbers.py` for shared
finite-number conversion. Promotion requires all three to
match the running implementation. Existing artifacts remain readable and usable for serving
and rollback; an artifact sealed under an earlier evaluator version remains refused for promotion.
Nothing hashes itself. Changing metadata or any inventoried bytes changes the
artifact identity.

Paths must be relative and canonical. Symlink files or directories, traversal, missing files,
extra files, wrong sizes, malformed pointers and incomplete model artifacts fail validation.
Publication writes a separate directory, fsyncs files and directories, then renames it into the
registry. A partial training directory can never become ACTIVE.

`ACTIVE` contains `{"artifact": "<sha256>", "generation": "<uuid>"}`. Absence, or a pointer
whose `artifact` is null, selects the pinned base. Serving captures one pointer per request and
includes the exact identity in the reading revision. Promotion fully hashes the candidate,
requires the sealed evaluator bytes to match the running evaluator, recomputes MeTTa admission
under the sealed current policy, and compares the entire captured
champion pointer under the registry lock. A concurrent promotion or intervening rollback makes
the old comparison stale, even if the model identity later returns to its old value.

Get the current generation from `status`, then request rollback:

```sh
uv run python -m goal_chainer.semantic_sleep status
uv run python -m goal_chainer.semantic_sleep rollback --expected-generation CURRENT_UUID
```

Rollback validates the current artifact and retained parent before replacing ACTIVE. It writes
a fresh generation even when returning to the base. The same filesystem lock protects
promotion and rollback; pointer replacement is atomic and fsynced. A failure before replacement
leaves the old pointer. A filesystem failure after replacement but during directory fsync may
leave the new pointer visible while durability is unconfirmed; inspect `status` and `verify`
before retrying. Do not delete retained ancestors while they are needed for rollback or replay.

Serving's frequent resolution checks the manifest digest, complete inventory, paths, existence
and sizes. `verify`, promotion and rollback hash every file. Same-size edits after verification
therefore require a full verification to detect. The registry assumes authorized local writers
and an ordinary local filesystem with advisory locks and same-filesystem atomic rename. A hash
provides integrity, not authentication: a reviewer name or evaluator report is a local assertion,
not a signed human identity. Keep review and registry write access limited to authorized users.

Commands print JSON. Invalid data, missing dependencies or models, refused admission, stale
baselines, corrupted artifacts and failed writes exit nonzero with a hard error. No command
uploads models or uses hosted or paid compute.

## Verify with a small public model

The integration test uses `prajjwal1/bert-tiny` at commit
`6f75de8b60a9f8a2fdf7b69cbd86d9e64bcb3837`, whose pinned card declares MIT. Provisioning verifies
the Hub's pinned git blob IDs and weight SHA-256. Its older BERT configuration is reconstructed
with Transformers' `BertConfig`; a one-output classification head is initialized with seed 7,
then the complete CrossEncoder construction is pinned by file content. The actual trainer
updates this 4,386,049-parameter model. Synthetic reviewed pairs demonstrate mechanism and
deliberate admission refusal, not GoalChainer task improvement.

```sh
uv sync --frozen --extra semantic --extra train --extra dev
mkdir -p ai-tmp/sleep-check/tmp
TMPDIR="$PWD/ai-tmp/sleep-check/tmp" PYTHONPATH=src uv run --no-sync python tests/test_semantic_sleep.py --prepare-base "$PWD/ai-tmp/sleep-check/tiny-base"
```

Run acceptance in a battery worktree using a revision containing the implementation and tests:

```sh
TMPDIR="$PWD/ai-tmp/sleep-check/tmp" \
GOALCHAINER_SLEEP_TEST_BASE="$PWD/ai-tmp/sleep-check/tiny-base" \
HF_HUB_OFFLINE=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
~/.claude/bin/battery-run /absolute/repository REVISION --label sleep-check -- \
  /absolute/verified/environment/bin/python -m pytest -q \
  tests/test_semantic_sleep.py tests/test_semantic_sleep_artifacts.py
```

The tiny-model test requires the provisioned fixture and fails clearly if it is missing. Its
update, serialization and champion/challenger replay run offline. Store and property tests
exercise strict reviews and leakage; persistence tests exercise tampering, incomplete artifacts,
concurrent/stale promotion, generation changes, rollback and failed pointer replacement.
Reviewed domain holdout, honest provenance groups and sufficient fresh examples are still
required before claiming any real task-quality improvement.

Primary references: [SentenceTransformers training overview](https://www.sbert.net/docs/cross_encoder/training_overview.html),
[6.1.0 trainer source](https://github.com/huggingface/sentence-transformers/blob/v6.1.0/sentence_transformers/cross_encoder/trainer.py),
[6.1.0 BCE loss](https://github.com/huggingface/sentence-transformers/blob/v6.1.0/sentence_transformers/cross_encoder/losses/binary_cross_entropy.py),
[adaptive holdout reuse](https://arxiv.org/abs/1506.02629),
[pinned tiny model](https://huggingface.co/prajjwal1/bert-tiny/tree/6f75de8b60a9f8a2fdf7b69cbd86d9e64bcb3837),
and [Python filesystem durability primitives](https://docs.python.org/3/library/os.html#os.replace).

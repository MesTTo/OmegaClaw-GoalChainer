"""Purpose: score (question, passage) pairs with a local cross-encoder for GoalChainer's semantic
reader: one loaded model per directory shared by every ranker of it, and for a causal yes-or-no judge
the prompt every pair of an instruction shares encoded once, held while a ranker of that instruction
lives, with only each pair's rest run through the model; any other model, and any pair whose tokens
do not start with that prefix, scored by sentence-transformers' predict. goal_chainer.semantic_ranker
pins this file, so the SHA-256 of the bytes this process compiled it from names the code that scores.
"""

from __future__ import annotations

import inspect
import threading
import weakref
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import DependencyUnavailableError


# One loaded cross-encoder and the lock its passes take, shared by every PassageRanker of its model
# directory whatever their instructions, with the batch size predict uses by default. A causal
# yes-or-no judge's encoder also shares the prefix each of its rankers holds for its instruction, only
# weakly, so a prefix lives exactly while some ranker of that instruction does.
# am[implements a-dr-shared-encoder-1018@ef35c7] am[implements a-rpc-adopt-e-1019@f69eef]
# am[implements a-integrate-rpc-cache-lifetime-batching-1019@67ca1c] am[addresses i-rpc-prefix-lifetime-1019@5e8465]
class _Encoder:
    def __init__(self, model: Any) -> None:
        self.model = model
        self.lock = threading.Lock()
        self.judge = _causal_judge(model)
        self.batch = inspect.signature(model.predict).parameters["batch_size"].default
        self.prefixes: weakref.WeakValueDictionary[str, _Prefix] = weakref.WeakValueDictionary()

    # The caller holds the lock. The prefix a new ranker of the instruction is to hold: the one a live
    # ranker of it holds already, else a newly encoded one the encoder then shares; None for a model
    # that is not a judge and for an instruction whose prompts share no prefix, which predict scores.
    # am[implements a-integrate-rpc-cache-lifetime-batching-1019@67ca1c] am[addresses i-rpc-prefix-lifetime-1019@5e8465]
    def prefix(self, instruction: str) -> _Prefix | None:
        if not self.judge:
            return None
        shared = self.prefixes.get(instruction)
        if shared is None:
            shared = _encoded_prefix(self.model, instruction)
            if shared is not None:
                self.prefixes[instruction] = shared
        return shared


# The keys and values a causal judge's layers compute for the tokens every pair of one instruction
# starts with: the chat template's system turn and the instruction up to the query slot, 63 tokens for
# the incident instruction (c-rpc-fixed-prefix-holds-1019). Weakly referable, so the encoder can share
# it without keeping it.
# am[implements a-rpc-adopt-e-1019@f69eef] am[implements a-integrate-rpc-cache-lifetime-batching-1019@67ca1c]
@dataclass(frozen=True, slots=True, weakref_slot=True)
class _Prefix:
    ids: tuple[int, ...]
    layers: tuple[tuple[Any, Any], ...]


# A judge is sentence-transformers' causal-LM cross-encoder: a text-generation Transformer followed by
# LogitScore, which reads the yes and no logits at the last position. A model that attends both ways,
# such as a BERT-style classifier, changes every position's state with the text after it, so no prefix
# of its input can be encoded alone, and predict scores it.
# am[implements a-rpc-adopt-e-1019@f69eef]
def _causal_judge(model: Any) -> bool:
    from sentence_transformers.cross_encoder.modules.logit_score import LogitScore  # noqa: PLC0415

    return (len(model) == 2 and getattr(model[0], "transformer_task", None) == "text-generation"
            and isinstance(model[1], LogitScore))


# am[implements a-rpc-adopt-e-1019@f69eef]
def _unpadded_ids(features: Mapping[str, Any]) -> list[list[int]]:
    """Each row's token ids in a preprocessed batch, its padding removed."""
    masks = features["attention_mask"].bool()
    return [row[mask].tolist() for row, mask in zip(features["input_ids"], masks, strict=True)]


# The prefix is what predict's own preprocess puts before the first text that varies: the prompts of
# two pairs whose texts differ in their first token share exactly the template up to the first text's
# slot. None when they share no token.
# Time: one preprocess of two one-letter pairs and one forward pass over the prefix, 1.44 s for the
# incident instruction's 63 tokens on a loaded 12-thread host, keeping 14.45 MB of float32 keys and
# values for the pinned base (c-rpc-fixed-cache-cost-1019).
# am[implements a-rpc-adopt-e-1019@f69eef] am[rests-on c-rpc-fixed-cache-cost-1019@1459e4]
def _encoded_prefix(model: Any, instruction: str) -> _Prefix | None:
    import torch  # noqa: PLC0415 (the semantic extra)

    first, second = (_unpadded_ids(model.preprocess([(text, text)], prompt=instruction))[0] for text in ("a", "b"))
    size = next((i for i, (x, y) in enumerate(zip(first, second)) if x != y), min(len(first), len(second)))
    if size == 0:
        return None
    ids = tuple(first[:size])
    with torch.inference_mode():
        cache = model[0].model(input_ids=torch.tensor([ids]), use_cache=True, logits_to_keep=1).past_key_values
    return _Prefix(ids, tuple((layer.keys, layer.values) for layer in cache.layers))


# As predict does, the pairs go longest first by characters, predict's own length key, in batches of
# predict's default size, and each batch is preprocessed by predict's own preprocess alone, so its
# template, prompt and truncation are predict's and no more than one batch is ever tokenized and
# padded at once. A pair whose tokens start with the prefix runs only the rest through the model, on a
# fresh cache of the prefix's keys and values; the batch's other pairs go to predict whole. The tails
# are left-padded so each row's last real token sits at the last position, where LogitScore reads
# it, with positions counted from the prefix's end, since the model would otherwise number a padded
# row's tokens by cache slot. They pass through the CrossEncoder's own modules and activation, as
# predict's batches do, so the scores differ from predict's only in float32 rounding
# (c-rpc-tiny-judge-design-holds-1019), and each lands at its pair's place.
# Time: each pair's tokens after the prefix through the model once, at most `batch` rows a pass; a
# batch's preprocess, tails and cache hold at most `batch` rows, the cache rows x (prefix + longest
# tail) x 229,376 bytes for the pinned base, no more than predict's own cache of the whole prompts
# (c-rpc-library-builds-full-cache-1019).
# am[implements a-rpc-adopt-e-1019@f69eef] am[implements a-integrate-rpc-cache-lifetime-batching-1019@67ca1c]
# am[addresses i-rpc-preprocess-request-batch-1019@53dc42] am[rests-on c-rpc-st-forward-passes-cache-1019@099140]
# am[rests-on c-rpc-left-padded-tails-need-positions-1019@f17379]
# am[rests-on c-rpc-dynamiccache-from-tensors-1019@91dc9c] am[rests-on c-rpc-library-builds-full-cache-1019@360490]
# am[rests-on c-rpc-tiny-judge-design-holds-1019@60dabd]
def _judged(model: Any, prefix: _Prefix, pairs: list[tuple[str, str]], instruction: str, batch: int) -> list[float]:
    import torch  # noqa: PLC0415 (the semantic extra)
    from transformers import DynamicCache  # noqa: PLC0415

    size = len(prefix.ids)
    pad = model.tokenizer.pad_token_id
    order = sorted(range(len(pairs)), key=lambda i: -(len(pairs[i][0]) + len(pairs[i][1])))
    scores: dict[int, float] = {}
    model.eval()
    for start in range(0, len(order), batch):
        members = order[start:start + batch]
        rows = _unpadded_ids(model.preprocess([pairs[i] for i in members], prompt=instruction))
        fits = [len(row) > size and tuple(row[:size]) == prefix.ids for row in rows]
        whole = [i for i, fit in zip(members, fits, strict=True) if not fit]
        if whole:
            values = model.predict([pairs[i] for i in whole], prompt=instruction, show_progress_bar=False)
            scores.update(zip(whole, (float(value) for value in values), strict=True))
        cached = [(i, row[size:]) for i, row, fit in zip(members, rows, fits, strict=True) if fit]
        if not cached:
            continue
        width = max(len(tail) for _, tail in cached)
        mask = torch.tensor([[0] * (width - len(tail)) + [1] * len(tail) for _, tail in cached])
        with torch.inference_mode():
            features = {
                "input_ids": torch.tensor([[pad] * (width - len(tail)) + tail for _, tail in cached]),
                "attention_mask": torch.cat([torch.ones(len(cached), size, dtype=mask.dtype), mask], dim=1),
                "position_ids": size + (mask.cumsum(1) - 1).clamp(min=0),
                "past_key_values": DynamicCache(
                    [(keys.expand(len(cached), -1, -1, -1), values.expand(len(cached), -1, -1, -1))
                     for keys, values in prefix.layers],
                    config=model[0].model.config,
                ),
                "logits_to_keep": 1,
            }
            judged = model.activation_fn(model(features)["scores"]).squeeze(-1)
        scores.update(zip((i for i, _ in cached), judged.tolist(), strict=True))
    return [scores[i] for i in range(len(pairs))]


# A model lives while some ranker holds it, so a promoted model replaces the old one once no reader
# keeps the old, and a process holds one model per served directory however many domains it reads.
_ENCODERS: weakref.WeakValueDictionary[Path, _Encoder] = weakref.WeakValueDictionary()
_ENCODERS_LOCK = threading.Lock()


# am[implements a-jev-cross-encoder-1016]
class PassageRanker:
    """Qwen3-Reranker-0.6B through sentence-transformers' CrossEncoder, on the CPU in float32.

    Its CrossEncoder builds the model card's yes-or-no judge prompt token for token and scores
    logit(yes) minus logit(no), so sigmoid gives the card's P(yes) (c-reranker-template-identical-
    1016); float32 because the default bfloat16 drifts by up to 0.0055 (c-reranker-bf16-drift-1016).
    The score orders passages and never weighs evidence (c-reranker-not-answer-judge-1016).

    The model is loaded once per directory and shared by every ranker of it: each ranker passes its
    instruction as the call's prompt, which builds the prompt exactly as a constructor's default
    prompt does (c-dr-call-prompt-identical-1018), and every ranker's passes take the shared model's
    one lock.

    A causal judge such as the pinned base encodes the part of its prompt every pair of an
    instruction shares once, keeps it while some ranker of that instruction does, and runs only
    each pair's question, passage and answer prompt through the model on those keys and values, a
    batch of predict's size at a time. Its scores differ from predict's by float32 rounding, not
    bit for bit, as predict's own differ between batch compositions; the tests accept 1e-5 on the
    incident corpus and on random judges, a tested tolerance that no proof bounds for other weights
    or inputs (c-integrate-rpc-numeric-adoption-1019). Other models are scored by predict.
    """

    # Time: the first ranker of a model directory in a process loads the model, 0.95 s measured
    # (c-dr-request-reader-per-request-1018), under the one registry lock, so first loads of two
    # directories run one after the other; every later ranker of it costs a lock round and a lookup.
    # A judge's ranker then holds its instruction's prefix, which the first live ranker of that
    # instruction encodes under the model's lock, 1.44 s on a loaded 12-thread host
    # (c-rpc-fixed-cache-cost-1019), and every later one takes from the encoder.
    # am[implements a-dr-shared-encoder-1018@ef35c7] am[rests-on c-dr-call-prompt-identical-1018@be6f90]
    # am[implements a-integrate-rpc-cache-lifetime-batching-1019@67ca1c] am[addresses i-rpc-prefix-lifetime-1019@5e8465]
    def __init__(self, model_dir: Path, instruction: str) -> None:
        try:
            import torch  # noqa: PLC0415 (the semantic extra)
            from sentence_transformers import CrossEncoder  # noqa: PLC0415
        except ImportError as error:
            raise DependencyUnavailableError(
                "The semantic extra is not installed; run `uv sync --frozen --extra semantic`.",
                details={"error": str(error)},
            ) from error
        key = Path(model_dir).resolve()
        with _ENCODERS_LOCK:
            encoder = _ENCODERS.get(key)
            if encoder is None:
                encoder = _ENCODERS[key] = _Encoder(CrossEncoder(
                    str(key),
                    device="cpu",
                    local_files_only=True,
                    model_kwargs={"dtype": torch.float32},
                    activation_fn=torch.nn.Sigmoid(),
                ))
        with encoder.lock:
            self._prefix = encoder.prefix(instruction)
        self._encoder = encoder
        self.instruction = instruction

    # Time: one forward pass of the 0.6B model per (question, passage) pair, batched at
    # sentence-transformers' own default size; about 0.23 s a pair in float32 at 8 threads on a
    # loaded 32-thread CPU through predict (c-reranker-dtype-thread-cost-1016), and a causal judge's
    # pass covers only the tokens after its instruction's prefix; concurrent callers wait their turn.
    # am[implements a-jev-library-batch-1016] am[implements a-dr-shared-encoder-1018@ef35c7]
    # am[implements a-rpc-adopt-e-1019@f69eef]
    def scores(self, pairs: Sequence[tuple[str, str]]) -> tuple[float, ...]:
        if not pairs:
            return ()
        with self._encoder.lock:
            if self._prefix is None:
                values = self._encoder.model.predict(list(pairs), prompt=self.instruction, show_progress_bar=False)
            else:
                values = _judged(self._encoder.model, self._prefix, list(pairs), self.instruction, self._encoder.batch)
        return tuple(float(value) for value in values)

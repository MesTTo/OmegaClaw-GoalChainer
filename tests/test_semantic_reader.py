"""Purpose: test the semantic reader's mechanics over the incident reading declaration: the
per-question answer cache and its write-once admission under concurrent writers, offline replay, the
classification of every hosted failure through the real TypeSafe SDK, the request deadline that
bounds every hosted request, three-draw settling, response validation, cross-encoder grounding and
the gc-reading facts a grounded reading projects to.

Answers served here through httpx2.MockTransport are synthetic fixtures for the client's
mechanics, labelled as such; claims about what Jev answers rest only on captured replays."""

from __future__ import annotations

import gc
import hashlib
import inspect
import json
import threading
import time
import uuid
import weakref
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import httpx2
import pytest
from hypothesis import given, settings, strategies as st
from jev_support import answering, client, sure
from typesafe_sdk import RetryPolicy

from goal_chainer import semantic_reader as sr
from goal_chainer import semantic_sleep as ss
from goal_chainer.semantic_ranker import scoring
from goal_chainer.runtime import budget as runtime_budget
from goal_chainer.runtime import modules as runtime_modules
from goal_chainer.runtime.budget import ReviewTimeout, RunBudget
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.domains.forms import parsed_forms
from goal_chainer.domains.readings import HEADS, read_section
from goal_chainer.semantic_models import RERANKER, ready_model_dir
from goal_chainer.errors import DependencyUnavailableError, InvalidInputError, MissingAnswerError, ProtocolError
from goal_chainer.sexpr.codec import SexprCodec
from goal_chainer.snars_ingestion import ReadingFact, reading_facts
from request_support import budget as request_budget
from reading_support import INCIDENT as TABLE, declarations, section, section_text

MODEL = TABLE.model

# The tolerance the tests accept between a causal judge's cached scores and predict's for the same
# pairs, not bit for bit: an acceptance threshold these fixtures exercise, not a bound proved for any
# weights or inputs (c-integrate-rpc-numeric-adoption-1019). On the incident corpus the cached pass
# differs from predict by at most 6.6e-6 while predict's own one-pair-versus-batch difference reaches
# 4.8e-6, and per read the cached difference exceeds that read's own batch difference on 32 of 39
# reads, every one-pair read among them, where predict has no batch difference at all
# (c-rpc-e2e-corpus-1019).
# am[rests-on c-rpc-tested-tolerance-1019@b27dbf] am[rests-on c-rpc-per-read-exceeds-1019@515bc2]
# am[rests-on c-rpc-e2e-corpus-1019@15127a]
SCORE_ROUNDING = 1e-5


# A judge's scores are predict's to within rounding, and each question, whose passages are a run of
# `passages` scores, grounds in predict's passage wherever predict's best two are farther apart than
# twice the rounding, by read()'s rule: the highest score, the first on a tie.
# am[verifies a-rpc-adopt-e-1019@f69eef] am[verifies c-rpc-tested-tolerance-1019@b27dbf]
def _judged_as_predicted(judged, library, passages) -> None:
    assert len(judged) == len(library)
    assert max(abs(a - b) for a, b in zip(judged, library, strict=True)) <= SCORE_ROUNDING
    for start in range(0, len(library), passages):
        row, mine = library[start:start + passages], judged[start:start + passages]
        best = max(range(passages), key=lambda i: (row[i], -i))
        if all(row[best] - row[i] > 2 * SCORE_ROUNDING for i in range(passages) if i != best):
            assert max(range(passages), key=lambda i: (mine[i], -i)) == best


# A causal yes-or-no judge with the pinned base's tokenizer, chat template and LogitScore head but two
# random 64-wide layers, so every token moves its scores and a pass costs milliseconds.
# am[verifies a-rpc-adopt-e-1019@f69eef]
@pytest.fixture(scope="module")
def tiny_judge(tmp_path_factory) -> Path:
    import torch  # noqa: PLC0415 (the semantic extra)
    from transformers import Qwen3Config, Qwen3ForCausalLM  # noqa: PLC0415

    base = ready_model_dir()
    directory = tmp_path_factory.mktemp("tiny-judge")
    for path in base.rglob("*"):
        name = path.relative_to(base).as_posix()
        if path.is_file() and name not in {"model.safetensors", "config.json", "goalchainer-ready.json"}:
            (directory / name).parent.mkdir(parents=True, exist_ok=True)
            (directory / name).write_bytes(path.read_bytes())
    config = json.loads((base / "config.json").read_text(encoding="utf-8"))
    torch.manual_seed(7)
    Qwen3ForCausalLM(Qwen3Config(**{**config, "hidden_size": 64, "intermediate_size": 128, "num_hidden_layers": 2,
                                    "max_window_layers": 2, "num_attention_heads": 4, "num_key_value_heads": 2,
                                    "head_dim": 16, "initializer_range": 0.2})).save_pretrained(directory)
    return directory


# The entries a request can store: Jev's answer, or its refusal of a text as too long.
# am[verifies a-jev-immutable-admission-1016]
def _entry(probabilities=None):
    return {"refused": "max_tokens_exceeded"} if probabilities is None else {
        "model": MODEL, "probabilities": probabilities}


TOO_LONG = {"error": {"code": "max_tokens_exceeded", "message": "max_tokens_exceeded"}}


# am[verifies a-jev-reading-table-1016] am[verifies a-dr-incident-declaration-1018@455a2f]
# am[verifies a-dr-sr-incident-file-1018@31f64a]
def test_the_incident_declaration_is_read_from_metta_in_file_order() -> None:
    assert MODEL == "jev-1.13.0"
    assert TABLE.name == "incident" and TABLE.module == Path("goal_chainer/domains/data/incident.metta")
    assert TABLE.answers == ("supported", "contradicted", "unknown")
    assert [o.direction for o in TABLE.options] == ["for", "against", "none"]
    assert TABLE.decided == frozenset({"supported", "contradicted"})
    assert TABLE.language == "en"
    assert [p.id for p in TABLE.propositions][:4] == [
        "sensitive-data", "public-data", "unverified", "coordination-needed"]
    questions = TABLE.questions()
    assert list(questions) == [p.id for p in TABLE.propositions] + ["mood"]
    assert set(questions["unverified"]["criteria"]) == set(TABLE.answers)
    assert questions["unverified"]["instructions"].endswith(TABLE.propositions[2].statement)
    assert set(questions["mood"]["criteria"]) == {"query", "directive", "declarative"}


# A domain file's reading section, as the domain loader hands it over: the forms whose heads are
# HEADS, here the incident declaration written back as its forms beside a core form, read as the
# same declaration, digest included, since the digest hashes content and not the file's place. A
# form with any other head is refused.
# am[verifies a-dr-readings-move-1018@8f7d09] am[verifies a-dr-sr-snars-batch-declaration-1018@5c965d]
def test_a_domain_file_s_reading_section_reads_as_its_declaration_file(tmp_path) -> None:
    from metta import Expression, Symbol  # noqa: PLC0415 (pymetta, the pinned engine)

    def head(atom):
        parts = list(atom) if isinstance(atom, Expression) else []
        return parts[0].name if parts and isinstance(parts[0], Symbol) else None

    forms = parsed_forms('(gc-signal elsewhere "a condition no proposition reads")\n' + section_text(TABLE), budget=None)
    section = read_section([(form, atom) for form, atom in forms if head(atom) in HEADS], tmp_path / "domain.metta")

    assert section.digest == TABLE.digest and section.propositions == TABLE.propositions
    assert section.content() == TABLE.content()
    assert section.module == tmp_path / "domain.metta"
    with pytest.raises(InvalidInputError, match="not a reading declaration form"):
        read_section(forms, tmp_path / "domain.metta")


# A declaration written back as its section's forms, as a SNARS batch carries it, reads back as
# itself, digest included, whatever its names and texts.
# am[verifies a-dr-sr-snars-batch-declaration-1018@5c965d]
@settings(max_examples=60, deadline=None)
@given(declaration=declarations())
def test_a_declaration_written_back_as_its_forms_reads_back_as_itself(declaration) -> None:
    assert section(section_text(declaration), declaration.module) == declaration


# Rankers of one model directory share the one loaded model whatever their instructions, and each
# scores with its own, and otherwise than under another domain's instruction. predict given the
# instruction as its call's prompt scores exactly as a cross-encoder built with it as its default
# prompt does; the pinned base is a causal judge, so a ranker's scores are that cross-encoder's to
# within float32 rounding and ground every question in the same passage (c-rpc-exact-predict-test-1019).
# am[verifies a-dr-shared-encoder-1018@ef35c7] am[verifies c-dr-call-prompt-identical-1018@be6f90]
# am[verifies a-rpc-adopt-e-1019@f69eef] am[verifies c-rpc-tested-tolerance-1019@b27dbf]
def test_rankers_of_one_model_share_it_and_score_with_their_own_instructions() -> None:
    import torch  # noqa: PLC0415 (the semantic extra)
    from sentence_transformers import CrossEncoder  # noqa: PLC0415

    model_dir = ready_model_dir()
    incident = sr.PassageRanker(model_dir, TABLE.ranking_instruction)
    weather = sr.PassageRanker(model_dir, "Given a question about the weather, retrieve the passage that answers it")
    pairs = [(p.question, text) for p in TABLE.propositions[:3]
             for text in ("Raw logs include customer emails.", "The cause is still being investigated.")]
    baked = CrossEncoder(str(model_dir), device="cpu", local_files_only=True, model_kwargs={"dtype": torch.float32},
                         prompts={"goalchainer": TABLE.ranking_instruction}, default_prompt_name="goalchainer",
                         activation_fn=torch.nn.Sigmoid())
    library = tuple(float(value) for value in baked.predict(pairs, show_progress_bar=False))

    assert incident._encoder is weather._encoder and incident._encoder.judge
    assert tuple(float(value) for value in incident._encoder.model.predict(
        pairs, prompt=TABLE.ranking_instruction, show_progress_bar=False)) == library
    _judged_as_predicted(incident.scores(pairs), library, 2)
    assert weather.scores(pairs) != incident.scores(pairs)


TEXTS = st.text(st.characters(codec="utf-8", exclude_categories=("Cs",)), max_size=60)


# A causal judge scores any pairs as predict does to within rounding and grounds each question as
# predict does: across predict's batch boundary, uneven padding, duplicates, empty and non-Latin
# texts, and questions opening with the colon, newline or tag the prefix ends beside.
# am[verifies a-rpc-adopt-e-1019@f69eef]
@settings(max_examples=40, deadline=None)
@given(questions=st.lists(st.one_of(TEXTS, st.sampled_from([":", "\n", ": Does it?", "<Document>: a"])),
                          min_size=1, max_size=4),
       passages=st.lists(TEXTS, min_size=1, max_size=12))
def test_a_causal_judge_scores_any_pairs_as_predict_does(tiny_judge, questions, passages) -> None:
    ranker = sr.PassageRanker(tiny_judge, TABLE.ranking_instruction)
    pairs = [(question, passage) for question in questions for passage in passages]
    library = [float(value) for value in ranker._encoder.model.predict(
        pairs, prompt=TABLE.ranking_instruction, show_progress_bar=False)]

    assert ranker._encoder.judge
    _judged_as_predicted(ranker.scores(pairs), library, len(passages))


# Truncation is predict's own: a max_seq_length that cuts a long pair after the instruction's prefix
# leaves it reusing the prefix and scored as predict does to within rounding, and one that cuts into
# the prefix, shorter than the prefix and the answer prompt kept after it, leaves no pair starting with
# it, so every pair goes to predict whole and the scores are predict's own, bit for bit.
# am[verifies a-rpc-adopt-e-1019@f69eef]
def test_truncation_is_predicts_and_a_pair_cut_into_the_prefix_goes_to_predict(tiny_judge) -> None:
    ranker = sr.PassageRanker(tiny_judge, TABLE.ranking_instruction)
    model = ranker._encoder.model
    instruction = TABLE.ranking_instruction
    pairs = [("a", "b"), (TABLE.propositions[0].question, "Raw logs include customer emails. " * 4)]
    prefix = ranker._prefix.ids
    full = [len(row) for row in scoring._unpadded_ids(model.preprocess(pairs, prompt=instruction))]
    limit = model[0].max_seq_length
    try:
        model[0].max_seq_length = len(prefix) + 24
        kept = scoring._unpadded_ids(model.preprocess(pairs, prompt=instruction))
        after = ranker.scores(pairs), [float(v) for v in model.predict(pairs, prompt=instruction, show_progress_bar=False)]
        model[0].max_seq_length = 40
        cut = scoring._unpadded_ids(model.preprocess(pairs, prompt=instruction))
        whole = ranker.scores(pairs), tuple(float(v) for v in model.predict(pairs, prompt=instruction, show_progress_bar=False))
    finally:
        model[0].max_seq_length = limit

    assert full[1] > len(prefix) + 24 and [len(row) for row in kept] == [min(n, len(prefix) + 24) for n in full]
    assert all(tuple(row[:len(prefix)]) == prefix for row in kept)
    _judged_as_predicted(*after, 1)
    assert not any(tuple(row[:len(prefix)]) == prefix for row in cut)
    assert whole[0] == whole[1]


# Pairs that do not start with the prefix go to predict and pairs that do reuse it, in one call, each
# score landing at its pair's place: here the prefix runs one token into the question, so only the
# questions opening with that token share it.
# am[verifies a-rpc-adopt-e-1019@f69eef]
def test_pairs_without_the_prefix_go_to_predict_beside_pairs_that_reuse_it(tiny_judge) -> None:
    import torch  # noqa: PLC0415 (the semantic extra)

    ranker = sr.PassageRanker(tiny_judge, TABLE.ranking_instruction)
    model = ranker._encoder.model
    instruction = TABLE.ranking_instruction
    ids = scoring._unpadded_ids(model.preprocess([("a", "z")], prompt=instruction))[0][:len(ranker._prefix.ids) + 1]
    with torch.inference_mode():
        cache = model[0].model(input_ids=torch.tensor([ids]), use_cache=True, logits_to_keep=1).past_key_values
    longer = scoring._Prefix(tuple(ids), tuple((layer.keys, layer.values) for layer in cache.layers))
    pairs = [("b", "a"), ("a", "b"), ("c", "a"), ("a", "c"), ("a", "b")]
    rows = scoring._unpadded_ids(model.preprocess(pairs, prompt=instruction))

    assert [tuple(row[:len(ids)]) == longer.ids for row in rows] == [False, True, False, True, True]
    _judged_as_predicted(scoring._judged(model, longer, pairs, instruction, ranker._encoder.batch),
                         [float(v) for v in model.predict(pairs, prompt=instruction, show_progress_bar=False)], 1)


# A cross-encoder that reads both ways, a BERT-style classifier, has no prefix it can encode alone, so
# predict itself scores its pairs.
# am[verifies a-rpc-adopt-e-1019@f69eef]
def test_a_cross_encoder_reading_both_ways_is_scored_by_predict_itself(tmp_path) -> None:
    import torch  # noqa: PLC0415 (the semantic extra)
    from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast  # noqa: PLC0415

    (tmp_path / "vocab.txt").write_text("\n".join(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", *"abcdefghijklmnopqrstuvwxyz?.,"]))
    torch.manual_seed(7)
    BertForSequenceClassification(BertConfig(vocab_size=34, hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
                                             intermediate_size=32, num_labels=1)).save_pretrained(tmp_path / "bert")
    BertTokenizerFast(vocab_file=str(tmp_path / "vocab.txt")).save_pretrained(tmp_path / "bert")
    ranker = sr.PassageRanker(tmp_path / "bert", TABLE.ranking_instruction)
    pairs = [(p.question, text) for p in TABLE.propositions[:2] for text in ("Raw logs.", "Nothing leaked.")]

    assert not ranker._encoder.judge and ranker._prefix is None
    assert ranker.scores(pairs) == tuple(float(value) for value in ranker._encoder.model.predict(
        pairs, prompt=TABLE.ranking_instruction, show_progress_bar=False))


# An instruction's prefix lives exactly while a ranker of that instruction does: rankers of one
# instruction share one prefix, and once the last of them is gone the shared model keeps none of it,
# while a live ranker of another instruction keeps its own.
# am[verifies a-integrate-rpc-cache-lifetime-batching-1019@67ca1c]
def test_an_instructions_prefix_lives_while_a_ranker_of_it_does(tiny_judge) -> None:
    weather = "Given a question about the weather, retrieve the passage that answers it"
    kept = sr.PassageRanker(tiny_judge, TABLE.ranking_instruction)
    first, second = sr.PassageRanker(tiny_judge, weather), sr.PassageRanker(tiny_judge, weather)
    encoder = kept._encoder
    gone = weakref.ref(first._prefix)

    assert first._encoder is second._encoder is encoder
    assert first._prefix is second._prefix is encoder.prefixes[weather]
    assert first._prefix is not kept._prefix
    del first
    gc.collect()
    assert gone() is not None and encoder.prefixes[weather] is second._prefix
    del second
    gc.collect()
    assert gone() is None and weather not in encoder.prefixes
    assert encoder.prefixes[TABLE.ranking_instruction] is kept._prefix


# As predict does, a judge preprocesses no more than predict's batch of pairs at a time, longest first
# by characters, so it never tokenizes and pads the whole request at once, and each score lands at its
# pair's place.
# am[verifies a-integrate-rpc-cache-lifetime-batching-1019@67ca1c]
def test_a_judge_preprocesses_a_batch_at_a_time_as_predict_does(tiny_judge, monkeypatch) -> None:
    ranker = sr.PassageRanker(tiny_judge, TABLE.ranking_instruction)
    model, batch = ranker._encoder.model, ranker._encoder.batch
    preprocess, calls = model.preprocess, []

    def recorded(inputs, **kwargs):
        calls.append([len(question) + len(passage) for question, passage in inputs])
        return preprocess(inputs, **kwargs)

    monkeypatch.setattr(model, "preprocess", recorded)
    pairs = [(f"Question {i}?", "A passage. " * (1 + i * 7 % 11)) for i in range(2 * batch + 5)]
    library = [float(value) for value in model.predict(pairs, prompt=TABLE.ranking_instruction, show_progress_bar=False)]
    predicted, calls[:] = list(calls), []
    judged = ranker.scores(pairs)
    lengths = [length for call in calls for length in call]

    assert [len(call) for call in predicted] == [len(call) for call in calls] == [batch, batch, 5]
    assert lengths == sorted(lengths, reverse=True) == sorted((len(q) + len(p) for q, p in pairs), reverse=True)
    _judged_as_predicted(judged, library, 1)


# The scoring code's identity is the SHA-256 of the scoring module's bytes, the copy the pinned
# loader compiled, so it names the code that scores with no model loaded and nothing hashed per read.
# am[verifies a-rpc-reading-scoring-identity-1019@452cee]
def test_the_scoring_identity_names_the_scoring_modules_bytes() -> None:
    from goal_chainer import semantic_ranker  # noqa: PLC0415

    assert semantic_ranker.scoring_identity() == hashlib.sha256(Path(scoring.__file__).read_bytes()).hexdigest()
    assert sr.scoring_identity is semantic_ranker.scoring_identity and sr.PassageRanker is scoring.PassageRanker


# Changed scoring code is a new reader revision and nothing else: the text's Jev answers replay from
# the cache entries the first read stored, under the same keys and with no second request, so the two
# readings ground in the same passages and give the same evidence facts, while their revisions differ
# (c-rpc-revision-not-evidence-identity-1019).
# am[verifies a-rpc-reading-scoring-identity-1019@452cee]
def test_changed_scoring_code_is_a_new_revision_with_the_same_answers_and_evidence(tmp_path, monkeypatch) -> None:
    calls: list = []

    def answer_for(q, state):
        if q == "mood":
            return sure(q, state)
        top = "supported" if q == "sensitive-data" else "unknown"
        return {option: (0.9 if option == top else 0.05) for option in TABLE.answers}

    served = sr.ServedRanker("base", tmp_path)
    jev = sr.JevClient(sr.AnswerCache(tmp_path / "answers"), MODEL, client_factory=client(answering(answer_for, calls=calls)))
    reader = sr.SemanticReader(declaration=TABLE, jev=jev, serve=lambda: served,
                               load=lambda _served: SimpleNamespace(scores=lambda pairs: tuple(0.5 for _ in pairs)))
    text = "Raw logs include customer emails. Engineering needs the incident room."
    first = reader.read(text, budget=request_budget())
    asked = len(calls)
    monkeypatch.setattr(sr, "scoring_identity", lambda: "another scoring implementation")
    second = reader.read(text, budget=request_budget())
    codec = SexprCodec()

    assert asked > 0 and len(calls) == asked
    assert first.revision != second.revision == reader.revision(served)
    assert first.to_dict() == {**second.to_dict(), "revision": first.revision}
    assert reading_facts(first, source="s", trust=1.0, codec=codec) == reading_facts(second, source="s", trust=1.0, codec=codec)


# am[verifies a-jev-client-1016]
# am[verifies a-jev-immutable-admission-1016]
def test_answer_cache_keys_hash_model_state_and_question(tmp_path) -> None:
    cache = sr.AnswerCache(tmp_path)
    question = TABLE.questions()["unverified"]
    key = cache.key(MODEL, {"text": "a"}, question)

    assert key == cache.key(MODEL, {"text": "a"}, dict(reversed(list(question.items()))))
    assert key != cache.key(MODEL, {"text": "b"}, question)
    assert key != cache.key("jev-1.14.0", {"text": "a"}, question)
    answer = _entry({"supported": 0.7, "contradicted": 0.2, "unknown": 0.1})
    assert cache.admit(key, answer) is True
    assert cache.get(key) == answer
    assert sorted(p.name for p in tmp_path.iterdir()) == [f"{key}.json"]


# For any order of writes to one key, the first entry stands, a repeat of it is admitted as a
# no-op, and every different entry is refused and leaves no file behind.
# am[verifies a-jev-immutable-admission-1016]
@settings(deadline=None, database=None)
@given(
    st.lists(
        st.one_of(
            st.none(),
            st.sampled_from([0.05, 0.1, 0.45, 0.9]).map(
                lambda p: {"supported": p, "contradicted": round(1 - p - 0.05, 2), "unknown": 0.05}),
        ).map(_entry),
        min_size=1,
        max_size=6,
    )
)
def test_the_first_entry_stored_under_a_key_never_changes(tmp_path_factory, entries) -> None:
    directory = tmp_path_factory.mktemp("admit")
    cache = sr.AnswerCache(directory)

    admitted = [cache.admit("k", entry) for entry in entries]

    assert admitted == [entry == entries[0] for entry in entries]
    assert cache.get("k") == entries[0]
    assert sorted(p.name for p in directory.iterdir()) == ["k.json"]


# Another reader of the same text stores its entry while this request is in flight. Whatever this
# request gets back, an answer or a refusal, the entry stored first stands, the reading returns
# what that entry says, and a different entry is counted as a conflict.
@pytest.mark.parametrize(
    "standing",
    [_entry({"supported": 0.9, "contradicted": 0.05, "unknown": 0.05}),
     _entry({"supported": 0.05, "contradicted": 0.9, "unknown": 0.05}),
     _entry()],
    ids=["same-answer", "other-answer", "refusal"],
)
@pytest.mark.parametrize("returned", ["answer", "refusal"])
# am[verifies a-jev-immutable-admission-1016]
def test_an_entry_stored_during_a_request_stands_and_the_reading_uses_it(tmp_path, standing, returned) -> None:
    cache = sr.AnswerCache(tmp_path)
    state = {"text": "Raw logs include customer emails."}
    question = {"unverified": TABLE.questions()["unverified"]}
    key = cache.key(MODEL, state, question["unverified"])
    ours = _entry(sure("unverified", state)) if returned == "answer" else _entry()

    def handler(request):
        assert cache.admit(key, standing)
        return answering(sure)(request) if returned == "answer" else httpx2.Response(400, json=TOO_LONG)

    jev = sr.JevClient(cache, MODEL, client_factory=client(handler))
    if "refused" in standing:
        with pytest.raises(MissingAnswerError) as raised:
            jev.answers(state, question, budget=request_budget())
        assert raised.value.details["reason"] == "refused"
        assert raised.value.details["key"] == key
    else:
        answer = jev.answers(state, question, budget=request_budget())["unverified"]
        assert answer.probabilities == standing["probabilities"]
    assert jev.conflicts == int(ours != standing)
    assert (tmp_path / f"{key}.json").read_bytes() == sr.canonical(standing).encode("utf-8")
    assert sorted(p.name for p in tmp_path.iterdir()) == [f"{key}.json"]


# am[verifies a-jev-immutable-admission-1016]
def test_writers_racing_on_one_key_leave_exactly_one_entry(tmp_path) -> None:
    cache = sr.AnswerCache(tmp_path)
    entries = [_entry({"supported": i / 16, "contradicted": 1 - i / 16, "unknown": 0.0}) for i in range(16)]
    start = threading.Barrier(len(entries))

    def admit(entry):
        start.wait()
        return cache.admit("k", entry)

    with ThreadPoolExecutor(len(entries)) as pool:
        admitted = list(pool.map(admit, entries))

    assert admitted.count(True) == 1
    assert cache.get("k") == entries[admitted.index(True)]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["k.json"]


# Two readers miss one key, and both requests are in flight before either stores, so Jev's two
# different samples race to the cache: both readings return the one entry that won.
# am[verifies a-jev-immutable-admission-1016]
def test_readers_that_both_miss_a_key_return_the_one_entry_stored(tmp_path) -> None:
    cache = sr.AnswerCache(tmp_path)
    state = {"text": "The root cause is unclear."}
    question = {"unverified": TABLE.questions()["unverified"]}
    key = cache.key(MODEL, state, question["unverified"])
    samples = iter([{"supported": 0.45, "contradicted": 0.35, "unknown": 0.20},
                    {"supported": 0.30, "contradicted": 0.50, "unknown": 0.20}])
    taking = threading.Lock()
    in_flight = threading.Barrier(2)

    def handler(request):
        with taking:
            sample = next(samples)
        in_flight.wait()
        return answering(lambda q, s: sample)(request)

    # A reader that fails before its request reaches the barrier breaks it, so the other reader
    # raises instead of waiting forever, and both failures surface.
    def read(jev):
        try:
            return jev.answers(state, question, budget=request_budget())["unverified"]
        except BaseException:
            in_flight.abort()
            raise

    readers = [sr.JevClient(cache, MODEL, client_factory=client(handler)) for _ in range(2)]
    with ThreadPoolExecutor(2) as pool:
        answers = list(pool.map(read, readers))

    assert answers[0] == answers[1]
    assert cache.get(key)["probabilities"] == answers[0].probabilities
    assert sorted(jev.conflicts for jev in readers) == [0, 1]
    assert sum(jev.requests for jev in readers) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == [f"{key}.json"]


# One client asked by concurrent reads, as a declaration's process reader is (reader_for), builds
# one hosted client and counts every request: eight first requests released together all reach the
# connection while the first is still building its client, and each request and its tokens count.
# am[verifies a-integrate-domain-reader-reuse-1018@bffd2b]
def test_one_client_asked_at_once_builds_one_hosted_client_and_counts_every_request(tmp_path) -> None:
    calls, built = [], []
    released = threading.Barrier(8)

    # A slow first connection: an unguarded check lets every request past it before the first
    # client exists, and each builds its own.
    def connecting():
        built.append(1)
        time.sleep(0.2)

    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL, retry=NO_RETRY,
                       client_factory=_recorded(client(answering(sure, calls=calls)), [], connecting))

    def ask(index):
        released.wait()
        return jev.answers({"text": f"Checkout {index} is down."}, TABLE.questions(), budget=request_budget())

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(ask, range(8)))

    assert len(built) == 1
    assert jev.requests == len(calls) >= 8 and jev.input_tokens == 100 * len(calls)


# am[verifies a-jev-client-1016]
def test_offline_reading_names_every_uncached_question(tmp_path) -> None:
    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL, offline=True)

    with pytest.raises(MissingAnswerError) as raised:
        jev.answers({"text": "Checkout is down."}, TABLE.questions(), budget=request_budget())

    assert raised.value.details["reason"] == "not_cached"
    assert raised.value.details["questions"] == sorted(TABLE.questions())


# am[verifies a-jev-client-1016]
def test_no_key_is_a_missing_answer_not_a_crash(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL)

    with pytest.raises(MissingAnswerError) as raised:
        jev.answers({"text": "Checkout is down."}, TABLE.questions(), budget=request_budget())

    assert raised.value.details["reason"] == "no_key"
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.parametrize(
    ("status", "reason"),
    [(401, "unauthorized"), (403, "unauthorized"), (429, "rate_limited"), (500, "service_error"),
     (503, "service_error")],
)
# am[verifies a-jev-client-1016]
def test_hosted_failures_are_classified_and_cache_nothing(tmp_path, status, reason) -> None:
    def handler(request):
        return httpx2.Response(status, json={"error": {"message": "synthetic failure"}})

    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL, client_factory=client(handler))
    with pytest.raises(MissingAnswerError) as raised:
        jev.answers({"text": "Checkout is down."}, TABLE.questions(), budget=request_budget())

    assert raised.value.details["reason"] == reason
    assert "synthetic-test-key" not in json.dumps(raised.value.to_dict())
    assert not list(tmp_path.glob("*.json"))


# am[verifies a-jev-client-1016]
def test_an_unreachable_service_is_classified(tmp_path) -> None:
    def handler(request):
        raise httpx2.ConnectError("synthetic refusal", request=request)

    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL, client_factory=client(handler))
    with pytest.raises(MissingAnswerError) as raised:
        jev.answers({"text": "Checkout is down."}, TABLE.questions(), budget=request_budget())

    assert raised.value.details["reason"] == "unreachable"


# A request's deadline bounds its reading: no hosted request is spent after the deadline, each one
# gets at most the seconds left, a request the deadline cut is ReviewTimeout, one that failed with
# time to spare keeps its reason, and stored answers replay whatever the budget, since reading them
# starts no stage. The clients retry nothing, so a failure is the attempt's own.
NO_RETRY = RetryPolicy(max_retries=0)


# am[verifies a-dr-reader-deadline-1018@1cdce4]
def _spent_budget() -> RunBudget:
    budget = RunBudget(inference_budget=None, timeout_seconds=0.001)
    time.sleep(0.01)
    return budget


# A controlled clock for every RunBudget: now[0] is the monotonic time they read.
# am[verifies a-dr-reader-deadline-1018@1cdce4]
def _controlled_clock(monkeypatch) -> list[float]:
    now = [0.0]
    monkeypatch.setattr(runtime_budget, "time", SimpleNamespace(monotonic=lambda: now[0]))
    return now


# A client factory for make's client that runs connect first, as a slow client construction would,
# and records the keyword arguments of every system_one call in seen.
# am[verifies a-dr-reader-deadline-1018@1cdce4]
def _recorded(make, seen, connect=lambda: None):
    def factory():
        connect()
        real = make()
        send = real.system_one

        def system_one(*args, **kwargs):
            seen.append(kwargs)
            return send(*args, **kwargs)

        real.system_one = system_one
        return real

    return factory


# Every entry that can send a Jev request takes a RunBudget by keyword, with no default a caller
# could inherit unawares and no None: tools outside any request pass one built from their command
# line's limits.
# am[verifies a-dr-reader-budget-required-1018@0b0cce] am[verifies a-dr-sr-tool-budgets-1018@e4d351]
def test_every_reading_entry_takes_its_budget_by_keyword_with_no_default() -> None:
    for entry in (sr.SemanticReader.read, sr.JevClient.answers, sr.JevClient.settle):
        parameter = inspect.signature(entry, eval_str=True).parameters["budget"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, entry.__qualname__
        assert parameter.default is inspect.Parameter.empty, entry.__qualname__
        assert parameter.annotation is RunBudget, entry.__qualname__


# am[verifies a-dr-reader-deadline-1018@1cdce4]
def test_a_spent_budget_spends_no_hosted_request(tmp_path) -> None:
    calls, built = [], []
    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL, retry=NO_RETRY,
                       client_factory=_recorded(client(answering(sure, calls=calls)), [], lambda: built.append(1)))
    with pytest.raises(ReviewTimeout):
        jev.answers({"text": "Checkout is down."}, TABLE.questions(), budget=_spent_budget())

    assert calls == built == [] and jev.requests == 0 and not list(tmp_path.glob("*.json"))


# am[verifies a-dr-reader-deadline-1018@1cdce4]
def test_each_hosted_request_gets_at_most_the_seconds_left(tmp_path) -> None:
    seen = []
    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL, client_factory=_recorded(client(answering(sure)), seen),
                       retry=NO_RETRY)
    jev.answers({"text": "Checkout is down."}, TABLE.questions(),
                budget=RunBudget(inference_budget=None, timeout_seconds=5.0))

    assert seen and all(0 < call["timeout"] <= 5.0 for call in seen)
    assert all(0 < call["retry"].timeout <= 5.0 and call["retry"].max_retries == 0 for call in seen)


# The seconds a request gets are read once its client exists: a client whose construction spends
# part of the deadline leaves the request only the rest, and one that spends all of it sends nothing.
# am[verifies a-dr-reader-deadline-1018@1cdce4]
def test_a_request_gets_only_the_seconds_its_client_construction_left(tmp_path, monkeypatch) -> None:
    now = _controlled_clock(monkeypatch)
    seen = []
    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL, retry=NO_RETRY,
                       client_factory=_recorded(client(answering(sure)), seen, lambda: now.__setitem__(0, 3.0)))
    jev.answers({"text": "Checkout is down."}, TABLE.questions(),
                budget=RunBudget(inference_budget=None, timeout_seconds=5.0))

    assert seen and all(call["timeout"] == 2.0 and call["retry"].timeout == 2.0 for call in seen)


# am[verifies a-dr-reader-deadline-1018@1cdce4]
def test_a_deadline_spent_building_the_client_sends_no_request(tmp_path, monkeypatch) -> None:
    now = _controlled_clock(monkeypatch)
    seen = []
    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL, retry=NO_RETRY,
                       client_factory=_recorded(client(answering(sure)), seen, lambda: now.__setitem__(0, 10.0)))
    with pytest.raises(ReviewTimeout):
        jev.answers({"text": "Checkout is down."}, TABLE.questions(),
                    budget=RunBudget(inference_budget=None, timeout_seconds=5.0))

    assert seen == [] and jev.requests == 0 and not list(tmp_path.glob("*.json"))


# am[verifies a-dr-reader-deadline-1018@1cdce4]
def test_a_request_the_deadline_cut_is_a_review_timeout(tmp_path) -> None:
    def handler(request):
        time.sleep(0.3)
        raise httpx2.ReadTimeout("synthetic deadline", request=request)

    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL, client_factory=client(handler), retry=NO_RETRY)
    with pytest.raises(ReviewTimeout):
        jev.answers({"text": "Checkout is down."}, TABLE.questions(),
                    budget=RunBudget(inference_budget=None, timeout_seconds=0.2))

    assert not list(tmp_path.glob("*.json"))


# am[verifies a-dr-reader-deadline-1018@1cdce4]
def test_a_timeout_with_time_to_spare_keeps_its_reason(tmp_path) -> None:
    def handler(request):
        raise httpx2.ReadTimeout("synthetic timeout", request=request)

    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL, client_factory=client(handler), retry=NO_RETRY)
    with pytest.raises(MissingAnswerError) as raised:
        jev.answers({"text": "Checkout is down."}, TABLE.questions(),
                    budget=RunBudget(inference_budget=None, timeout_seconds=60.0))

    assert raised.value.details["reason"] == "unreachable"


# am[verifies a-dr-reader-deadline-1018@1cdce4]
def test_stored_answers_replay_under_a_spent_budget(tmp_path) -> None:
    cache = sr.AnswerCache(tmp_path)
    state = {"text": "Checkout is down."}
    sr.JevClient(cache, MODEL, client_factory=client(answering(sure))).answers(state, TABLE.questions(),
                                                                               budget=request_budget())

    def never(request):
        raise AssertionError("a stored answer is never asked again")

    replayed = sr.JevClient(cache, MODEL, client_factory=client(never), retry=NO_RETRY).answers(
        state, TABLE.questions(), budget=_spent_budget())

    assert set(replayed) == set(TABLE.questions())


# A read whose deadline has passed does not start, and one whose deadline passed while Jev answered
# starts no ranking stage; either way the cross-encoder is never loaded. The late request is a
# synthetic answer the mock transport returns after the deadline, which it does not enforce.
# am[verifies a-dr-reader-deadline-1018@1cdce4]
def test_a_read_past_its_deadline_starts_no_ranking(tmp_path) -> None:
    text = "Checkout is down. Raw logs include customer emails."
    loads = []
    answer = answering(sure)

    def late(request):
        time.sleep(0.3)
        return answer(request)

    for directory, handler, budget in (
        ("spent", answer, _spent_budget),
        ("late", late, lambda: RunBudget(inference_budget=None, timeout_seconds=0.2)),
    ):
        jev = sr.JevClient(sr.AnswerCache(tmp_path / directory), MODEL, client_factory=client(handler), retry=NO_RETRY)
        reader = sr.SemanticReader(declaration=TABLE, jev=jev, serve=lambda: sr.ServedRanker("base", tmp_path),
                                   load=loads.append)
        with pytest.raises(ReviewTimeout):
            reader.read(text, budget=budget())
        assert jev.requests == (0 if directory == "spent" else 1)

    assert loads == []


# am[verifies a-jev-client-1016]
def test_answers_are_cached_per_question_and_replay_offline(tmp_path) -> None:
    calls = []
    cache = sr.AnswerCache(tmp_path)
    online = sr.JevClient(cache, MODEL, client_factory=client(answering(sure, calls=calls)))
    first = online.answers({"text": "Checkout is down."}, TABLE.questions(), budget=request_budget())

    assert len(calls) == 1 and set(calls[0]["questions"]) == set(TABLE.questions())
    assert calls[0]["model"] == MODEL and calls[0]["state"] == {"text": "Checkout is down."}
    assert online.requests == 1 and online.input_tokens == 100
    assert len(list(tmp_path.glob("*.json"))) == len(TABLE.questions())

    offline = sr.JevClient(cache, MODEL, offline=True)
    assert offline.answers({"text": "Checkout is down."}, TABLE.questions(), budget=request_budget()) == first

    subset = dict(list(TABLE.questions().items())[:2])
    replayed = offline.answers({"text": "Checkout is down."}, subset, budget=request_budget())
    assert replayed == {q: first[q] for q in subset}


# am[verifies a-jev-decided-nli-1016]
def test_an_unsure_answer_is_decided_on_the_mean_of_three_draws(tmp_path) -> None:
    draws = {
        None: {"supported": 0.45, "contradicted": 0.35, "unknown": 0.20},
        1: {"supported": 0.30, "contradicted": 0.50, "unknown": 0.20},
        2: {"supported": 0.30, "contradicted": 0.50, "unknown": 0.20},
    }

    def answer_for(q, state):
        return draws[state.get("draw")] if q == "unverified" else sure(q, state)

    calls = []
    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL, client_factory=client(answering(answer_for, calls=calls)))
    settled = jev.settle("The root cause is unclear.", TABLE.questions(), budget=request_budget())

    assert settled["unverified"].draws == 3
    assert settled["unverified"].answer.decided() == "contradicted"
    assert settled["unverified"].answer.probabilities["contradicted"] == pytest.approx((0.35 + 0.5 + 0.5) / 3)
    assert settled["sensitive-data"].draws == 1
    assert [sorted(c["questions"]) for c in calls[1:]] == [["unverified"], ["unverified"]]


# am[verifies a-jev-client-1016]
def test_too_long_requests_split_and_a_refused_question_replays(tmp_path) -> None:
    def handler(request):
        body = json.loads(request.content)
        if len(body["questions"]) > 1 or "unverified" in body["questions"]:
            return httpx2.Response(400, json=TOO_LONG)
        return answering(sure)(request)

    cache = sr.AnswerCache(tmp_path)
    jev = sr.JevClient(cache, MODEL, client_factory=client(handler))
    with pytest.raises(MissingAnswerError) as raised:
        jev.answers({"text": "x"}, TABLE.questions(), budget=request_budget())
    assert raised.value.details["reason"] == "refused"
    assert raised.value.details["question"] == "unverified"
    # The refusal is stored like an answer, and the questions beside it were still asked.
    assert len(list(tmp_path.glob("*.json"))) == len(TABLE.questions())

    replay = sr.JevClient(cache, MODEL, offline=True)
    with pytest.raises(MissingAnswerError) as replayed:
        replay.answers({"text": "x"}, {"unverified": TABLE.questions()["unverified"]}, budget=request_budget())
    assert replayed.value.details["reason"] == "refused"


# The estimate packs and never refuses: a text it reckons beyond the budget is still sent, one
# question a request, and Jev's answer stands.
# am[verifies a-jev-estimate-packs-only-1016]
def test_a_text_the_estimate_calls_long_is_still_sent(tmp_path) -> None:
    calls = []
    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL, client_factory=client(answering(sure, calls=calls)))
    long_text = "Checkout is down. " * (int(sr.REQUEST_BUDGET * sr.CHARS_PER_TOKEN) // 18 + 1)
    questions = dict(list(TABLE.questions().items())[:3])

    answers = jev.answers({"text": long_text}, questions, budget=request_budget())

    assert set(answers) == set(questions)
    assert [len(call["questions"]) for call in calls] == [1, 1, 1]


# am[verifies a-jev-client-1016]
def test_a_different_model_or_missing_option_is_a_protocol_error(tmp_path) -> None:
    other = sr.JevClient(sr.AnswerCache(tmp_path / "a"), MODEL,
                         client_factory=client(answering(sure, model="jev-1.14.0")))
    with pytest.raises(ProtocolError, match="another model"):
        other.answers({"text": "x"}, TABLE.questions(), budget=request_budget())

    partial = sr.JevClient(sr.AnswerCache(tmp_path / "b"), MODEL, client_factory=client(
        answering(lambda q, s: {"supported": 0.6, "unknown": 0.4})))
    with pytest.raises(ProtocolError, match="options are not"):
        partial.answers({"text": "x"}, {"unverified": TABLE.questions()["unverified"]}, budget=request_budget())
    assert not list((tmp_path / "a").glob("*.json")) and not list((tmp_path / "b").glob("*.json"))


# A live answer outside the simplex is refused before it is cached, never clamped.
# am[verifies a-jev-client-1016]
@pytest.mark.parametrize(
    "probabilities",
    [{"supported": 0.9, "contradicted": 0.6, "unknown": 0.0},
     {"supported": 1.2, "contradicted": -0.2, "unknown": 0.0}],
)
def test_a_live_answer_that_is_not_a_distribution_is_refused(tmp_path, probabilities) -> None:
    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL,
                       client_factory=client(answering(lambda q, s: probabilities)))
    with pytest.raises(ProtocolError, match="invalid"):
        jev.answers({"text": "x"}, {"unverified": TABLE.questions()["unverified"]}, budget=request_budget())
    assert not list(tmp_path.glob("*.json"))


# Every corrupt replay entry fails the reading, offline and online alike, and is never re-asked:
# the online handler fails the test if the client calls it. The first case is the parent's probe
# (i-integrate-jev-replay-validation-1016). Two hold an integer too large for a float, which
# float() overflows on (c-sn-reader-answer-overflow-1018). The last four repeat a key, which plain
# json.loads would read as its last value: one would pass as a valid jev-1.13.0 answer.
# am[verifies a-jev-client-1016@62f0db]
# am[verifies a-jev-strict-replay-json-1016@0e9148] am[verifies a-integrate-reader-number-refusal-1018@e49eaa]
@pytest.mark.parametrize(
    "body",
    [
        '{"model": "unexpected-model", "probabilities": {"supported": 2, "contradicted": -1, "unknown": 0}}',
        '{"model": "jev-1.13.0", "probabilities": {"supported": 2, "contradicted": -1, "unknown": 0}}',
        '{"model": "jev-1.13.0", "probabilities": {"supported": NaN, "contradicted": 0.5, "unknown": 0.5}}',
        '{"model": "jev-1.13.0", "probabilities": {"supported": Infinity, "contradicted": 0, "unknown": 0}}',
        '{"model": "jev-1.13.0", "probabilities": {"supported": 1' + "0" * 400 + ', "contradicted": 0, "unknown": 0}}',
        '{"model": "jev-1.13.0", "probabilities": {"supported": -1' + "0" * 400 + ', "contradicted": 0, "unknown": 0}}',
        '{"model": "jev-1.13.0", "probabilities": {}}',
        '{"model": "jev-1.13.0", "probabilities": {"supported": 0.6, "unknown": 0.4}}',
        '{"model": "jev-1.13.0", "probabilities": {"supported": 0.6, "contradicted": 0.2, "unknown": 0.1, "other": 0.1}}',
        '{"model": "jev-1.13.0", "probabilities": {"supported": "high", "contradicted": 0.2, "unknown": 0.1}}',
        '{"model": "jev-1.13.0", "probabilities": {"supported": true, "contradicted": 0, "unknown": 0}}',
        '{"model": "jev-1.13.0", "probabilities": {"supported": 0.5, "contradicted": 0.2, "unknown": 0.1}}',
        '{"model": "jev-1.13.0", "probabilities": [0.9, 0.05, 0.05]}',
        '{"model": "jev-1.13.0"}',
        '{"model": "jev-1.13.0", "probabilities": {"supported": 0.9, "contradicted": 0.05, "unknown": 0.05}, "extra": 1}',
        '{"refused": ""}',
        '[1, 2, 3]',
        'not json at all',
        '{"model": "jev-1.13.0", "model": "jev-1.13.0", "probabilities": {"supported": 0.9, "contradicted": 0.05, "unknown": 0.05}}',
        '{"model": "unexpected-model", "model": "jev-1.13.0", "probabilities": {"supported": 0.9, "contradicted": 0.05, "unknown": 0.05}}',
        '{"model": "jev-1.13.0", "probabilities": {"supported": 0.05, "supported": 0.9, "contradicted": 0.05, "unknown": 0.05}}',
        '{"refused": "max_tokens_exceeded", "refused": "max_tokens_exceeded"}',
    ],
)
def test_a_corrupt_cached_answer_fails_without_clamping_or_asking_again(tmp_path, body) -> None:
    question = {"unverified": TABLE.questions()["unverified"]}
    cache = sr.AnswerCache(tmp_path)
    key = cache.key(MODEL, {"text": "x"}, question["unverified"])
    (tmp_path / f"{key}.json").write_text(body, encoding="utf-8")

    def never(request):
        raise AssertionError("a corrupt cached answer must not be asked again")

    for jev in (sr.JevClient(cache, MODEL, offline=True), sr.JevClient(cache, MODEL, client_factory=client(never))):
        with pytest.raises(ProtocolError):
            jev.answers({"text": "x"}, question, budget=request_budget())
    assert (tmp_path / f"{key}.json").read_text(encoding="utf-8") == body


# Rounding each probability to its reported precision may leave the sum a little off 1; more is not.
# am[verifies a-jev-client-1016]
def test_the_sum_tolerance_is_the_rounding_the_reported_precision_allows() -> None:
    options = frozenset(TABLE.answers)
    origin = {"source": "test"}
    rounded = sr.checked_answer(MODEL, {"supported": 0.33, "contradicted": 0.33, "unknown": 0.33},
                                expected_model=MODEL, options=options, origin=origin)
    assert rounded.decided() == "contradicted"
    with pytest.raises(ProtocolError, match="sum to 1"):
        sr.checked_answer(MODEL, {"supported": 0.3333, "contradicted": 0.3333, "unknown": 0.3},
                          expected_model=MODEL, options=options, origin=origin)


# Every number outside 0 to 1 is the protocol's error whatever its size: an integer too large for a
# float, which float() overflows on (c-sn-reader-answer-overflow-1018), and one with more digits
# than repr writes (c-integrate-reader-number-refusal-edges-1018) included.
# am[verifies a-integrate-reader-number-refusal-1018@e49eaa] am[verifies a-integrate-reader-numeric-refusal-closure-1018@54efbb]
@settings(deadline=None, database=None)
@given(outside=st.one_of(
    st.integers(max_value=-1),
    st.integers(min_value=2),
    st.integers(min_value=2**1024),
    st.integers(max_value=-(2**1024)),
    st.integers(min_value=10**4300),
    st.integers(max_value=-(10**4300)),
    st.floats().filter(lambda number: not 0.0 <= number <= 1.0),
))
def test_a_probability_outside_0_to_1_is_a_protocol_error_whatever_its_size(outside) -> None:
    with pytest.raises(ProtocolError, match="outside 0 to 1"):
        sr.checked_answer(MODEL, {"supported": outside, "contradicted": 0, "unknown": 0},
                          expected_model=MODEL, options=frozenset(TABLE.answers), origin={"source": "test"})


# Every refusal's details quote what was found, and quoting cannot fail in turn: a value repr cannot
# write, an integer past the digit limit as the model, an option or a probability, or a list holding
# one, is quoted as errors.safe_repr names it, and the refusal stays the protocol's error.
# am[verifies a-integrate-reader-numeric-refusal-closure-1018@54efbb]
@pytest.mark.parametrize(
    ("model", "probabilities", "problem"),
    [
        pytest.param(10**5000, {"supported": 1.0, "contradicted": 0.0, "unknown": 0.0}, "another model", id="model"),
        pytest.param(MODEL, [10**5000], "options are not", id="not-a-mapping"),
        pytest.param(MODEL, {10**5000: 1.0, "contradicted": 0.0, "unknown": 0.0}, "options are not", id="option"),
        pytest.param(MODEL, {"supported": [10**5000], "contradicted": 0.0, "unknown": 0.0}, "not a number", id="nested"),
        pytest.param(MODEL, {"supported": 10**5000, "contradicted": 0.0, "unknown": 0.0}, "outside 0 to 1", id="positive"),
        pytest.param(MODEL, {"supported": -(10**5000), "contradicted": 0.0, "unknown": 0.0}, "outside 0 to 1", id="negative"),
    ],
)
def test_a_refusal_quotes_a_value_repr_cannot_write(model, probabilities, problem) -> None:
    with pytest.raises(ProtocolError, match=problem) as refused:
        sr.checked_answer(model, probabilities, expected_model=MODEL, options=frozenset(TABLE.answers),
                          origin={"source": "test"})
    found = refused.value.details["found"]
    assert all(isinstance(text, str) and len(text) <= 200 for text in (found if isinstance(found, list) else [found]))


# The integers 0 and 1 are probabilities like any other and are kept as floats.
# am[verifies a-integrate-reader-number-refusal-1018@e49eaa]
def test_the_integers_0_and_1_are_admitted_as_probabilities() -> None:
    answer = sr.checked_answer(MODEL, {"supported": 1, "contradicted": 0, "unknown": 0},
                               expected_model=MODEL, options=frozenset(TABLE.answers), origin={"source": "test"})
    assert answer.probabilities == {"supported": 1.0, "contradicted": 0.0, "unknown": 0.0}
    assert all(type(value) is float for value in answer.probabilities.values())
    assert answer.decided() == "supported"


# am[verifies a-jev-cross-encoder-1016]
def test_passages_are_sentences() -> None:
    assert sr.passages("Checkout is down. Raw logs include customer emails. Engineering needs the incident room.", TABLE.language) == (
        "Checkout is down.", "Raw logs include customer emails.", "Engineering needs the incident room.")
    assert sr.passages("no punctuation at all", TABLE.language) == ("no punctuation at all",)


# am[verifies a-jev-adapter-1016@05c430]
# am[verifies a-jev-cross-encoder-1016@14cba6] am[verifies a-sib-home-snars-ingestion-1018@5727d2]
def test_a_reading_grounds_each_decided_proposition_with_the_real_cross_encoder(tmp_path) -> None:
    text = "Checkout is down. Raw logs include customer emails. Engineering needs the incident room."

    def answer_for(q, state):
        decided = {"sensitive-data": "supported", "customer-emails": "supported", "public-data": "contradicted"}
        if q == "mood":
            return sure(q, state)
        top = decided.get(q, "unknown")
        return {option: (0.9 if option == top else 0.05) for option in TABLE.answers}

    jev = sr.JevClient(sr.AnswerCache(tmp_path), MODEL, client_factory=client(answering(answer_for)))
    reading = sr.SemanticReader(declaration=TABLE, jev=jev).read(text, budget=request_budget())

    sensitive = reading.proposition("sensitive-data")
    assert (sensitive.answer, sensitive.direction, sensitive.probability) == ("supported", "for", pytest.approx(0.9))
    assert sensitive.grounding.passage == "Raw logs include customer emails."
    assert reading.proposition("customer-emails").grounding.passage == "Raw logs include customer emails."
    assert reading.proposition("unverified").answer == "unknown"
    assert reading.proposition("unverified").direction == "none"
    assert reading.proposition("unverified").grounding is None
    assert reading.choice("mood").answer == "declarative"
    assert reading.model == MODEL and len(reading.revision) == 64
    assert reading.declaration is TABLE
    assert reading.to_dict()["domain"] == "incident" and reading.to_dict()["declaration"] == TABLE.digest

    codec = SexprCodec()
    facts = reading_facts(reading, source="goalchainer:request", trust=1.0, codec=codec)
    assert len(facts) == len(TABLE.propositions)
    assert [ReadingFact.parse(fact, codec).emit(codec) for fact in facts] == list(facts)
    assert any(
        fact.startswith('(gc-reading "goalchainer:request" 1.0 sensitive-data supported 0.9')
        and '"Raw logs include customer emails."' in fact
        for fact in facts
    )


# am[verifies a-jev-client-1016]
def test_the_reader_reads_its_cache_and_offline_switch_from_the_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(sr.JEV_CACHE_ENV, str(tmp_path / "answers"))
    assert sr.default_answer_cache().directory == (tmp_path / "answers").absolute()
    monkeypatch.delenv(sr.JEV_CACHE_ENV)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert sr.default_answer_cache().directory == tmp_path / "xdg" / "goalchainer" / "jev"
    monkeypatch.setenv(sr.JEV_OFFLINE_ENV, "1")
    assert sr.SemanticReader(declaration=TABLE).jev.offline is True
    monkeypatch.setenv(sr.JEV_OFFLINE_ENV, "0")
    assert sr.SemanticReader(declaration=TABLE).jev.offline is False


# A process with no cache setting and no home directory, as a uid with no passwd entry, builds a
# reader, which a SNARS session that never reads text needs; only asking for its Jev client, which
# a read does first thing after resolving the served model, looks for the answer cache's place, and
# finding none is the dependency error naming XDG_CACHE_HOME. A client the caller gives is still
# checked against the declaration's model when the reader is built.
# am[verifies a-dr-reader-home-at-read-1018@3ddda8] am[verifies a-dr-cache-home-typed-1018@63015f]
def test_a_reader_builds_without_a_home_and_looks_for_the_answer_cache_on_first_use(monkeypatch) -> None:
    def no_home(cls):
        raise RuntimeError("Could not determine home directory.")

    for name in (sr.JEV_CACHE_ENV, "XDG_CACHE_HOME", "HOME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(no_home))
    reader = sr.SemanticReader(declaration=TABLE)

    with pytest.raises(DependencyUnavailableError, match="set XDG_CACHE_HOME"):
        reader.jev  # noqa: B018 (the property builds the client)
    monkeypatch.setenv(sr.JEV_CACHE_ENV, "answers")
    assert reader.jev.cache.directory == Path("answers").absolute() and reader.jev is reader.jev
    with pytest.raises(InvalidInputError, match="different model"):
        sr.SemanticReader(declaration=TABLE, jev=sr.JevClient(sr.AnswerCache(Path("unused")), "jev-1.14.0"))


# A reviewed artifact as semantic_sleep publishes one, with stand-in model files: serving checks
# the manifest and file sizes, so the files need not be a real model.
# am[verifies a-jev-serve-active-1016]
def _artifact(root: Path, tmp_path: Path, *, instruction: str, base: str = RERANKER.identity) -> ss.Artifact:
    model = tmp_path / f"model-{uuid.uuid4().hex}"
    model.mkdir()
    for name in ("config.json", "tokenizer_config.json", "model.safetensors"):
        (model / name).write_text(f"stand-in {name}", encoding="utf-8")
    return ss.publish_artifact(root, model, {"base": {"identity": base}, "instruction": instruction}, {})


# am[verifies a-jev-serve-active-1016]
def _activate(root: Path, artifact: ss.Artifact | None) -> None:
    (root / "ACTIVE").write_bytes(ss.canonical(
        {"artifact": None if artifact is None else artifact.identity, "generation": str(uuid.uuid4())}))


# am[verifies a-jev-serve-active-1016]
def test_the_pinned_base_serves_until_an_artifact_is_active(tmp_path) -> None:
    root = tmp_path / "reranker"
    assert sr.served_ranker(TABLE, root) == sr.ServedRanker(RERANKER.identity, ready_model_dir())

    artifact = _artifact(root, tmp_path, instruction=TABLE.ranking_instruction)
    assert sr.served_ranker(TABLE, root).identity == RERANKER.identity
    _activate(root, artifact)
    assert sr.served_ranker(TABLE, root) == sr.ServedRanker(artifact.identity, artifact.model_dir)
    _activate(root, None)
    assert sr.served_ranker(TABLE, root).identity == RERANKER.identity


# An artifact evaluated under another instruction, built on another base, or changed on disk after
# publication is refused, never replaced by the base.
@pytest.mark.parametrize("fault", ["instruction", "base", "resized"])
# am[verifies a-jev-serve-active-1016]
def test_an_artifact_that_was_not_evaluated_as_served_is_refused(tmp_path, fault) -> None:
    root = tmp_path / "reranker"
    artifact = _artifact(
        root, tmp_path,
        instruction="Another instruction" if fault == "instruction" else TABLE.ranking_instruction,
        base="another/base@0" if fault == "base" else RERANKER.identity,
    )
    if fault == "resized":
        with (artifact.model_dir / "config.json").open("a", encoding="utf-8") as stream:
            stream.write(" changed")
    _activate(root, artifact)

    with pytest.raises(ProtocolError):
        sr.served_ranker(TABLE, root)


# Each read resolves what to serve: its revision names the served model, and the loaded model
# changes only when the served identity does.
# am[verifies a-jev-serve-active-1016]
def test_a_reading_names_the_model_that_grounded_it(tmp_path) -> None:
    def answer_for(q, state):
        if q == "mood":
            return sure(q, state)
        top = "supported" if q == "sensitive-data" else "unknown"
        return {option: (0.9 if option == top else 0.05) for option in TABLE.answers}

    served = iter([sr.ServedRanker("base", tmp_path), sr.ServedRanker("base", tmp_path),
                   sr.ServedRanker("promoted", tmp_path)])
    loads = []

    def load(ranker):
        loads.append(ranker.identity)
        return SimpleNamespace(scores=lambda pairs: tuple(0.5 for _ in pairs))

    jev = sr.JevClient(sr.AnswerCache(tmp_path / "answers"), MODEL, client_factory=client(answering(answer_for)))
    reader = sr.SemanticReader(declaration=TABLE, jev=jev, serve=lambda: next(served), load=load)
    revisions = [reader.read("Raw logs include customer emails.", budget=request_budget()).revision for _ in range(3)]

    assert revisions[0] == revisions[1] != revisions[2]
    assert loads == ["base", "promoted"]


# A promotion lands while one read is waiting on Jev: the read that captured the old identity
# keeps it for its revision and its scores, and the read that starts after the promotion uses the
# promoted model. Events order the two reads, so the interleaving is the same on every run.
# am[verifies a-jev-serve-active-1016]
def test_a_read_keeps_the_model_it_captured_across_a_promotion(tmp_path) -> None:
    old, new = sr.ServedRanker("old", tmp_path), sr.ServedRanker("promoted", tmp_path)
    active = {"served": old}
    first_in_jev, release = threading.Event(), threading.Event()
    respond = answering(lambda q, s: sure(q, s) if q == "mood" else {
        option: (0.9 if option == ("supported" if q == "sensitive-data" else "unknown") else 0.05)
        for option in TABLE.answers})

    def handler(request):
        if json.loads(request.content)["state"]["text"] == "First text.":
            first_in_jev.set()
            release.wait()
        return respond(request)

    loads = []

    def load(served):
        loads.append(served.identity)
        score = {"old": 0.1, "promoted": 0.9}[served.identity]
        return SimpleNamespace(scores=lambda pairs: tuple(score for _ in pairs))

    jev = sr.JevClient(sr.AnswerCache(tmp_path / "answers"), MODEL, client_factory=client(handler))
    reader = sr.SemanticReader(declaration=TABLE, jev=jev, serve=lambda: active["served"], load=load)
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(reader.read, "First text.", budget=request_budget())
        # A first read that fails before reaching Jev wakes the observer too; result() raises it.
        first.add_done_callback(lambda _done: first_in_jev.set())
        try:
            first_in_jev.wait()
            active["served"] = new
            second = reader.read("Second text.", budget=request_budget())
        finally:
            release.set()
        first = first.result()

    assert (first.revision, second.revision) == (reader.revision(old), reader.revision(new))
    assert first.proposition("sensitive-data").grounding.score == 0.1
    assert second.proposition("sensitive-data").grounding.score == 0.9
    assert loads == ["promoted", "old"]


# am[verifies a-jev-capture-1016]
def test_replay_fixture_directory_documents_its_provenance() -> None:
    readme = Path(__file__).parent / "data" / "jev" / "README.md"
    assert "captured from the live service" in readme.read_text(encoding="utf-8")


# A caller waiting for the default reader's first read waits only until its own deadline. With the
# engine held and a long-budget first caller waiting behind it, a 0.3 s caller raises its
# ReviewTimeout well before the engine is free; once it is, a retry returns the one reader the first
# caller read. The hold is an offline one outside any request, so it names no budget; it ends by
# itself after 5 s, a holder that fails to start raises its error here, and every wait is bounded,
# so a reader that waits past its deadline fails the test instead of hanging it.
# am[verifies a-integrate-default-reader-deadline-audit-1018@b7a2d5] am[verifies a-dr-sr-default-reader-1018@dce66c]
def test_a_short_caller_waiting_for_the_default_reader_stops_at_its_deadline_and_retries(monkeypatch) -> None:
    monkeypatch.setattr(sr, "_INCIDENT", None)
    monkeypatch.setattr(runtime_modules, "_SETUPS", set(runtime_modules._SETUPS) - {sr._INCIDENT_SETUP})
    held, release = threading.Event(), threading.Event()
    failed: list[BaseException] = []

    def hold_engine() -> None:
        try:
            with metta_engine(None):
                held.set()
                release.wait(5)
        except BaseException as error:  # noqa: BLE001 (the holder's failure is raised in the test)
            failed.append(error)
            held.set()

    first: dict[str, sr.SemanticReader] = {}
    holder = threading.Thread(target=hold_engine)
    holder.start()
    assert held.wait(60), "the engine holder never started"
    if failed:
        raise failed[0]
    loader = threading.Thread(target=lambda: first.setdefault(
        "reader", sr.default_reader(budget=RunBudget(inference_budget=None, timeout_seconds=600))))
    loader.start()
    started = time.monotonic()
    try:
        with pytest.raises(ReviewTimeout):
            sr.default_reader(budget=RunBudget(inference_budget=None, timeout_seconds=0.3))
        waited = time.monotonic() - started
    finally:
        release.set()
        holder.join(60)
        loader.join(300)

    assert not holder.is_alive() and not loader.is_alive()
    assert waited < 3
    assert sr.default_reader(budget=RunBudget(inference_budget=None, timeout_seconds=600)) is first["reader"]

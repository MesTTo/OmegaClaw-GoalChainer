"""Purpose: test the reading contract end to end. Negation, paraphrase and stated removal are read
from the frozen corpus's recorded Jev answers. A quoted mention and an instruction to remove are
carried through to the incident domain's review on synthetic answers, so no keyword path can stand
in for what Jev says, and captured requests reach that review as read. A renamed domain replays the
same recorded answers under its own identity, renamed answers keep their declared meaning, a miss
is a typed error, and the core reading modules name no domain's vocabulary.

Recorded answers are jev-1.13.0's, committed in tests/data/jev; synthetic ones come from
jev_support's mock transport and claim nothing about what Jev answers."""

from __future__ import annotations

import ast
import functools
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from jev_support import answering, client

from goal_chainer import reading_projection, semantic_reader
from goal_chainer.domains import readings
from goal_chainer.domains.loader import packaged_domain
from goal_chainer.domains.readings import JUDGEMENTS, ReadingDeclaration
from goal_chainer.reading_projection import signal_readings
from goal_chainer.semantic_evaluation import CORPUS_PATH
from goal_chainer.semantic_reader import JevClient, SemanticReader, default_answer_cache
from goal_chainer.snars_ingestion import ReadingFact, reading_facts
from goal_chainer.errors import InvalidInputError, MissingAnswerError
from goal_chainer.sexpr.codec import SexprCodec
from request_support import budget as request_budget
from reading_support import INCIDENT, section, section_text
from relevance_support import AS_OF, packet, reviewed

_TEXTS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))["texts"]
CORPUS = {text["id"]: text["text"] for text in _TEXTS}
LABELS = {text["id"]: text["labels"] for text in _TEXTS}


# A reader of a declaration that replays the committed answers offline and grounds with the
# provisioned cross-encoder, as the gate runs it; one per declaration, so the model loads once.
# am[verifies a-dr-contract-tests-1018@48c516]
@functools.cache
def _reader(declaration):
    return SemanticReader(declaration=declaration, jev=JevClient(default_answer_cache(), declaration.model, offline=True))


# The packaged incident domain, whose reading section INCIDENT is, read once.
# am[verifies a-dr-contract-tests-1018@48c516] am[verifies a-ie-c5b-regressions-1018]
@functools.cache
def _domain():
    return packaged_domain("incident", budget=request_budget())


# A reading's answers by proposition, as the reader decided them.
# am[verifies a-dr-contract-tests-1018@48c516] am[verifies a-ie-c5b-regressions-1018]
def _answers(reading) -> dict[str, str]:
    return {read.proposition.id: read.answer for read in reading.propositions}


# The domain's sensitive categories, its (sensitive-category ID LABEL) facts, and those a reading
# supports.
# am[verifies a-dr-contract-tests-1018@48c516] am[verifies a-ie-c5b-regressions-1018]
def _categories() -> list[str]:
    return [fact.args[0] for fact in _domain().facts if fact.functor == "sensitive-category"]


# am[verifies a-dr-contract-tests-1018@48c516] am[verifies a-ie-c5b-regressions-1018]
def _supported_categories(reading) -> set[str]:
    answers = _answers(reading)
    return {category for category in _categories() if answers[category] == "supported"}


# The packet a domain request builds from a reading, observed when the packet is, and the deontic
# standing the packaged incident domain's review of it gives each action.
# am[verifies a-dr-contract-tests-1018@48c516] am[verifies a-ie-c5b-regressions-1018]
def _packet(reading):
    return packet(*signal_readings(reading, INCIDENT, observed_at=AS_OF, valid_until=None))


# am[verifies a-dr-contract-tests-1018@48c516] am[verifies a-ie-c5b-regressions-1018]
def _standings(reading) -> dict[str, str]:
    review = reviewed(_domain(), _packet(reading)).to_dict()
    return {candidate["action"]: candidate["deontic"] for candidate in review["candidates"]}


# am[verifies a-dr-contract-tests-1018@48c516] am[verifies a-ie-c5b-regressions-1018]
def _raw_log(reading) -> str:
    return _standings(reading)["publish_raw_log"]


# Negation: "not a single email address" names email addresses only to deny them, and the recorded
# reading contradicts customer-emails, so no category is supported and the review's packet carries
# the denial. A text denying every kind of sensitive data reads that way for each, and the review
# permits the raw log.
# am[verifies a-dr-contract-tests-1018@48c516] am[rests-on c-user-jev-not-keyword-semantics-1018@d70449]
def test_a_negated_mention_reads_as_a_contradiction():
    text = CORPUS["t25"]
    assert "email address" in text
    reading = _reader(INCIDENT).read(text, budget=request_budget())

    assert _answers(reading)["customer-emails"] == "contradicted"
    assert "customer-emails" not in _supported_categories(reading)
    assert ("customer-emails", "refuted") in {(read.signal, read.state) for read in _packet(reading).readings}

    denied = _reader(INCIDENT).read(CORPUS["t02"], budget=request_budget())
    answers = _answers(denied)
    assert answers["sensitive-data"] == "contradicted" and answers["public-data"] == "supported"
    assert all(answers[category] == "contradicted" for category in _categories())
    assert _raw_log(denied) == "permitted"


# Paraphrase: a phone number and a home address are personal data though the text names neither
# "personal" nor "email", and an error output that carries order numbers holds order identifiers and
# raw log lines though it says neither. The recorded readings support each.
# am[verifies a-dr-contract-tests-1018@48c516] am[rests-on c-user-jev-not-keyword-semantics-1018@d70449]
def test_a_paraphrase_reads_without_the_declared_words():
    quoted = CORPUS["t12"]
    assert not re.search(r"personal|confidential|e-?mail", quoted, re.IGNORECASE)
    assert _answers(_reader(INCIDENT).read(quoted, budget=request_budget()))["sensitive-data"] == "supported"

    output = CORPUS["t26"]
    assert not re.search(r"identifier|raw log|log line", output, re.IGNORECASE)
    reading = _reader(INCIDENT).read(output, budget=request_budget())
    assert _supported_categories(reading) == {"order-ids", "raw-logs"}
    assert _raw_log(reading) == "forbidden"


# Stated removal: the corpus labels "We stripped the order identifiers" and "Credentials are masked
# ... holds no keys or passwords" as contradicting order-ids and tokens-or-secrets, and jev-1.13.0's
# recorded readings support both instead (0.86 and 0.93). The guard errs toward protecting the data,
# but it is a misreading (i-dr-removal-misread-1018). The test pins the recorded misreading against
# the corpus label, so a re-captured answer that reads the removal fails it, and the test then flips
# to assert the label. An expected failure would not do: the gate counts it, as it counts a skip, as
# a test that did not run.
# am[verifies a-dr-contract-tests-1018@48c516] am[related i-dr-removal-misread-1018@5d43c3]
@pytest.mark.parametrize(("text_id", "proposition"), [("t28", "order-ids"), ("t34", "tokens-or-secrets")])
def test_jev_still_reads_a_stated_removal_as_presence(text_id, proposition):
    label, _rationale = LABELS[text_id][proposition]
    reading = _reader(INCIDENT).read(CORPUS[text_id], budget=request_budget())

    assert (label, _answers(reading)[proposition]) == ("contradicted", "supported")


# A quoted mention names customer emails without the text being about any, and an instruction to
# remove them says the content holds them. Whatever Jev answers is what the packet and the incident
# domain's review carry: here a synthetic unknown for the quotation and a synthetic support for the
# instruction, against what the words alone would suggest in the first case.
# am[verifies a-dr-contract-tests-1018@48c516] am[rests-on c-user-jev-not-keyword-semantics-1018@d70449]
@pytest.mark.parametrize(
    ("text", "answer", "categories", "raw_log"),
    [
        ('The style guide defines the phrase "customer emails" for the glossary.', "unknown", set(), "permitted"),
        ("Remove every customer email address from the log before you post it.", "supported",
         {"customer-emails"}, "forbidden"),
    ],
    ids=["quoted-mention", "instruction-to-remove"],
)
def test_a_quoted_mention_and_an_instruction_to_remove_follow_jev(tmp_path, text, answer, categories, raw_log):
    def answer_for(question, state):
        del state
        if question == "mood":
            return {"query": 0.05, "directive": 0.9, "declarative": 0.05}
        decided = answer if question == "customer-emails" else "unknown"
        return {option: (0.9 if option == decided else 0.05) for option in INCIDENT.answers}

    jev = JevClient(semantic_reader.AnswerCache(tmp_path), INCIDENT.model, client_factory=client(answering(answer_for)))
    reading = SemanticReader(declaration=INCIDENT, jev=jev).read(text, budget=request_budget())

    assert _answers(reading)["customer-emails"] == answer
    assert _supported_categories(reading) == categories
    assert _raw_log(reading) == raw_log


# Requests read from their captured answers and carried to the incident domain's review: a
# paraphrase naming none of the declared words, and a refusal to publish that names the data, both
# put privacy at stake, so the raw log is forbidden; facts stated as not ready oblige holding the
# external update.
# am[verifies a-ie-c5b-regressions-1018] am[rests-on c-user-jev-not-keyword-semantics-1018@d70449]
@pytest.mark.parametrize(
    ("text", "action", "standing"),
    [
        ("The dump we want to share reveals who our shoppers are and their home addresses.",
         "publish_raw_log", "forbidden"),
        ("Do not publish the raw logs that expose customer emails.", "publish_raw_log", "forbidden"),
        ("Checkout is down but the root cause is unknown and the facts are not ready.",
         "hold_external_update", "obligated"),
    ],
    ids=["paraphrase", "refusal-to-publish", "facts-not-ready"],
)
def test_a_captured_request_reaches_the_incident_review_as_read(text, action, standing):
    assert _standings(_reader(INCIDENT).read(text, budget=request_budget()))[action] == standing


# The incident declaration with every name changed and every statement kept: the same questions, so
# the same recorded answers replay, read under another domain's identity.
# am[verifies a-dr-contract-tests-1018@48c516] am[verifies a-dr-sr-tests-1018@ae8cd4]
def _renamed_declaration(directory: Path) -> ReadingDeclaration:
    text = section_text(INCIDENT).replace("(gc-reading-domain incident)", "(gc-reading-domain privacy-review)")
    for proposition in INCIDENT.propositions:
        text = text.replace(f"(gc-reading-proposition {proposition.id} ",
                            f"(gc-reading-proposition pr-{proposition.id} ")
    text = text.replace("(gc-reading-choice mood ", "(gc-reading-choice speech-act ")
    return section(text, directory / "privacy_review.metta")


# A renamed domain asks the same questions, so the recorded answers replay under it with no hosted
# request. Its readings carry its own name, digest and revision, its facts are admitted by it alone,
# and each answer equals the incident reading's for the proposition with the same statement.
# am[verifies a-dr-contract-tests-1018@48c516] am[verifies a-dr-identity-1018@df82ab]
# am[verifies a-dr-incident-declaration-1018@455a2f]
def test_a_renamed_domain_replays_the_recorded_answers_under_its_own_identity(tmp_path):
    renamed = _renamed_declaration(tmp_path)
    assert renamed.name == "privacy-review" and renamed.digest != INCIDENT.digest
    assert list(renamed.questions().values()) == list(INCIDENT.questions().values())

    text = CORPUS["t25"]
    incident = _reader(INCIDENT).read(text, budget=request_budget())
    other = _reader(renamed).read(text, budget=request_budget())

    assert other.declaration is renamed and other.revision != incident.revision
    assert [(r.answer, r.direction) for r in other.propositions] == [(r.answer, r.direction) for r in incident.propositions]
    assert [r.proposition.id for r in other.propositions] == [f"pr-{p.id}" for p in INCIDENT.propositions]
    assert other.choice("speech-act").answer == incident.choice("mood").answer

    codec = SexprCodec()
    facts = [ReadingFact.parse(fact, codec) for fact in reading_facts(other, source="s", trust=1.0, codec=codec)]
    assert [renamed.admit(fact) for fact in facts] == facts
    with pytest.raises(InvalidInputError, match="not one the incident reading declaration asks"):
        INCIDENT.admit(facts[0])


# One reader serves every request reading one declaration. reader_for answers the same reader for
# any declaration of the same digest, wherever it was written, and another for another digest, and
# the default reader is its packaged incident case; readers of the two domains share one loaded
# cross-encoder. Four texts read on four threads through the shared reader give exactly what reading
# them one after another gives, groundings and their scores included, with no model loaded again,
# since a read keeps nothing in the reader and the model's passes take its one lock.
# am[verifies a-integrate-domain-reader-reuse-1018@bffd2b] am[verifies a-dr-shared-encoder-1018@ef35c7]
def test_one_reader_per_declaration_serves_concurrent_reads_as_sequential_ones(tmp_path):
    shared = semantic_reader.reader_for(INCIDENT)
    copy = section(section_text(INCIDENT), tmp_path / "copy.metta")
    renamed = semantic_reader.reader_for(_renamed_declaration(tmp_path))
    assert copy is not INCIDENT and semantic_reader.reader_for(copy) is shared
    assert semantic_reader.default_reader(budget=request_budget()) is shared
    assert renamed is not shared
    with pytest.raises(InvalidInputError, match="ReadingDeclaration"):
        semantic_reader.reader_for("incident")

    def summary(text):
        reading = shared.read(text, budget=request_budget())
        return (reading.text, reading.revision,
                [(r.proposition.id, r.answer, r.grounding) for r in reading.propositions],
                [(c.choice.id, c.answer) for c in reading.choices])

    texts = [CORPUS[key] for key in ("t01", "t02", "t25", "t30")]
    one_by_one = [summary(text) for text in texts]
    (served, model) = shared._loaded
    with ThreadPoolExecutor(len(texts)) as pool:
        together = list(pool.map(summary, texts))

    assert together == one_by_one
    assert shared._loaded == (served, model)
    assert renamed._ranked(served)._encoder is model._encoder


# A domain with its own propositions and answers named its own way. The answers mean what their
# declared directions say, Jev is asked with the declared option names, the theory reads a decided
# answer by its direction, and the stored answers replay offline under the domain's identity.
# am[verifies a-dr-contract-tests-1018@48c516] am[verifies a-dr-direction-words-1018@1b6ec6]
# am[verifies a-dr-explicit-table-1018@bba9ce]
def test_renamed_answers_keep_their_declared_meaning(tmp_path):
    weather = section(
        "(gc-reading-domain weather)\n"
        '(gc-reading-model "jev-1.13.0")\n'
        '(gc-reading-language "en")\n'
        '(gc-reading-instructions "Does `text` bear out this claim? Claim: ")\n'
        '(gc-reading-option holds for "The text says the claim is true.")\n'
        '(gc-reading-option fails against "The text says the claim is false.")\n'
        '(gc-reading-option open none "The text does not settle the claim.")\n'
        '(gc-reading-proposition rain-expected "Rain is expected today." "Is rain expected?")\n'
        '(gc-reading-proposition roads-closed "The roads are closed." "Are the roads closed?")\n'
        '(gc-reading-proposition flood-warning "A flood warning is in force." "Is there a flood warning?")\n'
        '(gc-ranking-instruction "Given a question about the weather, retrieve the passage that answers it")\n',
        tmp_path / "weather.metta",
    )
    decided = {"rain-expected": "holds", "roads-closed": "fails", "flood-warning": "open"}
    calls: list = []

    def answer_for(question, state):
        del state
        return {option: (0.9 if option == decided[question] else 0.05) for option in weather.answers}

    cache = semantic_reader.AnswerCache(tmp_path / "answers")
    live = JevClient(cache, weather.model, client_factory=client(answering(answer_for, calls=calls)))
    text = "Heavy rain is forecast this afternoon, and every road into town stays open."
    reading = SemanticReader(declaration=weather, jev=live).read(text, budget=request_budget())

    assert {name for body in calls for spec in body["questions"].values() for name in spec["criteria"]} == {"holds", "fails", "open"}
    assert [(r.proposition.id, r.answer, r.direction) for r in reading.propositions] == [
        ("rain-expected", "holds", "for"), ("roads-closed", "fails", "against"), ("flood-warning", "open", "none")]
    assert [JUDGEMENTS[r.direction] for r in reading.propositions if r.direction in JUDGEMENTS] == ["supported", "contradicted"]

    replayed = SemanticReader(declaration=weather, jev=JevClient(cache, weather.model, offline=True)).read(
        text, budget=request_budget())
    assert [(r.answer, r.key) for r in replayed.propositions] == [(r.answer, r.key) for r in reading.propositions]
    assert replayed.revision == reading.revision and replayed.declaration.digest == weather.digest


# Nothing falls back to keywords: a question the cache lacks, read offline, is a typed miss naming it,
# and a refusal stored for a text fails the reading the same way.
# am[verifies a-dr-contract-tests-1018@48c516] am[rests-on c-user-jev-not-keyword-semantics-1018@d70449]
def test_a_miss_or_a_refusal_is_a_typed_error_not_a_keyword_guess(tmp_path):
    empty = JevClient(semantic_reader.AnswerCache(tmp_path / "empty"), INCIDENT.model, offline=True)
    with pytest.raises(MissingAnswerError) as missed:
        SemanticReader(declaration=INCIDENT, jev=empty).read(
            "Raw logs include customer emails.", budget=request_budget())
    assert missed.value.details["reason"] == "not_cached"
    assert sorted(missed.value.details["questions"]) == sorted(INCIDENT.questions())

    refusing = semantic_reader.AnswerCache(tmp_path / "refused")
    state = {"text": "Raw logs include customer emails."}
    for question, spec in INCIDENT.questions().items():
        refusing.admit(refusing.key(INCIDENT.model, state, spec), {"refused": "max_tokens_exceeded"})
    with pytest.raises(MissingAnswerError) as refused:
        SemanticReader(declaration=INCIDENT, jev=JevClient(refusing, INCIDENT.model, offline=True)).read(
            state["text"], budget=request_budget())
    assert refused.value.details["reason"] == "refused"


# The core reading modules decide nothing by any domain's names: no string they hold is a proposition
# id, an answer, a choice or option name, or a kind the incident declaration once carried. The
# judgement words are the core's own, which the incident domain's answers happen to share. The
# reader, its declarations and the projection of a reading into a review packet are those modules.
# am[verifies a-dr-contract-tests-1018@48c516] am[verifies a-dr-one-name-1018@beba5e]
# am[verifies a-ie-c5b-regressions-1018]
def test_the_core_reading_modules_name_no_domain_vocabulary():
    names = {p.id for p in INCIDENT.propositions} | set(INCIDENT.answers) | {c.id for c in INCIDENT.choices}
    names |= {option for c in INCIDENT.choices for option, _ in c.options}
    names |= {"request-property", "sensitive-category", "request-mood"}
    names -= set(JUDGEMENTS.values())
    for module in (readings, semantic_reader, reading_projection):
        held = {
            node.value for node in ast.walk(ast.parse(Path(module.__file__).read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert held.isdisjoint(names), (module.__name__, sorted(held & names))

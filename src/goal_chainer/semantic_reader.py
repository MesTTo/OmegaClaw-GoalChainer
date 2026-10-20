"""Purpose: read a text semantically for GoalChainer against one domain's reading declaration
(goal_chainer.domains.readings). Jev judges every declared proposition as one of the declared
answers, whose declared direction says what it means, answers every declared choice, and chooses
for every binding the declared entity its proposition is about or no match; and a local
cross-encoder, the pinned base or the reviewed artifact semantic_sleep promoted, names the passage
that answers each decided proposition, scored by goal_chainer.semantic_ranker. Every Jev answer is
stored once under the SHA-256 of its model, state and question and never replaced, so a reading's
Jev answers replay offline exactly and its provenance names exactly the answers it used. Its
grounding scores are floats the scoring computes afresh: they can differ in their last digits
between scoring implementations, library versions and batch compositions, and where a question's
best passages nearly tie, so can the passage it is grounded in. A reading's revision names the
scoring code with the declaration, the served model and the segmenter. A read spends only what its
caller's RunBudget has left: no hosted request after the deadline, and each one bounded by the
seconds remaining. Every Jev request runs under a RunBudget: a decision's, or the one a tool's
command line gives capture and evaluation, which run outside any request.

Configuration comes from the environment: GOALCHAINER_JEV_CACHE names the answer cache directory
(default $XDG_CACHE_HOME/goalchainer/jev), GOALCHAINER_JEV_OFFLINE=1 answers from that cache alone,
TYPESAFE_API_KEY authorises any question the cache lacks, and GOALCHAINER_MODEL_CACHE locates the
provisioned cross-encoder (goal_chainer.semantic_models).
"""

# am[implements a-rpc-reading-scoring-identity-1019@452cee]
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sys
import tempfile
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from functools import partial
from importlib import metadata
from pathlib import Path
from typing import Any

from .semantic_models import RERANKER, cache_home, ready_model_dir
from .semantic_ranker import PassageRanker, scoring_identity
from .domains.loader import packaged_domain
from .domains.model import Domain
from .domains.readings import (
    NO_MATCH,
    Binding,
    Choice,
    Proposition,
    ReadingDeclaration,
)
from .errors import DependencyUnavailableError, InvalidInputError, MissingAnswerError, ProtocolError, safe_repr
from .runtime.budget import ReviewTimeout, RunBudget, caller_budget
from .runtime.modules import initialize_once

logger = logging.getLogger(__name__)

JEV_CACHE_ENV = "GOALCHAINER_JEV_CACHE"
JEV_OFFLINE_ENV = "GOALCHAINER_JEV_OFFLINE"

# Sampling policy, not a protocol limit: a choice whose top probability is below SURE is decided on
# the mean of DRAWS draws. TypeSafe measured Jev's probabilities moving between draws of one
# request by a standard deviation of up to 0.05 and treats a top probability under 0.60 as
# uncertain; multinetmetta's mind.jev settles its choices the same way (Adaptive-Consistency,
# Aggarwal et al., EMNLP 2023).
# am[rests-on c-mind-answer-cache-1016]
SURE = 0.60
DRAWS = 3

# Packing, never correctness: questions about one text are packed into requests whose estimated
# size stays under Jev's documented 64k tokens a request (docs.typesafe.ai models.md) less
# mind.jev's margin. The estimate is mind.jev's heuristic of 1.8 characters a token, calibrated
# against Jev's reported usage, not a bound: Jev's tokenizer is not public, so only Jev's own
# max_tokens_exceeded refusal decides that a text or a request is too long.
# am[rests-on c-jev-api-shape-1016]
# am[implements a-jev-estimate-packs-only-1016]
REQUEST_BUDGET = 48_000
CHARS_PER_TOKEN = 1.8


# am[implements a-jev-client-1016]
def canonical(value: Any) -> str:
    """One text for one JSON value: keys sorted, no spaces, Unicode kept (mind.cache.canonical)."""

    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# am[implements a-jev-client-1016]
def _digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


# am[implements a-jev-client-1016]
def _tokens(value: Any) -> int:
    return math.ceil(len(canonical(value)) / CHARS_PER_TOKEN)


# A replayed entry is decoded as strict JSON, as I-JSON (RFC 7493) requires of interchange:
# json.loads keeps the last of repeated keys and reads NaN and Infinity, so an entry such as
# {"model": "other", "model": "jev-1.13.0", ...} would otherwise pass as something it never said.
# Time: one pass over each object's keys.
# am[implements a-jev-strict-replay-json-1016]
def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for name, _value in pairs:
        if name in seen:
            raise ValueError(f"the key {name!r} appears more than once")
        seen.add(name)
    return dict(pairs)


# am[implements a-jev-strict-replay-json-1016]
def _no_constant(name: str) -> Any:
    raise ValueError(f"{name} is not a JSON number")


# ---------------------------------------------------------------------------
# Jev answers and their cache
# ---------------------------------------------------------------------------


# am[implements a-jev-client-1016]
@dataclass(frozen=True, slots=True)
class Answer:
    """Jev's answer to one Choice: the model that gave it and every option's probability, as
    checked_answer admitted them."""

    model: str
    probabilities: Mapping[str, float]

    def decided(self) -> str:
        """The most probable option, the first in sorted order on a tie."""

        return max(sorted(self.probabilities), key=lambda option: self.probabilities[option])

    @property
    def top(self) -> float:
        return max(self.probabilities.values())


# am[implements a-jev-client-1016]
def _decimals(value: float) -> int:
    """Digits after the point in the shortest text of value: 0.05 has 2, 0.6333333333333333 16."""

    exponent = Decimal(repr(value)).as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


# The one gate every answer passes, from the cache or from Jev: the model the table pins, exactly the
# question's options, each a finite probability from 0 to 1, summing to 1 within what rounding to
# the reported precision allows: half a unit in the last digit for each value, plus float addition's
# error. The precision is the finest any value shows, because one response rounds all its values
# alike and JSON drops trailing zeros (0.90 arrives as 0.9). Nothing is clamped or repaired, and an
# invalid cached answer is never re-asked: it fails the reading, because provenance cannot make an
# impossible distribution possible. Each probability is compared with 0 and 1 as given, before
# float(): the comparison is exact for an int or a float and NaN fails it, so an integer too large
# for a float is refused here instead of overflowing float().
# Every detail quotes what was found through errors.safe_repr, since repr raises for an integer with
# more digits than sys.get_int_max_str_digits() wherever it sits, and the refusal must stay this
# gate's ProtocolError (c-integrate-reader-number-refusal-edges-1018).
# am[implements a-jev-client-1016@62f0db]
# am[addresses i-integrate-jev-replay-validation-1016@832033]
# am[implements a-integrate-reader-number-refusal-1018@e49eaa] am[rests-on c-rn-exact-range-before-float-1018@81d212]
# am[implements a-integrate-reader-numeric-refusal-closure-1018@54efbb] am[related a-rt-rr-safe-repr-1018@ec9700]
def checked_answer(
    model: Any,
    probabilities: Any,
    *,
    expected_model: str,
    options: frozenset[str],
    origin: Mapping[str, Any],
) -> Answer:
    def invalid(problem: str, **found: Any) -> ProtocolError:
        return ProtocolError(
            f"A Jev answer is invalid: {problem}.",
            details={**origin, "problem": problem, **found},
        )

    if not isinstance(model, str) or model != expected_model:
        raise invalid("it names another model", expected=expected_model, found=safe_repr(model)[:200])
    if not isinstance(probabilities, Mapping) or set(probabilities) != options:
        found = (sorted(option if isinstance(option, str) else safe_repr(option)[:200] for option in probabilities)
                 if isinstance(probabilities, Mapping) else safe_repr(probabilities)[:200])
        raise invalid("its options are not the question's", expected=sorted(options), found=found)
    values: dict[str, float] = {}
    for option, value in probabilities.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise invalid("a probability is not a number", option=str(option), found=safe_repr(value)[:200])
        if not 0 <= value <= 1:
            raise invalid("a probability is outside 0 to 1", option=str(option), found=safe_repr(value)[:200])
        values[str(option)] = float(value)
    precision = max(_decimals(number) for number in values.values())
    tolerance = len(values) * (0.5 * 10.0 ** -precision + sys.float_info.epsilon)
    total = math.fsum(values.values())
    if abs(total - 1.0) > tolerance:
        raise invalid("the probabilities do not sum to 1", total=total, tolerance=tolerance)
    return Answer(model, values)


# am[implements a-jev-client-1016]
# am[implements a-jev-immutable-admission-1016]
@dataclass(frozen=True, slots=True)
class AnswerCache:
    """Jev answers on disk, one JSON file per question asked of one state, named by its hash.

    An entry never changes once stored: `admit` writes it to a file of its own and hard-links that
    file to the key's name, which fails when the name exists, as git publishes a loose object
    (object-file.c, finalize_object_file). So a reader never sees a partial file, and the first
    entry stored under a key is the one every later reading of the key gets. `get` answers a file's
    JSON object as stored, its shape checked; JevClient admits its values through checked_answer,
    the same gate a live answer passes.
    """

    directory: Path

    def key(self, model: str, state: Mapping[str, Any], question: Mapping[str, Any]) -> str:
        return _digest([model, state, question])

    def get(self, key: str) -> Mapping[str, Any] | None:
        """The entry stored under key, {"model", "probabilities"} or {"refused"}, or None; an entry
        that is not strict JSON, or has neither shape, is a protocol error and is left as it is."""

        path = self.directory / f"{key}.json"
        if not path.is_file():
            return None
        try:
            body = json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=_strict_object,
                parse_constant=_no_constant,
            )
        except (UnicodeDecodeError, ValueError) as error:
            raise ProtocolError(
                "A cached Jev answer is not readable JSON.",
                details={"key": key, "path": str(path), "error": f"{type(error).__name__}: {error}"},
            ) from error
        refusal = isinstance(body, dict) and set(body) == {"refused"} and isinstance(body["refused"], str) and body["refused"]
        if not (refusal or (isinstance(body, dict) and set(body) == {"model", "probabilities"})):
            raise ProtocolError(
                "A cached Jev answer has neither the answer nor the refusal shape.",
                details={"key": key, "path": str(path),
                         "found": sorted(body) if isinstance(body, dict) else type(body).__name__},
            )
        return body

    # git's check_collision compares a colliding object byte for byte and fails when the bytes
    # differ; here a different entry is expected, because Jev samples its answers and two requests
    # that both missed one key can come back with different distributions, so the caller is told
    # and the entry stored first stands.
    # am[rests-on c-git-link-finalize-1016]
    def admit(self, key: str, body: Mapping[str, Any]) -> bool:
        """Store body under key unless an entry stands there; True when the key then holds body,
        False when a different entry was stored first, which stays.

        Cost: one file write and two fsyncs, the file and then the directory entry the link adds,
        so a stored entry outlives a crash; a collision reads the standing file instead.
        """

        data = canonical(body).encode("utf-8")
        final = self.directory / f"{key}.json"
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.directory, prefix=f".{key}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, final)
            except FileExistsError:
                return final.read_bytes() == data
            directory = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return True
        finally:
            Path(temporary).unlink(missing_ok=True)


# The answer cache's place: GOALCHAINER_JEV_CACHE, else XDG_CACHE_HOME's or the home directory's
# goalchainer/jev. A process with none of them, as a uid with no passwd entry is, gets cache_home's
# DependencyUnavailableError naming XDG_CACHE_HOME, which a reader meets on its first read rather
# than when it is built (c-dr-reader-built-without-home-1018).
# am[implements a-jev-client-1016] am[related a-dr-cache-home-typed-1018@63015f]
def default_answer_cache(env: Mapping[str, str] | None = None) -> AnswerCache:
    values = os.environ if env is None else env
    configured = values.get(JEV_CACHE_ENV, "").strip()
    if configured:
        return AnswerCache(Path(configured).expanduser().absolute())
    return AnswerCache(cache_home(values) / "jev")


# am[implements a-jev-client-1016]
def _missing(reason: str, message: str, **details: Any) -> MissingAnswerError:
    return MissingAnswerError(message, details={"reason": reason, **details})


# am[implements a-jev-client-1016]
def _scrubbed(text: str) -> str:
    """Error text with the configured key removed, in case a service ever echoes it."""

    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    return text.replace(key, "[redacted]") if key else text


# am[implements a-jev-client-1016]
@dataclass
class JevClient:
    """Asks Jev through typesafe-sdk, one cache entry per question, offline from the cache alone.

    Each question is cached on its own because Jev answers every question of a request
    independently, against the state alone (docs.typesafe.ai primitives.md, "Ask multiple
    questions together"), so a stored answer is exact whatever was asked beside it, and a table
    edit re-asks only the questions it changed.
    """

    cache: AnswerCache
    model: str
    offline: bool = False
    client_factory: Callable[[], Any] | None = None
    # How a hosted call retries, a typesafe_sdk RetryPolicy. None is mind.jev's policy: Jev answers
    # 1,200 requests a minute, the SDK's default of two retries gave up on 429s at 72 requests in
    # flight, and five from 1 s to 20 s wait about 30 s at most. A call inside a request's budget
    # takes this policy with its total retry time cut to the seconds the request has left.
    retry: Any = None
    # What live requests cost so far: their count and the input tokens Jev reported; and how many
    # of their entries met a different one stored first under the same key, which stands.
    requests: int = 0
    input_tokens: int = 0
    conflicts: int = 0
    _client: Any = field(default=None, repr=False)
    # One shared client is asked by concurrent reads (reader_for), so connecting and counting take
    # this lock: two first reads build one hosted client, and no count loses an increment.
    # am[implements a-integrate-domain-reader-reuse-1018@bffd2b]
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    # am[implements a-jev-client-1016] am[implements a-dr-reader-deadline-1018@1cdce4]
    def _retry_policy(self) -> Any:
        if self.retry is None:
            from typesafe_sdk import RetryPolicy  # noqa: PLC0415

            self.retry = RetryPolicy(max_retries=5, backoff_initial=1.0, backoff_max=20.0)
        return self.retry

    def _connect(self) -> Any:
        with self._lock:
            if self._client is None:
                from typesafe_sdk import TypeSafeClient, TypeSafeError  # noqa: PLC0415

                try:
                    self._client = (
                        self.client_factory()
                        if self.client_factory is not None
                        else TypeSafeClient(retry=self._retry_policy())
                    )
                except TypeSafeError as error:
                    raise _missing(
                        "no_key",
                        "Jev cannot be asked: no TypeSafe API key is configured.",
                        error=_scrubbed(str(error)),
                    ) from error
            return self._client

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None

    # am[implements a-jev-immutable-admission-1016] am[implements a-dr-reader-deadline-1018@1cdce4]
    # am[implements a-dr-reader-budget-required-1018@0b0cce] am[implements a-dr-sr-tool-budgets-1018@e4d351]
    def answers(
        self,
        state: Mapping[str, Any],
        questions: Mapping[str, Mapping[str, Any]],
        *,
        budget: RunBudget,
    ) -> dict[str, Answer]:
        """Every question's answer about state: the entry stored under its key, asking Jev first
        for the keys that have none. A request only stores, and every answer, replayed or just
        asked, is read back from the cache, so a reading uses exactly the entries its keys name.
        budget bounds every request this makes; a stored answer never consults it, since reading
        one starts no stage."""

        keys = {q: self.cache.key(self.model, state, spec) for q, spec in questions.items()}
        standing = {q: self.cache.get(key) for q, key in keys.items()}
        missing = {q: questions[q] for q, entry in standing.items() if entry is None}
        # A stored refusal or an invalid entry fails the reading before any request is spent.
        found = {
            q: self._stored(q, keys[q], questions[q], entry)
            for q, entry in standing.items()
            if entry is not None
        }
        if missing and self.offline:
            raise _missing(
                "not_cached",
                "A Jev answer is not in the replay cache and the reader is offline.",
                questions=sorted(missing),
                keys=sorted(keys[q] for q in missing),
                cache=str(self.cache.directory),
            )
        for batch in self._batches(state, missing):
            self._request(state, batch, keys, budget)
        for q in missing:
            found[q] = self._stored(q, keys[q], questions[q], self.cache.get(keys[q]))
        return {q: found[q] for q in questions}

    # am[implements a-jev-immutable-admission-1016]
    def _stored(
        self, q: str, key: str, spec: Mapping[str, Any], entry: Mapping[str, Any] | None
    ) -> Answer:
        """The answer the entry stored under key gives question q: a refusal fails the reading,
        and an answer passes checked_answer."""

        if entry is None:
            raise ProtocolError(
                "A Jev answer was not stored after its request.",
                details={"question": q, "key": key},
            )
        if "refused" in entry:
            raise _missing("refused", "Jev refused this text.", question=q, key=key,
                           refusal=entry["refused"])
        return checked_answer(
            entry["model"], entry["probabilities"], expected_model=self.model,
            options=frozenset(spec["criteria"]),
            origin={"source": "cache", "question": q, "key": key},
        )

    # am[implements a-jev-immutable-admission-1016]
    def _store(self, q: str, key: str, body: Mapping[str, Any]) -> None:
        """Admit a request's entry for question q; an entry stored first under key stands, and
        the difference is counted and logged."""

        if not self.cache.admit(key, body):
            with self._lock:
                self.conflicts += 1
            logger.info("Jev entry for %s differs from the one stored first under %s, which stands", q, key)

    def _batches(
        self, state: Mapping[str, Any], questions: Mapping[str, Mapping[str, Any]]
    ) -> list[dict[str, Mapping[str, Any]]]:
        """Questions packed into requests whose estimated size stays under the budget, in table
        order, and no request for no questions. The estimate only packs: a text it calls long is
        still sent, and Jev's refusal decides."""

        base = _tokens(state)
        batches: list[dict[str, Mapping[str, Any]]] = []
        size = base
        for q, spec in questions.items():
            cost = _tokens(spec)
            if not batches or size + cost > REQUEST_BUDGET:
                batches.append({})
                size = base
            batches[-1][q] = spec
            size += cost
        return batches

    # A request inside a run's budget is checked before its client is built, so a spent budget
    # starts nothing, and again once the client exists, since building it takes time: none is sent
    # after the deadline, and its attempts and retries together get only the seconds left then
    # (system_one takes per-call timeout and retry overrides). A failure once the deadline has
    # passed is the deadline's, ReviewTimeout, whether the call was cut at it or its retries had no
    # time left; one with time to spare keeps its service reason.
    # am[implements a-dr-reader-deadline-1018@1cdce4] am[rests-on c-dr-jev-call-unbounded-by-request-1018@24c349]
    # am[implements a-dr-sr-tool-budgets-1018@e4d351]
    def _request(
        self,
        state: Mapping[str, Any],
        batch: Mapping[str, Mapping[str, Any]],
        keys: Mapping[str, str],
        budget: RunBudget,
    ) -> None:
        from typesafe_sdk import (  # noqa: PLC0415
            TypeSafeAPIConnectionError,
            TypeSafeAPIError,
            TypeSafeAPITimeoutError,
            TypeSafeAuthenticationError,
            TypeSafeError,
            TypeSafePermissionDeniedError,
            TypeSafeRateLimitError,
        )
        from typesafe_sdk.constants import DEFAULT_TIMEOUT  # noqa: PLC0415

        budget.remaining()
        client = self._connect()
        _, seconds = budget.remaining()
        policy = self._retry_policy()
        bounds = {
            "timeout": min(seconds, DEFAULT_TIMEOUT),
            "retry": replace(policy, timeout=seconds if policy.timeout is None else min(policy.timeout, seconds)),
        }
        try:
            response = client.system_one(
                dict(state), {q: dict(spec) for q, spec in batch.items()}, model=self.model, **bounds
            )
        except TypeSafeError as error:
            message = _scrubbed(str(error))
            if "max_tokens_exceeded" in message:
                if len(batch) > 1:
                    names = list(batch)
                    half = len(names) // 2
                    self._request(state, {q: batch[q] for q in names[:half]}, keys, budget)
                    self._request(state, {q: batch[q] for q in names[half:]}, keys, budget)
                    return
                (only,) = batch
                self._store(only, keys[only], {"refused": "max_tokens_exceeded"})
                return
            try:
                budget.remaining()
            except ReviewTimeout as timeout:
                raise timeout from error
            if isinstance(error, (TypeSafeAuthenticationError, TypeSafePermissionDeniedError)):
                reason = "unauthorized"
            elif isinstance(error, TypeSafeRateLimitError):
                reason = "rate_limited"
            elif isinstance(error, (TypeSafeAPIConnectionError, TypeSafeAPITimeoutError)):
                reason = "unreachable"
            elif isinstance(error, TypeSafeAPIError):
                reason = "service_error"
            else:
                reason = "service_error"
            raise _missing(
                reason,
                "Jev did not answer.",
                error=f"{type(error).__name__}: {message}",
                questions=sorted(batch),
            ) from error
        with self._lock:
            self.requests += 1
            self.input_tokens += int(response.usage.input_tokens or 0)
        for q, spec in batch.items():
            answer = response.choices.get(q)
            checked = checked_answer(
                response.model, None if answer is None else dict(answer.probabilities),
                expected_model=self.model, options=frozenset(spec["criteria"]),
                origin={"source": "jev", "question": q, "key": keys[q]},
            )
            self._store(q, keys[q], {"model": checked.model, "probabilities": dict(checked.probabilities)})

    # am[implements a-jev-decided-nli-1016] am[implements a-dr-reader-deadline-1018@1cdce4]
    # am[implements a-dr-reader-budget-required-1018@0b0cce] am[implements a-dr-sr-tool-budgets-1018@e4d351]
    def settle(
        self, text: str, questions: Mapping[str, Mapping[str, Any]], *, budget: RunBudget
    ) -> dict[str, Settled]:
        """Each question decided on one draw, or on the mean of DRAWS draws when the first draw's
        top probability is under SURE; every draw is a request of its own and a cache entry, and
        every request is bounded by budget, as answers says."""

        state = {"text": text}
        first = self.answers(state, questions, budget=budget)
        unsure = {q: questions[q] for q, answer in first.items() if answer.top < SURE}
        draws = [first] + [
            self.answers({"text": text, "draw": draw}, unsure, budget=budget) for draw in range(1, DRAWS) if unsure
        ]
        settled: dict[str, Settled] = {}
        for q in questions:
            asked = [d[q] for d in draws if q in d]
            options = sorted(asked[0].probabilities)
            mean = {o: sum(a.probabilities[o] for a in asked) / len(asked) for o in options}
            settled[q] = Settled(
                answer=Answer(asked[0].model, mean),
                draws=len(asked),
                key=self.cache.key(self.model, state, questions[q]),
            )
        return settled


# am[implements a-jev-client-1016]
@dataclass(frozen=True, slots=True)
class Settled:
    """A question's decided answer, how many draws decided it, and its first draw's cache key."""

    answer: Answer
    draws: int
    key: str


# ---------------------------------------------------------------------------
# The cross-encoder: which passage answers which question
# ---------------------------------------------------------------------------


# The cross-encoder one read is grounded by: the pinned base, or the reviewed artifact
# semantic_sleep promoted, under the identity the reading's revision digests.
# am[implements a-jev-serve-active-1016]
@dataclass(frozen=True, slots=True)
class ServedRanker:
    identity: str
    model_dir: Path


# ACTIVE is resolved once per read, so a promotion or a rollback takes effect on the next read.
# An artifact is served only under the ranking instruction it was trained and evaluated with:
# CrossEncoder puts the instruction into every prompt, so the same weights under another
# instruction are a model nobody evaluated. Serving checks the artifact's manifest and file sizes,
# not its bytes, which promotion hashed in full; that fast check assumes nothing but authorized
# publication writes under the artifact root and a published artifact is never edited in place, so
# a same-size edit by anything else goes unseen until a full-hash validation.
# am[implements a-jev-serve-active-1016]
# am[rests-on c-sleep-serving-contract-agreed-1016]
# am[rests-on c-serving-fast-validation-assumed-1016]
def served_ranker(declaration: ReadingDeclaration, root: Path | None = None) -> ServedRanker:
    """The cross-encoder to serve now: the artifact semantic_sleep's ACTIVE pointer names under
    root (default artifact_root()), else the pinned base."""

    from .semantic_artifacts import SleepError, artifact_root, resolve_active  # noqa: PLC0415

    where = artifact_root() if root is None else root
    try:
        reference = resolve_active(where, RERANKER.identity)
    except SleepError as error:
        raise ProtocolError(
            "The promoted cross-encoder cannot be served.",
            details={"root": str(where), "error": str(error)},
        ) from error
    if reference.model_dir is None:
        return ServedRanker(RERANKER.identity, ready_model_dir())
    evaluated = (reference.manifest or {}).get("instruction")
    if evaluated != declaration.ranking_instruction:
        raise ProtocolError(
            "The promoted cross-encoder was evaluated under another ranking instruction.",
            details={"artifact": reference.identity, "evaluated": evaluated,
                     "declaration": declaration.ranking_instruction},
        )
    return ServedRanker(reference.identity, reference.model_dir)


# am[implements a-jev-cross-encoder-1016]
# am[implements a-jev-derive-language-1016]
def passages(text: str, language: str) -> tuple[str, ...]:
    """The text's sentences in the reading declaration's language, by Wikimedia's sentencex
    segmenter, each stripped of edge spaces."""

    from sentencex import segment  # noqa: PLC0415 (the semantic extra)

    found = tuple(piece.strip() for piece in segment(language, text) if piece.strip())
    return found or (text.strip(),)


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------


# am[implements a-jev-cross-encoder-1016]
@dataclass(frozen=True, slots=True)
class Grounding:
    """The passage the cross-encoder ranks first for a question, and its ranking score."""

    passage: str
    score: float


# The direction travels with the answer, so what a reading means is read off it without asking
# which domain named the answer.
# am[implements a-jev-adapter-1016] am[implements a-dr-direction-words-1018@1b6ec6]
@dataclass(frozen=True, slots=True)
class PropositionReading:
    """One proposition's decided answer, the direction its declaration gives that answer, its
    probability, and the passage that answers it."""

    proposition: Proposition
    answer: str
    direction: str
    probability: float
    probabilities: Mapping[str, float]
    draws: int
    key: str
    grounding: Grounding | None


# am[implements a-jev-adapter-1016]
@dataclass(frozen=True, slots=True)
class ChoiceReading:
    """One choice reading's decided option and its probabilities."""

    choice: Choice
    answer: str
    probability: float
    probabilities: Mapping[str, float]
    draws: int
    key: str


# A binding's answer is one of the entities it offers or NO_MATCH, and its probability is the
# model's, never a reason to trust the entity more: what the answer supports is decided where the
# reading is projected (reading_projection.entity_readings).
# am[implements a-bnd-reading-1019@105c81]
@dataclass(frozen=True, slots=True)
class BindingReading:
    """One binding's decided answer, an offered entity or NO_MATCH, and its probabilities."""

    binding: Binding
    answer: str
    probability: float
    probabilities: Mapping[str, float]
    draws: int
    key: str

    @property
    def entity(self) -> str | None:
        """The entity the answer chose, or None for NO_MATCH."""

        return None if self.answer == NO_MATCH else self.answer


# A reading carries the declaration it was read against, so its facts are admitted, and its answers
# mean what they mean, only under that declaration's identity.
# am[implements a-jev-adapter-1016] am[implements a-dr-identity-1018@df82ab] am[implements a-bnd-reading-1019@105c81]
@dataclass(frozen=True, slots=True)
class Reading:
    """Everything the reader read in one text, under one reader revision and one declaration."""

    text: str
    model: str
    revision: str
    declaration: ReadingDeclaration
    passages: tuple[str, ...]
    propositions: tuple[PropositionReading, ...]
    choices: tuple[ChoiceReading, ...]
    bindings: tuple[BindingReading, ...]

    def proposition(self, reading_id: str) -> PropositionReading:
        return next(r for r in self.propositions if r.proposition.id == reading_id)

    def choice(self, reading_id: str) -> ChoiceReading:
        return next(r for r in self.choices if r.choice.id == reading_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "revision": self.revision,
            "domain": self.declaration.name,
            "declaration": self.declaration.digest,
            "propositions": [
                {
                    "id": r.proposition.id,
                    "answer": r.answer,
                    "direction": r.direction,
                    "probability": r.probability,
                    "probabilities": dict(r.probabilities),
                    "draws": r.draws,
                    "answer_key": r.key,
                    "grounding": None if r.grounding is None else {
                        "passage": r.grounding.passage, "score": r.grounding.score},
                    "estimator": "model-proposed",
                }
                for r in self.propositions
            ],
            "choices": [
                {"id": r.choice.id, "answer": r.answer, "probability": r.probability,
                 "probabilities": dict(r.probabilities), "draws": r.draws, "answer_key": r.key}
                for r in self.choices
            ],
            "bindings": [
                {"signal": r.binding.signal, "control": r.binding.control, "answer": r.answer, "entity": r.entity,
                 "probability": r.probability, "probabilities": dict(r.probabilities), "draws": r.draws,
                 "answer_key": r.key, "estimator": "model-proposed"}
                for r in self.bindings
            ],
        }


# am[implements a-jev-adapter-1016] am[implements a-dr-reader-core-1018@84955f]
class SemanticReader:
    """Reads texts against one reading declaration: Jev for every answer, the cross-encoder for
    which passage answers each decided proposition."""

    def __init__(
        self,
        *,
        declaration: ReadingDeclaration,
        jev: JevClient | None = None,
        serve: Callable[[], ServedRanker] | None = None,
        load: Callable[[ServedRanker], PassageRanker] | None = None,
    ) -> None:
        self.declaration = declaration
        if jev is not None and jev.model != declaration.model:
            raise InvalidInputError(
                "The Jev client asks a different model than the reading declaration pins.",
                details={"client": jev.model, "declaration": declaration.model},
            )
        self._jev = jev
        self._serve = serve or (lambda: served_ranker(self.declaration))
        self._load = load or (
            lambda served: PassageRanker(served.model_dir, self.declaration.ranking_instruction)
        )
        self._loaded: tuple[ServedRanker, PassageRanker] | None = None
        self._lock = threading.Lock()

    # The Jev client the reader asks: the caller's when it gave one, else one configured from the
    # environment on first use, under the reader's lock so concurrent first reads build one. Only a
    # read needs the answer cache's place, so a reader is built where it has none, as a SNARS session
    # that never reads text builds the default reader (c-dr-reader-built-without-home-1018).
    # am[implements a-dr-reader-home-at-read-1018@3ddda8] am[rests-on c-dr-reader-built-without-home-1018@99837f]
    @property
    def jev(self) -> JevClient:
        with self._lock:
            if self._jev is None:
                self._jev = JevClient(
                    default_answer_cache(),
                    self.declaration.model,
                    offline=os.environ.get(JEV_OFFLINE_ENV, "").strip() == "1",
                )
            return self._jev

    # am[implements a-jev-serve-active-1016]
    # am[implements a-rpc-reading-scoring-identity-1019@452cee] am[addresses i-rpc-reader-scoring-identity-1019@ea56eb]
    # am[rests-on c-rpc-revision-not-evidence-identity-1019@2b1277]
    def revision(self, served: ServedRanker) -> str:
        """What a reading depends on besides its text: the declaration (which pins the Jev model),
        the served cross-encoder's identity, the scoring code's identity and the segmenter's version,
        as a full SHA-256. Jev's answer keys digest none of these but the model, so a change of
        scoring code is a new revision whose answers replay from the same cache entries."""

        return _digest(
            {
                "declaration": self.declaration.digest,
                "ranker": served.identity,
                "scoring": scoring_identity(),
                "segmenter": f"sentencex {metadata.version('sentencex')}",
            }
        )

    # One model in memory at a time: a read served by another identity replaces the loaded one.
    # A read keeps the model it captured, so a read that captured an identity before a promotion
    # still scores with that model after another read has loaded the promoted one.
    # am[implements a-jev-serve-active-1016]
    def _ranked(self, served: ServedRanker) -> PassageRanker:
        with self._lock:
            if self._loaded is None or self._loaded[0] != served:
                self._loaded = (served, self._load(served))
            return self._loaded[1]

    # Time: one ACTIVE resolution, one Jev request per text (two more for each unsure question's
    # draws) and one cross-encoder pass per (decided proposition, passage) pair.
    # A read whose deadline has passed does not start, budget bounds every Jev request, and a
    # deadline that passes while Jev answers starts no ranking stage: RunBudget.remaining raises
    # ReviewTimeout before each, so the cross-encoder never loads late. Every read is some caller's
    # stage, so the budget has no default.
    # am[implements a-dr-reader-deadline-1018@1cdce4] am[implements a-dr-reader-budget-required-1018@0b0cce]
    def read(self, text: str, *, budget: RunBudget) -> Reading:
        if not isinstance(text, str) or not text.strip():
            raise InvalidInputError("Semantic reading requires nonempty text.")
        budget.remaining()
        served = self._serve()
        declaration = self.declaration
        settled = self.jev.settle(text, declaration.questions(), budget=budget)
        pieces = passages(text, declaration.language)
        decided = [
            p for p in declaration.propositions if settled[p.id].answer.decided() in declaration.decided
        ]
        pairs = [(p.question, piece) for p in decided for piece in pieces]
        if pairs:
            budget.remaining()
        scores = self._ranked(served).scores(pairs) if pairs else ()
        groundings: dict[str, Grounding] = {}
        for index, proposition in enumerate(decided):
            row = scores[index * len(pieces) : (index + 1) * len(pieces)]
            best = max(range(len(pieces)), key=lambda i: (row[i], -i))
            groundings[proposition.id] = Grounding(pieces[best], row[best])
        models = {settled[q].answer.model for q in settled}
        if len(models) != 1:
            raise ProtocolError(
                "One reading mixes answers from several Jev models.",
                details={"models": sorted(models)},
            )
        return Reading(
            text=text,
            model=models.pop(),
            revision=self.revision(served),
            declaration=declaration,
            passages=pieces,
            propositions=tuple(
                PropositionReading(
                    proposition=p,
                    answer=settled[p.id].answer.decided(),
                    direction=declaration.direction(settled[p.id].answer.decided()),
                    probability=settled[p.id].answer.top,
                    probabilities=dict(settled[p.id].answer.probabilities),
                    draws=settled[p.id].draws,
                    key=settled[p.id].key,
                    grounding=groundings.get(p.id),
                )
                for p in declaration.propositions
            ),
            choices=tuple(
                ChoiceReading(
                    choice=c,
                    answer=settled[c.id].answer.decided(),
                    probability=settled[c.id].answer.top,
                    probabilities=dict(settled[c.id].answer.probabilities),
                    draws=settled[c.id].draws,
                    key=settled[c.id].key,
                )
                for c in declaration.choices
            ),
            bindings=tuple(
                BindingReading(
                    binding=b,
                    answer=settled[b.question_id].answer.decided(),
                    probability=settled[b.question_id].answer.top,
                    probabilities=dict(settled[b.question_id].answer.probabilities),
                    draws=settled[b.question_id].draws,
                    key=settled[b.question_id].key,
                )
                for b in declaration.bindings
            ),
        )


_READERS_LOCK = threading.Lock()
_READERS: dict[str, SemanticReader] = {}


# One reader per declaration per process, found by the declaration's digest, its identity wherever
# it is written. A reader holds its declaration and the process's configuration, the answer cache
# the environment names and the cross-encoder ACTIVE serves, and nothing of any read: each read
# takes its text and its caller's budget as arguments and returns its reading. So every request
# reading one domain shares one reader and its loaded model, whose passes PassageRanker serializes,
# where a reader made per request loaded a model per request (c-dr-request-reader-per-request-1018).
# Time: one lock round and one dict lookup; a digest's first call also makes its reader, which loads
# nothing until it ranks.
# am[implements a-integrate-domain-reader-reuse-1018@bffd2b] am[rests-on c-dr-request-reader-per-request-1018@4dbff7]
# am[implements a-integrate-reader-numeric-refusal-closure-1018@54efbb]
def reader_for(declaration: ReadingDeclaration) -> SemanticReader:
    """The process's one reader of `declaration`, shared by every caller reading with a
    declaration of the same digest."""

    if not isinstance(declaration, ReadingDeclaration):
        raise InvalidInputError("A reader reads with a ReadingDeclaration.",
                                details={"declaration": safe_repr(declaration)[:200]})
    with _READERS_LOCK:
        reader = _READERS.get(declaration.digest)
        if reader is None:
            reader = _READERS[declaration.digest] = SemanticReader(declaration=declaration)
        return reader


# The reader of the domain a caller selected, and the one home of the refusal every surface gives
# text whose selected domain declares no reading section: the domain request and the SNARS command
# and dispatch alike.
# am[implements a-ie-sr-text-needs-domain-1018@8f7f0b] am[rests-on c-dr-domain-reader-one-home-1018@a821ed]
def domain_reader(domain: Domain) -> SemanticReader:
    """The process's one reader of `domain`'s reading section; InvalidInputError when the domain
    declares none."""

    if domain.readings is None:
        raise InvalidInputError("The selected domain declares no semantic readings.")
    return reader_for(domain.readings)


_INCIDENT_SETUP = "goal_chainer.semantic_reader:incident-reading-section"
_INCIDENT: ReadingDeclaration | None = None


# The packaged incident domain's reading section, read for default_reader by initialize_once, which
# records the setup only after this returns, so a read its deadline stops is attempted again whole.
# am[implements a-dr-sr-default-reader-1018@dce66c] am[implements a-integrate-default-reader-deadline-audit-1018@b7a2d5]
def _load_incident(engine: Any, *, budget: RunBudget) -> None:
    global _INCIDENT
    del engine
    declaration = packaged_domain("incident", budget=budget).readings
    if declaration is None:
        raise DependencyUnavailableError(
            "The packaged incident domain declares no reading section; reinstall GoalChainer.",
            details={"domain": "incident"},
        )
    _INCIDENT = declaration


# The capture, evaluation and sleep tools read with the packaged incident domain's reading section,
# and a request or a SNARS session with the domain its caller selects (domain_reader), so nothing
# else reads a declaration a caller did not choose; both read through reader_for. The packaged
# domain is read once per process, fixed startup work that the first caller's deadline bounds and
# no request's inferences pay (c-dr-packaged-load-fixed-init-1018), so which caller comes first
# changes no caller's charge. The read is the runtime's one-time startup, initialize_once: once it
# is done a call waits for nothing, and before then a caller waits for the engine only until its
# own deadline, so one behind a slow first read raises its ReviewTimeout where a lock held it to the
# first caller's deadline (c-dr-default-reader-lock-past-deadline-1018).
# Time: one packaged_domain read on the first call, for the incident domain about 0.29 million
# uncharged inferences and 0.1 s once the engine is booted; one set membership test and one
# reader_for round on every later call.
# am[implements a-jev-adapter-1016] am[implements a-dr-sr-default-reader-1018@dce66c]
# am[rests-on c-dr-packaged-load-fixed-init-1018@716be8] am[implements a-integrate-domain-reader-reuse-1018@bffd2b]
# am[implements a-integrate-default-reader-deadline-audit-1018@b7a2d5]
def default_reader(*, budget: RunBudget) -> SemanticReader:
    """The process's reader of the packaged incident domain's reading section, configured from the
    environment and read on first use within `budget`'s deadline, charged none of its inferences.
    A first use that cannot finish by that deadline raises ReviewTimeout and leaves the read to
    the next call."""

    startup = caller_budget(budget, "The default reader").deadline_only()
    initialize_once(_INCIDENT_SETUP, partial(_load_incident, budget=startup), budget=startup)
    return reader_for(_INCIDENT)


__all__ = [
    "Answer",
    "AnswerCache",
    "BindingReading",
    "ChoiceReading",
    "Grounding",
    "JevClient",
    "PassageRanker",
    "PropositionReading",
    "Reading",
    "SemanticReader",
    "ServedRanker",
    "Settled",
    "default_answer_cache",
    "default_reader",
    "domain_reader",
    "reader_for",
    "passages",
    "served_ranker",
]

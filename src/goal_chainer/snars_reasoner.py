"""Purpose: run replayable high-level SNARS sessions: each operation replays the session's stored
events with the operation as one batch, which runs in-process in the packaged SNARS library's world
for its optional features unless the session was given another executor, and a mutating operation's
event is appended only after its batch answered. A session runs every batch under the one RunBudget
its caller opened it with. Forward queries schedule speculative inference under that budget and
return a first supported witness without storing the derived world."""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .runtime.budget import RunBudget, caller_budget
from .runtime.numbers import finite_float
from .snars_engine import compiled_worlds, run_snars_batch, snars_identity
from .snars_models import (
    Evidence,
    SnarsBelief,
    SnarsCondition,
    SnarsCounterfactual,
    SnarsGoal,
    SnarsObligations,
    SnarsTrack,
)
from .errors import InvalidInputError, PersistenceError, ProtocolError
from .event_store import digest
from .snars_program import ProgramFragments, SnarsBatch, SnarsProgramBuilder, parse_guard, parse_statement
from .snars_protocol import (
    ProtocolEnvelope,
    atom_to_python,
    parse_belief,
    parse_condition,
    parse_counterfactual,
    parse_obligations,
    parse_protocol_output,
    parse_track,
)
from .snars_store import Redactor, SnarsEventStore

# A session's reader is its caller's to choose and is named here only in an annotation, so the
# SNARS core imports no semantic reader.
# am[implements a-sib-home-snars-ingestion-1018@5727d2]
if TYPE_CHECKING:
    from .semantic_reader import SemanticReader

DEFAULT_PROOF_DEPTH = 4
DEFAULT_PROOF_SIZE = 12
# The evidence a supposition carries when its caller names none: what_if's hypothesis and an
# obligation route's open premise, the strength SNARS's would?! assumes.
# am[implements a-rt-ob-session-1017@f1468f]
DEFAULT_HYPOTHESIS = Evidence(8.0, 0.0)
# What runs a session's batches: given the batch and its budget, it answers the batch's output
# lines, the engine's printed answers one per line.
SnarsExecutor = Callable[[SnarsBatch, RunBudget], Sequence[str]]


# The executor every session runs on unless it was given another: the in-process one.
# am[implements a-rt-snars-batch-speculative-1017@451056]
def execute_in_process(batch: SnarsBatch, budget: RunBudget) -> Sequence[str]:
    return run_snars_batch(batch, budget=budget).output_lines


# What a report names as the reasoner it ran on: the in-process engine and each SNARS world this
# process compiled, as compiled, with the SNARS identity a store records.
# am[implements a-rt-snars-batch-speculative-1017@451056] am[implements a-ie-s7-python-1018@e9b9d4]
def runtime_payload() -> dict[str, Any]:
    return {
        "reasoner": "goalchainer-snars-on-pymetta",
        "worlds": [
            {**asdict(world), "snars_identity": world.snars_identity} for world in compiled_worlds()
        ],
    }


@dataclass(frozen=True, slots=True)
class SnarsOperation:
    """A validated protocol response and its JSON-compatible projection."""

    operation: str
    payload: Any
    raw: str


class SnarsSession:
    """Replayable SNARS state without a long-running daemon."""

    # A session runs every batch under the one RunBudget its caller opened it with, so the
    # operations of one request share one deadline and one inference allowance; the store must
    # have been written against the SNARS library this process runs, since its events replay
    # through it. Each operation appends the event its batch decided under that budget too: the
    # append waits for the store's write lock no longer than the deadline and reads the budget again
    # before it commits, so an event that cannot commit by then, or after a batch that spent what was
    # left, raises the budget's exhaustion and leaves the store as it was, and no operation answers
    # what its batch computed for an event that did not commit (c-v2rs-snars-budget-ruling-1020).
    # Every read of the store the session makes, each batch's replay, an outcome's lookup of its
    # observation, has_outcome and the state report, takes that budget too, so none answers past a
    # spent budget or waits for a lock past the deadline.
    # It reads text with the reader its caller opened it with, whose declaration admits
    # every batch's readings and gives the policy its rows, so the caller, not the session, chooses
    # the domain a session reads. A session opened without a reader reads no text, and its batches
    # carry the policy with no rows, so each statement operation answers what it answers in a
    # session reading any domain that has read no text (c-dr-snars-facts-need-declaration-1018).
    # am[implements a-rt-snars-batch-speculative-1017@451056] am[implements a-rt-snars-store-identity-1017@deb59d]
    # am[implements a-rt-rbs-session-budget-1018@8c3da2] am[rests-on c-rt-sessions-request-scoped-1018@e869b6]
    # am[implements a-dr-sr-snars-batch-declaration-1018@5c965d] am[implements a-ie-sr-readerless-session-1018@9ffb9b]
    # am[implements a-v2rs-snars-budget-1020@5469ea] am[rests-on c-v2rs-snars-budget-ruling-1020@2b93de]
    # am[addresses i-v2-snars-append-past-deadline-1020@e019dd] am[implements a-v2rs-kr-session-1020@53ac31]
    def __init__(
        self,
        store: SnarsEventStore,
        *,
        budget: RunBudget,
        reader: SemanticReader | None = None,
        include_goalchainer_policy: bool = True,
        execute: SnarsExecutor = execute_in_process,
    ) -> None:
        self.budget = caller_budget(budget, "A SNARS session")
        identity = snars_identity()
        if store.snars_identity != identity:
            raise PersistenceError(
                "SNARS store was written against a different SNARS library than this process runs.",
                details={"store": store.snars_identity, "runtime": identity},
            )
        self.store = store
        self.builder = SnarsProgramBuilder(reader)
        self.include_goalchainer_policy = include_goalchainer_policy
        self._run = execute
        self._last_ingestion_payload: dict[str, Any] | None = None
        # The ingest events this session read, stored now or before: its batches carry their
        # readings and no other text's, whatever else the store holds.
        # am[implements a-jev-session-reads-1017@3d73d9]
        self._read: list[Mapping[str, Any]] = []

    # The budget is read as the store opens, as persistent's is, so a spent one refuses the session.
    # am[implements a-rt-snars-store-identity-1017@deb59d] am[implements a-v2rs-snars-budget-1020@5469ea]
    @classmethod
    def ephemeral(cls, *, budget: RunBudget, **options: Any) -> SnarsSession:
        budget = caller_budget(budget, "A SNARS session")
        return cls(
            SnarsEventStore.memory(snars_identity=snars_identity(), budget=budget),
            budget=budget,
            **options,
        )

    # The store reads the budget before it touches the file, so a session whose budget is spent is
    # refused with its exhaustion and leaves no database file, and the open waits for the write lock
    # no longer than the deadline.
    # am[implements a-rt-snars-store-identity-1017@deb59d] am[implements a-rt-rbs-session-budget-1018@8c3da2]
    # am[implements a-v2rs-snars-budget-1020@5469ea] am[addresses i-v2rs-snars-store-unbudgeted-1020@ab0398]
    @classmethod
    def persistent(
        cls,
        path: str | Path,
        *,
        budget: RunBudget,
        redactor: Redactor | None = None,
        **options: Any,
    ) -> SnarsSession:
        budget = caller_budget(budget, "A SNARS session")
        return cls(
            SnarsEventStore(
                path,
                snars_identity=snars_identity(),
                redactor=redactor,
                budget=budget,
            ),
            budget=budget,
            **options,
        )

    # The store deduplicates identical prepared events: the same text, source, trust, reader
    # revision and facts add nothing. A reading under another reader revision, such as a promoted
    # cross-encoder's, is a new event; SNARS then deduplicates support separately, by its receipt
    # for each statement and source, so that event adds no evidence
    # (c-snars-receipt-statement-source-1016). Either way the event is one this session read, so
    # its decisions believe the text's readings. Two sessions reading the same text at once append
    # it once, since the store keys the event by its content.
    # am[implements a-jev-snars-ingest-1016]
    # am[rests-on c-snars-receipt-statement-source-1016]
    # am[implements a-jev-session-reads-1017@3d73d9]
    # The reading runs under the session's budget, the request's, like every batch the session runs.
    # am[implements a-dr-reader-budget-required-1018@0b0cce] am[implements a-rt-rbs-session-budget-1018@8c3da2]
    # am[implements a-v2rs-snars-budget-1020@5469ea] am[implements a-v2rs-snars-keyed-dedup-1020@85653f]
    def ingest_text(
        self,
        text: str,
        *,
        source: str = "user",
        trust: float = 1.0,
    ) -> SnarsOperation:
        ingested = self.builder.text_ingestion(text, source=source, trust=trust, budget=self.budget)
        payload = {
            "text": text,
            "source": source,
            "trust": trust,
            "reader_revision": ingested.revision,
            "facts": list(ingested.fragments.facts),
            "effects": list(ingested.fragments.effects),
        }
        prepared = self.store.prepare_payload("ingest_text", payload)
        self._last_ingestion_payload = dict(prepared)
        if prepared not in self._read:
            self._read.append(prepared)
        if self._has_event("ingest_text", prepared):
            envelope = self._execute(
                self._gc("inspect-record"),
                expected_operation="inspect",
            )
            return _operation(envelope, self.builder)
        _event_fragments("ingest_text", prepared, self.builder)
        envelope = self._execute(
            self._gc("inspect-record"),
            expected_operation="inspect",
            pending=("ingest_text", prepared),
        )
        self.store.append_once("ingest_text", prepared, budget=self.budget)
        return _operation(envelope, self.builder)

    @property
    def last_ingestion_payload(self) -> dict[str, Any]:
        """Return the prepared event for the latest ingestion request."""

        if self._last_ingestion_payload is None:
            raise ProtocolError("No text has been ingested in this session.")
        return deepcopy(self._last_ingestion_payload)

    # A report of the store as one read of it found it, so its digest and its event count describe
    # the same events whatever another session appends meanwhile, as a motivation history's do.
    # The read takes the session's budget as every read does: a deadline passing during it after an
    # operation committed raises the budget's exhaustion, as the CLI's and the skill's own budget
    # check after the command would (c-v2rs-envelope-rechecks-1020); the committed event stays, and a
    # keyed one sent again is found already recorded.
    # The budget is read once more after the events are hashed, so the report never answers past
    # the deadline.
    # am[implements a-v2rs-state-one-read-1020@736ce1] am[addresses i-v2rs-snars-state-split-read-1020@cfd3fc]
    # am[related c-v2m-st-split-reads-1019@b1d1ca] am[implements a-v2rs-kr-session-1020@53ac31]
    # am[rests-on c-v2rs-envelope-rechecks-1020@807f41]
    def state_payload(self) -> dict[str, Any]:
        """Describe the current replay store for CLI and decision reports, from one read of it."""

        events = self.store.events(budget=self.budget)
        report = {
            "kind": "persistent" if self.store.persistent else "ephemeral",
            "path": str(self.store.path) if self.store.path else None,
            "digest": digest(events),
            "event_count": len(events),
        }
        self.budget.remaining()
        return report

    # am[implements a-ev-native-memory@cc9cc9]
    # am[rests-on c-ev-believe-receipt-gated@cc884c]
    # am[implements a-ev-br-session-1017@c3ddf0] am[implements a-v2rs-snars-budget-1020@5469ea]
    # am[implements a-v2rs-snars-keyed-dedup-1020@85653f]
    def believe(
        self,
        statement: str,
        *,
        evidence: Evidence | None = None,
        source: str = "caller",
        trust: float = 1.0,
        occurrence: float | None = None,
        proof_depth: int = DEFAULT_PROOF_DEPTH,
    ) -> SnarsBelief:
        """Author one belief, appending its event only when no identical one exists.

        SNARS gates evidence on a new (statement, source) receipt, so an
        identical belief adds nothing; skipping its event keeps a persistent
        store's digest unchanged when a caller resupplies the same evidence.
        The store keys the event by its content, so two sessions resupplying
        it at once append it once.
        Evidence that gives no base rate is stored without one and read by
        SNARS at its configured default.
        """

        atom = parse_statement(statement)
        counts = evidence or Evidence(1.0, 0.0)
        payload = {
            "statement": self.builder.codec.emit(atom),
            "positive": counts.positive,
            "negative": counts.negative,
            "base_rate": counts.base_rate,
            "source": source,
            "trust": _probability("trust", trust),
            "occurrence": occurrence,
        }
        prepared = self.store.prepare_payload("belief", payload)
        duplicate = self._has_event("belief", prepared)
        if not duplicate:
            _event_fragments("belief", prepared, self.builder)
        operation = self._gc(
            "belief-record",
            self.builder.codec.symbol("belief"),
            atom,
            _positive_integer("proof_depth", proof_depth),
        )
        envelope = self._execute(
            operation,
            expected_operation="belief",
            pending=None if duplicate else ("belief", prepared),
        )
        belief = parse_belief(envelope.payload, self.builder.codec)
        if not duplicate:
            self.store.append_once("belief", prepared, budget=self.budget)
        return belief

    def belief(
        self,
        statement: str,
        *,
        proof_depth: int = DEFAULT_PROOF_DEPTH,
    ) -> SnarsBelief:
        atom = parse_statement(statement)
        operation = self._gc(
            "belief-record",
            self.builder.codec.symbol("belief"),
            atom,
            _positive_integer("proof_depth", proof_depth),
        )
        envelope = self._execute(operation, expected_operation="belief")
        return parse_belief(envelope.payload, self.builder.codec)

    def ask(self, pattern: str) -> SnarsOperation:
        atom = parse_statement(pattern, pattern=True)
        envelope = self._execute(
            self._gc("ask-record", atom),
            expected_operation="ask",
        )
        return _operation(envelope, self.builder)

    # The optional world owns its hook; other operations keep their ordinary native worlds.
    # Time: event replay plus query graph construction and the inference work the budget admits.
    # am[implements a-integrate-ecan-forward-query-interface-1017] am[implements a-rt-rbs-session-budget-1018@8c3da2]
    def forward_query(self, statement: str) -> SnarsOperation:
        """Find the first receipt- or proof-supported ground answer using query-directed attention.

        Witness includes negative and vacuous evidence. Incomplete means the retained frontier
        was exhausted, not that the statement is false. The query runs under the session's budget,
        and a spent budget raises its typed error; the caller reads what the session has spent
        from session.budget.spent. No derived state or event is persisted.
        """
        atom = parse_statement(statement)
        envelope = self._execute(
            self._gc("forward-query-record", atom),
            expected_operation="forward-query",
            includes=self._default_includes | {"attention"},
        )
        return _operation(envelope, self.builder)

    # Every structural route to the statement within the size bound and what each still needs at
    # the threshold, an open premise standing under the stated hypothesis. One speculative batch
    # under the session's budget; a spent budget raises its typed error, never an empty answer, and
    # nothing persists.
    # Time: event replay plus sbc-sz over the live world, at most max_size nodes a route.
    # am[implements a-rt-ob-session-1017@f1468f] am[rests-on c-rt-pm-interface-shape-v6-1017@ec7b8c]
    # am[implements a-rt-rbs-session-budget-1018@8c3da2]
    def obligations(
        self,
        statement: str,
        *,
        hypothesis: Evidence = DEFAULT_HYPOTHESIS,
        threshold: float | None = None,
        max_size: int = DEFAULT_PROOF_SIZE,
    ) -> SnarsObligations:
        """Answer each route to `statement` and its open, undecided or failed leaves.

        A route's scenario is the opinion the statement would hold were every open premise to
        carry `hypothesis`: a labelled supposition, never attainable confidence, an information
        value or a bound. `threshold` defaults to SNARS's decision threshold.
        """

        if not isinstance(hypothesis, Evidence):
            raise InvalidInputError("obligations takes its hypothesis as Evidence.")
        atom = parse_statement(statement)
        envelope = self._execute(
            self._gc(
                "obligations-record",
                atom,
                hypothesis.positive,
                hypothesis.negative,
                self.builder.rate(hypothesis.base_rate),
                _positive_integer("max_size", max_size),
                _threshold(self.builder.codec, threshold),
            ),
            expected_operation="obligations",
        )
        return parse_obligations(envelope.payload, self.builder.codec)

    # The condition a planner reads: the attention forward search and its classification in one
    # batch, so a belief the search derived is read before the speculation discards it. A negated
    # condition classifies the literal (Not S) through the complement of S's opinion.
    # Time: event replay plus the forward query's graph, cycle and search under the session's
    # budget.
    # am[implements a-rt-ob-session-1017@f1468f] am[rests-on c-integrate-runtime-obligations-ruling-1017@6a2fe6]
    # am[implements a-rt-ob-negation-track-1017@a1a80d] am[implements a-rt-rbs-session-budget-1018@8c3da2]
    def condition(
        self,
        statement: str,
        *,
        threshold: float | None = None,
        negated: bool = False,
    ) -> SnarsCondition:
        """Classify `statement`, or (Not statement) when `negated`, once the attention search ran.

        Holds when the literal's belief b clears the threshold, Fails when its plausibility b + u
        falls below it, and Undecided otherwise, an unsupported statement and an exhausted search
        included. The literal (Not S) has S's complement opinion (d, b, u, 1 - a), so its interval
        is [d, d + u]. `threshold` defaults to SNARS's decision threshold.
        """

        if not isinstance(negated, bool):
            raise InvalidInputError("condition takes negated as a bool.")
        atom = parse_statement(statement)
        polarity = self.builder.codec.symbol("neg" if negated else "pos")
        envelope = self._execute(
            self._gc("condition-record", atom, polarity, _threshold(self.builder.codec, threshold)),
            expected_operation="condition",
            includes=self._default_includes | {"attention"},
        )
        return parse_condition(envelope.payload, self.builder.codec)

    def prove(
        self,
        statement: str,
        *,
        max_depth: int = DEFAULT_PROOF_DEPTH,
        max_size: int = DEFAULT_PROOF_SIZE,
    ) -> SnarsOperation:
        atom = parse_statement(statement)
        envelope = self._execute(
            self._gc(
                "prove-record",
                atom,
                _positive_integer("max_depth", max_depth),
                _positive_integer("max_size", max_size),
            ),
            expected_operation="prove",
        )
        return _operation(envelope, self.builder)

    def explain(
        self,
        statement: str,
        *,
        max_depth: int = DEFAULT_PROOF_DEPTH,
    ) -> SnarsOperation:
        atom = parse_statement(statement)
        envelope = self._execute(
            self._gc(
                "explain-record",
                atom,
                _positive_integer("max_depth", max_depth),
            ),
            expected_operation="explain",
        )
        return _operation(envelope, self.builder)

    def discover(self, pattern: str) -> SnarsOperation:
        atom = parse_statement(pattern, pattern=True)
        envelope = self._execute(
            self._gc("discover-record", atom),
            expected_operation="discover",
        )
        return _operation(envelope, self.builder)

    # A goal's event is appended under the session's budget, as every operation's is, and once by
    # its content, as a belief's is.
    # am[implements a-v2rs-snars-budget-1020@5469ea] am[implements a-v2rs-snars-keyed-dedup-1020@85653f]
    def register_goal(
        self,
        statement: str,
        *,
        owner: str,
        kind: str,
        desire: float,
        required: bool,
        source: str,
    ) -> SnarsGoal:
        if kind not in {"individual", "collective"}:
            raise InvalidInputError(
                "Goal kind must be individual or collective."
            )
        atom = parse_statement(statement)
        payload = {
            "statement": self.builder.codec.emit(atom),
            "owner": _nonempty("owner", owner),
            "kind": kind,
            "desire": _probability("desire", desire),
            "required": _boolean("required", required),
            "source": _nonempty("source", source),
        }
        prepared = self.store.prepare_payload("goal", payload)
        duplicate = self._has_event("goal", prepared)
        if not duplicate:
            _event_fragments("goal", prepared, self.builder)
        envelope = self._execute(
            self._gc(
                "goal-record",
                atom,
                self.builder.codec.string(owner),
                self.builder.codec.symbol(kind),
                desire,
                self.builder.codec.symbol(str(required)),
                self.builder.codec.string(source),
            ),
            expected_operation="goal",
            pending=None if duplicate else ("goal", prepared),
        )
        goal = _parse_goal(envelope.payload, self.builder)
        if not duplicate:
            self.store.append_once("goal", prepared, budget=self.budget)
        return goal

    def subgoals(self, statement: str) -> SnarsOperation:
        atom = parse_statement(statement)
        envelope = self._execute(
            self._gc("subgoals-record", atom),
            expected_operation="subgoals",
        )
        return _operation(envelope, self.builder)

    # A what-if writes nothing: no append follows its batch, and parse_counterfactual refuses an
    # answer whose SNARS state after the hypothesis is rolled back differs from the state before it.
    # The store can change meanwhile only by another session's append, which is not the
    # counterfactual's, so the session compares no digest of the whole stream
    # (c-v2rs-what-if-appends-nothing-1020).
    # am[implements a-ev-br-session-1017@c3ddf0] am[implements a-v2rs-kr-session-1020@53ac31]
    # am[rests-on c-v2rs-what-if-appends-nothing-1020@d30172] am[addresses i-v2rs-what-if-false-conflict-1020@8f32af]
    def what_if(
        self,
        hypothesis: str,
        query: str,
        *,
        evidence: Evidence | None = None,
        source: str = "what-if",
        trust: float = 1.0,
        max_depth: int = DEFAULT_PROOF_DEPTH,
    ) -> SnarsCounterfactual:
        hypothesis_atom = parse_statement(hypothesis)
        query_atom = parse_statement(query)
        counts = evidence or DEFAULT_HYPOTHESIS
        options = self.builder.evidence_options(
            positive=counts.positive,
            negative=counts.negative,
            base_rate=counts.base_rate,
            source=source,
            trust=_probability("trust", trust),
        )
        envelope = self._execute(
            self._gc(
                "what-if-record",
                hypothesis_atom,
                options,
                query_atom,
                _positive_integer("max_depth", max_depth),
            ),
            expected_operation="what-if",
        )
        return parse_counterfactual(envelope.payload, self.builder.codec)

    # now is a caller's real number, refused before anything is stored when no finite float holds it.
    # am[implements a-rt-nr-repair-1018@72901e] am[implements a-v2rs-snars-budget-1020@5469ea]
    def temporal(
        self,
        statement: str,
        *,
        now: float,
        budget: int = 8,
        persist: bool = True,
    ) -> SnarsOperation:
        atom = parse_statement(statement)
        payload = {
            "statement": self.builder.codec.emit(atom),
            "now": _real("now", now),
            "budget": _positive_integer("budget", budget),
        }
        pending = None
        if persist:
            prepared = self.store.prepare_payload("temporal", payload)
            _event_fragments("temporal", prepared, self.builder)
            pending = ("temporal", prepared)
        envelope = self._execute(
            self._gc("temporal-record", atom, budget, now),
            expected_operation="temporal",
        )
        if pending is not None:
            self.store.append_prepared(*pending, budget=self.budget)
        return _operation(envelope, self.builder)

    # am[implements a-ev-outcome-evidence@69a360]
    # am[addresses i-ev-outcome-reinflation@b31afa]
    # am[rests-on c-ev-outcome-not-idempotent@ce72f7]
    # am[implements a-ev-br-session-1017@c3ddf0]
    # am[implements a-v2-outcome-sequential-conflict-1020@10212e] am[addresses i-v2-outcome-sequential-conflict-1020@c45e70]
    # am[rests-on c-v2-outcome-early-return-1020@fcd081] am[implements a-v2rs-snars-budget-1020@5469ea]
    # am[implements a-v2rs-kr-session-1020@53ac31]
    def record_outcome(
        self,
        statement: str,
        *,
        evidence: Evidence,
        source: str,
        observation_id: str,
        trust: float = 1.0,
    ) -> SnarsOperation | None:
        """Grade and fuse one observed outcome, once per observation.

        SNARS fuses outcomes with no receipt gate, so the store is the only
        place a repeated observation can be recognised. The outcome recorded
        under an observation_id returns None again and changes nothing, while
        a different statement, evidence, source or trust under it raises
        PersistenceError, both decided by the store's keyed-append rule before
        any batch runs, in a lookup that keeps the session's budget. The same
        holds when another session records the observation while this one
        grades it: the store keys the append, so only one of two racing
        sessions writes.
        Evidence that gives no base rate is fused at SNARS's configured default.
        """

        atom = parse_statement(statement)
        identifier = _nonempty("observation_id", observation_id)
        payload = {
            "statement": self.builder.codec.emit(atom),
            "positive": evidence.positive,
            "negative": evidence.negative,
            "base_rate": evidence.base_rate,
            "source": source,
            "trust": _probability("trust", trust),
            "observation_id": identifier,
        }
        prepared = self.store.prepare_payload("outcome", payload)
        _event_fragments("outcome", prepared, self.builder)
        if self.store.recorded("outcome", prepared, key=identifier, budget=self.budget):
            return None
        envelope = self._execute(
            self._gc(
                "outcome-record",
                atom,
                evidence.positive,
                evidence.negative,
                self.builder.rate(evidence.base_rate),
                self.builder.codec.string(source),
                trust,
            ),
            expected_operation="outcome",
        )
        if self.store.append_prepared("outcome", prepared, key=identifier, budget=self.budget) is None:
            return None
        return _operation(envelope, self.builder)

    # The read keeps the session's budget, as every read of its store does.
    # am[implements a-ev-outcome-evidence@69a360] am[implements a-v2rs-kr-session-1020@53ac31]
    def has_outcome(self, observation_id: str) -> bool:
        """Whether the store already holds an outcome recorded for this observation."""

        return self.store.has_key("outcome", observation_id, budget=self.budget)

    def trust(self) -> SnarsOperation:
        envelope = self._execute(
            self._gc("trust-record"),
            expected_operation="trust",
        )
        return _operation(envelope, self.builder)

    def mine(self, minimum_support: int = 2) -> SnarsOperation:
        envelope = self._execute(
            self._gc(
                "mine-record",
                _positive_integer("minimum_support", minimum_support),
            ),
            expected_operation="mine",
        )
        return _operation(envelope, self.builder)

    def inspect(self) -> SnarsOperation:
        envelope = self._execute(
            self._gc("inspect-record"),
            expected_operation="inspect",
        )
        return _operation(envelope, self.builder)

    def truth(
        self,
        statement: str,
        *,
        threshold: float = 0.5,
    ) -> SnarsOperation:
        atom = parse_statement(statement)
        envelope = self._execute(
            self._gc(
                "truth-record",
                atom,
                _probability("threshold", threshold),
            ),
            expected_operation="truth",
        )
        return _operation(envelope, self.builder)

    # am[implements a-rt-snars-batch-value-1017@0e8147]
    def control(self, budget: int = 8) -> SnarsOperation:
        envelope = self._execute(
            self._gc(
                "control-record",
                _positive_integer("budget", budget),
            ),
            expected_operation="control",
            includes={"policy"},
        )
        return _operation(envelope, self.builder)

    # am[implements a-rt-snars-batch-value-1017@0e8147]
    def structural(self) -> SnarsOperation:
        envelope = self._execute(
            self._gc("structural-record"),
            expected_operation="structural",
            includes={"policy"},
        )
        return _operation(envelope, self.builder)

    # A marginal seeds the term's prior at base_rate, or at SNARS's configured default when none is
    # given; the other kinds take no rate.
    # am[implements a-ev-br-session-1017@c3ddf0] am[rests-on c-ev-transform-default-is-prior-1017@78ab4e]
    def transform(
        self,
        kind: str,
        statement: str,
        *,
        other_statement: str | None = None,
        base_rate: float | None = None,
    ) -> SnarsOperation:
        if kind not in {"marginal", "similarity", "symmetric", "disjunction"}:
            raise InvalidInputError(
                "Structural transform kind is unsupported.",
                details={"kind": kind},
            )
        first = parse_statement(statement)
        if kind == "disjunction":
            second = parse_statement(
                _nonempty("other_statement", other_statement)
            )
        else:
            second = self.builder.codec.symbol("NoStatement")
        envelope = self._execute(
            self._gc(
                "transform-record",
                self.builder.codec.symbol(kind),
                first,
                second,
                self.builder.rate(None if base_rate is None else _probability("base_rate", base_rate)),
            ),
            expected_operation="transform",
        )
        return _operation(envelope, self.builder)

    # am[implements a-rt-snars-batch-value-1017@0e8147]
    def compiled_prove(self, statement: str) -> SnarsOperation:
        atom = parse_statement(statement)
        envelope = self._execute(
            self._gc("compiled-prove-record", atom),
            expected_operation="compiled-prove",
            includes={"policy"},
        )
        return _operation(envelope, self.builder)

    # The guard runs with the features the session's other operations have, and the guard module.
    # am[implements a-rt-snars-batch-value-1017@0e8147]
    # am[implements a-integrate-guard-metta-build-1019@e688cb]
    def guard(
        self,
        goal: str,
        *,
        rules: tuple[str, ...] = (),
    ) -> SnarsOperation:
        """Query an s(CASP) program written as structured MeTTa expressions.

        A result reports support in one stable model, not truth in every model.
        Rules apply only within this speculative batch. Solver errors propagate.
        """
        if not isinstance(rules, tuple) or not all(
            isinstance(rule, str) and rule.strip() for rule in rules
        ):
            raise InvalidInputError(
                "Guard rules must be a tuple of nonempty strings."
            )
        effects = tuple(
            self.builder.codec.emit(
                self.builder.codec.expression(
                    "sn",
                    self.builder.codec.symbol("guard-rule!"),
                    self.builder.codec.expression("quote", parse_guard(rule)),
                )
            )
            for rule in rules
        )
        envelope = self._execute(
            self._gc(
                "guard-record",
                self.builder.codec.expression("quote", parse_guard(goal)),
            ),
            expected_operation="guard",
            extra_effects=effects,
            includes=self._default_includes | {"guard"},
        )
        return _operation(envelope, self.builder)

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> SnarsSession:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    # A batch replays every stored event except the readings of texts this session did not read:
    # a store keeps every text it ever read, and a decision on one request must believe nothing
    # another said (c-batch-replays-every-ingestion-1017).
    # Time: E x R payload comparisons, E = stored events, R = texts this session read.
    # am[implements a-jev-session-reads-1017@3d73d9] am[implements a-rt-snars-batch-speculative-1017@451056]
    # am[implements a-integrate-ecan-forward-query-interface-1017] am[implements a-rt-rbs-session-budget-1018@8c3da2]
    # am[implements a-v2rs-events-budget-1020@a8933d]
    def _execute(
        self,
        operation: Any,
        *,
        expected_operation: str,
        pending: tuple[str, Mapping[str, Any]] | None = None,
        includes: Iterable[str] | None = None,
        extra_effects: tuple[str, ...] = (),
    ) -> ProtocolEnvelope:
        facts: list[str] = []
        effects: list[str] = []
        for event in self.store.events(budget=self.budget):
            if event.kind == "ingest_text" and event.payload not in self._read:
                continue
            fragments = _event_fragments(event.kind, event.payload, self.builder)
            facts.extend(fragments.facts)
            effects.extend(fragments.effects)
        if pending is not None:
            fragments = _event_fragments(pending[0], pending[1], self.builder)
            facts.extend(fragments.facts)
            effects.extend(fragments.effects)
        effects.extend(extra_effects)
        batch = self.builder.batch(
            operation,
            facts=facts,
            effects=effects,
            includes=self._default_includes if includes is None else includes,
        )
        return parse_protocol_output(
            self._run(batch, self.budget),
            self.builder.codec,
            expected_operation=expected_operation,
        )

    # The features an operation that names none runs with: the policy unless the session was made
    # without it.
    # am[implements a-rt-snars-batch-value-1017@0e8147]
    @property
    def _default_includes(self) -> frozenset[str]:
        return frozenset({"policy"}) if self.include_goalchainer_policy else frozenset()

    def _gc(self, name: str, *arguments: Any) -> list[Any]:
        return self.builder.codec.expression(
            "gc",
            self.builder.codec.symbol(name),
            *arguments,
        )

    # Whether the store holds this event, read under the session's budget as every replay read is.
    # am[implements a-v2rs-events-budget-1020@a8933d]
    def _has_event(self, kind: str, payload: Mapping[str, Any]) -> bool:
        return any(
            event.kind == kind and event.payload == payload
            for event in self.store.events(budget=self.budget)
        )


# A threshold the caller gave, or SNARS's own decision threshold read inside the batch, so an
# omitted threshold stays distinct from an explicit 0.
# am[implements a-rt-ob-session-1017@f1468f]
def _threshold(codec: Any, threshold: float | None) -> Any:
    if threshold is None:
        return codec.expression("sn", codec.symbol("config"), codec.symbol("decision-threshold"))
    return _probability("threshold", threshold)


# A track record projected afresh from counts its caller attributes: the opinion SNARS gives them
# at its default rate and the one cut of it, in a batch with no events, so nothing is believed
# that a later receipt for the same attempt would have to withdraw.
# Time: one small batch on the base world under the caller's budget.
# am[implements a-rt-ob-negation-track-1017@a1a80d] am[rests-on c-rt-pm-interface-shape-v6-1017@ec7b8c]
# am[implements a-rt-rb-one-budget-1018@550ffd]
def track(
    positive: float,
    negative: float,
    *,
    budget: RunBudget,
    threshold: float | None = None,
) -> SnarsTrack:
    """Answer the opinion SNARS gives `positive` and `negative` counts and its condition."""

    caller_budget(budget, "track")
    try:
        counts = Evidence(positive, negative)
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("track takes finite non-negative counts.", details={"error": str(exc)}) from exc
    builder = SnarsProgramBuilder()
    codec = builder.codec
    operation = codec.expression("gc", codec.symbol("track-record"), counts.positive, counts.negative,
                                 _threshold(codec, threshold))
    lines = run_snars_batch(builder.batch(operation), budget=budget).output_lines
    return parse_track(parse_protocol_output(lines, codec, expected_operation="track").payload, codec)


# A stored event's effect. A belief or outcome stored without a base rate replays without one, so
# SNARS reads it at the default it is configured with when the event replays.
# am[implements a-ev-br-session-1017@c3ddf0]
def _event_fragments(
    kind: str,
    payload: Mapping[str, Any],
    builder: SnarsProgramBuilder,
) -> ProgramFragments:
    if kind == "ingest_text":
        facts = _string_sequence(payload, "facts")
        effects = _string_sequence(payload, "effects")
        return ProgramFragments(facts, effects)
    if kind == "belief":
        statement = parse_statement(_string(payload, "statement"))
        effect = builder.belief_effect(
            statement,
            positive=_number(payload, "positive"),
            negative=_number(payload, "negative"),
            base_rate=_optional_number(payload, "base_rate"),
            source=_string(payload, "source"),
            trust=_number(payload, "trust"),
            occurrence=_optional_number(payload, "occurrence"),
        )
        return ProgramFragments(effects=(effect,))
    if kind == "goal":
        statement = parse_statement(_string(payload, "statement"))
        return ProgramFragments(
            effects=(builder.goal_effect(statement, _number(payload, "desire")),)
        )
    if kind == "temporal":
        return ProgramFragments(
            effects=(
                builder.codec.emit(
                    builder.codec.expression(
                        "sn",
                        builder.codec.symbol("temporal!"),
                        _positive_integer("budget", payload.get("budget")),
                        _number(payload, "now"),
                    )
                ),
            )
        )
    if kind == "outcome":
        statement = parse_statement(_string(payload, "statement"))
        sid = builder.codec.expression(
            "sn",
            builder.codec.symbol("sid"),
            builder.codec.expression(
                "sn",
                builder.codec.symbol("canon"),
                statement,
            ),
        )
        return ProgramFragments(
            effects=(
                builder.codec.emit(
                    builder.codec.expression(
                        "sn",
                        builder.codec.symbol("outcome!"),
                        sid,
                        _number(payload, "positive"),
                        _number(payload, "negative"),
                        builder.rate(_optional_number(payload, "base_rate")),
                        builder.codec.string(_string(payload, "source")),
                        _number(payload, "trust"),
                    )
                ),
            )
        )
    raise PersistenceError(
        "SNARS event kind is unsupported.",
        details={"kind": kind},
    )


def _operation(
    envelope: ProtocolEnvelope,
    builder: SnarsProgramBuilder,
) -> SnarsOperation:
    return SnarsOperation(
        operation=envelope.operation,
        payload=atom_to_python(envelope.payload, builder.codec),
        raw=builder.codec.emit(envelope.raw),
    )


def _parse_goal(payload: Any, builder: SnarsProgramBuilder) -> SnarsGoal:
    codec = builder.codec
    if not isinstance(payload, list) or len(payload) != 9:
        raise ProtocolError("Goal protocol record has the wrong arity.")
    values = atom_to_python(payload, codec)
    if values[0] != "goal":
        raise ProtocolError("Goal protocol record has the wrong tag.")
    return SnarsGoal(
        goal_id=str(values[1]),
        canonical_statement=codec.emit(payload[2]),
        owner=str(values[3]),
        kind=str(values[4]),
        desire=float(values[5]),
        required=_protocol_bool(values[6]),
        source=str(values[7]),
    )


def _protocol_bool(value: Any) -> bool:
    if value in (True, "True", "true"):
        return True
    if value in (False, "False", "false"):
        return False
    raise ProtocolError(
        "Protocol boolean has an invalid value.",
        details={"value": value},
    )


def _string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PersistenceError(
            "SNARS event string field is invalid.",
            details={"field": key},
        )
    return value


def _string_sequence(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PersistenceError(
            "SNARS event string-list field is invalid.",
            details={"field": key},
        )
    return tuple(value)


# A stored event's number is one a finite float holds, as the event store wrote it; anything else,
# an integer beyond the float range included, is a store this cannot read.
# am[implements a-rt-nr-repair-1018@72901e] am[rests-on c-rt-nr-probe-bfd71102-1018@029356]
def _number(payload: Mapping[str, Any], key: str) -> float:
    value = finite_float(payload.get(key))
    if value is None:
        raise PersistenceError(
            "SNARS event numeric field is invalid.",
            details={"field": key},
        )
    return value


def _optional_number(payload: Mapping[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    return _number(payload, key)


def _nonempty(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"{name} must be nonempty.")
    return value


# A caller's real number: one a finite float holds, never a bool or a numeric string, which a bare
# float() would have taken as 1.0 or parsed.
# am[implements a-rt-nr-repair-1018@72901e] am[rests-on c-rt-nr-temporal-now-unvalidated-1018@0e2337]
def _real(name: str, value: Any) -> float:
    result = finite_float(value)
    if result is None:
        raise InvalidInputError(f"{name} must be a finite real number.")
    return result


# am[implements a-rt-nr-repair-1018@72901e] am[rests-on c-rt-nr-probe-bfd71102-1018@029356]
def _probability(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidInputError(f"{name} must be a real number.")
    result = finite_float(value)
    if result is None or not 0.0 <= result <= 1.0:
        raise InvalidInputError(f"{name} must be in [0, 1].")
    return result


def _positive_integer(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidInputError(f"{name} must be a positive integer.")
    return value


def _boolean(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise InvalidInputError(f"{name} must be a boolean.")
    return value


__all__ = [
    "DEFAULT_PROOF_DEPTH",
    "DEFAULT_PROOF_SIZE",
    "SnarsOperation",
    "SnarsSession",
    "track",
]

"""High-level sessions over the native Mettabase SNARS world."""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import CandidateAction, EvidenceProjection
from .snars_models import (
    EvidenceCounts,
    SnarsActionAssessment,
    SnarsBelief,
    SnarsCounterfactual,
    SnarsGoal,
    SnarsInvalidInputError,
    SnarsPersistenceError,
    SnarsProtocolError,
    SnarsRequestContext,
)
from .snars_program import ProgramFragments, SnarsProgramBuilder
from .snars_protocol import (
    ProtocolEnvelope,
    atom_to_python,
    parse_assessment,
    parse_belief,
    parse_counterfactual,
    parse_protocol_output,
    parse_request_context,
)
from .snars_runtime import SnarsRuntime
from .snars_store import Redactor, SnarsEventStore

DEFAULT_PROOF_DEPTH = 4
DEFAULT_PROOF_SIZE = 12


@dataclass(frozen=True, slots=True)
class SnarsOperation:
    """A validated protocol response and its JSON-compatible projection."""

    operation: str
    payload: Any
    raw: str


class SnarsActionReasoner:
    """Expose native SNARS action beliefs to the existing decision engine."""

    source = "mettabase-snars-on-petta"
    native_snars = True

    def __init__(
        self,
        assessments: tuple[SnarsActionAssessment, ...],
        deontic_by_action: Mapping[str, str],
        *,
        session: SnarsSession | None = None,
    ) -> None:
        self._assessments = {row.action_id: row for row in assessments}
        self._deontic = dict(deontic_by_action)
        self._session = session
        self.score_audit: dict[str, Any] | None = None

    def project(self, action: CandidateAction) -> EvidenceProjection:
        try:
            assessment = self._assessments[action.id]
        except KeyError as exc:
            raise SnarsProtocolError(
                "SNARS assessment omitted a candidate action.",
                details={"action_id": action.id},
            ) from exc
        belief = assessment.acceptable
        return EvidenceProjection(
            strength=belief.opinion.expectation,
            confidence=1.0 - belief.opinion.uncertainty,
            source=self.source,
            projection=belief.canonical_statement,
            proofs=tuple(
                f"{proof.kind}: {proof.conclusion}" for proof in belief.proofs
            ),
            deontic=self._deontic.get(action.id, "unregulated"),
            expectation=belief.opinion.expectation,
            opinion=belief.opinion,
            counts=belief.evidence,
            receipts=belief.receipts,
            native_proofs=belief.proofs,
            sources=belief.sources,
            conflict_degree=assessment.conflict_degree,
        )

    def score_rows(
        self,
        rows: list[Mapping[str, Any]],
    ) -> dict[str, tuple[float, str, str]]:
        if self._session is None:
            raise SnarsProtocolError(
                "Native SNARS scoring requires its live session."
            )
        operation = self._session.score(rows)
        payload = operation.payload
        if (
            not isinstance(payload, list)
            or len(payload) != 4
            or payload[0] != "ranking"
            or not isinstance(payload[1], list)
        ):
            raise SnarsProtocolError("SNARS score result has the wrong shape.")
        verdicts: dict[str, tuple[float, str, str]] = {}
        for row in payload[1]:
            if (
                not isinstance(row, list)
                or len(row) != 12
                or row[0] != "DecisionRow"
            ):
                raise SnarsProtocolError("SNARS decision row has the wrong shape.")
            action_id = str(row[1])
            if action_id in verdicts:
                raise SnarsProtocolError(
                    "SNARS score result contains a duplicate action.",
                    details={"action_id": action_id},
                )
            verdicts[action_id] = (float(row[3]), str(row[4]), str(row[11]))
        expected_ids = {str(row["action_id"]) for row in rows}
        if set(verdicts) != expected_ids:
            raise SnarsProtocolError(
                "SNARS score result does not match the candidate actions.",
                details={
                    "expected": sorted(expected_ids),
                    "received": sorted(verdicts),
                },
            )
        tied = payload[2]
        automatic = payload[3]
        if (
            not isinstance(tied, list)
            or len(tied) != 2
            or tied[0] != "tied"
            or not isinstance(tied[1], list)
            or not isinstance(automatic, list)
            or len(automatic) != 2
            or automatic[0] != "automatic"
        ):
            raise SnarsProtocolError("SNARS score audit has the wrong shape.")
        self.score_audit = {
            "order": [str(row[1]) for row in payload[1]],
            "tied": [str(action_id) for action_id in tied[1]],
            "automatic": _protocol_bool(automatic[1]),
        }
        return verdicts


class SnarsSession:
    """Replayable SNARS state without a long-running daemon."""

    def __init__(
        self,
        runtime: SnarsRuntime,
        store: SnarsEventStore,
        *,
        include_goalchainer_policy: bool = True,
    ) -> None:
        if store.mettabase_commit != runtime.diagnostics.mettabase_commit:
            raise SnarsPersistenceError(
                "SNARS store and runtime use different Mettabase commits.",
                details={
                    "store": store.mettabase_commit,
                    "runtime": runtime.diagnostics.mettabase_commit,
                },
            )
        self.runtime = runtime
        self.store = store
        self.builder = SnarsProgramBuilder(runtime)
        self.include_goalchainer_policy = include_goalchainer_policy
        self._last_ingestion_payload: dict[str, Any] | None = None

    @classmethod
    def ephemeral(cls, runtime: SnarsRuntime) -> SnarsSession:
        return cls(
            runtime,
            SnarsEventStore.memory(
                mettabase_commit=runtime.diagnostics.mettabase_commit
            ),
        )

    @classmethod
    def persistent(
        cls,
        runtime: SnarsRuntime,
        path: str | Path,
        *,
        redactor: Redactor | None = None,
    ) -> SnarsSession:
        return cls(
            runtime,
            SnarsEventStore(
                path,
                mettabase_commit=runtime.diagnostics.mettabase_commit,
                redactor=redactor,
            ),
        )

    def ingest_text(
        self,
        text: str,
        *,
        source: str = "user",
        trust: float = 1.0,
        parser_name: str = "alphabeta",
        lang: str = "en",
    ) -> SnarsOperation:
        fragments = self.builder.text_ingestion(
            text,
            source=source,
            trust=trust,
            parser_name=parser_name,
            lang=lang,
        )
        payload = {
            "text": text,
            "source": source,
            "trust": trust,
            "parser_name": parser_name,
            "lang": lang,
            "facts": list(fragments.facts),
            "effects": list(fragments.effects),
        }
        prepared = self.store.prepare_payload("ingest_text", payload)
        self._last_ingestion_payload = dict(prepared)
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
        self.store.append_prepared("ingest_text", prepared)
        return _operation(envelope, self.builder)

    @property
    def last_ingestion_payload(self) -> dict[str, Any]:
        """Return the prepared event for the latest ingestion request."""

        if self._last_ingestion_payload is None:
            raise SnarsProtocolError("No text has been ingested in this session.")
        return deepcopy(self._last_ingestion_payload)

    def state_payload(self) -> dict[str, Any]:
        """Describe the current replay store for CLI and decision reports."""

        return {
            "kind": "persistent" if self.store.persistent else "ephemeral",
            "path": str(self.store.path) if self.store.path else None,
            "digest": self.store.state_digest(),
            "event_count": len(self.store.events()),
        }

    def believe(
        self,
        statement: str,
        *,
        evidence: EvidenceCounts | None = None,
        source: str = "caller",
        trust: float = 1.0,
        occurrence: float | None = None,
        proof_depth: int = DEFAULT_PROOF_DEPTH,
    ) -> SnarsBelief:
        atom = self.builder.codec.statement(statement)
        counts = evidence or EvidenceCounts(1.0, 0.0, 0.5)
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
            pending=("belief", prepared),
        )
        belief = parse_belief(envelope.payload, self.builder.codec)
        self.store.append_prepared("belief", prepared)
        return belief

    def belief(
        self,
        statement: str,
        *,
        proof_depth: int = DEFAULT_PROOF_DEPTH,
    ) -> SnarsBelief:
        atom = self.builder.codec.statement(statement)
        operation = self._gc(
            "belief-record",
            self.builder.codec.symbol("belief"),
            atom,
            _positive_integer("proof_depth", proof_depth),
        )
        envelope = self._execute(operation, expected_operation="belief")
        return parse_belief(envelope.payload, self.builder.codec)

    def ask(self, pattern: str) -> SnarsOperation:
        atom = self.builder.codec.statement(pattern, pattern=True)
        envelope = self._execute(
            self._gc("ask-record", atom),
            expected_operation="ask",
        )
        return _operation(envelope, self.builder)

    def prove(
        self,
        statement: str,
        *,
        max_depth: int = DEFAULT_PROOF_DEPTH,
        max_size: int = DEFAULT_PROOF_SIZE,
    ) -> SnarsOperation:
        atom = self.builder.codec.statement(statement)
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
        atom = self.builder.codec.statement(statement)
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
        atom = self.builder.codec.statement(pattern, pattern=True)
        envelope = self._execute(
            self._gc("discover-record", atom),
            expected_operation="discover",
        )
        return _operation(envelope, self.builder)

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
            raise SnarsInvalidInputError(
                "Goal kind must be individual or collective."
            )
        atom = self.builder.codec.statement(statement)
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
            self.store.append_prepared("goal", prepared)
        return goal

    def subgoals(self, statement: str) -> SnarsOperation:
        atom = self.builder.codec.statement(statement)
        envelope = self._execute(
            self._gc("subgoals-record", atom),
            expected_operation="subgoals",
        )
        return _operation(envelope, self.builder)

    def what_if(
        self,
        hypothesis: str,
        query: str,
        *,
        evidence: EvidenceCounts | None = None,
        source: str = "what-if",
        trust: float = 1.0,
        max_depth: int = DEFAULT_PROOF_DEPTH,
    ) -> SnarsCounterfactual:
        hypothesis_atom = self.builder.codec.statement(hypothesis)
        query_atom = self.builder.codec.statement(query)
        counts = evidence or EvidenceCounts(8.0, 0.0, 0.5)
        options = [
            [
                self.builder.codec.symbol("evidence"),
                counts.positive,
                counts.negative,
            ],
            [self.builder.codec.symbol("rate"), counts.base_rate],
            [self.builder.codec.symbol("source"), self.builder.codec.string(source)],
            [self.builder.codec.symbol("trust"), _probability("trust", trust)],
        ]
        event_digest = self.store.state_digest()
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
        result = parse_counterfactual(envelope.payload, self.builder.codec)
        if self.store.state_digest() != event_digest:
            raise SnarsProtocolError(
                "Counterfactual changed the persistent event stream."
            )
        return result

    def temporal(
        self,
        statement: str,
        *,
        now: float,
        budget: int = 8,
        persist: bool = True,
    ) -> SnarsOperation:
        atom = self.builder.codec.statement(statement)
        payload = {
            "statement": self.builder.codec.emit(atom),
            "now": float(now),
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
            self.store.append_prepared(*pending)
        return _operation(envelope, self.builder)

    def record_outcome(
        self,
        statement: str,
        *,
        evidence: EvidenceCounts,
        source: str,
        trust: float = 1.0,
    ) -> SnarsOperation:
        atom = self.builder.codec.statement(statement)
        payload = {
            "statement": self.builder.codec.emit(atom),
            "positive": evidence.positive,
            "negative": evidence.negative,
            "base_rate": evidence.base_rate,
            "source": source,
            "trust": _probability("trust", trust),
        }
        prepared = self.store.prepare_payload("outcome", payload)
        _event_fragments("outcome", prepared, self.builder)
        envelope = self._execute(
            self._gc(
                "outcome-record",
                atom,
                evidence.positive,
                evidence.negative,
                evidence.base_rate,
                self.builder.codec.string(source),
                trust,
            ),
            expected_operation="outcome",
        )
        self.store.append_prepared("outcome", prepared)
        return _operation(envelope, self.builder)

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
        atom = self.builder.codec.statement(statement)
        envelope = self._execute(
            self._gc(
                "truth-record",
                atom,
                _probability("threshold", threshold),
            ),
            expected_operation="truth",
        )
        return _operation(envelope, self.builder)

    def control(self, budget: int = 8) -> SnarsOperation:
        envelope = self._execute(
            self._gc(
                "control-record",
                _positive_integer("budget", budget),
            ),
            expected_operation="control",
            include_policy=True,
        )
        return _operation(envelope, self.builder)

    def structural(self) -> SnarsOperation:
        envelope = self._execute(
            self._gc("structural-record"),
            expected_operation="structural",
            include_policy=True,
        )
        return _operation(envelope, self.builder)

    def transform(
        self,
        kind: str,
        statement: str,
        *,
        other_statement: str | None = None,
        base_rate: float = 0.5,
    ) -> SnarsOperation:
        if kind not in {"marginal", "similarity", "symmetric", "disjunction"}:
            raise SnarsInvalidInputError(
                "Structural transform kind is unsupported.",
                details={"kind": kind},
            )
        first = self.builder.codec.statement(statement)
        if kind == "disjunction":
            second = self.builder.codec.statement(
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
                _probability("base_rate", base_rate),
            ),
            expected_operation="transform",
        )
        return _operation(envelope, self.builder)

    def compiled_prove(self, statement: str) -> SnarsOperation:
        atom = self.builder.codec.statement(statement)
        envelope = self._execute(
            self._gc("compiled-prove-record", atom),
            expected_operation="compiled-prove",
            include_policy=True,
        )
        return _operation(envelope, self.builder)

    def guard(
        self,
        goal: str,
        *,
        rules: tuple[str, ...] = (),
    ) -> SnarsOperation:
        if not isinstance(rules, tuple) or not all(
            isinstance(rule, str) and rule.strip() for rule in rules
        ):
            raise SnarsInvalidInputError(
                "Guard rules must be a tuple of nonempty strings."
            )
        effects = tuple(
            self.builder.codec.emit(
                self.builder.codec.expression(
                    "sn",
                    self.builder.codec.symbol("guard-rule!"),
                    self.builder.codec.string(rule),
                )
            )
            for rule in rules
        )
        envelope = self._execute(
            self._gc(
                "guard-record",
                self.builder.codec.string(_nonempty("goal", goal)),
            ),
            expected_operation="guard",
            extra_effects=effects,
            include_guard=True,
        )
        return _operation(envelope, self.builder)

    def assess_actions(self) -> tuple[SnarsActionAssessment, ...]:
        envelope = self._execute(
            self._gc("assess-record"),
            expected_operation="assess",
            include_policy=True,
        )
        return parse_assessment(envelope.payload, self.builder.codec)

    def request_context(self) -> SnarsRequestContext:
        envelope = self._execute(
            self._gc("context-record"),
            expected_operation="context",
            include_policy=True,
        )
        return parse_request_context(envelope.payload, self.builder.codec)

    def score(
        self,
        rows: list[Mapping[str, Any]],
        *,
        tie_epsilon: float = 1e-12,
    ) -> SnarsOperation:
        if not rows:
            raise SnarsInvalidInputError("At least one action score row is required.")
        atoms = [
            self.builder.codec.expression(
                "ActionScore",
                self.builder.codec.string(_nonempty("action_id", row.get("action_id"))),
                _nonnegative_integer("order", row.get("order")),
                self.builder.codec.symbol(_nonempty("deontic", row.get("deontic"))),
                _probability("expectation", row.get("expectation")),
                _probability("goal_score", row.get("goal_score")),
                _probability("individual_score", row.get("individual_score")),
                _probability("collective_score", row.get("collective_score")),
                _motivation_atom(row.get("motivation"), self.builder),
                _nonnegative_integer(
                    "missing_required_count",
                    row.get("missing_required_count"),
                ),
            )
            for row in rows
        ]
        if (
            isinstance(tie_epsilon, bool)
            or not isinstance(tie_epsilon, int | float)
            or tie_epsilon < 0
        ):
            raise SnarsInvalidInputError("tie_epsilon must be nonnegative.")
        envelope = self._execute(
            self._gc("score-record", atoms, float(tie_epsilon)),
            expected_operation="score",
            include_policy=False,
        )
        return _operation(envelope, self.builder)

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> SnarsSession:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _execute(
        self,
        operation: Any,
        *,
        expected_operation: str,
        pending: tuple[str, Mapping[str, Any]] | None = None,
        include_policy: bool | None = None,
        include_guard: bool = False,
        extra_effects: tuple[str, ...] = (),
    ) -> ProtocolEnvelope:
        facts: list[str] = []
        effects: list[str] = []
        for event in self.store.events():
            fragments = _event_fragments(event.kind, event.payload, self.builder)
            facts.extend(fragments.facts)
            effects.extend(fragments.effects)
        if pending is not None:
            fragments = _event_fragments(pending[0], pending[1], self.builder)
            facts.extend(fragments.facts)
            effects.extend(fragments.effects)
        effects.extend(extra_effects)
        program = self.builder.batch(
            operation,
            facts=facts,
            effects=effects,
            include_policy=(
                self.include_goalchainer_policy
                if include_policy is None
                else include_policy
            ),
            include_guard=include_guard,
        )
        result = self.runtime.run_batch(program)
        return parse_protocol_output(
            result.output_lines,
            self.builder.codec,
            expected_operation=expected_operation,
        )

    def _gc(self, name: str, *arguments: Any) -> list[Any]:
        return self.builder.codec.expression(
            "gc",
            self.builder.codec.symbol(name),
            *arguments,
        )

    def _has_event(self, kind: str, payload: Mapping[str, Any]) -> bool:
        return any(
            event.kind == kind and event.payload == payload
            for event in self.store.events()
        )


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
        statement = builder.codec.statement(_string(payload, "statement"))
        effect = builder.belief_effect(
            statement,
            positive=_number(payload, "positive"),
            negative=_number(payload, "negative"),
            base_rate=_number(payload, "base_rate"),
            source=_string(payload, "source"),
            trust=_number(payload, "trust"),
            occurrence=_optional_number(payload, "occurrence"),
        )
        return ProgramFragments(effects=(effect,))
    if kind == "goal":
        statement = builder.codec.statement(_string(payload, "statement"))
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
        statement = builder.codec.statement(_string(payload, "statement"))
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
                        _number(payload, "base_rate"),
                        builder.codec.string(_string(payload, "source")),
                        _number(payload, "trust"),
                    )
                ),
            )
        )
    raise SnarsPersistenceError(
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
        raise SnarsProtocolError("Goal protocol record has the wrong arity.")
    values = atom_to_python(payload, codec)
    if values[0] != "goal":
        raise SnarsProtocolError("Goal protocol record has the wrong tag.")
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
    raise SnarsProtocolError(
        "Protocol boolean has an invalid value.",
        details={"value": value},
    )


def _string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SnarsPersistenceError(
            "SNARS event string field is invalid.",
            details={"field": key},
        )
    return value


def _string_sequence(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SnarsPersistenceError(
            "SNARS event string-list field is invalid.",
            details={"field": key},
        )
    return tuple(value)


def _number(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SnarsPersistenceError(
            "SNARS event numeric field is invalid.",
            details={"field": key},
        )
    return float(value)


def _optional_number(payload: Mapping[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    return _number(payload, key)


def _nonempty(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SnarsInvalidInputError(f"{name} must be nonempty.")
    return value


def _probability(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SnarsInvalidInputError(f"{name} must be a real number.")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise SnarsInvalidInputError(f"{name} must be in [0, 1].")
    return result


def _positive_integer(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SnarsInvalidInputError(f"{name} must be a positive integer.")
    return value


def _boolean(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise SnarsInvalidInputError(f"{name} must be a boolean.")
    return value


def _nonnegative_integer(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SnarsInvalidInputError(f"{name} must be a nonnegative integer.")
    return value


def _motivation_atom(value: Any, builder: SnarsProgramBuilder) -> list[Any]:
    if value is None:
        return builder.codec.expression("NoMotivation")
    return builder.codec.expression(
        "Motivation",
        _probability("motivation", value),
    )


__all__ = [
    "DEFAULT_PROOF_DEPTH",
    "DEFAULT_PROOF_SIZE",
    "SnarsActionReasoner",
    "SnarsOperation",
    "SnarsSession",
]

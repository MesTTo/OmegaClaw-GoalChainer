"""HyperBase-ready structured propositions for GoalChainer."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .evidence import IncidentEvidence, extract_evidence
from .ontology import OntologyContext

_TOKEN_RE = re.compile(r"[^a-z0-9]+")
STRUCTURED_ENGLISH_SYSTEM_PROMPT = """Rewrite the natural-language request into clear structured English propositions before tool use.
Write one proposition per sentence.
Use one concrete subject, one predicate, and one object or complement.
Avoid pronouns and vague references.
Preserve domain terms from the request.
Keep observations, norms, and recommendations in separate propositions.
Send the propositions to HyperBase first, then send the HyperBase projection to the native MeTTa/NAL reasoner."""


@dataclass(frozen=True)
class StructuredProposition:
    id: str
    sentence: str
    predicate: str
    subject: str
    object: str
    edge: str
    tree: str
    facts: tuple[str, ...]
    source: str
    ontology_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sentence": self.sentence,
            "predicate": self.predicate,
            "subject": self.subject,
            "object": self.object,
            "edge": self.edge,
            "tree": self.tree,
            "facts": list(self.facts),
            "source": self.source,
            "ontology_hint": self.ontology_hint,
        }


def build_hyperbase_packet(
    request: str,
    ontology: OntologyContext | None = None,
) -> dict[str, Any]:
    evidence = extract_evidence(request)
    propositions = incident_propositions(request)
    reasoner = _native_reasoner_payload(propositions, evidence)
    return {
        "contract": hyperbase_contract(),
        "structured_english_prompt": structured_english_prompt(),
        "structured_english": [proposition.sentence for proposition in propositions],
        "propositions": [proposition.to_dict() for proposition in propositions],
        "metta_program": [
            fact for proposition in propositions for fact in proposition.facts
        ],
        "ontology_grounding": _ontology_grounding(ontology),
        "evidence": evidence.to_dict(),
        "reasoner": reasoner,
    }


def hyperbase_contract() -> dict[str, Any]:
    return {
        "purpose": "structured propositions that HyperBase can translate into SH trees",
        "rules": [
            "write one proposition per sentence",
            "use concrete subject, predicate, and object or complement",
            "avoid pronouns and vague references",
            "preserve domain words from the request",
            "keep normative decisions separate from observed facts",
        ],
        "primary_forms": [
            '(edge/Pv.so subject/Cc object/Cc)',
            '(sh (tag P v so ()) "predicate" (args ((arg s ...) (arg o ...))))',
            "(hb tree EDGE_ID SH_TREE)",
        ],
    }


def structured_english_prompt() -> str:
    return STRUCTURED_ENGLISH_SYSTEM_PROMPT


def incident_propositions(request: str) -> tuple[StructuredProposition, ...]:
    rows: list[StructuredProposition] = []
    contained_items = [item for item in restricted_items(request) if item != "raw logs"]
    if not contained_items:
        contained_items = ["identifiable user data"]
    for index, item in enumerate(contained_items, start=1):
        rows.append(
            _proposition(
                prop_id=f"incident-pii-{index}",
                sentence=f"Raw incident logs contain {item}.",
                predicate="contain",
                edge_predicate="contains",
                subject="raw incident logs",
                object_=item,
                source="request",
            )
        )
    rows.extend(
        [
            _proposition(
                prop_id="incident-risk-1",
                sentence="Publishing raw incident logs exposes identifiable user data.",
                predicate="expose",
                edge_predicate="exposes",
                subject="publishing raw incident logs",
                object_="identifiable user data",
                source="goalchainer",
            ),
            _proposition(
                prop_id="incident-control-1",
                sentence="The redacted summary protects privacy.",
                predicate="protect",
                edge_predicate="protects",
                subject="redacted summary",
                object_="privacy",
                source="goalchainer",
            ),
            _proposition(
                prop_id="incident-control-2",
                sentence="The redacted summary supports responders.",
                predicate="support",
                edge_predicate="supports",
                subject="redacted summary",
                object_="responders",
                source="goalchainer",
            ),
            _proposition(
                prop_id="incident-control-3",
                sentence="Holding the external update protects privacy.",
                predicate="protect",
                edge_predicate="protects",
                subject="holding external update",
                object_="privacy",
                source="goalchainer",
            ),
            _proposition(
                prop_id="incident-time-1",
                sentence="Security review happens before verified customer update.",
                predicate="before",
                edge_predicate="before",
                subject="security review",
                object_="verified customer update",
                source="goalchainer",
                ontology_hint="COLORE timepoints/lp_ordering licenses before transitivity",
            ),
        ]
    )
    return tuple(rows)


def make_proposition(
    *,
    prop_id: str,
    sentence: str,
    predicate: str,
    subject: str,
    object_: str,
    source: str,
    edge_predicate: str | None = None,
    ontology_hint: str = "",
) -> StructuredProposition:
    return _proposition(
        prop_id=prop_id,
        sentence=sentence,
        predicate=predicate,
        edge_predicate=edge_predicate or predicate,
        subject=subject,
        object_=object_,
        source=source,
        ontology_hint=ontology_hint,
    )


def restricted_items(request: str) -> list[str]:
    items = list(extract_evidence(request).sensitive_categories)
    return items or ["raw evidence that may identify users or expose systems"]


def _proposition(
    *,
    prop_id: str,
    sentence: str,
    predicate: str,
    edge_predicate: str,
    subject: str,
    object_: str,
    source: str,
    ontology_hint: str = "",
) -> StructuredProposition:
    subject_edge = _edge_atom(subject)
    object_edge = _edge_atom(object_)
    connector = f"{_token(edge_predicate)}/Pv.so"
    edge = f"({connector} {subject_edge} {object_edge})"
    tree = _tree(edge_predicate, subject, object_)
    facts = (
        _hb_fact("edge", prop_id, edge),
        _hb_fact("type", prop_id, "predicate"),
        _hb_fact("tree", prop_id, tree),
        _hb_fact("main-type", prop_id, "P"),
        _hb_fact("subtype", prop_id, "v"),
        _hb_fact("roles", prop_id, "so"),
        _hb_fact("namespace", prop_id, "()"),
        _hb_fact("source", prop_id, _quote(sentence)),
        _hb_fact("connector", prop_id, connector),
        _hb_fact("arg-roles", prop_id, "so"),
        _hb_fact("connector-label", prop_id, _quote(edge_predicate)),
        _hb_fact("connector-main-type", prop_id, "P"),
        _hb_fact("connector-subtype", prop_id, "v"),
        _hb_fact("connector-roles", prop_id, "so"),
        _hb_fact("connector-namespace", prop_id, "()"),
        _hb_fact("arg", prop_id, "s", subject_edge),
        _hb_fact("arg-pos", prop_id, "0", "s", subject_edge),
        _hb_fact("role-kind", prop_id, "0", "s", "subject"),
        _hb_fact("arg", prop_id, "o", object_edge),
        _hb_fact("arg-pos", prop_id, "1", "o", object_edge),
        _hb_fact("role-kind", prop_id, "1", "o", "object"),
    )
    return StructuredProposition(
        id=prop_id,
        sentence=sentence,
        predicate=predicate,
        subject=subject,
        object=object_,
        edge=edge,
        tree=tree,
        facts=facts,
        source=source,
        ontology_hint=ontology_hint,
    )


def _tree(predicate: str, subject: str, object_: str) -> str:
    return (
        f'(sh (tag P v so ()) {_quote(predicate)} '
        f"(args ((arg s {_sh_atom(subject)}) (arg o {_sh_atom(object_)}))))"
    )


def _sh_atom(label: str) -> str:
    return f'(sh-atom (tag C c NoRoles ()) {_quote(label)})'


def _edge_atom(label: str) -> str:
    return f"{_token(label)}/Cc"


def _hb_fact(kind: str, *parts: str) -> str:
    key = " ".join(kind.replace("-", " ").split())
    return f"(hb {key} {' '.join(parts)})"


def _token(label: str) -> str:
    text = _TOKEN_RE.sub("_", label.lower()).strip("_")
    return text or "entity"


def _quote(text: str) -> str:
    return json.dumps(text, ensure_ascii=True)


def _native_reasoner_payload(
    propositions: tuple[StructuredProposition, ...],
    evidence: IncidentEvidence,
) -> dict[str, Any]:
    from .metta_reasoner import reason_over_hyperbase

    return reason_over_hyperbase(propositions, evidence)


def _ontology_grounding(ontology: OntologyContext | None) -> dict[str, Any]:
    if ontology is None:
        return {"source_available": False, "projection_rules": []}
    return {
        "source_available": ontology.source_available,
        "source_path": str(ontology.source_path),
        "module_count": ontology.module_count,
        "axiom_count": ontology.axiom_count,
        "projection_rules": list(ontology.projection_rules),
    }

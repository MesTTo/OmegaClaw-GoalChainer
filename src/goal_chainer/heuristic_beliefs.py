"""Heuristic PLN-style belief grading without PeTTaChainer compileadd.

This module mirrors the semantics of evidence_chainer.grade_beliefs() but uses
simple arithmetic on the evidence signals instead of running PeTTaChainer's
compileadd (which exceeds SWI's 8 GB stack limit for the current GoalChainer
query size). It produces the same Belief dataclass so callers are transparent
to which path was used.

The PLN rules in evidence_chainer.py are:
  - support_to_accept:   SupportsCollective(x) -> Acceptable(x),  STV 0.92/0.95
  - redaction_to_accept: Redacted(x) -> Acceptable(x),             STV 0.95/0.97
  - protect_to_accept:   ProtectsPrivacy(x) -> Acceptable(x),     STV 0.85/0.92
  - risk_to_accept:      RisksPrivacy(x) -> Acceptable(x),       STV 0.05/0.90

Ground facts per action are derived from IncidentEvidence in _facts_for().

The heuristic computes a weighted combination of the applicable rule consequent
truth values, using subjective-logic fusion (Dempster's rule simplified for
independent evidence sources) to combine multiple supports for one action.

This is deliberately a crude PLN-style guesstimate, per Ben's verification
posture: "use crude PLN-style guesstimate inferences / heuristic gates where
appropriate" (2026-07-02 GoalChainer pointer note).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, NamedTuple

from .deontic_engine import ACTION_ORDER
from .evidence import IncidentEvidence
from .evidence_chainer import Belief


# Rule truth values (strength, confidence) from evidence_chainer.py
_RULE_STRENGTH = {
    "support_to_accept": (0.92, 0.95),
    "redaction_to_accept": (0.95, 0.97),
    "protect_to_accept": (0.85, 0.92),
    "risk_to_accept": (0.05, 0.90),
}


class _Ground(NamedTuple):
    """A ground fact and the rule that fires on it."""
    rule: str
    fact_strength: float
    fact_confidence: float


def grade_beliefs_heuristic(evidence: IncidentEvidence) -> tuple[dict[str, Belief], str, list[str]]:
    """Grade action acceptability using heuristic PLN arithmetic.

    Returns (beliefs, program_description, outputs) matching the shape of
    evidence_chainer.grade_beliefs() so callers can swap transparently.
    """
    beliefs: dict[str, Belief] = {}
    outputs: list[str] = []

    for action_id in ACTION_ORDER:
        grounds = _facts_for(action_id, evidence)
        if not grounds:
            # No applicable evidence — weak neutral belief.
            beliefs[action_id] = Belief(0.5, 0.3, f"heuristic: no evidence for {action_id}")
            outputs.append(f"(Acceptable {action_id}) (STV 0.5000 0.3000)")
            continue

        # Combine multiple ground facts using subjective-logic fusion.
        # For each ground fact, the rule produces an implied (strength, confidence).
        # We fuse them sequentially using the SL combination rule.
        combined_s, combined_c = _fuse_grounds(grounds)
        proof = _build_proof(action_id, grounds, combined_s, combined_c)
        beliefs[action_id] = Belief(combined_s, combined_c, proof)
        outputs.append(f"(Acceptable {action_id}) (STV {combined_s:.4f} {combined_c:.4f})")

    program = (
        "heuristic_pln:\n"
        f"  rules: {list(_RULE_STRENGTH.keys())}\n"
        f"  actions: {list(ACTION_ORDER)}\n"
        f"  evidence: privacy_at_stake={evidence.privacy_at_stake}, facts_ready={evidence.facts_ready}\n"
    )
    return beliefs, program, outputs


def _facts_for(action_id: str, evidence: IncidentEvidence) -> list[_Ground]:
    """Derive ground facts matching evidence_chainer._facts_for()."""
    grounds: list[_Ground] = []

    if action_id == "publish_raw_log":
        if evidence.privacy_at_stake:
            count = len(evidence.sensitive_categories)
            freq = min(0.98, 0.6 + 0.1 * count)
            grounds.append(_Ground("risk_to_accept", freq, 0.95))
        else:
            grounds.append(_Ground("support_to_accept", 0.95, 0.95))
        return grounds

    if action_id == "publish_redacted_summary":
        support = 0.95 if evidence.facts_ready else 0.55
        grounds.append(_Ground("support_to_accept", support, 0.95))
        grounds.append(_Ground("redaction_to_accept", 1.0, 0.97))
        return grounds

    if action_id == "hold_external_update":
        protect = 0.95 if not evidence.facts_ready else 0.85
        grounds.append(_Ground("protect_to_accept", protect, 0.92))
        return grounds

    return grounds


def _fuse_grounds(grounds: list[_Ground]) -> tuple[float, float]:
    """Fuse multiple ground facts using simplified subjective-logic combination.

    For each ground fact, the implied belief is:
        s_implied = rule_strength * fact_strength   (chain product)
        c_implied = rule_confidence * fact_confidence

    Then fuse multiple independent evidence sources using the cumulative
    SL fusion: belief mass b_i = c_i * s_i, disbelief d_i = c_i * (1 - s_i),
    uncertainty u_i = 1 - c_i. Combine with:
        b12 = (b1*b2 + b1*u2 + b2*u1) / (1 - b1*d2 - d1*b2)
        d12 = (d1*d2 + d1*u2 + d2*u1) / (1 - b1*d2 - d1*b2)
        u12 = (u1*u2) / (1 - b1*d2 - d1*b2)
    Then s = b / (b + d), c = 1 - u.
    """
    if len(grounds) == 1:
        rule_s, rule_c = _RULE_STRENGTH[grounds[0].rule]
        s = rule_s * grounds[0].fact_strength
        c = rule_c * grounds[0].fact_confidence
        # Clamp to [0, 1]
        return (min(max(s, 0.0), 1.0), min(max(c, 0.0), 1.0))

    # Initialize with the first ground
    b, c = _ground_to_sl(grounds[0])
    d = c * (1.0 - b) if c > 0 else 0.0
    b = c * b
    u = 1.0 - c

    for ground in grounds[1:]:
        b2, c2 = _ground_to_sl(ground)
        d2 = c2 * (1.0 - b2) if c2 > 0 else 0.0
        b2 = c2 * b2
        u2 = 1.0 - c2

        denom = 1.0 - b * d2 - d * b2
        if abs(denom) < 1e-15:
            # Degenerate case — skip this ground
            continue

        b_new = (b * b2 + b * u2 + b2 * u) / denom
        d_new = (d * d2 + d * u2 + d2 * u) / denom
        u_new = (u * u2) / denom

        b, d, u = b_new, d_new, u_new

    # Convert back to (strength, confidence)
    total = b + d
    s = b / total if total > 1e-15 else 0.5
    c = 1.0 - u
    return (min(max(s, 0.0), 1.0), min(max(c, 0.0), 1.0))


def _ground_to_sl(ground: _Ground) -> tuple[float, float]:
    """Convert a ground fact to raw (strength, confidence) before SL mass.

    For standard PLN rules, the implied strength is rule_strength * fact_strength
    (chain product). For memory grounds (rule starts with 'memory_'), the
    fact_strength and fact_confidence ARE the final strength and confidence,
    since memory evidence doesn't go through a rule chain.
    """
    if ground.rule.startswith("memory_"):
        s = ground.fact_strength
        c = ground.fact_confidence
    else:
        rule_s, rule_c = _RULE_STRENGTH[ground.rule]
        s = rule_s * ground.fact_strength
        c = rule_c * ground.fact_confidence
    return (min(max(s, 0.0), 1.0), min(max(c, 0.0), 1.0))


def _build_proof(action_id: str, grounds: list[_Ground], s: float, c: float) -> str:
    rules = ", ".join(g.rule for g in grounds)
    return f"heuristic_pln({action_id}, rules=[{rules}], STV {s:.4f} {c:.4f})"


# ---------------------------------------------------------------------------
# Memory-evidence bridge: feed petta-memory promoted evidence packets as
# read-only inputs that adjust the heuristic belief grader's ground facts.
# ---------------------------------------------------------------------------

# Regex for parsing petta-memory handoff STV atoms:
#   (Acceptable <action>) (STV <strength> <confidence>)
_STV_RE = re.compile(
    r"\(Acceptable\s+(?P<action>[A-Za-z0-9_:-]+)\)\s+"
    r"\(STV\s+(?P<strength>[0-9.eE+-]+)\s+(?P<confidence>[0-9.eE+-]+)\)"
)

# Regex for parsing petta-memory EvidencePacket atoms:
#   (EvidencePacket (Acceptable <action>) (EC <support> <opposition>) ...)
_EC_RE = re.compile(
    r"\(EvidencePacket\s+\(Acceptable\s+(?P<action>[A-Za-z0-9_:-]+)\)\s+"
    r"\(EC\s+(?P<support>[0-9.eE+-]+)\s+(?P<opposition>[0-9.eE+-]+)\)"
)


@dataclass(frozen=True)
class MemoryEvidenceItem:
    """A parsed petta-memory promoted evidence item.

    Items come from the goalchainer_handoff_cache and carry either:
    - an STV atom (acceptability-belief-evidence slot): direct strength/confidence
    - an EC atom (contextual-appraisal-evidence slot): support/opposition counts
    """
    action_id: str
    source: str  # "stv" or "ec"
    strength: float  # derived strength in [0, 1]
    confidence: float  # derived confidence in [0, 1]
    belief_id: str | None = None
    cluster_id: str | None = None
    promotion_event: str | None = None
    promotion_domain: str | None = None
    raw_atom: str = ""


def parse_memory_evidence(items: list[dict[str, Any]]) -> list[MemoryEvidenceItem]:
    """Parse petta-memory handoff cache items into MemoryEvidenceItem objects.

    Only items with goalchainer_slot of 'acceptability-belief-evidence' (STV atoms)
    or 'contextual-appraisal-evidence' (EvidencePacket EC atoms) are parsed.
    Unparseable items are silently skipped.
    """
    parsed: list[MemoryEvidenceItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        atom = str(item.get("atom", ""))
        slot = item.get("goalchainer_slot", "")
        meta = {
            "belief_id": item.get("belief_id"),
            "cluster_id": item.get("cluster_id"),
            "promotion_event": item.get("promotion_event"),
            "promotion_domain": item.get("promotion_domain"),
            "raw_atom": atom,
        }
        if slot == "acceptability-belief-evidence":
            m = _STV_RE.search(atom)
            if m:
                s = _clamp(float(m.group("strength")))
                c = _clamp(float(m.group("confidence")))
                parsed.append(MemoryEvidenceItem(
                    action_id=m.group("action"), source="stv",
                    strength=s, confidence=c, **meta,
                ))
        elif slot == "contextual-appraisal-evidence":
            m = _EC_RE.search(atom)
            if m:
                support = max(0.0, float(m.group("support")))
                opposition = max(0.0, float(m.group("opposition")))
                total = support + opposition
                if total <= 0:
                    continue
                s = support / total
                c = total / (total + 2.0)
                parsed.append(MemoryEvidenceItem(
                    action_id=m.group("action"), source="ec",
                    strength=s, confidence=c, **meta,
                ))
    return parsed


def _dedup_provenance(items: list[MemoryEvidenceItem]) -> list[MemoryEvidenceItem]:
    """Collapse items that share provenance identifiers into one representative.

    The goalchainer handoff cache can emit multiple atoms for the same promoted
    belief (e.g. an STV atom and an EvidencePacket EC atom, both stamped with
    the same belief_id / cluster_id / promotion_event). Fusing those as
    independent grounds double-counts the evidence and inflates confidence.
    Group by (belief_id) or (cluster_id, promotion_event) and keep one item per
    group; prefer the 'stv' slot (raw STV is the direct value), then the lowest
    confidence, as the conservative representative.
    """
    groups: dict[tuple, list[MemoryEvidenceItem]] = {}
    order: list[tuple] = []
    for item in items:
        if item.belief_id is not None:
            key: tuple = ("belief", item.belief_id)
        elif item.cluster_id is not None and item.promotion_event is not None:
            key = ("cluster", item.cluster_id, item.promotion_event)
        else:
            key = ("item", id(item))
        if key not in groups:
            order.append(key)
        groups.setdefault(key, []).append(item)
    out: list[MemoryEvidenceItem] = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            out.append(group[0])
            continue
        rep = sorted(group, key=lambda it: (it.source != "stv", it.confidence))[0]
        out.append(rep)
    return out


def grade_beliefs_heuristic_with_memory(
    evidence: IncidentEvidence,
    memory_items: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Belief], str, list[str]]:
    """Grade beliefs using heuristic PLN arithmetic, optionally adjusted by
    petta-memory promoted evidence packets.

    When memory_items are provided, each parsed MemoryEvidenceItem is fused with
    the keyword-derived ground facts for the same action. This mirrors how a
    real PeTTaChainer query would combine request-derived premises with
    memory-derived evidence: the memory items adjust the belief away from the
    keyword-only baseline, providing a rudimentary appraisal-context bridge.

    The fusion uses the same subjective-logic combination rule as the base
    heuristic: memory evidence is treated as an additional independent ground
    fact whose rule strength/confidence come from the parsed STV/EC values.
    """
    if not memory_items:
        return grade_beliefs_heuristic(evidence)

    parsed = _dedup_provenance(parse_memory_evidence(memory_items))
    memory_by_action: dict[str, list[MemoryEvidenceItem]] = {}
    for item in parsed:
        memory_by_action.setdefault(item.action_id, []).append(item)

    beliefs: dict[str, Belief] = {}
    outputs: list[str] = []
    memory_notes: list[str] = []

    for action_id in ACTION_ORDER:
        grounds = _facts_for(action_id, evidence)
        if not grounds:
            beliefs[action_id] = Belief(0.5, 0.3, f"heuristic: no evidence for {action_id}")
            outputs.append(f"(Acceptable {action_id}) (STV 0.5000 0.3000)")
            continue

        # Convert memory items for this action into synthetic grounds.
        memory_grounds: list[_Ground] = []
        for mem_item in memory_by_action.get(action_id, []):
            # Use a synthetic rule label that won't collide with the real rules.
            rule_label = f"memory_{mem_item.source}"
            memory_grounds.append(_Ground(
                rule=rule_label,
                fact_strength=mem_item.strength,
                fact_confidence=mem_item.confidence,
            ))
            memory_notes.append(
                f"  memory: {action_id} {mem_item.source} "
                f"s={mem_item.strength:.4f} c={mem_item.confidence:.4f} "
                f"(belief_id={mem_item.belief_id})"
            )

        all_grounds = grounds + memory_grounds
        combined_s, combined_c = _fuse_grounds(all_grounds)
        proof = _build_proof_with_memory(action_id, all_grounds, combined_s, combined_c)
        beliefs[action_id] = Belief(combined_s, combined_c, proof)
        outputs.append(f"(Acceptable {action_id}) (STV {combined_s:.4f} {combined_c:.4f})")

    program = (
        "heuristic_pln_with_memory:\n"
        f"  rules: {list(_RULE_STRENGTH.keys())} + memory_evidence\n"
        f"  actions: {list(ACTION_ORDER)}\n"
        f"  evidence: privacy_at_stake={evidence.privacy_at_stake}, facts_ready={evidence.facts_ready}\n"
        f"  memory_items: {len(parsed)} kept after provenance dedup from {len(memory_items)} input items\n"
    )
    if memory_notes:
        program += "  memory_adjustments:\n" + "\n".join(memory_notes) + "\n"
    return beliefs, program, outputs


def _build_proof_with_memory(
    action_id: str,
    grounds: list[_Ground],
    s: float,
    c: float,
) -> str:
    rules = ", ".join(g.rule for g in grounds)
    has_memory = any(g.rule.startswith("memory_") for g in grounds)
    mem_tag = " +memory" if has_memory else ""
    return f"heuristic_pln({action_id}, rules=[{rules}]{mem_tag}, STV {s:.4f} {c:.4f})"


def _clamp(v: float) -> float:
    return min(max(v, 0.0), 1.0)

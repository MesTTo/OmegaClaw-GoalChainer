"""Run native OmegaClaw NAL reasoning over evidence read from the request.

What is variable and what is constant:

- The *grounding* truth values (does this action have this property, and how
  strongly) are derived from `IncidentEvidence`, so they change with the request.
- The *norm rules* (risky -> forbidden, protecting -> acceptable, supporting ->
  acceptable) are constants. They are the agent's standing, inspectable policy.

The native engine runs the deduction, the revision, and the Truth_Expectation. The
deontic status (forbidden / acceptable / permitted) is read off the expectation of
whatever the engine derives, not asserted in advance. So a request with no
sensitive data lowers the risk grounding, the forbidden expectation drops below the
threshold, and publishing the raw log stops being forbidden.

Native `lib_deontic.metta` would be the richer home for the F/O/P classification,
but it imports `(library OmegaClaw-Core ...)` modules the plain hyperon binary does
not resolve, so we stay inside lib_nal here and derive status from Truth_Expectation.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evidence import IncidentEvidence
from .models import CandidateAction, EvidenceProjection

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METTA_BIN = Path("/home/user/Dev/mettabase/hyperbase/.venv/bin/metta")
DEFAULT_NAL_LIB = Path("/home/user/Dev/OmegaClaw-Core/lib_nal.metta")
NATIVE_REASONER_SOURCE = "omega-core-lib-nal-native-metta"
NATIVE_PRELUDE = """(= (min $a $b) (if (< $a $b) $a $b))
(= (max $a $b) (if (> $a $b) $a $b))"""

# Deontic threshold on Truth_Expectation. An expectation at or above this means the
# conclusion is believed enough to act on; below it the term is too weak/uncertain.
DEONTIC_THRESHOLD = 0.6

# Standing norm rules: property -> deontic class. Constant, inspectable policy.
NORM_RISKY_FORBIDDEN = "((--> privacy_risky_action forbidden_action) (stv 0.95 0.90))"
NORM_PROTECTING_ACCEPTABLE = "((--> privacy_protecting_action acceptable_action) (stv 0.92 0.88))"
NORM_SUPPORTING_ACCEPTABLE = "((--> coordination_supporting_action acceptable_action) (stv 0.90 0.88))"

ACTION_ORDER = ("publish_raw_log", "publish_redacted_summary", "hold_external_update")

_STV_RE = re.compile(r"\(stv\s+(?P<f>[0-9.eE+-]+)\s+(?P<c>[0-9.eE+-]+)\)")
_CONCLUSION_RE = re.compile(
    r"\(\(-->\s+(?P<subject>[^\s()]+)\s+(?P<predicate>[^\s()]+)\)\s+"
    r"\(stv\s+(?P<f>[0-9.eE+-]+)\s+(?P<c>[0-9.eE+-]+)\)\)"
)
_FLOAT_RE = re.compile(r"-?[0-9]+\.?[0-9]*(?:[eE][+-]?[0-9]+)?")


@dataclass(frozen=True)
class Truth:
    frequency: float
    confidence: float

    def metta(self) -> str:
        return f"(stv {self.frequency:.4f} {self.confidence:.4f})"


@dataclass(frozen=True)
class Grounding:
    """A claim that an action has a property, with evidence-derived truth."""

    action_id: str
    property_term: str
    deontic_class: str
    truth: Truth
    norm_rule: str
    note: str

    @property
    def conclusion_term(self) -> str:
        return f"(--> {self.action_id} {self.deontic_class})"

    @property
    def grounding_term(self) -> str:
        return f"(--> {self.action_id} {self.property_term})"

    def deduction_query(self) -> str:
        return f"!(|-nal ({self.grounding_term} {self.truth.metta()}) {self.norm_rule})"


@dataclass(frozen=True)
class DerivedConclusion:
    action_id: str
    deontic_class: str
    term: str
    frequency: float
    confidence: float
    expectation: float
    proof: str
    notes: tuple[str, ...]

    @property
    def stv(self) -> str:
        return f"(stv {self.frequency:.6f} {self.confidence:.6f})"


class HyperBaseMettaReasoner:
    """Expose native MeTTa conclusions as GoalChainer action evidence."""

    source = NATIVE_REASONER_SOURCE

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self._evidence = {
            action["action_id"]: action for action in result.get("action_evidence", [])
        }

    def project(self, action: CandidateAction) -> EvidenceProjection:
        row = self._row(action.id)
        return EvidenceProjection(
            strength=float(row["strength"]),
            confidence=float(row["confidence"]),
            source=self.source,
            projection=str(row["projection"]),
            proofs=tuple(row["proofs"]),
            deontic=str(row["deontic"]),
            expectation=float(row["expectation"]),
        )

    def _row(self, action_id: str) -> dict[str, Any]:
        row = self._evidence.get(action_id)
        if row is None:
            raise RuntimeError(f"native MeTTa reasoner returned no evidence for {action_id}")
        return row


def reason_over_hyperbase(
    propositions: tuple[Any, ...],
    evidence: IncidentEvidence,
) -> dict[str, Any]:
    """Derive evidence-grounded premises and run them through native NAL."""

    groundings = _groundings_from_evidence(evidence)
    deduction_outputs = _run_native(tuple(g.deduction_query() for g in groundings))
    conclusions = _conclusions_from_deductions(groundings, deduction_outputs)
    revised = _revise(conclusions)
    finals = _finalize(conclusions, revised)
    expectations = _run_native(tuple(f"!(Truth_Expectation {c.stv})" for c in finals))
    finals = _attach_expectations(finals, expectations)
    action_evidence = _action_evidence(finals)
    return {
        "source": NATIVE_REASONER_SOURCE,
        "engine": "nal",
        "execution": {
            "mode": "native-metta",
            "metta_bin": str(_metta_bin()),
            "nal_library": str(_nal_lib()),
            "prelude": "min/max definitions required by OmegaClaw NAL Truth_Revision",
            "deontic_threshold": DEONTIC_THRESHOLD,
            "deontic_source": "Truth_Expectation over NAL conclusions (lib_nal)",
        },
        "input": "evidence read from the request",
        "evidence": evidence.to_dict(),
        "norm_rules": {
            "risky_forbidden": NORM_RISKY_FORBIDDEN,
            "protecting_acceptable": NORM_PROTECTING_ACCEPTABLE,
            "supporting_acceptable": NORM_SUPPORTING_ACCEPTABLE,
        },
        "groundings": [
            {
                "action_id": g.action_id,
                "term": g.grounding_term,
                "truth": g.truth.metta(),
                "note": g.note,
                "deontic_class": g.deontic_class,
            }
            for g in groundings
        ],
        "queries": [g.deduction_query() for g in groundings]
        + [f"!(Truth_Expectation {c.stv})" for c in finals],
        "raw_outputs": deduction_outputs + expectations,
        "conclusions": [
            {
                "action_id": c.action_id,
                "term": c.term,
                "truth": {"frequency": round(c.frequency, 6), "confidence": round(c.confidence, 6)},
                "expectation": round(c.expectation, 6),
                "proof": c.proof,
            }
            for c in finals
        ],
        "action_evidence": action_evidence,
    }


def _groundings_from_evidence(evidence: IncidentEvidence) -> tuple[Grounding, ...]:
    rows: list[Grounding] = [
        Grounding(
            action_id="publish_raw_log",
            property_term="privacy_risky_action",
            deontic_class="forbidden_action",
            truth=_risk_truth(evidence),
            norm_rule=NORM_RISKY_FORBIDDEN,
            note=_risk_note(evidence),
        ),
        Grounding(
            action_id="publish_raw_log",
            property_term="coordination_supporting_action",
            deontic_class="acceptable_action",
            truth=_raw_support_truth(evidence),
            norm_rule=NORM_SUPPORTING_ACCEPTABLE,
            note="a full log carries the most coordination detail",
        ),
        Grounding(
            action_id="publish_redacted_summary",
            property_term="privacy_protecting_action",
            deontic_class="acceptable_action",
            truth=Truth(0.95, 0.90),
            norm_rule=NORM_PROTECTING_ACCEPTABLE,
            note="redaction removes identifiers regardless of the request",
        ),
        Grounding(
            action_id="publish_redacted_summary",
            property_term="coordination_supporting_action",
            deontic_class="acceptable_action",
            truth=_redacted_support_truth(evidence),
            norm_rule=NORM_SUPPORTING_ACCEPTABLE,
            note=_redacted_support_note(evidence),
        ),
        Grounding(
            action_id="hold_external_update",
            property_term="privacy_protecting_action",
            deontic_class="acceptable_action",
            truth=_hold_truth(evidence),
            norm_rule=NORM_PROTECTING_ACCEPTABLE,
            note=_hold_note(evidence),
        ),
    ]
    return tuple(rows)


def _risk_truth(evidence: IncidentEvidence) -> Truth:
    if evidence.privacy_at_stake:
        count = len(evidence.sensitive_categories)
        return Truth(min(0.98, 0.55 + 0.11 * count), min(0.95, 0.55 + 0.08 * count))
    # No identifiable data, or the request declared the data public: little risk.
    return Truth(0.05, 0.30)


def _risk_note(evidence: IncidentEvidence) -> str:
    if evidence.privacy_at_stake:
        return f"raw log exposes {len(evidence.sensitive_categories)} sensitive categories"
    if evidence.public_declared:
        return "request declares the data is safe to share in full"
    return "no identifiable data detected in the request"


def _raw_support_truth(evidence: IncidentEvidence) -> Truth:
    return Truth(0.92, 0.85) if evidence.coordination_needed else Truth(0.70, 0.60)


def _redacted_support_truth(evidence: IncidentEvidence) -> Truth:
    # A redacted status only advances coordination once the facts are established;
    # broadcasting an unverified status helps responders less.
    return Truth(0.92, 0.90) if evidence.facts_ready else Truth(0.55, 0.70)


def _redacted_support_note(evidence: IncidentEvidence) -> str:
    if evidence.facts_ready:
        return "a verified redacted status gives responders shared context"
    return "facts are not ready, so an external status helps coordination less"


def _hold_truth(evidence: IncidentEvidence) -> Truth:
    return Truth(0.95, 0.92) if not evidence.facts_ready else Truth(0.90, 0.85)


def _hold_note(evidence: IncidentEvidence) -> str:
    if not evidence.facts_ready:
        return "holding is the safe move while facts are still unverified"
    return "holding always protects privacy but withholds context"


def _conclusions_from_deductions(
    groundings: tuple[Grounding, ...],
    outputs: list[dict[str, str]],
) -> tuple[DerivedConclusion, ...]:
    rows: list[DerivedConclusion] = []
    for grounding, output in zip(groundings, outputs):
        match = _select_conclusion(grounding.conclusion_term, output["stdout"])
        if match is None:
            raise RuntimeError(
                f"native MeTTa did not derive {grounding.conclusion_term}: {output['stdout']}"
            )
        rows.append(
            DerivedConclusion(
                action_id=grounding.action_id,
                deontic_class=grounding.deontic_class,
                term=grounding.conclusion_term,
                frequency=float(match["f"]),
                confidence=float(match["c"]),
                expectation=0.0,
                proof=output["stdout"],
                notes=(grounding.note,),
            )
        )
    return tuple(rows)


def _select_conclusion(term: str, output: str) -> dict[str, str] | None:
    for match in _CONCLUSION_RE.finditer(output):
        if f"(--> {match.group('subject')} {match.group('predicate')})" == term:
            return match.groupdict()
    return None


def _revise(conclusions: tuple[DerivedConclusion, ...]) -> tuple[DerivedConclusion, ...]:
    grouped: dict[tuple[str, str], list[DerivedConclusion]] = {}
    for conclusion in conclusions:
        grouped.setdefault((conclusion.action_id, conclusion.term), []).append(conclusion)

    revised: list[DerivedConclusion] = []
    queries: list[str] = []
    targets: list[tuple[tuple[str, str], DerivedConclusion, DerivedConclusion]] = []
    for key, group in grouped.items():
        if len(group) < 2:
            continue
        first, second = group[0], group[1]
        queries.append(f"!(|-nal ({first.term} {first.stv}) ({second.term} {second.stv}))")
        targets.append((key, first, second))
    if not queries:
        return ()

    outputs = _run_native(tuple(queries))
    for (key, first, second), output in zip(targets, outputs):
        match = _select_conclusion(first.term, output["stdout"])
        if match is None:
            raise RuntimeError(f"native MeTTa revision did not return {first.term}: {output['stdout']}")
        revised.append(
            DerivedConclusion(
                action_id=first.action_id,
                deontic_class=first.deontic_class,
                term=first.term,
                frequency=float(match["f"]),
                confidence=float(match["c"]),
                expectation=0.0,
                proof=output["stdout"],
                notes=first.notes + second.notes + ("revised",),
            )
        )
    return tuple(revised)


def _finalize(
    conclusions: tuple[DerivedConclusion, ...],
    revised: tuple[DerivedConclusion, ...],
) -> tuple[DerivedConclusion, ...]:
    """Keep the revised conclusion for a (action, term) pair when one exists."""

    revised_keys = {(c.action_id, c.term) for c in revised}
    kept = [c for c in conclusions if (c.action_id, c.term) not in revised_keys]
    return tuple(kept) + revised


def _attach_expectations(
    conclusions: tuple[DerivedConclusion, ...],
    outputs: list[dict[str, str]],
) -> tuple[DerivedConclusion, ...]:
    rows: list[DerivedConclusion] = []
    for conclusion, output in zip(conclusions, outputs):
        value = _parse_float(output["stdout"])
        if value is None:
            raise RuntimeError(f"native MeTTa Truth_Expectation returned no float: {output['stdout']}")
        rows.append(
            DerivedConclusion(
                action_id=conclusion.action_id,
                deontic_class=conclusion.deontic_class,
                term=conclusion.term,
                frequency=conclusion.frequency,
                confidence=conclusion.confidence,
                expectation=value,
                proof=conclusion.proof,
                notes=conclusion.notes,
            )
        )
    return tuple(rows)


def _action_evidence(conclusions: tuple[DerivedConclusion, ...]) -> list[dict[str, Any]]:
    by_action: dict[str, list[DerivedConclusion]] = {}
    for conclusion in conclusions:
        by_action.setdefault(conclusion.action_id, []).append(conclusion)

    rows: list[dict[str, Any]] = []
    for action_id in ACTION_ORDER:
        group = by_action.get(action_id)
        if not group:
            raise RuntimeError(f"native MeTTa reasoner derived no evidence for {action_id}")
        forbidden = _best(group, "forbidden_action")
        acceptable = _best(group, "acceptable_action")
        deontic, lead = _classify(forbidden, acceptable)
        if deontic == "forbidden":
            strength = 1.0 - lead.frequency
            confidence = lead.confidence
        else:
            strength = lead.frequency
            confidence = lead.confidence
        rows.append(
            {
                "action_id": action_id,
                "deontic": deontic,
                "expectation": round(lead.expectation, 6),
                "strength": round(strength, 6),
                "confidence": round(confidence, 6),
                "projection": f"{lead.term} {lead.stv}",
                "proofs": [c.proof for c in group],
                "notes": sorted({note for c in group for note in c.notes}),
            }
        )
    return rows


def _best(group: list[DerivedConclusion], deontic_class: str) -> DerivedConclusion | None:
    matches = [c for c in group if c.deontic_class == deontic_class]
    if not matches:
        return None
    return max(matches, key=lambda c: c.expectation)


def _classify(
    forbidden: DerivedConclusion | None,
    acceptable: DerivedConclusion | None,
) -> tuple[str, DerivedConclusion]:
    if forbidden is not None and forbidden.expectation >= DEONTIC_THRESHOLD:
        return "forbidden", forbidden
    if acceptable is not None and acceptable.expectation >= DEONTIC_THRESHOLD:
        return "acceptable", acceptable
    # Nothing crosses the threshold: report the strongest signal as permitted.
    lead = max(
        [c for c in (forbidden, acceptable) if c is not None],
        key=lambda c: c.expectation,
    )
    return "permitted", lead


def _run_native(queries: tuple[str, ...]) -> list[dict[str, str]]:
    if not queries:
        return []
    metta_bin = _metta_bin()
    nal_lib = _nal_lib()
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".metta", encoding="utf-8") as handle:
        program_path = Path(handle.name)
        handle.write(NATIVE_PRELUDE)
        handle.write("\n\n")
        handle.write(nal_lib.read_text(encoding="utf-8"))
        handle.write("\n\n")
        for query in queries:
            handle.write(query)
            handle.write("\n")
    try:
        result = subprocess.run(
            [str(metta_bin), str(program_path)],
            cwd=str(REPO_ROOT),
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        program_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(
            "native MeTTa execution failed:\n"
            f"command={metta_bin} {program_path}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != len(queries):
        raise RuntimeError(
            f"native MeTTa returned {len(lines)} lines for {len(queries)} queries: {lines}"
        )
    return [
        {"query": query, "stdout": line, "stderr": result.stderr.strip()}
        for query, line in zip(queries, lines)
    ]


def _parse_float(output: str) -> float | None:
    match = _FLOAT_RE.search(output)
    return float(match.group()) if match else None


def _metta_bin() -> Path:
    path = Path(os.environ.get("GOALCHAINER_METTA_BIN", DEFAULT_METTA_BIN))
    if not path.exists():
        raise RuntimeError(f"native MeTTa binary not found: {path}")
    return path


def _nal_lib() -> Path:
    path = Path(os.environ.get("GOALCHAINER_NAL_LIB", DEFAULT_NAL_LIB))
    if not path.exists():
        raise RuntimeError(f"OmegaClaw NAL library not found: {path}")
    return path

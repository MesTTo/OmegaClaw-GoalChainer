"""Run native OmegaClaw NAL reasoning over HyperBase propositions."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hyperbase import StructuredProposition
from .models import CandidateAction, EvidenceProjection


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METTA_BIN = Path("/home/user/Dev/mettabase/hyperbase/.venv/bin/metta")
DEFAULT_NAL_LIB = Path("/home/user/Dev/OmegaClaw-Core/lib_nal.metta")
NATIVE_REASONER_SOURCE = "omega-core-lib-nal-native-metta"
NATIVE_PRELUDE = """(= (min $a $b) (if (< $a $b) $a $b))
(= (max $a $b) (if (> $a $b) $a $b))"""
CONCLUSION_RE = re.compile(
    r"\(\(-->\s+(?P<subject>[^\s()]+)\s+(?P<predicate>[^\s()]+)\)\s+"
    r"\(stv\s+(?P<frequency>[0-9.eE+-]+)\s+(?P<confidence>[0-9.eE+-]+)\)\)"
)


@dataclass(frozen=True)
class NativePremise:
    id: str
    action_id: str
    from_proposition: str
    sentence: str
    term: str
    truth: str
    metta: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "from_proposition": self.from_proposition,
            "sentence": self.sentence,
            "term": self.term,
            "truth": self.truth,
            "metta": self.metta,
        }


@dataclass(frozen=True)
class NativeQuery:
    id: str
    action_id: str
    expected_term: str
    expression: str
    support: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "expected_term": self.expected_term,
            "expression": self.expression,
            "support": list(self.support),
        }


@dataclass(frozen=True)
class NativeConclusion:
    id: str
    action_id: str
    claim: str
    term: str
    frequency: float
    confidence: float
    expression: str
    support: tuple[str, ...]

    @property
    def stv(self) -> str:
        return f"(stv {self.frequency:.6f} {self.confidence:.6f})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "claim": self.claim,
            "term": self.term,
            "truth": {
                "frequency": round(self.frequency, 6),
                "confidence": round(self.confidence, 6),
            },
            "expression": self.expression,
            "support": list(self.support),
        }


class HyperBaseMettaReasoner:
    """Expose native MeTTa conclusions as GoalChainer action evidence."""

    source = NATIVE_REASONER_SOURCE

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self._action_evidence = {
            action["action_id"]: action for action in result.get("action_evidence", [])
        }

    def project(self, action: CandidateAction) -> EvidenceProjection:
        evidence = self._action_evidence.get(action.id)
        if evidence is None:
            raise RuntimeError(f"native MeTTa reasoner returned no evidence for {action.id}")
        return EvidenceProjection(
            strength=float(evidence["strength"]),
            confidence=float(evidence["confidence"]),
            source=self.source,
            projection=str(evidence["projection"]),
            proofs=tuple(evidence["proofs"]),
        )


def reason_over_hyperbase(propositions: tuple[StructuredProposition, ...]) -> dict[str, Any]:
    """Run OmegaClaw Core's native NAL rules over HyperBase-derived premises."""

    premises = _premises_from_propositions(propositions)
    deduction_queries = _deduction_queries(premises)
    deduction_outputs = _run_native_queries(deduction_queries)
    conclusions = _extract_conclusions(deduction_queries, deduction_outputs)
    revision_queries, revision_outputs, revised = _revise_conclusions(conclusions)
    action_evidence = _action_evidence(conclusions, revised)
    return {
        "source": NATIVE_REASONER_SOURCE,
        "engine": "nal",
        "execution": {
            "mode": "native-metta",
            "metta_bin": str(_metta_bin()),
            "nal_library": str(_nal_lib()),
            "prelude": "min/max definitions required by OmegaClaw NAL Truth_Revision",
        },
        "input": "structured English propositions",
        "premises": [premise.to_dict() for premise in premises],
        "queries": [query.to_dict() for query in (*deduction_queries, *revision_queries)],
        "metta_program": _visible_metta_program(premises, deduction_queries, revision_queries),
        "raw_outputs": deduction_outputs + revision_outputs,
        "conclusions": [conclusion.to_dict() for conclusion in (*conclusions, *revised)],
        "action_evidence": action_evidence,
    }


def _premises_from_propositions(
    propositions: tuple[StructuredProposition, ...],
) -> tuple[NativePremise, ...]:
    rows: list[NativePremise] = []
    for proposition in propositions:
        mapped = _map_proposition(proposition)
        if mapped is None:
            continue
        rows.append(mapped)
    if not rows:
        raise RuntimeError("no HyperBase propositions could be projected into native MeTTa premises")
    return tuple(rows)


def _map_proposition(proposition: StructuredProposition) -> NativePremise | None:
    truth = _source_truth(proposition.source)
    if proposition.predicate in {"contain", "expose"} and "raw" in proposition.subject:
        return _premise(
            f"raw-risk-{proposition.id}",
            "publish_raw_log",
            proposition,
            "(--> publish_raw_log privacy_risky_action)",
            truth,
        )
    if proposition.predicate == "protect" and "redacted" in proposition.subject:
        return _premise(
            "redacted-privacy",
            "publish_redacted_summary",
            proposition,
            "(--> publish_redacted_summary privacy_protecting_action)",
            truth,
        )
    if proposition.predicate == "support" and "redacted" in proposition.subject:
        return _premise(
            "redacted-coordination",
            "publish_redacted_summary",
            proposition,
            "(--> publish_redacted_summary coordination_supporting_action)",
            truth,
        )
    if proposition.predicate == "protect" and "holding external update" in proposition.subject:
        return _premise(
            "hold-privacy",
            "hold_external_update",
            proposition,
            "(--> hold_external_update privacy_protecting_action)",
            truth,
        )
    if proposition.predicate == "before":
        return _premise(
            "ordered-update",
            "publish_redacted_summary",
            proposition,
            "(--> publish_redacted_summary ordered_action)",
            truth,
        )
    if proposition.predicate == "forbids":
        return _premise(
            f"policy-guard-{proposition.id}",
            "publish_raw_log",
            proposition,
            "(--> publish_raw_log privacy_risky_action)",
            truth,
        )
    if proposition.predicate == "rejects":
        return _premise(
            f"test-guard-{proposition.id}",
            "publish_raw_log",
            proposition,
            "(--> publish_raw_log privacy_risky_action)",
            truth,
        )
    if proposition.predicate == "returns" and "raw_log" in proposition.object:
        return _premise(
            f"code-risk-{proposition.id}",
            "publish_raw_log",
            proposition,
            "(--> publish_raw_log privacy_risky_action)",
            truth,
        )
    return None


def _premise(
    premise_id: str,
    action_id: str,
    proposition: StructuredProposition,
    term: str,
    truth: str,
) -> NativePremise:
    return NativePremise(
        id=premise_id,
        action_id=action_id,
        from_proposition=proposition.id,
        sentence=proposition.sentence,
        term=term,
        truth=truth,
        metta=f"({term} {truth})",
    )


def _deduction_queries(premises: tuple[NativePremise, ...]) -> tuple[NativeQuery, ...]:
    rows: list[NativeQuery] = []
    for premise in premises:
        if premise.action_id == "publish_raw_log":
            rule = "((--> privacy_risky_action forbidden_action) (stv 0.980 0.920))"
            rows.append(
                _query(
                    f"{premise.id}-forbidden",
                    premise.action_id,
                    "(--> publish_raw_log forbidden_action)",
                    premise,
                    rule,
                )
            )
        elif premise.id == "redacted-coordination":
            rule = "((--> coordination_supporting_action acceptable_action) (stv 0.930 0.900))"
            rows.append(
                _query(
                    "redacted-coordination-acceptable",
                    premise.action_id,
                    "(--> publish_redacted_summary acceptable_action)",
                    premise,
                    rule,
                )
            )
        elif premise.id in {"redacted-privacy", "hold-privacy"}:
            rule = "((--> privacy_protecting_action acceptable_action) (stv 0.920 0.880))"
            rows.append(
                _query(
                    f"{premise.id}-acceptable",
                    premise.action_id,
                    f"(--> {premise.action_id} acceptable_action)",
                    premise,
                    rule,
                )
            )
        elif premise.id == "ordered-update":
            rule = "((--> ordered_action acceptable_action) (stv 0.880 0.860))"
            rows.append(
                _query(
                    "ordered-update-acceptable",
                    premise.action_id,
                    "(--> publish_redacted_summary acceptable_action)",
                    premise,
                    rule,
                )
            )
    if not rows:
        raise RuntimeError("no native MeTTa deduction queries were produced")
    return tuple(rows)


def _query(
    query_id: str,
    action_id: str,
    expected_term: str,
    premise: NativePremise,
    rule: str,
) -> NativeQuery:
    return NativeQuery(
        id=query_id,
        action_id=action_id,
        expected_term=expected_term,
        expression=f"!(|-nal ({premise.term} {premise.truth}) {rule})",
        support=(premise.id, rule),
    )


def _revise_conclusions(
    conclusions: tuple[NativeConclusion, ...],
) -> tuple[tuple[NativeQuery, ...], list[dict[str, str]], tuple[NativeConclusion, ...]]:
    grouped: dict[tuple[str, str], list[NativeConclusion]] = {}
    for conclusion in conclusions:
        grouped.setdefault((conclusion.action_id, conclusion.term), []).append(conclusion)

    queries: list[NativeQuery] = []
    outputs: list[dict[str, str]] = []
    revised_rows: list[NativeConclusion] = []
    for (action_id, term), group in grouped.items():
        if len(group) < 2:
            continue
        current = group[0]
        for index, next_item in enumerate(group[1:], start=2):
            query = NativeQuery(
                id=f"{action_id}-revision-{index}",
                action_id=action_id,
                expected_term=term,
                expression=f"!(|-nal ({term} {current.stv}) ({term} {next_item.stv}))",
                support=(current.id, next_item.id),
            )
            output = _run_native_queries((query,))
            revised = _extract_conclusions((query,), output)[0]
            current = NativeConclusion(
                id=revised.id,
                action_id=revised.action_id,
                claim=f"Native NAL revised evidence for {action_id}.",
                term=revised.term,
                frequency=revised.frequency,
                confidence=revised.confidence,
                expression=revised.expression,
                support=revised.support,
            )
            queries.append(query)
            outputs.extend(output)
            revised_rows.append(current)
    return tuple(queries), outputs, tuple(revised_rows)


def _run_native_queries(queries: tuple[NativeQuery, ...]) -> list[dict[str, str]]:
    metta_bin = _metta_bin()
    nal_lib = _nal_lib()
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".metta", encoding="utf-8") as handle:
        program_path = Path(handle.name)
        handle.write(NATIVE_PRELUDE)
        handle.write("\n\n")
        handle.write(nal_lib.read_text(encoding="utf-8"))
        handle.write("\n\n")
        for query in queries:
            handle.write(query.expression)
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
            f"native MeTTa returned {len(lines)} result lines for {len(queries)} queries: {lines}"
        )
    return [
        {
            "query_id": query.id,
            "stdout": line,
            "stderr": result.stderr.strip(),
        }
        for query, line in zip(queries, lines)
    ]


def _extract_conclusions(
    queries: tuple[NativeQuery, ...],
    outputs: list[dict[str, str]],
) -> tuple[NativeConclusion, ...]:
    rows: list[NativeConclusion] = []
    by_query = {query.id: query for query in queries}
    for output in outputs:
        query = by_query[output["query_id"]]
        match = _match_expected_conclusion(query.expected_term, output["stdout"])
        if match is None:
            raise RuntimeError(
                f"native MeTTa output did not contain {query.expected_term}: {output['stdout']}"
            )
        rows.append(
            NativeConclusion(
                id=query.id,
                action_id=query.action_id,
                claim=_claim_for(query.action_id, match["predicate"]),
                term=query.expected_term,
                frequency=float(match["frequency"]),
                confidence=float(match["confidence"]),
                expression=query.expression,
                support=query.support,
            )
        )
    return tuple(rows)


def _match_expected_conclusion(expected_term: str, output: str) -> dict[str, str] | None:
    for match in CONCLUSION_RE.finditer(output):
        term = f"(--> {match.group('subject')} {match.group('predicate')})"
        if term == expected_term:
            return match.groupdict()
    return None


def _claim_for(action_id: str, predicate: str) -> str:
    if predicate == "forbidden_action":
        return f"Native NAL derived that {action_id} is forbidden."
    if predicate == "acceptable_action":
        return f"Native NAL derived that {action_id} is acceptable."
    return f"Native NAL derived {predicate} for {action_id}."


def _action_evidence(
    conclusions: tuple[NativeConclusion, ...],
    revised: tuple[NativeConclusion, ...],
) -> list[dict[str, Any]]:
    best_by_action: dict[str, NativeConclusion] = {}
    for conclusion in (*conclusions, *revised):
        current = best_by_action.get(conclusion.action_id)
        if current is None or conclusion.confidence > current.confidence:
            best_by_action[conclusion.action_id] = conclusion

    rows = []
    proof_items = (*conclusions, *revised)
    for action_id in ("publish_raw_log", "publish_redacted_summary", "hold_external_update"):
        conclusion = best_by_action.get(action_id)
        if conclusion is None:
            raise RuntimeError(f"native MeTTa reasoner did not derive evidence for {action_id}")
        strength = conclusion.frequency
        if action_id == "publish_raw_log" and "forbidden_action" in conclusion.term:
            strength = 1.0 - conclusion.frequency
        rows.append(
            {
                "action_id": action_id,
                "strength": round(strength, 6),
                "confidence": round(conclusion.confidence, 6),
                "projection": f"{conclusion.term} {conclusion.stv}",
                "proofs": [item.expression for item in proof_items if item.action_id == action_id],
            }
        )
    return rows


def _visible_metta_program(
    premises: tuple[NativePremise, ...],
    deduction_queries: tuple[NativeQuery, ...],
    revision_queries: tuple[NativeQuery, ...],
) -> list[str]:
    return [
        "; Native prelude used by OmegaClaw Core Truth_Revision.",
        *NATIVE_PRELUDE.splitlines(),
        "; OmegaClaw Core lib_nal.metta is inlined before these generated forms.",
        *[premise.metta for premise in premises],
        *[query.expression for query in deduction_queries],
        *[query.expression for query in revision_queries],
    ]


def _source_truth(source: str) -> str:
    if source == "request":
        return "(stv 1.000 0.820)"
    if source == "goalchainer":
        return "(stv 1.000 0.900)"
    return "(stv 1.000 0.880)"


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

"""Grade each action's acceptability with PeTTaChainer's PLN contextual query.

PeTTaChainer is MeTTa on PeTTa, so it runs through the same `petta_runtime` wrapper
as lib_deontic. Per-action PLN statements (facts + implication rules with truth
values) are derived from the request evidence, added to a KB with `compileadd`, and
the KB is queried for `(Acceptable <action>)`. The answer is a real PLN belief with
a proof term, e.g.

    (: (merge/revision (rule-proof support_to_accept ...) (rule-proof redaction_to_accept ...))
       (Acceptable publish_redacted_summary) (STV 0.935 0.995))

The deontic verdict (forbidden/obligated/permitted) still comes from lib_deontic;
this only supplies the graded belief that feeds the score.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .deontic_engine import ACTION_ORDER
from .evidence import IncidentEvidence
from .petta_runtime import run_metta

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDORED_PETTACHAINER_DIR = REPO_ROOT / "external/PeTTaChainer"
QUERY_STEPS = 20
KB = "gckb"
BACKWARD_PREMISE_PREFILTER = True

# Shared PLN implication rules: a supporting / redacted / privacy-protecting action
# is acceptable; a privacy-risking action is not.
_RULES = (
    "(: support_to_accept (Implication (Premises (SupportsCollective $x)) (Conclusions (Acceptable $x))) (STV 0.92 0.95))",
    "(: redaction_to_accept (Implication (Premises (Redacted $x)) (Conclusions (Acceptable $x))) (STV 0.95 0.97))",
    "(: protect_to_accept (Implication (Premises (ProtectsPrivacy $x)) (Conclusions (Acceptable $x))) (STV 0.85 0.92))",
    "(: risk_to_accept (Implication (Premises (RisksPrivacy $x)) (Conclusions (Acceptable $x))) (STV 0.05 0.9))",
)

_ANSWER_RE = re.compile(
    r"\(Acceptable\s+(?P<action>[a-z_]+)\)\s+\(STV\s+(?P<f>[0-9.eE+-]+)\s+(?P<c>[0-9.eE+-]+)\)"
)


@dataclass(frozen=True)
class Belief:
    strength: float
    confidence: float
    proof: str


def chainer_metta_dir() -> Path:
    configured = os.environ.get("GOALCHAINER_PETTACHAINER_DIR")
    root = Path(configured).expanduser() if configured else VENDORED_PETTACHAINER_DIR
    metta = root / "pettachainer" / "metta"
    if not (metta / "petta_chainer.metta").exists():
        raise RuntimeError(f"PeTTaChainer MeTTa runtime not found under {metta}")
    return metta


def grade_beliefs(evidence: IncidentEvidence) -> tuple[dict[str, Belief], str, list[str]]:
    facts = [fact for action_id in ACTION_ORDER for fact in _facts_for(action_id, evidence)]
    statements = list(_RULES) + facts
    adds = " ".join(f"(compileadd {KB} {stmt})" for stmt in statements)
    queries = "\n".join(
        f"!(query {QUERY_STEPS} {KB} (: $prf (Acceptable {action_id}) $tv))"
        for action_id in ACTION_ORDER
    )
    prefilter = str(BACKWARD_PREMISE_PREFILTER).lower()
    program = (
        "!(import! &self petta_chainer)\n"
        "!(import! &self logic_configs/pln)\n"
        f"!(set-backward-premise-prefilter {KB} {prefilter})\n"
        f"!(superpose ({adds}))\n"
        f"{queries}\n"
    )
    outputs = run_metta(program, work_dir=chainer_metta_dir())
    beliefs = _parse(outputs)
    for action_id in ACTION_ORDER:
        if action_id not in beliefs:
            raise RuntimeError(f"PeTTaChainer returned no Acceptable belief for {action_id}: {outputs}")
    return beliefs, program, outputs


def _facts_for(action_id: str, evidence: IncidentEvidence) -> list[str]:
    if action_id == "publish_raw_log":
        if evidence.privacy_at_stake:
            count = len(evidence.sensitive_categories)
            freq = min(0.98, 0.6 + 0.1 * count)
            return [f"(: raw_risk (RisksPrivacy publish_raw_log) (STV {freq:.3f} 0.95))"]
        return ["(: raw_support (SupportsCollective publish_raw_log) (STV 0.95 0.95))"]
    if action_id == "publish_redacted_summary":
        support = 0.95 if evidence.facts_ready else 0.55
        return [
            f"(: red_support (SupportsCollective publish_redacted_summary) (STV {support:.3f} 0.95))",
            "(: red_redacted (Redacted publish_redacted_summary) (STV 1.0 0.97))",
        ]
    if action_id == "hold_external_update":
        protect = 0.95 if not evidence.facts_ready else 0.85
        return [f"(: hold_protect (ProtectsPrivacy hold_external_update) (STV {protect:.3f} 0.92))"]
    return []


def _parse(outputs: list[str]) -> dict[str, Belief]:
    beliefs: dict[str, Belief] = {}
    for line in outputs:
        match = _ANSWER_RE.search(line)
        if match is None:
            continue
        action = match.group("action")
        belief = Belief(float(match["f"]), float(match["c"]), line.strip())
        # Keep the highest-confidence answer per action.
        if action not in beliefs or belief.confidence > beliefs[action].confidence:
            beliefs[action] = belief
    return beliefs

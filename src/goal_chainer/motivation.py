"""Individual vs collective goals as MetaMo motivation subsystems on PeTTa.

MetaMo (iCog-Labs-Dev) is a MeTTa OpenPsi/MAGUS motivation system. Its
`consensusAction` evaluates a candidate set from two motivation states and picks the
action that maximizes a disagreement-penalized consensus score
`(scoreA+scoreB)/2 - 0.25*|scoreA-scoreB|`. We map each goal *owner* to a subsystem:
the individual (privacy) and the collective (repair/coordination). The action that
both can accept wins; an action one loves and the other hates is penalized for the
disagreement (a principled fairness floor).

This is the goals layer. `lib_deontic` still gates forbidden actions out first, and
the SNARS/PeTTaChainer risk feeds each action's riskEstimate.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .models import GoalScenario
from .petta_runtime import petta_dir, petta_swipl

METAMO_DIR = Path(
    os.environ.get("GOALCHAINER_METAMO_DIR", str(Path(__file__).resolve().parents[2] / "external/MetaMo"))
)
_ACTION_RE = re.compile(r"\(action (?P<id>[a-z_]+) ")


def available() -> bool:
    return (METAMO_DIR / "category" / "bimonad.metta").exists()


def consensus_decision(scenario: GoalScenario, reasoner) -> dict[str, Any]:
    """Run MetaMo's individual+collective consensus over the scenario's actions."""

    goals = scenario.goals
    individual = [1.0 if goal.kind == "individual" else 0.0 for goal in goals]
    collective = [1.0 if goal.kind == "collective" else 0.0 for goal in goals]

    candidates = []
    for action in scenario.actions:
        corr = [_correlation(action.id, goal.id) for goal in goals]
        risk = round(1.0 - float(reasoner.project(action).strength), 3)
        candidates.append({"id": action.id, "corr": corr, "risk": risk})

    chosen = _run_consensus(individual, collective, candidates)
    return {
        "engine": "MetaMo consensusAction (OpenPsi/MAGUS) on PeTTa",
        "individual_goals": individual,
        "collective_goals": collective,
        "candidates": candidates,
        # Pure goal pull (no risk) reveals the underlying tension; the risk-weighted
        # consensus from MetaMo resolves it.
        "goal_pull": {
            "individual": _best(individual, candidates, with_risk=False),
            "collective": _best(collective, candidates, with_risk=False),
        },
        "subsystem_preference": {
            "individual": _best(individual, candidates, with_risk=True),
            "collective": _best(collective, candidates, with_risk=True),
        },
        "consensus": chosen,
    }


# How each action correlates with (preserve_privacy, restore_service, coordinate_team).
# Graded, not binary: the raw log gives the collective the most coordination detail
# but harms privacy; the redacted summary protects privacy with slightly less detail;
# holding protects privacy but advances neither collective goal.
_CORRELATIONS = {
    "publish_raw_log": {"preserve_privacy": -1.0, "restore_service": 1.0, "coordinate_team": 1.0},
    "publish_redacted_summary": {"preserve_privacy": 1.0, "restore_service": 0.9, "coordinate_team": 0.7},
    "hold_external_update": {"preserve_privacy": 1.0, "restore_service": 0.0, "coordinate_team": 0.0},
}


def _correlation(action_id: str, goal_id: str) -> float:
    return _CORRELATIONS.get(action_id, {}).get(goal_id, 0.0)


def _score(goals: list[float], candidate: dict[str, Any], with_risk: bool) -> float:
    dot = sum(g * c for g, c in zip(goals, candidate["corr"]))
    return dot - (candidate["risk"] if with_risk else 0.0)


def _best(goals: list[float], candidates: list[dict[str, Any]], with_risk: bool) -> str:
    return max(candidates, key=lambda c: _score(goals, c, with_risk))["id"]


def _vec(values: list[float]) -> str:
    return "(" + " ".join(f"{v:.4f}" for v in values) + ")"


def _run_consensus(individual: list[float], collective: list[float], candidates: list[dict[str, Any]]) -> str:
    cands = "\n    ".join(
        f"(action {c['id']} {_vec(c['corr'])} {c['risk']:.4f} (0.0 0.0 0.0))" for c in candidates
    )
    mods = "(0.5 0.5 0.5)"
    driver = f"""!(import! &self core/helper)
!(import! &self "core/helpers.py")
!(import! &self category/bimonad)
!(import! &self core/state)
!(import! &self core/config)
!(import! &self category/functors)
!(import! &self openpsi/config)
(= (gcAppraise $s $stim) $s)
(= (gcExtract $s) $s)
(= (gcDamping $ds $d) $d)
(= (gcBoundary $s) $s)
(= (gcProject $s) $s)
(= (gcContractive $a $b $c $d) True)
(= (gcSafe $s) True)
(= (gcUnit $x) $x)
(= (gcDecide $s $c) (decisionResult (action none () 0.0 ()) ()))
(= (gcDot3 $a $b)
   (+ (+ (* (index-atom $a 0) (index-atom $b 0)) (* (index-atom $a 1) (index-atom $b 1))) (* (index-atom $a 2) (index-atom $b 2))))
(= (gcScore $s (action $id $corr $risk $dg)) (- (gcDot3 (motivationGoals $s) $corr) $risk))
(= (gcBimonad)
   (metaMoPseudoBimonad (appraisalComonad gcExtract gcAppraise) (decisionMonad gcUnit gcDecide gcScore)
     gcDamping gcBoundary gcProject gcContractive gcSafe))
!(consensusAction (gcBimonad)
    (motivation {_vec(individual)} {mods})
    (motivation {_vec(collective)} {mods})
    (stimulus (0.0 0.0 0.0 0.0))
    ({cands}))
"""
    lines = _run(driver)
    for line in reversed(lines):
        match = _ACTION_RE.search(line)
        if match:
            return match.group("id")
    raise RuntimeError(f"MetaMo consensus returned no action: {lines}")


def _run(driver: str) -> list[str]:
    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".metta", encoding="utf-8", dir=str(METAMO_DIR)
    ) as handle:
        path = Path(handle.name)
        handle.write(driver)
    try:
        result = subprocess.run(
            [
                petta_swipl(),
                "--stack_limit=8g",
                "-q",
                "-s",
                str(petta_dir() / "src" / "main.pl"),
                "--",
                str(path),
                "silent",
            ],
            cwd=str(METAMO_DIR),
            env={**os.environ, "PYTHONPATH": f"{petta_dir()}/python"},
            capture_output=True,
            text=True,
            timeout=200,
        )
    finally:
        path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"MetaMo run failed: {result.stderr[-1500:]}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]

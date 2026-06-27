"""Assess a GoalChainer claim with SNARS (Subjective-Logic NARS) on PeTTa.

This is the real System-2 step: a claim is asserted into the user's SNARS kernel
with `believe!`, queried back with `ask!`, and explained with `why!`. SNARS returns
a Subjective-Logic opinion (b,d,u,a) and a provenance receipt — calibrated belief
with a proof, which a raw scalar score does not carry.

SNARS runs through mettabase on PeTTa. The kernel resolves data relative to the
mettabase root, so the driver runs with cwd there (this was the missing piece that
made a standalone driver return empty).
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .mettabase_bridge import MB_ROOT
from .petta_runtime import petta_dir, petta_swipl

_OPINION_RE = re.compile(
    r"\(Opinion\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\)"
)
_WHY_RE = re.compile(r"\(because .*\)\s*$")
_PREMISE_RE = re.compile(
    r'\(premise "(?P<text>[^"]*)" \(Opinion '
    r"(?P<b>[0-9.eE+-]+) (?P<d>[0-9.eE+-]+) (?P<u>[0-9.eE+-]+) (?P<a>[0-9.eE+-]+)\)\)"
)
_DERIVED_RE = re.compile(r"\(derived \(: ")


def _inh(subject: str, object_: str) -> str:
    return f'(sn p so "is" ((arg s (sn c "{subject}")) (arg o (sn c "{object_}"))))'


def _src(text: str) -> str:
    """Sanitize a request phrase for use as a believe! source string literal."""
    cleaned = " ".join(text.replace('"', "'").replace("\\", " ").split())
    return cleaned[:160] or "the incident request"


def available() -> bool:
    return (MB_ROOT / "lib" / "mettabase" / "snars.metta").exists()


def assess(subject: str, relation: str, object_: str, *, source: str = "request") -> dict[str, Any]:
    """Believe `(subject relation object_)`, query it, and explain it via SNARS."""

    stmt = (
        f'(sn p so "{relation}" '
        f'((arg s (sn c "{subject}")) (arg o (sn c "{object_}"))))'
    )
    query = (
        f'(sn p so "{relation}" '
        f'((arg s (sn c "{subject}")) (arg o $what)))'
    )
    driver = (
        "!(import! &self lib/mettabase/hyperbase)\n"
        "!(import! &self lib/mettabase/snars)\n"
        f'!(believe! {stmt} (:evidence 9.0 0.0 :source "{source}"))\n'
        f"!(let $a (ask! {query}) (answer $a))\n"
        f"!(why! {stmt})\n"
    )
    lines = _run(driver)
    opinion = _parse_opinion(lines)
    why = next((line for line in lines if _WHY_RE.search(line)), "")
    return {
        "claim": f"{subject} {relation} {object_}",
        "engine": "SNARS (Subjective-Logic NARS) on PeTTa",
        "opinion": opinion,
        "expectation": round(opinion["b"] + opinion["a"] * opinion["u"], 6) if opinion else None,
        "why": why,
        "source": source,
    }


def derive(subject: str, middle: str, conclusion: str, *, sources: tuple[str, str] = ("request", "policy")) -> dict[str, Any]:
    """Believe `subject is middle` and `middle is conclusion`, run SNARS forward
    deduction, and return the derived `subject is conclusion` with its opinion and
    the proof (both premises with their opinions). Inheritance `is` is licensed, so
    SNARS deduces the closure with subjective-logic truth and provenance."""

    target = _inh(subject, conclusion)
    driver = (
        "!(import! &self lib/mettabase/hyperbase)\n"
        "!(import! &self lib/mettabase/snars)\n"
        f'!(believe! {_inh(subject, middle)} (:evidence 9.0 0.0 :source "{_src(sources[0])}"))\n'
        f'!(believe! {_inh(middle, conclusion)} (:evidence 9.0 0.0 :source "{_src(sources[1])}"))\n'
        "!(collapse (sn derive!))\n"
        f"!(let $a (ask! {target}) (derived $a))\n"
        f"!(why! {target})\n"
    )
    lines = _run(driver)
    derived_line = next((line for line in lines if _DERIVED_RE.search(line)), "")
    opinion = _parse_opinion([derived_line] if derived_line else lines)
    premises = [
        {
            "statement": match.group("text"),
            "opinion": {k: round(float(match.group(k)), 6) for k in ("b", "d", "u", "a")},
        }
        for line in lines
        for match in _PREMISE_RE.finditer(line)
    ]
    return {
        "claim": f"{subject} is {conclusion}",
        "engine": "SNARS deduction (Subjective-Logic NARS) on PeTTa",
        "derived": bool(derived_line),
        "opinion": opinion,
        "expectation": round(opinion["b"] + opinion["a"] * opinion["u"], 6) if opinion else None,
        "proof": {"rule": "deduction", "premises": premises},
        "why": next((line for line in lines if _WHY_RE.search(line)), ""),
    }


def derive_incident(request: str) -> dict[str, Any]:
    """Ground the deduction in the request itself: the premise that the raw log is
    risky is sourced from the request's own risk grounding (the parsed proposition /
    sentence the evidence layer found), not a GoalChainer-authored string. SNARS then
    deduces the forbidden verdict, with that request content as the premise's source."""

    from .evidence import extract_evidence

    evidence = extract_evidence(request)
    grounding = evidence.risk_grounding or "the incident request"
    result = derive(
        "publish_raw_log",
        "risky_action",
        "forbidden_action",
        sources=(grounding, "the incident privacy norm"),
    )
    result["grounding"] = grounding
    result["privacy_at_stake"] = evidence.privacy_at_stake
    result["evidence_provenance"] = evidence.provenance
    return result


def _run(driver: str) -> list[str]:
    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".metta", encoding="utf-8", dir=str(MB_ROOT)
    ) as handle:
        path = Path(handle.name)
        handle.write(driver)
    try:
        env = {
            **os.environ,
            "PYTHONPATH": f"{MB_ROOT}/src:{MB_ROOT}/lib:{petta_dir()}/python",
            "PETTA_PATH": str(petta_dir()),
        }
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
            cwd=str(MB_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
    finally:
        path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"SNARS run failed: {result.stderr[-1500:]}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _parse_opinion(lines: list[str]) -> dict[str, float]:
    for line in lines:
        match = _OPINION_RE.search(line)
        if match:
            b, d, u, a = (float(match.group(i)) for i in range(1, 5))
            return {"b": round(b, 6), "d": round(d, 6), "u": round(u, 6), "a": round(a, 6)}
    return {}

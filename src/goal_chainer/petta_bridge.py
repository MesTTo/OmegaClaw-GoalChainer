"""Optional PeTTaChainer bridge for generated-context evidence scoring."""

from __future__ import annotations

import contextlib
import os
import re
import sys
from pathlib import Path

from .models import CandidateAction, EvidenceProjection

STV_RE = re.compile(r"\(STV\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\)")


def parse_stv(text: str | None) -> tuple[float, float] | None:
    if not text:
        return None
    match = STV_RE.search(text)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


class FallbackReasoner:
    """Deterministic scorer used when PeTTaChainer is not enabled."""

    source = "scenario-default"

    def project(self, action: CandidateAction) -> EvidenceProjection:
        return EvidenceProjection(
            strength=action.default_strength,
            confidence=action.default_confidence,
            source=self.source,
            projection=None,
            proofs=(),
        )


class PeTTaChainerReasoner:
    """Score action evidence through PeTTaChainer.contextual_query."""

    source = "pettachainer-contextual-query"

    def __init__(self, repo_path: str | Path | None = None, quiet: bool = True) -> None:
        self.repo_path = Path(repo_path or os.environ.get("PETTACHAINER_PATH", "")).expanduser()
        if self.repo_path:
            sys.path.insert(0, str(self.repo_path))
            petta_python = _petta_python_path(self.repo_path)
            if petta_python is not None:
                sys.path.insert(0, str(petta_python))
        self.quiet = quiet
        from pettachainer import PeTTaChainer

        self._chainer_cls = PeTTaChainer

    def project(self, action: CandidateAction) -> EvidenceProjection:
        output_context = _suppress_process_output() if self.quiet else contextlib.nullcontext()
        with output_context:
            handler = self._chainer_cls()
            handler.add_atoms_no_check(list(action.evidence_atoms))
            result = handler.contextual_query(action.evidence_query, steps=20, timeout_sec=0)

        stv = parse_stv(result.projection)
        source = self.source
        if stv is None:
            proofs = tuple(str(proof) for proof in result.proofs)
            stv = _best_proof_stv(proofs) or (action.default_strength, action.default_confidence)
            source = f"{self.source}:proof-or-default"
        else:
            proofs = tuple(str(proof) for proof in result.proofs)

        return EvidenceProjection(
            strength=stv[0],
            confidence=stv[1],
            source=source,
            projection=result.projection,
            proofs=proofs,
        )


def _best_proof_stv(proofs: tuple[str, ...]) -> tuple[float, float] | None:
    values = [parse_stv(proof) for proof in proofs]
    present = [value for value in values if value is not None]
    if not present:
        return None
    return max(present, key=lambda item: item[0] * item[1])


def _petta_python_path(repo_path: Path) -> Path | None:
    configured = os.environ.get("PETTA_PATH")
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser() / "python")
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            repo_path.parent / "PeTTa" / "python",
            repo_path.parent / "petta" / "python",
            repo_path.parent / "PeTTa",
            repo_path.parent / "petta",
        ]
    )
    for candidate in candidates:
        if (candidate / "petta").is_dir() or (candidate / "pyproject.toml").exists():
            return candidate
    return None


@contextlib.contextmanager
def _suppress_process_output():
    saved_stdout = os.dup(1)
    saved_stderr = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(saved_stdout, 1)
        os.dup2(saved_stderr, 2)
        os.close(saved_stdout)
        os.close(saved_stderr)
        os.close(devnull)


def reasoner_from_env():
    if os.environ.get("GOALCHAINER_USE_PETTA") not in {"1", "true", "yes"}:
        return FallbackReasoner()
    return PeTTaChainerReasoner()

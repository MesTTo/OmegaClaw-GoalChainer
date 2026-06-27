"""Bridge to the user's mettabase stack: SH parsing + real semantic matching.

Two real capabilities, both the user's own machinery, no keyword matching:

1. The HyperBase AlphaBeta parser turns the request into Semantic-Hypergraph
   propositions (predicate-argument structure). It lives in the mettabase venv
   (spaCy `en_core_web_trf`), so we call it there via a subprocess.
2. Semantic concept matching uses the local Ollama embedding model
   (`qwen3-embedding`) — genuine paraphrase-robust similarity, the thing the
   mettabase token-hash fallback could not do. Same algorithm as mettabase's
   `semmatch` (embed query + candidates, cosine), pointed at the real model.

Both run in one subprocess call. If the venv or Ollama is unavailable the caller
falls back to the keyword extractor, so the rest of GoalChainer keeps working.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

MB_ROOT = Path(os.environ.get("GOALCHAINER_METTABASE_DIR", "/home/user/Dev/mettabase"))
MB_PYTHON = MB_ROOT / "hyperbase/.venv/bin/python"
OLLAMA_URL = os.environ.get("GOALCHAINER_OLLAMA_URL", "http://localhost:11434/api/embed")
OLLAMA_MODEL = os.environ.get("GOALCHAINER_OLLAMA_MODEL", "qwen3-embedding:0.6b")

# Runs inside the mettabase venv. Parses the request to SH propositions and scores
# it against each concept descriptor with real Ollama embeddings.
_WORKER = r'''
import json, math, sys, urllib.request

payload = json.load(sys.stdin)
request = payload["request"]
concepts = payload["concepts"]
ollama_url = payload["ollama_url"]
ollama_model = payload["ollama_model"]

def embed(text):
    req = urllib.request.Request(
        ollama_url,
        data=json.dumps({"model": ollama_model, "input": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())["embeddings"][0]

def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

# Embed each concept once.
concept_vecs = {name: embed(text) for name, text in concepts.items()}

# Per sentence: SH proposition, polarity (TNF peel), and concept scores. Polarity
# is structural -- "contains no private data" peels to negated=True -- which the
# caller uses to flip a matched concept's contribution.
sentences_out = []
propositions = []
try:
    from mettabase._vendor.hyperbase import get_parser
    from mettabase.hyperbase.typed_projection import edge_to_typed_metta
    from mettabase.snars.tnf import peel
    parser = get_parser("alphabeta", lang="en", max_parse_time=2.5)
    for sentence in [s.strip() for s in request.replace("\n", " ").split(".") if s.strip()]:
        negated = False
        result = parser.parse(sentence + ".")
        edge = result[0].edge if result else None
        if edge is not None:
            propositions.append(str(edge))
            try:
                _peeled, notes = peel(edge_to_typed_metta(edge))
                negated = bool(notes.negated)
            except Exception:
                negated = False
        vec = embed(sentence)
        scores = {name: cosine(vec, cvec) for name, cvec in concept_vecs.items()}
        sentences_out.append({"text": sentence, "negated": negated, "scores": scores})
except Exception as exc:  # parser is best-effort
    print(f"parser-error: {exc}", file=sys.stderr)

# Whole-request scores too, as a fallback signal.
request_scores = {name: cosine(embed(request), cvec) for name, cvec in concept_vecs.items()}

json.dump(
    {"propositions": propositions, "sentences": sentences_out, "request_scores": request_scores},
    sys.stdout,
)
'''


def available() -> bool:
    return MB_PYTHON.exists()


def parse_and_score(request: str, concepts: dict[str, str]) -> dict:
    """Return {'propositions': [...sh...], 'scores': {concept: cosine}} or raise."""

    proc = subprocess.run(
        [str(MB_PYTHON), "-c", _WORKER],
        input=json.dumps(
            {
                "request": request,
                "concepts": concepts,
                "ollama_url": OLLAMA_URL,
                "ollama_model": OLLAMA_MODEL,
            }
        ),
        cwd=str(MB_ROOT),
        env={**os.environ, "PYTHONPATH": f"{MB_ROOT}/src:{MB_ROOT}/lib"},
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"mettabase bridge failed: {proc.stderr[-1500:]}")
    return json.loads(proc.stdout)

#!/usr/bin/env bash
# Purpose: provision GoalChainer's semantic reader in the checkout this runs in: install the locked
# `semantic` extra into the project environment, then download the pinned cross-encoder
# anonymously and verify every file by SHA-256 into the model cache (GOALCHAINER_MODEL_CACHE, else
# $XDG_CACHE_HOME/goalchainer/models, by default ~/.cache/goalchainer/models).
#
# Exit codes: 0 ready; 1 a model file could not be downloaded; 2 usage or environment; 3 a model
# file failed verification and was removed. A second run on a ready cache re-verifies without
# downloading anything. `uv run --inexact` adds the extra without removing packages another sync
# installed, such as the dev extra the gate syncs first.
# am[implements a-jev-provision-user-cache-1016]

set -uo pipefail

repo="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "setup-semantic: run inside a GoalChainer checkout" >&2
  exit 2
}
cd "$repo" || exit 2
command -v uv >/dev/null || {
  echo "setup-semantic: uv is not on PATH" >&2
  exit 2
}
uv run --quiet --frozen --inexact --extra semantic python -m goal_chainer.semantic_models provision

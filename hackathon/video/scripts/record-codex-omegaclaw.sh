#!/usr/bin/env bash
# Purpose: record the single-shot session in which Codex drives Omega with one turn of tool calls to
# public/recordings/codex-omegaclaw.mp4. Codex really runs (network + the logged-in Codex path).
# See record-codex-omegaclaw-loop.sh for the multi-cycle run.
# am[implements a-op-drivers-tools-1018@a61ed7]
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$ROOT_DIR/scripts/record-cast.sh" \
  "$ROOT_DIR/scripts/recorders/live-codex-omegaclaw.sh" \
  "$ROOT_DIR/public/recordings/codex-omegaclaw.mp4" \
  104 30 "Codex drives Omega"

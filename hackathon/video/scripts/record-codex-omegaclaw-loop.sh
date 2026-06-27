#!/usr/bin/env bash
# Record the multi-cycle Codex-drives-OmegaClaw loop (decision -> solve -> send) to
# public/recordings/codex-omegaclaw-loop.mp4. Codex really runs across cycles
# (network + the logged-in Codex path); this is the film's headline footage.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$ROOT_DIR/scripts/record-cast.sh" \
  "$ROOT_DIR/scripts/recorders/live-codex-omegaclaw-loop.sh" \
  "$ROOT_DIR/public/recordings/codex-omegaclaw-loop.mp4" \
  104 30 "Codex drives OmegaClaw Core through the GoalChainer skill"

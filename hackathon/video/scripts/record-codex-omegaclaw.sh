#!/usr/bin/env bash
# Record the single-shot Codex-drives-OmegaClaw session (one command) to
# public/recordings/codex-omegaclaw.mp4. Codex really runs (network + the
# logged-in Codex path). See record-codex-omegaclaw-loop.sh for the multi-cycle run.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$ROOT_DIR/scripts/record-cast.sh" \
  "$ROOT_DIR/scripts/recorders/live-codex-omegaclaw.sh" \
  "$ROOT_DIR/public/recordings/codex-omegaclaw.mp4" \
  104 30 "Codex drives OmegaClaw Core"

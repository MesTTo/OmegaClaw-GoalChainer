#!/usr/bin/env bash
# Purpose: record the multi-cycle loop in which Codex drives Omega through the GoalChainer plugin's
# tools (pin, the incident review, the answer) to public/recordings/codex-omegaclaw-loop.mp4.
# Codex really runs across cycles (network + the logged-in Codex path); this is the film's
# headline footage.
# am[implements a-op-drivers-tools-1018@a61ed7]
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$ROOT_DIR/scripts/record-cast.sh" \
  "$ROOT_DIR/scripts/recorders/live-codex-omegaclaw-loop.sh" \
  "$ROOT_DIR/public/recordings/codex-omegaclaw-loop.mp4" \
  104 30 "Codex drives Omega through the GoalChainer plugin"

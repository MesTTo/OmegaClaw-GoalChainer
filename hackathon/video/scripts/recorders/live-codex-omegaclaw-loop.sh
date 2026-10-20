#!/usr/bin/env bash
# Purpose: record the film's headline session, Codex driving Omega through the GoalChainer plugin's
# tools across agent cycles (pin, the incident review, the answer), by running the real loop driver
# with CODEX_SHOW on, so the capture is the genuine run.
# am[implements a-od-drivers-1018@e5f805] am[implements a-op-drivers-tools-1018@a61ed7]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${OMEGACLAW_GOALCHAINER_DIR:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"

exec env \
  CODEX_SHOW=1 \
  DEMO_DELAY="${TERMINAL_DEMO_LINE_DELAY:-0.28}" \
  bash "$REPO_DIR/integrations/omegaclaw/codex_omegaclaw_loop.sh" "${1:-}"

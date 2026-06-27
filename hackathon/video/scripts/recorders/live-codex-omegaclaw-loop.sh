#!/usr/bin/env bash
# The session recorded for the film's headline: Codex driving OmegaClaw Core through
# the GoalChainer skill across agent cycles (decision -> solve -> send). Thin wrapper
# over the real loop with CODEX_SHOW on, so the capture is the genuine run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${OMEGACLAW_GOALCHAINER_DIR:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"

exec env \
  CODEX_SHOW=1 \
  DEMO_DELAY="${TERMINAL_DEMO_LINE_DELAY:-0.28}" \
  bash "$REPO_DIR/integrations/omegaclaw/codex_omegaclaw_loop.sh" "${1:-}"

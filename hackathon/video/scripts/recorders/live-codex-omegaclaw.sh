#!/usr/bin/env bash
# The session recorded for the film's headline scene: Codex drives OmegaClaw Core,
# which runs the GoalChainer skill. This is a thin wrapper over the real driver
# (integrations/omegaclaw/codex_drives_omegaclaw.sh) with CODEX_SHOW on, so the
# capture shows Codex's actual run (version, model, reasoning effort, the emitted
# command) and OmegaClaw evaluating it. No reconstruction.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${OMEGACLAW_GOALCHAINER_DIR:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"
DRIVER="$REPO_DIR/integrations/omegaclaw/codex_drives_omegaclaw.sh"

INCIDENT="${1:-Checkout is down. The on-call engineers want to paste the raw production logs, which include customer emails and order IDs, straight into the public incident channel so everyone can debug. Is that ok, and what should we actually post?}"

exec env \
  CODEX_SHOW=1 \
  DEMO_DELAY="${TERMINAL_DEMO_LINE_DELAY:-0.35}" \
  bash "$DRIVER" "$INCIDENT"

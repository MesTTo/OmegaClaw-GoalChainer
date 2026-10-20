#!/usr/bin/env bash
# Purpose: record the single-shot variant of the headline session, one Codex turn whose GoalChainer
# tool calls Omega evaluates on the incident review, by running the real driver
# (integrations/omegaclaw/codex_drives_omegaclaw.sh) with CODEX_SHOW on, so the capture shows
# Codex's actual run (version, model, reasoning effort, its tool calls) and Omega's answers. No
# reconstruction.
# am[implements a-od-drivers-1018@e5f805] am[implements a-op-drivers-tools-1018@a61ed7]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${OMEGACLAW_GOALCHAINER_DIR:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"
DRIVER="$REPO_DIR/integrations/omegaclaw/codex_drives_omegaclaw.sh"

INCIDENT="${1:-Checkout is down. The on-call engineers want to paste the raw production logs, which include customer emails and order IDs, straight into the public incident channel so everyone can debug. Is that ok, and what should we actually post?}"

exec env \
  CODEX_SHOW=1 \
  DEMO_DELAY="${TERMINAL_DEMO_LINE_DELAY:-0.35}" \
  bash "$DRIVER" "$INCIDENT"

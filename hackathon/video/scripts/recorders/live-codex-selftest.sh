#!/usr/bin/env bash
# Purpose: show that the stock Codex provider path the drivers use is ready, with no hosted call: the
# Codex CLI's version, its login as codex login status reads it from local auth storage, and the
# skills the installed GoalChainer plugin registers in Omega. A missing login fails the check.
# am[implements a-tr-selftest-stock-1018@9096d5] am[rests-on c-tr-login-status-local-1018@5bf8eb]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${OMEGACLAW_GOALCHAINER_DIR:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"
# shellcheck source=../../../../integrations/omegaclaw/_omega_lib.sh
source "$REPO_DIR/integrations/omegaclaw/_omega_lib.sh"

show() {
  printf '\033[1;36m$ %s\033[0m\n' "$*"
}

show "codex --version"
codex --version

# codex login status reports on standard error.
show "codex login status"
codex login status 2>&1

show "python integrations/omegaclaw/omega_metta.py --omega $OMEGACLAW_DIR registered"
omega_registered

printf '\n\033[1;32mCodex is logged in, and Omega offers the GoalChainer plugin'"'"'s skills.\033[0m\n'

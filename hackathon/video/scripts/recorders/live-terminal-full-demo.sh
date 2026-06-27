#!/usr/bin/env bash
set -euo pipefail

CODEX_AUTH_DIR="${OMEGACLAW_CORE_CODEX_AUTH_DIR:-/home/user/Dev/OmegaClaw-Core-codex-auth}"
CODEX_PYTHON="${CODEX_AUTH_PYTHON:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LINE_DELAY="${TERMINAL_DEMO_LINE_DELAY:-0.14}"

show() {
  printf '\033[1;36m$ %s\033[0m\n' "$*"
}

run_stream() {
  show "$*"
  "$@" 2>&1 | while IFS= read -r line; do
    printf '%s\n' "$line"
    sleep "$LINE_DELAY"
  done
  local status="${PIPESTATUS[0]}"
  if [[ "$status" != 0 ]]; then
    return "$status"
  fi
}

printf '\033[1;33mOmegaClaw terminal live demo\033[0m\n'
printf 'This run shows Codex leading a multi-step decision loop.\n\n'

cd "$CODEX_AUTH_DIR"

show "cd $CODEX_AUTH_DIR"
run_stream git branch --show-current
run_stream "$CODEX_PYTHON" lib_codex_auth.py

printf '\n\033[1;32mCodex provider is available. Starting the decision loop.\033[0m\n\n'
run_stream "$CODEX_PYTHON" -u "$SCRIPT_DIR/live-codex-goal-prompt.py"

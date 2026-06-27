#!/usr/bin/env bash
set -euo pipefail

show() {
  printf '\033[1;36m$ %s\033[0m\n' "$*"
}

CODEX_AUTH_DIR="${OMEGACLAW_CORE_CODEX_AUTH_DIR:-/home/user/Dev/OmegaClaw-Core-codex-auth}"
PYTHON_BIN="${CODEX_AUTH_PYTHON:-python3}"

cd "$CODEX_AUTH_DIR"

show "cd $CODEX_AUTH_DIR"
show "git branch --show-current"
git branch --show-current

show "$PYTHON_BIN lib_codex_auth.py"
"$PYTHON_BIN" lib_codex_auth.py

show "$PYTHON_BIN codex_chat.py --selftest"
"$PYTHON_BIN" codex_chat.py --selftest

printf '\n\033[1;32mCodex provider is available through the logged-in subscription path.\033[0m\n'

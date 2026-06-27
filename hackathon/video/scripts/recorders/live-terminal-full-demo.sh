#!/usr/bin/env bash
set -euo pipefail

CODEX_AUTH_DIR="${OMEGACLAW_CORE_CODEX_AUTH_DIR:-/home/user/Dev/OmegaClaw-Core-codex-auth}"
CODEX_PYTHON="${CODEX_AUTH_PYTHON:-python3}"
GOALCHAINER_DIR="${OMEGACLAW_GOALCHAINER_DIR:-/home/user/Dev/OmegaClaw-GoalChainer}"
PETTACHAINER_DIR="${PETTACHAINER_DIR:-/home/user/Dev/PeTTaChainer}"
GOALCHAINER_PYTHON="${GOALCHAINER_PYTHON:-python3}"
LINE_DELAY="${TERMINAL_DEMO_LINE_DELAY:-0.14}"
SECTION_PAUSE="${TERMINAL_DEMO_SECTION_PAUSE:-1.2}"

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
printf 'This run shows the Codex provider check, the GoalChainer decision demo, and the PeTTaChainer audit proof.\n\n'

cd "$CODEX_AUTH_DIR"

show "cd $CODEX_AUTH_DIR"
run_stream git branch --show-current
run_stream "$CODEX_PYTHON" lib_codex_auth.py
run_stream "$CODEX_PYTHON" codex_chat.py --selftest

printf '\n\033[1;32mCodex provider is available through the logged-in subscription path.\033[0m\n'
sleep "$SECTION_PAUSE"

printf '\n\033[1;33mNow running the GoalChainer decision demo and PeTTaChainer audit proof.\033[0m\n\n'

cd "$GOALCHAINER_DIR"

show "cd $GOALCHAINER_DIR"
run_stream env PYTHONPATH=src "$GOALCHAINER_PYTHON" -m goal_chainer.cli demo
sleep "$SECTION_PAUSE"

cd "$PETTACHAINER_DIR"

show "cd $PETTACHAINER_DIR"
run_stream "$GOALCHAINER_PYTHON" artifacts/showcase/showcase-verify-all.py artifacts/showcase
sleep "$SECTION_PAUSE"

run_stream sed -n '1,14p' artifacts/showcase/showcase-audit-verdict.md

printf '\n\033[1;32mTerminal demo complete: the redacted summary is selected, the raw log is blocked, and the audit proof verifies.\033[0m\n'

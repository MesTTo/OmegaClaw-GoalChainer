#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${GOALCHAINER_REPO_DIR:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"
PYTHON_BIN="${GOALCHAINER_PYTHON:-python3}"
LINE_DELAY="${TERMINAL_DEMO_LINE_DELAY:-0.12}"
export GOALCHAINER_CODEBASE_DEMO_REPO="${GOALCHAINER_CODEBASE_DEMO_REPO:-$REPO_DIR/artifacts/codebase-demo/checkout-status-video}"

PROMPT="The checkout status repo is leaking customer data in incident updates. Read the docs and tests, find the real cause in code, and patch it without dropping useful operational context."

show() {
  printf '\033[1;36m$ %s\033[0m\n' "$*"
}

run_stream() {
  show "$*"
  run_stream_output "$@"
}

run_stream_label() {
  local label="$1"
  shift
  show "$label"
  run_stream_output "$@"
}

run_stream_output() {
  "$@" 2>&1 | while IFS= read -r line; do
    printf '%s\n' "$line"
    sleep "$LINE_DELAY"
  done
  local status="${PIPESTATUS[0]}"
  if [[ "$status" != 0 ]]; then
    return "$status"
  fi
}

printf '\033[1;33mOmegaClaw codebase repair demo\033[0m\n'
printf 'The agent gets a natural-language bug report, then uses a generated repo as its working environment.\n\n'

show "cd $REPO_DIR"
cd "$REPO_DIR"

printf '\033[1;35mUser prompt\033[0m\n%s\n\n' "$PROMPT"

run_stream_label \
  "env PYTHONPATH=src $PYTHON_BIN -m goal_chainer.cli codebase-demo --request \"$PROMPT\"" \
  env PYTHONPATH=src "$PYTHON_BIN" -m goal_chainer.cli codebase-demo --request "$PROMPT"

printf '\n\033[1;32mGenerated repo evidence\033[0m\n'
run_stream git -C "$GOALCHAINER_CODEBASE_DEMO_REPO" log --oneline -2
run_stream "$PYTHON_BIN" -m pytest -q "$GOALCHAINER_CODEBASE_DEMO_REPO"

printf '\n\033[1;32mDone. The generated repo now contains the fixed commit.\033[0m\n'

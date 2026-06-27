#!/usr/bin/env bash
set -euo pipefail

show() {
  printf '\033[1;36m$ %s\033[0m\n' "$*"
}

GOALCHAINER_DIR="${OMEGACLAW_GOALCHAINER_DIR:-/home/user/Dev/OmegaClaw-GoalChainer}"
PETTACHAINER_DIR="${PETTACHAINER_DIR:-/home/user/Dev/PeTTaChainer}"
PYTHON_BIN="${GOALCHAINER_PYTHON:-python3}"

cd "$GOALCHAINER_DIR"

show "cd $GOALCHAINER_DIR"
show "PYTHONPATH=src $PYTHON_BIN -m goal_chainer.cli demo"
PYTHONPATH=src "$PYTHON_BIN" -m goal_chainer.cli demo
sleep 8

printf '\n'
cd "$PETTACHAINER_DIR"

show "cd $PETTACHAINER_DIR"
show "$PYTHON_BIN artifacts/showcase/showcase-verify-all.py artifacts/showcase"
"$PYTHON_BIN" artifacts/showcase/showcase-verify-all.py artifacts/showcase
sleep 4

show "sed -n '1,14p' artifacts/showcase/showcase-audit-verdict.md"
sed -n '1,14p' artifacts/showcase/showcase-audit-verdict.md

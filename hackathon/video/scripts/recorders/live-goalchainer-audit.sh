#!/usr/bin/env bash
# Purpose: record a bounded GoalChainer review of the checkout incident: the request file, the
# result the request command computes from it, and the provenance that same result records.
set -euo pipefail

show() {
  printf '\033[1;36m$ %s\033[0m\n' "$*"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GOALCHAINER_DIR="${OMEGACLAW_GOALCHAINER_DIR:-/home/user/Dev/OmegaClaw-GoalChainer}"
PYTHON_BIN="${GOALCHAINER_PYTHON:-python3}"
# The review's explicit selection: the packaged incident domain, and the readings engineering and
# support stated, each attributed to who said it as a human-asserted observation.
# am[implements a-cd-rec-audit-1018@09ddac] am[rests-on c-cd-rec-snapshot-behaviour-1018@8a11dd]
REQUEST_FILE="$SCRIPT_DIR/incident-review-request.json"
# The provenance shown is the result's own record of its inputs, read from the result this
# recording computed; no separate verifier or earlier artifact stands in for it.
# am[implements a-cd-rec-audit-provenance-1018@a15419] am[rests-on c-cd-rec-showcase-is-historical-1018@5b8237]
PROVENANCE='import json, sys, goalchainer_render; print(goalchainer_render.render_provenance(json.load(sys.stdin)))'

cd "$GOALCHAINER_DIR"

show "cd $GOALCHAINER_DIR"
show "cat $REQUEST_FILE"
cat "$REQUEST_FILE"
sleep 4

# A refused request prints its typed error and ends the recording with the command's status.
# am[implements a-integrate-request-budget-surface-1018@d6882c] am[implements a-cd-rec-audit-1018@09ddac]
show "PYTHONPATH=src $PYTHON_BIN -m goal_chainer.cli request --input $REQUEST_FILE --inference-budget 1000000000 --timeout-seconds 600"
status=0
result="$(PYTHONPATH=src "$PYTHON_BIN" -m goal_chainer.cli request --input "$REQUEST_FILE" --inference-budget 1000000000 --timeout-seconds 600)" || status=$?
printf '%s\n' "$result"
[ "$status" -eq 0 ] || exit "$status"
sleep 8

printf '\n'
# am[implements a-cd-rec-audit-provenance-1018@a15419]
show "printf '%s' \"\$result\" | PYTHONPATH=$SCRIPT_DIR $PYTHON_BIN -c '$PROVENANCE'"
printf '%s' "$result" | PYTHONPATH="$SCRIPT_DIR" "$PYTHON_BIN" -c "$PROVENANCE"
sleep 4

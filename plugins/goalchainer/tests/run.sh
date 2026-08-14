#!/bin/sh
# GoalChainer plugin suite. A file passes iff it exits 0 and prints no failures.
#
# The plugin is installed into an OmegaClaw-Core checkout, so the suite runs
# from that checkout's root: the loader resolves "./plugins/goalchainer" and the
# bootstrap registers the checkout from its parent directory. Point
# OMEGACLAW_DIR at the host checkout when this plugin lives elsewhere.
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
GC_ROOT=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
OMEGACLAW_DIR="${OMEGACLAW_DIR:-$GC_ROOT/external/OmegaClaw-Core}"
PETTA_DIR="${PETTA_DIR:-/home/user/Dev/PeTTa}"
SWIPL_BIN="${SWIPL_BIN:-swipl}"
if [ ! -d "$OMEGACLAW_DIR/plugins/goalchainer" ]; then
  echo "error: $OMEGACLAW_DIR has no plugins/goalchainer; install the plugin first" >&2
  exit 1
fi
# The engine is the omegaclaw-goalchainer package; the plugin only py-calls it.
PYTHONPATH="$GC_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
cd "$OMEGACLAW_DIR" || exit 1
FAIL=0; PASS=0
for f in "$SCRIPT_DIR"/test_*.metta; do
  [ -f "$f" ] || continue
  name=$(basename "$f")
  out=$(timeout -k 5 "${TEST_TIMEOUT:-600}" "$SWIPL_BIN" --stack_limit=8g -q \
        -s "$PETTA_DIR/src/main.pl" -- "$f" --silent </dev/null 2>&1)
  code=$?
  ok=$(printf '%s\n' "$out" | grep -c '✅')
  bad=$(printf '%s\n' "$out" | grep -c '❌')
  if [ "$code" -eq 0 ] && [ "$bad" -eq 0 ]; then
    echo "PASS  $name  ($ok checks)"; PASS=$((PASS + 1))
  else
    echo "FAIL  $name  ($ok ok, $bad failed, exit $code)"
    printf '%s\n' "$out" | grep -E '❌|Error|ERROR' | head -5; FAIL=$((FAIL + 1))
  fi
done
echo "----"; echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "ALL GOALCHAINER PLUGIN TESTS PASSED"
exit $FAIL

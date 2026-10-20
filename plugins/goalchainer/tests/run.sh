#!/usr/bin/env bash
# Purpose: run the GoalChainer plugin's MeTTa suite on pymetta from its OmegaClaw-Core checkout; a file
# passes iff it exits 0, reports no failed check and reports exactly as many checks as its source
# declares test forms, at least one (suite_accounting.py), and the run fails when there is no suite
# to run. The skills read text from the committed Jev replay cache and never ask the hosted service.
#
#   plugins/goalchainer/tests/run.sh [suite.metta ...]    the suites named, else every test_*.metta here
#
# The plugin is installed into an OmegaClaw-Core checkout, so the suite runs
# from that checkout's root: the loader resolves "./plugins/goalchainer" and the
# bootstrap registers the checkout from its parent directory. Point
# OMEGACLAW_DIR at the host checkout when this plugin lives elsewhere.
# Each file runs with python -m metta run in the interpreter the plugin's install recorded, the one
# the drivers' omega_python answers, or GOALCHAINER_PYTHON.
# A file runs until it finishes: the skills' own callers bound their work, and a
# runner deadline would report an unfinished run as a failed check.
# am[implements a-rt-vendored-defaults-1016@182749] am[implements a-rt-skill-process-boundary-1016@a36729]
# am[implements a-rt-oh-plugin-runner-1018@6466fc] am[implements a-integrate-mettaspeak-assertion-accounting-1019@905c82]
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
GC_ROOT=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
OMEGACLAW_DIR="${OMEGACLAW_DIR:-$GC_ROOT/external/OmegaClaw-Core}"
export OMEGACLAW_DIR
if [ ! -d "$OMEGACLAW_DIR/plugins/goalchainer" ]; then
  echo "error: $OMEGACLAW_DIR has no plugins/goalchainer; install the plugin first" >&2
  exit 1
fi
# The suites to run, as absolute paths since the run moves into the Omega checkout. None at all is a
# failure, as a suite with no test form is: a run that checked nothing has passed nothing.
# am[implements a-integrate-mettaspeak-assertion-accounting-1019@905c82]
suites=()
if [ "$#" -gt 0 ]; then
  for suite in "$@"; do
    [ -f "$suite" ] || { echo "error: no suite $suite" >&2; exit 1; }
    suites+=("$(cd -- "$(dirname -- "$suite")" && pwd)/$(basename -- "$suite")")
  done
else
  for suite in "$SCRIPT_DIR"/test_*.metta; do
    [ -f "$suite" ] && suites+=("$suite")
  done
fi
if [ "${#suites[@]}" -eq 0 ]; then
  echo "error: no test_*.metta suite in $SCRIPT_DIR, so nothing would be checked" >&2
  exit 1
fi
# shellcheck source=../../../integrations/omegaclaw/_omega_lib.sh
. "$GC_ROOT/integrations/omegaclaw/_omega_lib.sh"
PYTHON=$(omega_python) || exit 1
# pymetta's Python needs only gcskill, which runs GoalChainer as a child of the
# interpreter the installer recorded, this suite's helpers, and the installed
# plugin's directory, which Omega's loader puts on sys.path and which holds the
# goalchainer_host.py naming that interpreter.
# am[implements a-oc-plugin-host-module-1018@180dc9]
PYTHONPATH="$GC_ROOT/src:$SCRIPT_DIR:$OMEGACLAW_DIR/plugins/goalchainer${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
# The suite's decisions read their text through Jev in the skill's child process, which inherits
# these, so they replay the answers pytest replays whatever the environment holds: no capture runs
# this suite and its skill processes carry no request cap, so the switch is set rather than
# defaulted and no TypeSafe key reaches them. The cache stays a default a caller can point elsewhere.
# am[implements a-jev-plugin-suite-replays-cache-1017@04bf98] am[implements a-tbr-plugin-suite-replays-1018@53843d]
# am[rests-on c-tbr-no-capture-runs-plugin-suite-1018@85adcf]
GOALCHAINER_JEV_CACHE="${GOALCHAINER_JEV_CACHE:-$GC_ROOT/tests/data/jev}"
GOALCHAINER_JEV_OFFLINE=1
export GOALCHAINER_JEV_CACHE GOALCHAINER_JEV_OFFLINE
unset TYPESAFE_API_KEY
cd "$OMEGACLAW_DIR" || exit 1
FAIL=0; PASS=0
for f in "${suites[@]}"; do
  # pymetta refuses an SWI-Prolog home other than its own, which a pymetta parent process exports.
  out=$(env -u SWI_HOME_DIR "$PYTHON" -m metta run "$f" </dev/null 2>&1)
  code=$?
  # The run's checks counted against the test forms its source declares, in the same interpreter.
  # am[implements a-integrate-mettaspeak-assertion-accounting-1019@905c82]
  if verdict=$(printf '%s\n' "$out" | "$PYTHON" "$SCRIPT_DIR/suite_accounting.py" "$f" "$code"); then
    echo "$verdict"; PASS=$((PASS + 1))
  else
    echo "${verdict:-FAIL  $(basename "$f")  (its checks could not be counted)}"
    printf '%s\n' "$out" | grep -E '❌|Error|ERROR' | head -5; FAIL=$((FAIL + 1))
  fi
done
echo "----"; echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "ALL GOALCHAINER PLUGIN TESTS PASSED"
exit $FAIL

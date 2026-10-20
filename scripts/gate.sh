#!/usr/bin/env bash
# Purpose: provision GoalChainer's pinned dependencies in the checkout it runs in, then run the whole
# gate (pytest with zero skips, the Lean contracts and the OmegaClaw plugin's MeTTa suite) and exit
# nonzero on any failure or skip.
#
# Usage, from anywhere inside a checkout (a battery tree, a fresh clone, a working tree):
#   scripts/gate.sh                  provision, then the whole gate
#   scripts/gate.sh <pytest args>    provision, then only pytest with those arguments
#
# The whole gate is pytest, the Lean checker and the OmegaClaw plugin's own MeTTa suite,
# plugins/goalchainer/tests/run.sh, run from the installed OmegaClaw-Core. Nothing it runs needs
# Node (am[implements a-tk-packaging-1018@7cd2e8]).
#
# It follows the README's install steps in their order, so the gate exercises what a user runs:
# every submodule at exactly the commit the checked-out revision records, the native wheel
# directories scripts/native-wheels.py place verifies, `uv sync --frozen --all-extras` and
# native-wheels.py check on what it installed, ./scripts/setup-semantic.sh where the revision has
# it, ./scripts/setup-omegaclaw.sh into that OmegaClaw-Core, which records the locked environment's
# interpreter for the plugin's skills, then the tests. GOALCHAINER_NATIVE_WHEELS names the
# directory holding the native builds when the checkout has no native-wheels/ of its own.
# Submodules are cloned from the .gitmodules URL. To gate
# pins no public ref holds yet, the caller redirects those URLs with git's own configuration
# environment (GIT_CONFIG_COUNT and url.<mirror>.insteadOf); this script never picks a source by
# itself.
#
# The tests ask no machine service: Jev's answers replay offline from the committed cache,
# tests/data/jev, unless a capture names its own; a test that cannot read what it needs fails or
# skips, and a skip fails the gate with its reason (am[implements a-rt-runtime-resolves-markdown-1017@0e4c7a]).
# Two setup steps may download, and both fetch pinned public bytes and check every file's
# hash. setup-semantic.sh puts the semantic models in their cache (GOALCHAINER_MODEL_CACHE, else
# the user cache $XDG_CACHE_HOME/goalchainer/models). `tests/test_semantic_sleep.py --prepare-base`
# builds the sleep tests' tiny base model from an 18 MB pinned public revision, in
# GOALCHAINER_SLEEP_TEST_BASE when the caller names an absolute path, else in this checkout's
# ai-tmp/gate-sleep-base, which later runs re-verify and reuse. Everything after these two runs
# with HF_HUB_OFFLINE=1, so model loads read verified files only and a gate never resolves a model
# revision remotely.
#
# It changes only nested checkouts it created itself, which it lists in ai-tmp/gate-provisioned, and
# resets those to exactly their pins, untracked files included, whatever state an earlier run left
# them in, since nothing in them is anyone's work: a plugin uninstall by an older revision's
# installer can leave a file the newer one generates. A nested checkout it did not create must
# already be at its pin with no tracked changes and no plugin install, or the gate stops with the
# path named and changes nothing; such a checkout is only read. The plugin install changes the Omega
# checkout it goes into, so when external/OmegaClaw-Core is one the gate did not create, the install
# goes into the gate's own clone of the same pin, ai-tmp/gate-omegaclaw-core, cloned from that
# checkout with no network, and the plugin suite runs there. A fresh clone whose pin it cannot check
# out is removed again, so no later run inherits it.
# am[implements a-rt-gate-1016@93a6c6] am[implements a-gb-own-clone-1018@b10c8f]

set -uo pipefail

die() {
  echo "gate: error: $*" >&2
  exit 2
}

repo="$(git rev-parse --show-toplevel 2>/dev/null)" || die "run inside a GoalChainer checkout"
cd "$repo" || die "cannot enter $repo"
[ -f pyproject.toml ] && [ -f .gitmodules ] || die "$repo is not a GoalChainer checkout"

revision="$(git rev-parse HEAD)"
run_dir="$repo/ai-tmp/gate-${revision:0:12}-$(date +%Y%m%dT%H%M%S)-$$"
mkdir -p "$run_dir/tmp" || die "cannot create $run_dir"
export TMPDIR="$run_dir/tmp"
owned_list="$repo/ai-tmp/gate-provisioned"
touch "$owned_list" || die "cannot write $owned_list"
echo "gate: checkout $repo at $revision; artifacts in $run_dir"

owned() {
  grep -qxF -- "$1" "$owned_list"
}

# A plugin install leaves a receipt in OmegaClaw-Core. In a checkout this gate created, the reset
# below returns it to its pin with every installed file gone, whichever revision's installer made
# the install, so only a checkout the gate did not create is checked here: it must carry none.
# am[implements a-rt-incorporate-deontic-1016@6ea255]
core=external/OmegaClaw-Core
if compgen -G "$core/.*-receipt.json" >/dev/null && ! owned "$core"; then
  die "$core carries a plugin install this gate did not make; run" \
    "./scripts/setup-omegaclaw.sh --uninstall there first"
fi

# <path>, a checkout this gate owns, at exactly <pin> with nothing else in it: cloned from <source>
# and listed as owned when it is missing, given the pin from <source> when it lacks it, then checked
# out there and cleaned of untracked files. A fresh clone whose pin it cannot check out is removed.
# am[implements a-rt-gate-1016@93a6c6] am[implements a-gb-own-clone-1018@b10c8f]
own_at_pin() {
  local path="$1" pin="$2" source="$3"
  if [ -e "$path/.git" ]; then
    git -C "$path" cat-file -e "$pin^{commit}" 2>/dev/null \
      || git -C "$path" fetch --quiet "$source" "$pin" \
      || die "pin $pin for $path is not reachable from $source"
    git -C "$path" checkout --quiet --force --detach "$pin" || die "cannot check out $pin in $path"
    git -C "$path" clean --quiet -ffdx || die "cannot clean $path"
  else
    if [ -d "$path" ]; then
      rmdir "$path" || die "$path exists, is not a checkout and is not empty"
    fi
    git clone --quiet --no-checkout "$source" "$path" || die "cannot clone $source into $path"
    echo "$path" >>"$owned_list"
    if ! git -C "$path" checkout --quiet --detach "$pin"; then
      rm -rf "$path"
      die "pin $pin for $path is not reachable from $source"
    fi
  fi
}

# Time: one clone or checkout per submodule, s = number of submodules in .gitmodules.
# am[implements a-rt-gate-1016@93a6c6]
provision_submodule() {
  local name="$1" path="$2" url pin have
  url="$(git config -f .gitmodules --get "submodule.$name.url")" || die "$name has no url"
  pin="$(git rev-parse "HEAD:$path")" || die "$path has no gitlink in HEAD"
  if [ -e "$path/.git" ] && ! owned "$path"; then
    have="$(git -C "$path" rev-parse HEAD)"
    if [ -n "$(git -C "$path" status --porcelain --untracked-files=no)" ]; then
      die "$path has tracked changes; refusing to move it to $pin"
    elif [ "$have" != "$pin" ]; then
      die "$path is at $have, not the pinned $pin, and this gate did not create it"
    fi
  else
    own_at_pin "$path" "$pin" "$url"
  fi
  echo "gate: $path at $pin from $url"
}

while read -r key path; do
  name="${key#submodule.}"
  provision_submodule "${name%.path}" "$path"
done < <(git config -f .gitmodules --get-regexp '^submodule\..*\.path$')

# The plugin install copies plugins/goalchainer into the Omega checkout it goes into, appends a
# record to its tracked config/plugins.yaml and leaves its receipt there, so it goes only into a
# checkout this gate owns: external/OmegaClaw-Core when the gate cloned it, otherwise the gate's own
# clone of the same pin, ai-tmp/gate-omegaclaw-core, cloned from that checkout, which the
# provisioning above found at its pin, so no network is needed. That clone is listed and reset like
# every clone the gate owns, so the checkout the gate did not create is never changed and every
# later run finds it as it was.
# am[implements a-gb-own-clone-1018@b10c8f]
install_core="$core"
if ! owned "$core"; then
  install_core=ai-tmp/gate-omegaclaw-core
  if [ -e "$install_core" ] && ! owned "$install_core"; then
    die "$install_core exists and this gate did not create it"
  fi
  own_at_pin "$install_core" "$(git rev-parse "HEAD:$core")" "$repo/$core"
  echo "gate: $install_core at the pin of $core, for the plugin install"
fi

# pymetta brings its own SWI-Prolog, and nothing the gate runs starts PeTTa or a system swipl.
# am[implements a-rt-pv-gate-1018@6a751d]
command -v uv >/dev/null || die "uv is not on PATH"
echo "gate: uv $(uv --version | cut -d' ' -f2)"

# The native wheels the lock installs, pymetta's, come from content-addressed directories under
# native-wheels/ that no index serves, and uv reads them before it does anything else, so place
# verifies each against its MANIFEST, linking it from GOALCHAINER_NATIVE_WHEELS where the checkout
# lacks it, before uv sync; after it, check holds what uv sync installed to the published wheel byte
# for byte. Their codes are 1 missing, 2 usage, 3 integrity and 4 an unsupported host, reported here
# while the gate exits 2.
# am[implements a-rt-n2ic-gate-1018@85bccd]
uv run --quiet scripts/native-wheels.py place >"$run_dir/native-place.log" 2>&1
native_status=$?
[ "$native_status" -eq 0 ] || die "scripts/native-wheels.py place exited $native_status" \
  "(1 missing, 2 usage, 3 integrity); see $run_dir/native-place.log"
echo "gate: native wheels verified in $(tr '\n' ' ' <"$run_dir/native-place.log")"

# Every extra the revision declares, so a revision with the semantic extra gets its models' code.
uv sync --quiet --frozen --all-extras || die "uv sync --frozen --all-extras failed"
python="$repo/.venv/bin/python"
echo "gate: $("$python" --version) at $repo/.venv"
"$python" scripts/native-wheels.py check >"$run_dir/native-check.log" 2>&1
native_status=$?
[ "$native_status" -eq 0 ] || die "scripts/native-wheels.py check exited $native_status" \
  "(1 missing, 2 usage, 3 the install differs, 4 unsupported host); see $run_dir/native-check.log"
sed 's/^/gate: /' "$run_dir/native-check.log"
# The setup's own codes are 1 download, 2 usage and 3 integrity. The gate reports the code and
# exits 2, its own code for a gate that could not run, so 1 keeps meaning a failing test.
# am[implements a-rt-gate-1016@93a6c6]
if [ -x scripts/setup-semantic.sh ]; then
  (unset HF_HUB_OFFLINE; ./scripts/setup-semantic.sh) >"$run_dir/semantic-setup.log" 2>&1
  semantic_status=$?
  [ "$semantic_status" -eq 0 ] || die "scripts/setup-semantic.sh exited $semantic_status" \
    "(1 download, 2 usage, 3 integrity); see $run_dir/semantic-setup.log"
  echo "gate: $(tail -n 1 "$run_dir/semantic-setup.log")"
fi
# The sleep tests' base model is a fixture the test file itself builds and re-verifies: a fixture
# whose bytes differ from the pinned construction fails the step, and so does a failed download.
# am[implements a-rt-gate-sleep-base-1016@668661] am[rests-on c-rt-prepare-base-reverifies-1016@cfcb5f]
sleep_base="${GOALCHAINER_SLEEP_TEST_BASE:-$repo/ai-tmp/gate-sleep-base}"
case "$sleep_base" in
  /*) ;;
  *) die "GOALCHAINER_SLEEP_TEST_BASE must be an absolute path, not $sleep_base" ;;
esac
"$python" tests/test_semantic_sleep.py --prepare-base "$sleep_base" >"$run_dir/sleep-base.log" 2>&1
sleep_status=$?
[ "$sleep_status" -eq 0 ] || die "tests/test_semantic_sleep.py --prepare-base exited $sleep_status;" \
  "see $run_dir/sleep-base.log"
export GOALCHAINER_SLEEP_TEST_BASE="$sleep_base"
echo "gate: sleep test base verified in $sleep_base: $(tail -n 1 "$run_dir/sleep-base.log")"
export HF_HUB_OFFLINE=1
# After uv sync: the GoalChainer plugin records, and first runs one skill in, the interpreter of
# the environment uv sync made, in the Omega checkout chosen above, which OMEGACLAW_DIR names to
# the installer.
# am[implements a-gb-own-clone-1018@b10c8f]
OMEGACLAW_DIR="$repo/$install_core" ./scripts/setup-omegaclaw.sh >"$run_dir/plugin-install.log" 2>&1 \
  || die "plugin install failed; see $run_dir/plugin-install.log"
echo "gate: OmegaClaw plugins installed into $install_core"

junit="$run_dir/pytest-junit.xml"
"$python" -m pytest -ra -p no:cacheprovider --junitxml="$junit" "$@"
pytest_status=$?

# A skip is a test that did not run, so it fails the gate with the reason pytest gave for it.
skipped="$("$python" - "$junit" <<'PY'
import sys
import xml.etree.ElementTree as ElementTree

skipped = [
    (case.get("classname"), case.get("name"), skip.get("message", ""))
    for case in ElementTree.parse(sys.argv[1]).iter("testcase")
    for skip in case.findall("skipped")
]
for classname, name, message in skipped:
    print(f"gate: skipped {classname}::{name}: {message}", file=sys.stderr)
print(len(skipped))
PY
)" || skipped="unreadable"

plugin_status=not-run
math_status=not-run
if [ "$#" -eq 0 ]; then
  # am[implements a-math-delivery-1016@42d527]
  scripts/check-mathematical-contracts.sh >"$run_dir/math.log" 2>&1
  math_status=$?
  echo "gate: mathematical contracts logged in $run_dir/math.log"
  OMEGACLAW_DIR="$repo/$install_core" bash plugins/goalchainer/tests/run.sh
  plugin_status=$?
fi

echo "gate-verdict revision=$revision pytest=$pytest_status skipped=$skipped" \
  "plugin_metta=$plugin_status math=$math_status"
if [ "$pytest_status" -ne 0 ] || [ "$skipped" != 0 ]; then
  exit 1
fi
for status in "$plugin_status" "$math_status"; do
  if [ "$status" != not-run ] && [ "$status" -ne 0 ]; then
    exit 1
  fi
done
exit 0

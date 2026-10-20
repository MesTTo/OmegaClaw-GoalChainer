#!/usr/bin/env bash
# Purpose: build the Omega agent image with GoalChainer's plugin installed, from this checkout's
# committed tree and its pinned external/OmegaClaw-Core, on upstream's published Omega image, with
# the native wheel directories its lock installs from, verified, as a named build context.
#
#   scripts/build-omega-image.sh [docker build option ...]
#
# The context holds two trees taken with git archive, GoalChainer at HEAD and Omega at the commit
# HEAD's gitlink pins, so nothing uncommitted, no plugin install and no local environment reaches
# the image. The native wheel directories HEAD's uv.lock names come from the store
# GOALCHAINER_NATIVE_WHEELS names, or from this checkout's native-wheels/ when it is unset. IMAGE
# names the tag, goalchainer-omega:<revision> by default; the Dockerfile's OMEGA_IMAGE argument names
# the base.
# am[implements a-oc-plugin-stock-start-1018@f9e0a5]
set -euo pipefail

repo="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$repo"

# The image runs its agent as nobody, which must read both trees, so their modes are git's 0644 and
# 0755 however the caller's umask is set, as reproducible builds normalise the umask: tar extracts
# git archive's 0664 and 0775 under the umask in force, and under 0077 the image's sources are
# root's alone and the agent cannot start.
# am[implements a-irp-build-umask-022-1018@3f2c7e] am[addresses i-irp-build-umask-modes-1018@0eccb5]
umask 022
revision="$(git rev-parse HEAD)"
pin="$(git rev-parse HEAD:external/OmegaClaw-Core)"
if ! git -C external/OmegaClaw-Core cat-file -e "$pin^{commit}" 2>/dev/null; then
  echo "error: external/OmegaClaw-Core lacks the pinned $pin; run: git submodule update --init" >&2
  exit 1
fi

# The work directory goes however the script ends; the copies keep the store's read-only modes, so
# their owner's write bits come back first, or rm could not empty their directories.
work="$repo/ai-tmp/omega-image-${revision:0:12}-$$"
trap 'chmod -R u+w "$work" 2>/dev/null; rm -rf "$work"' EXIT
context="$work/context"
mkdir -p "$context/goalchainer" "$context/omega" "$work/native-wheels"
git archive HEAD | tar -x -C "$context/goalchainer"
git -C external/OmegaClaw-Core archive "$pin" | tar -x -C "$context/omega"

# The native wheel directories HEAD's lock installs from, pymetta's among them, which no index serves.
# HEAD's own verifier, scripts/native-wheels.py place, run as the gate runs it, checks each against
# its MANIFEST and links it into the archived tree; the build gets copies of exactly those, links
# followed, as the named context native-wheels, and the archived tree loses the links, so neither a
# wheel nor a host path reaches the image. Any source place accepts holds the same bytes. A missing
# or altered directory stops the build here, with place's status, before Docker starts.
# am[implements a-irp-image-native2-wheel-1018@ec11d2] am[rests-on c-irp-n2-source-immaterial-1018@63bd66]
store="${GOALCHAINER_NATIVE_WHEELS:-}"
[ -n "$store" ] || [ ! -d "$repo/native-wheels" ] || store="$repo/native-wheels"
directories="$(GOALCHAINER_NATIVE_WHEELS="$store" uv run --quiet "$context/goalchainer/scripts/native-wheels.py" place)"
while IFS= read -r directory; do
  [ -z "$directory" ] || cp -RL "$context/goalchainer/$directory" "$work/native-wheels/"
done <<<"$directories"
rm -rf "$context/goalchainer/native-wheels"

# Everything the build reads comes from the archived trees, never the working ones: Omega's version is
# the pinned commit's tags as the pinned commit's own helper formats them, and the Dockerfile is HEAD's.
# am[implements a-integrate-image-build-committed-inputs-1018@f4fcef]
version="$(python3 - "$context/omega" "$repo/external/OmegaClaw-Core" "$pin" <<'PY'
import subprocess, sys
sys.path.insert(0, sys.argv[1])
from src.helper import _format_omega_version
described = subprocess.run(["git", "-C", sys.argv[2], "describe", "--tags", "--always", sys.argv[3]],
                           check=True, capture_output=True, text=True).stdout
print(_format_omega_version(described))
PY
)"

image="${IMAGE:-goalchainer-omega:${revision:0:12}}"
docker build --file "$context/goalchainer/integrations/omegaclaw/image/Dockerfile" \
  --build-arg OMEGA_VERSION="$version" --build-arg GOALCHAINER_REVISION="$revision" \
  --build-context native-wheels="$work/native-wheels" \
  --tag "$image" "$@" "$context"
echo "built $image: GoalChainer $revision, $version"

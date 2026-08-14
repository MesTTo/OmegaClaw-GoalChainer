#!/usr/bin/env bash
# Install both plugins into the OmegaClaw-Core checkout GoalChainer runs against.
#
# external/OmegaClaw-Core is a stock upstream checkout. Everything GoalChainer
# needs on top of it is a plugin: the deontic stack (lib_deontic, lib_directive,
# the guard, the NAL bridge, the semantic layer) from external/omegaclaw-deontic,
# and GoalChainer's own skill seam from plugins/goalchainer. Each installs by
# copying a directory in and appending one record to config/plugins.yaml, so the
# checkout stays a stock upstream tree with no fork commits.
#
# Run this after `git submodule update --init`, and again after either plugin
# changes. `--uninstall` returns the checkout to a clean `git status`.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd -- "$here/.." && pwd)"
target="${OMEGACLAW_DIR:-$repo/external/OmegaClaw-Core}"
deontic="$repo/external/omegaclaw-deontic"

if [ ! -f "$target/lib_omegaclaw.metta" ]; then
  echo "error: $target is not an OmegaClaw-Core checkout" >&2
  echo "       run: git submodule update --init" >&2
  exit 1
fi
if [ ! -f "$deontic/installer/install.py" ]; then
  echo "error: $deontic is missing; run: git submodule update --init" >&2
  exit 1
fi

python3 "$deontic/installer/install.py" "$target" "$@"
python3 "$here/install_plugin.py" "$target" "$@"

case " $* " in
  *" --uninstall "*|*" --dry-run "*) ;;
  *)
    echo
    echo "OmegaClaw-Core at $target now carries:"
    echo "  plugins/deontic      the deontic and directive stack"
    echo "  plugins/goalchainer  GoalChainer's skills"
    ;;
esac

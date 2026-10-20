#!/usr/bin/env bash
# Purpose: install GoalChainer's skill plugin into the Omega checkout GoalChainer runs against, or
# remove it with --uninstall.
#
# external/OmegaClaw-Core is a stock checkout of upstream Omega, formerly OmegaClaw, and Omega is one
# harness GoalChainer serves. GoalChainer's reasoning runs from this repository's own package, its
# deontic library included, so all Omega needs is GoalChainer's skill seam from plugins/goalchainer.
# It installs through Omega's plugin API, by copying a directory in and appending one record to
# config/plugins.yaml, so the checkout stays a stock upstream tree with no fork commits.
#
# The plugin runs its skills in GoalChainer's own locked environment, as a child of the
# interpreter `uv sync --frozen` made for this repository, which the install records. Run this
# after `git submodule update --init` and `uv sync --frozen`, and again after the plugin or that
# environment changes. `--uninstall` returns the checkout to a clean `git status`.
# am[implements a-rt-incorporate-deontic-1016@6ea255] am[implements a-oc-plugin-entry-1018@3f1f44]
# am[rests-on c-oc-plugin-api-1018@14ec52]
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd -- "$here/.." && pwd)"
target="${OMEGACLAW_DIR:-$repo/external/OmegaClaw-Core}"

# lib_omega.metta is what Omega's run.metta imports; upstream renamed it from lib_omegaclaw.metta.
# am[rests-on c-oc-upstream-moved-1018@5d3f58]
if [ ! -f "$target/lib_omega.metta" ]; then
  echo "error: $target is not an Omega checkout" >&2
  echo "       run: git submodule update --init" >&2
  exit 1
fi

case " $* " in
  *" --uninstall "*)
    python3 "$here/install_plugin.py" "$target" "$@"
    ;;
  *)
    # uv answers which interpreter the project's environment is, wherever uv put it;
    # --no-sync keeps this from changing that environment.
    # am[implements a-rt-skill-process-boundary-1016@a36729]
    python="$(cd -- "$repo" && uv run --frozen --no-sync python -c 'import sys; print(sys.executable)')" || {
      echo "error: no locked GoalChainer environment; run: uv sync --frozen" >&2
      exit 1
    }
    python3 "$here/install_plugin.py" "$target" --python "$python" "$@"
    ;;
esac

case " $* " in
  *" --uninstall "*|*" --dry-run "*) ;;
  *)
    echo
    echo "Omega at $target now carries plugins/goalchainer, GoalChainer's skills."
    ;;
esac

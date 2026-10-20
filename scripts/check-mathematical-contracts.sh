#!/usr/bin/env bash
# Purpose: provision the pinned Lean dependencies and kernel-check GoalChainer's exact contracts.
# am[implements a-math-delivery-1016@42d527]
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo/proofs"
export PATH="$HOME/.elan/bin:$PATH"
command -v lean >/dev/null || { printf '%s\n' 'math: Lean/elan is required; install https://lean-lang.org/install/' >&2; exit 2; }
command -v lake >/dev/null || { printf '%s\n' 'math: lake is required beside Lean' >&2; exit 2; }
export TMPDIR="${TMPDIR:-$repo/ai-tmp/math-proof-tmp}"
mkdir -p "$TMPDIR"
lean --version
# A verified warm workspace avoids rebuilding mathlib; it is never an alternate model.
# am[implements a-math-delivery-1016@42d527]
if [ -n "${GOALCHAINER_MATHLIB_CACHE:-}" ]; then
  cache="$(cd "$GOALCHAINER_MATHLIB_CACHE" && pwd)"
  expected="$(cat lean-toolchain)"
  [ "$(cat "$cache/lean-toolchain")" = "$expected" ] || { printf '%s\n' 'math: cache toolchain does not match proofs/lean-toolchain' >&2; exit 2; }
  pin="$(git -C "$cache/.lake/packages/mathlib" rev-parse HEAD)"
  expected_pin="$(python3 -c 'import tomllib; print(tomllib.load(open("lakefile.toml", "rb"))["require"][0]["rev"])')"
  [ "$pin" = "$expected_pin" ] || { printf '%s\n' 'math: cache mathlib revision does not match proofs/lakefile.toml' >&2; exit 2; }
  cd "$cache"
else
  if [ ! -f lake-manifest.json ]; then
    lake update
  fi
fi
# Both cold and verified warm workspaces need the proofs' Mathlib imports. Fetch once if any
# required root is absent; cache get resolves their transitive imports at the pinned commit.
# am[implements a-math-delivery-1016@42d527] am[implements a-ie-c5b-evidence-mass-1018@91ad3f]
# am[implements a-jk-pf-lean-model-1019@bf3074]
# am[implements a-v2-motivation-lean-1019@654dcc]
# am[implements a-v2li-import-1020@00b3a6]
modules=(Mathlib.Data.Real.Basic Mathlib.Tactic.Linarith Mathlib.Algebra.BigOperators.Group.Finset.Basic
  Mathlib.Data.Finset.Card Mathlib.Data.Finset.Union Mathlib.Logic.Relation
  Mathlib.Analysis.SpecialFunctions.Pow.Real Mathlib.Tactic.NormNum
  Mathlib.Analysis.Convex.SpecificFunctions.Pow Mathlib.Analysis.SpecialFunctions.Pow.Continuity
  Mathlib.Topology.Order.IntermediateValue)
for module in "${modules[@]}"; do
  if [ ! -f ".lake/packages/mathlib/.lake/build/lib/lean/${module//.//}.olean" ]; then
    lake exe cache get "${modules[@]}"
    break
  fi
done
# am[verifies a-integrate-planning-evidence-lemma-1017@6f13e0]
lake env lean -DwarningAsError=true "$repo/proofs/PlanningEvidence.lean"
# am[implements a-ie-s2c-scalar-tests-proofs-1018@5a0031]
lake env lean -DwarningAsError=true "$repo/proofs/GoalChainer.lean"
# The motivational core is checked once and compiled to the olean its interval proofs import;
# the proofs package declares no library, so MotivationIntervals.lean finds it on LEAN_PATH.
# am[verifies a-v2-motivation-lean-1019@654dcc] am[implements a-v2li-import-1020@00b3a6]
motivation="$TMPDIR/motivation-olean"
mkdir -p "$motivation"
lake env lean -DwarningAsError=true --root="$repo/proofs" -o "$motivation/Motivation.olean" \
  -i "$motivation/Motivation.ilean" "$repo/proofs/Motivation.lean"
# am[verifies a-v2-lean-intervals-1020@35832d]
LEAN_PATH="$motivation" lake env lean -DwarningAsError=true "$repo/proofs/MotivationIntervals.lean"
# The planning model's proofs, then its main comparing the model with planning_oracle's record.
# am[implements a-jk-pf-lean-model-1019@bf3074] am[implements a-jk-pf-conformance-1019@8a012a]
lake env lean -DwarningAsError=true --run "$repo/proofs/PlanningModel.lean" "$repo/tests/data/planning_model_conformance.json"

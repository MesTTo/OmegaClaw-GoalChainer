/- Purpose: prove the order and authority laws the relevance review relies on: robust comparison of
interval coordinates, order transfer under a strictly increasing relabeling, and a licensed authority
ceiling that never exceeds the action's tier or any premise's. -/
import Mathlib.Data.Real.Basic
import Mathlib.Tactic.Linarith

namespace GoalChainer

-- Exact per-coordinate interval reasoning justifies robust Pareto comparisons.
-- am[implements a-math-proofs-1016@f44d34] am[implements a-ie-s2c-scalar-tests-proofs-1018@5a0031]
theorem robust_coordinate {alo bhi a b : ℝ}
    (ha : alo ≤ a) (hb : b ≤ bhi) (h : bhi ≤ alo) : b ≤ a := by linarith

-- A strictly increasing relabeling preserves endpoint comparisons, not arithmetic sums.
-- am[implements a-math-proofs-1016@f44d34]
theorem ordinal_order_transfer (f : ℝ → ℝ) (hf : StrictMono f) (x y : ℝ) :
    f x ≤ f y ↔ x ≤ y := hf.le_iff_le

-- Time: one minimum per premise; space: linear recursion depth in premise count.
-- am[implements a-math-proofs-1016@f44d34]
def licensed (action : Nat) : List Nat → Nat
  | [] => action
  | cap :: rest => min cap (licensed action rest)

-- am[implements a-math-proofs-1016@f44d34]
theorem authority_never_increases (action : Nat) (caps : List Nat) : licensed action caps ≤ action := by
  induction caps with
  | nil => exact Nat.le_refl _
  | cons cap rest ih => exact le_trans (min_le_right _ _) ih

-- am[implements a-math-proofs-1016@f44d34]
theorem authority_respects_every_premise (action : Nat) (caps : List Nat) :
    ∀ cap ∈ caps, licensed action caps ≤ cap := by
  induction caps with
  | nil => simp
  | cons first rest ih =>
    intro cap h
    rcases List.mem_cons.mp h with h | h
    · subst cap
      exact min_le_left _ _
    · exact le_trans (min_le_right _ _) (ih cap h)

end GoalChainer

#print axioms GoalChainer.robust_coordinate
#print axioms GoalChainer.ordinal_order_transfer
#print axioms GoalChainer.authority_never_increases
#print axioms GoalChainer.authority_respects_every_premise

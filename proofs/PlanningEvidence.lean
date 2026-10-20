/- Purpose: prove the opinion bounds and threshold cuts used by planning conditions. -/
-- am[implements a-integrate-remove-unused-choice-proof-1018@c4b0a8]
import Mathlib.Data.Real.Basic
import Mathlib.Tactic.Linarith

namespace GoalChainerPlanning

-- This is SubjectiveOpinion.expectation; its inputs describe evidence, not external truth.
-- am[implements a-integrate-planning-evidence-lemma-1017@6f13e0]
def expectation (belief uncertainty baseRate : ℝ) : ℝ :=
  belief + baseRate * uncertainty

-- These endpoints do not assume an exactly normalized simplex.
-- am[implements a-integrate-planning-evidence-lemma-1017@6f13e0]
theorem projection_bounds {b u a : ℝ}
    (hu : 0 ≤ u) (ha : 0 ≤ a ∧ a ≤ 1) :
    b ≤ expectation b u a ∧ expectation b u a ≤ b + u := by
  unfold expectation
  have lower := mul_nonneg ha.1 hu
  have upper := mul_le_of_le_one_left hu ha.2
  constructor <;> linarith

-- Only exact normalization identifies the computational upper endpoint with one minus disbelief.
-- am[implements a-integrate-planning-evidence-lemma-1017@6f13e0]
theorem expectation_interval {b d u a : ℝ}
    (hu : 0 ≤ u) (ha : 0 ≤ a ∧ a ≤ 1) (hs : b + d + u = 1) :
    b ≤ expectation b u a ∧ expectation b u a ≤ 1 - d := by
  have bounds := projection_bounds (b := b) hu ha
  constructor <;> linarith [bounds.1, bounds.2]

-- A strict belief cut bounds every projection, whatever base rate the source chose.
-- am[implements a-integrate-planning-evidence-lemma-1017@6f13e0]
theorem belief_cut {b u a threshold : ℝ}
    (hu : 0 ≤ u) (ha : 0 ≤ a ∧ a ≤ 1)
    (cut : threshold < b) : threshold < expectation b u a := by
  have bounds := projection_bounds (b := b) hu ha
  linarith [bounds.1]

-- An upper-endpoint cut rejects every projection using the same threshold as the belief cut.
-- am[implements a-integrate-planning-evidence-lemma-1017@6f13e0]
theorem upper_cut {b u a threshold : ℝ}
    (hu : 0 ≤ u) (ha : 0 ≤ a ∧ a ≤ 1)
    (cut : b + u < threshold) : expectation b u a < threshold := by
  have bounds := projection_bounds (b := b) hu ha
  linarith [bounds.2]

-- A valid interval cannot lie strictly on both sides of one threshold, including at its ends.
-- am[implements a-integrate-planning-evidence-lemma-1017@6f13e0]
theorem interval_cuts_exclusive {b u threshold : ℝ}
    (hu : 0 ≤ u) :
    ¬ (threshold < b ∧ b + u < threshold) := by
  rintro ⟨hb, hd⟩
  linarith

-- The symmetric disbelief cut bounds the complement, not the same threshold on the projection.
-- am[implements a-integrate-planning-evidence-lemma-1017@6f13e0]
theorem disbelief_cut {b d u a threshold : ℝ}
    (hu : 0 ≤ u) (ha : 0 ≤ a ∧ a ≤ 1) (hs : b + d + u = 1)
    (cut : threshold < d) : threshold < 1 - expectation b u a := by
  have bounds := expectation_interval hu ha hs
  linarith [bounds.2]

-- Below one half the two cuts can overlap; the classifier must handle that case explicitly.
-- am[implements a-integrate-planning-evidence-lemma-1017@6f13e0]
theorem symmetric_cuts_exclusive {b d u threshold : ℝ}
    (hu : 0 ≤ u) (hs : b + d + u = 1) (ht : 1 / 2 ≤ threshold) :
    ¬ (threshold < b ∧ threshold < d) := by
  rintro ⟨hb, hd⟩
  linarith

-- A vacuous opinion has no belief or disbelief support even when its projection is large.
-- am[implements a-integrate-planning-evidence-lemma-1017@6f13e0]
theorem vacuous_projection (a : ℝ) : expectation 0 1 a = a := by
  simp [expectation]

-- The floating-point boundary accepts a simplex tolerance. Its upper bound retains that slack.
-- This theorem does not model rounding in the multiplication itself.
-- am[implements a-integrate-planning-evidence-lemma-1017@6f13e0]
theorem approximate_simplex_upper {b d u a slack : ℝ}
    (hu : 0 ≤ u) (ha : a ≤ 1) (hs : b + d + u ≤ 1 + slack) :
    expectation b u a ≤ 1 - d + slack := by
  unfold expectation
  have upper := mul_le_of_le_one_left hu ha
  linarith

end GoalChainerPlanning

#print axioms GoalChainerPlanning.expectation_interval
#print axioms GoalChainerPlanning.projection_bounds
#print axioms GoalChainerPlanning.belief_cut
#print axioms GoalChainerPlanning.upper_cut
#print axioms GoalChainerPlanning.interval_cuts_exclusive
#print axioms GoalChainerPlanning.disbelief_cut
#print axioms GoalChainerPlanning.symmetric_cuts_exclusive
#print axioms GoalChainerPlanning.approximate_simplex_upper

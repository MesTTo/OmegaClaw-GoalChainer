/- Purpose: prove the bounds and satisfaction laws of target-band motivational drive reduction. -/
import Mathlib.Analysis.SpecialFunctions.Pow.Real
import Mathlib.Tactic.Linarith
import Mathlib.Tactic.NormNum

noncomputable section

namespace GoalChainerMotivation

-- am[implements a-v2-motivation-lean-1019@654dcc]
structure Need where
  lo : ℝ
  low : ℝ
  high : ℝ
  hi : ℝ
  lo_lt_hi : lo < hi
  lo_le_low : lo ≤ low
  low_le_high : low ≤ high
  high_le_hi : high ≤ hi

-- am[implements a-v2-motivation-lean-1019@654dcc]
def gap (b : Need) (level : ℝ) : ℝ := max 0 (max (b.low - level) (level - b.high))

-- am[implements a-v2-motivation-lean-1019@654dcc]
def margin (b : Need) : ℝ := max (b.low - b.lo) (b.hi - b.high)

-- Real division by zero makes the whole-scale band's normalized distance zero.
-- am[implements a-v2-motivation-lean-1019@654dcc]
def distance (b : Need) (level : ℝ) : ℝ := gap b level / margin b

-- am[implements a-v2-motivation-lean-1019@654dcc]
def drive (b : Need) (k level : ℝ) : ℝ := distance b level ^ k

-- am[implements a-v2-motivation-lean-1019@654dcc]
def clamp (b : Need) (level : ℝ) : ℝ := min b.hi (max b.lo level)

-- am[implements a-v2-motivation-lean-1019@654dcc]
def reduction (b : Need) (k level change : ℝ) : ℝ :=
  drive b k level - drive b k (clamp b (level + change))

-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem margin_nonneg (b : Need) : 0 ≤ margin b :=
  le_trans (sub_nonneg.mpr b.lo_le_low) (le_max_left _ _)

-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem gap_nonneg (b : Need) (level : ℝ) : 0 ≤ gap b level := le_max_left _ _

-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem gap_le_margin (b : Need) {level : ℝ} (hlo : b.lo ≤ level) (hhi : level ≤ b.hi) :
    gap b level ≤ margin b := by
  apply max_le (margin_nonneg b)
  apply max_le
  · exact le_trans (sub_le_sub_left hlo b.low) (le_max_left _ _)
  · exact le_trans (sub_le_sub_right hhi b.high) (le_max_right _ _)

-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem distance_nonneg (b : Need) (level : ℝ) : 0 ≤ distance b level :=
  div_nonneg (gap_nonneg b level) (margin_nonneg b)

-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem distance_bounds (b : Need) {level : ℝ} (hlo : b.lo ≤ level) (hhi : level ≤ b.hi) :
    0 ≤ distance b level ∧ distance b level ≤ 1 := by
  refine ⟨distance_nonneg b level, ?_⟩
  by_cases hz : margin b = 0
  · simp [distance, hz]
  · exact (div_le_one (lt_of_le_of_ne (margin_nonneg b) (Ne.symm hz))).mpr
      (gap_le_margin b hlo hhi)

-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem drive_nonneg (b : Need) (k level : ℝ) : 0 ≤ drive b k level :=
  Real.rpow_nonneg (distance_nonneg b level) k

-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem drive_bounds (b : Need) {k level : ℝ} (hk : 0 ≤ k)
    (hlo : b.lo ≤ level) (hhi : level ≤ b.hi) :
    0 ≤ drive b k level ∧ drive b k level ≤ 1 := by
  obtain ⟨h0, h1⟩ := distance_bounds b hlo hhi
  exact ⟨drive_nonneg b k level, Real.rpow_le_one h0 h1 hk⟩

-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem clamp_bounds (b : Need) (level : ℝ) : b.lo ≤ clamp b level ∧ clamp b level ≤ b.hi :=
  ⟨le_min b.lo_lt_hi.le (le_max_left _ _), min_le_left _ _⟩

-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem reduction_bounds (b : Need) {k level : ℝ} (change : ℝ) (hk : 0 ≤ k)
    (hlo : b.lo ≤ level) (hhi : level ≤ b.hi) :
    -1 ≤ reduction b k level change ∧ reduction b k level change ≤ 1 := by
  obtain ⟨h0, h1⟩ := drive_bounds b hk hlo hhi
  obtain ⟨clo, chi⟩ := clamp_bounds b (level + change)
  obtain ⟨c0, c1⟩ := drive_bounds b hk clo chi
  dsimp [reduction]
  constructor <;> linarith

-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem weighted_reduction_bounds (b : Need) {k level weight : ℝ} (change : ℝ)
    (hk : 0 ≤ k) (hw : 0 ≤ weight) (hlo : b.lo ≤ level) (hhi : level ≤ b.hi) :
    -weight ≤ weight * reduction b k level change ∧
      weight * reduction b k level change ≤ weight := by
  obtain ⟨h0, h1⟩ := reduction_bounds b change hk hlo hhi
  constructor <;> nlinarith

-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem in_band_gap_zero (b : Need) {level : ℝ} (hl : b.low ≤ level) (hh : level ≤ b.high) :
    gap b level = 0 := by
  apply le_antisymm _ (gap_nonneg b level)
  exact max_le (le_refl 0) (max_le (sub_nonpos.mpr hl) (sub_nonpos.mpr hh))

-- A positive exponent is needed: a zero exponent would make zero distance have drive one.
-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem in_band_drive_zero (b : Need) {k level : ℝ} (hk : 0 < k)
    (hl : b.low ≤ level) (hh : level ≤ b.high) : drive b k level = 0 := by
  simp [drive, distance, in_band_gap_zero b hl hh, Real.zero_rpow (ne_of_gt hk)]

-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem in_band_reduction_nonpos (b : Need) {k level : ℝ} (change : ℝ) (hk : 0 < k)
    (hl : b.low ≤ level) (hh : level ≤ b.high) : reduction b k level change ≤ 0 := by
  unfold reduction
  rw [in_band_drive_zero b hk hl hh, zero_sub]
  exact neg_nonpos.mpr (drive_nonneg b k _)

-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem whole_scale_drive_zero (b : Need) {k level : ℝ} (hk : 0 < k)
    (hl : b.low = b.lo) (hh : b.high = b.hi) : drive b k level = 0 := by
  simp [drive, distance, margin, hl, hh, Real.zero_rpow (ne_of_gt hk)]

-- This interval is an enclosure even when several candidates share the same unknown level.
-- am[implements a-v2-motivation-lean-1019@654dcc]
theorem conservative_lead {aLow a b bHigh : ℝ} (ha : aLow ≤ a) (hb : b ≤ bHigh) :
    aLow - bHigh ≤ a - b := by linarith

-- Drive orders levels exactly as their gaps do, whatever the exponent k > 0 and the positive
-- margin, so a reduction's sign is a comparison of two gaps: the runtime decides it exactly from
-- its binary64 inputs and evaluates only the magnitude in floating point.
-- am[implements a-v2r-exact-sign-1020] am[verifies c-v2r-sign-invariant-1020]
theorem drive_le_drive_iff (b : Need) {k x y : ℝ} (hk : 0 < k) (hm : 0 < margin b) :
    drive b k x ≤ drive b k y ↔ gap b x ≤ gap b y := by
  unfold drive distance
  rw [Real.rpow_le_rpow_iff (div_nonneg (gap_nonneg b x) hm.le) (div_nonneg (gap_nonneg b y) hm.le) hk,
    div_le_div_iff_of_pos_right hm]

-- am[implements a-v2r-exact-sign-1020] am[verifies c-v2r-sign-invariant-1020]
theorem drive_lt_drive_iff (b : Need) {k x y : ℝ} (hk : 0 < k) (hm : 0 < margin b) :
    drive b k x < drive b k y ↔ gap b x < gap b y := by
  rw [lt_iff_not_ge, lt_iff_not_ge, drive_le_drive_iff b hk hm]

-- am[implements a-v2r-exact-sign-1020] am[verifies c-v2r-sign-invariant-1020]
theorem reduction_pos_iff (b : Need) {k level change : ℝ} (hk : 0 < k) (hm : 0 < margin b) :
    0 < reduction b k level change ↔ gap b (clamp b (level + change)) < gap b level := by
  rw [reduction, sub_pos, drive_lt_drive_iff b hk hm]

-- am[implements a-v2r-exact-sign-1020] am[verifies c-v2r-sign-invariant-1020]
theorem reduction_neg_iff (b : Need) {k level change : ℝ} (hk : 0 < k) (hm : 0 < margin b) :
    reduction b k level change < 0 ↔ gap b level < gap b (clamp b (level + change)) := by
  rw [reduction, sub_neg, drive_lt_drive_iff b hk hm]

-- am[implements a-v2r-exact-sign-1020] am[verifies c-v2r-sign-invariant-1020]
theorem reduction_eq_zero_iff (b : Need) {k level change : ℝ} (hk : 0 < k) (hm : 0 < margin b) :
    reduction b k level change = 0 ↔ gap b level = gap b (clamp b (level + change)) := by
  rw [reduction, sub_eq_zero, le_antisymm_iff, le_antisymm_iff, drive_le_drive_iff b hk hm,
    drive_le_drive_iff b hk hm]

-- am[implements a-v2-motivation-lean-1019@654dcc]
def exampleNeed : Need where
  lo := 0
  low := 2 / 5
  high := 3 / 5
  hi := 1
  lo_lt_hi := by norm_num
  lo_le_low := by norm_num
  low_le_high := by norm_num
  high_le_hi := by norm_num

-- am[verifies a-v2-motivation-lean-1019@654dcc]
theorem signed_change_counterexample :
    reduction exampleNeed 1 (9 / 10) (1 / 10) = -(1 / 4) ∧
    reduction exampleNeed 1 (9 / 10) (-(2 / 5)) = 3 / 4 := by
  norm_num [reduction, drive, distance, gap, margin, clamp, exampleNeed, Real.rpow_one]

end GoalChainerMotivation

#print axioms GoalChainerMotivation.drive_bounds
#print axioms GoalChainerMotivation.weighted_reduction_bounds
#print axioms GoalChainerMotivation.in_band_reduction_nonpos
#print axioms GoalChainerMotivation.whole_scale_drive_zero
#print axioms GoalChainerMotivation.conservative_lead
#print axioms GoalChainerMotivation.signed_change_counterexample
#print axioms GoalChainerMotivation.reduction_pos_iff
#print axioms GoalChainerMotivation.reduction_neg_iff
#print axioms GoalChainerMotivation.reduction_eq_zero_iff

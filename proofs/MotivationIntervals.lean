/- Purpose: prove that, for a known change, the motivational reduction over an unknown level in
[lo, hi] takes exactly the values between its least and greatest values at the clipped breakpoints
lo, low, high, hi, lo - d, low - d, high - d and hi - d. -/
import Motivation
import Mathlib.Analysis.Convex.SpecificFunctions.Pow
import Mathlib.Analysis.SpecialFunctions.Pow.Continuity
import Mathlib.Topology.Order.IntermediateValue

noncomputable section

namespace GoalChainerMotivation

open Set

-- am[implements a-v2li-piece-proof-1020@16c6b8]
theorem gap_of_le_low (b : Need) {x : ℝ} (h : x ≤ b.low) : gap b x = b.low - x := by
  have := b.low_le_high
  rw [gap, max_eq_left (by linarith : x - b.high ≤ b.low - x),
    max_eq_right (by linarith : (0 : ℝ) ≤ b.low - x)]

-- am[implements a-v2li-piece-proof-1020@16c6b8]
theorem gap_of_high_le (b : Need) {x : ℝ} (h : b.high ≤ x) : gap b x = x - b.high := by
  have := b.low_le_high
  rw [gap, max_eq_right (by linarith : b.low - x ≤ x - b.high),
    max_eq_right (by linarith : (0 : ℝ) ≤ x - b.high)]

-- am[implements a-v2li-piece-proof-1020@16c6b8]
theorem clamp_of_le_lo (b : Need) {x : ℝ} (h : x ≤ b.lo) : clamp b x = b.lo := by
  rw [clamp, max_eq_left h, min_eq_right b.lo_lt_hi.le]

-- am[implements a-v2li-piece-proof-1020@16c6b8]
theorem clamp_of_mem (b : Need) {x : ℝ} (h₁ : b.lo ≤ x) (h₂ : x ≤ b.hi) : clamp b x = x := by
  rw [clamp, max_eq_right h₁, min_eq_right h₂]

-- am[implements a-v2li-piece-proof-1020@16c6b8]
theorem clamp_of_hi_le (b : Need) {x : ℝ} (h : b.hi ≤ x) : clamp b x = b.hi := by
  rw [clamp, max_eq_right (b.lo_lt_hi.le.trans h), min_eq_left h]

-- On a closed piece whose interior holds neither band edge, the level stays below, inside or
-- above the band, so its gap is affine with slope -1, 0 or 1.
-- am[implements a-v2li-piece-proof-1020@16c6b8] am[rests-on c-v2li-sides-1020@af6bdf]
theorem gap_affine_on (b : Need) {p q : ℝ}
    (hlow : b.low ≤ p ∨ q ≤ b.low) (hhigh : b.high ≤ p ∨ q ≤ b.high) :
    ∃ c s : ℝ, (s = -1 ∨ s = 0 ∨ s = 1) ∧ ∀ n ∈ Icc p q, gap b n = c + s * n := by
  rcases hlow with hlow | hlow
  · rcases hhigh with hhigh | hhigh
    · refine ⟨-b.high, 1, by norm_num, fun n hn => ?_⟩
      rw [gap_of_high_le b (hhigh.trans hn.1)]
      ring
    · refine ⟨0, 0, by norm_num, fun n hn => ?_⟩
      rw [in_band_gap_zero b (hlow.trans hn.1) (hn.2.trans hhigh)]
      ring
  · refine ⟨b.low, -1, by norm_num, fun n hn => ?_⟩
    rw [gap_of_le_low b (hn.2.trans hlow)]
    ring

-- On a closed piece whose interior holds none of lo - d, low - d, high - d and hi - d, the
-- target n + d stays below lo, in [lo, low], in the band, in [high, hi] or above hi; clamp is lo,
-- n + d, n + d, n + d or hi there, so the target's gap is affine in n with slope -1, 0 or 1.
-- am[implements a-v2li-piece-proof-1020@16c6b8] am[rests-on c-v2li-sides-1020@af6bdf]
theorem gap_clamp_affine_on (b : Need) (d : ℝ) {p q : ℝ}
    (hlo : b.lo ≤ p + d ∨ q + d ≤ b.lo) (hlow : b.low ≤ p + d ∨ q + d ≤ b.low)
    (hhigh : b.high ≤ p + d ∨ q + d ≤ b.high) (hhi : b.hi ≤ p + d ∨ q + d ≤ b.hi) :
    ∃ c s : ℝ, (s = -1 ∨ s = 0 ∨ s = 1) ∧
      ∀ n ∈ Icc p q, gap b (clamp b (n + d)) = c + s * n := by
  have h₁ := b.lo_le_low
  have h₂ := b.low_le_high
  have h₃ := b.high_le_hi
  rcases hlo with hlo | hlo
  · rcases hlow with hlow | hlow
    · rcases hhigh with hhigh | hhigh
      · rcases hhi with hhi | hhi
        · refine ⟨b.hi - b.high, 0, by norm_num, fun n hn => ?_⟩
          rw [clamp_of_hi_le b (by linarith [hn.1] : b.hi ≤ n + d), gap_of_high_le b h₃]
          ring
        · refine ⟨d - b.high, 1, by norm_num, fun n hn => ?_⟩
          rw [clamp_of_mem b (by linarith [hn.1] : b.lo ≤ n + d) (by linarith [hn.2] : n + d ≤ b.hi),
            gap_of_high_le b (by linarith [hn.1] : b.high ≤ n + d)]
          ring
      · refine ⟨0, 0, by norm_num, fun n hn => ?_⟩
        rw [clamp_of_mem b (by linarith [hn.1] : b.lo ≤ n + d) (by linarith [hn.2] : n + d ≤ b.hi),
          in_band_gap_zero b (by linarith [hn.1] : b.low ≤ n + d) (by linarith [hn.2] : n + d ≤ b.high)]
        ring
    · refine ⟨b.low - d, -1, by norm_num, fun n hn => ?_⟩
      rw [clamp_of_mem b (by linarith [hn.1] : b.lo ≤ n + d) (by linarith [hn.2] : n + d ≤ b.hi),
        gap_of_le_low b (by linarith [hn.2] : n + d ≤ b.low)]
      ring
  · refine ⟨b.low - b.lo, 0, by norm_num, fun n hn => ?_⟩
    rw [clamp_of_le_lo b (by linarith [hn.2] : n + d ≤ b.lo), gap_of_le_low b h₁]
    ring

-- Dividing by a nonnegative margin keeps an affine map's direction; Lean's x / 0 = 0 makes the
-- whole-scale band's distances constant.
-- am[implements a-v2li-piece-proof-1020@16c6b8] am[rests-on c-v2li-opposite-slopes-1020@547160]
theorem affine_div_monotone {c s D : ℝ} (hs : 0 ≤ s) (hD : 0 ≤ D) :
    Monotone fun n : ℝ => (c + s * n) / D := fun x y hxy =>
  div_le_div_of_nonneg_right (by linarith [mul_le_mul_of_nonneg_left hxy hs]) hD

-- am[implements a-v2li-piece-proof-1020@16c6b8] am[rests-on c-v2li-opposite-slopes-1020@547160]
theorem affine_div_antitone {c s D : ℝ} (hs : s ≤ 0) (hD : 0 ≤ D) :
    Antitone fun n : ℝ => (c + s * n) / D := fun x y hxy =>
  div_le_div_of_nonneg_right (by linarith [mul_le_mul_of_nonpos_left hxy hs]) hD

-- x ^ K with K ≥ 0 is monotone on nonnegative reals, so it keeps a nonnegative map's direction.
-- am[implements a-v2li-piece-proof-1020@16c6b8] am[rests-on c-v2li-opposite-slopes-1020@547160]
theorem rpow_monotoneOn {f : ℝ → ℝ} {S : Set ℝ} {k : ℝ} (hk : 0 ≤ k) (hf : MonotoneOn f S)
    (h0 : ∀ x ∈ S, 0 ≤ f x) : MonotoneOn (fun x => f x ^ k) S := fun x hx _ hy hxy =>
  Real.rpow_le_rpow (h0 x hx) (hf hx hy hxy) hk

-- am[implements a-v2li-piece-proof-1020@16c6b8] am[rests-on c-v2li-opposite-slopes-1020@547160]
theorem rpow_antitoneOn {f : ℝ → ℝ} {S : Set ℝ} {k : ℝ} (hk : 0 ≤ k) (hf : AntitoneOn f S)
    (h0 : ∀ x ∈ S, 0 ≤ f x) : AntitoneOn (fun x => f x ^ k) S := fun _ hx y hy hxy =>
  Real.rpow_le_rpow (h0 y hy) (hf hx hy hxy) hk

-- When the level's distance rises or stays while the target's falls or stays, the reduction rises.
-- am[implements a-v2li-piece-proof-1020@16c6b8] am[rests-on c-v2li-opposite-slopes-1020@547160]
theorem opposite_slopes_monotoneOn {S : Set ℝ} {k D c₀ c₁ s₀ s₁ : ℝ} (hk : 0 ≤ k) (hD : 0 ≤ D)
    (hs₀ : 0 ≤ s₀) (hs₁ : s₁ ≤ 0) (h₀ : ∀ n ∈ S, 0 ≤ c₀ + s₀ * n) (h₁ : ∀ n ∈ S, 0 ≤ c₁ + s₁ * n) :
    MonotoneOn (fun n => ((c₀ + s₀ * n) / D) ^ k - ((c₁ + s₁ * n) / D) ^ k) S := by
  have hA := rpow_monotoneOn hk ((affine_div_monotone hs₀ hD).monotoneOn S)
    fun n hn => div_nonneg (h₀ n hn) hD
  have hB := rpow_antitoneOn hk ((affine_div_antitone hs₁ hD).antitoneOn S)
    fun n hn => div_nonneg (h₁ n hn) hD
  exact fun x hx y hy hxy => sub_le_sub (hA hx hy hxy) (hB hx hy hxy)

-- am[implements a-v2li-piece-proof-1020@16c6b8] am[rests-on c-v2li-opposite-slopes-1020@547160]
theorem opposite_slopes_antitoneOn {S : Set ℝ} {k D c₀ c₁ s₀ s₁ : ℝ} (hk : 0 ≤ k) (hD : 0 ≤ D)
    (hs₀ : s₀ ≤ 0) (hs₁ : 0 ≤ s₁) (h₀ : ∀ n ∈ S, 0 ≤ c₀ + s₀ * n) (h₁ : ∀ n ∈ S, 0 ≤ c₁ + s₁ * n) :
    AntitoneOn (fun n => ((c₀ + s₀ * n) / D) ^ k - ((c₁ + s₁ * n) / D) ^ k) S := by
  have hA := rpow_antitoneOn hk ((affine_div_antitone hs₀ hD).antitoneOn S)
    fun n hn => div_nonneg (h₀ n hn) hD
  have hB := rpow_monotoneOn hk ((affine_div_monotone hs₁ hD).monotoneOn S)
    fun n hn => div_nonneg (h₁ n hn) hD
  exact fun x hx y hy hxy => sub_le_sub (hA hx hy hxy) (hB hx hy hxy)

-- A convex function's increment over a fixed width c ≥ 0 grows along its domain: the secant
-- slope over [t, t + c] is at most the one over [t, u + c], which is at most the one over
-- [u, u + c] (ConvexOn.secant_mono at a = t, then at a = u + c).
-- am[implements a-v2li-increment-proof-1020@18d542] am[rests-on c-v2li-increment-1020@0dcd81]
theorem convex_increment_monotoneOn {f : ℝ → ℝ} {S : Set ℝ} (hf : ConvexOn ℝ S f) {c : ℝ}
    (hc : 0 ≤ c) : MonotoneOn (fun t => f (t + c) - f t) {t | t ∈ S ∧ t + c ∈ S} := by
  intro t ht u hu htu
  rcases hc.eq_or_lt with rfl | hc
  · simp
  have h₁ := hf.secant_mono ht.1 ht.2 hu.2 (by linarith : t < t + c).ne'
    (by linarith : t < u + c).ne' (by linarith : t + c ≤ u + c)
  have h₂ := hf.secant_mono hu.2 ht.1 hu.1 (by linarith : t < u + c).ne
    (by linarith : u < u + c).ne htu
  rw [show t + c - t = c by ring] at h₁
  rw [show t - (u + c) = -(u + c - t) by ring, show f t - f (u + c) = -(f (u + c) - f t) by ring,
    neg_div_neg_eq, show u - (u + c) = -c by ring,
    show f u - f (u + c) = -(f (u + c) - f u) by ring, neg_div_neg_eq] at h₂
  exact (div_le_div_iff_of_pos_right hc).mp (h₁.trans h₂)

-- For K > 0 and a constant c, t ^ K - (t + c) ^ K is monotone or antitone where both bases are
-- nonnegative: x ^ K is convex for K ≥ 1 and concave for K ≤ 1, and the sign of c says whether
-- the difference is an increment or minus one.
-- am[implements a-v2li-increment-proof-1020@18d542] am[rests-on c-v2li-increment-1020@0dcd81]
theorem rpow_sub_shift_monotoneOn_or_antitoneOn {k : ℝ} (hk : 0 < k) (c : ℝ) :
    MonotoneOn (fun t : ℝ => t ^ k - (t + c) ^ k) {t | 0 ≤ t ∧ 0 ≤ t + c} ∨
      AntitoneOn (fun t : ℝ => t ^ k - (t + c) ^ k) {t | 0 ≤ t ∧ 0 ≤ t + c} := by
  rcases le_total 0 c with hc | hc <;> rcases le_total 1 k with hk₁ | hk₁
  · -- Convex power, c ≥ 0: the difference is minus a growing increment.
    right
    intro t ht u hu htu
    have := convex_increment_monotoneOn (convexOn_rpow hk₁) hc
      (show t ∈ {s | s ∈ Ici 0 ∧ s + c ∈ Ici 0} from ⟨ht.1, ht.2⟩)
      (show u ∈ {s | s ∈ Ici 0 ∧ s + c ∈ Ici 0} from ⟨hu.1, hu.2⟩) htu
    simp only at this ⊢
    linarith
  · -- Concave power, c ≥ 0: the difference is the increment of the convex -x ^ K.
    left
    intro t ht u hu htu
    have := convex_increment_monotoneOn (Real.concaveOn_rpow hk.le hk₁).neg hc
      (show t ∈ {s | s ∈ Ici 0 ∧ s + c ∈ Ici 0} from ⟨ht.1, ht.2⟩)
      (show u ∈ {s | s ∈ Ici 0 ∧ s + c ∈ Ici 0} from ⟨hu.1, hu.2⟩) htu
    simp only [Pi.neg_apply] at this ⊢
    linarith
  · -- Convex power, c ≤ 0: the difference is the increment of width -c starting at t + c.
    left
    intro t ht u hu htu
    have := convex_increment_monotoneOn (convexOn_rpow hk₁) (neg_nonneg.mpr hc)
      (show t + c ∈ {s | s ∈ Ici 0 ∧ s + -c ∈ Ici 0} from ⟨ht.2, by simpa using ht.1⟩)
      (show u + c ∈ {s | s ∈ Ici 0 ∧ s + -c ∈ Ici 0} from ⟨hu.2, by simpa using hu.1⟩)
      (by linarith : t + c ≤ u + c)
    simp only [add_neg_cancel_right] at this ⊢
    linarith
  · -- Concave power, c ≤ 0: the difference is minus that increment of the convex -x ^ K.
    right
    intro t ht u hu htu
    have := convex_increment_monotoneOn (Real.concaveOn_rpow hk.le hk₁).neg (neg_nonneg.mpr hc)
      (show t + c ∈ {s | s ∈ Ici 0 ∧ s + -c ∈ Ici 0} from ⟨ht.2, by simpa using ht.1⟩)
      (show u + c ∈ {s | s ∈ Ici 0 ∧ s + -c ∈ Ici 0} from ⟨hu.2, by simpa using hu.1⟩)
      (by linarith : t + c ≤ u + c)
    simp only [Pi.neg_apply, add_neg_cancel_right] at this ⊢
    linarith

-- When both distances have the same slope they differ by the constant (c₁ - c₀) / D, so the
-- difference of their powers is the shifted difference above composed with an affine map.
-- am[implements a-v2li-piece-proof-1020@16c6b8] am[rests-on c-v2li-increment-1020@0dcd81]
theorem equal_slopes_monotoneOn_or_antitoneOn {S : Set ℝ} {k D c₀ c₁ s : ℝ} (hk : 0 < k)
    (hD : 0 ≤ D) (h₀ : ∀ n ∈ S, 0 ≤ c₀ + s * n) (h₁ : ∀ n ∈ S, 0 ≤ c₁ + s * n) :
    MonotoneOn (fun n => ((c₀ + s * n) / D) ^ k - ((c₁ + s * n) / D) ^ k) S ∨
      AntitoneOn (fun n => ((c₀ + s * n) / D) ^ k - ((c₁ + s * n) / D) ^ k) S := by
  have hshift : ∀ n, (c₁ + s * n) / D = (c₀ + s * n) / D + (c₁ - c₀) / D := fun n => by ring
  have hmaps : MapsTo (fun n => (c₀ + s * n) / D) S {t | 0 ≤ t ∧ 0 ≤ t + (c₁ - c₀) / D} :=
    fun n hn => ⟨div_nonneg (h₀ n hn) hD, by rw [← hshift]; exact div_nonneg (h₁ n hn) hD⟩
  have hform : (fun n => ((c₀ + s * n) / D) ^ k - ((c₁ + s * n) / D) ^ k) =
      (fun t : ℝ => t ^ k - (t + (c₁ - c₀) / D) ^ k) ∘ fun n => (c₀ + s * n) / D := by
    funext n
    simp only [Function.comp_apply, hshift]
  rw [hform]
  rcases rpow_sub_shift_monotoneOn_or_antitoneOn hk ((c₁ - c₀) / D) with hg | hg <;>
    rcases le_total 0 s with hs | hs
  · exact Or.inl (hg.comp ((affine_div_monotone hs hD).monotoneOn S) hmaps)
  · exact Or.inr (hg.comp_AntitoneOn ((affine_div_antitone hs hD).antitoneOn S) hmaps)
  · exact Or.inr (hg.comp_MonotoneOn ((affine_div_monotone hs hD).monotoneOn S) hmaps)
  · exact Or.inl (hg.comp ((affine_div_antitone hs hD).antitoneOn S) hmaps)

-- Slopes in {-1, 0, 1} either agree, or the level's is at least the target's or at most it;
-- the nine pairs are dispatched one by one, since unifying unequal real literals is costly.
-- am[implements a-v2li-piece-proof-1020@16c6b8]
theorem slopes_monotoneOn_or_antitoneOn {S : Set ℝ} {k D c₀ c₁ s₀ s₁ : ℝ} (hk : 0 < k)
    (hD : 0 ≤ D) (hs₀ : s₀ = -1 ∨ s₀ = 0 ∨ s₀ = 1) (hs₁ : s₁ = -1 ∨ s₁ = 0 ∨ s₁ = 1)
    (h₀ : ∀ n ∈ S, 0 ≤ c₀ + s₀ * n) (h₁ : ∀ n ∈ S, 0 ≤ c₁ + s₁ * n) :
    MonotoneOn (fun n => ((c₀ + s₀ * n) / D) ^ k - ((c₁ + s₁ * n) / D) ^ k) S ∨
      AntitoneOn (fun n => ((c₀ + s₀ * n) / D) ^ k - ((c₁ + s₁ * n) / D) ^ k) S := by
  rcases hs₀ with rfl | rfl | rfl <;> rcases hs₁ with rfl | rfl | rfl
  · exact equal_slopes_monotoneOn_or_antitoneOn hk hD h₀ h₁
  · exact Or.inr (opposite_slopes_antitoneOn hk.le hD (by norm_num) (by norm_num) h₀ h₁)
  · exact Or.inr (opposite_slopes_antitoneOn hk.le hD (by norm_num) (by norm_num) h₀ h₁)
  · exact Or.inl (opposite_slopes_monotoneOn hk.le hD (by norm_num) (by norm_num) h₀ h₁)
  · exact equal_slopes_monotoneOn_or_antitoneOn hk hD h₀ h₁
  · exact Or.inr (opposite_slopes_antitoneOn hk.le hD (by norm_num) (by norm_num) h₀ h₁)
  · exact Or.inl (opposite_slopes_monotoneOn hk.le hD (by norm_num) (by norm_num) h₀ h₁)
  · exact Or.inl (opposite_slopes_monotoneOn hk.le hD (by norm_num) (by norm_num) h₀ h₁)
  · exact equal_slopes_monotoneOn_or_antitoneOn hk hD h₀ h₁

-- On a closed piece whose interior holds none of the candidates that matter, low, high, lo - d,
-- low - d, high - d and hi - d, the reduction is monotone or antitone.
-- am[implements a-v2li-piece-proof-1020@16c6b8] am[rests-on c-v2li-sides-1020@af6bdf]
theorem reduction_monotoneOn_or_antitoneOn_piece (b : Need) {k : ℝ} (hk : 0 < k) (d : ℝ)
    {p q : ℝ} (hlow : b.low ≤ p ∨ q ≤ b.low) (hhigh : b.high ≤ p ∨ q ≤ b.high)
    (hlo' : b.lo ≤ p + d ∨ q + d ≤ b.lo) (hlow' : b.low ≤ p + d ∨ q + d ≤ b.low)
    (hhigh' : b.high ≤ p + d ∨ q + d ≤ b.high) (hhi' : b.hi ≤ p + d ∨ q + d ≤ b.hi) :
    MonotoneOn (fun n => reduction b k n d) (Icc p q) ∨
      AntitoneOn (fun n => reduction b k n d) (Icc p q) := by
  obtain ⟨c₀, s₀, hs₀, hgap⟩ := gap_affine_on b hlow hhigh
  obtain ⟨c₁, s₁, hs₁, hgap'⟩ := gap_clamp_affine_on b d hlo' hlow' hhigh' hhi'
  have hform : ∀ n ∈ Icc p q, reduction b k n d =
      ((c₀ + s₀ * n) / margin b) ^ k - ((c₁ + s₁ * n) / margin b) ^ k := fun n hn => by
    simp only [reduction, drive, distance, hgap n hn, hgap' n hn]
  rcases slopes_monotoneOn_or_antitoneOn hk (margin_nonneg b) hs₀ hs₁
      (fun n hn => hgap n hn ▸ gap_nonneg b n) (fun n hn => hgap' n hn ▸ gap_nonneg b _) with h | h
  · left
    intro x hx y hy hxy
    simp only [hform x hx, hform y hy]
    exact h hx hy hxy
  · right
    intro x hx y hy hxy
    simp only [hform x hx, hform y hy]
    exact h hx hy hxy

-- The eight candidate levels for a known change: the scale ends and band edges, where the level
-- changes side, and each minus the change, where the clamped target does.
-- am[implements a-v2li-sandwich-proof-1020@e2a6a2]
def candidates (b : Need) (change : ℝ) : Finset ℝ :=
  {b.lo, b.low, b.high, b.hi, b.lo - change, b.low - change, b.high - change, b.hi - change}

-- The candidates within the scale, the levels the interval evaluator evaluates.
-- am[implements a-v2li-sandwich-proof-1020@e2a6a2]
def breakpoints (b : Need) (change : ℝ) : Finset ℝ :=
  (candidates b change).filter fun x => b.lo ≤ x ∧ x ≤ b.hi

-- am[implements a-v2li-sandwich-proof-1020@e2a6a2]
theorem lo_mem_breakpoints (b : Need) (d : ℝ) : b.lo ∈ breakpoints b d := by
  simp [breakpoints, candidates, b.lo_lt_hi.le]

-- am[implements a-v2li-sandwich-proof-1020@e2a6a2]
theorem hi_mem_breakpoints (b : Need) (d : ℝ) : b.hi ∈ breakpoints b d := by
  simp [breakpoints, candidates, b.lo_lt_hi.le]

-- am[implements a-v2li-sandwich-proof-1020@e2a6a2]
theorem breakpoint_bounds (b : Need) (d : ℝ) {x : ℝ} (hx : x ∈ breakpoints b d) :
    b.lo ≤ x ∧ x ≤ b.hi :=
  (Finset.mem_filter.mp hx).2

-- Clamping the candidates into the scale, instead of discarding those outside it, gives the same
-- levels: an outside candidate clamps to lo or hi, both candidates already.
-- am[implements a-v2li-sandwich-proof-1020@e2a6a2]
-- am[rests-on c-v2li-clamp-equals-filter-1020@3fc26c]
theorem candidates_image_clamp (b : Need) (d : ℝ) :
    (candidates b d).image (clamp b) = breakpoints b d := by
  ext x
  simp only [Finset.mem_image, breakpoints, Finset.mem_filter]
  constructor
  · rintro ⟨y, hy, rfl⟩
    refine ⟨?_, clamp_bounds b y⟩
    rcases le_total y b.lo with h | h
    · rw [clamp_of_le_lo b h]
      simp [candidates]
    · rcases le_total y b.hi with h' | h'
      · rwa [clamp_of_mem b h h']
      · rw [clamp_of_hi_le b h']
        simp [candidates]
  · rintro ⟨hx, hlo, hhi⟩
    exact ⟨x, hx, clamp_of_mem b hlo hhi⟩

-- Each level lies between the greatest breakpoint at or below it and the least at or above it,
-- and no candidate lies strictly between those two, so the reduction is monotone or antitone on
-- the piece they bound.
-- am[implements a-v2li-sandwich-proof-1020@e2a6a2] am[rests-on c-v2li-sandwich-1020@e6d0b5]
theorem exists_breakpoint_piece (b : Need) {k : ℝ} (hk : 0 < k) (d : ℝ) {n : ℝ}
    (hlo : b.lo ≤ n) (hhi : n ≤ b.hi) :
    ∃ p ∈ breakpoints b d, ∃ q ∈ breakpoints b d, n ∈ Icc p q ∧
      (MonotoneOn (fun n => reduction b k n d) (Icc p q) ∨
        AntitoneOn (fun n => reduction b k n d) (Icc p q)) := by
  have hL : ((breakpoints b d).filter (· ≤ n)).Nonempty :=
    ⟨b.lo, Finset.mem_filter.mpr ⟨lo_mem_breakpoints b d, hlo⟩⟩
  have hU : ((breakpoints b d).filter (n ≤ ·)).Nonempty :=
    ⟨b.hi, Finset.mem_filter.mpr ⟨hi_mem_breakpoints b d, hhi⟩⟩
  obtain ⟨hpB, hpn⟩ := Finset.mem_filter.mp (Finset.max'_mem _ hL)
  obtain ⟨hqB, hnq⟩ := Finset.mem_filter.mp (Finset.min'_mem _ hU)
  set p := ((breakpoints b d).filter (· ≤ n)).max' hL
  set q := ((breakpoints b d).filter (n ≤ ·)).min' hU
  have hbetween : ∀ c ∈ candidates b d, c ≤ p ∨ q ≤ c := by
    intro c hc
    by_contra h
    rw [not_or, not_le, not_le] at h
    have hcB : c ∈ breakpoints b d := Finset.mem_filter.mpr
      ⟨hc, (breakpoint_bounds b d hpB).1.trans h.1.le, h.2.le.trans (breakpoint_bounds b d hqB).2⟩
    rcases le_total c n with hcn | hnc
    · exact h.1.not_ge (Finset.le_max' _ c (Finset.mem_filter.mpr ⟨hcB, hcn⟩))
    · exact h.2.not_ge (Finset.min'_le _ c (Finset.mem_filter.mpr ⟨hcB, hnc⟩))
  have hshift : ∀ c, c - d ∈ candidates b d → c ≤ p + d ∨ q + d ≤ c := fun c hc =>
    (hbetween _ hc).imp (fun h => by linarith) (fun h => by linarith)
  exact ⟨p, hpB, q, hqB, ⟨hpn, hnq⟩, reduction_monotoneOn_or_antitoneOn_piece b hk d
    (hbetween _ (by simp [candidates])) (hbetween _ (by simp [candidates]))
    (hshift _ (by simp [candidates])) (hshift _ (by simp [candidates]))
    (hshift _ (by simp [candidates])) (hshift _ (by simp [candidates]))⟩

-- The least reduction over the breakpoints, the evaluator's lower end for a known change.
-- am[implements a-v2li-sandwich-proof-1020@e2a6a2]
def reductionLeast (b : Need) (k change : ℝ) : ℝ :=
  (breakpoints b change).inf' ⟨b.lo, lo_mem_breakpoints b change⟩ fun n => reduction b k n change

-- The greatest reduction over the breakpoints, the evaluator's upper end for a known change.
-- am[implements a-v2li-sandwich-proof-1020@e2a6a2]
def reductionGreatest (b : Need) (k change : ℝ) : ℝ :=
  (breakpoints b change).sup' ⟨b.lo, lo_mem_breakpoints b change⟩ fun n => reduction b k n change

-- am[implements a-v2li-sandwich-proof-1020@e2a6a2] am[rests-on c-v2li-sandwich-1020@e6d0b5]
theorem reductionLeast_le (b : Need) {k : ℝ} (hk : 0 < k) (d : ℝ) {n : ℝ}
    (hlo : b.lo ≤ n) (hhi : n ≤ b.hi) : reductionLeast b k d ≤ reduction b k n d := by
  obtain ⟨p, hp, q, hq, hn, h | h⟩ := exists_breakpoint_piece b hk d hlo hhi
  · exact (Finset.inf'_le (fun n => reduction b k n d) hp).trans
      (h ⟨le_rfl, hn.1.trans hn.2⟩ hn hn.1)
  · exact (Finset.inf'_le (fun n => reduction b k n d) hq).trans
      (h hn ⟨hn.1.trans hn.2, le_rfl⟩ hn.2)

-- am[implements a-v2li-sandwich-proof-1020@e2a6a2] am[rests-on c-v2li-sandwich-1020@e6d0b5]
theorem le_reductionGreatest (b : Need) {k : ℝ} (hk : 0 < k) (d : ℝ) {n : ℝ}
    (hlo : b.lo ≤ n) (hhi : n ≤ b.hi) : reduction b k n d ≤ reductionGreatest b k d := by
  obtain ⟨p, hp, q, hq, hn, h | h⟩ := exists_breakpoint_piece b hk d hlo hhi
  · exact (h hn ⟨hn.1.trans hn.2, le_rfl⟩ hn.2).trans
      (Finset.le_sup' (fun n => reduction b k n d) hq)
  · exact (h ⟨le_rfl, hn.1.trans hn.2⟩ hn hn.1).trans
      (Finset.le_sup' (fun n => reduction b k n d) hp)

-- The lower end is attained at a breakpoint, which lies in the scale.
-- am[implements a-v2li-sandwich-proof-1020@e2a6a2]
theorem reduction_isLeast (b : Need) {k : ℝ} (hk : 0 < k) (d : ℝ) :
    IsLeast ((fun n => reduction b k n d) '' Icc b.lo b.hi) (reductionLeast b k d) := by
  obtain ⟨p, hp, hpeq⟩ := Finset.exists_mem_eq_inf' ⟨b.lo, lo_mem_breakpoints b d⟩
    fun n => reduction b k n d
  refine ⟨⟨p, breakpoint_bounds b d hp, hpeq.symm⟩, ?_⟩
  rintro _ ⟨n, hn, rfl⟩
  exact reductionLeast_le b hk d hn.1 hn.2

-- am[implements a-v2li-sandwich-proof-1020@e2a6a2]
theorem reduction_isGreatest (b : Need) {k : ℝ} (hk : 0 < k) (d : ℝ) :
    IsGreatest ((fun n => reduction b k n d) '' Icc b.lo b.hi) (reductionGreatest b k d) := by
  obtain ⟨p, hp, hpeq⟩ := Finset.exists_mem_eq_sup' ⟨b.lo, lo_mem_breakpoints b d⟩
    fun n => reduction b k n d
  refine ⟨⟨p, breakpoint_bounds b d hp, hpeq.symm⟩, ?_⟩
  rintro _ ⟨n, hn, rfl⟩
  exact le_reductionGreatest b hk d hn.1 hn.2

-- am[implements a-v2li-image-proof-1020@d6d35f] am[rests-on c-v2li-exact-image-1020@407494]
theorem reduction_continuous (b : Need) {k : ℝ} (hk : 0 ≤ k) (d : ℝ) :
    Continuous fun n => reduction b k n d := by
  have hgap : Continuous (gap b) := continuous_const.max
    ((continuous_const.sub continuous_id).max (continuous_id.sub continuous_const))
  have hdist : Continuous (distance b) := hgap.div_const _
  have hclamp : Continuous (clamp b) := continuous_const.min (continuous_const.max continuous_id)
  have hpow : Continuous fun x : ℝ => x ^ k := Real.continuous_rpow_const hk
  exact (hpow.comp hdist).sub
    (hpow.comp (hdist.comp (hclamp.comp (continuous_id.add continuous_const))))

-- The exact range: every reduction an unknown level can give lies between the breakpoint
-- extremes, and every value between them is some level's reduction.
-- am[implements a-v2li-image-proof-1020@d6d35f] am[rests-on c-v2li-exact-image-1020@407494]
theorem reduction_image_eq (b : Need) {k : ℝ} (hk : 0 < k) (d : ℝ) :
    (fun n => reduction b k n d) '' Icc b.lo b.hi =
      Icc (reductionLeast b k d) (reductionGreatest b k d) := by
  apply Subset.antisymm
  · rintro _ ⟨n, hn, rfl⟩
    exact ⟨reductionLeast_le b hk d hn.1 hn.2, le_reductionGreatest b hk d hn.1 hn.2⟩
  · exact (isPreconnected_Icc.image _ (reduction_continuous b hk.le d).continuousOn).Icc_subset
      (reduction_isLeast b hk d).1 (reduction_isGreatest b hk d).1

-- A need's path value is its goal's priority times the reduction, so a nonnegative priority
-- scales the exact range.
-- am[implements a-v2li-image-proof-1020@d6d35f]
theorem weighted_reduction_image_eq (b : Need) {k w : ℝ} (hk : 0 < k) (hw : 0 ≤ w) (d : ℝ) :
    (fun n => w * reduction b k n d) '' Icc b.lo b.hi =
      Icc (w * reductionLeast b k d) (w * reductionGreatest b k d) := by
  rw [show (fun n => w * reduction b k n d) = (fun r => w * r) ∘ fun n => reduction b k n d
      from rfl, image_comp, reduction_image_eq b hk d,
    image_mul_left_Icc hw ((reduction_isLeast b hk d).2 (reduction_isGreatest b hk d).1)]

-- A worked instance for executable conformance: band [2/5, 3/5] on [0, 1], K = 1 and a change of
-- +1/10. The breakpoints are 0, 3/10, 2/5, 1/2, 3/5, 9/10 and 1, the reductions there 1/4, 1/4,
-- 0, 0, -1/4, -1/4 and 0, and the exact range is [-1/4, 1/4].
-- am[verifies a-v2-lean-intervals-1020@35832d]
theorem example_breakpoint_range :
    (fun n => reduction exampleNeed 1 n (1 / 10)) '' Icc exampleNeed.lo exampleNeed.hi =
      Icc (-(1 / 4)) (1 / 4) := by
  have hleast : reductionLeast exampleNeed 1 (1 / 10) = -(1 / 4) := by
    apply le_antisymm
    · have hmem : (3 / 5 : ℝ) ∈ breakpoints exampleNeed (1 / 10) := by
        norm_num [breakpoints, candidates, exampleNeed]
      exact (Finset.inf'_le (fun n => reduction exampleNeed 1 n (1 / 10)) hmem).trans_eq
        (by norm_num [reduction, drive, distance, gap, margin, clamp, exampleNeed, Real.rpow_one])
    · refine Finset.le_inf' _ _ fun p hp => ?_
      simp only [breakpoints, candidates, Finset.mem_filter, Finset.mem_insert,
        Finset.mem_singleton] at hp
      obtain ⟨hp | hp | hp | hp | hp | hp | hp | hp, -⟩ := hp <;> subst hp <;>
        norm_num [reduction, drive, distance, gap, margin, clamp, exampleNeed, Real.rpow_one]
  have hgreatest : reductionGreatest exampleNeed 1 (1 / 10) = 1 / 4 := by
    apply le_antisymm
    · refine Finset.sup'_le _ _ fun p hp => ?_
      simp only [breakpoints, candidates, Finset.mem_filter, Finset.mem_insert,
        Finset.mem_singleton] at hp
      obtain ⟨hp | hp | hp | hp | hp | hp | hp | hp, -⟩ := hp <;> subst hp <;>
        norm_num [reduction, drive, distance, gap, margin, clamp, exampleNeed, Real.rpow_one]
    · have hmem : (0 : ℝ) ∈ breakpoints exampleNeed (1 / 10) := by
        norm_num [breakpoints, candidates, exampleNeed]
      exact le_of_eq_of_le
        (by norm_num [reduction, drive, distance, gap, margin, clamp, exampleNeed, Real.rpow_one])
        (Finset.le_sup' (fun n => reduction exampleNeed 1 n (1 / 10)) hmem)
  rw [reduction_image_eq exampleNeed one_pos (1 / 10), hleast, hgreatest]

end GoalChainerMotivation

#print axioms GoalChainerMotivation.reduction_image_eq
#print axioms GoalChainerMotivation.reduction_isLeast
#print axioms GoalChainerMotivation.reduction_isGreatest
#print axioms GoalChainerMotivation.weighted_reduction_image_eq
#print axioms GoalChainerMotivation.candidates_image_clamp
#print axioms GoalChainerMotivation.example_breakpoint_range

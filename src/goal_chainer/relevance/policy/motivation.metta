; Purpose: the relevance review's motivation policy: from a domain's declared needs and expected
; changes and a stream's need observations and host attempts, derive each need's level at the
; review's instant, each action's expected change of each need, learned from attributed measured
; changes, and each action's reduction interval of each need's urgency, which the ranking reads
; before it appraises any candidate.
;
;   (gc-motivation-snapshot
;     (MotivationInput (AsOf T)
;                      (Needs ((Need "ID" "GOAL" LO HI LOW HIGH K) ...))
;                      (Declared ((Expectation "ACTION" "NEED" CHANGE "CLASS") ...))
;                      (Actions ("ACTION" ...))
;                      (Observations ((Obs "ID" "NEED" LEVEL LO HI "CLASS" AT UNTIL PRODUCER) ...))
;                      (Attempts ((Attempt "ID" "ACTION" APPLIED) ...))))
;     -> (Snapshot (Levels ((Level "NEED" STATE VALUE DISTANCE URGENCY (Support ((Sup "OBS" "CLASS") ...))) ...))
;                  (Changes ((Change "ACTION" "NEED" STATE MEAN COUNT CLASS (Samples ((Key "ATTEMPT" "BEFORE" "AFTER") ...))) ...))
;                  (Reductions ((Reduction "ACTION" "NEED" (Interval LOW HIGH) (Interval FROM TO)) ...))
;                  (Samples ((Sample "ATTEMPT" "ACTION" "NEED" ("BEFORE" ...) ("AFTER" ...) CHANGE PRIOR RESIDUAL) ...))
;                  (NotSampled ((NotSampled "ATTEMPT" "NEED" "REASON") ...))
;                  (Excluded ((Excluded "OBS" "REASON") ...)))
;
; T, AT and an applied instant are microseconds; UNTIL is (Until MICROSECONDS) or Forever, PRODUCER
; (ProducedBy "ATTEMPT") or Unstated and APPLIED (Applied MICROSECONDS) or NotApplied. Numbers are
; floats with -0.0 written 0.0, since == tells the two apart, and K >= 1 (c-v2m-drive-convex-1019);
; LO HI on an observation is the scale it was recorded on. A Level's STATE is "observed", with VALUE
; its number, DISTANCE its band distance
; and URGENCY that distance to the power K, or "unobserved", "expired" or "conflicted", each an
; unknown level whose VALUE, DISTANCE and URGENCY are None. A Change's STATE is "measured", MEAN the
; mean of its COUNT samples and CLASS "receipt-calibrated", "declared", MEAN and CLASS the domain's,
; or "unknown" with MEAN and CLASS None; a sample's key is (Key "ATTEMPT" ("BEFORE" ...) ("AFTER" ...)).
; A Sample's PRIOR is the expectation it was observed against and RESIDUAL its change minus that,
; both None before any expectation existed.
;
; The rules, each one function below:
;   level      the latest observation of the need at or before T decides; none is unobserved, all
;              of the latest expired is expired, and the latest disagreeing is conflicted
;              (c-v2m-latest-is-state-1019);
;   distance   x(n) = (max(LOW - n, 0) + max(n - HIGH, 0)) / max(LOW - LO, HI - HIGH), 0 for a band
;              spanning the scale, and urgency x^K (c-v2m-reduction-formula-1019);
;   endpoint   the observations of one need sharing its latest instant in a window, those still valid
;              where validity is asked, agreeing on one level: all of them are its support, whatever
;              order they arrive in, and it establishes when any of them is of an establishing class,
;              as a reading's strongest agreeing class licenses it (c-v2m-endpoint-order-free-1019);
;   sample     an applied attempt at or before T, with no other applied at its instant: its outcome
;              is the endpoint of its observations of the need produced_by it after its application
;              and not after the stream's next applied attempt or T, and its baseline the endpoint of
;              the need's observations at or before its application that are valid then, so an
;              expired pre-state is never resurrected by an older one; both must establish, and the
;              outcome counts at its own observation, whatever T is (c-v2m-receipt-window-1019,
;              c-v2m-window-subject-1019); it is a host-attributed change, an association and not a
;              causal measurement (c-v2m-attribution-associational-1019);
;   change     the running mean m_k = m_(k-1) + (x_k - m_(k-1)) / k of an action's samples in the
;              order applied, which replaces the declared change from the first sample on
;              (c-v2m-sample-mean-convex-1019);
;   reduction  x(n)^K - x(clamp(n + d))^K, a point for a known level and change; for an unknown level
;              and a known change the least and greatest value over the breakpoints {LO, LOW, HIGH,
;              HI, LO-d, LOW-d, HIGH-d, HI-d} inside the scale, among which the parent's proof puts
;              the real reduction's extremes (c-v2m-breakpoints-1019); for a known level and an
;              unknown change [x(n)^K - 1, x(n)^K], and for both unknown [-1, 1], 0 everywhere when
;              the band spans the scale (c-v2m-whole-range-cases-1019); each value has exactly the
;              sign of x(n) - x(clamp(n + d)), whatever K (c-v2r-sign-invariant-1020), below;
;   predicted  clamp(n + d), the level a known change is predicted to leave: [FROM, TO] is that point,
;              the clamped targets of LO and HI for an unknown level, the scale for an unknown change.
; The real model's inputs are the binary64 values the engine reads, not the decimals a domain or a
; host writes: on [0, 1] with band [0.05, 0.95], d = 0.96 and K = 1 the real upper end is 0.8 on the
; decimals and 0.7999999999999992 on their binary64 values (c-v2li-input-conversion-1020); a learned
; change's input is the double the snapshot reports for it. Every urgency lies in [0, 1] and every
; reduction, and every end of a reduction's interval, in [-1, 1]; each has exactly the sign of the
; real model's value on those inputs and is 0.0 exactly where that value is 0, except that a nonzero
; value below the least normal double, 2^-1022, can round to 0.0, never to the other sign, since
; subnormal urgencies keep too few bits (a-v2r-exact-sign-1020). Its magnitude is a floating-point
; evaluation from the exact gaps (a-v2r-stable-magnitude-1020), whose error tests measure against an
; 800-digit reference and no proof bounds (docs/mathematical-contracts.md): an end can miss the real
; range's on the same side of 0, and no interval is claimed to enclose it (i-v2li-float-round-trip-1020,
; c-v2li-b-misses-ulps-1020).
; Every function is prefixed gc-motivation-, since names are global to the process's one engine,
; and every destructuring is its own small function (c-rel-petta-case-scope-1016).
; am[implements a-v2m-levels-1019@387e68] am[implements a-v2m-expectations-1019@b13468]
; am[rests-on c-v2m-reduction-formula-1019@0fcd08] am[rests-on c-v2m-breakpoints-1019@8e56ef]
; am[rests-on c-v2m-whole-range-cases-1019@b4864a] am[rests-on c-v2m-latest-is-state-1019@c5a57e]
; am[rests-on c-v2m-receipt-window-1019@9fe31b] am[rests-on c-v2m-window-subject-1019@077441]
; am[rests-on c-v2m-attribution-associational-1019@daf305] am[rests-on c-v2m-sample-mean-convex-1019@5e2db0]
; am[rests-on c-rel-strings-inert-1016@947e27] am[rests-on c-rel-petta-case-scope-1016@431484]
; am[rests-on c-v2m-endpoint-order-free-1019@6a9e43]

; ---- reading the input -----------------------------------------------------------------------

(= (gc-motivation-as-of (MotivationInput (AsOf $t) $n $d $a $o $m)) $t)
(= (gc-motivation-needs (MotivationInput $t (Needs $n) $d $a $o $m)) $n)
(= (gc-motivation-declared (MotivationInput $t $n (Declared $d) $a $o $m)) $d)
(= (gc-motivation-actions (MotivationInput $t $n $d (Actions $a) $o $m)) $a)
(= (gc-motivation-observations (MotivationInput $t $n $d $a (Observations $o) $m)) $o)
(= (gc-motivation-attempts (MotivationInput $t $n $d $a $o (Attempts $m))) $m)

(= (gc-motivation-need-id (Need $id $goal $lo $hi $low $high $k)) $id)
(= (gc-motivation-need-lo (Need $id $goal $lo $hi $low $high $k)) $lo)
(= (gc-motivation-need-hi (Need $id $goal $lo $hi $low $high $k)) $hi)
(= (gc-motivation-need-low (Need $id $goal $lo $hi $low $high $k)) $low)
(= (gc-motivation-need-high (Need $id $goal $lo $hi $low $high $k)) $high)
(= (gc-motivation-need-k (Need $id $goal $lo $hi $low $high $k)) $k)

(= (gc-motivation-expected-action (Expectation $action $need $change $class)) $action)
(= (gc-motivation-expected-need (Expectation $action $need $change $class)) $need)
(= (gc-motivation-expected-change (Expectation $action $need $change $class)) $change)
(= (gc-motivation-expected-class (Expectation $action $need $change $class)) $class)

(= (gc-motivation-obs-id (Obs $id $need $level $lo $hi $class $at $until $producer)) $id)
(= (gc-motivation-obs-need (Obs $id $need $level $lo $hi $class $at $until $producer)) $need)
(= (gc-motivation-obs-level (Obs $id $need $level $lo $hi $class $at $until $producer)) $level)
(= (gc-motivation-obs-lo (Obs $id $need $level $lo $hi $class $at $until $producer)) $lo)
(= (gc-motivation-obs-hi (Obs $id $need $level $lo $hi $class $at $until $producer)) $hi)
(= (gc-motivation-obs-class (Obs $id $need $level $lo $hi $class $at $until $producer)) $class)
(= (gc-motivation-obs-at (Obs $id $need $level $lo $hi $class $at $until $producer)) $at)
(= (gc-motivation-obs-until (Obs $id $need $level $lo $hi $class $at $until $producer)) $until)
(= (gc-motivation-obs-producer (Obs $id $need $level $lo $hi $class $at $until $producer)) $producer)

(= (gc-motivation-attempt-id (Attempt $id $action $applied)) $id)
(= (gc-motivation-attempt-action (Attempt $id $action $applied)) $action)
(= (gc-motivation-attempt-applied (Attempt $id $action $applied)) $applied)

; ---- which observations count --------------------------------------------------------------------
; An observation counts for its need when the domain declares the need on the scale the observation
; was recorded on, one recorded against another scale having measured another quantity, and when the
; shared vocabulary still holds its estimator class, which a stream recorded under an older
; vocabulary may lack. Observations made
; after the review's instant are not yet part of its history and are neither counted nor listed.

(= (gc-motivation-need-of $needs $id) (gc-relevance-first (filter-atom $needs $n (== (gc-motivation-need-id $n) $id))))
(= (gc-motivation-exclusion $needs $obs) (gc-motivation-exclusion-of (gc-motivation-need-of $needs (gc-motivation-obs-need $obs)) $obs))
(= (gc-motivation-exclusion-of None $obs) (Some "undeclared-need"))
(= (gc-motivation-exclusion-of (Some $need) $obs)
   (if (and (== (gc-motivation-obs-lo $obs) (gc-motivation-need-lo $need))
            (== (gc-motivation-obs-hi $obs) (gc-motivation-need-hi $need)))
       (if (gc-has (gc-estimator-classes) (gc-motivation-obs-class $obs)) None (Some "unknown-estimator"))
       (Some "scale-changed")))
(= (gc-motivation-excluded $needs $obs) (gc-motivation-excluded-of $obs (gc-motivation-exclusion $needs $obs)))
(= (gc-motivation-excluded-of $obs None) ())
(= (gc-motivation-excluded-of $obs (Some $reason)) ((Excluded (gc-motivation-obs-id $obs) $reason)))
(= (gc-motivation-counts $needs $obs) (== (gc-motivation-exclusion $needs $obs) None))

(= (gc-motivation-of-need $observations $need)
   (filter-atom $observations $o (== (gc-motivation-obs-need $o) (gc-motivation-need-id $need))))
(= (gc-motivation-by-at-most $observations $t) (filter-atom $observations $o (<= (gc-motivation-obs-at $o) $t)))

; The observations sharing the latest instant of a nonempty list.
(= (gc-motivation-latest $observations)
   (gc-motivation-at-instant $observations (max-atom (map-atom $observations $o (gc-motivation-obs-at $o)))))
(= (gc-motivation-at-instant $observations $at) (filter-atom $observations $o (== (gc-motivation-obs-at $o) $at)))
(= (gc-motivation-values $observations) (unique-atom (map-atom $observations $o (gc-motivation-obs-level $o))))
(= (gc-motivation-support $observations) (map-atom $observations $o (Sup (gc-motivation-obs-id $o) (gc-motivation-obs-class $o))))
(= (gc-motivation-ids $observations) (map-atom $observations $o (gc-motivation-obs-id $o)))
; Whether an endpoint establishes: any of its agreeing observations of an establishing class does,
; so neither their order nor the spelling of their ids decides it.
(= (gc-motivation-establishes $observations)
   (gc-relevance-any (map-atom $observations $o (gc-establishes (gc-motivation-obs-class $o)))))

; ---- distance and urgency (c-v2m-reduction-formula-1019) ---------------------------------------------

(= (gc-motivation-span $need)
   (max (- (gc-motivation-need-low $need) (gc-motivation-need-lo $need))
        (- (gc-motivation-need-hi $need) (gc-motivation-need-high $need))))
; A gap from a level's two signed differences to the band, LOW - n and n - HIGH.
(= (gc-motivation-gap-of $below $above) (+ (max $below 0.0) (max $above 0.0)))
(= (gc-motivation-gap $need $value)
   (gc-motivation-gap-of (- (gc-motivation-need-low $need) $value) (- $value (gc-motivation-need-high $need))))
; The gap never exceeds the span for a level inside the scale; min keeps rounding from passing 1.
(= (gc-motivation-distance $need $value) (gc-motivation-scaled (gc-motivation-span $need) (gc-motivation-gap $need $value)))
(= (gc-motivation-scaled $span $gap) (if (> $span 0.0) (min 1.0 (/ $gap $span)) 0.0))
; A level's urgency, from its exact gap (a-v2r-stable-magnitude-1020).
(= (gc-motivation-urgency $need $value) (gc-motivation-urgency-of $need (gc-motivation-gap-terms $need (At $value 0.0))))
; The largest urgency any level of the scale has: 1 at the end farther from the band, or 0 when the
; band spans the scale.
(= (gc-motivation-top $need) (if (> (gc-motivation-span $need) 0.0) 1.0 0.0))

; ---- exact signs (c-v2r-sign-invariant-1020) ------------------------------------------------------------
; A reduction is positive, zero or negative exactly as the level's gap exceeds, equals or falls
; short of its target's, whatever K and the span are, so its sign is a comparison of two distances,
; each a short sum of the doubles the snapshot holds. The engine's own + and - decide such a
; comparison exactly: Knuth's TwoSum gives a sum's rounding error exactly (c-v2r-twosum-exact-1020)
; and Shewchuk's Grow-Expansion turns a list of doubles into a nonoverlapping expansion whose largest
; component has its sum's sign (c-v2r-expansion-sign-1020). A place on the scale is (At BASE OFFSET),
; the real BASE + OFFSET: a level n is (At n 0.0), the target a change d moves it to (At n d), and the
; level from which d reaches b (At b -d), so neither n + d nor b - d is ever rounded across a band
; edge or overflowed (the parent's review of d4c87737: n = 1.7e308, d = 3e307 on [1.4e308, 1.7e308]).
; Every difference formed is of two quantities on the scale and every partial sum is within twice
; its width, which needs.py requires to be a finite double.
; am[implements a-v2r-exact-sign-1020] am[rests-on c-v2r-sign-invariant-1020]
; am[rests-on c-v2r-twosum-exact-1020] am[rests-on c-v2r-expansion-sign-1020] am[rests-on c-v2r-side-test-1020]

; Knuth's TwoSum: (Sum S E), S = fl(A + B) and S + E = A + B exactly in binary64 round-to-nearest.
(= (gc-motivation-two-sum $a $b) (gc-motivation-two-sum-of $a $b (+ $a $b)))
(= (gc-motivation-two-sum-of $a $b $s) (gc-motivation-two-sum-error $a $b $s (- $s $a)))
(= (gc-motivation-two-sum-error $a $b $s $bb) (Sum $s (+ (- $a (- $s $bb)) (- $b $bb))))

; -1, 0 or 1 by a number's sign, -0.0 being 0.
(= (gc-motivation-sign $x) (if (> $x 0.0) 1 (if (< $x 0.0) -1 0)))

(= (gc-motivation-at-base (At $base $offset)) $base)
(= (gc-motivation-at-offset (At $base $offset)) $offset)

; Where place (At B O) lies from the double Z: -1 below it, 0 on it, 1 above it. With
; (S, E) = TwoSum(Z, -B), Z - B - O has the sign of S - O where S differs from O and of E where it
; does not, since rounding to nearest is monotone (c-v2r-side-test-1020).
(= (gc-motivation-side (At $base $offset) $z) (gc-motivation-side-of (gc-motivation-two-sum $z (- 0.0 $base)) $offset))
(= (gc-motivation-side-of (Sum $s $e) $offset)
   (if (> $s $offset) -1 (if (< $s $offset) 1 (- 0 (gc-motivation-sign $e)))))
(= (gc-motivation-on-scale? $need $place)
   (and (>= (gc-motivation-side $place (gc-motivation-need-lo $need)) 0)
        (<= (gc-motivation-side $place (gc-motivation-need-hi $need)) 0)))
; The level a place stands for: itself on the scale, the nearer end beyond it.
(= (gc-motivation-clamped $need $place)
   (if (<= (gc-motivation-side $place (gc-motivation-need-lo $need)) 0)
       (At (gc-motivation-need-lo $need) 0.0)
       (if (>= (gc-motivation-side $place (gc-motivation-need-hi $need)) 0)
           (At (gc-motivation-need-hi $need) 0.0)
           $place)))

; A place's gap to the band as doubles whose exact sum it is, LOW - B - O below the band and
; B - HIGH + O above it, none inside, each starting from a difference across the scale.
(= (gc-motivation-gap-terms $need $place)
   (if (< (gc-motivation-side $place (gc-motivation-need-low $need)) 0)
       (gc-motivation-terms-of (gc-motivation-two-sum (gc-motivation-need-low $need) (- 0.0 (gc-motivation-at-base $place)))
                               (- 0.0 (gc-motivation-at-offset $place)))
       (if (> (gc-motivation-side $place (gc-motivation-need-high $need)) 0)
           (gc-motivation-terms-of (gc-motivation-two-sum (gc-motivation-at-base $place) (- 0.0 (gc-motivation-need-high $need)))
                                   (gc-motivation-at-offset $place))
           ())))
(= (gc-motivation-terms-of (Sum $s $e) $offset) ($s $e $offset))
(= (gc-motivation-negated $terms) (map-atom $terms $t (- 0.0 $t)))

; Shewchuk's Grow-Expansion: the double B absorbs expansion E's components from the smallest,
; leaving each TwoSum's error behind, so the result is again nonoverlapping and by increasing
; magnitude. Time: k components, k TwoSums.
(= (gc-motivation-grow $expansion $b)
   (gc-motivation-grown (foldl-atom $expansion (Grow $b ()) $acc $e (gc-motivation-grow-step $acc $e))))
(= (gc-motivation-grow-step (Grow $q $errors) $e) (gc-motivation-grow-into (gc-motivation-two-sum $q $e) $errors))
(= (gc-motivation-grow-into (Sum $q $h) $errors) (Grow $q (cons-atom $h $errors)))
(= (gc-motivation-grown (Grow $q $errors)) (gc-relevance-reversed (cons-atom $q $errors)))
; The exact sum of t doubles as an expansion. Time: t^2 / 2 TwoSums.
(= (gc-motivation-expansion $terms) (foldl-atom $terms () $acc $t (gc-motivation-grow $acc $t)))
; An expansion's largest nonzero component, which has its sum's sign, or 0.0 for a zero sum. It is
; no estimate of the sum's size: after cancellation it keeps beside it the rounding errors of larger
; partial sums, so (0.001488668423428358 -1.0757318430129614e-19 -0.0014886684234283578), whose sum
; is 1.0926725019580474e-19, leads with 2.168404344971009e-19 (i-v2r-leading-not-value-1020).
(= (gc-motivation-leading $expansion) (foldl-atom $expansion 0.0 $acc $c (if (== (gc-motivation-sign $c) 0) $acc $c)))
; An expansion's value as a double: its components summed from the smallest, 0.0 only for a zero
; sum and, for m components, within 4.5 (1 + 2^-53)^m 2^-53 of the sum relative to it: an expansion
; grown by Grow-Expansion under round-to-nearest-even is nonadjacent (Shewchuk 1997, Theorem 10), so
; the components below each one sum to less than half of it, and no partial sum overflows, since
; every term is within the scale's finite width (c-v2r-expansion-value-1020). Rounding a gap's terms'
; plain sum is not: B - HIGH and O can cancel to 0.0 while the TwoSum error left beside them, 1e-300
; for a level 1e-300 above a band on [1e-300, 1], is the gap. Time: one addition per component.
; am[implements a-v2r-stable-magnitude-1020] am[rests-on c-v2r-expansion-value-1020]
(= (gc-motivation-value $expansion) (foldl-atom $expansion 0.0 $acc $c (+ $acc $c)))

; ---- magnitudes (a-v2r-stable-magnitude-1020) ---------------------------------------------------------
; Urgencies and reductions are evaluated from the exact gaps, so that K never raises a rounding the
; real model's inputs lack. A gap near the span is the case that needs it: on [0, 1] with band
; [0, 0], level 1 and change -5e-17, the target's gap 1 - 5e-17 rounds to 1, and the difference of
; two rounded urgencies is 0.0 where the real reduction is 5e-17 at K = 1 and 1 - e^-0.5 = 0.393469
; at K = 1e16; the first-order term K u(a)(a - b) / a that stood in for it gave 0.5 and, at K = 1e308,
; 5e291 (i-v2r-first-order-large-k-1020). Each value is formed so that it lies in [0, 1], so every
; reduction lies in [-1, 1] whatever K; its error is measured against a high-precision reference
; (tests/test_mathematical_contracts.py), not proved.
; am[implements a-v2r-stable-magnitude-1020] am[addresses i-v2r-first-order-large-k-1020]
; am[addresses i-v2r-leading-not-value-1020]

; The span S as doubles whose exact sum it is: the gap of the end of the scale farther from the band.
(= (gc-motivation-span-terms $need) (gc-motivation-gap-terms $need (gc-motivation-worst $need)))

; The urgency (g / S)^K of a gap g, given as doubles whose exact sum it is and that sum's value:
; pow(g / S, K) for g <= S / 2, and above it exp(K log1p(-(S - g) / S)) with S - g formed exactly,
; since g / S rounds to 1 while g < S. It is 0.0 for a zero gap, whatever the span, and lies in
; [0, 1]: g / S <= 1/2 below and K log1p(-x) <= 0 above. Time: three expansions of at most six
; terms, so at most 21 TwoSums, and one power or exp.
(= (gc-motivation-urgency-of $need $terms) (gc-motivation-urgency-of-gap $need $terms (gc-motivation-value (gc-motivation-expansion $terms))))
(= (gc-motivation-urgency-of-gap $need $terms $gap)
   (if (<= $gap 0.0)
       0.0
       (let* (($span (gc-motivation-span-terms $need))
              ($s (gc-motivation-value (gc-motivation-expansion $span))))
         (if (<= $gap (* 0.5 $s))
             (pow-math (/ $gap $s) (gc-motivation-need-k $need))
             (exp-math (gc-motivation-k-log1p (gc-motivation-need-k $need)
                         (gc-motivation-value (gc-motivation-expansion (union-atom $span (gc-motivation-negated $terms))))
                         $s))))))

; K log1p(-N / D) for K >= 1 and 0 <= N / D <= 1/2 + a rounding, neither overflowing, since
; |log1p(-x)| < 1 there, nor rounding to 0 before its time: below the least normal double 2^-1022,
; N / D keeps too few bits for K to multiply, so K N / D is formed as (K 2^-1022)((N 2^1022) / D),
; whose factors are exact or normal down to where K N / D falls below 2^-1022 itself (N < 4 there,
; since D is at most the largest double).
(= (gc-motivation-k-log1p $k $n $d) (gc-motivation-k-log1p-of $k $n $d (/ $n $d)))
(= (gc-motivation-k-log1p-of $k $n $d $x)
   (if (< $x 2.2250738585072014e-308)
       (- 0.0 (* (* $k 2.2250738585072014e-308) (/ (* $n 4.49423283715579e+307) $d)))
       (* $k (gc-motivation-log1p (- 0.0 $x)))))

; Kahan's log1p (Goldberg 1991, Theorem 4; c-v2r-kahan-log1p-1020): z where 1 + z rounds to 1, and
; otherwise ln(w) z / (w - 1) for w = fl(1 + z), whose quotient cancels the rounding of w.
(= (gc-motivation-log1p $z) (gc-motivation-log1p-of $z (+ 1.0 $z)))
(= (gc-motivation-log1p-of $z $w) (if (== $w 1.0) $z (* (gc-motivation-ln $w) (/ $z (- $w 1.0)))))
; The natural logarithm: log-math divides by log(2.718281828459045), which is 1.0 (c-v2r-engine-math-matches-libm-1020).
(= (gc-motivation-ln $x) (log-math 2.718281828459045 $x))

; 1 - e^z for z <= 0, which lies in [0, 1]: 1 - u itself where u = fl(e^z) <= 1/2, -z where u rounds
; to 1, and otherwise Kahan's (1 - u) z / ln u (Higham 2002, section 1.14.1; c-v2r-kahan-expm1-1020),
; whose quotient cancels the rounding of u.
(= (gc-motivation-one-minus-exp $z) (gc-motivation-one-minus-exp-of $z (exp-math $z)))
(= (gc-motivation-one-minus-exp-of $z $u)
   (if (<= $u 0.5)
       (- 1.0 $u)
       (if (== $u 1.0) (- 0.0 $z) (* (- 1.0 $u) (/ $z (gc-motivation-ln $u))))))

; The reduction of urgency from place FROM to place TO, both on the scale: 0.0 exactly when their
; gaps are equal, and otherwise a magnitude with the sign of their gaps' exact difference.
; Time: at most six terms, so at most 15 TwoSums for the difference, and two urgencies.
(= (gc-motivation-moved $need $from $to)
   (gc-motivation-moved-of $need (gc-motivation-gap-terms $need $from) (gc-motivation-gap-terms $need $to)))
(= (gc-motivation-moved-of $need $before $after)
   (gc-motivation-signed $need $before $after (gc-motivation-expansion (union-atom $before (gc-motivation-negated $after)))))
(= (gc-motivation-signed $need $before $after $difference)
   (gc-motivation-signed-by $need $before $after $difference (gc-motivation-leading $difference)))
(= (gc-motivation-signed-by $need $before $after $difference $leading)
   (if (> $leading 0.0)
       (gc-motivation-magnitude $need $before $after $difference)
       (if (< $leading 0.0)
           (- 0.0 (gc-motivation-magnitude $need $after $before (gc-motivation-negated $difference)))
           0.0)))
; u(a) - u(b) for gaps a > b, given as doubles whose exact sums they are with the expansion of a - b:
; the urgencies' difference for b <= a / 2, where u(b) <= u(a) / 2 so nothing cancels, and above it
; u(a)(1 - e^(K log1p(-(a - b) / a))) with a - b formed exactly, where the two urgencies agree to their
; last bits; Boost.Math's powm1 forms x^y - 1 as expm1(y log x) for the same reason
; (c-v2r-powm1-prior-art-1020). It lies in [0, u(a)].
(= (gc-motivation-magnitude $need $larger $smaller $difference)
   (let* (($a (gc-motivation-value (gc-motivation-expansion $larger)))
          ($b (gc-motivation-value (gc-motivation-expansion $smaller))))
     (if (<= $b (* 0.5 $a))
         (- (gc-motivation-urgency-of-gap $need $larger $a) (gc-motivation-urgency-of-gap $need $smaller $b))
         (* (gc-motivation-urgency-of-gap $need $larger $a)
            (gc-motivation-one-minus-exp (gc-motivation-k-log1p (gc-motivation-need-k $need) (gc-motivation-value $difference) $a))))))
; The reduction a change brings at a level: the move to the level's target, clamped to the scale.
(= (gc-motivation-moved-by $need $level $change)
   (gc-motivation-moved $need (At $level 0.0) (gc-motivation-clamped $need (At $level $change))))
; The end of the scale farther from the band, whose urgency is the top; LO where both are as far.
(= (gc-motivation-worst $need)
   (if (< (gc-motivation-leading
            (gc-motivation-expansion (union-atom (gc-motivation-gap-terms $need (At (gc-motivation-need-lo $need) 0.0))
                                                 (gc-motivation-negated (gc-motivation-gap-terms $need (At (gc-motivation-need-hi $need) 0.0))))))
          0.0)
       (At (gc-motivation-need-hi $need) 0.0)
       (At (gc-motivation-need-lo $need) 0.0)))

; ---- levels ------------------------------------------------------------------------------------------
; Time: one pass over the need's counted observations.

(= (gc-motivation-level $t $need $counted)
   (gc-motivation-level-from $t $need (gc-motivation-by-at-most (gc-motivation-of-need $counted $need) $t)))
(= (gc-motivation-level-from $t $need $mine)
   (if (== $mine ())
       (gc-motivation-unknown $need "unobserved" ())
       (gc-motivation-latest-level $t $need (gc-motivation-latest $mine))))
(= (gc-motivation-latest-level $t $need $latest)
   (gc-motivation-valid-level $need $latest (filter-atom $latest $o (gc-motivation-valid-at $t (gc-motivation-obs-until $o)))))
(= (gc-motivation-valid-at $t Forever) True)
(= (gc-motivation-valid-at $t (Until $until)) (>= $until $t))
(= (gc-motivation-valid-level $need $latest $valid)
   (if (== $valid ())
       (gc-motivation-unknown $need "expired" (gc-motivation-support $latest))
       (gc-motivation-agreed-level $need $valid (gc-motivation-values $valid))))
(= (gc-motivation-agreed-level $need $valid $values)
   (if (== (size-atom $values) 1)
       (gc-motivation-observed $need (car-atom $values) (gc-motivation-support $valid))
       (gc-motivation-unknown $need "conflicted" (gc-motivation-support $valid))))
(= (gc-motivation-observed $need $value $support)
   (Level (gc-motivation-need-id $need) "observed" $value (gc-motivation-distance $need $value)
          (gc-motivation-urgency $need $value) (Support $support)))
(= (gc-motivation-unknown $need $state $support) (Level (gc-motivation-need-id $need) $state None None None (Support $support)))

(= (gc-motivation-level-need (Level $need $state $value $distance $urgency $support)) $need)
(= (gc-motivation-level-state (Level $need $state $value $distance $urgency $support)) $state)
(= (gc-motivation-level-value (Level $need $state $value $distance $urgency $support)) $value)
(= (gc-motivation-level-of $levels $need)
   (car-atom (filter-atom $levels $l (== (gc-motivation-level-need $l) (gc-motivation-need-id $need)))))
(= (gc-motivation-known-level $level)
   (if (== (gc-motivation-level-state $level) "observed") (Known (gc-motivation-level-value $level)) Unknown))

; ---- samples (c-v2m-receipt-window-1019, c-v2m-window-subject-1019) -------------------------------------
; Every applied attempt at or before T, for every need it produced an observation of, gives one
; sample or one (NotSampled ATTEMPT NEED REASON) naming the first rule it fails, in this order. The
; stream is swept in time order rather than searched once per attempt (a-v2m-snapshot-sweep-1020):
; sort-atom is the engine's msort, so a sort of s entries costs s log s comparisons, and every other
; step is one fold over a sorted list, since index-atom would walk a list to reach an element
; (c-v2m-nth0-walks-lists-1020). Each sort keys its entries by instant and id, both unique to the
; record they key, so the order is total and no entry depends on the order the stream holds them.

; One level of nesting removed in time linear in the result: lib_functional's flatten-once appends
; each element to the growing result, which copies the result every time, so a stream's lists are
; joined last first, each prepended to what follows it with union-atom, which is append/3 and so
; copies only the list it prepends (c-v2m-flatten-once-quadratic-1020).
(= (gc-motivation-concat $lists) (foldl-atom (gc-relevance-reversed $lists) () $acc $list (union-atom $list $acc)))

(= (gc-motivation-applied-time (Applied $at)) (Some $at))
(= (gc-motivation-applied-time NotApplied) None)

; The observations in the order of their instants and then their ids.
(= (gc-motivation-in-time-order $observations)
   (map-atom (sort-atom (map-atom $observations $o (gc-motivation-time-key $o))) $k (gc-motivation-keyed $k)))
(= (gc-motivation-time-key $o) (Keyed (gc-motivation-obs-at $o) (gc-motivation-obs-id $o) $o))
(= (gc-motivation-keyed (Keyed $at $id $item)) $item)

; The attempts applied at or before T, as (At AT ID ACTION) in the order of their instants and ids.
(= (gc-motivation-applied-at $t $attempts)
   (sort-atom (gc-motivation-concat (map-atom $attempts $a (gc-motivation-applied-entry $t $a)))))
(= (gc-motivation-applied-entry $t (Attempt $id $action $applied))
   (gc-motivation-applied-entry-of $t $id $action (gc-motivation-applied-time $applied)))
(= (gc-motivation-applied-entry-of $t $id $action None) ())
(= (gc-motivation-applied-entry-of $t $id $action (Some $at)) (if (<= $at $t) ((At $at $id $action)) ()))
(= (gc-motivation-entry-at (At $at $id $action)) $at)

; The applied attempts grouped by instant, latest first, as (Group AT (ENTRY ...)): entries sharing
; an instant are adjacent once sorted, so one fold conses each onto the group it continues.
(= (gc-motivation-instant-groups $applied) (foldl-atom $applied () $acc $entry (gc-motivation-group-step $acc $entry)))
(= (gc-motivation-group-step $groups $entry)
   (if (== $groups ())
       ((Group (gc-motivation-entry-at $entry) ($entry)))
       (gc-motivation-group-onto (car-atom $groups) (cdr-atom $groups) $entry)))
(= (gc-motivation-group-onto (Group $at $members) $rest $entry)
   (if (== $at (gc-motivation-entry-at $entry))
       (cons-atom (Group $at (cons-atom $entry $members)) $rest)
       (cons-atom (Group (gc-motivation-entry-at $entry) ($entry)) (cons-atom (Group $at $members) $rest))))

; Each applied attempt as (Slot AT ID ACTION SIMULTANEOUS END), earliest first: SIMULTANEOUS when
; another applied attempt shares its instant, and END the stream's next applied instant after it,
; or T after the last, since one stream is one subject and any act on it may move any of its needs.
; Folding the groups latest first and consing leaves the slots earliest first.
(= (gc-motivation-slots $t $groups)
   (gc-motivation-slots-of (foldl-atom $groups (Next $t ()) $acc $group (gc-motivation-slot-step $acc $group))))
(= (gc-motivation-slots-of (Next $end $slots)) $slots)
(= (gc-motivation-slot-step (Next $end $slots) (Group $at $members))
   (Next $at (gc-motivation-group-slots $members (> (size-atom $members) 1) $end $slots)))
(= (gc-motivation-group-slots $members $simultaneous $end $slots)
   (foldl-atom $members $slots $acc $member (cons-atom (gc-motivation-slot $member $simultaneous $end) $acc)))
(= (gc-motivation-slot (At $at $id $action) $simultaneous $end) (Slot $at $id $action $simultaneous $end))
(= (gc-motivation-slot-at (Slot $at $id $action $simultaneous $end)) $at)

; Each slot with each need's baseline candidates, as (Based SLOT (LATEST ...)) in the needs' order,
; LATEST being (Latest AT (OBSERVATION ...)), the need's counted observations at the latest instant
; at or before the slot's, or None: every need's history, in time order, is consumed once across
; all the slots.
(= (gc-motivation-based $slots $needs $counted)
   (gc-motivation-based-of
     (foldl-atom $slots (Sweeps (map-atom $needs $n (Sweep (gc-motivation-of-need $counted $n) None)) ()) $acc $slot
       (gc-motivation-sweeps-step $acc $slot))))
(= (gc-motivation-based-of (Sweeps $states $out)) (gc-relevance-reversed $out))
(= (gc-motivation-sweeps-step (Sweeps $states $out) $slot)
   (gc-motivation-sweeps-next (map-atom $states $s (gc-motivation-sweep-to $s (gc-motivation-slot-at $slot))) $slot $out))
(= (gc-motivation-sweeps-next $states $slot $out)
   (Sweeps $states (cons-atom (Based $slot (map-atom $states $s (gc-motivation-sweep-latest $s))) $out)))
(= (gc-motivation-sweep-latest (Sweep $rest $latest)) $latest)
(= (gc-motivation-sweep-to (Sweep $rest $latest) $at)
   (if (== $rest ())
       (Sweep () $latest)
       (gc-motivation-sweep-by (car-atom $rest) $rest $latest $at)))
(= (gc-motivation-sweep-by $next $rest $latest $at)
   (if (<= (gc-motivation-obs-at $next) $at)
       (gc-motivation-sweep-to (Sweep (cdr-atom $rest) (gc-motivation-with-latest $latest $next)) $at)
       (Sweep $rest $latest)))
(= (gc-motivation-with-latest None $o) (Latest (gc-motivation-obs-at $o) ($o)))
(= (gc-motivation-with-latest (Latest $at $members) $o)
   (if (== $at (gc-motivation-obs-at $o))
       (Latest $at (cons-atom $o $members))
       (Latest (gc-motivation-obs-at $o) ($o))))

; Each based slot with the counted observations its attempt produced, as (Made BASED (OBS ...)),
; joined by attempt id: slots and products sorted into one list by (Key ID 0 ...) and
; (Key ATTEMPT 1 AT OBS-ID ...), so a slot comes just before its own products and one fold attaches
; them; a product naming no applied attempt follows no slot of its id and is dropped. The joined
; slots are then put back in the order of their instants and ids.
(= (gc-motivation-with-products $based $counted)
   (gc-motivation-in-slot-order
     (gc-motivation-joined
       (foldl-atom
         (sort-atom (union-atom (map-atom $based $b (gc-motivation-slot-key $b))
                                (gc-motivation-concat (map-atom $counted $o (gc-motivation-product-key (gc-motivation-obs-producer $o) $o)))))
         (Join None () ()) $acc $entry (gc-motivation-join-step $acc $entry)))))
(= (gc-motivation-slot-key (Based (Slot $at $id $action $simultaneous $end) $latest))
   (Key $id 0 (Based (Slot $at $id $action $simultaneous $end) $latest)))
(= (gc-motivation-product-key Unstated $o) ())
(= (gc-motivation-product-key (ProducedBy $attempt) $o)
   ((Key $attempt 1 (gc-motivation-obs-at $o) (gc-motivation-obs-id $o) $o)))
(= (gc-motivation-join-step (Join $current $made $out) (Key $id 0 $based))
   (Join $based () (gc-motivation-emit $current $made $out)))
(= (gc-motivation-join-step (Join $current $made $out) (Key $attempt 1 $at $oid $o))
   (if (gc-motivation-current-is $current $attempt)
       (Join $current (cons-atom $o $made) $out)
       (Join $current $made $out)))
(= (gc-motivation-current-is None $attempt) False)
(= (gc-motivation-current-is (Based (Slot $at $id $action $simultaneous $end) $latest) $attempt) (== $id $attempt))
(= (gc-motivation-emit None $made $out) $out)
(= (gc-motivation-emit (Based $slot $latest) $made $out) (cons-atom (Made (Based $slot $latest) $made) $out))
(= (gc-motivation-joined (Join $current $made $out)) (gc-motivation-emit $current $made $out))
(= (gc-motivation-in-slot-order $made)
   (map-atom (sort-atom (map-atom $made $x (gc-motivation-made-key $x))) $k (gc-motivation-keyed $k)))
(= (gc-motivation-made-key (Made (Based (Slot $at $id $action $simultaneous $end) $latest) $products))
   (Keyed $at $id (Made (Based (Slot $at $id $action $simultaneous $end) $latest) $products)))

; One slot's samples or reasons, a need at a time in the needs' order, for each need it produced
; an observation of.
(= (gc-motivation-slot-samples (Made (Based (Slot $at $id $action $simultaneous $end) $latests) $products) $needs)
   (gc-motivation-concat (map-atom (gc-motivation-pairs $needs $latests) $pair
     (gc-motivation-need-sample $pair $at $id $action $simultaneous $end $products))))
(= (gc-motivation-pairs $needs $latests)
   (if (== $needs ())
       ()
       (cons-atom (With (car-atom $needs) (car-atom $latests)) (gc-motivation-pairs (cdr-atom $needs) (cdr-atom $latests)))))
(= (gc-motivation-need-sample (With $need $latest) $at $id $action $simultaneous $end $products)
   (gc-motivation-need-sample-of $need $latest $at $id $action $simultaneous $end (gc-motivation-of-need $products $need)))
(= (gc-motivation-need-sample-of $need $latest $at $id $action $simultaneous $end $mine)
   (if (== $mine ())
       ()
       ((gc-motivation-sample $need $id $action $at $simultaneous $end $mine $latest))))

(= (gc-motivation-sample $need $id $action $at True $end $products $latest)
   (gc-motivation-not-sampled $id $need "simultaneous-attempt"))
(= (gc-motivation-sample $need $id $action $at False $end $products $latest)
   (gc-motivation-sample-in $need $id $action $at
     (filter-atom $products $o (and (> (gc-motivation-obs-at $o) $at) (<= (gc-motivation-obs-at $o) $end)))
     $latest))
(= (gc-motivation-sample-in $need $id $action $at $outcomes $latest)
   (if (== $outcomes ())
       (gc-motivation-not-sampled $id $need "outside-window")
       (gc-motivation-sample-outcome $need $id $action $at (gc-motivation-latest $outcomes) $latest)))
(= (gc-motivation-sample-outcome $need $id $action $at $outcome $latest)
   (if (> (size-atom (gc-motivation-values $outcome)) 1)
       (gc-motivation-not-sampled $id $need "conflicted-outcome")
       (if (not (gc-motivation-establishes $outcome))
           (gc-motivation-not-sampled $id $need "outcome-not-establishing")
           (gc-motivation-sample-baseline $need $id $action $at $outcome $latest))))
; The baseline is the need's observations at the latest instant at or before the application that
; are still valid then, so an expired latest pre-state is never replaced by an older one.
(= (gc-motivation-sample-baseline $need $id $action $at $after None)
   (gc-motivation-not-sampled $id $need "no-baseline"))
(= (gc-motivation-sample-baseline $need $id $action $at $after (Latest $bat $members))
   (gc-motivation-sample-valid $need $id $action $at $after
     (filter-atom $members $o (gc-motivation-valid-at $at (gc-motivation-obs-until $o)))))
(= (gc-motivation-sample-valid $need $id $action $at $after $before)
   (if (== $before ())
       (gc-motivation-not-sampled $id $need "baseline-expired")
       (gc-motivation-sample-before $need $id $action $at $after $before)))
(= (gc-motivation-sample-before $need $id $action $at $after $before)
   (if (> (size-atom (gc-motivation-values $before)) 1)
       (gc-motivation-not-sampled $id $need "conflicted-baseline")
       (if (not (gc-motivation-establishes $before))
           (gc-motivation-not-sampled $id $need "baseline-not-establishing")
           (Raw $id $action (gc-motivation-need-id $need) $at
                (gc-motivation-ids $before) (gc-motivation-ids $after)
                (- (gc-motivation-obs-level (car-atom $after)) (gc-motivation-obs-level (car-atom $before)))))))
(= (gc-motivation-not-sampled $id $need $reason) (NotSampled $id (gc-motivation-need-id $need) $reason))

(= (gc-motivation-raw? (Raw $attempt $action $need $at $before $after $change)) True)
(= (gc-motivation-raw? (NotSampled $attempt $need $reason)) False)

; ---- expected changes (c-v2m-sample-mean-convex-1019) ----------------------------------------------------
; The running mean is eq. 8's convex blend with alpha_k = 1/k, so it stays within the range of its
; samples whatever their order; the declared change is the prior the first residual is measured
; against and nothing more.

; The raw samples grouped by action and need, as (Pair ACTION NEED (RAW ...)) with each group's
; samples in the order applied: one sort of (ByPair ACTION NEED AT ID RAW), folded latest first so
; that consing leaves every group earliest first.
(= (gc-motivation-raw-groups $raw)
   (foldl-atom (gc-relevance-reversed (sort-atom (map-atom $raw $r (gc-motivation-raw-key $r)))) () $acc $entry
     (gc-motivation-raw-group-step $acc $entry)))
(= (gc-motivation-raw-key (Raw $attempt $action $need $at $before $after $change))
   (ByPair $action $need $at $attempt (Raw $attempt $action $need $at $before $after $change)))
(= (gc-motivation-raw-group-step $groups (ByPair $action $need $at $attempt $raw))
   (if (== $groups ())
       ((Pair $action $need ($raw)))
       (gc-motivation-raw-group-onto (car-atom $groups) (cdr-atom $groups) $action $need $raw)))
(= (gc-motivation-raw-group-onto (Pair $a $n $members) $rest $action $need $raw)
   (if (and (== $a $action) (== $n $need))
       (cons-atom (Pair $a $n (cons-atom $raw $members)) $rest)
       (cons-atom (Pair $action $need ($raw)) (cons-atom (Pair $a $n $members) $rest))))
(= (gc-motivation-group-is (Pair $a $n $members) $action $need) (and (== $a $action) (== $n $need)))
(= (gc-motivation-members-of None) ())
(= (gc-motivation-members-of (Some (Pair $a $n $members))) $members)

; The samples folded into the running mean, consed and reversed once, so a group of s samples
; costs s steps.
(= (gc-motivation-learn $prior $samples)
   (gc-motivation-learned-in-order (foldl-atom $samples (Acc $prior 0 ()) $acc $s (gc-motivation-learn-step $acc $s))))
(= (gc-motivation-learned-in-order (Acc $mean $count $done)) (Acc $mean $count (gc-relevance-reversed $done)))
(= (gc-motivation-learn-step (Acc $mean $count $done) (Raw $attempt $action $need $at $before $after $change))
   (Acc (gc-motivation-next-mean $mean $count $change) (+ $count 1)
        (cons-atom (Sample $attempt $action $need $before $after $change
                           (gc-motivation-known-or-none $mean) (gc-motivation-residual $mean $change))
                   $done)))
(= (gc-motivation-next-mean Unknown $count $x) (Known $x))
; m + (x - m)/(k + 1) written as the convex combination it is, k/(k + 1) m + x/(k + 1), whose terms
; never exceed the scale's width, so no intermediate overflows; a declared prior (count 0) is
; replaced by the first sample exactly.
(= (gc-motivation-next-mean (Known $m) $count $x)
   (Known (+ (* $m (/ $count (+ $count 1.0))) (/ $x (+ $count 1.0)))))
(= (gc-motivation-residual Unknown $x) None)
(= (gc-motivation-residual (Known $m) $x) (- $x $m))
(= (gc-motivation-known-or-none Unknown) None)
(= (gc-motivation-known-or-none (Known $v)) $v)

(= (gc-motivation-declared-of $declared $action $need)
   (gc-relevance-first (filter-atom $declared $e (and (== (gc-motivation-expected-action $e) $action)
                                                       (== (gc-motivation-expected-need $e) (gc-motivation-need-id $need))))))
(= (gc-motivation-prior None) Unknown)
(= (gc-motivation-prior (Some $expectation)) (Known (gc-motivation-expected-change $expectation)))

; One action's change of one need: its group's samples, in the order applied, learned from its prior.
(= (gc-motivation-learned $declared $groups $action $need)
   (gc-motivation-learned-of (gc-motivation-declared-of $declared $action $need)
     (gc-motivation-members-of (gc-relevance-first (filter-atom $groups $g (gc-motivation-group-is $g $action (gc-motivation-need-id $need)))))
     $action $need))
(= (gc-motivation-learned-of $declared $ordered $action $need)
   (gc-motivation-change $action $need $declared (gc-motivation-learn (gc-motivation-prior $declared) $ordered)))
(= (gc-motivation-change $action $need $declared (Acc $mean $count $samples))
   (Learned (gc-motivation-change-record $action (gc-motivation-need-id $need) $declared $mean $count $samples) $samples))
(= (gc-motivation-change-record $action $need $declared $mean $count $samples)
   (if (> $count 0)
       (Change $action $need "measured" (gc-motivation-known-or-none $mean) $count "receipt-calibrated" (Samples (gc-motivation-keys $samples)))
       (gc-motivation-declared-record $action $need $declared)))
(= (gc-motivation-declared-record $action $need None) (Change $action $need "unknown" None 0 None (Samples ())))
(= (gc-motivation-declared-record $action $need (Some $e))
   (Change $action $need "declared" (gc-motivation-expected-change $e) 0 (gc-motivation-expected-class $e) (Samples ())))
(= (gc-motivation-keys $samples) (map-atom $samples $s (gc-motivation-key $s)))
(= (gc-motivation-key (Sample $attempt $action $need $before $after $change $prior $residual)) (Key $attempt $before $after))
(= (gc-motivation-learned-change (Learned $change $samples)) $change)
(= (gc-motivation-learned-samples (Learned $change $samples)) $samples)

(= (gc-motivation-change-state (Change $action $need $state $mean $count $class $samples)) $state)
(= (gc-motivation-change-mean (Change $action $need $state $mean $count $class $samples)) $mean)
(= (gc-motivation-known-change $change)
   (if (== (gc-motivation-change-state $change) "unknown") Unknown (Known (gc-motivation-change-mean $change))))

; ---- reductions (c-v2m-breakpoints-1019, c-v2m-whole-range-cases-1019) ---------------------------------
; One clause per case of a known or unknown level and change; none overlaps. Every end is a move
; between two places, so it lies in [-1, 1] and has exactly the sign of the real model's value on the
; binary64 inputs, a learned change being the double the snapshot reports, 0.0 exactly where that
; value is 0 and possibly where it is below 2^-1022; its magnitude is a floating-point evaluation,
; which can miss the real one on the same side of 0. The real theorems (the parent's
; proofs/Motivation.lean and MotivationIntervals.lean) say the candidate set holds the real extremes,
; and nothing here certifies an enclosure (a-v2m-exact-candidates-1019, c-v2li-input-conversion-1020,
; a-v2r-exact-sign-1020).

(= (gc-motivation-interval $need (Known $level) (Known $change))
   (gc-motivation-point (gc-motivation-moved-by $need $level $change)))
; A known level with an unknown change can reach any level of the scale: at worst the far end, whose
; urgency is the top, at best a level in the band, whose urgency is 0.
(= (gc-motivation-interval $need (Known $level) Unknown)
   (Interval (gc-motivation-moved $need (At $level 0.0) (gc-motivation-worst $need))
             (gc-motivation-moved $need (At $level 0.0) (At (gc-motivation-need-low $need) 0.0))))
(= (gc-motivation-interval $need Unknown (Known $change))
   (gc-motivation-over (gc-motivation-candidate-reductions $need $change)))
(= (gc-motivation-interval $need Unknown Unknown)
   (Interval (- 0.0 (gc-motivation-top $need)) (gc-motivation-top $need)))
(= (gc-motivation-point $value) (Interval $value $value))
(= (gc-motivation-over $values) (Interval (min-atom $values) (max-atom $values)))
; The reductions at the candidate levels, at which a term of the reduction changes regime: each end
; b of {LO, LOW, HIGH, HI}, and each shifted level b - d the exact side tests put on the scale,
; whose target is b itself (the candidate whose target fl(fl(b - d) + d) landed one ulp outside a
; band edge, i-v2li-float-round-trip-1020). The real reduction is continuous and monotone between
; consecutive candidates, so its real extremes over the scale are among them, and since every
; candidate's value has its real sign, so do the least and the greatest (c-v2m-breakpoints-1019,
; c-v2m-candidate-differences-1019). Time: at most eight moves.
(= (gc-motivation-candidate-reductions $need $change)
   (union-atom
     (map-atom (gc-motivation-ends $need) $b (gc-motivation-moved-by $need $b $change))
     (map-atom (filter-atom (gc-motivation-ends $need) $c (gc-motivation-on-scale? $need (At $c (- 0.0 $change)))) $e
       (gc-motivation-moved $need (At $e (- 0.0 $change)) (At $e 0.0)))))
(= (gc-motivation-ends $need)
   (cdr-atom (Ends (gc-motivation-need-lo $need) (gc-motivation-need-low $need)
                   (gc-motivation-need-high $need) (gc-motivation-need-hi $need))))

(= (gc-motivation-reduction $levels $changes $need $action)
   (gc-motivation-reduction-of $need $action (gc-motivation-known-level (gc-motivation-level-of $levels $need))
     (gc-motivation-known-change (gc-motivation-change-of $changes $action $need))))
; am[implements a-v2r-predicted-level-1020]
(= (gc-motivation-reduction-of $need $action $level $change)
   (Reduction $action (gc-motivation-need-id $need) (gc-motivation-interval $need $level $change)
              (gc-motivation-predicted $need $level $change)))
; The level the change is predicted to leave, the clamped target: a point for a known level and
; change; for an unknown level the targets of LO and HI, which bound every level's, since the
; clamped target never falls as the level rises; for an unknown change the whole scale. A place on
; the scale is finite, and rounding it to nearest keeps it on the scale.
; am[implements a-v2r-predicted-level-1020]
(= (gc-motivation-predicted $need (Known $level) (Known $change))
   (gc-motivation-point (gc-motivation-place-value (gc-motivation-clamped $need (At $level $change)))))
(= (gc-motivation-predicted $need Unknown (Known $change))
   (Interval (gc-motivation-place-value (gc-motivation-clamped $need (At (gc-motivation-need-lo $need) $change)))
             (gc-motivation-place-value (gc-motivation-clamped $need (At (gc-motivation-need-hi $need) $change)))))
(= (gc-motivation-predicted $need $level Unknown)
   (Interval (gc-motivation-need-lo $need) (gc-motivation-need-hi $need)))
(= (gc-motivation-place-value (At $base $offset)) (+ $base $offset))
(= (gc-motivation-change-action (Change $action $need $state $mean $count $class $samples)) $action)
(= (gc-motivation-change-need (Change $action $need $state $mean $count $class $samples)) $need)
(= (gc-motivation-change-of $changes $action $need)
   (car-atom (filter-atom $changes $c (and (== (gc-motivation-change-action $c) $action)
                                            (== (gc-motivation-change-need $c) (gc-motivation-need-id $need))))))

; ---- the entry ---------------------------------------------------------------------------------------
; Time: for m attempts, n observations, p needs, q actions, e declared changes and r samples:
; n log n to put the observations in time order and n * p to check them against the needs, p * n
; for the levels, m log m to order the applied attempts and m for their groups and windows,
; p * (m + n) for the baseline sweep, (m + n) log (m + n) for the join of attempts and their
; products and m log m to restore time order, p * n for each slot's products of each need, r log r
; to group the samples, then for each of the q * p action and need pairs a scan of the at most
; q * p groups and the e declared changes, and for its reduction a scan of the p levels and the
; q * p changes and at most eight breakpoints: (m + n) log (m + n) + p * (m + n) +
; q * p * (q * p + e) comparisons in all. Reading the stream's history to hand it here is linear
; in its length too, so a review of a longer stream still costs more, by n log n and not n^2. It
; runs under the caller's RunBudget, whose inference bound stops a stream too long for it.

; am[implements a-v2m-levels-1019@387e68] am[implements a-v2m-expectations-1019@b13468]
; am[implements a-v2m-snapshot-sweep-1020@fefbd6]
(: gc-motivation-snapshot (-> Atom Expression))
(= (gc-motivation-snapshot $input) (gc-motivation-snapshot-of $input))
(= (gc-motivation-snapshot-of $input)
   (let* (($t (gc-motivation-as-of $input))
          ($needs (gc-motivation-needs $input))
          ($past (gc-motivation-in-time-order (gc-motivation-by-at-most (gc-motivation-observations $input) $t)))
          ($counted (filter-atom $past $o (gc-motivation-counts $needs $o)))
          ($excluded (gc-motivation-concat (map-atom $past $p (gc-motivation-excluded $needs $p))))
          ($levels (map-atom $needs $n (gc-motivation-level $t $n $counted)))
          ($slots (gc-motivation-slots $t (gc-motivation-instant-groups (gc-motivation-applied-at $t (gc-motivation-attempts $input)))))
          ($made (gc-motivation-with-products (gc-motivation-based $slots $needs $counted) $counted))
          ($sampled (gc-motivation-concat (map-atom $made $x (gc-motivation-slot-samples $x $needs))))
          ($raw (filter-atom $sampled $r (gc-motivation-raw? $r)))
          ($unsampled (filter-atom $sampled $u (not (gc-motivation-raw? $u))))
          ($groups (gc-motivation-raw-groups $raw))
          ($learned (gc-motivation-concat (map-atom (gc-motivation-actions $input) $a
                       (map-atom $needs $m (gc-motivation-learned (gc-motivation-declared $input) $groups $a $m)))))
          ($changes (map-atom $learned $l (gc-motivation-learned-change $l)))
          ($reductions (gc-motivation-concat (map-atom (gc-motivation-actions $input) $b
                          (map-atom $needs $k (gc-motivation-reduction $levels $changes $k $b))))))
     (Snapshot (Levels $levels)
               (Changes $changes)
               (Reductions $reductions)
               (Samples (gc-motivation-concat (map-atom $learned $s (gc-motivation-learned-samples $s))))
               (NotSampled $unsampled)
               (Excluded $excluded))))

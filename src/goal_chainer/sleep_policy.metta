; Purpose: own reviewed reranker holdout, statistical risk and promotion admission policy.
; am[implements a-sleep-policy-1016@0dbdf0] am[rests-on c-sleep-numerical-contract-1016@79a33a]

; Explicit conservative policy: a fifth of source hashes is reserved for evaluation.
(= (gc-sleep-partition $fraction) (if (< $fraction 0.2) "holdout" "train"))
; The telescoping spending sequence sums to 0.05 across all reserved attempts.
(= (gc-sleep-alpha $attempt) (/ 0.05 (* $attempt (+ $attempt 1))))
(= (gc-sleep-admit $groups $lower $rank $brier $retained-rank $retained-brier $changed)
   (if (not $changed) "unchanged-weights"
     (if (== $groups 0) "insufficient-fresh-holdout"
       (if (or (< $rank 0.0) (< $retained-rank 0.0)) "ranking-regression"
         (if (or (< $brier 0.0) (< $retained-brier 0.0)) "brier-regression"
           (if (> $lower 0.0) "admit" "uncertain-improvement"))))))

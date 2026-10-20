;;; Purpose: conserve query-local attention while transferring it over a closed incidence graph.

;; Internal rows are sorted by unique key, closed under neighbor references, and carry finite
;; nonnegative balances. These are the internal transition's input preconditions.
;; Each source keeps its untransferred balance and divides the rest among distinct neighbors.
;; Self edges retain attention. An isolated node emits only its own credit.
;; Time: V+E credits, V rows and E directed incidences. Space: V+E credits.
;; am[implements a-integrate-ecan-conserved-cycle-code-1017]
;; am[rests-on c-integrate-sparse-cycle-conserves-real-1017]
;; am[rests-on c-integrate-query-attention-domain-1017]
(= (gc-attention-credits $rows $fraction $minimum)
 (collapse
  (let (Row $key $value $neighbors) (superpose $rows)
   (let* (($targets (filter-atom $neighbors $target (not (== $key $target))))
          ($degree (size-atom $targets))
          ($out (if (== $targets ()) 0.0 (* $fraction (- $value $minimum)))))
    (superpose (
     (Credit $key (- $value $out))
     (let $target (superpose $targets)
      (Credit $target (/ $out $degree)))))))))

;; Destination-sorted credits make each group contiguous, including zero-balance destinations.
;; Time: V+E additions and list cells after sorting.
;; am[implements a-integrate-ecan-conserved-cycle-code-1017]
(= (gc-attention-fold $credits $key $value $reversed)
 (if (== $credits ())
  (foldl-atom (cons-atom (Balance $key $value) $reversed) () $out $row (cons-atom $row $out))
  (let* ((($head $tail) (decons-atom $credits))
         ((Credit $next $amount) $head))
   (if (== $next $key)
    (gc-attention-fold $tail $key (+ $value $amount) $reversed)
    (gc-attention-fold $tail $next $amount (cons-atom (Balance $key $value) $reversed))))))

;; Every node credits itself, so balance keys and graph keys agree by construction.
;; Time: V outputs. Space: V rows sharing their unchanged adjacency values.
;; am[implements a-integrate-ecan-conserved-cycle-code-1017]
(= (gc-attention-zip $rows $balances)
 (if (== $rows ()) ()
  (let* ((($row $tail) (decons-atom $rows))
         ((Row $key $old $neighbors) $row)
         (($balance $rest) (decons-atom $balances))
         ((Balance $key $value) $balance))
   (cons-atom (Row $key $value $neighbors) (gc-attention-zip $tail $rest)))))

;; All transfers read the same frozen vector. For fraction in [0,1], the minimum stays local.
;; An equal vector is fixed; an empty vector stays empty. No global state is read or written.
;; Real arithmetic preserves total attention; floating summation has ordinary roundoff, not clips.
;; Time: O((V+E) log(V+E)) comparisons plus O(V+E) additions. Space: O(V+E).
;; am[implements a-integrate-ecan-conserved-cycle-code-1017]
;; am[rests-on c-integrate-sparse-cycle-conserves-real-1017]
(= (gc-attention-cycle $rows $fraction)
 (if (== $rows ()) ()
  (let* (($minimum (min-atom (collapse (let (Row $key $value $neighbors) (superpose $rows) $value))))
         ($credits (msort (gc-attention-credits $rows $fraction $minimum)))
         (($first $tail) (decons-atom $credits))
         ((Credit $key $value) $first)
         ($balances (gc-attention-fold $tail $key $value ())))
   (gc-attention-zip $rows $balances))))

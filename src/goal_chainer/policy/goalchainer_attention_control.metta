;;; Purpose: order a query's inference frontier by conserved attention while retaining native rules.

;; The context flag is a speculative fact, never persistent world configuration.
;; am[implements a-integrate-ecan-packaged-hook-1017]
(= (gc-attention-active?)
 (not (== () (collapse (once (match &self (gc-attention-active) True))))))

;; A function call scopes the match variables independently for each premise lookup.
;; am[implements a-integrate-ecan-packaged-hook-1017]
;; am[addresses i-integrate-attention-premise-match-coupling-1017]
(= (gc-attention-balance $sid)
 (match &self (gc-attention-row (AttentionStatement $sid) $balance $links) $balance))

;; Both premise nodes exist before attention admission: initial graph build or the touch hook.
;; Mean premise balance is an empirical scheduling hypothesis, not a truth or utility estimate.
;; am[implements a-integrate-ecan-packaged-hook-1017]
;; am[rests-on c-integrate-compiled-controls-four-edge-1017]
(= (gc-attention-importance (Fr $value $tick $left $right))
 (/ (+ (gc-attention-balance $left) (gc-attention-balance $right)) 2.0))

;; Numeric ties retain the native key supplied by the caller: raw at insert, decayed at pop.
;; Time: four indexed row reads and at most three numeric comparisons.
;; am[implements a-integrate-ecan-packaged-hook-1017]
;; am[rests-on c-integrate-attention-arithmetic-tie-confirmed-1017]
(= (gc-attention-before $first $first-key $second $second-key)
 (if (gc-attention-active?)
  (let* (($a (gc-attention-importance $first)) ($b (gc-attention-importance $second)))
   (if (> $a $b) True
    (if (> $b $a) False
     (gc-attention-native-before $first $first-key $second $second-key))))
  (gc-attention-native-before $first $first-key $second $second-key)))

;; Stable merging takes the left occurrence on a tie, preserving duplicate jobs.
;; Time: at most m+n-1 comparisons and m+n list cells for two runs of lengths m,n.
;; am[implements a-integrate-ecan-packaged-hook-1017]
;; am[rests-on c-integrate-stable-comparator-merge-source-1017]
(= (gc-attention-merge $left $right)
 (if (== $left ()) $right
  (if (== $right ()) $left
   (let* ((($a $as) (decons-atom $left)) (($b $bs) (decons-atom $right))
          ((Fr $av $at $ax $ay) $a) ((Fr $bv $bt $bx $by) $b))
    (if (sn fr-before $b $bv $a $av)
     (cons-atom $b (gc-attention-merge $left $bs))
     (cons-atom $a (gc-attention-merge $as $right)))))))

;; Time: one pass over runs; every contained occurrence is merged at most once.
;; am[implements a-integrate-ecan-packaged-hook-1017]
(= (gc-attention-merge-pairs $runs)
 (if (== $runs ()) ()
  (let ($first $rest) (decons-atom $runs)
   (if (== $rest ()) $runs
    (let ($second $tail) (decons-atom $rest)
     (cons-atom (gc-attention-merge $first $second) (gc-attention-merge-pairs $tail)))))))

;; Each pass halves the number of runs, rounding up.
;; am[implements a-integrate-ecan-packaged-hook-1017]
(= (gc-attention-merge-all $runs)
 (if (== $runs ()) ()
  (let ($first $rest) (decons-atom $runs)
   (if (== $rest ()) $first
    (gc-attention-merge-all (gc-attention-merge-pairs $runs))))))

;; A strict inversion ends a run; ties remain together in their encounter order.
;; Time: one comparison per consumed occurrence and one reversal per run.
;; am[implements a-integrate-ecan-packaged-hook-1017]
(= (gc-attention-run $items $previous $reversed)
 (if (== $items ())
  (Run (foldl-atom $reversed () $out $item (cons-atom $item $out)) ())
  (let* ((($next $tail) (decons-atom $items))
         ((Fr $nv $nt $nx $ny) $next) ((Fr $pv $pt $px $py) $previous))
   (if (sn fr-before $next $nv $previous $pv)
    (Run (foldl-atom $reversed () $out $item (cons-atom $item $out)) $items)
    (gc-attention-run $tail $next (cons-atom $next $reversed))))))

;; Runs partition all queue occurrences without creating, removing or reticking any job.
;; am[implements a-integrate-ecan-packaged-hook-1017]
(= (gc-attention-runs $items)
 (if (== $items ()) ()
  (let* ((($first $rest) (decons-atom $items))
         ((Run $run $tail) (gc-attention-run $rest $first ($first))))
   (cons-atom $run (gc-attention-runs $tail)))))

;; Time: O(n + n log r) comparisons for n occurrences in r existing ordered runs.
;; am[implements a-integrate-ecan-packaged-hook-1017]
(= (gc-attention-rekey $items)
 (gc-attention-merge-all (gc-attention-runs $items)))

;; Preserve the measured incident allocation during integration; it is not fitted to the query.
;; am[related n-integrate-ecan-hook-fraction-1017]
(= (gc-attention-fraction) 0.38)

;; All transfers are computed before publishing any balance. Graph adjacency is unchanged.
;; Time: the pure cycle's O((V+E) log(V+E)) work plus V row writes.
;; am[implements a-integrate-ecan-packaged-hook-1017]
(= (gc-attention-diffuse!)
 (let* (($rows (gc-attention-rows))
        ($next (gc-attention-cycle $rows (gc-attention-fraction)))
        ($written (collapse
         (let (Row $node $value $neighbors) (superpose $next)
          (gc-attention-set-balance! $node $value)))))
  True))

;; Publish new incidence and current ordering before the native body admits any new pairs.
;; The saved body contains every native partner alternative, including supported conditional ends.
;; Time: incremental graph insertion plus one cycle and rekey only for a newly indexed statement.
;; am[implements a-integrate-ecan-packaged-hook-1017]
;; am[rests-on c-integrate-hg-touch-one-equation-1017]
(= (gc-attention-touch! $sid)
 (let $updated
  (if (gc-attention-active?)
   (if (gc-attention-add-statement! $sid)
    (let* (($diffused (gc-attention-diffuse!))
           ($ordered (gc-attention-rekey (sn frontier)))
           ($published (sn_cell_put sn-frontier $ordered))) True)
    False)
   False)
  (gc-attention-native-touch! $sid)))

;; Save the complete native body once. Rehydration sees the saved equation and skips the move.
;; am[implements a-integrate-ecan-packaged-hook-1017]
;; am[rests-on c-rt-rebind-lifecycle-guarded-1017]
!(if (== () (collapse (once (match &self (= (gc-attention-native-before $a $av $b $bv) $body) True))))
 (collapse (match &self (= (sn fr-before $a $av $b $bv) $body)
   (let* (($removed (remove-atom &self (= (sn fr-before $a $av $b $bv) $body)))
          ($saved (add-atom &self (= (gc-attention-native-before $a $av $b $bv) $body)))) True)))
 True)

;; am[implements a-integrate-ecan-packaged-hook-1017]
;; am[rests-on c-rt-rebind-lifecycle-guarded-1017]
!(if (== () (collapse (once (match &self (= (sn fr-before $a $av $b $bv) (gc-attention-before $a $av $b $bv)) True))))
 (add-atom &self (= (sn fr-before $a $av $b $bv) (gc-attention-before $a $av $b $bv)))
 True)

;; am[implements a-integrate-ecan-packaged-hook-1017]
;; am[rests-on c-rt-rebind-lifecycle-guarded-1017]
!(if (== () (collapse (once (match &self (= (gc-attention-native-touch! $sid) $body) True))))
 (collapse (match &self (= (sn fr-touch! $sid) $body)
   (let* (($removed (remove-atom &self (= (sn fr-touch! $sid) $body)))
          ($saved (add-atom &self (= (gc-attention-native-touch! $sid) $body)))) True)))
 True)

;; am[implements a-integrate-ecan-packaged-hook-1017]
;; am[rests-on c-rt-rebind-lifecycle-guarded-1017]
!(if (== () (collapse (once (match &self (= (sn fr-touch! $sid) (gc-attention-touch! $sid)) True))))
 (add-atom &self (= (sn fr-touch! $sid) (gc-attention-touch! $sid)))
 True)

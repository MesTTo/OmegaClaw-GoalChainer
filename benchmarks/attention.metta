;;; Purpose: vary frontier scheduling in an isolated benchmark world while reusing native queries.

;; One experiment row supplies exactly one mode and seed inside speculation.
;; am[implements a-integrate-cairn-harness-1018@4ba2ae]
(= (gc-benchmark-mode) (match &self (gc-benchmark $mode $seed) $mode))

;; A pair has a stable seeded priority, so comparisons define a consistent order.
;; Time: linear in the printed premise identifiers per comparison.
;; am[implements a-integrate-cairn-harness-1018@4ba2ae]
(= (gc-benchmark-key (Fr $v $tick $left $right))
 (match &self (gc-benchmark $mode $seed)
  ((py-atom benchmarks.attention.random_priority) $seed $left $right)))

;; Only ordering changes; every native supported-premise and capacity check remains in place.
;; am[implements a-integrate-cairn-harness-1018@4ba2ae]
(= (gc-benchmark-before $a $av $b $bv)
 (case (gc-benchmark-mode)
  ((random (> (gc-benchmark-key $a) (gc-benchmark-key $b)))
   (native (gc-attention-native-before $a $av $b $bv))
   (ecan (gc-attention-before $a $av $b $bv)))))

;; Graph maintenance is charged only to the arm that performs it.
;; am[implements a-integrate-cairn-harness-1018@4ba2ae]
(= (gc-benchmark-touch! $sid)
 (if (== (gc-benchmark-mode) ecan)
  (gc-attention-touch! $sid)
  (gc-attention-native-touch! $sid)))

;; The production record and search termination are shared by all three arms.
;; am[implements a-integrate-cairn-harness-1018@4ba2ae]
(= (gc-benchmark-start! $statement $sid)
 (if (== (gc-benchmark-mode) ecan)
  (gc-benchmark-attention-start! $statement $sid)
  (gc-attention-search! $statement $sid 0)))

;; Install once into the benchmark's own space, never a production world.
;; am[implements a-integrate-cairn-harness-1018@4ba2ae]
!(collapse (match &self (= (sn fr-before $a $av $b $bv) $body)
 (remove-atom &self (= (sn fr-before $a $av $b $bv) $body))))
!(add-atom &self (= (sn fr-before $a $av $b $bv) (gc-benchmark-before $a $av $b $bv)))
!(collapse (match &self (= (sn fr-touch! $sid) $body)
 (remove-atom &self (= (sn fr-touch! $sid) $body))))
!(add-atom &self (= (sn fr-touch! $sid) (gc-benchmark-touch! $sid)))
!(collapse (match &self (= (gc-attention-start! $statement $sid) $body)
 (let* (($removed (remove-atom &self (= (gc-attention-start! $statement $sid) $body)))
        ($saved (add-atom &self (= (gc-benchmark-attention-start! $statement $sid) $body)))) True)))
!(add-atom &self (= (gc-attention-start! $statement $sid) (gc-benchmark-start! $statement $sid)))

;; Compare receipt identities and trust before and after search, within the same snapshot.
;; am[implements a-integrate-cairn-harness-1018@4ba2ae]
(= (gc-benchmark-evidence)
 (msort (collapse (match &self (sn receipt $sid $source $hash)
  (Receipt $sid $source $hash (sn_tr_rs src $source))))))

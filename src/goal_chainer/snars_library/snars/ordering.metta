;;; SNARS module — the ordering domain (Mapping 1.9; rule pack R3).
;;; Import via the snars.metta aggregator; load order lives there.
;;; An ordering relation (taller, older, more-X) is NOT similarity: it is
;;; irreflexive, antisymmetric, and TRANSITIVE in its own reasoning regime.
;;; Transitivity is the domain's structural rule, never deduction-through-
;;; taxonomy (R0 already walls instance vs ordering apart). Degree direction
;;; normalizes to ONE polarity upstream (the "more-X" canonical form); the
;;; parser-fed have-degree-NN routing is the sense session's seam to feed.

(= (sn ord-rules?) (== 1 (sn cfg ord-rules 1)))

;; ordering transitivity: (more-A x y) + (more-A y z) |- (more-A x z).
;; STRUCTURAL_TRUTH (3.7: a structural rule's conclusion is discounted by
;; b_struct, never asserted at full strength): one bounded quantum, weight
;; w = b1 * b2 * b_struct, frequency f = 1 (orderings don't flip sign under
;; chaining). Both premises must share the copula, the middle term, AND the
;; ordering domain -- the R0 guard re-stated structurally so an instance or
;; similarity statement can never sneak across.
(= (|- (stmt $s1 (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $y)))))
       (stmt $s2 (sh (tag P d so $amr2) $cop (args ((arg s $y) (arg o $z))))))
   (if (and (sn ord-rules?)
            (and (sn licensed-kind? ordering $amr $cop)
                 (and (not (== $x $z))
                      (and (sn disjoint $s1 $s2)
                           (and (== ordering (sn dom-of $s1)) (== ordering (sn dom-of $s2)))))))
       (let* (((Opinion $b1 $d1 $u1 $a1) (sn opinion $s1))
              ((Opinion $b2 $d2 $u2 $a2) (sn opinion $s2))
              ($w (* (* $b1 $b2) (sn config structural-b)))
              ($tree (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $z))))))
         (stmt (sn weak-quantum-d! $tree (ord $s1 $s2) $w 1.0 0.5 ordering $s1 $s2) $tree))
       (empty)))

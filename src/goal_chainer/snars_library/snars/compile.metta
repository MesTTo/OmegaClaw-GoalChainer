;;; SNARS module — stamp-aware clause compilation of rule packs (Wave K4).
;;; Import via the snars.metta aggregator; load AFTER rulekit (it
;;; compiles the registry rows) and sbc (it reuses rw-fire!/disjoint).
;;;
;;; The registry driver (rulekit |-) SCANS every (sn rw ...) row per statement
;;; pair -- all rows share the `rw` first-arg bucket, so Prolog can't index them
;;; apart (the R5 "indexed partner lookup is future" note). K4 COMPILES each
;;; deductive row into a dispatch clause keyed on the conclusion COPULA:
;;;   (= (sn cgoal <cop> <concl>) <find premises, guard, fire>)
;;; so a goal-directed call (sn cgoal "keeps" <goal>) compiles to
;;; sn(cgoal, "keeps", Concl, R) -- SWI JIT multi-argument indexing discriminates
;;; on the copula constant, no scan. PeTTa probe (2026-06-13): runtime-added
;;; clauses under sn/N dispatch DIRECTLY (no reduce needed) on this build.
;;;
;;; The innovation is the BODY: it retains `sn disjoint` + `same-domain?` and
;;; fires through `rw-fire!` (the class-specific SL truth + graft + stamp
;;; inheritance, whose commits refuse a premise without a receipt or a proof,
;;; intern.metta). So the compiled pack chains at dispatch speed WITH the full
;;; evidence discipline -- exactly what implication->clause compilation (PLN's
;;; `=>`, ProbLog) THROWS AWAY (stamp-blind Truth_Revision double-counts shared
;;; sub-proofs, the SLN §3.0d critique). This merges execution strategies (1)
;;; the |- KB and (3) clause compilation, admissible for ANY pack, not only
;;; receipt-disjoint ones. Compiled firing is bit-identical to the interpreted
;;; rw-fire! (same proof term, same graft), so proof dedup unifies the two paths.

(@doc (sn compile-rules!)
  (@desc "Compile every deductive (ded-shape/structural) R5 registry row into a copula-keyed dispatch clause (sn cgoal COP CONCL) (K4). The compiled clause finds believed premises, enforces the disjoint + same-domain stamp discipline, and fires through rw-fire! -- compiled-dispatch speed WITH the full evidence discipline (the stamp-blindness that PLN/ProbLog clause compilation drops). Idempotent per rule. Returns the compiled rule names.")
  (@params ())
  (@return "Compiled rule name per row"))

(@doc (sn cfire!)
  (@desc "Goal-directed firing through the COMPILED pack (K4): extract the goal's copula and dispatch (sn cgoal COP goal) -- the indexed fast path, no registry scan. Returns the ask!-shaped (: view proof (stmt sid tree)) triple per firing, stamp-checked. A no-op until compile-rules! has run.")
  (@params ((@param "Typed SH goal tree (conclusion to fire toward)")))
  (@return "Answer triple per compiled firing"))

(@doc (sn compiled)
  (@desc "Reflectivity (K4): the rule names compiled into the dispatch pack.")
  (@params ())
  (@return "Compiled rule name per clause"))

(sn (function compile-rules!))
(sn (function cfire!))
(sn (function compiled))

;; the copula of a conclusion/premise sh-tree (the dispatch key)
(= (sn cop-of $tree)
   (case $tree
     (((sh $tag $cop (args $a)) $cop)
      ($other NoCop))))

;; compile ONE registry row into its copula-keyed dispatch clause. The bound
;; $p1/$p2/$concl (carrying the row's freshened variables) are substituted into
;; the added clause -- head and body share those variables, exactly as a
;; hand-written clause; $cs1/$cs2/$ccsid/$cctree stay body-local. A (sn compiled
;; NAME) marker records the compilation (idempotency + reflectivity).
(= (sn compile-row! $name $class $p1 $p2 $concl)
   (let $ccop (sn cop-of $concl)
     (let* (($clause (add-atom &self
                       (= (sn cgoal $ccop $concl)
                          (match &self (, (sn stmt $cs1 $p1) (sn stmt $cs2 $p2))
                            (if (and (sn disjoint $cs1 $cs2) (sn same-domain? $cs1 $cs2))
                                (let (stmt $ccsid $cctree) (sn rw-fire! $name $class $concl $cs1 $cs2)
                                  (: (sn view $ccsid) (sn proof-of $ccsid) (stmt $ccsid $cctree)))
                                (empty))))))
            ($marker (add-atom &self (sn compiled-row $name))))
       $name)))

;; compile every deductive row not yet compiled (idempotent).
(: (sn compile-rules!) (-> %Undefined%))
(= (sn compile-rules!)
   (match &self (sn rw $name $class $p1 $p2 $concl)
     (if (and (sn deductive-class? $class)
              (== () (collapse (once (match &self (sn compiled-row $name) True)))))
         (sn compile-row! $name $class $p1 $p2 $concl)
         (empty))))

;; only deductive shapes are compiled into the goal-directed pack (abduction/
;; induction are not backward-firing; weak shapes stay interpreted).
(= (sn deductive-class? $class)
   (case $class ((ded-shape True) (structural True) ($other False))))

;; goal-directed firing through the compiled pack: copula-indexed dispatch.
(: (sn cfire!) (-> %Undefined% %Undefined%))
(= (sn cfire! $goal)
   (let $cg (sn pat $goal)
     (sn cgoal (sn cop-of $cg) $cg)))

;; reflectivity: the compiled rule set
(= (sn compiled)
   (match &self (sn compiled-row $name) $name))

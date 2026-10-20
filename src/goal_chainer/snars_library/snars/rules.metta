;;; SNARS module — split from the snars.metta monolith (2026-06-12).
;;; Import via the snars.metta aggregator; load order lives there.

;; ---- inference licenses (v2 package L): chaining is licensed, not assumed ----
;; copula chaining (ded/abd/ind/exe/cnv) presumes inheritance-like semantics;
;; P171 chains, P40 must not. The hand table covers the built-in copula and
;; the M1 crawl properties; the COLORE emitters generate licenses at scale.
(sn license transitive "is")
(sn license transitive P171)
(sn license transitive P279)
(sn license transitive P131)

;; license KINDS (R0): a license row is a per-predicate property-
;; characteristic declaration (OWL 2 property characteristics / SROIQ role
;; axioms; lib_pln's RuleGuard tables are the hardcoded precedent). kind =
;; which structural rule family the predicate participates in.
(= (sn licensed-kind? $kind (amr $aid) $cop)
   (not (== () (collapse (once (match &self (sn license $kind $aid) True))))))
(= (sn licensed-kind? $kind () $cop)
   (not (== () (collapse (once (match &self (sn license $kind $cop) True))))))
(= (sn licensed? $amr $cop) (sn licensed-kind? transitive $amr $cop))

;; ---- the rule KB: PLN.metta |- shape (3.0d), truth through one kernel call ----
;; strong: deduction — chain copulas through the middle term (SLN 3.4 / J 9.41)
(= (|- (stmt $s1 (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $m)))))
       (stmt $s2 (sh (tag P d so $amr) $cop (args ((arg s $m) (arg o $y))))))
   (if (and (sn licensed? $amr $cop) (and (sn same-domain? $s1 $s2) (and (sn disjoint $s1 $s2) (sn fr1-ok $s2 (sn marginal $m) (sn marginal $y)))))
       (stmt (sn derived! (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $y)))) $s1 $s2 (sn marginal $y))
             (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $y)))))
       (empty)))

;; weak: abduction — shared predicate (SLN 3.5: w = b1*c2, f = f2)
(= (|- (stmt $s1 (sh (tag P d so $amr) $cop (args ((arg s $p) (arg o $m)))))
       (stmt $s2 (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $m))))))
   (if (and (sn licensed? $amr $cop) (and (not (== $p $x)) (and (sn same-domain? $s1 $s2) (sn disjoint $s1 $s2))))
       (let* (((Opinion $eb $ed $eu $ea) (sn opinion $s1))
              ((Opinion $ob $od $ou $oa) (sn opinion $s2))
              ($c2 (+ $ob $od))
              ($w (* $eb $c2))
              ($f (/ $ob (max (sn config k-eps) $c2))))
         (stmt (sn weak-quantum! (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $p)))) (abd $s1 $s2) $w $f (sn marginal $p) $s1 $s2)
               (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $p))))))
       (empty)))

;; weak: induction — shared subject (SLN 3.5: w = b2*c1, f = f1)
(= (|- (stmt $s1 (sh (tag P d so $amr) $cop (args ((arg s $m) (arg o $p)))))
       (stmt $s2 (sh (tag P d so $amr) $cop (args ((arg s $m) (arg o $x))))))
   (if (and (sn licensed? $amr $cop) (and (not (== $p $x)) (and (sn same-domain? $s1 $s2) (sn disjoint $s1 $s2))))
       (let* (((Opinion $b1 $d1 $u1 $a1) (sn opinion $s1))
              ((Opinion $b2 $d2 $u2 $a2) (sn opinion $s2))
              ($c1 (+ $b1 $d1))
              ($w (* $b2 $c1))
              ($f (/ $b1 (max (sn config k-eps) $c1))))
         (stmt (sn weak-quantum! (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $p)))) (ind $s1 $s2) $w $f (sn marginal $p) $s1 $s2)
               (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $p))))))
       (empty)))

;; weak: exemplification — the reversed chain conclusion (SLN 3.5: w = b1*b2, f = 1)
(= (|- (stmt $s1 (sh (tag P d so $amr) $cop (args ((arg s $p) (arg o $m)))))
       (stmt $s2 (sh (tag P d so $amr) $cop (args ((arg s $m) (arg o $x))))))
   (if (and (sn licensed? $amr $cop) (and (not (== $p $x)) (and (sn same-domain? $s1 $s2) (sn disjoint $s1 $s2))))
       (let* (((Opinion $b1 $d1 $u1 $a1) (sn opinion $s1))
              ((Opinion $b2 $d2 $u2 $a2) (sn opinion $s2))
              ($w (* $b1 $b2)))
         (stmt (sn weak-quantum! (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $p)))) (exe $s1 $s2) $w 1.0 (sn marginal $p) $s1 $s2)
               (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $p))))))
       (empty)))

;; conversion is ON DEMAND (ONA: question answering, never the forward sweep)
(= (sn convert! $sid)
   (match &self (sn stmt $sid (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $y)))))
     (if (sn licensed? $amr $cop)
         (let (Opinion $b $d $u $a) (sn view $sid)
           (sn weak-quantum-d! (sh (tag P d so $amr) $cop (args ((arg s $y) (arg o $x)))) (cnv $sid) $b 1.0 (sn marginal $x) (sn dom-of $sid) $sid $sid))
         (empty))))

;; ---- B3: tuple-domain weak rules (Mapping 3.0d weak shape; benchmark-gated,
;; default ON like every pack -- D3's p1 A/B prices it) ----
(= (sn tuple-rules?) (== 1 (sn cfg tuple-rules 1)))

;; role->filler pairs, dropping any malformed members (3.0f skeleton)
(: (sn role-fillers) (-> Atom Expression))
(= (sn role-fillers $items)
   (if (== $items ())
       ()
       (let ($head $tail) (decons-atom $items)
         (case $head
           (((arg $role $f) (cons-atom ($role $f) (sn role-fillers $tail)))
            ($other (sn role-fillers $tail)))))))

(: (sn filler-for) (-> %Undefined% Atom %Undefined%))
(= (sn filler-for $role $pairs)
   (if (== $pairs ())
       NoFiller
       (let ($head $tail) (decons-atom $pairs)
         (let ($r $f) $head
           (if (== $r $role) $f (sn filler-for $role $tail))))))

;; role-aligned mismatches between two filler lists: (($role $f1 $f2) ...)
(= (sn diff-pairs $p1 $p2)
   (collapse
     (let ($role $f1) (superpose $p1)
       (let $f2 (sn filler-for $role $p2)
         (if (or (== $f2 NoFiller) (== $f1 $f2))
             (empty)
             ($role $f1 $f2))))))

;; weak: shared-tuple abduction (tab) -- same predicate, all-but-one role
;; shared => one bounded quantum (w = b1*c2 <= 1, SLN 3.5 shape) that the
;; differing fillers are alike. Tuple-only by the size>2 guard (binary copula
;; pairs prune to empty -- the sanctioned way the superposed |- KB stays
;; clean); each ordered pair mints its own proof node.
(= (|- (stmt $s1 (sh (tag P d $ro1 $amr) $cop (args $a1)))
       (stmt $s2 (sh (tag P d $ro2 $amr) $cop (args $a2))))
   (if (and (sn tuple-rules?)
            (and (> (size-atom $a1) 2)
                 (and (== (size-atom $a1) (size-atom $a2))
                      (and (not (== $s1 $s2)) (sn disjoint $s1 $s2)))))
       (let $diffs (sn diff-pairs (sn role-fillers $a1) (sn role-fillers $a2))
         (if (== 1 (size-atom $diffs))
             (let ($role $f1 $f2) (car-atom $diffs)
               (let* (((Opinion $b1 $d1 $u1 $aa1) (sn opinion $s1))
                      ((Opinion $b2 $d2 $u2 $aa2) (sn opinion $s2))
                      ($w (* $b1 (+ $b2 $d2)))
                      ($tree (sh (tag P d so ()) "is" (args ((arg s $f1) (arg o $f2))))))
                 (stmt (sn weak-quantum! $tree (tab $s1 $s2) $w 1.0 (sn marginal $f2) $s1 $s2)
                       $tree)))
             (empty)))
       (empty)))

;; ---- B3: T5 specifier lift (Mapping 0.2; on-demand, the convert! precedent).
;; first-x/strip-x/host-minus-x are shared with the conditional pack -- reused,
;; not redefined (smart-dispatch: one sn predicate across modules). ----

;; the trigger's payload (T+C principle: the concept inside IS the context)
(= (sn spec-inner $spec)
   (case $spec
     (((sh (tag T $st $tr $ta) $tl (args ((arg $ir $inner)))) $inner)
      ($other $other))))

;; a conditional-class specifier (if/because/although/unless) is an inter-
;; statement EDGE, not an ist context: when route-conditionals is on it is
;; ingest-cond!'s to consume, never lifted here (sibling R2 coordination).
(= (sn cond-class? $sub)
   (or (== $sub f) (or (== $sub c) (or (== $sub g) (== $sub fneg)))))
(= (sn spec-liftable? $spec)
   (case $spec
     (((sh (tag T $st $tr $ta) $tl $sargs)
       (if (== 1 (sn cfg route-conditionals 1))
           (not (sn cond-class? (sn trig-sub $ta $st $tl)))
           True))
      ($other True))))

;; lift: the spec-stripped parent statement as ONE weak quantum (w = the
;; host's belief mass), the spec recorded as the parent's ist context. The
;; host tree is untouched (drop nothing).
(= (sn lift-spec! $sid)
   (match &self (sn stmt $sid (sh $tag $lbl (args $items)))
     (let $spec (sn first-x $items)
       (if (or (== $spec NoSpec) (not (sn spec-liftable? $spec)))
           (empty)
           (let* (($parent (sn host-minus-x (sh $tag $lbl (args $items))))
                  ((Opinion $b $d $u $a) (sn view $sid))
                  ($inner (sn spec-inner $spec))
                  ($psid (sn weak-quantum! $parent (spc $sid) $b 1.0 (sn config default-rate) $sid $sid))
                  ($ctxed (sn ctx! $psid (sn sid $inner))))
             $psid)))))

;; ---- R4b: role-filler generalization/specialization through taxonomy
;; (NAL-4 products -- structural currying, no truth transform; SLN 10 item 1).
;; Same tuple-rules gate as B3. Both directions substitute ONE filler at the
;; role where it matches the inheritance edge's endpoint. ----

;; replace the FIRST filler equal to $old with $new; return (Sub $role $items')
;; or NoSub (the role is carried into the proof term, so direction is auditable)
(= (sn sub-filler $items $old $new)
   (if (== $items ())
       NoSub
       (let ($head $tail) (decons-atom $items)
         (case $head
           (((arg $r $f)
             (if (== $f $old)
                 (Sub $r (cons-atom (arg $r $new) $tail))
                 (let $rest (sn sub-filler $tail $old $new)
                   (case $rest
                     (((Sub $r2 $items2) (Sub $r2 (cons-atom $head $items2)))
                      (NoSub NoSub))))))
            ($other
             (let $rest (sn sub-filler $tail $old $new)
               (case $rest
                 (((Sub $r2 $items2) (Sub $r2 (cons-atom $head $items2)))
                  (NoSub NoSub))))))))))

;; UPWARD (generalize, induction-shaped, weak): a tuple holding instance f at
;; role r + licensed (f -> g) |- the tuple with g at r. Existentially sound for
;; any tuple; one weak quantum w = b_tuple * b_edge, f = 1. Domain tuple.
(= (|- (stmt $s1 (sh (tag P d $ro1 $amr1) $cop1 (args $a1)))
       (stmt $s2 (sh (tag P d so $eamr) $ecop (args ((arg s $f) (arg o $g))))))
   (if (and (sn tuple-rules?)
            (and (> (size-atom $a1) 2)
                 (and (sn licensed? $eamr $ecop)
                      (and (not (== $s1 $s2)) (sn disjoint $s1 $s2)))))
       (let $sub (sn sub-filler $a1 $f $g)
         (case $sub
           (((Sub $r $newitems)
             (let* (((Opinion $tb $td $tu $ta) (sn opinion $s1))
                    ((Opinion $eb $ed $eu $ea) (sn opinion $s2))
                    ($w (* $tb $eb))
                    ($tree (sh (tag P d $ro1 $amr1) $cop1 (args $newitems))))
               (stmt (sn weak-quantum-d! $tree (gnr $s1 $s2 $r) $w 1.0 (sn marginal $g) tuple $s1 $s2) $tree)))
            (NoSub (empty)))))
       (empty)))

;; DOWNWARD (specialize, deduction-shaped, strong): a GENERIC tuple (aleatory --
;; the 2.2 genericity gate; "mary gave john a book" says nothing about tom)
;; holding class g at role r + licensed (f -> g) |- the tuple with f at r,
;; grafted at discount(omega_tuple, P(edge)) (the 3.7 discount ruling). spz.
(= (|- (stmt $s1 (sh (tag P d $ro1 $amr1) $cop1 (args $a1)))
       (stmt $s2 (sh (tag P d so $eamr) $ecop (args ((arg s $f) (arg o $g))))))
   (if (and (sn tuple-rules?)
            (and (> (size-atom $a1) 2)
                 (and (sn licensed? $eamr $ecop)
                      (and (== aleatory (sn kind-of $s1))
                           (and (not (== $s1 $s2)) (sn disjoint $s1 $s2))))))
       (let $sub (sn sub-filler $a1 $g $f)
         (case $sub
           (((Sub $r $newitems)
             (let* (($op (sn discount-op (sn view $s1) (sn expect $s2)))
                    ($tree (sh (tag P d $ro1 $amr1) $cop1 (args $newitems))))
               (stmt (sn graft! $tree (spz $s1 $s2 $r) $op tuple $s1 $s2) $tree)))
            (NoSub (empty)))))
       (empty)))


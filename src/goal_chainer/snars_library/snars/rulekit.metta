;;; SNARS module — the reflective rewrite-rule registry (rule pack R5).
;;; Import via the snars.metta aggregator; load order lives there.
;;;
;;; Rules are DATA: (sn rw <name> <class> <prem1-pat> <prem2-pat> <concl-pat>)
;;; rows live in &self with logic variables in the stored patterns. ONE driver
;;; |- clause matches a BOUND premise pair against the patterns (clause-head
;;; matching -- the 4-arg atom-form `unify` does not reduce in PeTTa, so stored
;;; rows in match-pattern positions are the mechanism; probe-verified), binds
;;; the row's variables, and instantiates the conclusion. Truth is attached per
;;; class. The system can read its own rule set (the paper-5 reflectivity
;;; property) and the ledger learns each registered rule's reliability via the
;;; (rw <name>)-keyed trust cells, exactly as it does for the built-in |- rules.
;;; This is the extension framework's rule-pack contribution point: an extension
;;; registers rows -- license facts, clause heads, rewrite rules -- without code.

(= (sn rw-rules?) (== 1 (sn cfg rw-rules 1)))

;; per-row gate (default ON): (add-atom &self (sn cfg-set (rw-off <name>) 1)) disables
(= (sn rw-enabled? $name) (== 0 (sn cfg (rw-off $name) 0)))

;; the conclusion's object base rate (binary-copula conclusions; the o-filler's
;; live marginal, else the default prior). Reuses B3's role-fillers/filler-for.
(= (sn rw-obj-a $concl)
   (case $concl
     (((sh $tag $lbl (args $items))
       (let $o (sn filler-for o (sn role-fillers $items))
         (if (== $o NoFiller) (sn config default-rate) (sn marginal $o))))
      ($other (sn config default-rate)))))

;; truth by class: deduction-shaped grafts deduce() (J 9.41); the weak shapes
;; fuse the SLN 3.5 quanta (mirroring the built-in abd/ind clauses); structural
;; fuses one w = b1*b2*b_struct, f=1 quantum (the 3.7 structural-truth discount).
;; Proof (rw <name> s1 s2) -> proof-op (rw <name>), so the trust ledger keys a
;; cell per (rule name, conclusion pred-key) -- learned reliability, per rule.
(= (sn rw-fire! $name $class $concl $s1 $s2)
   (case $class
     ((ded-shape
       (let $op (sn deduce $s1 $s2 (sn rw-obj-a $concl))
         (stmt (sn graft! $concl (rw $name $s1 $s2) $op (sn dom-of $s1) $s1 $s2) $concl)))
      (weak-abd-shape
       (let* (((Opinion $eb $ed $eu $ea) (sn opinion $s1))
              ((Opinion $ob $od $ou $oa) (sn opinion $s2))
              ($c2 (+ $ob $od))
              ($w (* $eb $c2))
              ($f (/ $ob (max (sn config k-eps) $c2))))
         (stmt (sn weak-quantum-d! $concl (rw $name $s1 $s2) $w $f (sn rw-obj-a $concl) (sn dom-of $s1) $s1 $s2) $concl)))
      (weak-ind-shape
       (let* (((Opinion $b1 $d1 $u1 $a1) (sn opinion $s1))
              ((Opinion $b2 $d2 $u2 $a2) (sn opinion $s2))
              ($c1 (+ $b1 $d1))
              ($w (* $b2 $c1))
              ($f (/ $b1 (max (sn config k-eps) $c1))))
         (stmt (sn weak-quantum-d! $concl (rw $name $s1 $s2) $w $f (sn rw-obj-a $concl) (sn dom-of $s1) $s1 $s2) $concl)))
      (structural
       (let* (((Opinion $b1 $d1 $u1 $a1) (sn opinion $s1))
              ((Opinion $b2 $d2 $u2 $a2) (sn opinion $s2))
              ($w (* (* $b1 $b2) (sn config structural-b))))
         (stmt (sn weak-quantum-d! $concl (rw $name $s1 $s2) $w 1.0 (sn rw-obj-a $concl) (sn dom-of $s1) $s1 $s2) $concl))))))

;; the driver: ONE |- clause closing the loop over every registry row. The
;; bound premise trees $t1/$t2 in the match-pattern positions unify against the
;; stored row patterns, instantiating $concl; truth dispatches on the row class.
(= (|- (stmt $s1 $t1) (stmt $s2 $t2))
   (if (sn rw-rules?)
       (match &self (sn rw $name $class $t1 $t2 $concl)
         (if (and (sn rw-enabled? $name) (and (sn disjoint $s1 $s2) (sn same-domain? $s1 $s2)))
             (sn rw-fire! $name $class $concl $s1 $s2)
             (empty)))
       (empty)))

;; chainer-compat view (O25 sbc / dtl synthesize ride these rows unchanged):
;; project each row as a typed constructor. On demand only -- never materialized.
(= (sn rw-typed)
   (match &self (sn rw $name $class $p1 $p2 $c)
     (: (rw $name) (-> (stmt $p1) (stmt $p2) (stmt $c)))))

;; reflectivity: the system reads its own rule set (the paper-5 property)
(= (sn rw-list) (collapse (match &self (sn rw $name $cl $p1 $p2 $c) $name)))

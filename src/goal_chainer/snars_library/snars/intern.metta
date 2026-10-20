;;; SNARS module — split from the snars.metta monolith (2026-06-12).
;;; Import via the snars.metta aggregator; load order lives there.

;; ---- statement interning, proofs, receipts ----
;; coarse adjacency keys (O18 transposed indexes): atom label or connector
;; label — collisions only add candidates, |- head unification still verifies
(= (sn term-key (sh-atom $tag $label)) $label)
(= (sn term-key (sh $tag $label $args)) $label)
(= (sn term-key (sh-conn $conn $args)) (sn term-key $conn))
;; sn-ref fillers key by their sid (B2; safe append -- constructor heads
;; are mutually exclusive, no clause superposition)
(= (sn term-key (sn-ref $sid)) $sid)

;; the concept-as-cache move: copula statements index by subject/object key,
;; so partner lookup is an indexed fetch instead of an O(n) scan. Binary so
;; copulas keep the dedicated fast path and emit NO rk rows (no-double-
;; counting: indexed both ways they would conduct twice in diffusion).
;; rk writer note: add-atom does NOT evaluate its argument -- the key MUST
;; be let-bound before the add.
(: (sn index-args!) (-> %Undefined% Atom Bool))
(= (sn index-args! $sid $items)
   (if (== $items ())
       True
       (let ($head $tail) (decons-atom $items)
         (let $done (case $head
                      (((arg $role $f)
                        (let $key (sn term-key $f)
                          (let $added (add-atom &self (sn rk $role $key $sid)) True)))
                       ($other True)))
           (sn index-args! $sid $tail)))))

(= (sn index! $sid $tree)
   (case $tree
     (((sh (tag P $sub so $amr) $cop (args ((arg s $x) (arg o $y))))
       (let* (($sk (sn term-key $x))
              ($ok (sn term-key $y))
              ($a1 (add-atom &self (sn sub $sk $sid)))
              ($a2 (add-atom &self (sn obj $ok $sid))))
         True))
      ((sh $tag $cop (args $items))
       (sn index-args! $sid $items))
      ($other True))))

(= (sn intern! $sid $tree $domain $kind)
   (if (== () (collapse (once (match &self (sn stmt $sid $t) True))))
       (let* (($stmt (add-atom &self (sn stmt $sid $tree)))
              ($dom (add-atom &self (sn domain $sid $domain)))
              ($knd (add-atom &self (sn kind $sid $kind)))
              ($idx (sn index! $sid $tree)))
         True)
       False))

(= (sn stamps-inherit! $to $from)
   (collapse (match &self (sn stamp $from $h)
     (sn stamp! $to $h))))

;; ---- support: which statements may be premises ----
;; a statement is supported when it was observed, a receipt row (receipt! writes
;; one for every authored, ingested or structural assertion, whatever evidence
;; it carries, vacuous and negative included), or derived, a proof row. An
;; interned reference with neither -- a conditional's endpoint, a query, a
;; believe-channel content, a claim -- names a proposition without asserting
;; it, and carries no stamp, so stamp disjointness alone would let it through.
;; The commits below write a proof only from supported premises, so every
;; proof row rests on support and a consumer's local check is enough. A raw
;; (sn input ...) on a sid is a numeric primitive: it writes a cell, never
;; support.
(= (sn supported? $sid)
   (if (== () (collapse (once (match &self (sn receipt $sid $sigma $h) True))))
       (not (== () (collapse (once (match &self (sn proof $sid $p) True)))))
       True))
(= (sn supported-pair? $s1 $s2)
   (and (sn supported? $s1) (sn supported? $s2)))

;; ---- domain helpers (R0; 1.9 domain-homogeneity, SLN 9.5 typed domains) ----
;; a statement's domain is its reasoning-regime tag; rules never cross regimes
(= (sn dom-of $sid)
   (case (collapse (match &self (sn domain $sid $d) $d))
     ((() instance)
      (($d) $d))))
(= (sn same-domain? $s1 $s2) (== (sn dom-of $s1) (sn dom-of $s2)))

;; the reasoning kind of a statement (aleatory|epistemic|structural); the
;; default is aleatory (a bare cell with no kind row reads generic). R4b's
;; genericity gate (2.2) reads this.
(= (sn kind-of $sid)
   (case (collapse (once (match &self (sn kind $sid $k) $k)))
     ((() aleatory)
      (($k) $k))))

;; ---- step-3 routing (Mapping 3.1 step 3; 3.0f domains) ----
(= (sn args-of $canon)
   (case $canon
     (((sh $tag $lbl (args $items)) $items)
      ($other ()))))

(= (sn has-role? $items $role)
   (not (== () (collapse (once
     (let (arg $r $f) (superpose $items)
       (if (== $r $role) True (empty))))))))

;; 3+ role fillers -> tuple; a t-role or temporal-trigger x-role -> occasion;
;; binary copulas stay instance. ordering arrives via believe!'s :domain and
;; the R3 comparative route. (Parser-fed time arrives as Tt x-args per the
;; current SH manual; the bare t-role is the authored/wikidata convention.)
(= (sn domain-of $canon)
   (let $items (sn args-of $canon)
     (if (> (size-atom $items) 2)
         tuple
         (if (sn has-role? $items t) occasion instance))))

;; lift occ and ist-context facts from role fillers; fillers STAY in the
;; tree (identity unchanged, sid stable) -- extraction is additive facts only
(= (sn ctx! $sid $cid)
   (with_mutex sn-commit
     (if (== () (collapse (once (match &self (sn ctx $sid $cid) True))))
         (let $added (add-atom &self (sn ctx $sid $cid)) True)
         False)))

(= (sn extract-one! $sid $item)
   (case $item
     (((arg t $f) (sn occ! $sid (sn term-key $f)))
      ((arg x (sh (tag T t $tr $ta) $tl (args ((arg $ir $inner)))))
       (sn occ! $sid (sn term-key $inner)))
      ((arg x (sh (tag T l $tr $ta) $tl (args ((arg $ir $inner)))))
       (sn ctx! $sid (sn sid $inner)))
      ;; Tr is an attention hint first (1.6) -- weak ist tag + a topical touch
      ((arg x (sh (tag T r $tr $ta) $tl (args ((arg $ir $inner)))))
       (let* (($c (sn ctx! $sid (sn sid $inner)))
              ($hot (sn act-touch! (sn term-key $inner) 1.0)))
         True))
      ($other True))))

(: (sn extract-args!) (-> %Undefined% Atom Bool))
(= (sn extract-args! $sid $items)
   (if (== $items ())
       True
       (let ($head $tail) (decons-atom $items)
         (let $done (sn extract-one! $sid $head)
           (sn extract-args! $sid $tail)))))

(: (sn disjoint) (-> %Undefined% %Undefined% Bool))
(= (sn disjoint $a $b)
   (== () (collapse (match &self (, (sn stamp $a $h) (sn stamp $b $h)) $h))))

(= (sn derived! $tree $s1 $s2 $ay)
   (if (sn supported-pair? $s1 $s2)
       (with_mutex sn-commit
         (let $sid (sn sid $tree)
           (if (== () (collapse (once (match &self (sn proof $sid (ded $s1 $s2)) True))))
               (let* (((Opinion $b $d $u $a) (sn deduce $s1 $s2 $ay))
                      ((Ev $r $s $ae) (sn op-to-ev (Opinion $b $d $u $a)))
                      ($interned (sn intern! $sid $tree instance aleatory))
                      ($prule (sn rule-p ded $tree))
                      ($fused (sn input $sid $r $s $a "derived" $prule))
                      ($proved (add-atom &self (sn proof $sid (ded $s1 $s2))))
                      ($stamp1 (sn stamps-inherit! $sid $s1))
                      ($stamp2 (sn stamps-inherit! $sid $s2))
                      ($touched (sn fr-touch! $sid)))
                 $sid)
               $sid)))
       (empty)))

;; one bounded pseudo-observation (3.5): w <= 1, fused never stored standalone.
;; The -d! form carries the conclusion's DOMAIN (R0); weak-quantum! delegates
;; at instance so existing call sites are unchanged.
(= (sn weak-quantum-d! $tree $prfterm $w $f $a $domain $from1 $from2)
   (if (sn supported-pair? $from1 $from2)
       (with_mutex sn-commit
         (let $sid (sn sid $tree)
           (if (== () (collapse (once (match &self (sn proof $sid $prfterm) True))))
               (let* (($interned (sn intern! $sid $tree $domain aleatory))
                      ($prule (sn rule-p (sn proof-op $prfterm) $tree))
                      ($fused (sn input $sid (* $f $w) (* (- 1.0 $f) $w) $a "weak" $prule))
                      ($proved (add-atom &self (sn proof $sid $prfterm)))
                      ($stamp1 (sn stamps-inherit! $sid $from1))
                      ($stamp2 (sn stamps-inherit! $sid $from2))
                      ($touched (sn fr-touch! $sid)))
                 $sid)
               $sid)))
       (empty)))
(= (sn weak-quantum! $tree $prfterm $w $f $a $from1 $from2)
   (sn weak-quantum-d! $tree $prfterm $w $f $a instance $from1 $from2))

;; graft: fuse a derived OPINION as evidence with proof + stamps (the strong-
;; rule commit for non-deduction math: analogy, mp, sim2inh, hs, mirrors)
(= (sn graft-into! $sid $prf $op $from1 $from2)
   (if (sn supported-pair? $from1 $from2)
       (with_mutex sn-commit
         (if (== () (collapse (once (match &self (sn proof $sid $prf) True))))
             (let* (((Ev $r $s $ae) (sn op-to-ev $op))
                    ((Opinion $b $d $u $a) $op)
                    ($fused (sn input $sid $r $s $a "derived" 1.0))
                    ($proved (add-atom &self (sn proof $sid $prf)))
                    ($st1 (sn stamps-inherit! $sid $from1))
                    ($st2 (sn stamps-inherit! $sid $from2))
                    ($touched (sn fr-touch! $sid)))
               $sid)
             $sid))
       (empty)))
;; graft! interns a new conclusion, so it refuses before interning
(= (sn graft! $tree $prf $op $domain $from1 $from2)
   (if (sn supported-pair? $from1 $from2)
       (with_mutex sn-commit
         (let* (($sid (sn sid $tree))
                ($interned (sn intern! $sid $tree $domain aleatory)))
           (sn graft-into! $sid $prf $op $from1 $from2)))
       (empty)))

;; symmetric license (SLN 9.8.4: conversion is Bayes; for a symmetric relation
;; the inverse IS the original -- full view carries, f preserved, w = c).
;; v1 fires on first intern only (proof-deduped); canon-level arg-sort identity
;; is the COMMITTED v2 (ruling 2026-06-12 -- prerelease, sid re-keying blessed):
;; this mirror op is deleted the day canon sorts symmetric-licensed args. The
;; mirror inherits the source's DOMAIN (equative orderings mirror in ordering).
(= (sn sym-edges! $sid)
   (if (== 1 (sn cfg sym-rules 1))
       (match &self (sn stmt $sid (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $y)))))
         (if (sn licensed-kind? symmetric $amr $cop)
             (let* (((Opinion $b $d $u $a) (sn view $sid))
                    ($c (+ $b $d))
                    ($f (sn kdiv $b (+ $b $d)))
                    ($mt (sh (tag P d so $amr) $cop (args ((arg s $y) (arg o $x))))))
               (sn weak-quantum-d! $mt (sym $sid) $c $f $a (sn dom-of $sid) $sid $sid))
             (empty)))
       (empty)))

;; ---- term marginals (SLN section 8): seeded priors read as live base rates ----
(= (sn marginal! $term $a)
   (sn input (sn sid $term) 0.0 0.0 $a "prior" 1.0))
(= (sn marginal $term)
   (sn expect (sn sid $term)))

;; ---- Frechet consistency (SLN 8.5; PLN book 5.2.2.2 preconditions) ----
(= (sn frechet $ax $ay)
   (let $axc (sn aclamp $ax)
     ((max 0.0 (/ (- (+ $axc $ay) 1.0) $axc))
      (min 1.0 (/ $ay $axc)))))
(= (sn fr1-ok $se $ax $ay)
   (let* ((($lo $hi) (sn frechet $ax $ay))
          ($q (sn expect $se)))
     (and (>= $q $lo) (<= $q $hi))))


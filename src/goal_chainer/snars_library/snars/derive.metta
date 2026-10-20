;;; SNARS module — split from the snars.metta monolith (2026-06-12).
;;; Import via the snars.metta aggregator; load order lives there.

;; ---- forward driver and bounded cycle (lib_nars/lib_pln Derive, frontier-less v0) ----
;; every rule a pair fires commits through derived!, weak-quantum-d! or
;; graft-into!, which refuse an unsupported premise (intern.metta)
(= (sn derive-pair! $s1 $s2)
   (match &self (, (sn stmt $s1 $t1) (sn stmt $s2 $t2))
     (|- (stmt $s1 $t1) (stmt $s2 $t2))))

;; the sweep walks the REAL co-occurrence graph (O18 indexes), not all pairs:
;; chain partners by subject-of-object, abduction by shared object, induction
;; by shared subject — |- head unification remains the verifier
(: (sn derive!) (-> %Undefined%))
(= (sn derive!)
   (match &self (sn stmt $s1 (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $m)))))
     (let* (($mk (sn term-key $m))
            ($xk (sn term-key $x)))
       (superpose (
         (match &self (sn sub $mk $s2) (if (== $s1 $s2) (empty) (sn derive-pair! $s1 $s2)))
         (match &self (sn obj $mk $s2) (if (== $s1 $s2) (empty) (sn derive-pair! $s1 $s2)))
         (match &self (sn sub $xk $s2) (if (== $s1 $s2) (empty) (sn derive-pair! $s1 $s2))))))))

;; R2 partners, which the label keys above never reach: each ==> edge with typed
;; (sn-ref) fillers pairs with the statements they name, its antecedent for
;; modus ponens and its consequent for abductive mp, found by sid, so a premise
;; of any arity takes part
(= (sn derive!)
   (match &self (sn stmt $e (sh (tag P d so ()) "==>" (args ((arg s (sn-ref $sa)) (arg o (sn-ref $sb))))))
     (let $p (superpose ($sa $sb))
       (sn derive-pair! $p $e))))

(: (sn cycles) (-> Number Expression))
(= (sn cycles $n)
   (if (<= $n 0)
       ()
       (let $step (collapse (sn derive!))
         (sn cycles (- $n 1)))))


;; ---- the derivation frontier (3.1b): bounded best-first, valued c * Psi ----
;; Psi is the relevance lemma |P(y|x) - P(y|not-x)| computed from the edge's
;; view and the synthesized else; c is the premise's confidence. This is the
;; structural socket the learned G1 value plugs into later.
!(sn_cell_put sn-frontier ())
(= (sn frontier) (sn_cell_get sn-frontier))
(= (sn config frontier-cap) 64)
(= (sn config decay) 0.95)
(= (sn config ws-size) 8)
(= (sn config ws-boost) 0.5)
(= (sn config act-alpha) 0.5)
(= (sn config act-eps) 0.05)
(= (sn config act-boost) 0.5)
(= (sn config diffuse-budget) 4)

;; the working set: the last K touched concept keys (the locality assumption —
;; what comes next is probably about what was just processed)
!(sn_cell_put sn-ws ())

(: (sn ws-add!) (-> %Undefined% Expression))
(= (sn ws-add! $key)
   (with_mutex sn-commit
     (let* (($ws (sn_cell_get sn-ws))
            ($next (sn fr-take (sn config ws-size) (cons-atom $key $ws)))
            ($set (sn_cell_put sn-ws $next)))
       $next)))

(= (sn ws-member? $key)
   (let $ws (sn_cell_get sn-ws)
     (not (== () (collapse (let $k (superpose $ws) (case (== $k $key) ((True True)))))))))

;; topical boost: pairs about working-set concepts get (1 + ws-boost)
(= (sn ws-factor $key)
   (if (sn ws-member? $key)
       (+ 1.0 (sn config ws-boost))
       1.0))

;; ---- the diffusion field (Andersen-Chung-Lang local push over concept keys) ----
;; estimate = the attention field; residual = mass not yet spread; a key pushes
;; only when residual >= eps * degree (the ACT-R fan effect for free: hubs need
;; more accumulated evidence before they propagate). Neighbors come from the
;; adjacency indexes; work per event is bounded by the diffuse budget.
!(sn_cell_put sn-resq (queue () () 0))

(= (sn act $key)
   (sn_act_val $key (sn config decay) (sn_tick_now)))

;; weighted neighbors (v2 P3): conduction proportional to the connecting
;; statement's confidence c_e — ACT-R S_ji in place of a uniform walk; the
;; weighted walk is the standard push generalization (transitions ~ w_e)
(= (sn edge-c $s)
   (let (Ev $r $sn $a) (sn evidence $s)
     (let $w (+ $r $sn) (/ $w (+ $w 2.0)))))

(= (sn neighbors $key)
   (collapse (superpose (
     (match &self (, (sn sub $key $s) (sn stmt $s (sh (tag P d so $a) $c (args ((arg s $x) (arg o $y))))))
       ((sn term-key $y) (sn edge-c $s)))
     (match &self (, (sn obj $key $s) (sn stmt $s (sh (tag P d so $a) $c (args ((arg s $x) (arg o $y))))))
       ((sn term-key $x) (sn edge-c $s)))
     ;; B2: tuple co-occurrence conducts too (rk rows; edge-confidence weighted)
     (match &self (, (sn rk $r1 $key $s) (sn rk $r2 $k2 $s))
       (if (== $k2 $key) (empty) ($k2 (sn edge-c $s))))))))

(: (sn wsum) (-> Atom Number))
(= (sn wsum $ps)
   (if (== $ps ()) 0.0
       (+ (car-atom (cdr-atom (car-atom $ps))) (sn wsum (cdr-atom $ps)))))

;; Okasaki two-list functional queue (banker's queue; Okasaki, Purely
;; Functional Data Structures, 1998): amortized O(1) enqueue/dequeue
;; replacing the O(n)-per-add append list (P0 perf item ix). Cap semantics
;; preserved exactly: at cap 32 NEW keys drop (the old fr-take-32 read kept
;; the first 32); FIFO order preserved (enqueue conses onto In, dequeue
;; reverses In into Out on demand).
(: (sn rev-onto) (-> Atom Atom Expression))
(= (sn rev-onto $xs $acc)
   (if (== $xs ())
       $acc
       (let ($h $t) (decons-atom $xs)
         (sn rev-onto $t (cons-atom $h $acc)))))

(= (sn resq-pop!)
   (with_mutex sn-commit
     (let (queue $in $out $n) (sn_cell_get sn-resq)
       (if (== $out ())
           (if (== $in ())
               ()
               (let ($h $t) (decons-atom (sn rev-onto $in ()))
                 (let $set (sn_cell_put sn-resq (queue () $t (- $n 1)))
                   ($h))))
           (let ($h $t) (decons-atom $out)
             (let $set (sn_cell_put sn-resq (queue $in $t (- $n 1)))
               ($h)))))))

(= (sn resq-add! $key)
   (with_mutex sn-commit
     (let (queue $in $out $n) (sn_cell_get sn-resq)
       (if (>= $n 32)
           True
           (let $set (sn_cell_put sn-resq (queue (cons-atom $key $in) $out (+ $n 1)))
             True)))))

(= (sn act-touch! $key $w)
   (let* (($r (sn_act_res $key $w (sn config decay) (sn_tick_now)))
          ($q (sn resq-add! $key)))
     $r))

;; one budgeted push round (ACL local push): pop a key, push if over threshold,
;; spread to neighbors (multiplicity-weighted) and enqueue them; below the
;; threshold the residual stays latent — deferred work, never lost
(: (sn diffuse!) (-> Number Expression))
(= (sn diffuse! $budget)
   (if (<= $budget 0)
       ()
       (let $popped (sn resq-pop!)
         (if (== $popped ())
             ()
             (let* (($key (car-atom $popped))
                    ($res (sn_act_res $key 0.0 (sn config decay) (sn_tick_now)))
                    ($ns (sn neighbors $key))
                    ($dw (max 1.0 (sn wsum $ns))))
               (if (>= $res (* (sn config act-eps) $dw))
                   (let* (($spread (sn_act_push $key (sn config act-alpha) (sn config decay) (sn_tick_now)))
                          ($sent (collapse (let $p (superpose $ns)
                                   (sn act-touch! (car-atom $p)
                                     (* $spread (/ (car-atom (cdr-atom $p)) $dw)))))))
                     (sn diffuse! (- $budget 1)))
                   (sn diffuse! (- $budget 1))))))))

(= (sn psi $se $am $ay)
   (let* (($ayc (sn aclamp $ay))
          ((Opinion $eb $ed $eu $ea) (sn view $se))
          ($pos (Opinion $eb $ed $eu $ayc))
          ((Opinion $nb $nd $nu $na) (sn synth-else $pos (sn aclamp $am) $ayc))
          ($q (+ $eb (* $ayc $eu)))
          ($pbar (+ $nb (* $na $nu))))
     (abs-math (- $q $pbar))))

;; E1 (3.1b): surprise is a frontier-value factor -- a statement that moved its
;; cell sharply at the last fuse earns priority (the curriculum weight, 1+KL).
(= (sn fr-value $s1 $s2 $am $ay)
   (let* (((Opinion $b $d $u $a) (sn view $s1))
          ($c (+ $b $d)))
     (* (* $c (sn psi $s2 $am $ay)) (+ 1.0 (sn surprise $s1)))))

;; Callers supply their native key: raw at admission, decayed at selection.
;; An optional world can replace this equation; default worlds compare only keys.
;; am[implements a-integrate-frontier-order-hook-1017@dab0ee]
;; am[rests-on c-integrate-frontier-default-substitution-1017@9a11e9]
(= (sn fr-before $first $first-key $second $second-key)
   (> $first-key $second-key))

;; Time: at most n comparisons and n list cells, n = frontier length.
;; am[implements a-integrate-frontier-order-hook-1017@dab0ee]
(: (sn fr-insert) (-> Atom %Undefined% Expression))
(= (sn fr-insert $items $item)
   (if (== $items ())
       ($item)
       (let ($head $tail) (decons-atom $items)
         (let (Fr $v1 $t1 $x1 $y1) $item
           (let (Fr $v2 $t2 $x2 $y2) $head
             (if (sn fr-before $item $v1 $head $v2)
                 (cons-atom $item $items)
                 (cons-atom $head (sn fr-insert $tail $item))))))))

;; activation: value decays with logical age (ALANN-style, no wall clock)
(= (sn fr-act $v $tick $now)
   (* $v (pow-math (sn config decay) (- $now $tick))))

;; The sentinel keeps its native bound; only comparisons between items use the hook.
;; Time: n decays and at most n comparisons, n = frontier length.
;; am[implements a-integrate-frontier-order-hook-1017@dab0ee]
(: (sn fr-best) (-> Atom Number %Undefined% Number %Undefined%))
(= (sn fr-best $items $now $best $bv)
   (if (== $items ())
       $best
       (let ($head $tail) (decons-atom $items)
         (let (Fr $v $t $x $y) $head
           (let* (($av (sn fr-act $v $t $now))
                  ($better (if (== $best NoItem)
                              (> $av $bv)
                              (sn fr-before $head $av $best $bv))))
             (if $better
                 (sn fr-best $tail $now $head $av)
                 (sn fr-best $tail $now $best $bv)))))))

(: (sn fr-remove) (-> Atom %Undefined% Expression))
(= (sn fr-remove $items $item)
   (if (== $items ())
       ()
       (let ($head $tail) (decons-atom $items)
         (if (== $head $item)
             $tail
             (cons-atom $head (sn fr-remove $tail $item))))))

(: (sn fr-take) (-> Number Atom Expression))
(= (sn fr-take $k $items)
   (if (or (<= $k 0) (== $items ()))
       ()
       (let ($head $tail) (decons-atom $items)
         (cons-atom $head (sn fr-take (- $k 1) $tail)))))

;; the frontier's one admission point: every touch clause pushes here, so a pair
;; with an unsupported statement (intern.metta) is never queued, and neither the
;; working set nor the activation field moves for it
(= (sn fr-push! $s1 $s2 $am $ay $mkey)
   (if (sn supported-pair? $s1 $s2)
       (with_mutex sn-commit
         (let* (($v (* (sn fr-value $s1 $s2 $am $ay)
                       (* (sn ws-factor $mkey)
                          (+ 1.0 (* (sn config act-boost) (sn act $mkey))))))
                ($tick (sn_tick))
                ($wsd (sn ws-add! $mkey))
                ($touched (sn act-touch! $mkey 1.0))
                ($diffused (sn diffuse! (sn config diffuse-budget)))
                ($items (sn_cell_get sn-frontier))
                ($next (sn fr-take (sn config frontier-cap) (sn fr-insert $items (Fr $v $tick $s1 $s2))))
                ($set (sn_cell_put sn-frontier $next)))
           $v))
       (empty)))

;; push the pairs a statement participates in — partner lookup is INDEXED
;; (the 3.1 step-6 wavefront: O(degree) per touched statement, never a scan)
;; predicate-compatible pairs only (shared $amr/$cop, mirroring the |- premise
;; constraint): key-collision junk pairs are unfireable and, under the frontier
;; cap, would crowd out real chains — found at 4.5k wikidata scale where many
;; predicates coexist (synth data has one predicate, so it never showed)
(= (sn fr-touch! $sid)
   (collapse (superpose (
     (match &self (sn stmt $sid (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $m)))))
       (let $mk (sn term-key $m)
         (match &self (, (sn sub $mk $s2)
                         (sn stmt $s2 (sh (tag P d so $amr) $cop (args ((arg s $m2) (arg o $y))))))
           (if (== $sid $s2)
               (empty)
               (sn fr-push! $sid $s2 (sn marginal $m2) (sn marginal $y) $mk)))))
     (match &self (sn stmt $sid (sh (tag P d so $amr) $cop (args ((arg s $m) (arg o $y)))))
       (let $mk (sn term-key $m)
         (match &self (, (sn obj $mk $s1)
                         (sn stmt $s1 (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $m1))))))
           (if (== $sid $s1)
               (empty)
               (sn fr-push! $s1 $sid (sn marginal $m1) (sn marginal $y) $mk)))))
     ;; R2: a touched statement pairs with each ==> edge whose typed (sn-ref
     ;; $sid) filler names it, the filler both conditional rules match. An edge
     ;; is binary, so index! files it under the sid as a sub row where it names
     ;; its antecedent (modus ponens) and as an obj row where it names its
     ;; consequent (abductive mp); binary statements write no rk rows. Indexed,
     ;; never a scan. A concept whose label is the same symbol shares the key
     ;; but not the typed filler, so it never pairs
     (match &self (, (sn sub $sid $edge)
                     (sn stmt $edge (sh (tag P d so ()) "==>" (args ((arg s (sn-ref $sid)) (arg o (sn-ref $sb)))))))
       (sn fr-push! $sid $edge 0.5 0.5 $sid))
     (match &self (, (sn obj $sid $edge)
                     (sn stmt $edge (sh (tag P d so ()) "==>" (args ((arg s (sn-ref $sa)) (arg o (sn-ref $sid)))))))
       (sn fr-push! $sid $edge 0.5 0.5 $sid))
     ;; R2, the other arrival order: a touched edge pairs with each statement
     ;; its fillers name, valued as above, so a pair reaches the frontier
     ;; whichever of the two arrives last
     (match &self (sn stmt $sid (sh (tag P d so ()) "==>" (args ((arg s (sn-ref $sa)) (arg o (sn-ref $sb))))))
       (let $p (superpose ($sa $sb))
         (match &self (sn stmt $p $tp)
           (sn fr-push! $p $sid 0.5 0.5 $p))))
     ;; B2: tuple statements seed frontier pairs through shared rk keys
     ;; (predicate-compatible only -- key-collision junk would crowd the cap);
     ;; v0 valuation passes flat 0.5 marginals (no middle-term marginal exists
     ;; for tuples; the learned G1 value replaces this socket later, 3.1b)
     (match &self (sn rk $role $k $sid)
       (match &self (sn rk $role $k $s2)
         (if (or (== $sid $s2) (not (sn same-pred? $sid $s2)))
             (empty)
             (sn fr-push! $sid $s2 0.5 0.5 $k))))))))

;; single-valued predicate-key equality (B2; total via A1's pred-key)
(= (sn same-pred? $s1 $s2)
   (case (collapse (once (match &self (, (sn stmt $s1 $t1) (sn stmt $s2 $t2))
                     (== (sn pred-key $t1) (sn pred-key $t2)))))
     ((() False)
      (($r) $r))))

;; pop the single best pair and fire the rule KB on it
(= (sn step!)
   (let $popped (with_mutex sn-commit
                  (let $items (sn_cell_get sn-frontier)
                    (if (== $items ())
                        ()
                        (let* (($now (sn_tick_now))
                               ($best (sn fr-best $items $now NoItem -1.0))
                               ($set (sn_cell_put sn-frontier (sn fr-remove $items $best))))
                          ($best)))))
     (if (== $popped ())
         (empty)
         (let (Fr $v $t $s1 $s2) (car-atom $popped)
           (match &self (, (sn stmt $s1 $t1) (sn stmt $s2 $t2))
             (|- (stmt $s1 $t1) (stmt $s2 $t2)))))))

;; bounded best-first control loop: n pops, highest value first
(: (sn focus!) (-> Number Expression))
(= (sn focus! $n)
   (if (<= $n 0)
       ()
       (let $step (collapse (sn step!))
         (sn focus! (- $n 1)))))


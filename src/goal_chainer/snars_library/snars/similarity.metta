;;; SNARS module — the SLN 9.8 similarity pack (plan: 2026-06-12 rule pack R1).
;;; Import via the snars.metta aggregator; load order lives there.
;;; Similarity is the Jaccard conditional in disguise (9.8.1): conclusions
;;; live in the similarity DOMAIN under the canonical label "<->" (symmetric-
;;; licensed; "alike" is an aliased spelling -- one sid, two spellings).

(= (sn sim-rules?) (== 1 (sn cfg sim-rules 1)))

;; the canonical similarity label is symmetric-licensed (R0 machinery)
(sn license symmetric "<->")

;; authoring/query sugar: aliased pred labels normalize to the canonical
;; identity-bearing label BEFORE sid; display can render the friendly face
(sn pred-alias "alike" "<->")
(sn label "<->" "alike")

;; evidence-coordinate views (NAL f/c from a cell, k=W=2)
(= (sn fc-of $sid)
   (let (Ev $r $s $a) (sn evidence $sid)
     ((sn kdiv $r (+ $r $s)) (sn kdiv (+ $r $s) (+ (+ $r $s) 2.0)))))

;; comparison (9.8.2): M->S, M->P |- S<->P -- ONE bounded Jaccard quantum,
;; canonical arg order via sn_key_le (the mirrored read comes from the
;; symmetric license, never a second cell). NAL's formula derived: the
;; (f1 v f2)-fraction of M's evidence lands in the union domain.
(= (|- (stmt $s1 (sh (tag P d so $amr) $cop (args ((arg s $m) (arg o $p)))))
       (stmt $s2 (sh (tag P d so $amr2) $cop (args ((arg s $m) (arg o $x))))))
   (if (and (sn sim-rules?)
            (and (sn licensed? $amr $cop)
                 (and (not (== $p $x))
                      (and (sn_key_le (sn term-key $p) (sn term-key $x))
                           (and (sn same-domain? $s1 $s2) (sn disjoint $s1 $s2))))))
       (let* ((($f1 $c1) (sn fc-of $s1))
              (($f2 $c2) (sn fc-of $s2))
              ($funion (- (+ $f1 $f2) (* $f1 $f2)))
              ($w (* $funion (* $c1 $c2)))
              ($fj (sn kdiv (* $f1 $f2) $funion))
              ($aj (sn ajac (sn marginal $p) (sn marginal $x)))
              ($tree (sh (tag P d so ()) "<->" (args ((arg s $p) (arg o $x))))))
         (stmt (sn weak-quantum-d! $tree (cmp $s1 $s2) $w $fj $aj similarity $s1 $s2) $tree))
       (empty)))

;; analogy (SLN 3.7 ruling; 9.8.3 names the exact pipeline): inh(S->M) +
;; sim(M<->P) |- inh(S->P) = discount(omega_inh, b_sim), grafted strong
;; with stamps. Two clauses cover the sim statement's slot orders.
(= (|- (stmt $s1 (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $m)))))
       (stmt $s2 (sh (tag P d so ()) "<->" (args ((arg s $m) (arg o $p))))))
   (sn ana-fire $s1 $s2 $amr $cop $x $p))
(= (|- (stmt $s1 (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $m)))))
       (stmt $s2 (sh (tag P d so ()) "<->" (args ((arg s $p) (arg o $m))))))
   (sn ana-fire $s1 $s2 $amr $cop $x $p))
(= (sn ana-fire $s1 $s2 $amr $cop $x $p)
   (if (and (sn sim-rules?)
            (and (sn licensed? $amr $cop) (and (not (== $x $p)) (sn disjoint $s1 $s2))))
       (let* (((Opinion $b2 $d2 $u2 $a2) (sn view $s2))
              ($op (sn discount-op (sn view $s1) $b2))
              ($tree (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $p))))))
         (stmt (sn graft! $tree (ana $s1 $s2) $op instance $s1 $s2) $tree))
       (empty)))

;; resemblance (9.8.5): point f = J1*J2; the Jaccard metric's triangle
;; envelope [max(0,J1+J2-1), 1-|J1-J2|] floors honesty -- w shrinks by width
;; (Jaccard distance is a metric: Levandowsky & Winter, Nature 234, 1971)
(= (sn sim-chain $x1 $y1 $x2 $y2)
   (if (== $y1 $x2) (chain $x1 $y2)
       (if (== $y1 $y2) (chain $x1 $x2)
           (if (== $x1 $x2) (chain $y1 $y2)
               (if (== $x1 $y2) (chain $y1 $x2) NoChain)))))
(= (|- (stmt $s1 (sh (tag P d so ()) "<->" (args ((arg s $x1) (arg o $y1)))))
       (stmt $s2 (sh (tag P d so ()) "<->" (args ((arg s $x2) (arg o $y2))))))
   (if (and (sn sim-rules?) (sn disjoint $s1 $s2))
       (case (sn sim-chain $x1 $y1 $x2 $y2)
         (((chain $a $b)
           (if (and (not (== $a $b)) (sn_key_le (sn term-key $a) (sn term-key $b)))
               (let* ((($j1 $c1) (sn fc-of $s1))
                      (($j2 $c2) (sn fc-of $s2))
                      ($lo (max 0.0 (- (+ $j1 $j2) 1.0)))
                      ($hi (- 1.0 (abs-math (- $j1 $j2))))
                      ($width (max 0.0 (- $hi $lo)))
                      ($w (* (* $c1 $c2) (- 1.0 $width)))
                      ($aj (sn ajac (sn marginal $a) (sn marginal $b)))
                      ($tree (sh (tag P d so ()) "<->" (args ((arg s $a) (arg o $b))))))
                 (stmt (sn weak-quantum-d! $tree (res $s1 $s2) $w (* $j1 $j2) $aj similarity $s1 $s2) $tree))
               (empty)))
          ($other (empty))))
       (empty)))

;; sim2inh (9.8.3, exact set identity -- PLN's heuristic is the theorem):
;; P(P|S) = J(aS+aP)/((1+J)aS); both directions, confidence = the sim's
;; certainty, each direction its own proof node. ON-DEMAND op (convert!
;; precedent: question answering, never the forward sweep).
(= (sn sim2inh! $simsid)
   (match &self (sn stmt $simsid (sh (tag P d so ()) "<->" (args ((arg s $x) (arg o $y)))))
     (superpose ((sn s2i-dir! $simsid $x $y) (sn s2i-dir! $simsid $y $x)))))
(= (sn s2i-dir! $simsid $s $p)
   (let* (((Opinion $b $d $u $a) (sn view $simsid))
          ($j (+ $b (* $a $u)))
          ($as (sn aclamp (sn marginal $s)))
          ($ap (sn marginal $p))
          ($fi (sn clamp (sn kdiv (* $j (+ $as $ap)) (* (+ 1.0 $j) $as)) 0.0 1.0))
          ($c (- 1.0 $u))
          ($tree (sh (tag P d so ()) "is" (args ((arg s $s) (arg o $p))))))
     (sn weak-quantum! $tree (s2i $simsid $s) $c $fi $ap $simsid $simsid)))

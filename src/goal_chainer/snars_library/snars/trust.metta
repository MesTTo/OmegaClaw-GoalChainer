;;; SNARS module — split from the snars.metta monolith (2026-06-12).
;;; Import via the snars.metta aggregator; load order lives there.

;; ---- trust ledger (v2 P1): rule + source reliability as Beta evidence ----
;; Confirmation: q = 1 - |y - P| = Pr[Bernoulli(P) = y], the expected 0-1 match
;; -- the Beta Reputation update (Josang & Ismail 2002), receipts as stamps.
;; Conflict: DC = PD*CC = |Phat - y| * chat * c_unit is Josang's exact degree of
;; conflict (J 4.61-4.63). The REVISION s_sigma += DC * u_t(sigma) is JIM-2015
;; INSPIRED, not the exact operator: JIM apportions blame between two sources via
;; relative uncertainty UD = (u1-u2)/(u1+u2) and factors (1+-UD)/2; we use a
;; single-source form -- blame the contested source by its OWN trust-uncertainty
;; (a new source u_t=1 absorbs full DC, an established one little). Same
;; qualitative law ("most-unestablished revised most"), simpler arithmetic.
;; Source trust applies as ratio rho = P(cell)/a (prior => rho = 1, INV-1): a
;; LEARNED multiplicative correction to the caller's structural trust (centred at
;; 1), composed as evidence-scaling (EBSL form) -- not a literal J 14.6 read.
(= (sn internal-sigma? $sigma)
   (case $sigma (("derived" True) ("weak" True) ("prior" True)
                 ("structural" True) ("goal" True) ("eternal" True)
                 ($other False))))

;; ---- the rule/trust key of a statement tree (2.5, 3.0d) ----
;; ONE clause, case-dispatched: exclusive and total by construction. A naive
;; appended catch-all clause would SUPERPOSE with the specific clauses (all
;; matching clauses fire) -- (sn rule-p ...) would return two keys per so-tree
;; and sn score-rule! would double-fire sn_tr_add on the Beta ledger. The
;; case generalizes `so` to any role string, so claim wrappers (sr), unary
;; statements (s) and Wave-B tuples (sio...) key by sense/label too. Non-SH
;; trees (e.g. (sn-ref ...) fillers) share the documented fallback key
;; `unkeyed`: one conservative pooled ledger row, never a prune.
(= (sn pred-key $tree)
   (case $tree
     (((sh (tag P $sub $roles (amr $aid)) $lbl $args) $aid)
      ((sh (tag P $sub $roles ()) $lbl $args) $lbl)
      ((sh-conn $conn $args) (sn pred-key $conn))
      ((sh-atom (tag $t $st $ro (amr $aid)) $lbl) $aid)
      ((sh-atom $tag $lbl) $lbl)
      ($other unkeyed))))

(= (sn proof-op (ded $a $b)) ded)
(= (sn proof-op (abd $a $b)) abd)
(= (sn proof-op (ind $a $b)) ind)
(= (sn proof-op (exe $a $b)) exe)
(= (sn proof-op (cnv $a)) cnv)
(= (sn proof-op (sym $a)) sym)
(= (sn proof-op (cmp $a $b)) cmp)
(= (sn proof-op (ana $a $b)) ana)
(= (sn proof-op (res $a $b)) res)
(= (sn proof-op (s2i $a $b)) s2i)
(= (sn proof-op (mp $a $b)) mp)
(= (sn proof-op (mpa $a $b)) mpa)
(= (sn proof-op (hs $a $b)) hs)
(= (sn proof-op (ord $a $b)) ord)
(= (sn proof-op (tab $a $b)) tab)
(= (sn proof-op (spc $a)) spc)
(= (sn proof-op (gnr $a $b $r)) gnr)
(= (sn proof-op (spz $a $b $r)) spz)
;; registry rules key their trust cell per RULE NAME (R5): the ledger learns
;; each registered rule's reliability exactly as it does the built-ins'.
(= (sn proof-op (rw $name $a $b)) (rw $name))

;; rule cells: prior a = 1.0 => identity discount until evidence arrives
(= (sn rule-p $op $tree) (sn_tr_p $op (sn pred-key $tree) 1.0))

;; K2: Thompson draw from a rule's reliability Beta instead of its mean --
;; principled exploration over rules (the 9.7 governance posture). The trust
;; prior is 1.0 (rules start trusted; J 3.7 alpha=r+Wa, beta=s+W(1-a), W=2), so
;; a fresh rule samples ~1.0 and exploration grows only as misfires accrue.
(= (sn rule-sample $op $tree)
   (let ($r $s) (sn_tr_rs $op (sn pred-key $tree))
     (py-call (goalchainer_snars.snars_beta_sample (+ $r 2.0) $s))))

(= (sn tstamp! $kind $k1 $k2 $sid)
   (if (== () (collapse (once (match &self (sn tstamp $kind $k1 $k2 $sid) True))))
       (let $added (add-atom &self (sn tstamp $kind $k1 $k2 $sid)) True)
       False))

;; binary outcome of a direct unit; fractional units are not scored in v2
(= (sn unit-y $r $s)
   (if (and (> $r 0.0) (== $s 0.0)) 1.0
       (if (and (== $r 0.0) (> $s 0.0)) 0.0 none)))

(= (sn score-rule! $sid $q)
   (collapse (match &self (, (sn proof $sid $prf) (sn stmt $sid $tree))
     (let* (($op (sn proof-op $prf))
            ($pk (sn pred-key $tree)))
       (if (sn tstamp! conf $op $pk $sid)
           (sn_tr_add $op $pk $q (- 1.0 $q))
           ())))))

;; touch a statement's concept keys (goal seeding, conflict heat)
(= (sn seed-keys! $tree $w)
   (case $tree
     (((sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $y))))
       (let* (($k1 (sn act-touch! (sn term-key $x) $w))
              ($k2 (sn act-touch! (sn term-key $y) $w)))
         True))
      ($other True))))

(= (sn score-conflict! $sid $sigma $dc)
   (if (sn tstamp! dcx src $sigma $sid)
       (let* (($u (sn_tr_u src $sigma))
              ($rev (sn_tr_add src $sigma 0.0 (* $dc $u)))
              ($hot (collapse (match &self (sn stmt $sid $tree) (sn seed-keys! $tree $dc)))))
         $rev)
       ()))

;; step-5 hook (Mapping 3.1): score the pre-fuse prediction, then fuse.
;; The trust-floor skips near-vacuous predictions (nothing to judge a source by);
;; the dc-threshold fires source-trust revision only on a REAL conflict, not the
;; minor gap between a binary outcome and a continuous P-hat (without it, every
;; correct-but-imperfect prediction would slowly bleed source trust).
(= (sn score! $sid $r $s $sigma)
   (if (sn internal-sigma? $sigma) ()
       (let $y (sn unit-y $r $s)
         (if (== $y none) ()
             (let* (((Ev $rr $ss $ar) (sn evidence $sid))
                    ($w (+ $rr $ss))
                    ($chat (/ $w (+ $w 2.0))))
               (if (< $chat (sn config trust-floor-c)) ()
                   (let* (($phat (sn expect $sid))
                          ($q (- 1.0 (abs-math (- $y $phat))))
                          ($cu (/ (+ $r $s) (+ (+ $r $s) 2.0)))
                          ($dc (* (* (abs-math (- $phat $y)) $chat) $cu))
                          ($scored (sn score-rule! $sid $q))
                          ($conflicted (if (> $dc (sn config dc-threshold))
                                           (sn score-conflict! $sid $sigma $dc)
                                           ())))
                     ())))))))

(: (sn input) (-> %Undefined% Number Number Number %Undefined% Number %Undefined%))
(= (sn input $sid $r $s $a $sigma $p)
   (if (sn frozen?)
       (sn_ev_add_src $sid $sigma $r $s $a $p)
       (let* (($scored (sn score! $sid $r $s $sigma))
              ($rho (sn_tr_rho src $sigma (sn config trust-prior-src)))
              ($pe (sn clamp (* $p $rho) 0.0 1.0)))
         (sn_ev_add_src $sid $sigma $r $s $a $pe))))

;; M1 prequential hook (v2 P2): read the pre-fuse prediction, emit the outcome
;; record, THEN fuse the held-out unit. Prediction is scored before it sees its
;; own outcome (Dawid prequential discipline). Derived? = has a proof, no receipt.
(= (sn outcome! $sid $r $s $a $sigma $p)
   (let* (($y (sn unit-y $r $s))
          ((Ev $rr $ss $ar) (sn evidence $sid))
          ($w (+ $rr $ss))
          ($phat (sn expect $sid))
          ($chat (/ $w (+ $w 2.0)))
          ($derived (if (== () (collapse (once (match &self (sn proof $sid $pf) True)))) 0 1))
          ($fused (sn input $sid $r $s $a $sigma $p)))
     (OUTCOME $sid $phat $chat $y $sigma $derived)))

(= (sn stamp! $sid $h)
   (if (== () (collapse (once (match &self (sn stamp $sid $h) True))))
       (let $added (add-atom &self (sn stamp $sid $h))
         True)
       False))

(= (sn receipt! $sid $sigma $h)
   (with_mutex sn-commit
     (if (== () (collapse (once (match &self (sn receipt $sid $sigma $h) True))))
         (let* (($added (add-atom &self (sn receipt $sid $sigma $h)))
                ($stamped (sn stamp! $sid $h)))
           True)
         False)))

(= (sn occ! $sid $occ)
   (with_mutex sn-commit
     (if (== () (collapse (once (match &self (sn occ $sid $occ) True))))
         (let $added (add-atom &self (sn occ $sid $occ))
           True)
         False)))


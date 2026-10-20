;;; SNARS module — split from the snars.metta monolith (2026-06-12).
;;; Import via the snars.metta aggregator; load order lives there.

;; ---- opinion views (J 3.11, k=W=2) ----
(: (sn evidence) (-> %Undefined% %Undefined%))
(= (sn evidence $sid)
   (sn_ev_view $sid))

;; E1: the KL surprise stored at the last fuse (curriculum weight, 3.1 step 5);
;; unseen statements read 0.0 (the kernel reader's default).
(: (sn surprise) (-> %Undefined% Number))
(= (sn surprise $sid) (sn_surprise $sid))

(: (sn opinion) (-> %Undefined% %Undefined%))
(= (sn opinion $sid)
   (sn ev-op (sn evidence $sid)))

;; an evidence triple's opinion at W = 2: a statement's cell reads through it, and so
;; does evidence a caller only supposes, such as an obligation's hypothesis
(= (sn ev-op (Ev $r $s $a))
   (let $t (+ (+ $r $s) 2.0)
     (Opinion (/ $r $t) (/ $s $t) (max (sn config u-min) (/ 2.0 $t)) $a)))

(= (sn project (Opinion $b $d $u $a)) (+ $b (* $a $u)))

(: (sn expect) (-> %Undefined% Number))
(= (sn expect $sid) (sn project (sn opinion $sid)))

(: (sn above) (-> %Undefined% Number Bool))
(= (sn above $sid $t) (> (sn expect $sid) $t))

;; a condition at threshold theta, cut once on the opinion's probability interval
;; [b, b + u], its Dempster-Shafer belief and plausibility as computed: Holds when
;; even the worst case b clears theta, Fails when even the best case b + u falls
;; short, and Undecided between. u >= 0 and floating addition is monotone, so
;; b + u >= b exactly as computed and Holds and Fails exclude each other for every
;; theta and every branch order. The simplex form 1 - d does not: an opinion the
;; simplex tolerance accepts, b 0.5000000000001, d 0.5, u 0, has b > 1 - d, and at
;; theta 0.50000000000005 both of its cuts would hold. The base rate only places
;; the expectation inside the interval, so it never decides: (Opinion 0 0 1 a) is
;; Undecided for every a, where an expectation cut would let a = 0.9 clear 0.6.
(= (sn condition (Opinion $b $d $u $a) $theta)
   (if (> $b $theta)
       Holds
       (if (< (+ $b $u) $theta) Fails Undecided)))

;; a statement as a literal: pos reads its view, neg reads (Not S), the complement
;; (d, b, u, 1 - a), whose interval is [d, d + u], so one cut serves both
(= (sn literal-view $sid pos) (sn view $sid))
(= (sn literal-view $sid neg) (sn complement (sn view $sid)))

;; a literal's condition: support is premise eligibility, so only a statement with
;; a receipt or a proof can hold or fail, either way round, and evidence fused
;; without one, as outcome! fuses it, decides nothing
(= (sn condition-of $sid $polarity $theta)
   (if (sn supported? $sid) (sn condition (sn literal-view $sid $polarity) $theta) Undecided))

(= (sn op-to-ev (Opinion $b $d $u $a))
   (Ev (/ (* 2.0 $b) $u) (/ (* 2.0 $d) $u) $a))

;; complement (SLN 3.2, exact): swap belief and disbelief, mirror the base rate
(= (sn complement (Opinion $b $d $u $a))
   (Opinion $d $b $u (- 1.0 $a)))

;; the read-time view (SLN 9.4): epistemic statements u-maximise at read
(: (sn view) (-> %Undefined% %Undefined%))
(= (sn view $sid)
   (if (== () (collapse (match &self (sn kind $sid epistemic) True)))
       (sn opinion $sid)
       (sn umax (sn opinion $sid))))

;; degree of conflict on current views (SLN 3.7 / J 4.63): |dP| * c1 * c2
(: (sn dc) (-> %Undefined% %Undefined% Number))
(= (sn dc $s1 $s2)
   (let* (((Opinion $b1 $d1 $u1 $a1) (sn view $s1))
          ((Opinion $b2 $d2 $u2 $a2) (sn view $s2))
          ($p1 (+ $b1 (* $a1 $u1)))
          ($p2 (+ $b2 (* $a2 $u2))))
     (* (abs-math (- $p1 $p2)) (* (- 1.0 $u1) (- 1.0 $u2)))))

;; binomial multiplication (J 7.1): premise conjunction for multi-premise rules
(= (sn and-op (Opinion $b1 $d1 $u1 $a1) (Opinion $b2 $d2 $u2 $a2))
   (let* (($den (- 1.0 (* $a1 $a2)))
          ($b (+ (* $b1 $b2) (sn kdiv (+ (* (* (- 1.0 $a1) $a2) (* $b1 $u2)) (* (* $a1 (- 1.0 $a2)) (* $u1 $b2))) $den)))
          ($d (- (+ $d1 $d2) (* $d1 $d2)))
          ($u (+ (* $u1 $u2) (sn kdiv (+ (* (- 1.0 $a2) (* $b1 $u2)) (* (- 1.0 $a1) (* $u1 $b2))) $den)))
          ($a (* $a1 $a2)))
     (Opinion $b $d $u $a)))

;; binomial comultiplication (J 7.3): the exact De Morgan dual of and-op
;; (b<->d, a<->1-a). Clausal disjunction; SLN 3.6 ruling uses this for (||).
(= (sn or-op (Opinion $b1 $d1 $u1 $a1) (Opinion $b2 $d2 $u2 $a2))
   (let* (($den (- (+ $a1 $a2) (* $a1 $a2)))
          ($b (- (+ $b1 $b2) (* $b1 $b2)))
          ($d (+ (* $d1 $d2) (sn kdiv (+ (* (* $a1 (- 1.0 $a2)) (* $d1 $u2)) (* (* (- 1.0 $a1) $a2) (* $u1 $d2))) $den)))
          ($u (+ (* $u1 $u2) (sn kdiv (+ (* $a2 (* $d1 $u2)) (* $a1 (* $u1 $d2))) $den)))
          ($a $den))
     (Opinion $b $d $u $a)))

;; binomial division (J 7.12 / Def 7.3): un-AND. Recover ox from prod=and(ox,oy)
;; and oy. A constraint breach (J 7.13) is FR1-grade signal, not an error --
;; returns (Inconsistent <which-bound>), a registered data head (SLN 9.8.6).
(= (sn div-op (Opinion $bx $dx $ux $ax) (Opinion $by $dy $uy $ay))
   (if (not (< $ax $ay))
       (Inconsistent a-order)
       (if (< $dx $dy)
           (Inconsistent d-order)
           (let* (($adiff (- $ay $ax))
                  ($bbound (sn kdiv (* (* (* $ax (- 1.0 $ay)) (- 1.0 $dx)) $by) (* (* (- 1.0 $ax) $ay) (- 1.0 $dy))))
                  ($ubound (sn kdiv (* (* (- 1.0 $ay) (- 1.0 $dx)) $uy) (* (- 1.0 $ax) (- 1.0 $dy)))))
             (if (< $bx $bbound)
                 (Inconsistent b-bound)
                 (if (< $ux $ubound)
                     (Inconsistent u-bound)
                     (let* (($t1 (sn kdiv (* $ay (+ $bx (* $ax $ux))) (* $adiff (+ $by (* $ay $uy)))))
                            ($t2 (sn kdiv (* $ay (- 1.0 $dx)) (* $adiff (- 1.0 $dy))))
                            ($t3 (sn kdiv (* $ax (- 1.0 $dx)) (* $adiff (- 1.0 $dy))))
                            ($b (- $t1 $t3))
                            ($d (sn kdiv (- $dx $dy) (- 1.0 $dy)))
                            ($u (- $t2 $t1))
                            ($a (sn kdiv $ax $ay)))
                       (Opinion $b $d $u $a))))))))

;; binomial codivision (J 7.15 / Def 7.4): un-OR, the dual of div-op. Recover
;; ox from coprod=or(ox,oy) and oy; J 7.16 breach -> (Inconsistent <bound>).
(= (sn codiv-op (Opinion $bx $dx $ux $ax) (Opinion $by $dy $uy $ay))
   (if (not (> $ax $ay))
       (Inconsistent a-order)
       (if (< $bx $by)
           (Inconsistent b-order)
           (let* (($adiff (- $ax $ay))
                  ($dbound (sn kdiv (* (* (* (- 1.0 $ax) $ay) (- 1.0 $bx)) $dy) (* (* $ax (- 1.0 $ay)) (- 1.0 $by))))
                  ($ubound (sn kdiv (* (* $ay (- 1.0 $bx)) $uy) (* $ax (- 1.0 $by)))))
             (if (< $dx $dbound)
                 (Inconsistent d-bound)
                 (if (< $ux $ubound)
                     (Inconsistent u-bound)
                     (let* (($t1 (sn kdiv (* (- 1.0 $ay) (+ $dx (* (- 1.0 $ax) $ux))) (* $adiff (+ $dy (* (- 1.0 $ay) $uy)))))
                            ($t2 (sn kdiv (* (- 1.0 $ay) (- 1.0 $bx)) (* $adiff (- 1.0 $by))))
                            ($t3 (sn kdiv (* (- 1.0 $ax) (- 1.0 $bx)) (* $adiff (- 1.0 $by))))
                            ($b (sn kdiv (- $bx $by) (- 1.0 $by)))
                            ($d (- $t1 $t3))
                            ($u (- $t2 $t1))
                            ($a (sn kdiv $adiff (- 1.0 $ay))))
                       (Opinion $b $d $u $a))))))))

;; read-time disjunction composition (R4): the OR of two statements' views,
;; computed on demand (the sentence stored ONE opinion; this composes members)
(= (sn or-view $s1 $s2) (sn or-op (sn view $s1) (sn view $s2)))

;; value-level modus ponens: antecedent through a conditional, else synthesized (SLN 3.4/8.4)
(= (sn mp-op (Opinion $xb $xd $xu $xa) (Opinion $rb $rd $ru $ra))
   (let* (($ayc (sn aclamp $ra))
          ($pos (Opinion $rb $rd $ru $ayc))
          ($neg (sn synth-else $pos (sn aclamp $xa) $ayc)))
     (sn deduce-op (Opinion $xb $xd $xu $xa) $pos $neg)))

;; theoretical max uncertainty at fixed projection (J 10.13)
(= (sn max-u $p $a)
   (let $ac (sn aclamp $a)
     (if (< $p $ac) (/ $p $ac) (sn kdiv (- 1.0 $p) (- 1.0 $ac)))))

;; subjective Bayes inversion (J Def 10.4; SLN 3.5 four-step): invert the
;; conditional pair (pos, neg over Y given X; a slot of pos = a_Y) at the
;; antecedent base rate ax. Returns (Conds posInv negInv) over X given Y,
;; a = ax. Stable under repeated inversion on projections (J 10.28).
(= (sn invert-op (Opinion $pb $pd $pu $pa) (Opinion $nb $nd $nu $na) $ax)
   (let* (($ay (sn aclamp $pa))
          ($pyx (+ $pb (* $ay $pu)))
          ($pyxn (+ $nb (* $ay $nu)))
          ($axc (sn aclamp $ax))
          ($pxy (sn kdiv (* $axc $pyx) (+ (* $axc $pyx) (* (- 1.0 $axc) $pyxn))))
          ($pxyn (sn kdiv (* $axc (- 1.0 $pyx)) (+ (* $axc (- 1.0 $pyx)) (* (- 1.0 $axc) (- 1.0 $pyxn)))))
          ($us (+ $pu $nu))
          ;; NB: one logic variable per NAME per clause (no let shadowing in
          ;; the Prolog translation) -- sibling bindings need distinct names
          ($uup (let $up (sn max-u $pyx $ay) (if (> $up 0.0) (* (sn kdiv $pu $us) (/ $pu $up)) 0.0)))
          ($uwn (let $un (sn max-u $pyxn $ay) (if (> $un 0.0) (* (sn kdiv $nu $us) (/ $nu $un)) 0.0)))
          ($uw (+ $uup $uwn))
          ($irr (- 1.0 (abs-math (- $pyx $pyxn))))
          ($relu (- (+ $uw $irr) (* $uw $irr)))
          ($u1 (sn clamp (* (sn max-u $pxy $axc) $relu) (sn config u-min) 1.0))
          ($u2 (sn clamp (* (sn max-u $pxyn $axc) $relu) (sn config u-min) 1.0))
          ($ipos (Opinion (max 0.0 (- $pxy (* $axc $u1)))
                          (max 0.0 (- (- 1.0 $pxy) (* (- 1.0 $axc) $u1))) $u1 $ax))
          ($ineg (Opinion (max 0.0 (- $pxyn (* $axc $u2)))
                          (max 0.0 (- (- 1.0 $pxyn) (* (- 1.0 $axc) $u2))) $u2 $ax)))
     (Conds $ipos $ineg)))

;; abduction (J Def 10.5) = invert then deduce: the consequent's opinion
;; through the INVERTED conditionals, concluding on the antecedent
(= (sn abduce-op $oy $pos $neg $ax)
   (let (Conds $ipos $ineg) (sn invert-op $pos $neg $ax)
     (sn deduce-op $oy $ipos $ineg)))

;; trust/decay discounting (J 14.6): frequency preserved, certainty scaled
(= (sn discount-op (Opinion $b $d $u $a) $p)
   (Opinion (* $p $b) (* $p $d) (- 1.0 (* $p (+ $b $d))) $a))

;; temporal projection = discount by lambda^dt (SLN 9.3, Truth_Projection twin)
(= (sn project-op $o $lambda $dt)
   (sn discount-op $o (pow-math $lambda $dt)))

;; read-time projected view of an event statement
(= (sn project-view $sid $lambda $dt)
   (sn discount-op (sn view $sid) (pow-math $lambda $dt)))

;; value-level cumulative fusion (J 12.12): evidence addition on opinion views
(= (sn fuse-op $o1 $o2)
   (let* (((Ev $r1 $s1 $a1) (sn op-to-ev $o1))
          ((Ev $r2 $s2 $a2) (sn op-to-ev $o2))
          ($t (+ (+ (+ $r1 $r2) (+ $s1 $s2)) 2.0)))
     (Opinion (/ (+ $r1 $r2) $t)
              (/ (+ $s1 $s2) $t)
              (max (sn config u-min) (/ 2.0 $t))
              $a1)))

;; ---- pure truth math (transliterated from SLN section 7) ----
(= (sn clamp $x $lo $hi) (min $hi (max $lo $x)))
(= (sn aclamp $x) (sn clamp $x (sn config a-clamp) (- 1.0 (sn config a-clamp))))

;; uncertainty maximisation (J 3.25-3.27); p uses the unclamped a, u-bounds the clamped one
(= (sn umax (Opinion $b $d $u $a))
   (let* (($ac (sn aclamp $a))
          ($p (+ $b (* $a $u)))
          ($uu (min-atom ((/ $p $ac) (/ (- 1.0 $p) (- 1.0 $ac)) 1.0)))
          ($bb (max 0.0 (- $p (* $ac $uu))))
          ($dd (max 0.0 (- (- 1.0 $p) (* (- 1.0 $ac) $uu)))))
     (Opinion $bb $dd $uu $a)))

;; marginal else-synthesis (SLN 8.4): omega_{y|not-x} from the edge and live marginals
(= (sn synth-else (Opinion $eb $ed $eu $ea) $ax $ay)
   (let* (($q (+ $eb (* $ea $eu)))
          ($pbar (min 1.0 (max 0.0 (/ (- $ay (* $ax $q)) (- 1.0 $ax))))))
     (sn umax (Opinion $pbar (- 1.0 $pbar) 0.0 $ay))))

(= (sn kdiv $n $d)
   (if (< (abs-math $d) (sn config k-eps)) 0.0 (/ $n $d)))

;; Jaccard prior under independence (SLN 9.8.1): a_J = aS*aP/(aS+aP-aS*aP)
(= (sn ajac $as $ap)
   (sn kdiv (* $as $ap) (- (+ $as $ap) (* $as $ap))))

;; K-correction case analysis (J 9.42-9.50)
(= (sn kcorr $bi $di $pyx (Opinion $xb $xd $xu $ax) (Opinion $pb $pd $pu $pa) (Opinion $nb $nd $nu $na))
   (let* (($gb (> $pb $nb))
          ($gd (> $pd $nd)))
     (if (== $gb $gd)
         0.0
         (let* (($ay $pa)
                ($px (+ $xb (* $ax $xu)))
                ($bp (max (sn config k-eps) (+ $xb (* $ax $xu))))
                ($dp (max (sn config k-eps) (+ $xd (* (- 1.0 $ax) $xu))))
                ($k (if $gb
                        (if (<= $pyx (+ $nb (* $ay (- 1.0 (+ $nb $pd)))))
                            (if (<= $px $ax)
                                (sn kdiv (* (* $ax $xu) (- $bi $nb)) (* $bp $ay))
                                (sn kdiv (* (* (* $ax $xu) (- $di $pd)) (- $pb $nb)) (* (* $dp $ay) (- $nd $pd))))
                            (if (<= $px $ax)
                                (sn kdiv (* (* (* (- 1.0 $ax) $xu) (- $bi $nb)) (- $nd $pd)) (* (* $bp (- 1.0 $ay)) (- $pb $nb)))
                                (sn kdiv (* (* (- 1.0 $ax) $xu) (- $di $pd)) (* $dp (- 1.0 $ay)))))
                        (if (<= $pyx (+ $pb (* $ay (- 1.0 (+ $pb $nd)))))
                            (if (<= $px $ax)
                                (sn kdiv (* (* (* (- 1.0 $ax) $xu) (- $di $nd)) (- $nb $pb)) (* (* $bp $ay) (- $pd $nd)))
                                (sn kdiv (* (* (- 1.0 $ax) $xu) (- $bi $pb)) (* $dp $ay)))
                            (if (<= $px $ax)
                                (sn kdiv (* (* $ax $xu) (- $di $nd)) (* $bp (- 1.0 $ay)))
                                (sn kdiv (* (* (* $ax $xu) (- $bi $pb)) (- $pd $nd)) (* (* $dp (- 1.0 $ay)) (- $nb $pb))))))))
           (max 0.0 $k)))))

;; stage-I interpolation (J 9.41) + K-correction
(= (sn deduce-op (Opinion $xb $xd $xu $ax) (Opinion $pb $pd $pu $pa) (Opinion $nb $nd $nu $na))
   (let* (($ay $pa)
          ($bi (+ (+ (* $xb $pb) (* $xd $nb)) (* $xu (+ (* $pb $ax) (* $nb (- 1.0 $ax))))))
          ($di (+ (+ (* $xb $pd) (* $xd $nd)) (* $xu (+ (* $pd $ax) (* $nd (- 1.0 $ax))))))
          ($ui (+ (+ (* $xb $pu) (* $xd $nu)) (* $xu (+ (* $pu $ax) (* $nu (- 1.0 $ax))))))
          ($pyx (+ (+ (* $pb $ax) (* $nb (- 1.0 $ax))) (* $ay (+ (* $pu $ax) (* $nu (- 1.0 $ax))))))
          ($k (sn kcorr $bi $di $pyx (Opinion $xb $xd $xu $ax) (Opinion $pb $pd $pu $pa) (Opinion $nb $nd $nu $na))))
     (Opinion (- $bi (* $ay $k))
              (- $di (* (- 1.0 $ay) $k))
              (max (sn config u-min) (+ $ui $k))
              $ay)))

(: (sn deduce) (-> %Undefined% %Undefined% Number %Undefined%))
(= (sn deduce $sx $se $ay)
   (let* (($ayc (sn aclamp $ay))
          ((Opinion $xb $xd $xu $xa) (sn opinion $sx))
          ((Opinion $eb $ed $eu $ea) (sn opinion $se))
          ($pos (Opinion $eb $ed $eu $ayc))
          ($neg (sn synth-else $pos (sn aclamp $xa) $ayc)))
     (sn deduce-op (Opinion $xb $xd $xu $xa) $pos $neg)))


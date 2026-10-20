;;; SNARS module — split from the snars.metta monolith (2026-06-12).
;;; Import via the snars.metta aggregator; load order lives there.

;; ---- option-group parsing (:key value ... flat keywords in one group) ----
;; legacy flat readers -- normalized paths use opt-c/opt2-c/opt?-c over
;; (sn opts-norm ...) clauses (format v2 F5); these stay for external callers
(: (sn opt) (-> Atom %Undefined% %Undefined% %Undefined%))
(= (sn opt $opts $key $default)
   (if (== $opts ())
       $default
       (let ($head $tail) (decons-atom $opts)
         (if (== $head $key)
             (car-atom $tail)
             (sn opt $tail $key $default)))))

(: (sn opt2) (-> Atom %Undefined% Atom Expression))
(= (sn opt2 $opts $key $defaults)
   (if (== $opts ())
       $defaults
       (let ($head $tail) (decons-atom $opts)
         (if (== $head $key)
             (let ($v1 $rest) (decons-atom $tail)
               ($v1 (car-atom $rest)))
             (sn opt2 $tail $key $defaults)))))

(: (sn opt?) (-> Atom %Undefined% Bool))
(= (sn opt? $opts $key)
   (if (== $opts ())
       False
       (let ($head $tail) (decons-atom $opts)
         (if (== $head $key)
             True
             (sn opt? $tail $key)))))

;; ---- authoring ----
(= (sn claimify-agent! $sid $agent)
   (let* (($ctree (sh (tag P d sr ()) "claim" (args ((arg s $agent) (arg r (sn-ref $sid))))))
          ($csid (sn sid $ctree)))
     (with_mutex sn-commit
       (if (sn intern! $csid $ctree occasion epistemic)
           (let* (($port (add-atom &self (sn port $csid object)))
                  ($that (add-atom &self (sn that $csid $sid)))
                  ($index (add-atom &self (sn claim $sid $agent))))
             $csid)
           $csid))))

(= (sn claimify! $sid $sigma)
   (sn claimify-agent! $sid (sh-atom (tag C p NoRoles ()) $sigma)))

(= (sn pl-canon (Peeled $canon $neg $mood)) $canon)
(= (sn pl-neg (Peeled $canon $neg $mood)) $neg)
(= (sn pl-mood (Peeled $canon $neg $mood)) $mood)

;; SH full-form capture (prerelease ruling: nothing the parse emits is lost).
;; The canonical (sn stmt ...) is the voice/mood-normalized proposition the
;; reasoner chains over; the complete original tree rides alongside as
;; (sn sh ...) and the speech-act mood the canonical flattens away as
;; (sn mood ...), so SNARS can route on the full SH notation (Pi -> query,
;; Pj -> goal, Pe -> existential) even where reasoning uses the proposition.
(= (sn capture-sh! $sid $tree $mood)
   (with_mutex sn-commit
     (let* (($s (if (== () (collapse (once (match &self (sn sh $sid $t) True))))
                    (add-atom &self (sn sh $sid $tree))
                    ()))
            ($m (if (or (sn mood-default? $mood)
                        (not (== () (collapse (once (match &self (sn mood $sid $mo) True))))))
                    ()
                    (add-atom &self (sn mood $sid $mood)))))
       $sid)))

(: believe! (-> %Undefined% Atom %Undefined%))
(= (believe! $tree $opts)
   (let* (($pn (sn peel $tree))
          ($canon (sn pl-canon $pn))
          ($neg (sn pl-neg $pn))
          ($sid (sn sid $canon))
          ;; F5: ONE normalizer -- grouped clauses pass through, flat :keys
          ;; become clauses; every read below is over normalized clauses
          ($cls (sn opts-norm $opts))
          (($r0 $s0) (sn opt2-c $cls evidence (1.0 0.0)))
          ;; 2.4: quantifier splits the unit BEFORE negation routing --
          ;; "no" is itself a polarity-carrying frequency, Mn composes on top
          ($qw (sn opt-c $cls quant NoQuant))
          (($rq $sq) (sn fq-split $qw $r0 $s0))
          ($r (if $neg $sq $rq))
          ($s (if $neg $rq $sq))
          ($a (sn opt-c $cls rate (sn config default-rate)))
          ($sigma (sn opt-c $cls source "self"))
          ;; 2.4: hedges scale the evidence weight p, never the frequency;
          ;; quantifier-split x hedge x trust compose multiplicatively in p
          ($hedge (sn opt-c $cls hedge NoHedge))
          ($trust0 (sn opt-c $cls trust (sn config default-trust)))
          ($trust (* $trust0 (sn hedge-p $hedge)))
          ;; B1: routed default (tuple/occasion/instance); explicit option wins
          ($domain (sn opt-c $cls domain (sn domain-of $canon)))
          ($kind (sn opt-c $cls kind aleatory))
          ($occ (sn opt-c $cls occ NoOcc))
          ;; C1: temporal-cells mode routes an occ-carrying unit into the EVENT
          ;; cell keyed (Event canon occ), and hashes the receipt over THAT sid,
          ;; so repeated same-source observations at different times are not
          ;; receipt-blocked. Default OFF => $cell = $sid, fuse bit-identical.
          ($cell (if (and (sn temporal-cells?) (not (== $occ NoOcc)))
                     (sn sid (Event $canon $occ))
                     $sid))
          ($h (sn rh $cell $sigma)))
     (with_mutex sn-commit
       (let* (($interned (sn intern! $sid $canon $domain $kind))
              ;; SH full-form capture: the complete authored tree + its mood
              ($shcap (sn capture-sh! $sid $tree (sn pl-mood $pn)))
              ;; F4: unconsumed clauses land verbatim in the open channel
              ($mres (sn meta-residue! $sid $sigma $cls))
              ;; M1 residue (F3): store the resolved quantifier, sigma-carrying
              ($qres (if (== $qw NoQuant) () (add-atom &self (sn q $sid $sigma $qw))))
              ($timed (if (== $occ NoOcc) False (sn occ! $sid $occ)))
              ($labeled (sn label-all! (sn labels $tree)))
              ($compounded (sn compound-edges! $canon))
              ;; B1: step-3 extraction (occ/ctx from role fillers; additive)
              ($extracted (sn extract-args! $sid (sn args-of $canon))))
         (if (sn receipt! $sid $sigma $h)
             ;; C2: grading keys on the statement sid, not the event cell --
             ;; predicted markers live on sids; event-cell forecasts are later
             ;; work. So route through fuse-unit! only when $cell == $sid.
             (let* (($fused (if (== $cell $sid)
                                (sn fuse-unit! $sid $r $s $a $sigma $trust)
                                (sn input $cell $r $s $a $sigma $trust)))
                    ($claimed (if (sn opt?-c $cls claim)
                                  (let* (($c (sn claimify! $sid $sigma))
                                         ;; F3: explicit :claim writes the attitude residue
                                         ($attc (add-atom &self (sn att $sid $sigma claim))))
                                    $c)
                                  False))
                    ;; 1.5 Mm: "will" marks a forecast the world will grade (C2)
                    ($forecast (if (== $hedge "will") (sn predicted! $sid) False))
                    ;; M1 residue (F3): store the resolved hedge, sigma-carrying
                    ($hres (if (== $hedge NoHedge) () (add-atom &self (sn hedged $sid $sigma $hedge))))
                    ($touched (sn fr-touch! $sid))
                    ;; E2: 9.7 push gate (flag-gated, quiet by default)
                    ($gated (sn gates! $sid))
                    ;; R0: symmetric-licensed predicates mirror (proof-deduped)
                    ($symd (collapse (sn sym-edges! $sid))))
               $sid)
             ;; E2: duplicate receipt is re-assertion -- average sigma's unit
             ;; (flag-gated; a no-op skip by default)
             (let* (($avg (sn reassert! $sid $r $s $a $sigma $trust))) $sid))))))

(= (sn proof-of $sid)
   (case (collapse (match &self (sn proof $sid $p) $p))
     ((() (ax $sid))
      ($ps (car-atom $ps)))))

;; queries canonicalize their patterns: surface spellings normalize to sense
;; atoms, so same-sense different-surface patterns match the world model; an
;; answer is a supported statement (intern.metta), observed or derived, never
;; an interned reference that asserts nothing
(: ask! (-> %Undefined% %Undefined%))
(= (ask! $pattern)
   (let $cp (sn pat $pattern)
     (match &self (sn stmt $sid $cp)
       (if (sn supported? $sid)
           (: (sn view $sid) (sn proof-of $sid) (stmt $sid $cp))
           (empty)))))

(: discover! (-> %Undefined% %Undefined%))
(= (discover! $pattern)
   (let $cp (sn pat $pattern)
     (match &self (sn stmt $sid $cp)
       (if (and (not (== () (collapse (once (match &self (sn proof $sid $p) True)))))
                (== () (collapse (once (match &self (sn receipt $sid $sig $h) True)))))
           (: (sn view $sid) (sn proof-of $sid) (stmt $sid $cp))
           (empty)))))

(: goal! (-> %Undefined% Atom %Undefined%))
(= (goal! $tree $opts)
   (let* (($pn (sn peel $tree))
          ($canon (sn pl-canon $pn))
          ($gsid (sn sid (Goal $canon)))
          ($cls (sn opts-norm $opts))
          ($d (sn opt-c $cls desire 0.5)))
     (with_mutex sn-commit
       (let* (($interned (if (== () (collapse (once (match &self (sn goal $gsid $canon) True))))
                             (let $added (add-atom &self (sn goal $gsid $canon))
                               True)
                             False))
              ($desired (sn input $gsid 0.0 0.0 $d "goal" 1.0))
              ($seeded (sn seed-keys! $canon $d)))
         $gsid))))

(: (sn desire) (-> %Undefined% Number))
(= (sn desire $gsid) (sn expect $gsid))

;; subgoals (R2; control, not truth -- SLN 3.9's caveat: desire is P(g), the
;; GoalDeduction max-trick stays NAL-side): walk =/> links into a registered
;; goal, register antecedent actions as subgoals at discounted desire
(= (sn subgoals! $gsid)
   (match &self (sn goal $gsid $gtree)
     (let $gs (sn sid $gtree)
       (match &self (sn stmt $e (sh (tag P d so ()) "=/>" (args ((arg s (sn-ref $act)) (arg o (sn-ref $gs))))))
         (let* (($p (sn expect $e))
                ($d (* $p (sn desire $gsid))))
           (if (> $d (sn config decision-threshold))
               (match &self (sn stmt $act $atree)
                 (goal! $atree ((desire $d))))
               (empty)))))))

(= (sn en $sid)
   (match &self (sn stmt $sid $tree) (hb en $tree)))

;; ---- R6: proof-kind-complete explanations ----
;; the premise sids of ANY proof term (1/2-premise rules, the role/name-
;; carrying 3-arg gnr/spz/rw, and ax which has none). Order matters: the
;; name/role-carrying heads are matched before the generic 2-premise pattern.
(= (sn proof-premises $prf)
   (case $prf
     (((ax $a) ())
      ((cnv $a) ($a))
      ((sym $a) ($a))
      ((spc $a) ($a))
      ((gnr $a $b $r) ($a $b))
      ((spz $a $b $r) ($a $b))
      ((rw $n $a $b) ($a $b))
      (($k $a $b) ($a $b))
      ($other ()))))

;; render each premise sid as (premise <english> <opinion>)
(= (sn render-prems $sids)
   (if (== $sids ())
       ()
       (let ($h $t) (decons-atom $sids)
         (cons-atom (premise (sn en $h) (sn opinion $h)) (sn render-prems $t)))))

;; F3 residue rendering: the testimony channel of a statement -- quantifier,
;; hedge, attitude, deixis, source -- filtered from the open meta-view, so an
;; explanation carries WHO asserted it and HOW, not just the proof.
(= (sn asserted-clause? $clause)
   (case $clause
     (((q $g $v) True)
      ((hedge $g $v) True)
      ((att $g $c) True)
      ((deixis $g $d) True)
      ((src $g) True)
      ($other False))))
(= (sn keep-asserted $clauses)
   (if (== $clauses ())
       ()
       (let ($h $t) (decons-atom $clauses)
         (if (sn asserted-clause? $h)
             (cons-atom $h (sn keep-asserted $t))
             (sn keep-asserted $t)))))
(= (sn asserted-residue $sid)
   (let $filtered (sn keep-asserted (sn meta-view $sid))
     (if (== $filtered ())
         ()
         (cons-atom because-asserted $filtered))))

;; why!: explain a believed statement -- DERIVED ones by each proof (rule kind +
;; premises with english/opinion), ASSERTED-only ones as axioms; both carry the
;; testimony residue when present. Output: (because <kind> <prem-list> <res|()>).
(: why! (-> %Undefined% %Undefined%))
(= (why! $pattern)
   (let $cp (sn pat $pattern)
     (match &self (sn stmt $sid $cp)
       (if (== () (collapse (once (match &self (sn proof $sid $p) True))))
           (because ax ((axiom (sn en $sid) (sn opinion $sid))) (sn asserted-residue $sid))
           (match &self (sn proof $sid $prf)
             (let $prems (sn proof-premises $prf)
               (because (sn proof-op $prf) (sn render-prems $prems) (sn asserted-residue $sid))))))))

(: why-not! (-> %Undefined% %Undefined%))
(= (why-not! $pattern)
   (let $cp (sn pat $pattern)
     (match &self (sn stmt $sid $cp)
       (let* (((Ev $r $s $a) (sn evidence $sid))
              ($res (sn asserted-residue $sid)))
         (if (> $s 0.0)
             (because-not (negative-evidence $s)
                          (sources (collapse (match &self (sn receipt $sid $sig $h) $sig)))
                          $res)
             (because-not (insufficient-support (sn view $sid)) $res))))))

;; ---- K6: proof-tree rendering (why-draw!) ----
;; the proof DAG as a nested (PfNode english kind (kids)) / (PfLeaf english)
;; structure for the Python renderer; depth-capped (proofs are DAGs, but a
;; cap bounds shared-node re-expansion). Reuses R6's proof-premises.
(= (sn proof-dag $sid) (sn proof-dag-d $sid 6))
(= (sn proof-dag-d $sid $depth)
   (if (< $depth 1)
       (PfLeaf (sn en $sid))
       (case (collapse (once (match &self (sn proof $sid $p) $p)))
         ((() (PfLeaf (sn en $sid)))
          (($prf) (PfNode (sn en $sid) (sn proof-op $prf)
                          (sn dag-kids (sn proof-premises $prf) (- $depth 1))))))))
(= (sn dag-kids $sids $depth)
   (if (== $sids ())
       ()
       (let ($h $t) (decons-atom $sids)
         (cons-atom (sn proof-dag-d $h $depth) (sn dag-kids $t $depth)))))

;; why-draw!: the human face of why! -- an indented proof tree per match
(: why-draw! (-> %Undefined% %Undefined%))
(= (why-draw! $pattern)
   (let $cp (sn pat $pattern)
     (match &self (sn stmt $sid $cp)
       (py-call (goalchainer_snars.snars_draw_tree (sn proof-dag $sid))))))


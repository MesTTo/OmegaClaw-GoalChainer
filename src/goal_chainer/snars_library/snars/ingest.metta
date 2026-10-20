;;; SNARS module — split from the snars.metta monolith (2026-06-12).
;;; Import via the snars.metta aggregator; load order lives there.

;; ---- ingestion (3.1 steps 0-6): the hb facts -> sn facts spine ----
(= (sn compounds $tree) (sread (py-call (goalchainer_snars.snars_compounds $tree))))

;; structural edges grow the taxonomy at intern time, before any assertion:
;; strong (r=9) but revisable, NEVER recursing into compound extraction
(= (sn structural! $compound $head)
   (let* (($ctree (sh (tag P d so ()) "is" (args ((arg s $compound) (arg o $head)))))
          ($sid (sn sid $ctree))
          ($h (sn rh $sid "structural")))
     (with_mutex sn-commit
       (let $interned (sn intern! $sid $ctree instance structural)
         (if (sn receipt! $sid "structural" $h)
             (let $fused (sn input $sid (sn config structural-r) 0.0 (sn config structural-a) "structural" 1.0)
               $sid)
             $sid)))))

(: (sn compound-each!) (-> Atom Bool))
(= (sn compound-each! $pairs)
   (if (== $pairs ())
       True
       (let ($head $tail) (decons-atom $pairs)
         (let ($compound $chead) $head
           (let* (($made (sn structural! $compound $chead))
                  ($rest (sn compound-each! $tail)))
             True)))))

(= (sn compound-edges! $tree)
   (sn compound-each! (sn compounds $tree)))

;; that/Tx complements unwrap to their content (single-arg T edges)
(= (sn unthat $n)
   (case $n
     (((sh (tag T $sub $roles $amr) $lbl (args ((arg $role $inner)))) $inner)
      ($other $other))))

;; first-person deixis: a pronoun claimer IS the source (one trust link)
(= (sn deixis $agent $sigma)
   (case $agent
     (((sh-atom (tag C i $roles $amr) $lbl) (sh-atom (tag C p NoRoles ()) $sigma))
      ($other $other))))

;; the -d! form carries an explicit DOMAIN (R2: conditional edges); the
;; plain form routes via domain-of -- same delegation pattern as weak-quantum
(= (sn ingest-stmt! $canon $neg $eid $sigma $w $kind)
   (sn ingest-stmt-d! $canon $neg $eid $sigma $w $kind (sn domain-of $canon)))
(= (sn ingest-stmt-d! $canon $neg $eid $sigma $w $kind $domain)
   (let* (($sid (sn sid $canon))
          ($h (sn rh $sid $sigma))
          ($r (if $neg 0.0 1.0))
          ($s (if $neg 1.0 0.0)))
     (with_mutex sn-commit
       (let* (($interned (sn intern! $sid $canon $domain $kind))
              ($from (if (== () (collapse (once (match &self (sn from $sid $e) True))))
                         (add-atom &self (sn from $sid $eid))
                         ()))
              ($compounded (sn compound-edges! $canon))
              ;; B1: step-3 extraction (occ/ctx from role fillers; additive)
              ($extracted (sn extract-args! $sid (sn args-of $canon))))
         (if (sn receipt! $sid $sigma $h)
             (let* (($fused (sn fuse-unit! $sid $r $s (sn config default-rate) $sigma $w))
                    ($touched (sn fr-touch! $sid))
                    ($gated (sn gates! $sid))
                    ;; R0: symmetric-licensed predicates mirror (proof-deduped)
                    ($symd (collapse (sn sym-edges! $sid))))
               $sid)
             ;; E2: duplicate receipt -> re-assertion averaging (flag-gated)
             (let* (($avg (sn reassert! $sid $r $s (sn config default-rate) $sigma $w))) $sid))))))

;; intern + provenance WITHOUT evidence -- the believe-class object-port path
(= (sn intern-only! $canon $eid)
   (let $sid (sn sid $canon)
     (with_mutex sn-commit
       (let* (($interned (sn intern! $sid $canon instance epistemic))
              ($from (if (== () (collapse (once (match &self (sn from $sid $e) True))))
                         (add-atom &self (sn from $sid $eid))
                         ()))
              ($compounded (sn compound-edges! $canon)))
         $sid))))

;; port fact, occ!-idiom dedup
(= (sn port! $sid $port)
   (with_mutex sn-commit
     (if (== () (collapse (once (match &self (sn port $sid $port) True))))
         (let $added (add-atom &self (sn port $sid $port)) True)
         False)))

;; O5/1.7: the channel table decides which ports an attitude verb feeds.
;; The resolved channel is passed in (the caller has both $amr and $albl
;; bound; resolving at the call site keeps this arity stable). M1 residues
;; (F3): the channel and first-person deixis are STORED, sigma-carrying.
(= (sn ingest-claim! $chan $agent $content $neg $eid $sigma $w)
   (let* (($claimer (sn deixis $agent $sigma))
          ($inner (case $chan
                    ((claim
                      (sn ingest-stmt! $content $neg $eid $sigma
                                       (* $w (sn config claimer-trust)) epistemic))
                     (believe
                      (sn intern-only! $content $eid))
                     (know
                      (sn ingest-stmt! $content $neg $eid $sigma
                                       (* $w (sn config know-trust)) epistemic))
                     (deny
                      (sn ingest-stmt! $content (not $neg) $eid $sigma
                                       (* $w (sn config claimer-trust)) epistemic)))))
          ($claimed (sn claimify-agent! $inner $claimer))
          ($attres (add-atom &self (sn att $inner $sigma $chan)))
          ($dres (if (== $claimer $agent) () (add-atom &self (sn deixis $inner $sigma speaker)))))
     $inner))

(= (sn conflict-verb? $tree)
   (case $tree
     (((sh (tag P $sub $roles $amr) $lbl $args) (== conflict (sn att-channel $amr $lbl)))
      ($other False))))

;; conflict-class (1.7, paper 7.1): "X slams Y" is testimony of a conflict
;; between X and Y, never truth about the topic. Emit the object-port
;; <SOURCE against TARGET> statement carrying the unit; the literal event
;; statement is kept but marked object-port (discourse record). The
;; "[against,for,of,over]/T TOPIC" x-argument becomes a ctx fact once
;; Task B1's extraction vocabulary is in place (paper 7.1 carries it).
(= (sn ingest-conflict! $canon $neg $eid $sigma $w)
   (case $canon
     (((sh (tag P $psub so $amr) $vlbl (args ((arg s $src) (arg o $tgt))))
       (let* (($atree (sh (tag P d so ()) "against" (args ((arg s $src) (arg o $tgt)))))
              ($asid (sn ingest-stmt! $atree $neg $eid $sigma $w epistemic))
              ($attres (add-atom &self (sn att $asid $sigma conflict)))
              ($ap (sn port! $asid object))
              ($lit (sn ingest-stmt! $canon $neg $eid $sigma $w epistemic))
              ($lp (sn port! $lit object)))
         $asid))
      ($other (sn ingest-stmt! $canon $neg $eid $sigma $w aleatory)))))

;; find the first conditional-classed x-arg trigger with a P-typed inner:
;; (CondX <sub> <inner>) or NoCond (the R2 dual-cue routing; fneg deferred
;; pending negative-term encoding -- outcome notes)
(= (sn cond-x $items)
   (if (== $items ())
       NoCond
       (let ($head $tail) (decons-atom $items)
         (case $head
           (((arg x (sh (tag T $tsub $tr $ta) $tl (args ((arg $ir $inner)))))
             (case $inner
               (((sh (tag P $ps $pr $pa) $plbl $pargs)
                 (let $sub (sn trig-sub $ta $tsub $tl)
                   (if (or (== $sub f) (or (== $sub c) (== $sub g)))
                       (CondX $sub $inner)
                       (sn cond-x $tail))))
                ($otherinner (sn cond-x $tail)))))
            ($otherarg (sn cond-x $tail)))))))

;; ---- R4: measured compound routing (1.7 shared-stamp; gated route-compounds)
;; the connective the reasoner keys on is the AMR SENSE, not the surface string
;; (the att-channel sense-first discipline, units.metta): a filled AMR slot is
;; primary; the label is the coarse-parse fallback. Senses normalize to the
;; INERT tokens conj|disj (NOT and|or -- those are live boolean operators that
;; reduce in head position, so a resolved sense returned as a value would
;; vanish; conj|disj survive as data) so "&"/"et"/a non-English conjunction
;; carrying the right synset still routes.
(sn conn-class "and" conj) (sn conn-class "et" conj) (sn conn-class "&" conj)
(sn conn-class "or" disj)
(= (sn conn-lbl $lbl)
   (case (collapse (once (match &self (sn conn-class $lbl $c) $c)))
     ((() NoConn)
      (($c) $c))))
(= (sn conn-of $amr $lbl)
   (case $amr
     (((amr $aid)
       (case (collapse (once (match &self (sn conn-class $aid $c) $c)))
         ((() (sn conn-lbl $lbl))
          (($c) $c))))
      ($other (sn conn-lbl $lbl)))))

;; a J-tagged root carries the clausal connective; resolve its sense, route
;; and|or, all else (and gate-off) fall through to the ordinary statement path.
(= (sn compound-conn $canon)
   (if (== 1 (sn cfg route-compounds 1))
       (case $canon
         (((sh (tag J $js $jr $ja) $jlbl $jargs) (sn conn-of $ja $jlbl))
          ($other NoConn)))
       NoConn))

;; AND-distribution: each P-typed conjunct interns as its OWN statement, and
;; ALL conjuncts additionally carry ONE shared stamp (the root's receipt hash),
;; so they read as common-ancestry -- disjoint=False (Mapping 1.7 shared-stamp).
(= (sn ingest-and! $canon $eid $sigma $w)
   (let $sharedh (sn rh (sn sid $canon) $sigma)
     (sn and-each! (sn args-of $canon) $sharedh $eid $sigma $w)))
(= (sn and-each! $items $sharedh $eid $sigma $w)
   (if (== $items ())
       ()
       (let ($head $tail) (decons-atom $items)
         (case $head
           (((arg $role (sh (tag P $ps $pr $pa) $plbl $pargs))
             (let* (($msid (sn ingest-stmt! (sh (tag P $ps $pr $pa) $plbl $pargs) False $eid $sigma $w aleatory))
                    ($shared (sn stamp! $msid $sharedh)))
               (cons-atom $msid (sn and-each! $tail $sharedh $eid $sigma $w))))
            ($other (sn and-each! $tail $sharedh $eid $sigma $w)))))))

;; OR: the sentence witnesses the disjunction, never a disjunct -- ONE
;; statement on the canonical "or" tree; or-view composes members on demand.
(= (sn ingest-or! $canon $neg $eid $sigma $w)
   (sn ingest-stmt! $canon $neg $eid $sigma $w aleatory))

(= (sn ingest-route! $canon $neg $eid $sigma $w)
   (let $conn (sn compound-conn $canon)
     (if (== $conn conj)
         (sn ingest-and! $canon $eid $sigma $w)
         (if (== $conn disj)
             (sn ingest-or! $canon $neg $eid $sigma $w)
             (let $cx (if (== 1 (sn cfg route-conditionals 1)) (sn cond-x (sn args-of $canon)) NoCond)
               (case $cx
                 (((CondX $sub $atree)
                   (sn ingest-cond! $sub $atree (sn host-minus-x $canon) $eid $sigma $w))
                  (NoCond
                   (if (sn conflict-verb? $canon)
                       (sn ingest-conflict! $canon $neg $eid $sigma $w)
                       (sn ingest-stmt! $canon $neg $eid $sigma $w aleatory))))))))))

;; mood routing (SNARS-SH Mapping 1.3): the captured speech act decides what an
;; utterance DOES, not just what it says. A parsed interrogative is a query
;; (the proposition is interned so it can be answered, but never asserted as
;; evidence); an imperative is a goal (desire); declaratives (and the v/d/n/e
;; defaults) flow to the ordinary belief path. The full form + mood are already
;; captured by the caller, so this only chooses the act.
(= (sn ingest-query! $canon $eid)
   (sn intern-only! $canon $eid))
(= (sn ingest-goal! $canon)
   (let $d (sn config default-rate)
     (goal! $canon ((desire $d)))))

;; declarative path: attitude reification, else the structural router
(= (sn ingest-decl! $canon $neg $eid $sigma $w)
   (case $canon
     (((sh (tag P d sr $amr) $albl (args ((arg s $agent) (arg r $content))))
       (sn ingest-claim! (sn att-channel $amr $albl) $agent (sn unthat $content) $neg $eid $sigma $w))
      ((sh (tag P d so $amr) $albl (args ((arg s $agent) (arg o (sh (tag T $tsub $trol $tamr) $tlbl (args ((arg $ro $content))))))))
       (sn ingest-claim! (sn att-channel $amr $albl) $agent $content $neg $eid $sigma $w))
      ($other (sn ingest-route! $canon $neg $eid $sigma $w)))))

(= (sn ingest-tree! $tree $eid $sigma $w)
   (let* (($pn (sn peel $tree))
          ($canon (sn pl-canon $pn))
          ($neg (sn pl-neg $pn))
          ($mood (sn pl-mood $pn))
          ($labeled (sn label-all! (sn labels $tree)))
          ;; SH full-form capture: the complete parsed utterance + its mood,
          ;; keyed to the proposition the canonical form chains over
          ($shcap (sn capture-sh! (sn sid $canon) $tree $mood)))
     (case $mood
       ((i (sn ingest-query! $canon $eid))
        (j (sn ingest-goal! $canon))
        ($other (sn ingest-decl! $canon $neg $eid $sigma $w))))))

(= (sn hb-root? $eid)
   (== () (collapse (once (match &self (hb subedge $eid $root) True)))))

(: (sn ingest!) (-> %Undefined% %Undefined% Number Number %Undefined%))
(= (sn ingest! $eid $sigma $trust $pparse)
   (match &self (hb tree $eid $tree)
     (if (sn hb-root? $eid)
         (sn ingest-tree! $tree $eid $sigma (* $trust $pparse))
         (empty))))

(: (sn ingest-all!) (-> %Undefined% Number Number Expression))
(= (sn ingest-all! $sigma $trust $pparse)
   (collapse (match &self (hb tree $eid $tree)
     (if (sn hb-root? $eid)
         (sn ingest-tree! $tree $eid $sigma (* $trust $pparse))
         (empty)))))

;; ---- fixture helpers ----
(= (sn approx $x $y $eps) (< (abs-math (- $x $y)) $eps))
(= (sn approx-op (Opinion $b1 $d1 $u1 $a1) (Opinion $b2 $d2 $u2 $a2) $eps)
   (and (sn approx $b1 $b2 $eps)
        (and (sn approx $d1 $d2 $eps)
             (and (sn approx $u1 $u2 $eps)
                  (sn approx $a1 $a2 $eps)))))

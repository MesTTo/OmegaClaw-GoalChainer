;;; SNARS module — Tf/Tc conditional layer + Tp/To goals (rule pack R2).
;;; Import via the snars.metta aggregator; load order lives there.
;;; Encoding ruling: a conditional is an ORDINARY statement
;;; (sh (tag P d so ()) "==>" (args ((arg s (sn-ref A)) (arg o (sn-ref B)))))
;;; in the conditional domain -- stored as the conditional opinion w_{B|A},
;;; never material implication (SLN 3.4 / J 9.7).

(= (sn cond-rules?) (== 1 (sn cfg cond-rules 1)))

;; trigger post-classification (coarse builds emit Tx for every trigger):
;; label -> effective subtype; genuine subtypes (rich parses, ACE-tier,
;; later sense keys) win first -- the A4 dual-cue discipline.
(sn trig-class "if" f)       (sn trig-class "unless" fneg)
(sn trig-class "because" c)  (sn trig-class "since" c)
(sn trig-class "although" g) (sn trig-class "though" g)
(sn trig-class "like" e)     (sn trig-class "as" e)
(sn trig-class "than" n)
(= (sn trig-sub $sub $lbl)
   (if (== $sub x)
       (case (collapse (once (match &self (sn trig-class $lbl $c) $c)))
         ((() x)
          (($c) $c)))
       $sub))

;; sense-first (the att-channel discipline): a filled AMR slot is the primary
;; key (the trig-class table is keyed by synset when the parser disambiguates);
;; the subtype char then the surface label are the coarse-parse fallbacks.
(= (sn trig-sub $amr $sub $lbl)
   (case $amr
     (((amr $aid)
       (case (collapse (once (match &self (sn trig-class $aid $c) $c)))
         ((() (sn trig-sub $sub $lbl))
          (($c) $c))))
      ($other (sn trig-sub $sub $lbl)))))

;; ---- x-slot mechanics (shared with B3's specifier lift) ----
(: (sn first-x) (-> Atom %Undefined%))
(= (sn first-x $items)
   (if (== $items ())
       NoSpec
       (let ($head $tail) (decons-atom $items)
         (case $head
           (((arg x $spec) $spec)
            ($other (sn first-x $tail)))))))

(: (sn strip-x) (-> Atom Expression))
(= (sn strip-x $items)
   (if (== $items ())
       ()
       (let ($head $tail) (decons-atom $items)
         (case $head
           (((arg x $spec) (sn strip-x $tail))
            ($other (cons-atom $head (sn strip-x $tail))))))))

;; rebuild the host minus its x-args, roles string rebuilt by canon (3.0f)
(= (sn host-minus-x (sh $tag $lbl (args $items)))
   (sn canon (sh $tag $lbl (args (sn strip-x $items)))))

;; intern + provenance WITHOUT receipts or evidence -- "if A then B"
;; witnesses neither A nor B, only the link (1.6 Tf)
(= (sn intern-ref! $tree $eid)
   (let* (($pn (sn peel $tree))
          ($canon (sn pl-canon $pn))
          ($sid (sn sid $canon)))
     (with_mutex sn-commit
       (let* (($interned (sn intern! $sid $canon instance aleatory))
              ($shcap (sn capture-sh! $sid $tree (sn pl-mood $pn)))
              ($from (if (== () (collapse (once (match &self (sn from $sid $e) True))))
                         (add-atom &self (sn from $sid $eid))
                         ())))
         $sid))))

;; conditional extraction (1.6 Tf/Tc/Tg; T+R principle): antecedent = the
;; trigger's inner P-tree, consequent = host minus the x-arg. Tf interns
;; both clauses receipt-free; Tc gives all three units with SHARED stamp
;; ancestry (1.7 -- the root receipt hash threaded); Tg (O3 resolved):
;; both units land, the edge takes ONE w-capped unit fq-split at the
;; concessive frequency + the exception-context seed.
(= (sn ingest-cond! $sub $atree $btree $eid $sigma $w)
   (let* (($asid (if (== $sub c)
                     (sn ingest-stmt! $atree False $eid $sigma $w epistemic)
                     (sn intern-ref! $atree $eid)))
          ($bsid (if (== $sub c)
                     (sn ingest-stmt! $btree False $eid $sigma $w epistemic)
                     (sn intern-ref! $btree $eid)))
          ($etree (sh (tag P d so ()) "==>" (args ((arg s (sn-ref $asid)) (arg o (sn-ref $bsid))))))
          ($esid (sn sid $etree)))
     (case $sub
       ((g
         ;; concessive: A and B both happened; the edge gets the split unit
         (let* (($au (sn ingest-stmt! $atree False $eid $sigma $w epistemic))
                ($bu (sn ingest-stmt! $btree False $eid $sigma $w epistemic))
                ($h (sn rh $esid $sigma))
                (($rq $sq) (sn fq-split "although" 1.0 0.0)))
           (with_mutex sn-commit
             (let* (($interned (sn intern! $esid $etree conditional aleatory))
                    ($rcpt (if (sn receipt! $esid $sigma $h)
                               (let $fused (sn input $esid $rq $sq (sn config default-rate) $sigma $w) True)
                               False))
                    ;; SLN 10.1 restructure signal arriving from syntax
                    ($seed (sn ctx! $esid $eid))
                    ($touched (sn fr-touch! $esid)))
               $esid))))
        ($othersub
         (sn ingest-stmt-d! $etree False $eid $sigma $w aleatory conditional))))))

;; Tp/To (1.6; authored trees and rich parses only -- coarse Tp/To parses
;; are mangled, probe 2026-06-12): purpose = object-port desire statement +
;; vacuous procedural "=/>" link (intended, never achieved); result = the
;; link + ONE positive unit on it + the consequence unit (an observed
;; outcome of <action =/> outcome>).
(= (sn ingest-purpose! $agent $acttree $goaltree $eid $sigma $w)
   (let* (($asid (sn ingest-stmt! $acttree False $eid $sigma $w epistemic))
          ($gsid (sn intern-ref! $goaltree $eid))
          ($dtree (sh (tag P d so ()) "desires" (args ((arg s $agent) (arg o (sn-ref $gsid))))))
          ($dsid (sn ingest-stmt! $dtree False $eid $sigma $w epistemic))
          ($ported (sn port! $dsid object))
          ($ltree (sh (tag P d so ()) "=/>" (args ((arg s (sn-ref $asid)) (arg o (sn-ref $gsid))))))
          ($lsid (sn intern-ref! $ltree $eid))
          ($ldom (with_mutex sn-commit
                   (let $cur (sn dom-of $lsid)
                     (if (== $cur conditional) True
                         (let* (($rm (collapse (match &self (sn domain $lsid $d) (remove-atom &self (sn domain $lsid $d)))))
                                ($ad (add-atom &self (sn domain $lsid conditional))))
                           True))))))
     $dsid))
(= (sn ingest-result! $acttree $outtree $eid $sigma $w)
   (let* (($asid (sn ingest-stmt! $acttree False $eid $sigma $w epistemic))
          ($osid (sn ingest-stmt! $outtree False $eid $sigma $w epistemic))
          ($ltree (sh (tag P d so ()) "=/>" (args ((arg s (sn-ref $asid)) (arg o (sn-ref $osid))))))
          ($lsid (sn ingest-stmt-d! $ltree False $eid $sigma $w aleatory conditional)))
     $osid))

;; (subgoals! lives in authoring.metta: it calls goal!, whose head compiles
;; later than this module -- the smart-dispatch placement rule)

;; modus ponens along a conditional edge (3.1 step 6; SLN 3.4): premise A +
;; (==> A B) grafts deduce(A, edge, a_B) INTO the existing consequent cell.
(= (|- (stmt $s1 $t1)
       (stmt $s2 (sh (tag P d so ()) "==>" (args ((arg s (sn-ref $sa)) (arg o (sn-ref $sb)))))))
   (if (and (sn cond-rules?) (and (== $s1 $sa) (sn disjoint $s1 $s2)))
       (let* (($ab (let (Ev $r $s $a) (sn evidence $sb) $a))
              ($op (sn deduce $s1 $s2 $ab)))
         (stmt (sn graft-into! $sb (mp $s1 $s2) $op $s1 $s2) (sn-ref $sb)))
       (empty)))

;; abductive mp (NAL-5 lib_nars precedent: B + (==> A B) |- A; the SL form is
;; invert-then-deduce, J Def 10.5 / SLN 3.5) -- the edge view is Bayes-
;; inverted at the antecedent's base rate, else synthesized (8.4 chain),
;; then ordinary deduction grafts into the ANTECEDENT's cell.
(= (|- (stmt $s1 $t1x)
       (stmt $s2 (sh (tag P d so ()) "==>" (args ((arg s (sn-ref $sa)) (arg o (sn-ref $sb)))))))
   (if (and (sn cond-rules?) (and (== $s1 $sb) (sn disjoint $s1 $s2)))
       (let* (($ax (sn aclamp (let (Ev $r $s $a) (sn evidence $sa) $a)))
              ($ay (sn aclamp (let (Ev $r2 $s2v $a2) (sn evidence $sb) $a2)))
              ((Opinion $eb $ed $eu $ea) (sn view $s2))
              ($pos (Opinion $eb $ed $eu $ay))
              ($neg (sn synth-else $pos $ax $ay))
              ($op (sn abduce-op (sn view $s1) $pos $neg $ax)))
         (stmt (sn graft-into! $sa (mpa $s1 $s2) $op $s1 $s2) (sn-ref $sa)))
       (empty)))

;; hypothetical syllogism (review amendment 2026-06-12 -- the heterogeneous-
;; chaining seam): (==> A B) + (==> B C) |- (==> A C), treating edge1's view
;; as the opinion-on-B-within-A's-context -- sound under the screening
;; assumption P(C|B,A)=P(C|B) (SLN 9.1 edge-compose; PLN book 5.2.2.2;
;; lib_pln's SyllogisticRuleGuard Implication is the lineage precedent).
;; Direction matters: no key-order canonicalization.
(= (|- (stmt $s1 (sh (tag P d so ()) "==>" (args ((arg s (sn-ref $sa)) (arg o (sn-ref $sb))))))
       (stmt $s2 (sh (tag P d so ()) "==>" (args ((arg s (sn-ref $sb)) (arg o (sn-ref $sc)))))))
   (if (and (sn cond-rules?) (and (not (== $sa $sc)) (sn disjoint $s1 $s2)))
       (let* (($ac (let (Ev $r $s $a) (sn evidence $sc) $a))
              ($op (sn deduce $s1 $s2 $ac))
              ($tree (sh (tag P d so ()) "==>" (args ((arg s (sn-ref $sa)) (arg o (sn-ref $sc)))))))
         (stmt (sn graft! $tree (hs $s1 $s2) $op conditional $s1 $s2) $tree))
       (empty)))

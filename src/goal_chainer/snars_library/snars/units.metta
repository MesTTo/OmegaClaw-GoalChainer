;;; SNARS module — evidence-modulation tables (Mapping 2.4, 1.7/O5).
;;; Import via the snars.metta aggregator; load order lives there.

;; ---- 2.4 quantifier table: frequency testimony, ONE observation split ----
;; fractionally across the poles: Evidence(+f_q*w, +(1-f_q)*w). [O11: values
;; are the doctrine's proposal — calibration anchors: Kent 1964 (Words of
;; Estimative Probability); Mosteller & Youtz 1990 (Stat. Sci.); IPCC
;; calibrated-language guidance (Mastrandrea et al. 2010); GenericsKB
;; quantifier annotations at p1. Calibrate later — change data, not code.]
;; "some" is deliberately ABSENT: existential, not frequency (2.4).
(sn fq "all" 1.0)
(sn fq "most" 0.9)
(sn fq "many" 0.75)
(sn fq "few" 0.15)
(sn fq "no" 0.0)
;; Tg ruling (O3 resolved 2026-06-12): a concessive is fractional frequency
;; testimony on the conditional it defeats -- "although" leaks the speaker's
;; world-model (A usually yields not-B, yet this time it did not). Sits
;; between "few" (.15) and "may" (.4); denial-of-expectation semantics
;; (Koenig 1986; Lakoff 1971). Calibratable data, never code.
(sn fq "although" 0.25)

;; single-valued lookup (the cfg idiom, config.metta): unknown word or
;; no option -> NoSplit, never a prune
(= (sn fq-of $q)
   (if (== $q NoQuant)
       NoSplit
       (case (collapse (match &self (sn fq $q $f) $f))
         ((() NoSplit)
          (($f) $f)))))

;; split a base unit (r0,s0) by quantifier: the quantified generic is one
;; observation of total weight w = r0+s0 redistributed across the poles
(: (sn fq-split) (-> %Undefined% Number Number Expression))
(= (sn fq-split $q $r0 $s0)
   (let $f (sn fq-of $q)
     (if (== $f NoSplit)
         ($r0 $s0)
         (let $w (+ $r0 $s0)
           ((* $f $w) (* (- 1.0 $f) $w))))))

;; ---- 2.4 hedge table: weight scaling, the second uncertainty channel ----
;; [O2: calibrate later -- data, not code; anchors as for fq. Register note
;; (review 2026-06-13): these weights encode the EVIDENTIAL reading of
;; modals in loose prose; ACE-tier modal operators (must/may as obligation/
;; permission, possible/necessary) are alethic/deontic and route to the
;; crisp layer -- never through hedge-p.]
(sn hedge "must" 1.0)
(sn hedge "will" 0.9)
(sn hedge "probably" 0.7)
(sn hedge "may" 0.4)
(sn hedge "might" 0.4)
(sn hedge "could" 0.25)

(= (sn hedge-p $h)
   (if (== $h NoHedge)
       1.0
       (case (collapse (match &self (sn hedge $h $p) $p))
         ((() 1.0)
          (($p) $p)))))

;; 1.5 Mm: "will" forecasts -- the statement is a prediction the world will
;; grade (Task C2 wires the grading); immutable marker, occ!-idiom dedup
(= (sn predicted? $sid)
   (not (== () (collapse (once (match &self (sn predicted $sid) True))))))
(= (sn predicted! $sid)
   (with_mutex sn-commit
     (if (sn predicted? $sid)
         True
         (let $a (add-atom &self (sn predicted $sid)) True))))

;; ---- E2: re-assertion averaging + 9.7 push gates (flag-gated, default OFF) ----
;; SLN 9.2 overlap policy beyond skip: unfuse + average + refuse (J Def 13.1 /
;; Def 12.7 via Thm 12.3 -- a novel composition of two textbook operators; see
;; the kernel comment). Only the re-asserting source's contribution moves.
(= (sn reassert! $sid $r $s $a $sigma $trust)
   (if (== 1 (sn config reassert-avg))
       (sn_ev_reassert $sid $sigma $r $s $a $trust)
       $sid))

;; SLN 9.7 governance: a push fires only when the statement's surprise clears
;; the tracked quantile (the DC/FR1 channels join when their producers land).
(= (sn gate-note! $sid)
   (let* (($v (sn surprise $sid))
          ($tracked (sn_q_add surprise (sn config push-q) $v))
          ($thr (sn_q_at surprise)))
     (if (>= $v $thr)
         (let $a (with_mutex sn-commit
                   (if (== () (collapse (match &self (sn push $sid) True)))
                       (let $b (add-atom &self (sn push $sid)) True)
                       True))
           pushed)
         quiet)))
(= (sn gates! $sid)
   (if (== 1 (sn config gates)) (sn gate-note! $sid) quiet))

;; ---- SH mood (speech act) reader + classifiers ----
;; the predicate subtype the canonical form normalizes away, captured as
;; full-form metadata so SNARS routes on the complete SH notation: v
;; declarative (the default when unmarked), i interrogative -> query/hole, j
;; imperative -> goal/desire, n nominal/copular, e existential -> instance.
(= (sn mood-of $sid)
   (case (collapse (once (match &self (sn mood $sid $m) $m)))
     ((() v)
      (($m) $m))))
;; v (Pv declarative) and d (the canonical placeholder) are the default; only
;; the routable non-default moods earn a (sn mood ...) index row (the complete
;; subtype is always retained in the (sn sh ...) full form regardless).
(= (sn mood-default? $mood)
   (or (== $mood NoMood) (or (== $mood d) (== $mood v))))
(= (sn interrogative? $sid) (== (sn mood-of $sid) i))
(= (sn imperative? $sid) (== (sn mood-of $sid) j))
(= (sn existential? $sid) (== (sn mood-of $sid) e))

;; ---- C2: anticipation grading (Mapping step 6) ----
;; a predicted statement's next EXTERNAL unit routes through the prequential
;; outcome! hook (the prediction is scored BEFORE it sees its own outcome --
;; the Dawid 1984 discipline already encoded there), and the "will" marker
;; resolves to (sn anticipation <sid> confirmed|disconfirmed|ungraded).
(= (sn grade-prediction! $sid $r $s $a $sigma $trust)
   (let* (((OUTCOME $osid $phat $chat $y $osig $der) (sn outcome! $sid $r $s $a $sigma $trust))
          ($verdict (if (== $y 1.0) confirmed (if (== $y 0.0) disconfirmed ungraded)))
          ($swap (with_mutex sn-commit
                   (let* (($rm (collapse (match &self (sn predicted $sid)
                                           (remove-atom &self (sn predicted $sid)))))
                          ($add (add-atom &self (sn anticipation $sid $verdict))))
                     True))))
     $sid))

;; the fuse router shared by believe! and ingest-stmt!: an external unit on a
;; predicted statement grades it; everything else fuses plainly (internal
;; sigmas -- derived/weak/eternal/... -- never grade, never self-fulfil).
(= (sn fuse-unit! $sid $r $s $a $sigma $trust)
   (if (and (sn predicted? $sid) (not (sn internal-sigma? $sigma)))
       (sn grade-prediction! $sid $r $s $a $sigma $trust)
       (sn input $sid $r $s $a $sigma $trust)))

;; ---- 1.7/O5 attitude-verb channel table (paper 7.1 seed lemma sets) ----
;; Channel semantics = factivity, quantified (Kiparsky & Kiparsky 1970;
;; veridicality classes; FactBank as future calibration corpus):
;; claim-class -> object-port + truth-port (the full channel)
(sn att-class "say" claim)
(sn att-class "claim" claim)
;; believe-class -> object-port only (belief != assertion)
(sn att-class "think" believe)
(sn att-class "believe" believe)
;; know-class -> object-port + boosted truth-port (factive)
(sn att-class "know" know)
;; deny-class -> object-port + complemented truth-port (anti-veridical)
(sn att-class "deny" deny)
;; conflict-class -> <SOURCE against TARGET> object-port statements (1.7)
(sn att-class "accuse" conflict)
(sn att-class "arrest" conflict)
(sn att-class "clash" conflict)
(sn att-class "condemn" conflict)
(sn att-class "kill" conflict)
(sn att-class "slam" conflict)
(sn att-class "warn" conflict)

;; SENSE rows -- the primary key (0.1 rich-cue): canonical WordNet synset ids
;; exactly as wordnet_sense.resolve emits them (pinned 2026-06-13 by running
;; the module: say->state-v-01, arrest->collar-v-01, clash->collide-v-03 are
;; most-frequent-synset canonicalizations; reckon->think-v-02, hence BOTH
;; think senses sit in believe-class -- synonym unification happens per
;; synset, not per lemma)
(sn att-class claim-v-01 claim)
(sn att-class state-v-01 claim)
(sn att-class think-v-01 believe)
(sn att-class think-v-02 believe)
(sn att-class believe-v-01 believe)
(sn att-class know-v-01 know)
(sn att-class deny-v-01 deny)
(sn att-class accuse-v-01 conflict)
(sn att-class collar-v-01 conflict)
(sn att-class collide-v-03 conflict)
(sn att-class condemn-v-01 conflict)
(sn att-class kill-v-01 conflict)
(sn att-class slam-v-01 conflict)
(sn att-class warn-v-01 conflict)

;; surface->lemma bridge -- the SENSELESS-TREE FALLBACK only (fixtures,
;; believe! authoring trees, coarse parses, WordNet misses); doctrine: "use
;; lemma edges, not inflections" -- these rows are degradation handling and
;; go dead as the senseless paths disappear
(sn att-alias "says" "say")     (sn att-alias "said" "say")
(sn att-alias "claims" "claim") (sn att-alias "claimed" "claim")
(sn att-alias "thinks" "think") (sn att-alias "believes" "believe")
(sn att-alias "knows" "know")   (sn att-alias "knew" "know")
(sn att-alias "denies" "deny")  (sn att-alias "denied" "deny")
(sn att-alias "accuses" "accuse") (sn att-alias "accused" "accuse")
(sn att-alias "arrests" "arrest") (sn att-alias "arrested" "arrest")
(sn att-alias "clashes" "clash")  (sn att-alias "clashed" "clash")
(sn att-alias "condemns" "condemn") (sn att-alias "condemned" "condemn")
(sn att-alias "kills" "kill")   (sn att-alias "killed" "kill")
(sn att-alias "slams" "slam")   (sn att-alias "slammed" "slam")
(sn att-alias "warns" "warn")   (sn att-alias "warned" "warn")

(= (sn att-lemma $lbl)
   (case (collapse (match &self (sn att-alias $lbl $lemma) $lemma))
     ((() $lbl)
      (($l) $l))))

;; label-keyed lookup (the fallback path); unknown attitude verbs keep the
;; full channel (today's behaviour; the 5.2 worked example ingests
;; "observe" with truth-port + object-port)
(= (sn att-channel-lbl $lbl)
   (let $lemma (sn att-lemma $lbl)
     (case (collapse (match &self (sn att-class $lemma $c) $c))
       ((() claim)
        (($c) $c)))))

;; sense-first dispatch: a filled AMR slot (WordNet synset / QID) is the
;; primary key; an unknown synset or an empty slot falls back to the label
(= (sn att-channel $amr $lbl)
   (case $amr
     (((amr $aid)
       (case (collapse (match &self (sn att-class $aid $c) $c))
         ((() (sn att-channel-lbl $lbl))
          (($c) $c))))
      ($other (sn att-channel-lbl $lbl)))))

;; parser-fed seam: peel notes as data (consumed when the TNF determiner/aux
;; capture feeds quantifier words; until then believe!/ingest options drive)
(= (sn peel-notes $tree) (sread (py-call (goalchainer_snars.snars_peel_notes $tree))))

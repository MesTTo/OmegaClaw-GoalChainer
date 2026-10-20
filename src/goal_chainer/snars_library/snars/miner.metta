;;; SNARS module — the rule miner (Wave K5; adapted from hyperon-miner's apriori
;;; core, /home/user/Dev/hyperon-miner). Import via the snars.metta
;;; aggregator; load order lives there (AFTER rulekit + sbc, whose rows/chainer
;;; it feeds).
;;;
;;; The miner closes the self-improvement loop: it reads the supported statement
;;; base (sn supported?: a receipt or a proof), DISCOVERS frequent inference-
;;; shaped regularities (apriori support + confidence), and PROPOSES them as R5
;;; registry rows -- which the consolidated
;;; backward chainer (sbc / sn prove) then uses unchanged. The headline is the
;;; reference miner's `test_transitivity`: from raw `(cop x y)` pairs the miner
;;; recovers the transitivity conjunction `(cop x m) & (cop m y) |- (cop x y)`
;;; -- i.e. the system mints its own license row from data, the data-not-code
;;; doctrine gaining a data SOURCE. Mining stats ride along as the proposed
;;; rule's interestingness record (support, hits, confidence); seeding the trust
;;; ledger's Beta cell from them (emp-tv, support-capped so low-support mines
;;; cannot arrive over-confident) is the documented K2-interacting upgrade --
;;; it needs the per-(rule, conclusion-pred-key) cell, resolved only at firing.
;;;
;;; v0 is MeTTa-native (support counting via collapse; the foldall match-count
;;; idiom and hyperon-miner's Prolog apriori core are the perf upgrades). The
;;; mined family here is binary-copula transitivity (the license-row proposer);
;;; conjunction-expansion to arbitrary rule shapes and PatternCounter's SH-shape
;;; (trigger/attitude) gap mining are the next families.

;; min confidence (hits/chains) for a transitivity proposal to be minted
(= (sn config mine-conf) 0.5)
;; cap on emp-tv seed counts (low-support mines cannot over-confide; see K2)
(= (sn config mine-seed-cap) 8.0)

(@doc (sn support)
  (@desc "Apriori support of a typed-SH pattern: the number of supported statements (a receipt or a proof) that match it, each counted once however many receipts or proofs it has. The miner's counting primitive (anti-monotone under specialization).")
  (@params ((@param "Typed SH pattern with MeTTa variables in arg positions")))
  (@return "Match count"))

(@doc (sn mine!)
  (@desc "Mine every binary copula among the supported statements for the transitivity license at minimum support ms (K5): for each copula, count middle-term chains (cop x m)&(cop m y) of two supported statements and how many are closed by a supported direct (cop x y); if chains>=ms and confidence>=mine-conf, propose the registry row (sn rw (mt cop) ded-shape ...) -- the consolidated chainer then uses it. Idempotent (re-mining an already-proposed copula is a no-op). Returns the (sn mined ...) record per proposal.")
  (@params ((@param "Minimum support (chain count) ms")))
  (@return "(sn mined NAME COP CHAINS HITS CONF) per proposed rule"))

(@doc (sn mine-trans!)
  (@desc "Mine ONE copula for the transitivity license at minimum support ms (K5). The per-copula core of mine!.")
  (@params ((@param "Copula label") (@param "Minimum support ms")))
  (@return "(sn mined ...) record if proposed, else empty"))

(@doc (sn proposals)
  (@desc "Reflectivity (K5): the rules the miner proposed from data -- the system reading what it learned, distinct from hand-authored rows. Each (sn mined NAME COP CHAINS HITS CONF).")
  (@params ())
  (@return "(sn mined ...) record per mined rule"))

(sn (function support))
(sn (function mine!))
(sn (function mine-trans!))
(sn (function proposals))

;; data heads minted by the miner (phantom-call lint exemptions)
(mb-lint-data-head mt)
(mb-lint-data-head Mined)

;; ---- apriori support: anti-monotone count of pattern matches ----
;; Every count below reads supported statements only, each once: support is an
;; existence test on the statement, so two receipts or two proofs make one
;; match. A conditional's endpoint or a parsed query names a statement without
;; observing it, so it counts toward no pattern, chain or closing edge. A
;; derived statement counts through its proof, which is provenance, not an
;; independent observation: a closing edge deduced from the chain it closes
;; counts as a hit.
(: (sn support) (-> %Undefined% Number))
(= (sn support $pat)
   (size-atom (collapse (match &self (sn stmt $s $pat) (if (sn supported? $s) $s (empty))))))

;; ---- transitivity mining (the license-row proposer) ----
;; CHAINS: distinct middle-term paths x->m->y (m,x,y distinct) under copula COP,
;; both statements supported.
(= (sn trans-chains $cop)
   (size-atom (collapse
     (match &self (, (sn stmt $s1 (sh (tag P d so ()) $cop (args ((arg s $x) (arg o $m)))))
                     (sn stmt $s2 (sh (tag P d so ()) $cop (args ((arg s $m) (arg o $y))))))
       (if (and (sn supported-pair? $s1 $s2) (and (not (== $x $m)) (and (not (== $m $y)) (not (== $x $y)))))
           ($x $m $y) (empty))))))

;; HITS: chains additionally closed by a supported direct edge x->y (transitivity holds).
;; The chain is a binary conjunction (verified to match); closure is a nested
;; existence check on the bound (x,y) -- robuster than a 3-way comma match.
(= (sn trans-edge? $cop $x $y)
   (not (== () (collapse (once (match &self (sn stmt $s3 (sh (tag P d so ()) $cop (args ((arg s $x) (arg o $y)))))
                                 (if (sn supported? $s3) True (empty))))))))
(= (sn trans-hits $cop)
   (size-atom (collapse
     (match &self (, (sn stmt $s1 (sh (tag P d so ()) $cop (args ((arg s $x) (arg o $m)))))
                     (sn stmt $s2 (sh (tag P d so ()) $cop (args ((arg s $m) (arg o $y))))))
       (if (and (sn supported-pair? $s1 $s2)
                (and (not (== $x $m)) (and (not (== $m $y)) (and (not (== $x $y)) (sn trans-edge? $cop $x $y)))))
           ($x $m $y) (empty))))))

;; add the transitivity registry row for COP. Isolated in its own helper so the
;; unbound pattern variables $x/$m/$y stay clause-local (mixing a variable-
;; bearing add-atom with a second add in one let* drops the second -- probed
;; 2026-06-13). The stored premise/conclusion variables are fresh, exactly as a
;; hand-authored (sn rw ...) row -- the chainer rides it unchanged.
(= (sn add-trans-row! $rname $cop)
   (add-atom &self (sn rw $rname ded-shape
     (sh (tag P d so ()) $cop (args ((arg s $x) (arg o $m))))
     (sh (tag P d so ()) $cop (args ((arg s $m) (arg o $y))))
     (sh (tag P d so ()) $cop (args ((arg s $x) (arg o $y)))))))

;; propose the transitivity rule for COP (idempotent), recording the mining
;; stats. The record is STORED as (sn mined ...) -- a space fact, matched as a
;; pattern -- but RETURNED as the data tuple (Mined ...): a naked (sn mined ...)
;; would dispatch the sn/N function (no `mined` clause) and reduce to empty,
;; masking the stored fact (probe-confirmed 2026-06-13; the ask!/(stmt ...)
;; idiom -- (sn ...) heads are functions, values use data heads).
(= (sn propose-trans! $cop $chains $hits $conf)
   (let $rname (mt $cop)
     (if (not (== () (collapse (once (match &self (sn mined $rname $a $b $cc $dd) True)))))
         (match &self (sn mined $rname $a2 $b2 $cc2 $dd2) (Mined $rname $a2 $b2 $cc2 $dd2))
         (let* (($rec (add-atom &self (sn mined $rname $cop $chains $hits $conf)))
                ($row (sn add-trans-row! $rname $cop))
                ($seed (sn mine-seed! $rname $cop $hits (- $chains $hits))))
           (Mined $rname $cop $chains $hits $conf)))))

;; emp-tv seed: the mining statistics become the proposed rule's INITIAL trust-
;; ledger Beta cell -- keyed ((rw name), conclusion pred-key = the copula), the
;; exact cell (sn rule-p)/(sn rule-sample) read at firing. hits -> positive,
;; misses (chains-hits) -> negative, each CAPPED at mine-seed-cap so a low-
;; support mine cannot arrive over-confident (the K2 interaction). So a mined
;; rule starts at its measured reliability instead of the vacuous 1.0 prior, and
;; the Thompson sampler explores it accordingly.
(= (sn mine-seed! $name $cop $hits $misses)
   (let* (($cap (sn config mine-seed-cap))
          ($r (min $hits $cap))
          ($s (min $misses $cap)))
     (sn_tr_add (rw $name) $cop $r $s)))

(: (sn mine-trans!) (-> %Undefined% Number %Undefined%))
(= (sn mine-trans! $cop $ms)
   (let* (($chains (sn trans-chains $cop))
          ($hits (sn trans-hits $cop)))
     (if (and (>= $chains $ms) (> $hits 0))
         (let $conf (/ $hits $chains)
           (if (>= $conf (sn config mine-conf))
               (sn propose-trans! $cop $chains $hits $conf)
               (empty)))
         (empty))))

;; mine every DISTINCT binary copula among the supported statements (idempotent
;; per copula). The copula list is deduped (unique-atom) so each is mined once.
(: (sn mine!) (-> Number %Undefined%))
(= (sn mine! $ms)
   (let $cops (unique-atom (collapse (match &self (sn stmt $s (sh (tag P d so ()) $cop (args ((arg s $x) (arg o $y)))))
                                       (if (sn supported? $s) $cop (empty)))))
     (let $c (superpose $cops)
       (sn mine-trans! $c $ms))))

;; reflectivity: the rules the miner proposed (the system reading what it
;; learned). Returns (Mined ...) data tuples (a (sn mined ...) value would
;; dispatch to empty -- see propose-trans!).
(= (sn proposals)
   (match &self (sn mined $rname $cop $chains $hits $conf)
     (Mined $rname $cop $chains $hits $conf)))

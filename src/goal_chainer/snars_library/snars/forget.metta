;;; SNARS module — split from the snars.metta monolith (2026-06-12).
;;; Import via the snars.metta aggregator; load order lives there.

;; ---- forgetting = attention-gated eviction (v2 P4; Mapping 3.1 step 7) ----
;; doctrine: receipts are ground truth, derived statements a materialized view.
;; A derivation with no receipts and an all-cold concept neighborhood is
;; re-derivable on demand, so it is safe cache to evict. The act value already
;; carries recency (lambda^age), so "cold key" subsumes the age test.
;;
;; CONFIGURATION. Forgetting is OFF by default — a knowledge base never evicts
;; unless the operator opts in. The switch is a space data atom (janus-free,
;; single-valued — the frozen? idiom), never a config redefinition:
;;   (sn forget-enable!)  / (sn forget-disable!)   global on/off
;;   (sn pin! sid)        / (sn unpin! sid)         protect one statement
;;   (sn config forget-act)                         coldness threshold when on
;; Receipts are ALWAYS protected (ground truth), enabled or not. So "I never
;; want to forget" is simply the default: do nothing.
(= (sn forget-enabled?)
   (not (== () (collapse (once (match &self (sn forget-on) True))))))
(= (sn forget-enable!)
   (if (sn forget-enabled?) True (let $a (add-atom &self (sn forget-on)) True)))
(= (sn forget-disable!)
   (let $r (collapse (match &self (sn forget-on) (remove-atom &self (sn forget-on)))) True))

(= (sn pinned? $sid)
   (not (== () (collapse (once (match &self (sn pinned $sid) True))))))
(= (sn pin! $sid)
   (if (sn pinned? $sid) True (let $a (add-atom &self (sn pinned $sid)) True)))
(= (sn unpin! $sid)
   (let $r (collapse (match &self (sn pinned $sid) (remove-atom &self (sn pinned $sid)))) True))

(= (sn cold? $key) (< (sn act $key) (sn config forget-act)))

(= (sn keys-cold? $sid)
   (case (collapse (match &self (sn stmt $sid (sh (tag P d so $amr) $cop (args ((arg s $x) (arg o $y)))))
                     (and (sn cold? (sn term-key $x)) (sn cold? (sn term-key $y)))))
     ((() True)            ;; non-copula or absent: nothing to keep warm
      (($r) $r))))

;; evictable = forgetting is on, the statement is derived (has a proof), carries
;; NO receipt (never directly observed), is not pinned, and its keys are cold
(= (sn evictable? $sid)
   (and (sn forget-enabled?)
        (and (not (sn pinned? $sid))
             (and (not (== () (collapse (match &self (sn proof $sid $p) True))))
                  (and (== () (collapse (match &self (sn receipt $sid $sig $h) True)))
                       (sn keys-cold? $sid))))))

;; remove every fact about a derived statement, then its cell — collected first,
;; removed outside the matcher (the immutability lint rule: no remove in a query)
(= (sn forget-one! $sid)
   (with_mutex sn-commit
     (let* (($f1 (collapse (match &self (sn stmt $sid $t) (remove-atom &self (sn stmt $sid $t)))))
            ($f2 (collapse (match &self (sn proof $sid $p) (remove-atom &self (sn proof $sid $p)))))
            ($f3 (collapse (match &self (sn domain $sid $d) (remove-atom &self (sn domain $sid $d)))))
            ($f4 (collapse (match &self (sn kind $sid $k) (remove-atom &self (sn kind $sid $k)))))
            ($f5 (collapse (match &self (sn sub $sk $sid) (remove-atom &self (sn sub $sk $sid)))))
            ($f6 (collapse (match &self (sn obj $ok $sid) (remove-atom &self (sn obj $ok $sid)))))
            ($f6b (collapse (match &self (sn rk $r $k $sid) (remove-atom &self (sn rk $r $k $sid)))))
            ($f7 (collapse (match &self (sn stamp $sid $h) (remove-atom &self (sn stamp $sid $h)))))
            ($cell (sn_ev_del $sid)))
       $sid)))

;; evict up to a budget; returns how many were forgotten. A no-op (0) when
;; forgetting is disabled — the explicit guarantee that the KB never shrinks.
(: (sn forget!) (-> Number Number))
(= (sn forget! $budget)
   (if (not (sn forget-enabled?))
       0
       (let $victims (sn fr-take $budget
                       (collapse (match &self (sn proof $sid $p)
                         (if (sn evictable? $sid) $sid (empty)))))
         (let $done (collapse (let $v (superpose $victims) (sn forget-one! $v)))
           (size-atom $done)))))

